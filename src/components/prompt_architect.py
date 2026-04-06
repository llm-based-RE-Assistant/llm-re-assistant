"""
src/components/prompt_architect.py
====================
RE Assistant — Iteration 3 | University of Hildesheim
Modular System Prompt Architecture

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

# Domain status constants
DOMAIN_STATUS_CONFIRMED = "confirmed"
DOMAIN_STATUS_PARTIAL   = "partial"
DOMAIN_STATUS_UNPROBED  = "unprobed"
DOMAIN_STATUS_EXCLUDED  = "excluded"

DOMAIN_COVERAGE_GATE: dict[str, dict] = {}


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
"Fast", "secure", "simple" or such words must be given measurable definitions.

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
"""


# ---------------------------------------------------------------------------
# Domain gate generation and update (Dynamic LLM-based)
# ---------------------------------------------------------------------------

def generate_domain_gate_from_llm(
    first_user_message: str,
    project_context: str,
    llm_provider,
) -> dict[str, dict]:
    """
    After first user message, call LLM to generate initial domain gate.
    
    Args:
        first_user_message: The user's first message describing the project
        project_context: Brief project context extracted from the message
        llm_provider: LLM provider to call
    
    Returns:
        Dictionary of domain → {label, detection_kw, exclusion_kw, fallback_probe}
    """
    system_prompt = """\
You are an expert Requirements Engineer generating domain categories for elicitation.
Based on the project description, generate 5-8 domain/feature areas that need to be explored.

For EACH domain, return VALID JSON with this exact structure:
{
  "domain_key": {
    "label": "Human-readable domain name",
    "detection_kw": ["keyword1", "keyword2", ...],
    "exclusion_kw": ["exclusion1", ...],
    "fallback_probe": "A question to ask if this domain hasn't been discussed"
  }
}

Detection keywords should be terms likely to appear if the domain is mentioned.
Exclusion keywords are phrases that clearly exclude the domain from scope.
Keep keywords lowercase and concise.
Keep the fallback_probe as a single, clear question.
"""
    
    user_prompt = f"""\
Project Name: {project_context}
Project description: {first_user_message}

Generate 5-8 domain/feature areas relevant to this project.
Return ONLY valid JSON, no markdown, no explanations.
"""
    
    try:
        response = llm_provider.chat(
            system_message=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.3,
        )
        
        # Parse JSON response
        import json
        import re
        
        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            parsed = json.loads(json_str)
            # Merge with defaults and return
            merge_gate = dict(DOMAIN_COVERAGE_GATE)
            for key, spec in parsed.items():
                if all(k in spec for k in ["label", "detection_kw", "exclusion_kw", "fallback_probe"]):
                    merge_gate[key] = spec
            return merge_gate
    except Exception as e:
        print(f"Warning: Failed to generate domain gate from LLM: {e}")
    
    # Fallback to default
    return dict(DOMAIN_COVERAGE_GATE)


def expand_domain_gate_from_llm(
    current_gate: dict[str, dict],
    conversation_corpus: str,
    requirements_texts: list[str],
    llm_provider,
) -> dict[str, dict]:
    """
    After turn 5, call LLM to evaluate if additional domains should be added.
    
    Args:
        current_gate: Current domain gate dictionary
        conversation_corpus: Full conversation text so far
        requirements_texts: List of extracted requirement texts
        llm_provider: LLM provider to call
    
    Returns:
        Updated domain gate with potentially new domains
    """
    current_labels = ", ".join(f"• {spec['label']}" for spec in current_gate.values())
    
    system_prompt = """\
You are an expert Requirements Engineer analyzing an elicitation conversation.
Review the current domains and conversation, then suggest if additional domain areas should be added.

Response format - return ONLY valid JSON:
{
  "should_expand": true/false,
  "new_domains": {
    "domain_key": {
      "label": "Domain name",
      "detection_kw": ["kw1", "kw2"],
      "exclusion_kw": ["excl1"],
      "fallback_probe": "Question to ask"
    }
  }
}
"""
    
    user_prompt = f"""\
Current domains:
{current_labels}

Conversation excerpt (first 5 turns):
{conversation_corpus[:2000]}

Extracted requirements so far:
{'; '.join(requirements_texts[:10]) if requirements_texts else '(none yet)'}

Based on this, should we add any new domain areas not yet covered? 
Return only JSON response, no explanations.
"""
    
    try:
        response = llm_provider.chat(
            system_message=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.3,
        )
        
        import json
        import re
        
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            parsed = json.loads(json_str)
            
            if parsed.get("should_expand") and parsed.get("new_domains"):
                updated_gate = dict(current_gate)
                for key, spec in parsed["new_domains"].items():
                    if all(k in spec for k in ["label", "detection_kw", "exclusion_kw", "fallback_probe"]):
                        updated_gate[key] = spec
                return updated_gate
    except Exception as e:
        print(f"Warning: Failed to expand domain gate from LLM: {e}")
    
    # Return unchanged if expansion fails
    return current_gate


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


def compute_domain_gate(state: "ConversationState", domain_gate: dict[str, dict]) -> dict[str, str]:
    """
    Compute the current status of all domain gate entries.
    Returns dict: domain_key → status string.
    Called by _build_context_block() every turn and by SRSFormatter (Priority 4).
    """
    parts: list[str] = []
    for turn in state.turns:
        parts.append(turn.user_message)
        parts.append(turn.assistant_message)
    corpus = " ".join(parts)

    req_texts = [r.text for r in state.requirements.values()]
    status_dict = {}
    for key, spec in domain_gate.items():
        status = _assess_domain_status(key, spec, corpus, req_texts)
        status_dict[key] = status
    return status_dict


def domain_gate_completeness(gate_status: dict[str, str]) -> tuple[int, int]:
    """Returns (done_count, total_count) where done = confirmed or excluded."""
    done = sum(
        1 for s in gate_status.values()
        if s in (DOMAIN_STATUS_CONFIRMED, DOMAIN_STATUS_EXCLUDED)
    )
    return done, len(gate_status)


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
    
    The domain_gate is dynamically populated:
      - After first user message: LLM generates initial domains
      - After turn 5: LLM evaluates if new domains should be added
    """

    role_block:    str = field(default=ROLE_BLOCK)
    task_block:    str = field(default=TASK_BLOCK)
    extra_context: str = field(default="")
    domain_gate:   dict[str, dict] = field(default_factory=lambda: dict(DOMAIN_COVERAGE_GATE))

    def _build_context_block(self, state: "ConversationState") -> str:
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
        gate_status = compute_domain_gate(state, self.domain_gate)
        done_count, total_count = domain_gate_completeness(gate_status)
        domain_pct = round(done_count / total_count * 100) if total_count > 0 else 0

        gate_lines = [
            f"━━━ DOMAIN COVERAGE GATE  [{done_count}/{total_count} — {domain_pct}%] ━━━",
            "  ✅ Confirmed  🔶 Partial  ⬜ Unprobed  ❌ Excluded",
            "",
        ]

        next_probe_domain: tuple[str, str] | None = None

        for key, spec in self.domain_gate.items():
            status = gate_status.get(key, DOMAIN_STATUS_UNPROBED)
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

    def build_system_message(self, state: "ConversationState") -> str:
        context_block = self._build_context_block(state)

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
        """Return the current domain gate spec (used by SRSFormatter — Priority 4)."""
        return dict(self.domain_gate)

    def compute_domain_gate_status(
        self, state: "ConversationState"
    ) -> dict[str, str]:
        """Public accessor used by SRSFormatter for design-derived stubs."""
        return compute_domain_gate(state, self.domain_gate)

    def is_srs_generation_permitted(self, state: "ConversationState") -> bool:
        """
        Hard gate: returns True only when:
          • Domain gate is fully satisfied (all domains confirmed or excluded)
          • All mandatory NFR categories are covered
          • Minimum FR count is met
        """
        gate_ok = gate_is_satisfied(compute_domain_gate(state, self.domain_gate))
        nfrs_ok = MANDATORY_NFR_CATEGORIES.issubset(state.covered_categories)
        frs_ok  = state.functional_count >= MIN_FUNCTIONAL_REQS
        return gate_ok and nfrs_ok and frs_ok