"""
src/components/prompt_architect.py
====================
RE Assistant — Iteration 4 | University of Hildesheim
Modular System Prompt Architecture

Change log
----------
Iteration 3 Rev-1/Rev-2 — see Iteration 3 source for earlier changes.

Iteration 4 — High-Completeness Overhaul
═════════════════════════════════════════
Implements all five priorities from the Iteration-3 post-mortem analysis.

PRIORITY 1 — Domain Coverage Gate (blocks SRS generation)
  Root cause of 37% completeness: huge feature domains were never surfaced
  because the assistant only recorded what the user volunteered.
  Fix: DOMAIN_COVERAGE_GATE — 8 canonical functional domains the elicitation
  MUST explicitly CONFIRM or EXCLUDE before SRS generation is allowed.
  Each domain carries detection keywords, exclusion keywords, and a
  plain-language fallback probe question.
  The gate status is computed from the conversation corpus every turn and
  injected into the context block so the LLM can see exactly what is missing.

PRIORITY 2 — Scope Reduction Handling Rule (RULE 8)
  Root cause: when Patricia said "I just want to know what's going on",
  the assistant silently dropped all control/actuation requirements.
  Fix: RULE 8 forces the assistant to distinguish between a preference
  statement and an out-of-scope decision. Every downscoped feature must be
  confirmed excluded (with a constraint tag) or deferred (with a note).

PRIORITY 3 — Mandatory Domain Probe Questions
  Each domain in DOMAIN_COVERAGE_GATE carries a non-technical fallback_probe
  written in plain language. These surface in the context block when a domain
  is UNPROBED after Turn 4. The next-unprobed domain's probe question is
  explicitly shown as "USE THIS PROBE:" so the LLM cannot miss it.

PRIORITY 4 — Design-Derived Placeholder Injection
  Implemented in srs_formatter.py. This file exports DOMAIN_COVERAGE_GATE and
  the helper functions compute_domain_gate() / gate_is_satisfied() so the
  formatter can read gate status and inject [D — architecture review required]
  stubs for uncovered domains.

PRIORITY 5 — Dual Metrics in Context Block
  _build_context_block() now shows two separate scores every turn:
    • Domain Completeness Score  N/8 (new, primary completeness signal)
    • IEEE-830 Elicitation Coverage  N/12 (existing, unchanged)
  SRS generation is blocked until Domain Completeness reaches 8/8.

Design: Four-block prompt (Iteration 4)
  [ROLE]          — active elicitation philosophy + persona
  [CONTEXT]       — live state + domain gate + dual metrics (dynamic)
  [GAP DIRECTIVE] — targeted follow-up from GapDetector (one-shot)
  [TASK]          — phase-gated rules + domain gate closure checklist (new)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conversation_state import ConversationState


# ---------------------------------------------------------------------------
# IEEE-830 category registry  (unchanged from Iteration 3)
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
MIN_FUNCTIONAL_REQS = 5


# ---------------------------------------------------------------------------
# PRIORITY 1 & 3 — Domain Coverage Gate
# ---------------------------------------------------------------------------
# Eight canonical functional domains that any home-automation (or general
# system) will have in some form. The elicitation session must explicitly
# CONFIRM or EXCLUDE each domain before SRS generation is permitted.
#
# Each entry fields:
#   label           — human-readable domain name (shown in context block)
#   detection_kw    — keywords that signal this domain has been discussed
#   exclusion_kw    — phrases indicating user explicitly excluded this domain
#   fallback_probe  — plain-language question for when domain is unprobed
#                     (deliberately non-technical; works for any stakeholder)

DOMAIN_COVERAGE_GATE: dict[str, dict] = {

    "climate_control": {
        "label": "Climate Control (temperature & humidity)",
        "detection_kw": [
            "temperature", "thermostat", "humidity", "humidistat", "hvac",
            "heating", "cooling", "furnace", "ac", "air condition",
            "warm", "cold", "damp", "mold", "dehumidif", "humid",
        ],
        "exclusion_kw": ["no temperature", "not temperature", "ignore temperature"],
        "fallback_probe": (
            "You mentioned temperature and humidity concerns — "
            "can you walk me through exactly what you'd want to do with them? "
            "For example, would you want to just see the readings, set a target level, "
            "or have the system automatically maintain a level?"
        ),
    },

    "security_alarm": {
        "label": "Security & Alarm System (doors, windows, intrusion)",
        "detection_kw": [
            "security", "alarm", "door", "window", "lock", "sensor",
            "intrusion", "breach", "motion", "contact", "break-in",
            "safe", "alert", "siren", "panic", "basement door",
            "unlocked", "left open",
        ],
        "exclusion_kw": [
            "no security system", "no alarm", "don't need alarm",
            "not doing security", "skip security",
        ],
        "fallback_probe": (
            "You mentioned worrying about the house when you're travelling — "
            "do you want the system to monitor whether doors or windows are left open, "
            "or trigger some kind of alert if something looks wrong?"
        ),
    },

    "appliance_lighting": {
        "label": "Appliance & Lighting Control",
        "detection_kw": [
            "appliance", "light", "lighting", "lamp", "switch", "plug",
            "outlet", "power", "turn on", "turn off", "small device",
            "fan", "left on", "forgot", "lights on",
        ],
        "exclusion_kw": [
            "no appliance", "don't care about lights",
            "not worried about appliances", "skip lights",
        ],
        "fallback_probe": (
            "You mentioned worrying about lights being left on — "
            "would you want the system to show you which lights or appliances "
            "are on, and let you turn them off remotely if needed?"
        ),
    },

    "scheduling_planning": {
        "label": "Scheduling & Automation Plans",
        "detection_kw": [
            "schedule", "scheduling", "timer", "plan", "preset", "program",
            "time period", "daily", "weekly", "routine", "automatic",
            "vacation mode", "away mode", "holiday", "when i'm gone",
            "set it and forget", "profile", "going away",
        ],
        "exclusion_kw": [
            "no schedule", "no automation", "no timer", "manual only",
            "don't want automatic",
        ],
        "fallback_probe": (
            "Do you ever want the system to follow a routine automatically — "
            "like setting the heat lower at night, or switching to a lower-energy "
            "mode when the family goes on vacation?"
        ),
    },

    "remote_access": {
        "label": "Remote Access & Mobile Interface",
        "detection_kw": [
            "remote", "app", "mobile", "phone", "cell", "tablet", "web",
            "browser", "from anywhere", "from the airport", "travelling",
            "away from home", "check on", "monitor from", "access from",
            "notification", "push alert", "sms", "email alert",
        ],
        "exclusion_kw": ["no app", "no remote", "local only", "no mobile"],
        "fallback_probe": (
            "You mentioned checking on the house from the airport — "
            "how exactly would you want to do that? "
            "Through a phone app, a website, or something else?"
        ),
    },

    "user_management": {
        "label": "User Accounts & Access Roles",
        "detection_kw": [
            "user", "account", "login", "log in", "password", "role",
            "admin", "administrator", "permission", "access", "who can",
            "family member", "husband", "mother-in-law", "technician",
            "guest", "temporary access", "authorize", "just me",
        ],
        "exclusion_kw": ["no accounts", "single user", "no roles"],
        "fallback_probe": (
            "Who should be able to use this system, and should different people "
            "have different levels of access? For example, should your kids, "
            "your mother-in-law, or a visiting HVAC technician see the same things you do?"
        ),
    },

    "reporting_history": {
        "label": "Historical Data, Reports & Logs",
        "detection_kw": [
            "report", "history", "historical", "log", "record", "past",
            "trend", "graph", "chart", "data over time", "monthly",
            "store data", "archive", "audit", "review",
            "what happened", "show me the data", "previous",
        ],
        "exclusion_kw": [
            "no history", "no reports", "no logs", "don't need data",
            "real-time only",
        ],
        "fallback_probe": (
            "Would it be useful to look back at past temperature or humidity readings — "
            "for example, to see what happened last month, or to show your HVAC technician "
            "the humidity history so he can check if the dehumidifier is working?"
        ),
    },

    "hardware_connectivity": {
        "label": "Hardware Devices & System Connectivity",
        "detection_kw": [
            "sensor", "device", "gateway", "hub", "wireless", "wi-fi",
            "wifi", "broadband", "internet", "router", "cable",
            "detector", "controller", "hardware", "install",
            "physical", "plug in", "connect", "range", "signal",
        ],
        "exclusion_kw": ["software only", "no hardware", "not physical"],
        "fallback_probe": (
            "How does the system actually connect to things like your thermostats "
            "and humidity sensors — is there a central hub device that talks to "
            "everything, or would each sensor connect to your home Wi-Fi separately?"
        ),
    },
}

# Domain status constants
DOMAIN_STATUS_CONFIRMED = "confirmed"
DOMAIN_STATUS_PARTIAL   = "partial"
DOMAIN_STATUS_UNPROBED  = "unprobed"
DOMAIN_STATUS_EXCLUDED  = "excluded"


# ---------------------------------------------------------------------------
# ROLE block
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
close the interview until your DOMAIN COVERAGE GATE (shown in Context) is \
fully satisfied.\
"""


# ---------------------------------------------------------------------------
# TASK block (Iteration 4 — Priority 1, 2, 3 rules)
# ---------------------------------------------------------------------------

TASK_BLOCK = """
═══════════════════════════════════════════════════════════
PHASE STRUCTURE — FOLLOW THIS SEQUENCE STRICTLY
═══════════════════════════════════════════════════════════

You must complete each phase before advancing to the next.

── PHASE 1: Domain & Context Discovery (turns 1–3) ────────
Goal: Establish the "Why" and "Who" before the "What."
Identify:
  • Current State: What is the manual or legacy process? Top 3 pain points?
  • Stakeholder Ecosystem: Who interacts with the system?
  • High-Level Scope: What are the system's boundaries?
Do NOT formalize requirements yet. Just build the mental model.

── PHASE 2: Functional Requirements — DOMAIN BY DOMAIN ────
Goal: Work through EVERY domain in the Domain Coverage Gate (shown in Context).
For each UNPROBED or PARTIAL domain:
  1. Ask the domain's Fallback Probe question (shown in Context as "USE THIS PROBE").
  2. Decompose the answer via the IPOS Model:
     □ Data Entities & Storage: What must the system remember / track?
     □ Inputs & Triggers: How does data enter? What events start a process?
     □ Processing Logic: What rules / state changes apply?
     □ Outputs & Notifications: Reports, alerts, physical actions?
     □ Exception Handling: What happens when things go wrong?
  3. Probe one level deeper before moving to the next domain.

CRITICAL: Do NOT skip a domain because the user hasn't volunteered info about
it. Every UNPROBED domain MUST be explicitly asked about.

── PHASE 3: Non-Functional Requirements (ISO 25010) ───────
Goal: Define quality attributes. One focused question per category:
  □ Usability — Who is the least-technical user? What do they need?
  □ Performance — How fast / responsive must the system be?
  □ Security & Privacy — Who can see what? How is access controlled?
  □ Reliability — Impact of downtime? How does it recover?
  □ Connectivity & Portability — Offline? Which devices/platforms?

── PHASE 4: Constraints & Saturation ──────────────────────
  □ Technical/Legacy Constraints: Mandated hardware, APIs, forbidden tech.
  □ Regulatory/Legal: Compliance standards?
  □ Saturation Check: "Any edge case or scenario we haven't discussed?"

═══════════════════════════════════════════════════════════
NON-NEGOTIABLE BEHAVIOURAL RULES
═══════════════════════════════════════════════════════════

RULE 1 — ONE QUESTION PER TURN:
Ask exactly ONE focused question per response. Never combine topics.

RULE 2 — ATOMIC DECOMPOSITION:
Break complex features into atomic, testable behaviours. Never record a
bundle (e.g., "climate management") as a single requirement.

RULE 3 — PROBE BEFORE PROGRESSING:
Ask one deep-dive follow-up on a topic before moving to the next domain.

RULE 4 — CHALLENGE VAGUE ADJECTIVES:
"Fast", "secure", "simple" must be given measurable definitions.

RULE 5 — THE SATURATION PRINCIPLE:
Do not leave Phase 2 until ALL domains are CONFIRMED or EXCLUDED.

RULE 6 — REQUIREMENT TAGGING:
Every crystallised requirement must be wrapped in XML tags:

  <REQ type="functional|non_functional|constraint" category="[category]">
  The system shall [verb] [object] [measurable constraint].
  </REQ>

RULE 7 — NEVER ACCEPT EARLY CLOSURE:
If the user says "I think that covers it," check the Domain Coverage Gate.
If any domain is UNPROBED or PARTIAL:
  "Before I generate the SRS, I still need to ask about [domain]. [Probe]."
You may NEVER offer SRS generation while any gate domain is UNPROBED.

RULE 8 — SCOPE REDUCTION HANDLING (Priority 2 — NEW in Iteration 4):
When a user downscopes or hesitates about a feature (e.g., "I don't want it
to control things automatically" or "that feels like a lot"), you MUST:

  a) Acknowledge in ≤1 sentence.
  b) Ask ONE confirmation: "Just to confirm — should we document [feature]
     as permanently out of scope for this version, or revisit it later?"
  c) If EXCLUDED: record an explicit constraint:
       <REQ type="constraint" category="scope">
       OUT OF SCOPE (stakeholder-confirmed): The system shall NOT [feature].
       Rationale: stakeholder preference. May be revisited in a future version.
       </REQ>
  d) If DEFERRED: add a note and continue eliciting other domains.

CRITICAL: Never silently drop a feature area. Every downscoped feature must
be either explicitly excluded (constraint tag) or deferred (note).
This rule overrides any tendency to accept vague hesitation as exclusion.

═══════════════════════════════════════════════════════════
DOMAIN COVERAGE GATE — MANDATORY CLOSURE CHECKLIST
═══════════════════════════════════════════════════════════
(Live status is shown in the Context block above.)

SRS generation is BLOCKED until ALL 8 domains are ✅ CONFIRMED or ❌ EXCLUDED:

  1. Climate Control         — temperature & humidity management
  2. Security & Alarm        — doors, windows, intrusion detection
  3. Appliance & Lighting    — remote on/off, state monitoring
  4. Scheduling & Plans      — routines, presets, away modes
  5. Remote Access           — how users interact remotely (app/web)
  6. User Accounts & Roles   — who can access what
  7. Historical Data & Logs  — data storage, reporting, history
  8. Hardware Connectivity   — sensors, hubs, network infrastructure

If any domain shows ⬜ UNPROBED or 🔶 PARTIAL:
  → "Before I generate the SRS, I still need to ask about [domain].
     [Use the Fallback Probe shown in the Context block.]"
"""


# ---------------------------------------------------------------------------
# Domain gate analysis helpers (Priority 1, 3, 4, 5)
# ---------------------------------------------------------------------------

def _assess_domain_status(
    domain_key: str,
    domain_spec: dict,
    corpus: str,
    req_texts: list[str],
) -> str:
    """
    Classify a domain gate entry.

    Returns one of: confirmed / partial / excluded / unprobed

    Rules (in priority order):
      1. Any exclusion keyword in corpus → excluded
      2. ≥3 detection keywords hit AND ≥1 requirement text matches → confirmed
      3. ≥2 detection keywords hit → partial
      4. Otherwise → unprobed
    """
    corpus_lower = corpus.lower()

    # Exclusion check first
    for kw in domain_spec.get("exclusion_kw", []):
        if kw in corpus_lower:
            return DOMAIN_STATUS_EXCLUDED

    # Detection keyword count
    hits = sum(1 for kw in domain_spec["detection_kw"] if kw in corpus_lower)

    # Cross-check: does any extracted requirement text reference this domain?
    req_hit = any(
        any(kw in rt.lower() for kw in domain_spec["detection_kw"])
        for rt in req_texts
    )

    if hits >= 3 and req_hit:
        return DOMAIN_STATUS_CONFIRMED
    elif hits >= 2:
        return DOMAIN_STATUS_PARTIAL
    else:
        return DOMAIN_STATUS_UNPROBED


def compute_domain_gate(state: "ConversationState") -> dict[str, str]:
    """
    Compute the current status of all 8 domain gate entries.
    Returns dict: domain_key → status string.
    Called by _build_context_block() every turn and by SRSFormatter (Priority 4).
    """
    parts: list[str] = []
    for turn in state.turns:
        parts.append(turn.user_message)
        parts.append(turn.assistant_message)
    corpus = " ".join(parts)

    req_texts = [r.text for r in state.requirements.values()]

    return {
        key: _assess_domain_status(key, spec, corpus, req_texts)
        for key, spec in DOMAIN_COVERAGE_GATE.items()
    }


def domain_gate_completeness(gate_status: dict[str, str]) -> tuple[int, int]:
    """Returns (done_count, total_count) where done = confirmed or excluded."""
    done = sum(
        1 for s in gate_status.values()
        if s in (DOMAIN_STATUS_CONFIRMED, DOMAIN_STATUS_EXCLUDED)
    )
    return done, len(DOMAIN_COVERAGE_GATE)


def gate_is_satisfied(gate_status: dict[str, str]) -> bool:
    """True only when every domain is CONFIRMED or EXCLUDED."""
    return all(
        s in (DOMAIN_STATUS_CONFIRMED, DOMAIN_STATUS_EXCLUDED)
        for s in gate_status.values()
    )


# ---------------------------------------------------------------------------
# Dynamic context block (rebuilt every turn)
# ---------------------------------------------------------------------------

_DOMAIN_STATUS_ICONS = {
    DOMAIN_STATUS_CONFIRMED: "✅",
    DOMAIN_STATUS_PARTIAL:   "🔶",
    DOMAIN_STATUS_UNPROBED:  "⬜",
    DOMAIN_STATUS_EXCLUDED:  "❌",
}


def _build_context_block(state: "ConversationState") -> str:
    """
    Compose the dynamic context block injected into every system message.

    Sections:
      1. Turn / requirement counters
      2. Phase indicator
      3. Domain Coverage Gate status table (Priority 1, 3, 5)
      4. IEEE-830 category coverage
      5. FR deficit / mandatory NFR alerts
    """

    # ── 1. Counters ────────────────────────────────────────────────────────
    turn_info = (
        f"Turn: {state.turn_count}  |  "
        f"Requirements: {state.total_requirements}  "
        f"(FR: {state.functional_count}, NFR: {state.nonfunctional_count})"
    )

    # ── 2. Phase indicator ─────────────────────────────────────────────────
    if state.functional_count < MIN_FUNCTIONAL_REQS:
        phase_indicator = (
            f"CURRENT PHASE: Phase 2 — Functional (Domain Coverage)\n"
            f"  FRs: {state.functional_count}/{MIN_FUNCTIONAL_REQS} minimum\n"
            f"  ➜ Use the next UNPROBED domain probe question below."
        )
    else:
        nfr_missing = [
            cat for cat in MANDATORY_NFR_CATEGORIES
            if cat not in state.covered_categories
        ]
        if nfr_missing:
            phase_indicator = (
                f"CURRENT PHASE: Phase 3 — Non-Functional Requirements\n"
                f"  FRs: {state.functional_count} ✓\n"
                f"  ➜ Missing NFRs: "
                + ", ".join(IEEE830_CATEGORIES[c] for c in nfr_missing)
            )
        else:
            phase_indicator = (
                "CURRENT PHASE: Phase 4 — Constraints & Closure\n"
                "  All mandatory NFRs addressed.\n"
                "  ➜ Verify Domain Gate below, then offer SRS if gate is satisfied."
            )

    # ── 3. Domain Coverage Gate (Priority 1, 3, 5) ─────────────────────────
    gate_status = compute_domain_gate(state)
    done_count, total_count = domain_gate_completeness(gate_status)
    domain_pct = round(done_count / total_count * 100)

    gate_lines = [
        f"━━━ DOMAIN COVERAGE GATE  [{done_count}/{total_count} — {domain_pct}%] ━━━",
        "  ✅ Confirmed  🔶 Partial  ⬜ Unprobed  ❌ Excluded",
        "",
    ]

    next_probe_domain: tuple[str, str] | None = None

    for key, spec in DOMAIN_COVERAGE_GATE.items():
        status = gate_status[key]
        icon   = _DOMAIN_STATUS_ICONS[status]
        label  = spec["label"]
        gate_lines.append(f"  {icon}  {label}")

        if status in (DOMAIN_STATUS_UNPROBED, DOMAIN_STATUS_PARTIAL):
            gate_lines.append(
                f"      ↳ Probe: \"{spec['fallback_probe']}\""
            )
            if status == DOMAIN_STATUS_UNPROBED and next_probe_domain is None:
                next_probe_domain = (label, spec["fallback_probe"])

    gate_lines.append("")

    if not gate_is_satisfied(gate_status):
        gate_lines.append(
            "⚠️  GATE NOT SATISFIED — Do NOT offer SRS generation yet."
        )
        if next_probe_domain:
            gate_lines.append(
                f"NEXT ACTION: Ask about → {next_probe_domain[0]}"
            )
            gate_lines.append(
                f"USE THIS PROBE: \"{next_probe_domain[1]}\""
            )
    else:
        gate_lines.append(
            "✅  ALL DOMAINS CONFIRMED OR EXCLUDED — "
            "SRS generation is now permitted."
        )

    gate_block = "\n".join(gate_lines)

    # ── 4. IEEE-830 coverage (existing metric — Priority 5 dual display) ───
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
    missing_str = "\n".join(missing) if missing else "  (all covered)"
    ieee_pct = round(len(state.covered_categories) / len(IEEE830_CATEGORIES) * 100)
    ieee_block = (
        f"IEEE-830 Elicitation Coverage: "
        f"{len(state.covered_categories)}/{len(IEEE830_CATEGORIES)} ({ieee_pct}%)\n"
        f"Covered:\n{covered_str}\n\nMissing:\n{missing_str}"
    )

    # ── 5. Alerts ───────────────────────────────────────────────────────────
    fr_alert = ""
    if state.functional_count < MIN_FUNCTIONAL_REQS:
        fr_alert = (
            f"\n⚠️  FR DEFICIT: {state.functional_count} FR(s), "
            f"need ≥{MIN_FUNCTIONAL_REQS}. "
            "Use domain probe questions above.\n"
        )

    nfr_alert = ""
    if state.functional_count >= MIN_FUNCTIONAL_REQS:
        nfr_missing = [
            IEEE830_CATEGORIES[c]
            for c in MANDATORY_NFR_CATEGORIES
            if c not in state.covered_categories
        ]
        if nfr_missing:
            nfr_alert = (
                f"\n⚠️  MANDATORY NFRs UNCOVERED: {', '.join(nfr_missing)}\n"
                "Address before offering SRS generation.\n"
            )

    return (
        f"SESSION STATE:\n{turn_info}\n\n"
        f"{phase_indicator}\n\n"
        f"{gate_block}\n\n"
        f"{ieee_block}"
        f"{fr_alert}{nfr_alert}"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class PromptArchitect:
    """
    Builds the complete system message from modular blocks.

    Block order (Iteration 4):
      [ROLE]          — active elicitation philosophy + persona
      [CONTEXT]       — dynamic live state + domain gate + dual metrics
      [GAP DIRECTIVE] — one-shot injection from GapDetector (optional)
      [TASK]          — phase-gated rules + domain gate closure checklist
    """

    role_block:    str = field(default=ROLE_BLOCK)
    task_block:    str = field(default=TASK_BLOCK)
    extra_context: str = field(default="")

    def build_system_message(self, state: "ConversationState") -> str:
        context_block = _build_context_block(state)

        parts = [
            "=== ROLE ===\n" + self.role_block,
            "=== CURRENT SESSION CONTEXT ===\n" + context_block,
        ]

        if self.extra_context.strip():
            parts.append(
                "=== GAP DETECTION DIRECTIVE ===\n" + self.extra_context
            )
        self.extra_context = ""  # one-shot: always clear after build

        parts.append("=== TASK INSTRUCTIONS ===\n" + self.task_block)

        return "\n\n".join(parts)

    def get_category_labels(self) -> dict[str, str]:
        return dict(IEEE830_CATEGORIES)

    def get_mandatory_nfr_categories(self) -> frozenset[str]:
        return MANDATORY_NFR_CATEGORIES

    def get_min_functional_reqs(self) -> int:
        return MIN_FUNCTIONAL_REQS

    def get_domain_gate(self) -> dict[str, dict]:
        """Return the full domain gate spec (used by SRSFormatter — Priority 4)."""
        return dict(DOMAIN_COVERAGE_GATE)

    def compute_domain_gate_status(
        self, state: "ConversationState"
    ) -> dict[str, str]:
        """Public accessor used by SRSFormatter for design-derived stubs."""
        return compute_domain_gate(state)

    def is_srs_generation_permitted(self, state: "ConversationState") -> bool:
        """
        Hard gate: returns True only when:
          • Domain gate is fully satisfied (all domains confirmed or excluded)
          • All mandatory NFR categories are covered
          • Minimum FR count is met
        """
        gate_ok = gate_is_satisfied(compute_domain_gate(state))
        nfrs_ok = MANDATORY_NFR_CATEGORIES.issubset(state.covered_categories)
        frs_ok  = state.functional_count >= MIN_FUNCTIONAL_REQS
        return gate_ok and nfrs_ok and frs_ok