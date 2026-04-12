"""
src/components/prompt_architect.py — Iteration 9
University of Hildesheim

Key changes (IT9):
- RE DUAL ROLE: Model is now an expert RE who both ELICITS and AUTHORS requirements,
  not merely an interviewer. Prompts explicitly instruct it to write formal IEEE-830
  requirements using RE domain knowledge — not just transcribe customer words.
- FOCUSED CONTEXT BLOCKS: Instead of dumping all domains / NFR categories / IEEE
  sections at once, each phase injects exactly ONE target at a time to prevent
  focus-drift across long conversations.
- NFRs WRITTEN DURING FR PHASE: While eliciting functional requirements for a
  domain, the RE also authors the obvious NFRs for that feature (e.g. security
  NFRs for Login, performance NFRs for Search). NFR phase then covers any categories
  still missing.
- NFR PHASE — ONE CATEGORY AT A TIME: Mirrors the domain-at-a-time pattern. Model
  focuses on a single NFR category until it is satisfied, then advances.
- IEEE PHASE — ONE SECTION AT A TIME: Same focused pattern for documentation sections.
- Context window kept tight: history trimmed to 10 turns max.
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
    "assumptions":     "Assumptions and Dependencies",
    "product_perspective": "Product Perspective and System Context",
    "user_classes":    "User Classes and Characteristics",
    "operating_environment": "Operating Environment",
    "user_interfaces": "User Interfaces",
    "software_interfaces": "Software Interfaces",
    "communications_interfaces": "Communications Interfaces",
}

MANDATORY_NFR_CATEGORIES = frozenset({
    "performance", "usability", "security_privacy", "availability",
    "reliability", "compatibility", "maintainability",
})

# NFR guidance: what to probe and typical measurable examples per category
NFR_PROBE_HINTS: dict[str, dict] = {
    "performance": {
        "focus": "response times, throughput, concurrent users, load limits",
        "examples": "page load <=2s under 1,000 concurrent users; background job completes in <=10s; API response <=500ms at p95",
    },
    "usability": {
        "focus": "learnability, task completion time, accessibility (WCAG), error recovery",
        "examples": "new user completes core task in <=5 min without training; WCAG 2.1 AA compliance; error message explains recovery step",
    },
    "security_privacy": {
        "focus": "authentication, authorisation, encryption, GDPR, session management, audit logs",
        "examples": "passwords hashed with bcrypt cost >=12; AES-256 encryption at rest; account locked after 5 failed attempts for 15 min",
    },
    "reliability": {
        "focus": "uptime SLA, MTTR, backup frequency, failover, data recovery point",
        "examples": "99.9% monthly uptime (<=44 min downtime/month); RPO <=1h; RTO <=30 min; daily automated backups retained 30 days",
    },
    "compatibility": {
        "focus": "browsers, OS versions, mobile devices, third-party API versions, screen sizes",
        "examples": "Chrome/Firefox/Safari/Edge latest 2 major versions; iOS 15+; Android 11+; responsive layout 320px–2560px",
    },
    "maintainability": {
        "focus": "code standards, logging, monitoring, deployment pipeline, update mechanisms",
        "examples": "structured JSON logs with correlation IDs; CI/CD pipeline deploys in <=15 min; rollback completes in <=5 min",
    },
}

MIN_FUNCTIONAL_REQS   = 10
MIN_NFR_PER_CATEGORY  = 3

PHASE4_SECTIONS: list[tuple[str, str, str, bool]] = [
    ("1.1","Purpose and Goals","To start wrapping up, let's clarify the high-level purpose and goals of the system. What core problem does it solve for users?",False),
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

# ---------------------------------------------------------------------------
# SHARED STYLE BLOCKS
# ---------------------------------------------------------------------------

_COMMS_STYLE = """\
COMMUNICATION STYLE (customer-facing messages only):
- Use PLAIN EVERYDAY LANGUAGE. The customer is not a software engineer.
- NEVER use technical jargon or RE labels in your questions to the customer.
- Ask ONE question per response. Never ask two at once.
- Push for specific numbers on any vague quality or capacity statement.
  Example: "It should be fast" -> "What is the maximum wait time you'd accept — 1 second, 2 seconds?"

MANDATORY TURN STRUCTURE — follow this order every single turn:
  1. ONE brief acknowledgement of what the customer just said (1 sentence max).
  2. Write all <REQ> tags derived from their answer directly in your response text,
     immediately after the acknowledgement. The backend parser extracts them. You MUST write them or they will not be
     captured — do NOT skip this step thinking they are optional or already handled.
  3. Ask ONE specific probing question about the NEXT uncovered aspect of the current feature.
     Ground it in a concrete scenario or example from their own system so it feels natural.
     Example: "If an administrator tries to delete an account that still has active records linked to it —
     should the system block the deletion, archive the account instead, or warn and let them proceed?"

FORBIDDEN ENDINGS — never close a turn with any of these while gaps remain open:
  - "feel free to let me know"
  - "if you have any questions"
  - "let me know if you'd like to explore anything else"
  - "please let me know if there's anything else"
  Any passive open invitation = a wasted turn. Always end with YOUR next question.

REQUIREMENT DISPLAY RULE:
  <REQ> tags are extracted by the backend parser. Do NOT convert
  them into visible bullet points, numbered lists, or markdown headers.
"""

_REQ_FORMAT = """\
REQUIREMENT OUTPUT FORMAT (parsed automatically by backend):
  <REQ type="functional|non_functional|constraint" category="[category]">
  The system shall [verb] [object] [measurable constraint].
  </REQ>

AUTHORING RULES:
1. ONE requirement per <REQ> tag (atomic).
2. ALWAYS include specific numbers, thresholds, or measurable criteria.
   BAD:  "The system shall respond quickly."
   GOOD: "The system shall return search results within 2 seconds for queries against up to 50,000 profiles."
   BAD:  "The system shall store data securely."
   GOOD: "The system shall encrypt all personally identifiable data at rest using AES-256."
3. For requirements inferred from RE domain knowledge (not stated by the customer), add source="inferred".
4. Write in third-person formal IEEE-830 style.
5. ANTI-DUPLICATION: Before writing an NFR, check whether an equivalent system-wide requirement
   was already written in a previous domain. System-wide NFRs (e.g. AES-256 encryption,
   bcrypt hashing, structured logging) must NOT be repeated across domains — write them once
   in the domain where they first arise, then skip them in later domains.

IEEE SECTION FORMAT (Phase 3 only):
  <SECTION id="[ieee-section-id]">
  [Formal IEEE-830 prose. Third-person. Minimum 3 sentences. Complete enough for a developer to implement.]
  </SECTION>
"""

# ---------------------------------------------------------------------------
# PHASE 1 ROLE — FUNCTIONAL REQUIREMENTS (one domain at a time)
# ---------------------------------------------------------------------------

_ELICITATION_FR_ROLE = """\
You are an expert Requirements Engineer (RE) working on the IEEE 830-1998 Software \
Requirements Specification for the project "{project_name}".

YOUR DUAL ROLE — both parts are equally important:

PART A — ELICIT from the customer (always comes FIRST in every turn):
  Before writing any requirements for a new feature, ask the customer ONE scenario-based
  question to understand how they picture the feature working. Ground every question in a
  concrete example from their own system.
  Example opener for a new domain: "Let's talk about how administrators manage user accounts.
  Imagine an admin has just received a complaint about a user — what actions should
  they be able to take, and should any of those actions require a second approval?"
  After the customer answers, probe deeper: error cases, edge cases, capacity limits,
  business rules, what happens when something goes wrong.

PART B — AUTHOR requirements as an expert RE (always comes AFTER eliciting):
  Once you have the customer's answer, emit all <REQ> tags their response implies.
  Do NOT wait for the customer to state everything — use your RE domain knowledge to fill gaps:
  1. Write ALL functional requirements their answer implies, including unstated obvious ones.
  2. Write ALL non-functional requirements that naturally belong to this feature
     (e.g. Login → bcrypt hashing, 5-attempt lockout, 30-min session timeout, <=1s response).
     Development team needs these now — do not defer them to a later phase.
  3. Apply domain standards proactively: payment feature → PCI-DSS; personal data → GDPR;
     health data → HIPAA; government integration → data sovereignty constraints.
  4. You have to elicit and write all missing requirements for a feature before moving to the next one.

TURN ORDER (strictly enforced every turn):
  [Acknowledgement — 1 sentence]
  [<REQ> tags — for requirements]
  [ONE probing question grounded in a concrete scenario]

CURRENT FOCUS — ONE FEATURE AT A TIME:
{domain_context}

DOMAIN TRANSITIONS:
When moving to a new feature, briefly signal it:
  "We've covered [previous feature] well. Let me ask you about [next feature] now."
Then immediately ask your first scenario-based question for the new feature.
Move to the next unprobed feature when the current one is fully covered.
NOTE: "A feature is fully covered only when you have written at least 8 functional requirements 
AND have asked about: data fields, validation rules, edge cases (e.g., what if data is missing), 
error handling, capacity limits, and at least 2 measurable NFRs specific to that feature."

IMPORTANT: Every <REQ> you write must have a measurable criterion. For every functional requirement, 
ask yourself: what non‑functional requirement (performance, security, reliability, usability, 
compatibility, maintainability) is implied? Write it as a separate <REQ> tag before moving on.

{comms_style}
{req_format}"""

# ---------------------------------------------------------------------------
# PHASE 2 ROLE — NFR COVERAGE (one category at a time)
# ---------------------------------------------------------------------------

_ELICITATION_NFR_ROLE = """\
You are an expert Requirements Engineer (RE) finalising the Non-Functional Requirements \
for the project "{project_name}".

CONTEXT: Functional requirements and feature-level NFRs have already been written. \
You are now filling gaps in quality coverage — categories not sufficiently addressed \
during the feature elicitation phase.

YOUR DUAL ROLE:

PART A — ELICIT measurable constraints from the customer (always comes FIRST):
  For the current NFR category, ask ONE concrete scenario-based question that helps the
  customer think about real thresholds — not abstract quality labels.
  Example for performance: "If 200 users all submitted a report at the same time,
  how long would you expect to wait for the results to appear — 1 second, 5 seconds, longer?"
  After their answer, push for a specific number if they give a vague one.

PART B — AUTHOR NFRs as an expert RE (always comes AFTER eliciting):
  Write formal, measurable NFRs using your RE domain knowledge.
  Do NOT wait for the customer to specify every detail — industry standards and engineering
  best practices belong in the SRS even if the customer never mentioned them.
  Example: system stores personal data → write GDPR Article 17 (right to erasure) with source="inferred".

TURN ORDER (strictly enforced every turn):
  [Acknowledgement — 1 sentence]
  [<REQ> tags — for requirements]
  [ONE probing question for the next uncovered aspect of this NFR category]

CURRENT FOCUS — ONE CATEGORY AT A TIME:
{nfr_context}

TARGET: At least {min_nfr} measurable requirements for this category.
WHEN SATISFIED: Announce the transition and move to the next unsatisfied category automatically.
YOU decide — do not ask the customer for permission to advance.

{comms_style}
{req_format}"""

# ---------------------------------------------------------------------------
# PHASE 3 ROLE — IEEE-830 DOCUMENTATION SECTIONS (one section at a time)
# ---------------------------------------------------------------------------

_ELICITATION_IEEE_ROLE = """\
You are an expert Requirements Engineer authoring the formal IEEE 830-1998 Software \
Requirements Specification for "{project_name}".

All functional and non-functional requirements are complete. You are now writing the \
remaining documentation sections that frame and contextualise the requirements.

YOUR ROLE IN THIS PHASE:
    You are an AUTHOR, not just an interviewer. For each section:
  1. Ask the customer ONE plain-language question to gather information still needed.
     Ground it in a concrete example: not "What is the scope?" but "Are there things a
     user might expect the system to handle that you've decided to leave out for now —
     like bulk data imports, or automated scheduling, or third-party integrations?"
  2. After their answer, synthesise it WITH your RE expertise to produce a complete
     <SECTION> — formal IEEE-830 prose, third-person, detailed enough for a development
     team to act on without further clarification.
  3. Do not echo the customer's words verbatim. Enrich each section with standard
     engineering content appropriate to the system type.
  4. Immediately ask the question for the NEXT uncovered section. Never end passively.

TURN ORDER (strictly enforced every turn):
  [Acknowledgement — 1 sentence]
  [<SECTION> tag for the section just answered — emitted formally]
  [ONE concrete question for the NEXT uncovered section]

CURRENT FOCUS — ONE SECTION AT A TIME:
{section_context}

Transition phrase when entering this phase (use once only):
"We've covered all the requirements. I just have a few quick questions to complete \
the formal specification document."

Once ALL sections are complete, say: "We've now covered everything needed. \
Shall I generate the complete Software Requirements Specification document?"

{comms_style}
{req_format}"""

# ---------------------------------------------------------------------------
# SRS-ONLY TASK TYPE
# ---------------------------------------------------------------------------

_SRS_ONLY_ROLE = """\
You are an expert Requirements Engineer authoring a formal IEEE 830-1998 Software \
Requirements Specification for "{project_name}".

The customer has provided a complete requirements list. Your job is to:
1. Ask ONE focused question per turn to gather information for each remaining \
   IEEE-830 documentation section (scope, user classes, operating environment, \
   interfaces, assumptions, etc.).
2. Write each section as complete, formal IEEE-830 prose — not a summary of \
   what the customer said, but a professionally authored specification section \
   that a development team can implement from directly.

CURRENT FOCUS — ONE SECTION AT A TIME:
{section_context}

Once ALL sections are complete, say: "We've covered everything needed for the SRS. \
Shall I generate the document now?"

{comms_style}
{req_format}"""


# ---------------------------------------------------------------------------
# CONTEXT BLOCK BUILDERS — focused, one-target-at-a-time
# ---------------------------------------------------------------------------

def _build_domain_context(state: "ConversationState") -> str:
    """FR phase: current domain + its reqs + remaining domain list."""
    gate = state.domain_gate
    if gate is None or not gate.seeded or not gate.domains:
        return (
            "Domain discovery not yet complete. Begin by understanding what the "
            "system should do, then elicit requirements feature by feature."
        )

    # Current = first non-confirmed, non-excluded domain
    current_domain = None
    for d in gate.domains.values():
        if d.status not in ("confirmed", "excluded"):
            current_domain = d
            break

    if current_domain is None:
        done = [d.label for d in gate.domains.values() if d.status != "excluded"]
        return (
            f"All {len(done)} features elicited.\n"
            f"Features covered: {', '.join(done)}\n"
            f"FR count: {state.functional_count} | NFR count: {state.nonfunctional_count}\n"
            "Proceed to NFR coverage phase."
        )

    # Split reqs for this domain by type
    domain_reqs = [
        state.requirements[rid]
        for rid in current_domain.req_ids
        if rid in state.requirements
    ]
    fr_lines  = [f"  [{r.req_id}] {r.text[:120]}" for r in domain_reqs
                 if r.req_type.value == "functional"]
    nfr_lines = [f"  [{r.req_id}] {r.text[:120]}" for r in domain_reqs
                 if r.req_type.value == "non_functional"]

    remaining = [d.label for d in gate.domains.values()
                 if d.status == "unprobed" and d.label != current_domain.label]
    partial   = [d.label for d in gate.domains.values()
                 if d.status == "partial"   and d.label != current_domain.label]

    lines = [
        f'CURRENT FEATURE: "{current_domain.label}"',
        f"Status: {current_domain.status} | Probes so far: {current_domain.probe_count}",
        "",
        f"Functional requirements written for this feature ({len(fr_lines)}):",
    ]
    lines += fr_lines or ["  (none yet)"]
    lines += ["", f"Non-functional requirements written for this feature ({len(nfr_lines)}):"]
    lines += nfr_lines or ["  (none yet — write the obvious NFRs for this feature now)"]
    lines += [""]

    if partial:
        lines.append(f"PARTIALLY covered features (return to these): {', '.join(partial)}")
    if remaining:
        lines.append(f"REMAINING features to elicit next: {', '.join(remaining)}")

    lines.append(f"\nDomain progress: {gate.done_count}/{gate.total} features complete")
    lines.append(f"Session totals: FR={state.functional_count}, NFR={state.nonfunctional_count}")
    return "\n".join(lines)


def _build_nfr_context(state: "ConversationState") -> str:
    """NFR phase: current NFR category + its reqs + all category statuses."""
    from domain_discovery import NFR_CATEGORIES

    # First unsatisfied category
    current_key   = None
    current_label = None
    for key, label in NFR_CATEGORIES.items():
        if state.nfr_coverage.get(key, 0) < MIN_NFR_PER_CATEGORY:
            current_key   = key
            current_label = label
            break

    if current_key is None:
        return (
            "All NFR categories are sufficiently covered.\n"
            f"NFR total: {state.nonfunctional_count}\n"
            "Proceed to the IEEE-830 documentation sections phase."
        )

    # Reqs already written for this category
    cat_reqs  = [r for r in state.requirements.values()
                 if r.req_type.value == "non_functional" and r.category == current_key]
    req_lines = [f"  [{r.req_id}] {r.text[:120]}" for r in cat_reqs]

    hint         = NFR_PROBE_HINTS.get(current_key, {})
    focus_text   = hint.get("focus",    "")
    example_text = hint.get("examples", "")

    remaining = [label for key, label in NFR_CATEGORIES.items()
                 if state.nfr_coverage.get(key, 0) < MIN_NFR_PER_CATEGORY
                 and key != current_key]

    lines = [
        f'CURRENT NFR CATEGORY: "{current_label}"',
        f"Coverage: {state.nfr_coverage.get(current_key, 0)}/{MIN_NFR_PER_CATEGORY} required",
        "",
        f"What to probe: {focus_text}",
        f"Example requirements: {example_text}",
        "",
        f"NFRs already written for this category ({len(req_lines)}):",
    ]
    lines += req_lines or ["  (none yet)"]
    lines += ["", "ALL NFR CATEGORIES:"]

    for key, label in NFR_CATEGORIES.items():
        count  = state.nfr_coverage.get(key, 0)
        met    = count >= MIN_NFR_PER_CATEGORY
        icon   = "✅" if met else ("🔶" if count > 0 else "⬜")
        marker = " <- CURRENT" if key == current_key else ""
        lines.append(f"  {icon} {label} ({count}/{MIN_NFR_PER_CATEGORY}){marker}")

    if remaining:
        lines.append(f"\nCategories still to cover after this: {', '.join(remaining)}")

    return "\n".join(lines)


def _build_ieee_section_context(state: "ConversationState") -> str:
    """IEEE phase: current section + completed / remaining sections."""
    phase4_covered = getattr(state, 'phase4_sections_covered', set())

    # First uncovered section
    current_section = None
    for sec_id, label, question, _ in PHASE4_SECTIONS:
        if sec_id not in phase4_covered:
            current_section = (sec_id, label, question)
            break

    if current_section is None:
        return (
            f"All {len(PHASE4_SECTIONS)} IEEE-830 documentation sections are complete.\n"
            "Ready to generate the full SRS document."
        )

    sec_id, label, question = current_section

    completed = [f"  [{sid}] {lbl}" for sid, lbl, _, _ in PHASE4_SECTIONS
                 if sid in phase4_covered]
    remaining  = [f"  [{sid}] {lbl}" for sid, lbl, _, _ in PHASE4_SECTIONS
                  if sid not in phase4_covered and sid != sec_id]

    lines = [
        f"CURRENT SECTION: §{sec_id} — {label}",
        f'Suggested question: "{question}"',
        "",
        f"SECTION PROGRESS: {len(phase4_covered)}/{len(PHASE4_SECTIONS)} complete",
    ]
    if completed:
        lines.append("Completed sections:")
        lines += completed
    if remaining:
        lines.append("Remaining sections after this:")
        lines += remaining

    lines += [
        "",
        "REQUIREMENTS FOR CONTEXT:",
        f"  FR={state.functional_count} | NFR={state.nonfunctional_count} | Total={state.total_requirements}",
    ]
    return "\n".join(lines)


def _build_requirements_summary(state: "ConversationState") -> str:
    """Compact requirements list for SRS-only mode."""
    reqs = state.requirements
    if not reqs:
        return ""
    MAX_INLINE = 60
    if len(reqs) <= MAX_INLINE:
        lines = ["REQUIREMENTS:"]
        for req in reqs.values():
            tag = ("FR"  if req.req_type.value == "functional"     else
                   "NFR" if req.req_type.value == "non_functional"  else "CON")
            lines.append(f"  [{req.req_id}][{tag}] {req.text[:120]}")
        return "\n".join(lines)
    else:
        from collections import defaultdict
        by_cat: dict[str, list] = defaultdict(list)
        for req in reqs.values():
            by_cat[req.category or "general"].append(req)
        lines = [f"REQUIREMENTS SUMMARY ({len(reqs)} total):"]
        for cat, cat_reqs in sorted(by_cat.items(), key=lambda x: -len(x[1])):
            fr_c  = sum(1 for r in cat_reqs if r.req_type.value == "functional")
            nfr_c = sum(1 for r in cat_reqs if r.req_type.value == "non_functional")
            lines.append(f"  {cat}: {len(cat_reqs)} reqs (FR:{fr_c}, NFR:{nfr_c})")
        lines.append(f"  Total: FR={state.functional_count}, NFR={state.nonfunctional_count}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# PHASE DETERMINATION
# ---------------------------------------------------------------------------

def determine_elicitation_phase(state: "ConversationState") -> ElicitationPhase:
    fr_done   = state.functional_count >= MIN_FUNCTIONAL_REQS
    gate      = state.domain_gate
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


# ---------------------------------------------------------------------------
# PROMPT ARCHITECT
# ---------------------------------------------------------------------------

@dataclass
class PromptArchitect:
    task_type: TaskType = "elicitation"
    extra_context: str = field(default="")

    def build_system_message(self, state: "ConversationState") -> str:
        if self.task_type == "srs_only":
            return self._build_srs_only_message(state)
        return self._build_elicitation_message(state)

    def _build_elicitation_message(self, state: "ConversationState") -> str:
        phase        = determine_elicitation_phase(state)
        project_name = state.project_name

        if phase == "fr":
            domain_ctx = _build_domain_context(state)
            role = _ELICITATION_FR_ROLE.format(
                project_name=project_name,
                domain_context=domain_ctx,
                comms_style=_COMMS_STYLE,
                req_format=_REQ_FORMAT,
            )
            phase_label = "CURRENT TASK: ELICIT AND AUTHOR REQUIREMENTS FOR ONE FEATURE AT A TIME"

        elif phase == "nfr":
            nfr_ctx = _build_nfr_context(state)
            role = _ELICITATION_NFR_ROLE.format(
                project_name=project_name,
                nfr_context=nfr_ctx,
                min_nfr=MIN_NFR_PER_CATEGORY,
                comms_style=_COMMS_STYLE,
                req_format=_REQ_FORMAT,
            )
            phase_label = "PHASE 2: NON-FUNCTIONAL REQUIREMENTS — GAP COVERAGE"

        else:  # ieee
            sec_ctx = _build_ieee_section_context(state)
            role = _ELICITATION_IEEE_ROLE.format(
                project_name=project_name,
                section_context=sec_ctx,
                comms_style=_COMMS_STYLE,
                req_format=_REQ_FORMAT,
            )
            phase_label = "PHASE 3: IEEE-830 DOCUMENTATION SECTIONS"

        parts = [
            f"=== ROLE & INSTRUCTIONS ===\n{role}",
            f"=== CURRENT {phase_label} ===",
        ]
        if self.extra_context:
            parts.append(f"=== ADDITIONAL CONTEXT ===\n{self.extra_context}")
        return "\n\n".join(parts)

    def _build_srs_only_message(self, state: "ConversationState") -> str:
        sec_ctx     = _build_ieee_section_context(state)
        req_summary = _build_requirements_summary(state)
        role = _SRS_ONLY_ROLE.format(
            project_name=state.project_name,
            section_context=sec_ctx,
            comms_style=_COMMS_STYLE,
            req_format=_REQ_FORMAT,
        )
        parts = [
            "=== ROLE & INSTRUCTIONS ===\n" + role,
            "=== TASK: SRS FROM EXISTING REQUIREMENTS ===",
        ]
        if req_summary:
            parts.append("=== PROVIDED REQUIREMENTS ===\n" + req_summary)
        return "\n\n".join(parts)

    # -- Public helpers (unchanged interface) --

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