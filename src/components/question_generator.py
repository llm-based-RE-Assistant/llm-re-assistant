"""
question_generator.py
=====================
RE Assistant — Iteration 3 | University of Hildesheim
Proactive Follow-Up Question Generator

Research Question (Iteration 3)
--------------------------------
Can the RE Assistant generate context-aware, targeted follow-up questions
for uncovered requirement gaps?

Responsibilities
----------------
- Consume a GapReport (from GapDetector) and conversation context
- Generate 1–3 targeted follow-up questions per conversation turn
  (never overwhelm the user with too many at once)
- Rank questions by gap severity (critical first)
- Adapt question phrasing to the project context (not generic)
- Avoid repeating questions already asked in the same session
- Support two modes: TEMPLATE (fast, deterministic) and LLM (rich, context-aware)

Architecture
------------
  GapReport  →  ProactiveQuestionGenerator.generate()  →  list[FollowUpQuestion]
  FollowUpQuestion  →  injected into PromptArchitect system message block

Design notes
------------
- Template mode uses parameterised question templates (faster, ablation-safe).
- LLM mode calls the LLMProvider with a meta-prompt to generate a custom question.
- The PromptArchitect's CONTEXT block is extended with the top follow-up question
  so the assistant weaves it naturally into its reply.
- Asked question IDs are tracked in QuestionTracker (in-memory per session)
  to prevent repetition.
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
# Question templates per IEEE-830 / Volere category
# Each template can reference {project_name} and {context} placeholders.
# Multiple templates per category provide variety across sessions.
# ---------------------------------------------------------------------------

QUESTION_TEMPLATES: dict[str, list[str]] = {
    "purpose": [
        "What specific problem does {project_name} solve, and why is an automated software system the right solution?",
        "Can you describe the main business goal that {project_name} should achieve within the next 12 months?",
        "What does success look like for {project_name} — how will you know the system has achieved its purpose?",
    ],
    "scope": [
        "What is explicitly OUT of scope for {project_name}? What should the system not do?",
        "Where does {project_name} end and another system or manual process begin?",
        "Are there any features that stakeholders have requested but you've decided to exclude — and why?",
    ],
    "stakeholders": [
        "Who are the different types of users of {project_name}, and how do their needs differ?",
        "Besides end users, who else has an interest in {project_name}? (e.g. administrators, executives, regulators)",
        "Which user group is most critical to satisfy first, and what are their top three priorities?",
    ],
    "functional": [
        "What are the three most important things a user must be able to DO with {project_name}?",
        "Walk me through a typical user journey — from opening the system to completing their main task.",
        "Are there any automated processes {project_name} should perform without user interaction?",
    ],
    "use_cases": [
        "Can you describe a concrete scenario where a user achieves their goal using {project_name} step by step?",
        "What happens when something goes wrong — for example, if the user makes a mistake or the network fails?",
        "Are there any edge cases or exceptional situations the system must handle gracefully?",
    ],
    "business_rules": [
        "Are there any legal, regulatory, or compliance requirements {project_name} must satisfy (e.g. GDPR, HIPAA, industry standards)?",
        "What business rules or policies must the system enforce? For example, who can approve what, or what limits apply?",
        "Are there any contractual obligations or SLAs that constrain how {project_name} must behave?",
    ],
    "performance": [
        "How quickly must {project_name} respond to a typical user request? Please give a specific number (e.g. under 2 seconds).",
        "How many concurrent users do you expect at peak load, and how many total users in the first year?",
        "Are there any batch processing operations that must complete within a specific time window?",
    ],
    "usability": [
        "What is the technical skill level of the typical user of {project_name} — are they technical experts or general public?",
        "Are there any accessibility requirements? For example, must the system work for users with visual or motor impairments?",
        "How much training should a new user need before they can use {project_name} independently?",
    ],
    "security_privacy": [
        "What types of sensitive or personal data will {project_name} handle, and who should have access to it?",
        "How must users authenticate — username/password, SSO, MFA, or something else?",
        "Are there data residency or privacy regulations that dictate where data must be stored or how long it can be kept?",
    ],
    "reliability": [
        "What is the acceptable downtime for {project_name}? For example, 99.9% uptime means ~8.7 hours downtime per year.",
        "What should happen to user data and ongoing operations if {project_name} experiences an unexpected failure?",
        "How quickly must {project_name} recover after an outage — is there a maximum recovery time objective (RTO)?",
    ],
    "compatibility": [
        "Which operating systems, browsers, or devices must {project_name} support?",
        "Does {project_name} need to integrate with any existing systems your organisation already uses?",
        "Are there any legacy systems or file formats that {project_name} must be compatible with?",
    ],
    "maintainability": [
        "How often do you expect {project_name} to receive updates or new features after launch?",
        "What team will maintain {project_name} — an internal dev team, a vendor, or both?",
        "Are there any code quality, documentation, or testing standards the team must follow?",
    ],
    "scalability": [
        "If {project_name} is successful and user numbers double or triple, how should the system handle that growth?",
        "Are there seasonal traffic spikes you need to plan for (e.g. end of year, product launches)?",
        "Should {project_name} be able to scale automatically, or is manual scaling acceptable?",
    ],
    "interfaces": [
        "What external services or APIs does {project_name} need to call or receive data from?",
        "Will {project_name} need to send notifications via email, SMS, or push notifications? If so, through which service?",
        "Are there any third-party payment processors, identity providers, or analytics platforms to integrate?",
    ],
    "data_requirements": [
        "What are the main types of data {project_name} will create, store, and manage?",
        "How long must data be retained, and are there any data deletion or archival requirements?",
        "Are there any data import/export requirements — for example, migrating data from a legacy system?",
    ],
    "constraints": [
        "Are there any technology choices already decided — for example, a required programming language, database, or cloud platform?",
        "What is the approximate budget and timeline for delivering {project_name}?",
        "Are there any team size, skill set, or infrastructure constraints I should factor into the requirements?",
    ],
    "assumptions": [
        "What assumptions are you making about the environment or users that, if wrong, would change the requirements significantly?",
        "Are there any dependencies on other projects or systems that must be completed before {project_name} can launch?",
        "What would cause the project to be cancelled or significantly descoped?",
    ],
    "testability": [
        "How will you verify that {project_name} meets its requirements? What does a passing acceptance test look like?",
        "Are there specific measurable success criteria for the most important features?",
        "Who is responsible for testing — a dedicated QA team, the developers, or the end users?",
    ],
    "deployment": [
        "Where will {project_name} be deployed — on-premise servers, a specific cloud provider, or both?",
        "How should {project_name} be released — big-bang launch or incremental rollout to user groups?",
        "What monitoring, logging, or alerting does the operations team need once {project_name} is live?",
    ],
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FollowUpQuestion:
    """A single generated follow-up question targeting a specific gap."""
    question_id:   str          # unique ID for deduplication tracking
    category_key:  str
    category_label: str
    question_text: str
    severity:      str          # "critical" | "important" | "optional"
    is_partial:    bool         # True if category was partially covered
    rationale:     str          # Why this question was chosen (for logging)
    timestamp:     float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "question_id":    self.question_id,
            "category_key":   self.category_key,
            "category_label": self.category_label,
            "question_text":  self.question_text,
            "severity":       self.severity,
            "is_partial":     self.is_partial,
            "rationale":      self.rationale,
            "timestamp":      self.timestamp,
        }


@dataclass
class QuestionSet:
    """The output of one generate() call — a ranked set of follow-up questions."""
    session_id:         str
    turn_id:            int
    questions:          list[FollowUpQuestion] = field(default_factory=list)
    primary_question:   Optional[FollowUpQuestion] = None  # top-ranked question to inject
    total_gaps:         int = 0
    addressed_gaps:     int = 0

    @property
    def has_questions(self) -> bool:
        return len(self.questions) > 0

    def to_dict(self) -> dict:
        return {
            "session_id":       self.session_id,
            "turn_id":          self.turn_id,
            "questions":        [q.to_dict() for q in self.questions],
            "primary_question": self.primary_question.to_dict() if self.primary_question else None,
            "total_gaps":       self.total_gaps,
            "addressed_gaps":   self.addressed_gaps,
        }


# ---------------------------------------------------------------------------
# Question Tracker — prevents repetition within a session
# ---------------------------------------------------------------------------

class QuestionTracker:
    """
    Tracks which question IDs have already been generated in this session.
    Prevents the assistant from asking the same question twice.
    """

    def __init__(self):
        self._asked: set[str] = set()
        self._asked_categories: dict[str, int] = {}  # category → times asked

    def is_asked(self, question_id: str) -> bool:
        return question_id in self._asked

    def mark_asked(self, question: FollowUpQuestion) -> None:
        self._asked.add(question.question_id)
        self._asked_categories[question.category_key] = (
            self._asked_categories.get(question.category_key, 0) + 1
        )

    def times_asked(self, category_key: str) -> int:
        return self._asked_categories.get(category_key, 0)

    def to_dict(self) -> dict:
        return {
            "asked_ids":        list(self._asked),
            "asked_categories": self._asked_categories,
        }


# ---------------------------------------------------------------------------
# Proactive Question Generator
# ---------------------------------------------------------------------------

class ProactiveQuestionGenerator:
    """
    Generates context-aware follow-up questions for uncovered requirement gaps.

    Usage
    -----
        generator = ProactiveQuestionGenerator()
        tracker   = QuestionTracker()
        question_set = generator.generate(gap_report, state, tracker)
        # Inject question_set.primary_question.question_text into PromptArchitect

    Parameters
    ----------
    max_questions_per_turn : int
        Maximum number of questions to generate per turn (default: 2).
        Keeping this low prevents overwhelming the user.
    mode : "template" | "hybrid"
        "template" — use parameterised templates only (fast, deterministic).
        "hybrid"   — use templates but annotate with project context.
    """

    def __init__(
        self,
        max_questions_per_turn: int = 2,
        mode: str = "template",
        templates: Optional[dict] = None,
    ):
        self.max_questions_per_turn = max_questions_per_turn
        self.mode = mode
        self._templates = templates or QUESTION_TEMPLATES

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
        Generate follow-up questions for the top-priority gaps.

        Parameters
        ----------
        gap_report : GapReport from GapDetector.analyse()
        state      : Current ConversationState (for project name context)
        tracker    : QuestionTracker to avoid repetition

        Returns
        -------
        QuestionSet with ranked follow-up questions.
        """
        project_name = getattr(state, "project_name", "the system") or "the system"

        question_set = QuestionSet(
            session_id   = gap_report.session_id,
            turn_id      = gap_report.turn_id,
            total_gaps   = len(gap_report.all_gaps),
        )

        if not gap_report.all_gaps:
            return question_set

        # Work through priority gaps (critical → important → optional)
        generated = 0
        for gap in gap_report.priority_gaps:
            if generated >= self.max_questions_per_turn:
                break

            # Skip if we've already asked about this category 3+ times
            if tracker.times_asked(gap.category_key) >= 3:
                continue

            question = self._generate_for_gap(gap, project_name, state, tracker)
            if question and not tracker.is_asked(question.question_id):
                question_set.questions.append(question)
                tracker.mark_asked(question)
                question_set.addressed_gaps += 1
                generated += 1

        # Set primary question (highest priority, first generated)
        if question_set.questions:
            question_set.primary_question = question_set.questions[0]

        return question_set

    def build_injection_text(self, question_set: QuestionSet) -> str:
        """
        Build the text block to inject into the PromptArchitect CONTEXT block.
        This tells the LLM which gap to probe in its next response.
        """
        if not question_set.has_questions:
            return ""

        primary = question_set.primary_question
        lines = [
            "\n── PROACTIVE QUESTIONING DIRECTIVE ──",
            f"The following requirement category has NOT been covered yet: "
            f"**{primary.category_label}** (severity: {primary.severity.upper()})",
            f"Description: {self._get_category_description(primary.category_key)}",
            "",
            "You MUST weave a targeted question about this topic into your next response.",
            "Do NOT ask it as a separate bullet point — integrate it naturally into the conversation.",
            f"Suggested question: {primary.question_text}",
            "── END DIRECTIVE ──\n",
        ]
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
        """Select and parameterise a question template for the given gap."""
        templates = self._templates.get(gap.category_key, [])
        if not templates:
            return None

        # Choose a template variant based on how many times we've asked before
        asked_count  = tracker.times_asked(gap.category_key)
        template_idx = asked_count % len(templates)
        template     = templates[template_idx]

        # Parameterise
        question_text = template.replace("{project_name}", project_name)

        # Build a stable question ID for deduplication
        question_id = f"{gap.category_key}_{template_idx}"

        rationale = (
            f"Category '{gap.label}' is {'partially' if gap.is_partial else 'not'} covered. "
            f"Severity: {gap.severity.value}. Template variant #{template_idx + 1}."
        )

        return FollowUpQuestion(
            question_id    = question_id,
            category_key   = gap.category_key,
            category_label = gap.label,
            question_text  = question_text,
            severity       = gap.severity.value,
            is_partial     = gap.is_partial,
            rationale      = rationale,
        )

    def _get_category_description(self, key: str) -> str:
        from gap_detector import COVERAGE_CHECKLIST
        return COVERAGE_CHECKLIST.get(key, {}).get("description", "")


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_question_generator(
    max_questions_per_turn: int = 2,
    mode: str = "template",
) -> ProactiveQuestionGenerator:
    """Factory function — mirrors create_* pattern from other modules."""
    return ProactiveQuestionGenerator(
        max_questions_per_turn=max_questions_per_turn,
        mode=mode,
    )