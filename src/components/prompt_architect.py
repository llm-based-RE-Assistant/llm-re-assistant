"""
src/components/prompt_architect.py — Iteration 5
University of Hildesheim

Fixes:
  FIX-JARGON  Rule added: NEVER use technical domain labels in questions.
              Always rephrase with a concrete example from the user's own system.
  FIX-NFR     Phase 3 now mandatory — system cannot offer SRS until all 6
              mandatory NFRs are covered.
  FIX-DEPTH   Probe depth reduced to 1 follow-up per domain to prevent loops.
              Quality comes from decomposition, not over-probing.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from conversation_state import ConversationState

IEEE830_CATEGORIES: dict[str, str] = {
    "purpose":"System Purpose & Goals","scope":"System Scope & Boundaries",
    "stakeholders":"Stakeholders & User Classes","functional":"Functional Requirements",
    "performance":"Performance Requirements","usability":"Usability Requirements",
    "security_privacy":"Security & Privacy Requirements",
    "reliability":"Reliability & Availability Requirements",
    "compatibility":"Compatibility & Portability Requirements",
    "maintainability":"Maintainability Requirements",
    "constraints":"Design & Implementation Constraints",
    "interfaces":"External Interfaces",
}
MANDATORY_NFR_CATEGORIES = frozenset({
    "performance","usability","security_privacy","reliability","compatibility","maintainability"})
MIN_FUNCTIONAL_REQS = 10

ROLE_BLOCK = """\
You are an expert Requirements Engineer conducting a structured elicitation \
interview. You follow IEEE 830 and ISO/IEC 25010 standards.

YOUR FUNDAMENTAL JOB:
You are an ACTIVE elicitor, not a passive recorder. A real stakeholder does \
not know what a "requirement" is. They describe what they want in vague, \
conversational language. Your job is to:
1. Extract what they explicitly stated as formal requirements.
2. INFER what they assumed but did not say — and ask about it.
3. ADD measurable constraints (how many, what range, what units).
4. PROBE for capacity limits, boundary values, and error cases.

COMMUNICATION STYLE — THIS IS CRITICAL:
- Use PLAIN EVERYDAY LANGUAGE. The stakeholder is not a software engineer.
- NEVER use technical domain labels like "Error Detection & Recovery" or \
"System Maintenance Tools" in your questions. The stakeholder won't understand.
- Instead, describe the concept with a CONCRETE EXAMPLE from their own system:
  BAD:  "Can you tell me about the System Maintenance Tools aspects?"
  GOOD: "Who keeps the system running — like, if there's a software update \
or something breaks, should it fix itself or do you need to call someone?"
  BAD:  "Tell me about Error Detection & Recovery"
  GOOD: "What should happen if something goes wrong — say a thermostat \
stops responding or the internet goes out at home?"

Do not let the user close the interview until the DOMAIN COVERAGE GATE shown \
in the Context block is fully satisfied.\
"""

TASK_BLOCK = """
═══════════════════════════════════════════════════════════
YOUR PRIMARY INSTRUCTION — READ FIRST
═══════════════════════════════════════════════════════════

The Session Context above contains a ⛔ HARD STOP or ✅ message.
OBEY IT BEFORE READING ANYTHING ELSE.

If ⛔ HARD STOP: your response after any <REQ> tags must be exactly ONE
question ending in '?'. Nothing more. No summaries. No SRS offer.

═══════════════════════════════════════════════════════════
PHASE STRUCTURE
═══════════════════════════════════════════════════════════

PHASE 1 (turns 1-2): Listen. Build context. No requirements yet.

PHASE 2 (turns 3+): Work through every domain in the gate.
  For each domain:
  1. Ask an open-ended question about this topic using PLAIN LANGUAGE
     and a CONCRETE EXAMPLE from the user's system.
  2. Extract <REQ> tags from their answer.
  3. Ask ONE deeper follow-up targeting what they missed
     (numbers, ranges, capacities, what-if scenarios).
  4. Move on to the next domain.

PHASE 3: After domain gate satisfied, ask about EACH missing NFR category.
  This phase is MANDATORY — you cannot skip it or offer SRS until done.
  Use plain language with examples for each:
  - Performance: "How quickly should things respond when you tap a button?"
  - Usability: "Your kids and mother-in-law will use this too — what would
    make it easy enough for the least technical person?"
  - Security: "How should people log in, and should anyone be locked out
    of certain features?"
  - Reliability: "How dependable does this need to be — like, is it okay
    if it goes down for a few minutes sometimes?"
  - Compatibility: "What phones or devices does everyone in the family use?"
  - Maintainability: "Who keeps everything running and handles updates?"

PHASE 4: When all gates are satisfied, complete IEEE 830 sections.
    This phase is very important for quality! Don't skip it by offering SRS too early.
    Ask about each section with plain language and examples:
    - 1.2 Scope: "What is in scope for this system, and what is out of scope?"
    - 2.1 Product Perspective: "Does this system connect to or depend on any other systems or services?"
    - 2.3 User Classes and Characteristics: "Who are the different users, and their requirements or permissions might be different?"
    - 2.4 Operating Environment: "Details hardware, software, and operational environment. For example, does it run on phones, tablets, or computers? Does it need to work without internet?"
    - 2.6 User Documentation: "What kind of help or instructions should the system provide?"
    - 2.7 Assumptions & Dependencies: "Factors that, if changed, would affect requirements. Are there any external factors or systems this depends on, or any assumptions we haven't discussed?"
    - 3.1 External Interface Requirements: "User interfaces, hardware interfaces, software interfaces, and communication protocols. What devices, apps, or services should this system connect to or work with?"
    - 3.2 System Features: "Any specific features or capabilities we haven't discussed yet?"
    - 3.4 Design and Implementation Constraints: "Regulatory policies, hardware limitations, and interfaces. Are there any rules or limits around how this should be designed or built, like it has to work on old phones or follow certain regulations?"
    then offer SRS generation.

═══════════════════════════════════════════════════════════
NON-NEGOTIABLE RULES
═══════════════════════════════════════════════════════════

RULE 1 — ONE QUESTION PER RESPONSE, ALWAYS.
RULE 2 — ATOMIC REQUIREMENTS: one per <REQ> tag.
RULE 3 — ALWAYS ADD NUMBERS when extracting capacity/range/timing reqs.
RULE 4 — NO JARGON: never put technical terms or domain labels in questions.
         Always rephrase with a concrete example.
RULE 5 — NO EARLY CLOSURE: if ⛔ HARD STOP, ignore user's "I think that's it".
RULE 6 — REQUIREMENT FORMAT:
  <REQ type="functional|non_functional|constraint" category="[category]">
  The system shall [verb] [object] [measurable constraint].
  </REQ>
RULE 7 — SCOPE REDUCTIONS: confirm if out of scope permanently or for now.
         Do NOT treat excluding ONE feature as excluding the ENTIRE domain.
RULE 8 — INFER TYPICAL REQUIREMENTS: if stakeholder's answer is vague,
         extract what a system of this type would typically need.
"""

_STATUS_ICONS = {"confirmed":"✅","partial":"🔶","unprobed":"⬜","excluded":"❌"}

def _build_context_block(state: "ConversationState") -> str:
    from domain_discovery import NFR_CATEGORIES, DomainGate

    turn_info = (f"Turn: {state.turn_count}  |  "
                 f"Requirements: {state.total_requirements}  "
                 f"(FR: {state.functional_count}, NFR: {state.nonfunctional_count})")

    gate: DomainGate | None = state.domain_gate
    gate_satisfied = gate is not None and gate.is_satisfied
    gate_seeded = gate is not None and gate.seeded

    nfr_missing = [cat for cat in NFR_CATEGORIES if state.nfr_coverage.get(cat,0) < 1]

    _NFR_PROBES = {
        "performance":"How quickly should things respond when you tap a button — what would feel too slow?",
        "usability":"Who is the least technical person using this, and what would make it simple enough for them?",
        "security_privacy":"How should people log in, and should certain features be restricted from some users?",
        "reliability":"How dependable does this need to be — is it okay if it goes down briefly, or must it always work?",
        "compatibility":"What phones, tablets, or computers does everyone in the family use?",
        "maintainability":"Who keeps the system running after it's set up — should it update itself, or does someone manage it?",
    }

    hard_stop = ""

    if not gate_seeded:
        hard_stop = ("⏳ DOMAIN GATE NOT YET SEEDED\n Ask what the system should do and what features they want.")
    elif not gate_satisfied:
        nd = gate.next_unprobed()
        if nd:
            probe_q = nd.probe_question or (
                f"I'd like to understand more about how you'd use the "
                f"{nd.label.lower()} features — for example, "
                f"how often would you use them and what's most important?")
            done, total = gate.done_count, gate.total
            hard_stop = (
                f"⛔ HARD STOP — DOMAIN GATE [{done}/{total}]\n"
                f"NEXT DOMAIN: {nd.label}\n"
                f"Ask this (adapt to plain language with examples):\n"
                f"\"{probe_q}\"\n"
                f"Do NOT summarize. Do NOT offer SRS. ONE question only.")
        else:
            # Gate not satisfied but no "unprobed/partial-needy" domain found.
            # Remaining domains are "partial" — force-probe them.
            partial_domains = [d for d in gate.domains.values() if d.status == "partial"]
            remaining = [d for d in gate.domains.values()
                         if d.status not in ("confirmed", "excluded")]
            target = partial_domains[0] if partial_domains else remaining[0] if remaining else None
            done, total = gate.done_count, gate.total
            if target:
                probe_q = target.probe_question or (
                    f"I'd like to understand a bit more about the "
                    f"{target.label.lower()} side of things — "
                    f"what should it do and are there any limits or rules around it?")
                hard_stop = (
                    f"⛔ HARD STOP — DOMAIN GATE [{done}/{total}] (partial domains remain)\n"
                    f"NEXT DOMAIN: {target.label}\n"
                    f"Ask this (adapt to plain language with examples):\n"
                    f"\"{probe_q}\"\n"
                    f"Do NOT summarize. Do NOT offer SRS. ONE question only.")
            else:
                hard_stop = (
                    f"⛔ HARD STOP — DOMAIN GATE [{done}/{total}] INCOMPLETE\n"
                    f"Do NOT close the session. Ask about any uncovered features.\n"
                    f"ONE question only.")
    elif nfr_missing and state.functional_count >= MIN_FUNCTIONAL_REQS:
        # FIX-NFR: mandatory NFR phase
        next_nfr = nfr_missing[0]
        probe = _NFR_PROBES.get(next_nfr, f"Tell me about your {next_nfr} needs.")
        label = IEEE830_CATEGORIES.get(next_nfr, next_nfr)
        hard_stop = (
            f"⛔ HARD STOP — MANDATORY NFR MISSING: {label}\n"
            f"Domain gate satisfied. Now ask about this quality requirement.\n"
            f"Use plain language: \"{probe}\"\n"
            f"Ask for SPECIFIC MEASURABLE values. Do NOT offer SRS yet.")
    else:
        done = gate.done_count if gate else 0
        total = gate.total if gate else 0
        hard_stop = (
            f"✅ ALL GATES SATISFIED [{done}/{total} domains, all NFRs covered]\n"
            f"Ask final questions if not yet covered:\n"
            f"1. Who are the different users and do they have different permissions?\n"
            f"2. What kind of help or documentation should the system provide?\n"
            f"3. Any scenarios we haven't discussed?\n"
            f"Then offer SRS generation.")
    
    # Domain gate table
    gate_lines = []
    if gate_seeded and gate:
        gate_lines.append(f"DOMAIN GATE [{gate.done_count}/{gate.total} — {gate.completeness_pct}%]")
        for d in gate.domains.values():
            icon = _STATUS_ICONS.get(d.status, "⬜")
            gate_lines.append(f"  {icon} {d.label} [{len(d.req_ids)} reqs]")
    else:
        gate_lines.append("DOMAIN GATE [not yet seeded]")

    # NFR coverage
    nfr_lines = ["NFR COVERAGE:"]
    for ck, cl in NFR_CATEGORIES.items():
        count = state.nfr_coverage.get(ck, 0)
        nfr_lines.append(f"  {'✅' if count>=1 else '⬜'} {cl} ({count} req)")

    covered = state.covered_categories
    ieee_pct = round(len(covered)/len(IEEE830_CATEGORIES)*100)

    fr_alert = ""
    if state.functional_count < MIN_FUNCTIONAL_REQS:
        fr_alert = f"\n⚠️ FR DEFICIT: {state.functional_count} FRs, need ≥{MIN_FUNCTIONAL_REQS}\n"

    return (f"SESSION STATE:\n{turn_info}\n\n"
            f"{hard_stop}\n\n"
            f"{chr(10).join(gate_lines)}\n\n"
            f"{chr(10).join(nfr_lines)}\n\n"
            f"IEEE-830 Coverage: {len(covered)}/{len(IEEE830_CATEGORIES)} ({ieee_pct}%)"
            f"{fr_alert}")


@dataclass
class PromptArchitect:
    role_block: str = field(default=ROLE_BLOCK)
    task_block: str = field(default=TASK_BLOCK)
    extra_context: str = field(default="")

    def build_system_message(self, state):
        ctx = _build_context_block(state)
        parts = ["=== ROLE ===\n"+self.role_block,
                 "=== CURRENT SESSION CONTEXT ===\n"+ctx]
        if self.extra_context.strip():
            parts.append("=== GAP DETECTION DIRECTIVE ===\n"+self.extra_context)
        self.extra_context = ""
        parts.append("=== TASK INSTRUCTIONS ===\n"+self.task_block)
        return "\n\n".join(parts)

    def get_category_labels(self): return dict(IEEE830_CATEGORIES)
    def get_mandatory_nfr_categories(self): return MANDATORY_NFR_CATEGORIES
    def get_min_functional_reqs(self): return MIN_FUNCTIONAL_REQS
    def is_srs_generation_permitted(self, state): return state.is_ready_for_srs()