"""
src/components/question_generator.py
=====================
RE Assistant — Iteration 4 | University of Hildesheim
Proactive Follow-Up Question Generator

Change log
----------
Iteration 3 fixes (FIX-A through FIX-D) — see Iteration 3 source.

Iteration 4 — Priority 3: Domain-Aware Probe Questions
═══════════════════════════════════════════════════════
The root cause of missing domains in Iteration 3 was that the question
generator was only triggered by GapDetector's IEEE-830 category gaps.
It had no concept of "functional domain coverage" — it could not tell
that 'security alarm', 'appliance control', or 'scheduling' had never
been asked about.

Changes in Iteration 4:
  IT4-A  Domain-first priority: when any DOMAIN_COVERAGE_GATE entry is
         UNPROBED, the generator always produces a question for it ahead
         of any IEEE-830 category gap. This ensures that the 8 functional
         domains are probed exhaustively before NFR or structural gaps.

  IT4-B  Domain probe templates: the FALLBACK_TEMPLATES dict is extended
         with one entry per domain gate key (prefixed "domain_"). These are
         the plain-language fallback_probe questions from DOMAIN_COVERAGE_GATE,
         kept in sync here so that both the context block and the question
         generator use identical wording.

  IT4-C  Scope reduction probe: new "scope_reduction" template category.
         When the gap detector signals a scope reduction event (user
         downscoped a domain), the generator produces the Rule-8 confirmation
         question: "Should we document [feature] as permanently out of scope,
         or revisit it later?"

  IT4-D  LLM meta-prompt extended with domain gate awareness: the meta-prompt
         now receives the list of unprobed domains so the LLM-generated
         question can be targeted even more precisely.

Architecture (Iteration 4)
--------------------------
  GapReport + ConversationState  →  ProactiveQuestionGenerator.generate()
    → Domain gate check first (IT4-A)
    → GapDetector gap check second
    → LLM meta-prompt (primary) | template lookup (fallback)
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
# Fallback question templates
# Iteration 4: extended with domain-specific probes (IT4-B) and
# scope-reduction confirmation (IT4-C).
# ---------------------------------------------------------------------------

FALLBACK_TEMPLATES: dict[str, list[str]] = {

    # ── IEEE-830 structural gaps (Iteration 3, retained) ──────────────────
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
        "Walk me through a typical user journey from opening the system to completing their main task.",
        "Are there any automated processes {project_name} should perform without user interaction?",
    ],
    "use_cases": [
        "Can you describe a concrete scenario where a user achieves their goal step by step?",
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
        "Are there any accessibility requirements (e.g. for users with limited technical skills)?",
    ],
    "security_privacy": [
        "What types of sensitive or personal data will {project_name} handle, and who should have access?",
        "How must users authenticate — username/password, single sign-on, or something else?",
    ],
    "reliability": [
        "What is the acceptable downtime for {project_name}? For example, 99.9% uptime means about 8.7 hours per year.",
        "How quickly must {project_name} recover after an outage?",
    ],
    "compatibility": [
        "Which operating systems, browsers, or devices must {project_name} support?",
        "Does {project_name} need to integrate with any existing systems?",
    ],
    "maintainability": [
        "How often do you expect {project_name} to receive updates after launch?",
        "What team will maintain {project_name} over time?",
    ],
    "scalability": [
        "If {project_name} is successful and usage doubles, how should the system handle that growth?",
    ],
    "interfaces": [
        "What external services, devices, or APIs does {project_name} need to communicate with?",
        "How does the system physically connect to sensors or control devices — is there a central hub?",
    ],
    "data_requirements": [
        "What are the main types of data {project_name} will create, store, and manage?",
    ],
    "constraints": [
        "Are there any technology choices already decided — e.g. a required hardware platform, protocol, or cloud provider?",
    ],
    "assumptions": [
        "What assumptions are you making that, if wrong, would change the requirements significantly?",
    ],
    "testability": [
        "How will you verify that {project_name} meets its requirements? What does a passing acceptance test look like?",
    ],
    "deployment": [
        "Where will {project_name} be deployed — on local hardware, a cloud service, or both?",
    ],

    # ── Domain gate probes (IT4-B) ─────────────────────────────────────────
    # Keys are prefixed "domain_" + DOMAIN_COVERAGE_GATE key.
    # Wording is kept in sync with DOMAIN_COVERAGE_GATE.fallback_probe.

    "domain_climate_control": [
        "You mentioned temperature and humidity concerns — can you walk me through "
        "exactly what you'd want to do with them? For example, would you want to just "
        "see the readings, set a target level, or have the system automatically maintain a level?",
        "For the rooms you want to monitor — which ones are most critical, and would "
        "you need to control each one independently or as a group?",
    ],

    "domain_security_alarm": [
        "You mentioned worrying about the house when travelling — do you want the system "
        "to monitor whether doors or windows are left open, or trigger some kind of alert "
        "if something looks wrong?",
        "If the system detects an open door or window, what should it do — send a notification, "
        "sound an alarm, or both?",
    ],

    "domain_appliance_lighting": [
        "You mentioned worrying about lights being left on — would you want the system to show "
        "you which lights or appliances are on, and let you turn them off remotely if needed?",
        "Are there specific appliances — like a dehumidifier, space heater, or lamp — "
        "you'd want to switch on or off from your phone?",
    ],

    "domain_scheduling_planning": [
        "Do you ever want the system to follow a routine automatically — like setting the "
        "heat lower at night, or switching to a lower-energy mode when the family goes on vacation?",
        "Would you want to pre-program different 'profiles' for different situations — "
        "for example, a weekday routine versus a weekend one?",
    ],

    "domain_remote_access": [
        "You mentioned checking on the house from the airport — how exactly would you want "
        "to do that? Through a phone app, a website, or something else?",
        "When you're away, what's the most important thing you'd want to be able to check "
        "or do from your phone?",
    ],

    "domain_user_management": [
        "Who should be able to use this system, and should different people have different "
        "levels of access? For example, should your kids, your mother-in-law, or a visiting "
        "HVAC technician see the same things you do?",
        "Should there be an 'administrator' account — someone who can add or remove users "
        "and change system settings — separate from regular users?",
    ],

    "domain_reporting_history": [
        "Would it be useful to look back at past temperature or humidity readings — for "
        "example, to see what happened last month, or to show your HVAC technician the "
        "humidity history so he can check if the dehumidifier is working?",
        "How long should the system keep historical data — a few weeks, months, or years?",
    ],

    "domain_hardware_connectivity": [
        "How does the system actually connect to things like your thermostats and humidity "
        "sensors — is there a central hub device that talks to everything, or would each "
        "sensor connect to your home Wi-Fi separately?",
        "Do you have a preference for how the sensors communicate — for example, via "
        "Wi-Fi, or a separate wireless protocol like Zigbee or Z-Wave?",
    ],

    # ── Scope reduction confirmation (IT4-C) ──────────────────────────────
    "scope_reduction": [
        "Just to confirm — should we document that as permanently out of scope for this "
        "version, or would you like to revisit it in a future release?",
        "To make sure I capture this correctly — are you saying the system should never "
        "do [feature], or just not in this first version?",
    ],
}


# ---------------------------------------------------------------------------
# LLM meta-prompt (extended for domain awareness — IT4-D)
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
1. Naturally continues the conversation (references what was just said if possible)
2. If unprobed domains exist, targets the FIRST one listed above
3. Otherwise targets the gap category: {gap_label}
4. Is specific to {project_name}, not generic
5. Is concise — one sentence, no sub-bullets
6. Uses plain, non-technical language (the stakeholder is not an engineer)
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
    """Build a plain-text list of unprobed domains for the meta-prompt."""
    from prompt_architect import compute_domain_gate, DOMAIN_COVERAGE_GATE
    from prompt_architect import DOMAIN_STATUS_UNPROBED, DOMAIN_STATUS_PARTIAL

    gate_status = compute_domain_gate(state)
    unprobed = [
        f"  - {DOMAIN_COVERAGE_GATE[k]['label']}"
        for k, s in gate_status.items()
        if s in (DOMAIN_STATUS_UNPROBED, DOMAIN_STATUS_PARTIAL)
    ]
    return "\n".join(unprobed) if unprobed else "  (all domains probed)"


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
    source:         str = "llm"   # "llm" | "template" | "domain_gate"

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
    """Collection of follow-up questions for a single turn."""
    questions:       list[FollowUpQuestion] = field(default_factory=list)
    primary_question: Optional[FollowUpQuestion] = None
    addressed_gaps:  int = 0

    @property
    def has_questions(self) -> bool:
        return bool(self.questions)


class QuestionTracker:
    """Tracks which questions have been asked to avoid repetition."""

    def __init__(self) -> None:
        self._asked: set[str] = set()
        self._category_counts: dict[str, int] = {}

    def is_asked(self, question_id: str) -> bool:
        return question_id in self._asked

    def mark_asked(self, question: FollowUpQuestion) -> None:
        self._asked.add(question.question_id)
        self._category_counts[question.category_key] = (
            self._category_counts.get(question.category_key, 0) + 1
        )

    def times_asked(self, category_key: str) -> int:
        return self._category_counts.get(category_key, 0)


# ---------------------------------------------------------------------------
# ProactiveQuestionGenerator
# ---------------------------------------------------------------------------

class ProactiveQuestionGenerator:
    """
    Generates targeted follow-up questions from gap reports and domain gate.

    Priority order (Iteration 4):
      1. Unprobed domain gate entries     (IT4-A — highest priority)
      2. Critical IEEE-830 gaps           (existing logic)
      3. Important IEEE-830 gaps          (existing logic)
      4. Optional IEEE-830 gaps           (existing logic)

    Generation modes:
      "llm"      — LLM meta-prompt (primary, context-aware)
      "template" — deterministic fallback
    """

    def __init__(
        self,
        max_questions_per_turn: int = 1,
        mode: str = "llm",
        llm_provider=None,
        templates: Optional[dict] = None,
    ) -> None:
        self.max_questions_per_turn = max_questions_per_turn
        self.mode = mode
        self._llm_provider = llm_provider
        self._templates = templates or FALLBACK_TEMPLATES
        self._tracker = QuestionTracker()

    @property
    def tracker(self) -> QuestionTracker:
        return self._tracker

    def generate(
        self,
        gap_report: "GapReport",
        state: "ConversationState",
        project_name: str = "the system",
    ) -> QuestionSet:
        """
        Generate up to max_questions_per_turn follow-up questions.
        Domain gate gaps are always processed before IEEE-830 category gaps.
        """
        question_set = QuestionSet()
        tracker = self._tracker

        # ── IT4-A: Domain gate priority pass ──────────────────────────────
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

        # ── IEEE-830 gap pass (existing logic) ────────────────────────────
        from prompt_architect import MIN_FUNCTIONAL_REQS
        from gap_detector import GapSeverity

        all_gaps = gap_report.all_gaps if gap_report else []

        # FR-deficit: always probe functional gaps first
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
        """
        Build the directive injected into PromptArchitect.extra_context.
        """
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
                "This is an UNPROBED FUNCTIONAL DOMAIN — highest priority.",
                f"Domain probe question: \"{primary.question_text}\"",
                "",
                "Use this question verbatim or adapt it to flow naturally. "
                "Do NOT skip this domain.",
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
    # Internal: domain gate question generation (IT4-A)
    # ------------------------------------------------------------------

    def _generate_domain_gate_questions(
        self,
        state: "ConversationState",
        project_name: str,
        tracker: QuestionTracker,
    ) -> list[FollowUpQuestion]:
        """
        Generate questions for UNPROBED domain gate entries.
        Returns at most max_questions_per_turn questions, unprobed first.
        """
        from prompt_architect import (
            compute_domain_gate, DOMAIN_COVERAGE_GATE,
            DOMAIN_STATUS_UNPROBED, DOMAIN_STATUS_PARTIAL,
        )

        gate_status = compute_domain_gate(state)
        questions: list[FollowUpQuestion] = []

        # Process UNPROBED first, then PARTIAL
        ordered_keys = (
            [k for k, s in gate_status.items() if s == DOMAIN_STATUS_UNPROBED]
            + [k for k, s in gate_status.items() if s == DOMAIN_STATUS_PARTIAL]
        )

        for domain_key in ordered_keys:
            if len(questions) >= self.max_questions_per_turn:
                break

            template_key = f"domain_{domain_key}"
            templates = self._templates.get(template_key, [])
            if not templates:
                continue

            asked_count  = tracker.times_asked(template_key)
            if asked_count >= len(templates):
                continue

            question_text = templates[asked_count % len(templates)]
            question_id   = f"{template_key}_{asked_count}"

            if tracker.is_asked(question_id):
                continue

            questions.append(FollowUpQuestion(
                question_id    = question_id,
                category_key   = template_key,
                category_label = DOMAIN_COVERAGE_GATE[domain_key]["label"],
                question_text  = question_text,
                severity       = "critical",
                is_partial     = gate_status[domain_key] == DOMAIN_STATUS_PARTIAL,
                rationale      = (
                    f"Domain gate: '{DOMAIN_COVERAGE_GATE[domain_key]['label']}' "
                    f"is {gate_status[domain_key]} — must be probed before SRS generation."
                ),
                source         = "domain_gate",
            ))

        return questions

    # ------------------------------------------------------------------
    # Internal: IEEE-830 gap question generation (existing)
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