"""
prompt_architect.py — Iteration 9
University of Hildesheim

Key changes (IT9):
- TWO task types: ELICITATION (full elicitation + SRS) and SRS_ONLY (existing reqs → SRS)
- PHASED system prompts for ELICITATION: Phase FR → Phase NFR → Phase IEEE
  System switches the active phase-block automatically based on state.
- SRS_ONLY task type gets its own focused system prompt for IEEE section filling.
- Known requirements list is injected into context (tiered summary for large lists).
- Context window kept tight: history reduced to 10 turns max.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from conversation_state import ConversationState

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

PHASE4_SECTIONS: list[tuple[str, str, str, bool]] = [
    ("1.2","Scope","Now that we've covered all requirements, let me confirm the boundaries. What is definitely IN scope and what is OUT of scope?",False),
    ("2.3","User Classes and Characteristics","Who are the different types of people using this system? Is there an admin role vs regular user? How tech-savvy are they?",True),
    ("2.4","Operating Environment","What devices and environments must the system run on? Phones, tablets, computers? Works offline?",True),
    ("2.5","Assumptions and Dependencies","Any external services this relies on — cloud, payment, mapping APIs? Any assumptions that if changed would alter requirements?",True),
    ("3.1.1","User Interfaces","What should the main screens look like at a high level? Dashboard, settings page, history view? Any specific visual/layout requirements?",True),
    ("3.1.3","Software Interfaces","Does it need to connect to external software, APIs, or services? Google login, notification service, third-party platforms?",True),
    ("3.1.4","Communications Interfaces","What communication channels should it support? Emails, push notifications, SMS?",True),
    ("2.1","Product Perspective","Is this a new standalone system or does it replace/extend something existing? Fits into a larger ecosystem?",False),
]

_STATUS_ICONS = {
    "confirmed": "✅",
    "partial":   "🔶",
    "unprobed":  "⬜",
    "excluded":  "❌",
}

TaskType = Literal["elicitation", "srs_only"]
ElicitationPhase = Literal["fr", "nfr", "ieee"]

_COMMS_STYLE = """\
COMMUNICATION STYLE:
- Use PLAIN EVERYDAY LANGUAGE. The stakeholder is not a software engineer.
- NEVER use jargon labels like "Error Detection & Recovery" in questions.
- ONE question per response. Never ask two at once.
- Push for specific numbers on any vague quality/capacity statement.
- NEVER end with "feel free to let me know" while coverage gaps remain open.
"""

_REQ_FORMAT = """\
REQUIREMENT FORMAT (hidden — system parses automatically):
  <REQ type="functional|non_functional|constraint" category="[category]">
  The system shall [verb] [object] [measurable constraint].
  </REQ>
- ONE requirement per tag (atomic).
- Add specific numbers when stakeholder mentions capacity, speed, or frequency.
- Tag vague inferences with source="inferred".

SECTION FORMAT (IEEE phase only):
  <SECTION id="[ieee-section-id]">
  [Formal IEEE-830 prose. Third-person. Minimum 2 sentences.]
  </SECTION>
"""

_ELICITATION_FR_ROLE = """\
You are an expert Requirements Engineer conducting a structured elicitation interview \
following IEEE 830-1998 standards.

YOUR JOB IN THIS PHASE: Elicit FUNCTIONAL REQUIREMENTS ONLY.
Focus on WHAT the system must DO — features, user actions, system behaviours, \
data handling, business rules, error cases.

APPROACH:
1. Extract what the stakeholder explicitly states as formal requirements.
2. INFER what they assumed but did not say — and ask about it.
3. Probe for capacity limits, boundary values, and edge/error cases.
4. Use the FUNCTIONAL DOMAIN COVERAGE table to find uncovered areas.
   Prioritise ⬜ (unprobed) domains. Confirm ❌ domains are truly out of scope.

DO NOT ask about performance, security, reliability or quality attributes in this phase. \
If the stakeholder volunteers NFR info, capture it with <REQ type="non_functional"> \
but stay focused on features.

{comms_style}
{req_format}"""

_ELICITATION_NFR_ROLE = """\
You are an expert Requirements Engineer. Functional requirements elicitation is COMPLETE. \
Your job now is to elicit NON-FUNCTIONAL REQUIREMENTS (quality attributes).

YOUR JOB: Cover every quality category in the table below. \
Each needs at least {min_nfr} measurable requirements.

Quality categories to cover:
- Performance: response times, throughput, concurrency limits
- Usability: learnability, error recovery, accessibility
- Security & Privacy: authentication, authorisation, data encryption, GDPR compliance
- Reliability & Availability: uptime %, MTTR, backup/recovery procedures
- Compatibility & Portability: browsers, OS, devices, APIs
- Maintainability: code standards, logging, monitoring, update mechanisms

Always push for numbers:
  "It should be fast" → "What is the maximum page load time you'd accept — 1s, 2s, 3s?"
  "Needs to be reliable" → "What is the max downtime per month — 1 hour, 30 minutes, near zero?"
  "Should be secure" → "How many failed login attempts before lockout? Session timeout?"

Do NOT re-ask about features. Do NOT ask about IEEE documentation sections yet.

{comms_style}
{req_format}"""

_ELICITATION_IEEE_ROLE = """\
You are an expert Requirements Engineer. Both functional and non-functional requirements \
are now complete. Your job is to fill in remaining IEEE-830 documentation sections.

Say: "Great, I think we've covered all the requirements. I just have a few quick questions \
to complete the specification document."

Ask naturally about each ⬜ section in the IEEE-830 SECTIONS table. \
After each answer, emit a <SECTION id="..."> tag with formal IEEE-830 prose.

Once ALL sections are ✅, say: "We've now covered everything needed. \
Shall I generate the complete Software Requirements Specification document?"

{comms_style}
{req_format}"""

_SRS_ONLY_ROLE = """\
You are an expert Requirements Engineer. The stakeholder has provided a complete list \
of requirements and wants a full IEEE 830-1998 Software Requirements Specification.

YOUR JOB: Fill in the IEEE-830 documentation sections that cannot be derived from the \
requirements list alone (scope, user classes, operating environment, interfaces, etc.).

You have been given the complete requirements list — use it to understand the system. \
Then ask naturally about each ⬜ section in the IEEE-830 SECTIONS table below.

After each answer, emit: <SECTION id="...">formal IEEE-830 prose</SECTION>

Once ALL sections are ✅, say: "We've covered everything needed for the SRS. \
Shall I generate the document now?"

{comms_style}
{req_format}"""


def _build_requirements_summary(state: "ConversationState", phase: ElicitationPhase) -> str:
    reqs = state.requirements
    if not reqs:
        return ""
    MAX_INLINE = 60
    if len(reqs) <= MAX_INLINE:
        lines = ["REQUIREMENTS COLLECTED:"]
        for req in reqs.values():
            tag = "FR" if req.req_type.value == "functional" else \
                  "NFR" if req.req_type.value == "non_functional" else "CON"
            lines.append(f"  [{req.req_id}][{tag}] {req.text[:120]}")
        return "\n".join(lines)
    else:
        from collections import defaultdict
        by_cat: dict[str, list] = defaultdict(list)
        for req in reqs.values():
            by_cat[req.category or "general"].append(req)
        lines = [f"REQUIREMENTS SUMMARY ({len(reqs)} total):"]
        for cat, cat_reqs in sorted(by_cat.items(), key=lambda x: -len(x[1])):
            fr_c = sum(1 for r in cat_reqs if r.req_type.value == "functional")
            nfr_c = sum(1 for r in cat_reqs if r.req_type.value == "non_functional")
            lines.append(f"  {cat}: {len(cat_reqs)} reqs (FR:{fr_c}, NFR:{nfr_c})")
        lines.append(f"  Total: FR={state.functional_count}, NFR={state.nonfunctional_count}")
        return "\n".join(lines)


def _build_context_block(state: "ConversationState", phase: ElicitationPhase) -> str:
    from domain_discovery import NFR_CATEGORIES, DomainGate
    turn_info = (
        f"Turn: {state.turn_count}  |  "
        f"Requirements: {state.total_requirements}  "
        f"(FR: {state.functional_count}, NFR: {state.nonfunctional_count})"
    )
    gate: DomainGate | None = state.domain_gate
    gate_lines = []
    if gate is not None and gate.seeded and gate.total > 0:
        gate_lines.append(
            f"FUNCTIONAL DOMAIN COVERAGE [{gate.done_count}/{gate.total} — {gate.completeness_pct}%]"
        )
        for d in list(gate.domains.values())[:12]:
            icon = _STATUS_ICONS.get(d.status, "⬜")
            gate_lines.append(f"  {icon} {d.label} [{len(d.req_ids)} reqs]")
        if len(gate.domains) > 12:
            gate_lines.append(f"  ... and {len(gate.domains) - 12} more")
    else:
        gate_lines.append("FUNCTIONAL DOMAIN COVERAGE [not yet seeded]")

    nfr_lines = [f"QUALITY REQUIREMENT COVERAGE (target ≥{MIN_NFR_PER_CATEGORY} each):"]
    for ck, cl in NFR_CATEGORIES.items():
        count = state.nfr_coverage.get(ck, 0)
        met = count >= MIN_NFR_PER_CATEGORY
        icon = "✅" if met else ("🔶" if count > 0 else "⬜")
        nfr_lines.append(f"  {icon} {cl} ({count}/{MIN_NFR_PER_CATEGORY})")

    phase4_covered = getattr(state, 'phase4_sections_covered', set())
    p4_lines = [f"IEEE-830 SECTIONS ({len(phase4_covered)}/{len(PHASE4_SECTIONS)}):"]
    for sec_id, label, _, _ in PHASE4_SECTIONS:
        icon = "✅" if sec_id in phase4_covered else "⬜"
        p4_lines.append(f"  {icon} §{sec_id} {label}")

    covered  = state.covered_categories
    ieee_pct = round(len(covered) / len(IEEE830_CATEGORIES) * 100)
    fr_note  = ""
    if phase == "fr" and state.functional_count < MIN_FUNCTIONAL_REQS:
        fr_note = (
            f"\n⚠️  FR TARGET: {state.functional_count}/{MIN_FUNCTIONAL_REQS}. "
            "Keep probing functional areas."
        )

    req_summary = _build_requirements_summary(state, phase)
    parts = [f"SESSION STATE:\n{turn_info}", "\n".join(gate_lines)]
    if phase in ("nfr", "ieee"):
        parts.append("\n".join(nfr_lines))
    if phase == "ieee":
        parts.append("\n".join(p4_lines))
    parts.append(f"IEEE-830 Coverage: {len(covered)}/{len(IEEE830_CATEGORIES)} ({ieee_pct}%){fr_note}")
    if req_summary:
        parts.append(req_summary)
    return "\n\n".join(parts)


def _build_srs_only_context(state: "ConversationState") -> str:
    from domain_discovery import NFR_CATEGORIES
    phase4_covered = getattr(state, 'phase4_sections_covered', set())
    p4_lines = [f"IEEE-830 SECTIONS ({len(phase4_covered)}/{len(PHASE4_SECTIONS)}):"]
    for sec_id, label, _, _ in PHASE4_SECTIONS:
        icon = "✅" if sec_id in phase4_covered else "⬜"
        p4_lines.append(f"  {icon} §{sec_id} {label}")
    nfr_lines = ["NFR COVERAGE:"]
    for ck, cl in NFR_CATEGORIES.items():
        count = state.nfr_coverage.get(ck, 0)
        icon = "✅" if count >= MIN_NFR_PER_CATEGORY else ("🔶" if count > 0 else "⬜")
        nfr_lines.append(f"  {icon} {cl} ({count})")
    req_summary = _build_requirements_summary(state, "ieee")
    parts = [
        f"Turn: {state.turn_count} | Reqs loaded: {state.total_requirements} "
        f"(FR:{state.functional_count}, NFR:{state.nonfunctional_count})",
        "\n".join(p4_lines),
        "\n".join(nfr_lines),
    ]
    if req_summary:
        parts.append(req_summary)
    return "\n\n".join(parts)


def determine_elicitation_phase(state: "ConversationState") -> ElicitationPhase:
    fr_done = state.functional_count >= MIN_FUNCTIONAL_REQS
    gate = state.domain_gate
    domain_ok = (gate is None or not gate.seeded or gate.is_satisfied)
    if not fr_done or not domain_ok:
        return "fr"
    nfr_done = all(
        state.nfr_coverage.get(c, 0) >= MIN_NFR_PER_CATEGORY
        for c in MANDATORY_NFR_CATEGORIES
    )
    if not nfr_done:
        return "nfr"
    return "ieee"


@dataclass
class PromptArchitect:
    task_type: TaskType = "elicitation"
    extra_context: str = field(default="")

    def build_system_message(self, state: "ConversationState") -> str:
        if self.task_type == "srs_only":
            return self._build_srs_only_message(state)
        return self._build_elicitation_message(state)

    def _build_elicitation_message(self, state: "ConversationState") -> str:
        phase = determine_elicitation_phase(state)
        ctx = _build_context_block(state, phase)
        if phase == "fr":
            role = _ELICITATION_FR_ROLE.format(comms_style=_COMMS_STYLE, req_format=_REQ_FORMAT)
            phase_label = "PHASE: FUNCTIONAL REQUIREMENTS ELICITATION"
        elif phase == "nfr":
            role = _ELICITATION_NFR_ROLE.format(min_nfr=MIN_NFR_PER_CATEGORY, comms_style=_COMMS_STYLE, req_format=_REQ_FORMAT)
            phase_label = "PHASE: NON-FUNCTIONAL REQUIREMENTS ELICITATION"
        else:
            role = _ELICITATION_IEEE_ROLE.format(comms_style=_COMMS_STYLE, req_format=_REQ_FORMAT)
            phase_label = "PHASE: IEEE-830 DOCUMENTATION SECTIONS"
        parts = [
            f"=== ROLE ===\n{role}",
            f"=== CURRENT {phase_label} ===",
            f"=== SESSION COVERAGE AWARENESS ===\n{ctx}",
        ]
        if self.extra_context:
            parts.append(f"=== ADDITIONAL CONTEXT ===\n{self.extra_context}")
        return "\n\n".join(parts)

    def _build_srs_only_message(self, state: "ConversationState") -> str:
        role = _SRS_ONLY_ROLE.format(comms_style=_COMMS_STYLE, req_format=_REQ_FORMAT)
        ctx = _build_srs_only_context(state)
        return "\n\n".join([
            "=== ROLE ===\n" + role,
            "=== TASK: SRS FROM EXISTING REQUIREMENTS ===",
            "=== SESSION STATE ===\n" + ctx,
        ])

    def get_category_labels(self) -> dict[str, str]:
        return dict(IEEE830_CATEGORIES)

    def get_mandatory_nfr_categories(self) -> frozenset[str]:
        return MANDATORY_NFR_CATEGORIES

    def get_min_functional_reqs(self) -> int:
        return MIN_FUNCTIONAL_REQS

    def is_srs_generation_permitted(self, state: "ConversationState") -> bool:
        return state.is_ready_for_srs()

    def get_current_phase(self, state: "ConversationState") -> ElicitationPhase:
        if self.task_type == "srs_only":
            return "ieee"
        return determine_elicitation_phase(state)