"""
src/components/prompt_architect.py
====================
RE Assistant — Iteration 3 (rev-2) | University of Hildesheim
Modular System Prompt Architecture

Change log
----------
Rev-1  (Iteration 3 fix)
  FIX-1  FR-first elicitation: NFR probing blocked until ≥3 FRs recorded.
  FIX-2  Closure rule raised from 1 FR to 3 FRs minimum.
  FIX-3  FR-deficit warning added to context block, mirroring NFR alert.
  FIX-4  extra_context injection path preserved for GapDetector wiring.

Rev-2  (Pre-Iteration 4 — addresses low elicitation completeness)
  NEW-1  ROLE_BLOCK extended: active vs. passive elicitation philosophy
         added so the LLM understands its job is to DRIVE the conversation,
         not wait for the user to volunteer information.

  NEW-2  TASK_BLOCK completely restructured:
         — Old design: 8 flat rules, no ordering, no phase structure.
           The LLM treated them as equal hints and cherry-picked.
         — New design: four explicit PHASES (Domain → Functional →
           Non-Functional → Closure) with a per-phase checklist the LLM
           must complete before advancing. This mirrors how a real RE
           interview is conducted and prevents premature closure.

  NEW-3  ONE-QUESTION-PER-TURN rule added (was missing entirely).
         The old prompt allowed batched questions which caused the customer
         to give shallow answers to many things instead of deep answers to one.

  NEW-4  REDIRECT rule added: when the customer goes off-topic (feasibility,
         costs, change management) the LLM must acknowledge in ≤1 sentence
         then return to the last uncovered item. Turns 7–11 of the test
         transcript were entirely wasted on off-topic discussion.

  NEW-5  NEVER-ACCEPT-EARLY-CLOSURE rule added. The LLM must reject
         "I think you have a good picture" and name the specific item
         still missing. This directly fixes the Turn 7 failure in the
         test transcript.

  NEW-6  MANDATORY CLOSURE CHECKLIST added as a named, itemised gate.
         Old closure rule was vague ("functional requirements identified
         for all major features"). New checklist names 12 specific items
         that must each be explicitly discussed before SRS generation.

  NEW-7  Probing depth rule added: the LLM must ask one level deeper on
         every answer before changing topic.

Design: Four-block prompt (Iteration 3 rev-2+)
  [ROLE]            — who the assistant is + active elicitation philosophy
  [CONTEXT]         — live coverage state (dynamic per turn)
  [GAP DIRECTIVE]   — targeted follow-up from GapDetector (injected one-shot)
  [TASK]            — phase-gated behavioural rules + closure checklist

All blocks are independently replaceable for ablation studies.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conversation_state import ConversationState


# ---------------------------------------------------------------------------
# IEEE-830 category registry
# ---------------------------------------------------------------------------

IEEE830_CATEGORIES: dict[str, str] = {
    "purpose":           "System Purpose & Goals",
    "scope":             "System Scope & Boundaries",
    "stakeholders":      "Stakeholders & User Classes",
    "functional":        "Functional Requirements",
    "performance":       "Performance Requirements",
    "usability":         "Usability Requirements",
    "security_privacy":  "Security & Privacy Requirements",
    "reliability":       "Reliability & Availability Requirements",
    "compatibility":     "Compatibility & Portability Requirements",
    "maintainability":   "Maintainability Requirements",
    "constraints":       "Design & Implementation Constraints",
    "interfaces":        "External Interfaces",
}

MANDATORY_NFR_CATEGORIES: frozenset[str] = frozenset({
    "performance",
    "usability",
    "security_privacy",
    "reliability",
    "compatibility",
    "maintainability",
})

# Minimum distinct FRs before NFR deep-dive is allowed
MIN_FUNCTIONAL_REQS = 5   # raised from 3 — 5 gives a richer functional baseline


# ---------------------------------------------------------------------------
# ROLE block
# NEW-1: extended with active elicitation philosophy
# ---------------------------------------------------------------------------

ROLE_BLOCK = """\
You are an expert Requirements Engineer with 15 years of industry experience \
conducting structured elicitation interviews. You are rigorous, methodical, \
and precise. You follow IEEE 830 for functional structuring and ISO/IEC 25010 \
for software quality standards. You apply SMART criteria (Specific, Measurable, \
Achievable, Relevant, Time-bound) to ensure every requirement is atomic and testable.

YOUR FUNDAMENTAL JOB — READ THIS BEFORE ANYTHING ELSE:
Your job is ACTIVE elicitation, not passive recording.

  PASSIVE (wrong): User volunteers information → you formalize it → \
ask "is there anything else?"
  ACTIVE (correct): You notice what was NOT said → you ask targeted \
questions to surface hidden requirements, edge cases, and constraints → \
you probe each answer one level deeper before moving on.

A real stakeholder does not know what a "requirement" is. They answer \
what you ask and nothing more. They describe outcomes, not systems. They assume \
obvious things are obvious, they go off-topic, and they try to end the \
interview early. 

YOUR job is to guide the conversation. Be professionally empathetic to their \
business problems, but relentlessly persistent in your questioning. Keep the \
conversation productive, structurally complete, and focused on extracting \
granular details. Do not accept vague statements, and do not let the user \
close the interview until your elicitation framework is fully satisfied.\
"""


# ---------------------------------------------------------------------------
# TASK block
# NEW-2 through NEW-7: phase-gated structure, one-question rule,
# redirect rule, never-accept-early-closure rule, closure checklist,
# probing depth rule.
# ---------------------------------------------------------------------------

TASK_BLOCK = """
═══════════════════════════════════════════════════════════
PHASE STRUCTURE — FOLLOW THIS SEQUENCE STRICTLY
═══════════════════════════════════════════════════════════

You must complete each phase before advancing to the next. 

── PHASE 1: Domain & Context Discovery (turns 1–3) ────────
Goal: Establish the "Why" and "Who" before the "What."
You must identify:
  • The Current State: What is the manual or legacy process? What are the top 3 "pain points"?
  • Stakeholder Ecosystem: Who interacts with the system? (Direct users, admins, external actors).
  • High-Level Scope: What are the boundaries of the system?
Do NOT formalize requirements yet. Just listen and build the mental model.

── PHASE 2: Functional Requirements (IPOS Model) ──────────
Goal: Decompose behaviors into atomic, testable requirements.
You must explicitly explore each of these dimensions:
  □ Data Entities & Storage: What core information must the system "remember" or track?
  □ Inputs & Triggers: How does data enter the system? What events (time, sensor, user action) start a process?
  □ Processing Logic: What are the "business rules" or calculations? How do states change (e.g., "Normal" to "Alert")?
  □ Outputs & Notifications: What are the results? (Reports, alerts, physical actions, dashboard updates).
  □ Search & Management: How do users find, filter, update, or delete information?
  □ Exception Handling: What should happen when things go wrong or data is missing?

── PHASE 3: Non-Functional Requirements (ISO 25010) ───────
Goal: Define the quality attributes (The "How Well").
Ask exactly one focused question for each:
  □ Usability: Who is the "least technical" user? What are their specific needs for ease-of-use?
  □ Performance: What are the expectations for speed, response time, or concurrent handling?
  □ Security & Privacy: Who can see what? How is access controlled? What data is sensitive?
  □ Reliability & Availability: What is the impact of downtime? How does the system recover from failure?
  □ Connectivity & Portability: Does it need to work offline? What devices/platforms must it support?

── PHASE 4: Constraints & Final Validation ────────────────
Goal: Capture "Hard" limits and verify saturation.
Ask about:
  □ Technical/Legacy Constraints: Mandated hardware, specific APIs, or forbidden technologies.
  □ Regulatory/Legal: Are there compliance standards (GDPR, safety codes, etc.)?
  □ Saturation Check: Summarize the key findings and ask: "Is there any edge case or scenario we haven't discussed?"

═══════════════════════════════════════════════════════════
NON-NEGOTIABLE BEHAVIOURAL RULES
═══════════════════════════════════════════════════════════

RULE 1 — ONE QUESTION PER TURN: 
Ask exactly ONE focused question per response. Never combine topics.

RULE 2 — ATOMIC DECOMPOSITION: 
If a user mentions a complex feature (e.g., "Remote Climate Control"), you must break it down into smaller parts (Viewing status, updating status, scheduling). Do not record a "bundle" as a single requirement.

RULE 3 — PROBE BEFORE PROGRESSING:
When a user gives a high-level answer, ask one "deep-dive" follow-up on that specific topic before moving to a new checklist item.

RULE 4 — CHALLENGE VAGUE ADJECTIVES:
If the user says "fast," "secure," "simple," or "easy," you MUST ask for a measurable definition (e.g., "How many seconds is 'fast' to you?").

RULE 5 — THE SATURATION PRINCIPLE:
Do not move from Phase 2 to Phase 3 until the user stops providing new functionality details during your probes.

RULE 6 — REQUIREMENT TAGGING:
Every time a requirement is crystallized, wrap it in XML tags:

<REQ type="functional|non_functional|constraint" category="[relevant_category]">
The system shall [verb] [object] [measurable constraint].
</REQ>

═══════════════════════════════════════════════════════════
MANDATORY CLOSURE CHECKLIST
═══════════════════════════════════════════════════════════
ONLY offer the SRS when:
□ All IPOS dimensions (Input, Process, Output, Storage) have been discussed.
□ At least 4 ISO 25010 quality categories have been defined with metrics.
□ All named stakeholder roles have been mapped to specific functionalities.
□ A Saturation Check has been performed and the user confirms "nothing else.

If any box is unchecked: "Before I generate the SRS, I still need to
ask about [item]. [Ask the one most important uncovered question.]"
"""


# ---------------------------------------------------------------------------
# Dynamic context block (injected fresh every turn)
# ---------------------------------------------------------------------------

def _build_context_block(state: "ConversationState") -> str:
    """
    Build a dynamic context block showing live coverage state.

    Shows:
    - Turn count and requirement counts (FR / NFR split)
    - Phase indicator: which phase the session should be in now
    - IEEE-830 categories covered vs. missing
    - FR deficit warning (blocks NFR probing until MIN_FUNCTIONAL_REQS met)
    - Mandatory NFR alert (once FR threshold is reached)
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

    covered_str = "\n".join(covered) if covered else "  (none yet — you are in Phase 1)"
    missing_str = "\n".join(missing) if missing else "  (all covered — ready to generate SRS)"

    # Phase indicator
    if state.functional_count < MIN_FUNCTIONAL_REQS:
        phase_indicator = (
            f"CURRENT PHASE: Phase 2 — Functional Requirements\n"
            f"  FRs recorded: {state.functional_count} / {MIN_FUNCTIONAL_REQS} minimum\n"
            f"  ➜ Your next question MUST target a functional capability."
        )
    else:
        mandatory_still_missing = [
            cat for cat in MANDATORY_NFR_CATEGORIES
            if cat not in state.covered_categories
        ]
        if mandatory_still_missing:
            phase_indicator = (
                f"CURRENT PHASE: Phase 3 — Non-Functional Requirements\n"
                f"  FRs recorded: {state.functional_count} ✓ (threshold met)\n"
                f"  ➜ Probe NFRs next. Still missing: "
                + ", ".join(IEEE830_CATEGORIES[c] for c in mandatory_still_missing)
            )
        else:
            phase_indicator = (
                "CURRENT PHASE: Phase 4 — Constraints and Closure\n"
                "  All mandatory categories addressed.\n"
                "  ➜ Confirm closure checklist, then offer SRS generation."
            )

    # FR deficit warning (hard block on NFR probing)
    fr_alert = ""
    if state.functional_count < MIN_FUNCTIONAL_REQS:
        fr_alert = (
            f"\n⚠️  FR DEFICIT: {state.functional_count} FR(s) recorded, "
            f"need ≥{MIN_FUNCTIONAL_REQS}.\n"
            "Do NOT ask about NFRs. Your next question must target a "
            "functional behaviour — what the system does, not how well it does it.\n"
        )

    # Mandatory NFR warning (only shown once FR threshold is met)
    mandatory_alert = ""
    if state.functional_count >= MIN_FUNCTIONAL_REQS:
        mandatory_missing = [
            IEEE830_CATEGORIES[cat]
            for cat in MANDATORY_NFR_CATEGORIES
            if cat not in state.covered_categories
        ]
        if mandatory_missing:
            cats = ", ".join(mandatory_missing)
            mandatory_alert = (
                f"\n⚠️  MANDATORY NFRs NOT YET COVERED: {cats}\n"
                "You MUST address all of these before offering to generate the SRS.\n"
            )

    turn_info = (
        f"Turn: {state.turn_count}  |  "
        f"Total requirements: {state.total_requirements}  "
        f"(FR: {state.functional_count}, NFR: {state.nonfunctional_count})"
    )

    return (
        f"SESSION STATE:\n{turn_info}\n\n"
        f"{phase_indicator}\n\n"
        f"IEEE-830 categories COVERED:\n{covered_str}\n\n"
        f"IEEE-830 categories STILL MISSING:\n{missing_str}"
        f"{fr_alert}{mandatory_alert}"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class PromptArchitect:
    """
    Builds the complete system message from modular blocks.

    Block order (rev-2):
      [ROLE]          — active elicitation philosophy + persona
      [CONTEXT]       — dynamic live state (rebuilt every turn)
      [GAP DIRECTIVE] — one-shot injection from GapDetector (optional)
      [TASK]          — phase-gated rules + closure checklist

    Gap detection injection pattern:
        architect.extra_context = question_generator.build_injection_text(q_set)
        system_msg = architect.build_system_message(state)
        # extra_context is auto-cleared after each build (one-shot)
    """

    role_block:    str = field(default=ROLE_BLOCK)
    task_block:    str = field(default=TASK_BLOCK)
    extra_context: str = field(default="")

    def build_system_message(self, state: "ConversationState") -> str:
        """
        Compose the full system message for a given conversation state.
        Context block is rebuilt on every call — state changes are always
        reflected in the next LLM request.
        extra_context (gap directive) is injected between CONTEXT and TASK,
        then cleared immediately (one-shot pattern).
        """
        context_block = _build_context_block(state)

        parts = [
            "=== ROLE ===\n" + self.role_block,
            "=== CURRENT SESSION CONTEXT ===\n" + context_block,
        ]

        if self.extra_context.strip():
            parts.append(
                "=== GAP DETECTION DIRECTIVE ===\n" + self.extra_context
            )
        self.extra_context = ""  # always clear after build — never carry over

        parts.append("=== TASK INSTRUCTIONS ===\n" + self.task_block)

        return "\n\n".join(parts)

    def get_category_labels(self) -> dict[str, str]:
        """Return the full IEEE-830 category registry."""
        return dict(IEEE830_CATEGORIES)

    def get_mandatory_nfr_categories(self) -> frozenset[str]:
        """Return the set of NFR category IDs that must be covered."""
        return MANDATORY_NFR_CATEGORIES

    def get_min_functional_reqs(self) -> int:
        """Return the minimum FR count threshold for NFR probing."""
        return MIN_FUNCTIONAL_REQS