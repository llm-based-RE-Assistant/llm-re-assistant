"""
src/components/question_generator.py
=====================
RE Assistant — Iteration 5 | University of Hildesheim
Proactive Follow-Up Question Generator

Iteration 5 changes
═══════════════════════════════════════
IT5-A  Domain gate questions now target SPECIFIC missing sub-dimensions
       rather than generic "tell me more about X" probes.

IT5-B  Probe depth awareness: if a domain has been probed ≥1 time,
       the question specifically targets the missing sub-dimension
       (constraints, automation, edge_cases, etc.)

IT5-C  Added "final coverage" questions for user roles and documentation
       that are asked after all domains are confirmed.
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
# Fallback question templates
# ---------------------------------------------------------------------------

FALLBACK_TEMPLATES: dict[str, list[str]] = {

    # ── IEEE-830 structural gaps ──
    "purpose": [
        "What specific problem does {project_name} solve, and why is an automated software system the right solution?",
        "What does success look like for {project_name} — how will you know the system has achieved its purpose?",
    ],
    "scope": [
        "What is explicitly OUT of scope for {project_name}? What should the system not do?",
        "Where does {project_name} end and another system or manual process begin?",
    ],
    "stakeholders": [
        "Who are the different types of users of {project_name}, and how do their needs differ — for example, are there regular users and administrators?",
        "Besides end users, who else has an interest in {project_name} — installers, technicians, support staff?",
    ],
    "functional": [
        "What are the three most important things a user must be able to DO with {project_name}?",
        "Walk me through a typical user journey from opening the system to completing their main task.",
        "Are there any automated processes {project_name} should perform without user interaction?",
    ],
    "use_cases": [
        "Can you describe a concrete scenario where a user achieves their goal step by step?",
        "What happens when something goes wrong — for example, if the user makes a mistake?",
    ],
    "business_rules": [
        "Are there any legal or regulatory requirements {project_name} must satisfy?",
        "What business rules or policies must the system enforce?",
    ],
    "performance": [
        "How quickly must {project_name} respond to a typical user request? Give me a specific number in seconds.",
        "How often must sensor or status data be refreshed — every second, every 5 seconds, or less often?",
    ],
    "usability": [
        "Who is the least technical person using {project_name}, and what would they need to find it easy?",
        "Should users be able to use {project_name} without reading any manual at all?",
    ],
    "security_privacy": [
        "How must users authenticate — username/password, two-factor, or something else?",
        "Is there any data that must be encrypted or kept private from certain users?",
    ],
    "reliability": [
        "What is the maximum acceptable downtime? For example, no more than one failure per 10,000 hours.",
        "If {project_name} goes offline, what should happen — should it recover automatically and restore data?",
    ],
    "compatibility": [
        "Which operating systems, browsers, or devices must {project_name} support?",
        "Does {project_name} need to integrate with any existing hardware or protocols?",
    ],
    "maintainability": [
        "Who will maintain {project_name} after deployment — the vendor, your IT team, or a third party?",
        "Should {project_name} update itself automatically, or should updates require approval?",
    ],
    "interfaces": [
        "What external devices, sensors, or APIs does {project_name} need to communicate with?",
        "How does the system physically connect to its devices — wireless, wired, through a hub?",
    ],
    "constraints": [
        "Are there any technology choices already decided — required hardware, protocols, or standards?",
        "Are there any development standards or document formats the project must follow?",
    ],
    "user_roles": [
        "Who are the different types of users, and do they have different permissions or capabilities?",
        "Is there a master administrator who can change system settings that regular users cannot?",
    ],
    "documentation": [
        "What kind of online help or documentation should the system provide to users?",
        "Should the system include an FAQ or a guide explaining how to use its main features?",
    ],
}


# ---------------------------------------------------------------------------
# LLM meta-prompt
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

UNPROBED FUNCTIONAL DOMAINS (highest priority — ask about these first):
{unprobed_domains}

TARGET GAP: {gap_label} ({gap_description})
Gap severity: {gap_severity}

TASK:
Generate exactly ONE short, open-ended elicitation question that:
1. Naturally continues the conversation
2. If unprobed domains exist, targets the FIRST one listed above
3. Otherwise targets the gap category: {gap_label}
4. Asks for SPECIFIC, MEASURABLE details (how many, what range, how fast, what units)
5. Is concise — one sentence, no sub-bullets
6. Uses plain, non-technical language
7. Does NOT repeat a question already asked

Reply with ONLY the question text. No preamble, no explanation, no quotes.\
"""


def _build_history_summary(state: "ConversationState", max_turns: int = 4) -> tuple[str, int]:
    turns = state.turns[-max_turns:]
    lines = []
    for t in turns:
        u = t.user_message[:200].replace("\n", " ")
        a = t.assistant_message[:200].replace("\n", " ")
        lines.append(f"  User: {u}")
        lines.append(f"  Assistant: {a}")
    return "\n".join(lines) if lines else "  (no turns yet)", len(turns)


def _build_unprobed_domains_text(state: "ConversationState") -> str:
    """Build a plain-text list of unprobed/partial domains with sub-dimension details."""
    gate = getattr(state, "domain_gate", None)
    if gate is None or not gate.seeded:
        return "  (domain gate not yet seeded)"

    lines = []
    for key, domain in gate.domains.items():
        if domain.status in ("unprobed", "partial"):
            covered_dims = [d for d, ids in domain.sub_dimensions.items() if ids]
            missing_dims = [d for d in ["data", "actions", "constraints", "automation", "edge_cases"]
                          if d not in covered_dims]
            status_str = f"[{len(domain.req_ids)} reqs, missing: {', '.join(missing_dims)}]"
            lines.append(f"  ⬜ {domain.label} {status_str}")
        elif domain.needs_deeper_probing:
            covered_dims = [d for d, ids in domain.sub_dimensions.items() if ids]
            missing_dims = [d for d in ["data", "actions", "constraints", "automation", "edge_cases"]
                          if d not in covered_dims]
            status_str = f"[{len(domain.req_ids)} reqs, needs depth: {', '.join(missing_dims)}]"
            lines.append(f"  🔶 {domain.label} {status_str}")

    return "\n".join(lines) if lines else "  (all domains confirmed)"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FollowUpQuestion:
    question_id:    str
    category_key:   str
    category_label: str
    question_text:  str
    severity:       str = "critical"
    is_partial:     bool = False
    rationale:      str = ""
    source:         str = "template"

    def to_dict(self) -> dict:
        return {
            "question_id":    self.question_id,
            "category_key":   self.category_key,
            "category_label": self.category_label,
            "question_text":  self.question_text,
            "severity":       self.severity,
            "is_partial":     self.is_partial,
            "rationale":      self.rationale,
            "source":         self.source,
        }

@dataclass
class QuestionSet:
    questions:         list[FollowUpQuestion] = field(default_factory=list)
    primary_question:  Optional[FollowUpQuestion] = None
    addressed_gaps:    int = 0

    @property
    def has_questions(self) -> bool:
        return len(self.questions) > 0


class QuestionTracker:
    """Track which questions were asked to avoid repetition."""

    def __init__(self):
        self._asked: dict[str, int] = {}

    def mark_asked(self, q: FollowUpQuestion) -> None:
        self._asked[q.question_id] = self._asked.get(q.question_id, 0) + 1
        base = q.category_key
        self._asked[base] = self._asked.get(base, 0) + 1

    def is_asked(self, question_id: str) -> bool:
        return question_id in self._asked

    def times_asked(self, key: str) -> int:
        return self._asked.get(key, 0)


# ---------------------------------------------------------------------------
# ProactiveQuestionGenerator
# ---------------------------------------------------------------------------

class ProactiveQuestionGenerator:

    def __init__(
        self,
        max_questions_per_turn: int = 1,
        mode: str = "llm",
        llm_provider=None,
    ):
        self.max_questions_per_turn = max_questions_per_turn
        self.mode = mode
        self._llm_provider = llm_provider
        self._templates = dict(FALLBACK_TEMPLATES)
        self._tracker = QuestionTracker()

    def generate(
        self,
        gap_report: "GapReport | None",
        state: "ConversationState",
        project_name: str = "",
    ) -> QuestionSet:
        question_set = QuestionSet()
        tracker = self._tracker

        # ── Domain gate priority pass ──
        domain_questions = self._generate_domain_gate_questions(
            state, project_name, tracker
        )
        for q in domain_questions:
            if len(question_set.questions) >= self.max_questions_per_turn:
                break
            if not tracker.is_asked(q.question_id):
                question_set.questions.append(q)
                tracker.mark_asked(q)
                question_set.addressed_gaps += 1

        if len(question_set.questions) >= self.max_questions_per_turn:
            question_set.primary_question = question_set.questions[0]
            return question_set

        # ── IEEE-830 gap pass ──
        from prompt_architect import MIN_FUNCTIONAL_REQS
        from gap_detector import GapSeverity

        all_gaps = gap_report.all_gaps if gap_report else []

        if state.functional_count < MIN_FUNCTIONAL_REQS:
            functional_gaps = [g for g in all_gaps if g.category_key == "functional"]
            other_gaps = [g for g in all_gaps if g.category_key != "functional"]
            priority_gaps = functional_gaps + other_gaps
        else:
            priority_gaps = all_gaps

        for gap in priority_gaps:
            if len(question_set.questions) >= self.max_questions_per_turn:
                break
            if tracker.times_asked(gap.category_key) >= 3:
                continue
            q = self._generate_for_gap(gap, project_name, state, tracker)
            if q and not tracker.is_asked(q.question_id):
                question_set.questions.append(q)
                tracker.mark_asked(q)
                question_set.addressed_gaps += 1

        if question_set.questions:
            question_set.primary_question = question_set.questions[0]

        return question_set

    def build_injection_text(self, question_set: QuestionSet) -> str:
        if not question_set.has_questions:
            return ""

        primary = question_set.primary_question
        from gap_detector import COVERAGE_CHECKLIST
        desc = COVERAGE_CHECKLIST.get(primary.category_key, {}).get("description", "")

        lines = [
            "── PROACTIVE QUESTIONING DIRECTIVE ──",
            f"Gap to probe next: {primary.category_label} (severity: {primary.severity.upper()})",
        ]
        if desc:
            lines.append(f"Why: {desc}")
        lines.append("")

        if primary.source == "domain_gate":
            lines += [
                "This is a FUNCTIONAL DOMAIN that needs probing — highest priority.",
                f"Suggested question: \"{primary.question_text}\"",
                "",
                "Use this question or adapt it naturally. "
                "Do NOT skip this domain. Ask for SPECIFIC NUMBERS if relevant.",
            ]
        elif primary.source == "llm":
            lines += [
                "Context-aware question pre-generated for this gap:",
                f"  \"{primary.question_text}\"",
                "",
                "You MAY use this verbatim or adapt it. Do NOT ignore this gap.",
            ]
        else:
            lines += [
                "Suggested question (template fallback):",
                f"  \"{primary.question_text}\"",
                "",
                "Integrate this naturally into your response.",
            ]

        lines.append("── END DIRECTIVE ──")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal: domain gate question generation — IT6-A, B
    # ------------------------------------------------------------------

    def _generate_domain_gate_questions(
        self,
        state: "ConversationState",
        project_name: str,
        tracker: QuestionTracker,
    ) -> list[FollowUpQuestion]:
        gate = getattr(state, "domain_gate", None)
        if gate is None or not gate.seeded:
            return []

        questions: list[FollowUpQuestion] = []

        # Collect all domains needing attention
        ordered_domains = (
            [d for d in gate.domains.items() if d[1].status == "unprobed"]
            + [d for d in gate.domains.items() if d[1].status == "partial"]
            + [d for d in gate.domains.items()
               if d[1].needs_deeper_probing and d[1].status not in ("unprobed", "partial", "excluded")]
        )

        for key, domain in ordered_domains:
            if len(questions) >= self.max_questions_per_turn:
                break

            question_text = domain.probe_question or (
                f"Can you tell me more about the {domain.label} aspects of your system?"
            )

            asked_count = tracker.times_asked(f"domain_{key}")
            if asked_count >= 4:  # IT6: allow more probes per domain
                continue

            question_id = f"domain_{key}_{asked_count}"
            if tracker.is_asked(question_id):
                continue

            questions.append(FollowUpQuestion(
                question_id    = question_id,
                category_key   = f"domain_{key}",
                category_label = domain.label,
                question_text  = question_text,
                severity       = "critical",
                is_partial     = (domain.status == "partial"),
                rationale      = (
                    f"Domain '{domain.label}' is {domain.status} — "
                    f"needs {', '.join(d for d in ['data','actions','constraints','automation','edge_cases'] if d not in [sd for sd, ids in domain.sub_dimensions.items() if ids])}"
                ),
                source         = "domain_gate",
            ))

        return questions

    # ------------------------------------------------------------------
    # Internal: IEEE-830 gap question generation
    # ------------------------------------------------------------------

    def _generate_for_gap(
        self,
        gap: "CategoryGap",
        project_name: str,
        state: "ConversationState",
        tracker: QuestionTracker,
    ) -> Optional[FollowUpQuestion]:
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
        history_summary, n_turns = _build_history_summary(state, max_turns=4)
        unprobed_text = _build_unprobed_domains_text(state)

        meta_prompt = _META_PROMPT_TEMPLATE.format(
            project_name     = project_name,
            n_turns          = n_turns,
            history_summary  = history_summary,
            fr_count         = state.functional_count,
            nfr_count        = state.nonfunctional_count,
            unprobed_domains = unprobed_text,
            gap_label        = gap.label,
            gap_description  = gap.description,
            gap_severity     = gap.severity.value,
        )

        try:
            raw = self._llm_provider.chat(
                system_message="You are a concise requirements engineering assistant.",
                messages=[{"role": "user", "content": meta_prompt}],
                temperature=0.4,
            )
            question_text = raw.strip().strip('"').strip("'").strip()
            if not question_text or len(question_text) < 10:
                raise ValueError("LLM returned empty question.")
        except Exception:
            return self._generate_template(gap, project_name, state, tracker)

        question_id = (
            f"{gap.category_key}_llm_{abs(hash(question_text[:40])) % 10000:04d}"
        )
        return FollowUpQuestion(
            question_id    = question_id,
            category_key   = gap.category_key,
            category_label = gap.label,
            question_text  = question_text,
            severity       = gap.severity.value,
            is_partial     = gap.is_partial,
            rationale      = (
                f"LLM-generated for '{gap.label}' "
                f"({'partial' if gap.is_partial else 'uncovered'}, {gap.severity.value})."
            ),
            source         = "llm",
        )

    def _generate_template(
        self,
        gap: "CategoryGap",
        project_name: str,
        state: "ConversationState",
        tracker: QuestionTracker,
    ) -> Optional[FollowUpQuestion]:
        templates = self._templates.get(gap.category_key, [])
        if not templates:
            return None

        asked_count   = tracker.times_asked(gap.category_key)
        template_idx  = asked_count % len(templates)
        question_text = templates[template_idx].replace("{project_name}", project_name)
        question_id   = f"{gap.category_key}_{template_idx}"

        return FollowUpQuestion(
            question_id    = question_id,
            category_key   = gap.category_key,
            category_label = gap.label,
            question_text  = question_text,
            severity       = gap.severity.value,
            is_partial     = gap.is_partial,
            rationale      = (
                f"Template fallback for '{gap.label}' "
                f"({'partial' if gap.is_partial else 'uncovered'}, variant #{template_idx + 1})."
            ),
            source         = "template",
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
    return ProactiveQuestionGenerator(
        max_questions_per_turn=max_questions_per_turn,
        mode=mode,
        llm_provider=llm_provider,
    )