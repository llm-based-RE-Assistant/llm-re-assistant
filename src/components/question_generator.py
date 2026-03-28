"""
src/components/question_generator.py
=====================
RE Assistant — Iteration 3 (fixed) | University of Hildesheim
Proactive Follow-Up Question Generator

Fix log (applied before Iteration 4)
--------------------------------------
FIX-A  Hard-coded question templates are REMOVED as the primary question source.
       Your concern was correct: template questions are context-blind.  They tell
       the LLM what to ask regardless of what the user just said, which breaks the
       conversational flow and causes users to give shorter answers.

FIX-B  New primary mode: LLM-GENERATED questions.
       ProactiveQuestionGenerator now calls the LLM with a meta-prompt that has
       full access to (a) the conversation history summary, (b) the gap category
       to probe, and (c) the project context.  The result is a single, targeted,
       context-aware question that feels like a natural continuation of the
       conversation rather than a scripted interrogation.

FIX-C  Templates are KEPT as a fast fallback for cases where:
         - no LLM provider is available (unit tests, offline mode)
         - the LLM meta-call fails
       This preserves backward-compatibility and ablation study support.

FIX-D  FR-aware priority: when functional_count < MIN_FUNCTIONAL_REQS, the
       generator always targets the "functional" gap first, overriding the
       normal critical→important→optional ordering.

Architecture (updated)
----------------------
  GapReport + ConversationState  →  ProactiveQuestionGenerator.generate()
    → LLM meta-prompt call (primary)  OR  template lookup (fallback)
    → FollowUpQuestion
    → injected into PromptArchitect.extra_context
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from gap_detector import GapReport, CategoryGap, GapSeverity
    from conversation_state import ConversationState


# ---------------------------------------------------------------------------
# Fallback question templates (retained as backup only — see FIX-A/C)
# ---------------------------------------------------------------------------

FALLBACK_TEMPLATES: dict[str, list[str]] = {
    "purpose": [
        "What specific problem does {project_name} solve, and why is an automated software system the right solution?",
        "What does success look like for {project_name} — how will you know the system has achieved its purpose?",
    ],
    "scope": [
        "What is explicitly OUT of scope for {project_name}? What should the system not do?",
        "Where does {project_name} end and another system or manual process begin?",
    ],
    "stakeholders": [
        "Who are the different types of users of {project_name}, and how do their needs differ?",
        "Besides end users, who else has an interest in {project_name}?",
    ],
    "functional": [
        "What are the three most important things a user must be able to DO with {project_name}?",
        "Walk me through a typical user journey — from opening the system to completing their main task.",
        "Are there any automated processes {project_name} should perform without user interaction?",
    ],
    "use_cases": [
        "Can you describe a concrete scenario where a user achieves their goal using {project_name} step by step?",
        "What happens when something goes wrong — for example, if the user makes a mistake?",
    ],
    "business_rules": [
        "Are there any legal or regulatory requirements {project_name} must satisfy (e.g. GDPR, HIPAA)?",
        "What business rules or policies must the system enforce?",
    ],
    "performance": [
        "How quickly must {project_name} respond to a typical user request? Please give a specific number (e.g. under 2 seconds).",
        "How many concurrent users do you expect at peak load?",
    ],
    "usability": [
        "What is the technical skill level of the typical user of {project_name}?",
        "Are there any accessibility requirements?",
    ],
    "security_privacy": [
        "What types of sensitive or personal data will {project_name} handle, and who should have access?",
        "How must users authenticate — username/password, SSO, MFA, or something else?",
    ],
    "reliability": [
        "What is the acceptable downtime for {project_name}? For example, 99.9% uptime means ~8.7 hours downtime per year.",
        "How quickly must {project_name} recover after an outage?",
    ],
    "compatibility": [
        "Which operating systems, browsers, or devices must {project_name} support?",
        "Does {project_name} need to integrate with any existing systems?",
    ],
    "maintainability": [
        "How often do you expect {project_name} to receive updates after launch?",
        "What team will maintain {project_name}?",
    ],
    "scalability": [
        "If {project_name} is successful and user numbers double, how should the system handle that growth?",
    ],
    "interfaces": [
        "What external services or APIs does {project_name} need to call or receive data from?",
    ],
    "data_requirements": [
        "What are the main types of data {project_name} will create, store, and manage?",
    ],
    "constraints": [
        "Are there any technology choices already decided — e.g. a required programming language, database, or cloud platform?",
    ],
    "assumptions": [
        "What assumptions are you making that, if wrong, would change the requirements significantly?",
    ],
    "testability": [
        "How will you verify that {project_name} meets its requirements? What does a passing acceptance test look like?",
    ],
    "deployment": [
        "Where will {project_name} be deployed — on-premise servers, a specific cloud provider, or both?",
    ],
}


# ---------------------------------------------------------------------------
# Meta-prompt for LLM-generated questions (FIX-B)
# ---------------------------------------------------------------------------

_META_PROMPT_TEMPLATE = """\
You are a requirements engineering assistant helping to elicit a complete \
Software Requirements Specification (SRS).

PROJECT: {project_name}
CONVERSATION SUMMARY (last {n_turns} turns):
{history_summary}

REQUIREMENTS COLLECTED SO FAR:
  Functional: {fr_count}
  Non-functional: {nfr_count}

TARGET GAP: {gap_label} ({gap_description})
Gap severity: {gap_severity}

TASK:
Generate exactly ONE short, open-ended elicitation question that:
1. Naturally continues the conversation above (references what was just said if possible)
2. Targets the gap category: {gap_label}
3. Is specific to {project_name}, not generic
4. Is concise — one sentence, no sub-bullets
5. Does NOT repeat a question already asked in the conversation

Reply with ONLY the question text.  No preamble, no explanation, no quotes."""


def _build_history_summary(state: "ConversationState", max_turns: int = 4) -> tuple[str, int]:
    """Return a text summary of the last N turns for the meta-prompt."""
    turns = state.turns[-max_turns:]
    lines = []
    for t in turns:
        u = t.user_message[:200].replace("\n", " ")
        a = t.assistant_message[:200].replace("\n", " ")
        lines.append(f"  User: {u}")
        lines.append(f"  Assistant: {a}")
    return "\n".join(lines) if lines else "  (no turns yet)", len(turns)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FollowUpQuestion:
    """A single generated follow-up question targeting a specific gap."""
    question_id:    str
    category_key:   str
    category_label: str
    question_text:  str
    severity:       str
    is_partial:     bool
    rationale:      str = ""
    source:         str = "llm"   # "llm" | "template"

    def to_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "category_key": self.category_key,
            "category_label": self.category_label,
            "question_text": self.question_text,
            "severity": self.severity,
            "is_partial": self.is_partial,
            "rationale": self.rationale,
            "source": self.source,
        }


@dataclass
class QuestionSet:
    """All follow-up questions generated for a single turn."""
    session_id:      str = ""
    turn_id:         int = 0
    total_gaps:      int = 0
    addressed_gaps:  int = 0
    questions:       list[FollowUpQuestion] = field(default_factory=list)
    primary_question: Optional[FollowUpQuestion] = None

    @property
    def has_questions(self) -> bool:
        return bool(self.questions)


class QuestionTracker:
    """Tracks which question IDs and category keys have been asked this session."""

    def __init__(self):
        self._asked_ids: set[str]          = set()
        self._category_counts: dict[str, int] = {}

    def is_asked(self, question_id: str) -> bool:
        return question_id in self._asked_ids

    def times_asked(self, category_key: str) -> int:
        return self._category_counts.get(category_key, 0)

    def mark_asked(self, question: FollowUpQuestion) -> None:
        self._asked_ids.add(question.question_id)
        self._category_counts[question.category_key] = (
            self._category_counts.get(question.category_key, 0) + 1
        )


# ---------------------------------------------------------------------------
# ProactiveQuestionGenerator
# ---------------------------------------------------------------------------

class ProactiveQuestionGenerator:
    """
    Generates one targeted follow-up question per turn.

    Mode hierarchy (FIX-B/C):
      1. LLM mode (default): calls the LLM with a meta-prompt for a
         context-aware, project-specific question.
      2. Template fallback: used when LLM provider is unavailable or the
         meta-call fails.

    Parameters
    ----------
    max_questions_per_turn : int
        Maximum questions to surface per turn (keep at 1 — do not overwhelm).
    mode : "llm" | "template"
        "llm"      — use LLM meta-prompt (primary, recommended).
        "template" — use parameterised templates (fallback / ablation OFF branch).
    llm_provider : optional LLMProvider instance
        Required for mode="llm".  If None, falls back to template mode silently.
    """

    # Minimum FRs before NFR questions are prioritised (mirrors prompt_architect)
    MIN_FUNCTIONAL_REQS: int = 3

    def __init__(
        self,
        max_questions_per_turn: int = 1,
        mode: str = "llm",
        llm_provider=None,
        templates: Optional[dict] = None,
    ):
        self.max_questions_per_turn = max_questions_per_turn
        self.mode = mode
        self._llm_provider = llm_provider
        self._templates = templates or FALLBACK_TEMPLATES

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        gap_report: "GapReport",
        state: "ConversationState",
        tracker: QuestionTracker,
    ) -> QuestionSet:
        """
        Generate a follow-up question for the highest-priority uncovered gap.

        FIX-D: If functional_count < MIN_FUNCTIONAL_REQS, the "functional"
        gap is always surfaced first regardless of gap_report ordering.
        """
        project_name = getattr(state, "project_name", "the system") or "the system"

        question_set = QuestionSet(
            session_id=gap_report.session_id,
            turn_id=gap_report.turn_id,
            total_gaps=len(gap_report.all_gaps),
        )

        if not gap_report.all_gaps:
            return question_set

        # FIX-D: FR deficit check — override gap ordering
        priority_gaps = list(gap_report.priority_gaps)
        if state.functional_count < self.MIN_FUNCTIONAL_REQS:
            # Move functional gap to front if present
            functional_gaps = [g for g in priority_gaps if g.category_key == "functional"]
            other_gaps = [g for g in priority_gaps if g.category_key != "functional"]
            priority_gaps = functional_gaps + other_gaps

        generated = 0
        for gap in priority_gaps:
            if generated >= self.max_questions_per_turn:
                break
            if tracker.times_asked(gap.category_key) >= 3:
                continue

            question = self._generate_for_gap(gap, project_name, state, tracker)
            if question and not tracker.is_asked(question.question_id):
                question_set.questions.append(question)
                tracker.mark_asked(question)
                question_set.addressed_gaps += 1
                generated += 1

        if question_set.questions:
            question_set.primary_question = question_set.questions[0]

        return question_set

    def build_injection_text(self, question_set: QuestionSet) -> str:
        """
        Build the directive block injected into PromptArchitect.extra_context.

        The directive tells the LLM WHICH gap to probe, but does NOT dictate
        the exact wording — the LLM weaves the question naturally.
        If mode=llm and we have a generated question, we surface it as a
        "suggested phrasing" rather than a mandatory script.
        """
        if not question_set.has_questions:
            return ""

        primary = question_set.primary_question
        from gap_detector import COVERAGE_CHECKLIST
        desc = COVERAGE_CHECKLIST.get(primary.category_key, {}).get("description", "")

        lines = [
            "── PROACTIVE QUESTIONING DIRECTIVE ──",
            f"Gap to probe next: {primary.category_label} (severity: {primary.severity.upper()})",
            f"Why: {desc}",
            "",
        ]

        if primary.source == "llm":
            lines += [
                "A context-aware question has been pre-generated for this gap:",
                f"  \"{primary.question_text}\"",
                "",
                "You MAY use this question verbatim or adapt it to flow naturally from your "
                "previous statement.  Do NOT ignore this gap category.",
            ]
        else:
            lines += [
                "Suggested question (template fallback):",
                f"  \"{primary.question_text}\"",
                "",
                "Integrate this naturally into your response rather than listing it as a "
                "separate bullet point.",
            ]

        lines.append("── END DIRECTIVE ──")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_for_gap(
        self,
        gap: "CategoryGap",
        project_name: str,
        state: "ConversationState",
        tracker: QuestionTracker,
    ) -> Optional[FollowUpQuestion]:
        """Route to LLM or template based on mode and provider availability."""
        if self.mode == "llm" and self._llm_provider is not None:
            return self._generate_llm(gap, project_name, state, tracker)
        return self._generate_template(gap, project_name, state, tracker)

    def _generate_llm(
        self,
        gap: "CategoryGap",
        project_name: str,
        state: "ConversationState",
        tracker: QuestionTracker,
    ) -> Optional[FollowUpQuestion]:
        """Generate a question using the LLM meta-prompt (FIX-B)."""
        history_summary, n_turns = _build_history_summary(state, max_turns=4)

        meta_prompt = _META_PROMPT_TEMPLATE.format(
            project_name=project_name,
            n_turns=n_turns,
            history_summary=history_summary,
            fr_count=state.functional_count,
            nfr_count=state.nonfunctional_count,
            gap_label=gap.label,
            gap_description=gap.description,
            gap_severity=gap.severity.value,
        )

        try:
            # The meta-prompt is a self-contained single-turn call
            raw = self._llm_provider.chat(
                system_message="You are a concise requirements engineering assistant.",
                messages=[{"role": "user", "content": meta_prompt}],
                temperature=0.4,   # slight creativity for question variety
            )
            # Strip any markdown or leading/trailing quotes the LLM might add
            question_text = raw.strip().strip('"').strip("'").strip()
            if not question_text or len(question_text) < 10:
                raise ValueError("LLM returned an empty or too-short question.")
        except Exception:
            # FIX-C: graceful fallback to template
            return self._generate_template(gap, project_name, state, tracker)

        # Build a stable ID: category + hash of question text first 40 chars
        question_id = f"{gap.category_key}_llm_{abs(hash(question_text[:40])) % 10000:04d}"

        return FollowUpQuestion(
            question_id=question_id,
            category_key=gap.category_key,
            category_label=gap.label,
            question_text=question_text,
            severity=gap.severity.value,
            is_partial=gap.is_partial,
            rationale=(
                f"LLM-generated for '{gap.label}' gap "
                f"({'partial' if gap.is_partial else 'uncovered'}, {gap.severity.value})."
            ),
            source="llm",
        )

    def _generate_template(
        self,
        gap: "CategoryGap",
        project_name: str,
        state: "ConversationState",
        tracker: QuestionTracker,
    ) -> Optional[FollowUpQuestion]:
        """Select and parameterise a fallback template (FIX-C)."""
        templates = self._templates.get(gap.category_key, [])
        if not templates:
            return None

        asked_count  = tracker.times_asked(gap.category_key)
        template_idx = asked_count % len(templates)
        question_text = templates[template_idx].replace("{project_name}", project_name)
        question_id = f"{gap.category_key}_{template_idx}"

        return FollowUpQuestion(
            question_id=question_id,
            category_key=gap.category_key,
            category_label=gap.label,
            question_text=question_text,
            severity=gap.severity.value,
            is_partial=gap.is_partial,
            rationale=(
                f"Template fallback for '{gap.label}' "
                f"({'partial' if gap.is_partial else 'uncovered'}, variant #{template_idx + 1})."
            ),
            source="template",
        )

    def _get_category_description(self, key: str) -> str:
        from gap_detector import COVERAGE_CHECKLIST
        return COVERAGE_CHECKLIST.get(key, {}).get("description", "")


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_question_generator(
    max_questions_per_turn: int = 1,
    mode: str = "llm",
    llm_provider=None,
) -> ProactiveQuestionGenerator:
    """
    Factory function.

    Parameters
    ----------
    mode : "llm" (default) | "template"
    llm_provider : LLMProvider instance (required for mode="llm").
                   Pass the same provider used by ConversationManager.
    """
    return ProactiveQuestionGenerator(
        max_questions_per_turn=max_questions_per_turn,
        mode=mode,
        llm_provider=llm_provider,
    )