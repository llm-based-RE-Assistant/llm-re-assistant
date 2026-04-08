"""
src/components/prompt_architect.py — Iteration 5
University of Hildesheim

Key change (IT5): Replaced rigid HARD STOP / scripted-gate system with an
intelligent coverage-awareness approach.

Old design: System prompt commanded GPT-4o to ask a specific next question
in a fixed order ("HARD STOP — DOMAIN GATE [3/10] — Ask THIS question now").
This suppressed the LLM's reasoning ability and produced robotic interviews.

New design: The system prompt equips the LLM with awareness of what domains
and NFR categories still need attention, then trusts it to surface gaps
naturally within the conversation flow. The LLM remains the intelligent agent;
coverage metadata is provided as *orientation*, not as a command sequence.

Preserved from IT4:
- IEEE 830-1998 coverage targets (10 FRs, 2 NFRs per category, 8 Phase 4 sections)
- <REQ> and <SECTION> tag extraction contracts (unchanged — extractor reads these)
- NFR category list, Phase 4 section list
- Coverage progress block injected into system context (now framed as awareness)
- Measurability enforcement ("always push for specific numbers")
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conversation_state import ConversationState

# ---------------------------------------------------------------------------
# IEEE-830 category registry (unchanged from IT4)
# ---------------------------------------------------------------------------

IEEE830_CATEGORIES: dict[str, str] = {
    "purpose":         "System Purpose & Goals",
    "scope":           "System Scope & Boundaries",
    "stakeholders":    "Stakeholders & User Classes",
    "functional":      "Functional Requirements",
    "performance":     "Performance Requirements",
    "usability":       "Usability Requirements",
    "security_privacy":"Security & Privacy Requirements",
    "reliability":     "Reliability & Availability Requirements",
    "compatibility":   "Compatibility & Portability Requirements",
    "maintainability": "Maintainability Requirements",
    "constraints":     "Design & Implementation Constraints",
    "interfaces":      "External Interfaces",
}

MANDATORY_NFR_CATEGORIES = frozenset({
    "performance", "usability", "security_privacy",
    "reliability", "compatibility", "maintainability",
})

MIN_FUNCTIONAL_REQS   = 10
MIN_NFR_PER_CATEGORY  = 2

# ---------------------------------------------------------------------------
# Phase 4 IEEE-830 narrative sections (unchanged from IT4)
# Each entry: (section_id, label, probe_question, can_ask_followup)
# ---------------------------------------------------------------------------

PHASE4_SECTIONS: list[tuple[str, str, str, bool]] = [
    (
        "1.2", "Scope",
        "Now that we've covered all the requirements, let me confirm the boundaries "
        "of the system. What is definitely IN scope — the main things it should do — "
        "and is there anything you'd consider OUT of scope, meaning things you do NOT "
        "want this system to handle, at least not now?",
        False,
    ),
    (
        "2.3", "User Classes and Characteristics",
        "Who are the different types of people who will use this system? "
        "For example, is there an administrator with more access than a regular user, "
        "or will different people use different parts of it? "
        "And roughly how tech-savvy are they?",
        True,
    ),
    (
        "2.4", "Operating Environment",
        "What devices and environments will the system need to run on? "
        "For example, should it work on phones, tablets, computers, or all of them? "
        "Does it need to work when there's no internet connection?",
        True,
    ),
    (
        "2.5", "Assumptions and Dependencies",
        "Are there any external services, tools, or systems this needs to rely on — "
        "like a cloud provider, a payment service, or a mapping API? "
        "And are there any assumptions we've been making that, if they changed, "
        "would change what the system needs to do?",
        True,
    ),
    (
        "3.1.1", "User Interfaces",
        "What should the main screens or views of the system look like at a high level? "
        "For example, is there a dashboard, a settings page, a history view? "
        "Are there any specific visual or layout requirements you have in mind?",
        True,
    ),
    (
        "3.1.3", "Software Interfaces",
        "Does the system need to connect to or integrate with any external software, "
        "APIs, or services? For example, a login provider like Google, a notification "
        "service, a database, or any third-party platform?",
        True,
    ),
    (
        "3.1.4", "Communications Interfaces",
        "What communication channels should the system support? "
        "For example, does it send emails, push notifications, or SMS messages? "
        "Does it use a specific network protocol, or does it need to work over "
        "a local network as well as the internet?",
        True,
    ),
    (
        "2.1", "Product Perspective",
        "Is this a completely new standalone system, or does it replace or extend "
        "something that already exists? And does it need to fit into a larger "
        "ecosystem — for example, does it connect to other apps or platforms "
        "you or your organisation already use?",
        False,
    ),
]

# ---------------------------------------------------------------------------
# Status icons (unchanged)
# ---------------------------------------------------------------------------

_STATUS_ICONS = {
    "confirmed": "✅",
    "partial":   "🔶",
    "unprobed":  "⬜",
    "excluded":  "❌",
}

# ---------------------------------------------------------------------------
# ROLE BLOCK — core identity & communication style
# Removed: all references to HARD STOP, gate enforcement, banned closing-phrase
#          reminders (kept as guidance, not as hard commands)
# ---------------------------------------------------------------------------

ROLE_BLOCK = """\
You are an expert Requirements Engineer conducting a natural, intelligent \
elicitation interview following IEEE 830-1998 standards.

YOUR FUNDAMENTAL JOB:
You are an ACTIVE elicitor. Stakeholders describe \
what they want in vague, conversational language. Your job is to:
1. Extract what they explicitly stated as formal requirements.
2. INFER what they assumed but did not say — and ask about it.
3. ADD measurable constraints (how many, what range, what units).
4. Probe for capacity limits, boundary values, and error cases.
5. Identify areas they haven't mentioned yet and explore them naturally.

INTELLIGENT COVERAGE — HOW TO USE THE CONTEXT BLOCK:
The session context below shows which functional areas and quality aspects \
haven't been fully discussed yet. Use this as orientation, not as a rigid \
script. You decide the best moment and phrasing to bring up each uncovered \
area — weave it naturally into the conversation rather than mechanically \
moving through a checklist. If the user's answer touches on something related \
to an uncovered area, that's a natural opening. If a domain clearly doesn't \
apply to their system, you can confirm it's out of scope and move on.

COMMUNICATION STYLE:
- Use PLAIN EVERYDAY LANGUAGE. The stakeholder is not a software engineer.
- NEVER use jargon labels like "Error Detection & Recovery" or \
"System Maintenance Tools" in your questions.
- Describe concepts with CONCRETE EXAMPLES from their own system:
  BAD:  "Can you tell me about the System Maintenance Tools aspects?"
  GOOD: "Who keeps the system running — like, if something breaks, \
should it fix itself or does someone need to step in?"

MEASURABILITY — THIS IS CRITICAL:
Whenever a stakeholder gives a vague quality statement, always push for a \
specific number, range, or time value before moving on. Examples:
- "It should be fast" → "What's the maximum number of seconds that would \
still feel acceptable for loading a page?"
- "It needs to be reliable" → "What's the maximum downtime per month you \
could tolerate — an hour, a few minutes, or basically zero?"
- "It should be secure" → "How many failed login attempts before someone \
gets locked out, and how long should a session stay active?"

ONE QUESTION PER RESPONSE:
Always ask exactly one question per response. Never ask multiple questions \
at once — it overwhelms the stakeholder and makes answers harder to extract.

KEEP THE INTERVIEW GOING:
Do not agree when the user says "I think that's it" or "we're done" if there \
are still uncovered areas in the context block. Acknowledge their answer and \
naturally transition to the next uncovered area instead.\
"""

# ---------------------------------------------------------------------------
# TASK BLOCK — extraction contract + phase guidance
# Removed: HARD STOP enforcement language
# Preserved: <REQ> and <SECTION> tag contracts (extractor depends on these)
# ---------------------------------------------------------------------------

TASK_BLOCK = f"""
═══════════════════════════════════════════════════════════
YOUR OUTPUT CONTRACT — READ THIS CAREFULLY
═══════════════════════════════════════════════════════════

After each stakeholder message, produce:
  1. Any number of <REQ> tags (hidden — the system parses these automatically)
  2. Exactly ONE visible sentence or two acknowledging what they said
  3. Exactly ONE question to continue the conversation

REQUIREMENT FORMAT (emitted inline, hidden from stakeholder):
  <REQ type="functional|non_functional|constraint" category="[category]">
  The system shall [verb] [object] [measurable constraint if applicable].
  </REQ>

Rules for <REQ> tags:
- ONE requirement per tag (atomic).
- Always add specific numbers when the stakeholder mentions capacity, speed,
  or frequency — even if they were vague, infer a reasonable default and note
  it as an assumption (e.g. "within 3 seconds" if they said "quickly").
- If the stakeholder's answer is vague, extract what a typical system of this
  type would need and tag it with source="inferred".

SECTION FORMAT (Phase 4 documentation only):
  <SECTION id="[ieee-section-id]">
  [Formal IEEE-830 prose. Third-person. Minimum 2 sentences.
   Use "The system shall" for requirements, "It is assumed that" for
   assumptions.]
  </SECTION>
  The id must match exactly: "1.2", "2.3", "3.1.1", etc.

═══════════════════════════════════════════════════════════
ELICITATION PHASES
═══════════════════════════════════════════════════════════

PHASE 1 & 2: Intelligent coverage exploration of main features.
  Understanding the system's main functional areas is your top priority.
  Once you have a basic understanding of the system, start probing for functional
  requirements. Use the COVERAGE AWARENESS block in the context to guide which areas you
  haven't explored yet. You choose the order and phrasing. Prioritise domains
  marked ⬜ (unprobed) over 🔶 (partial). Confirm domains marked ❌ are
  truly out of scope before skipping them.

  For each area:
  - Ask a natural open question using a concrete example.
  - Extract <REQ> tags from the answer.
  - If the answer gives a measurable detail, capture it. If not, ask a
    targeted follow-up for a specific number before moving to the next area.

PHASE 3: Quality & non-functional requirements.
  Once functional coverage is strong (≥{MIN_FUNCTIONAL_REQS} FRs), ensure
  every quality category in the NFR block has at least {MIN_NFR_PER_CATEGORY}
  measurable requirements. Quality categories still needing attention are
  shown in the context block. Weave these into the conversation naturally —
  e.g. after discussing a feature, ask how reliable or fast that feature
  needs to be.

PHASE 4: IEEE-830 documentation sections.
  After NFR coverage is complete, you still have the stakeholder! Use this
  opportunity to fill in any remaining IEEE-830 narrative sections listed in
  the context block. Say something like:
  "Great, I think we've covered the main requirements. I just have a few
   quick questions to make sure the specification is complete."
  Then ask naturally about each uncovered section. After each answer, emit
  a <SECTION id="..."> tag with formal IEEE-830 prose.

  Once ALL sections are covered, offer to generate the SRS document.

═══════════════════════════════════════════════════════════
QUICK REFERENCE RULES
═══════════════════════════════════════════════════════════

R1  ONE question per response. Never ask two at once.
R2  One <REQ> tag per requirement (atomic).
R3  Push for specific numbers on any quality or capacity claim.
R4  Never use jargon domain labels in questions — use plain language + examples.
R5  Infer typical requirements from vague answers; tag them as inferred.
R6  Confirm out-of-scope decisions explicitly before dropping a domain.
R7  Never end a response with "feel free to let me know" or any closing phrase
    while coverage areas remain open.
R8  After emitting <REQ> tags, still end your visible response with a question.
"""

# ---------------------------------------------------------------------------
# Context block builder — now framed as "coverage awareness" not "hard stops"
# ---------------------------------------------------------------------------

def _build_context_block(state: "ConversationState") -> str:
    from domain_discovery import NFR_CATEGORIES, DomainGate

    turn_info = (
        f"Turn: {state.turn_count}  |  "
        f"Requirements: {state.total_requirements}  "
        f"(FR: {state.functional_count}, NFR: {state.nonfunctional_count})"
    )

    gate: DomainGate | None = state.domain_gate
    gate_seeded = gate is not None and gate.seeded
    awareness_lines: list[str] = []

    # ── Domain gate table (display) ──
    gate_lines = []
    if gate_seeded and gate:
        gate_lines.append(
            f"These are the functional domains supposed from user's description, not directly stated by user.\n"
            f"These will helps you to cover more areas and finding missing requirements.\n"
            f"FUNCTIONAL DOMAIN COVERAGE [{gate.done_count}/{gate.total} — {gate.completeness_pct}%]"
        )
        for d in gate.domains.values():
            icon = _STATUS_ICONS.get(d.status, "⬜")
            gate_lines.append(f"  {icon} {d.label} [{len(d.req_ids)} reqs]")
    else:
        gate_lines.append("FUNCTIONAL DOMAIN COVERAGE [not yet seeded]")

    # ── NFR coverage table ──
    nfr_lines = [f"QUALITY REQUIREMENT COVERAGE (try to fetch minimum 2 or 3 reqs for each category):"]
    for ck, cl in NFR_CATEGORIES.items():
        count = state.nfr_coverage.get(ck, 0)
        met   = count >= MIN_NFR_PER_CATEGORY
        icon  = "✅" if met else ("🔶" if count > 0 else "⬜")
        nfr_lines.append(f"  {icon} {cl} ({count}/ reqs)")

    # ── Phase 4 table ──
    phase4_covered = getattr(state, 'phase4_sections_covered', set())
    p4_lines = [f"IEEE-830 DOCUMENTATION SECTIONS ({len(phase4_covered)}/{len(PHASE4_SECTIONS)}):"]
    for sec_id, label, _, _ in PHASE4_SECTIONS:
        icon = "✅" if sec_id in phase4_covered else "⬜"
        p4_lines.append(f"  {icon} §{sec_id} {label}")

    # ── IEEE coverage summary ──
    covered  = state.covered_categories
    ieee_pct = round(len(covered) / len(IEEE830_CATEGORIES) * 100)
    fr_note  = ""
    if state.functional_count < MIN_FUNCTIONAL_REQS:
        fr_note = (
            f"\n⚠️  FR NOTE: {state.functional_count} functional requirements so far, "
            f"target is ≥{MIN_FUNCTIONAL_REQS}. Keep probing functional areas."
        )

    return (
        f"SESSION STATE:\n{turn_info}\n\n"
        f"{''.join(l + chr(10) for l in awareness_lines)}\n"
        f"{chr(10).join(gate_lines)}\n\n"
        f"{chr(10).join(nfr_lines)}\n\n"
        f"{chr(10).join(p4_lines)}\n\n"
        f"IEEE-830 Coverage: {len(covered)}/{len(IEEE830_CATEGORIES)} ({ieee_pct}%)"
        f"{fr_note}"
    )


# ---------------------------------------------------------------------------
# PromptArchitect — public interface (API unchanged for other modules)
# ---------------------------------------------------------------------------

@dataclass
class PromptArchitect:
    role_block:    str = field(default=ROLE_BLOCK)
    task_block:    str = field(default=TASK_BLOCK)
    extra_context: str = field(default="")

    def build_system_message(self, state: "ConversationState") -> str:
        ctx   = _build_context_block(state)
        parts = [
            "=== ROLE ===\n" + self.role_block,
            "=== SESSION COVERAGE AWARENESS ===\n" + ctx,
        ]
        parts.append("=== TASK CONTRACT ===\n" + self.task_block)
        return "\n\n".join(parts)

    # ── Accessors used by other modules (unchanged interface) ──

    def get_category_labels(self) -> dict[str, str]:
        return dict(IEEE830_CATEGORIES)

    def get_mandatory_nfr_categories(self) -> frozenset[str]:
        return MANDATORY_NFR_CATEGORIES

    def get_min_functional_reqs(self) -> int:
        return MIN_FUNCTIONAL_REQS

    def is_srs_generation_permitted(self, state: "ConversationState") -> bool:
        return state.is_ready_for_srs()