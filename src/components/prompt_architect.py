"""
src/components/prompt_architect.py — Iteration 6
University of Hildesheim

IT8-VOLERE      Volere removed. IEEE-830 only throughout.
IT8-NFR-DEPTH   MIN_NFR_PER_CATEGORY = 2. Phase 3 hard stop now shows per-category
                count vs threshold and demands measurable follow-up until 2 reached.
IT8-PHASE4      PHASE4_SECTIONS defined. _build_context_block() emits Phase 4
                hard stop after NFRs complete, covering narrative sections one by one.
                TASK_BLOCK updated with <SECTION> tag format rule.
IT8-SRS-GATE    SRS offer only after Phase 4 complete (all sections covered).
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
# IT8: Minimum requirements per NFR sub-category (was 1, now 2 for depth)
MIN_NFR_PER_CATEGORY = 2

# IT8-PHASE4: Ordered list of IEEE-830 narrative sections to complete after elicitation.
# Each entry: (section_id, label, probe_question, can_ask_followup)
# section_id matches IEEE-830 numbering and is used as the <SECTION id="..."> key.
# can_ask_followup=True means the RE may ask a clarifying question if the answer is vague.
PHASE4_SECTIONS: list[tuple[str, str, str, bool]] = [
    (
        "1.2",
        "Scope",
        "Now that we've covered all the requirements, let me confirm the boundaries "
        "of the system. What is definitely IN scope — the main things it should do — "
        "and is there anything you'd consider OUT of scope, meaning things you do NOT "
        "want this system to handle, at least not now?",
        False,
    ),
    (
        "2.3",
        "User Classes and Characteristics",
        "Who are the different types of people who will use this system? "
        "For example, is there an administrator with more access than a regular user, "
        "or will different people use different parts of it? "
        "And roughly how tech-savvy are they?",
        True,
    ),
    (
        "2.4",
        "Operating Environment",
        "What devices and environments will the system need to run on? "
        "For example, should it work on phones, tablets, computers, or all of them? "
        "Does it need to work when there's no internet connection?",
        True,
    ),
    (
        "2.5",
        "Assumptions and Dependencies",
        "Are there any external services, tools, or systems this needs to rely on — "
        "like a cloud provider, a payment service, or a mapping API? "
        "And are there any assumptions we've been making that, if they changed, "
        "would change what the system needs to do?",
        True,
    ),
    (
        "3.1.1",
        "User Interfaces",
        "What should the main screens or views of the system look like at a high level? "
        "For example, is there a dashboard, a settings page, a history view? "
        "Are there any specific visual or layout requirements you have in mind?",
        True,
    ),
    (
        "3.1.3",
        "Software Interfaces",
        "Does the system need to connect to or integrate with any external software, "
        "APIs, or services? For example, a login provider like Google, a notification "
        "service, a database, or any third-party platform?",
        True,
    ),
    (
        "3.1.4",
        "Communications Interfaces",
        "What communication channels should the system support? "
        "For example, does it send emails, push notifications, or SMS messages? "
        "Does it use a specific network protocol, or does it need to work over "
        "a local network as well as the internet?",
        True,
    ),
    (
        "2.1",
        "Product Perspective",
        "Is this a completely new standalone system, or does it replace or extend "
        "something that already exists? And does it need to fit into a larger "
        "ecosystem — for example, does it connect to other apps or platforms "
        "you or your organisation already use?",
        False,
    ),
]

ROLE_BLOCK = """\
You are an expert Requirements Engineer conducting a structured elicitation \
interview. You follow IEEE 830-1998 standards.

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

BANNED PHRASES — NEVER use any of the following:
- "If you have any other questions, feel free to let me know"
- "Thank you for sharing that"
- "Is there anything else you'd like to discuss?"
- "Feel free to reach out"
- "That covers it"
- "We're done" / "I think that's everything"
- Any variation of "if you need anything else"
These are session-closing phrases. Using them when a ⛔ HARD STOP is active \
is a critical failure. Even when the customer says "I think that covers it", \
you must NOT agree — you must ask the next required question.

Do not let the user close the interview until ALL gates are fully satisfied \
AND Phase 4 documentation sections are complete.\
"""

TASK_BLOCK = """
═══════════════════════════════════════════════════════════
YOUR PRIMARY INSTRUCTION — READ THIS FIRST, OBEY IT ALWAYS
═══════════════════════════════════════════════════════════

Step 1. Read the ⛔ HARD STOP or ✅ message in the Session Context above.
Step 2. Your ENTIRE visible response (everything the customer reads) must
        follow ONE of these two templates:

  IF ⛔ HARD STOP is active:
    [Any <REQ> or <SECTION> tags — these are hidden from the customer]
    [ONE sentence acknowledging what they said — max 10 words, no praise]
    [ONE question ending in '?']
    ← That is the complete response. Nothing else. No "thank you". No offers.
       No "if you have any questions". No summaries. No SRS offer.

  IF ✅ ALL GATES SATISFIED:
    [Any <REQ> or <SECTION> tags]
    [Offer to generate the SRS document]

CRITICAL: Emitting a <REQ> tag does NOT end your obligation to ask the next
question. After every <REQ> tag, if a ⛔ HARD STOP is still active, you MUST
ask the next required question. The <REQ> tag is invisible to the customer —
your visible response still needs to contain exactly one question.

EXAMPLE of correct behaviour when ⛔ HARD STOP is active:
  <REQ type="non_functional" category="reliability">
  The system shall remain available 99.5% of the time.
  </REQ>
  Good to know. What devices — phone, tablet, or computer — do you use most?

EXAMPLE of WRONG behaviour (DO NOT DO THIS):
  <REQ type="functional" category="scheduling">
  The system shall allow timer scheduling.
  </REQ>
  Thank you for sharing that! If you have any other questions, feel free
  to let me know.  ← THIS IS A CRITICAL FAILURE

═══════════════════════════════════════════════════════════
PHASE STRUCTURE
═══════════════════════════════════════════════════════════

PHASE 1 (turns 1-2): Listen. Build context. No requirements yet.

PHASE 2 (turns 3+): Work through every domain in the gate.
  For each domain:
  1. Ask an open-ended question using PLAIN LANGUAGE and a CONCRETE EXAMPLE.
  2. Extract <REQ> tags from their answer.
  3. Ask ONE deeper follow-up targeting what they missed
     (numbers, ranges, capacities, what-if scenarios).
  4. Move on to the next domain.

PHASE 3: After domain gate satisfied, ask about EACH NFR category until
  EACH category has at least {min_nfr} measurable requirements.
  This phase is MANDATORY — you cannot skip it or offer SRS until done.
  For each NFR category that is below the threshold:
  - First turn: ask the opening probe question in plain language.
  - If count is still below threshold after first answer: ask a targeted
    follow-up demanding a SPECIFIC NUMBER, RANGE, or TIME VALUE.
    e.g. "You said it should be fast — what's the maximum time in seconds
    that would still feel acceptable for loading a page?"
  Use these plain-language probes:
  - Performance: "How quickly should things respond when you tap a button?"
  - Usability: "Your kids and mother-in-law will use this too — what would
    make it easy enough for the least technical person?"
  - Security: "How should people log in, and should anyone be locked out
    of certain features?"
  - Reliability: "How dependable does this need to be — like, is it okay
    if it goes down for a few minutes sometimes?"
  - Compatibility: "What phones or devices does everyone in the family use?"
  - Maintainability: "Who keeps everything running and handles updates?"

PHASE 4: After all NFRs are covered at depth, complete IEEE-830 narrative
  sections. This is the documentation phase — you still have the customer!
  Transition message (say this ONCE at the start of Phase 4):
  "Great, I have all the requirements I need! I just have a few quick
   documentation questions to make sure the specification is complete."
  Then for each uncovered section, ask the probe question from the context.
  IMPORTANT — after the customer answers each Phase 4 question:
  1. Emit a <SECTION id="X.Y"> tag with the section content written in
     formal IEEE-830 prose, synthesised from their answer.
  2. If the answer is vague and can_ask_followup is True for this section,
     ask ONE clarifying follow-up question before emitting the section tag.
  3. Move on to the next uncovered section.
  4. After ALL sections are covered, offer SRS generation.

═══════════════════════════════════════════════════════════
NON-NEGOTIABLE RULES
═══════════════════════════════════════════════════════════

RULE 1 — ONE QUESTION PER RESPONSE, ALWAYS. No exceptions.
RULE 2 — ATOMIC REQUIREMENTS: one per <REQ> tag.
RULE 3 — ALWAYS ADD NUMBERS when extracting capacity/range/timing reqs.
RULE 4 — NO JARGON: never put technical terms or domain labels in questions.
         Always rephrase with a concrete example.
RULE 5 — NO EARLY CLOSURE: if ⛔ HARD STOP, ignore user's "I think that's it"
         or "I think we're done". Ask the next required question immediately.
RULE 6 — REQUIREMENT FORMAT:
  <REQ type="functional|non_functional|constraint" category="[category]">
  The system shall [verb] [object] [measurable constraint].
  </REQ>
RULE 7 — SCOPE REDUCTIONS: confirm if out of scope permanently or for now.
         Do NOT treat excluding ONE feature as excluding the ENTIRE domain.
RULE 8 — INFER TYPICAL REQUIREMENTS: if stakeholder's answer is vague,
         extract what a system of this type would typically need.
RULE 9 — SECTION FORMAT (Phase 4 only):
  <SECTION id="[ieee-section-id]">
  [Formal IEEE-830 prose synthesised from the customer's answer.
   Write in third-person. Use "The system shall" for requirements,
   "It is assumed that" for assumptions. Minimum 2 sentences.]
  </SECTION>
  The section ID must match the IEEE-830 section number exactly,
  e.g. "1.2", "2.3", "3.1.1".
RULE 10 — NFR DEPTH: each NFR category needs {min_nfr} requirements with
          specific measurable values. A vague statement like "it should be
          reliable" does NOT count as a measurable requirement.
RULE 11 — BANNED CLOSING PHRASES: Never end a response with "feel free to
          let me know", "if you have any questions", "thank you for sharing",
          or any session-closing phrase while a ⛔ HARD STOP is active.
          The ONLY valid ending while ⛔ HARD STOP is active is a question.
""".format(min_nfr=MIN_NFR_PER_CATEGORY)

_STATUS_ICONS = {"confirmed":"✅","partial":"🔶","unprobed":"⬜","excluded":"❌"}

def _build_context_block(state: "ConversationState") -> str:
    from domain_discovery import NFR_CATEGORIES, DomainGate

    turn_info = (f"Turn: {state.turn_count}  |  "
                 f"Requirements: {state.total_requirements}  "
                 f"(FR: {state.functional_count}, NFR: {state.nonfunctional_count})")

    gate: DomainGate | None = state.domain_gate
    gate_satisfied = gate is not None and gate.is_satisfied
    gate_seeded = gate is not None and gate.seeded

    # IT8: NFR missing = any category below MIN_NFR_PER_CATEGORY
    nfr_below_threshold = [
        cat for cat in NFR_CATEGORIES
        if state.nfr_coverage.get(cat, 0) < MIN_NFR_PER_CATEGORY
    ]

    _NFR_PROBES = {
        "performance":"How quickly should things respond when you tap a button — what would feel too slow?",
        "usability":"Who is the least technical person using this, and what would make it simple enough for them?",
        "security_privacy":"How should people log in, and should certain features be restricted from some users?",
        "reliability":"How dependable does this need to be — is it okay if it goes down briefly, or must it always work?",
        "compatibility":"What phones, tablets, or computers does everyone in the family use?",
        "maintainability":"Who keeps the system running after it's set up — should it update itself, or does someone manage it?",
    }

    _NFR_DEPTH_PROBES = {
        "performance": "You've mentioned performance — but what's the maximum number of seconds that would still feel acceptable for the slowest operation? Give me a specific number.",
        "usability": "You've described usability needs — but can you give me a specific example of something that would be too complicated for your least technical user?",
        "security_privacy": "You've covered security — but how many failed login attempts should be allowed before locking someone out? And how long should a session stay active?",
        "reliability": "You've mentioned reliability — but what is the maximum acceptable downtime per month in hours or minutes? And how quickly should the system recover after a failure?",
        "compatibility": "You've listed devices — but which specific operating system versions must be supported as a minimum? For example, iOS 14+, Android 10+?",
        "maintainability": "You've described maintenance needs — but how quickly should a developer be able to deploy a bug fix? And should the system support rollbacks if an update fails?",
    }

    # Appended to every ⛔ HARD STOP — reinforces the no-closing-phrase rule on every turn
    _HARD_STOP_FOOTER = (
        "\nREMINDER: After any <REQ> tag, your visible response MUST end with a "
        "question mark. NEVER end with 'feel free to let me know' or any closing phrase."
    )

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
                f"Do NOT summarize. Do NOT offer SRS. ONE question only."
                f"{_HARD_STOP_FOOTER}")
        else:
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
                    f"Do NOT summarize. Do NOT offer SRS. ONE question only."
                    f"{_HARD_STOP_FOOTER}")
            else:
                hard_stop = (
                    f"⛔ HARD STOP — DOMAIN GATE [{done}/{total}] INCOMPLETE\n"
                    f"Do NOT close the session. Ask about any uncovered features.\n"
                    f"ONE question only."
                    f"{_HARD_STOP_FOOTER}")

    elif nfr_below_threshold and state.functional_count >= MIN_FUNCTIONAL_REQS:
        # IT8-PHASE3: mandatory NFR phase with depth enforcement
        next_nfr = nfr_below_threshold[0]
        current_count = state.nfr_coverage.get(next_nfr, 0)
        label = NFR_CATEGORIES.get(next_nfr, next_nfr)

        if current_count == 0:
            # First probe — opening question
            probe = _NFR_PROBES.get(next_nfr, f"Tell me about your {next_nfr} needs.")
            hard_stop = (
                f"⛔ HARD STOP — NFR PHASE 3: {label} [{current_count}/{MIN_NFR_PER_CATEGORY}]\n"
                f"Domain gate satisfied. Ask about this quality requirement.\n"
                f"Use plain language: \"{probe}\"\n"
                f"Ask for SPECIFIC MEASURABLE values. Do NOT offer SRS yet."
                f"{_HARD_STOP_FOOTER}")
        else:
            # Has some coverage but below threshold — demand measurable depth
            depth_probe = _NFR_DEPTH_PROBES.get(next_nfr,
                f"You've mentioned {label.lower()} needs — but can you give me specific numbers or limits?")
            hard_stop = (
                f"⛔ HARD STOP — NFR DEPTH REQUIRED: {label} [{current_count}/{MIN_NFR_PER_CATEGORY}]\n"
                f"You have {current_count} requirement(s) but need {MIN_NFR_PER_CATEGORY}.\n"
                f"Ask for a MEASURABLE follow-up: \"{depth_probe}\"\n"
                f"Do NOT accept vague answers. Push for specific numbers/ranges. Do NOT offer SRS yet."
                f"{_HARD_STOP_FOOTER}")

    elif len(getattr(state, 'phase4_sections_covered', set())) < len(PHASE4_SECTIONS):
        # IT8-PHASE4: all NFRs covered at depth — now complete narrative sections
        phase4_covered = getattr(state, 'phase4_sections_covered', set())
        next_section = None
        for sec_id, label, probe_q, can_followup in PHASE4_SECTIONS:
            if sec_id not in phase4_covered:
                next_section = (sec_id, label, probe_q, can_followup)
                break

        done_p4 = len(phase4_covered)
        total_p4 = len(PHASE4_SECTIONS)

        if next_section:
            sec_id, label, probe_q, can_followup = next_section
            followup_note = (
                "If the answer is vague, ask ONE clarifying follow-up before emitting the <SECTION> tag."
                if can_followup else
                "Synthesise directly from their answer into the <SECTION> tag, no follow-up needed."
            )
            transition = ""
            if done_p4 == 0:
                transition = (
                    "TRANSITION (say this first, ONCE): "
                    "\"Great, I have all the requirements I need! I just have a few quick "
                    "documentation questions to make sure the specification is complete.\"\n"
                )
            hard_stop = (
                f"⛔ HARD STOP — IEEE-830 DOCUMENTATION PHASE 4 [{done_p4}/{total_p4}]\n"
                f"{transition}"
                f"NEXT SECTION: §{sec_id} {label}\n"
                f"Ask: \"{probe_q}\"\n"
                f"{followup_note}\n"
                f"After capturing answer: emit <SECTION id=\"{sec_id}\">...</SECTION> "
                f"with formal IEEE-830 prose synthesised from the customer's answer.\n"
                f"Do NOT offer SRS yet."
                f"{_HARD_STOP_FOOTER}")
        else:
            hard_stop = (
                f"⛔ HARD STOP — PHASE 4 ALMOST COMPLETE [{done_p4}/{total_p4}]\n"
                f"Cover any remaining uncovered sections, then offer SRS."
                f"{_HARD_STOP_FOOTER}")

    else:
        done = gate.done_count if gate else 0
        total = gate.total if gate else 0
        p4_done = len(getattr(state, 'phase4_sections_covered', set()))
        p4_total = len(PHASE4_SECTIONS)
        hard_stop = (
            f"✅ ALL GATES SATISFIED [{done}/{total} domains | all NFRs at depth | "
            f"Phase 4 {p4_done}/{p4_total} sections]\n"
            f"Offer SRS generation now.")

    # Domain gate table
    gate_lines = []
    if gate_seeded and gate:
        gate_lines.append(f"DOMAIN GATE [{gate.done_count}/{gate.total} — {gate.completeness_pct}%]")
        for d in gate.domains.values():
            icon = _STATUS_ICONS.get(d.status, "⬜")
            gate_lines.append(f"  {icon} {d.label} [{len(d.req_ids)} reqs]")
    else:
        gate_lines.append("DOMAIN GATE [not yet seeded]")

    # IT8: NFR coverage with depth indicator (count / MIN_NFR_PER_CATEGORY)
    nfr_lines = [f"NFR COVERAGE (need {MIN_NFR_PER_CATEGORY} per category):"]
    for ck, cl in NFR_CATEGORIES.items():
        count = state.nfr_coverage.get(ck, 0)
        met = count >= MIN_NFR_PER_CATEGORY
        icon = "✅" if met else ("🔶" if count > 0 else "⬜")
        nfr_lines.append(f"  {icon} {cl} ({count}/{MIN_NFR_PER_CATEGORY})")

    # IT8: Phase 4 section progress — defensive getattr for backward compat
    phase4_covered = getattr(state, 'phase4_sections_covered', set())
    p4_lines = [f"PHASE 4 SECTIONS ({len(phase4_covered)}/{len(PHASE4_SECTIONS)}):"]
    for sec_id, label, _, _ in PHASE4_SECTIONS:
        icon = "✅" if sec_id in phase4_covered else "⬜"
        p4_lines.append(f"  {icon} §{sec_id} {label}")

    covered = state.covered_categories
    ieee_pct = round(len(covered)/len(IEEE830_CATEGORIES)*100)

    fr_alert = ""
    if state.functional_count < MIN_FUNCTIONAL_REQS:
        fr_alert = f"\n⚠️ FR DEFICIT: {state.functional_count} FRs, need ≥{MIN_FUNCTIONAL_REQS}\n"

    return (f"SESSION STATE:\n{turn_info}\n\n"
            f"{hard_stop}\n\n"
            f"{chr(10).join(gate_lines)}\n\n"
            f"{chr(10).join(nfr_lines)}\n\n"
            f"{chr(10).join(p4_lines)}\n\n"
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