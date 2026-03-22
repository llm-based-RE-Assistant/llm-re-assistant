"""
src/components/prompt_architect.py
====================
RE Assistant — Iteration 2 | University of Hildesheim
Modular System Prompt Architecture

Responsibilities
----------------
- Build the system message from discrete, independently-testable blocks
- Enforce mandatory NFR coverage checklist (addresses Failure Mode 2: Privacy/Security blind spot)
- Inject ambiguity challenge instructions (addresses Failure Mode 1: ambiguity acceptance)
- Inject conversation-state context so the LLM knows what is still missing
  (addresses Failure Mode 3: premature closure via fixed-template)

Design: Three-block prompt
  [ROLE]    — who the assistant is and its expertise
  [CONTEXT] — what IEEE-830 categories are already covered vs. still missing (dynamic)
  [TASK]    — explicit behavioural instructions (ambiguity challenge, NFR checklist, etc.)

All blocks are independently replaceable, which supports ablation studies in later iterations.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conversation_state import ConversationState


# ---------------------------------------------------------------------------
# IEEE-830 category registry
# These are the canonical categories tracked throughout the session.
# Keys are short internal IDs; values are human-readable labels.
# ---------------------------------------------------------------------------
IEEE830_CATEGORIES: dict[str, str] = {
    "purpose":           "System Purpose & Goals",
    "scope":             "System Scope & Boundaries",
    "stakeholders":      "Stakeholders & User Classes",
    "functional":        "Functional Requirements",
    "performance":       "Performance Requirements",
    "usability":         "Usability Requirements",
    "security_privacy":  "Security & Privacy Requirements",   # historically missed
    "reliability":       "Reliability & Availability Requirements",
    "compatibility":     "Compatibility & Portability Requirements",
    "maintainability":   "Maintainability Requirements",
    "constraints":       "Design & Implementation Constraints",
    "interfaces":        "External Interfaces",
}

# NFR categories that MUST be explicitly probed (Failure Mode 2 fix)
MANDATORY_NFR_CATEGORIES: frozenset[str] = frozenset({
    "performance",
    "usability",
    "security_privacy",
    "reliability",
    "compatibility",
    "maintainability",
})


# ---------------------------------------------------------------------------
# Prompt blocks (static)
# ---------------------------------------------------------------------------

ROLE_BLOCK = """You are an expert Requirements Engineer with 15 years of industry experience \
conducting structured elicitation interviews. You are rigorous, methodical, and precise. \
Your goal is to elicit COMPLETE, TESTABLE requirements for a software system through a \
natural, conversational dialogue.

You follow IEEE 830 as your specification standard. You are familiar with SMART criteria \
(Specific, Measurable, Achievable, Relevant, Time-bound/Testable) and apply them to every \
requirement you record."""


TASK_BLOCK = """BEHAVIOURAL INSTRUCTIONS — FOLLOW THESE WITHOUT EXCEPTION:

1. AMBIGUITY CHALLENGE RULE (Critical):
   When the user provides vague qualifiers — such as "simple", "fast", "easy", "modern", \
"user-friendly", "good performance", "automated", "high quality", "flexible", "scalable", \
"secure", "robust", or similar adjectives — you MUST ask for a measurable operationalisation \
BEFORE recording or accepting the term. Do not paraphrase vague terms into the SRS verbatim.
   Example: User says "it should be fast" → You respond: "What does 'fast' mean in measurable \
terms? For example, should the system respond within 2 seconds, 5 seconds, or something else?"

2. MANDATORY NFR COVERAGE (Critical):
   Before ending the session, you MUST have explicitly addressed ALL of the following NFR categories:
   - Performance (response times, throughput, capacity)
   - Usability (who are the users? what is their technical level? any accessibility needs?)
   - Security & Privacy (authentication, data protection, GDPR applicability, sensitive data handling)
   - Reliability (uptime, recovery time, data persistence guarantees)
   - Compatibility (platforms, browsers, operating systems, integrations)
   - Maintainability (who will maintain this? update frequency? open standards?)
   If any of these remain uncovered, you MUST ask about them before generating the SRS.

3. MULTI-TURN ELICITATION RULE:
   Do NOT ask all questions in one batch. Ask focused follow-up questions based on previous answers. \
Each turn should deepen understanding of one area. Only transition to a new area when the current \
one is adequately covered.

4. CONFLICT DETECTION:
   If the user provides contradictory information (e.g., "no budget constraints" but also \
"we need sensors on every bin"), surface the contradiction explicitly: "I noticed a potential \
conflict between X and Y — could you clarify how you'd like to resolve this?"

5. REQUIREMENT FORMALISATION:
   As you elicit requirements, mentally structure them as: \
"The system shall [action] [object] [constraint]." \
If a requirement cannot be phrased this way, it needs further clarification.

6. CONVERSATION CLOSURE:
   Only suggest generating the SRS when ALL of the following are true:
   (a) Functional requirements have been identified for all major features.
   (b) ALL 6 mandatory NFR categories have been addressed.
   (c) No unresolved ambiguities remain.
   (d) Stakeholder roles have been identified.
   If not all conditions are met, continue elicitation and explain what is still missing."""


def _build_context_block(state: "ConversationState") -> str:
    """
    Build a dynamic context block that injects current coverage status into
    the system prompt. This gives the LLM explicit knowledge of what remains
    uncovered, directly addressing Failure Mode 3 (premature closure).
    """
    covered = [
        f"  ✓ {IEEE830_CATEGORIES[cat]}"
        for cat in state.covered_categories
        if cat in IEEE830_CATEGORIES
    ]
    missing = [
        f"  ✗ {IEEE830_CATEGORIES[cat]}"
        for cat in IEEE830_CATEGORIES
        if cat not in state.covered_categories
    ]

    covered_str = "\n".join(covered) if covered else "  (none yet)"
    missing_str = "\n".join(missing) if missing else "  (all covered — ready to generate SRS)"

    # Flag mandatory NFRs still uncovered
    mandatory_missing = [
        IEEE830_CATEGORIES[cat]
        for cat in MANDATORY_NFR_CATEGORIES
        if cat not in state.covered_categories
    ]
    mandatory_alert = ""
    if mandatory_missing:
        cats = ", ".join(mandatory_missing)
        mandatory_alert = (
            f"\n⚠️  MANDATORY NFR CATEGORIES NOT YET COVERED: {cats}\n"
            "You MUST address these before offering to generate the SRS.\n"
        )

    turn_info = (
        f"Current turn: {state.turn_count}\n"
        f"Requirements elicited so far: {state.total_requirements}\n"
        f"  Functional: {state.functional_count}\n"
        f"  Non-functional: {state.nonfunctional_count}"
    )

    return f"""CURRENT SESSION STATE:
{turn_info}

IEEE-830 categories COVERED so far:
{covered_str}

IEEE-830 categories STILL MISSING:
{missing_str}
{mandatory_alert}"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class PromptArchitect:
    """
    Builds the complete system message from three modular blocks.

    Blocks
    ------
    ROLE    — static, defines persona and expertise
    CONTEXT — dynamic, injected from ConversationState each turn
    TASK    — static, defines behavioural rules (ambiguity challenge, NFR checklist)

    Usage
    -----
    architect = PromptArchitect()
    system_msg = architect.build_system_message(state)
    """

    role_block: str = field(default=ROLE_BLOCK)
    task_block: str = field(default=TASK_BLOCK)

    def build_system_message(self, state: "ConversationState") -> str:
        """
        Compose the full system message for a given conversation state.
        The context block is rebuilt on every call, so state changes are
        always reflected in the next LLM request.
        """
        context_block = _build_context_block(state)

        return (
            "=== ROLE ===\n"
            f"{self.role_block}\n\n"
            "=== CURRENT SESSION CONTEXT ===\n"
            f"{context_block}\n\n"
            "=== TASK INSTRUCTIONS ===\n"
            f"{self.task_block}"
        )

    def get_category_labels(self) -> dict[str, str]:
        """Return the full IEEE-830 category registry."""
        return dict(IEEE830_CATEGORIES)

    def get_mandatory_nfr_categories(self) -> frozenset[str]:
        """Return the set of NFR category IDs that must be covered."""
        return MANDATORY_NFR_CATEGORIES