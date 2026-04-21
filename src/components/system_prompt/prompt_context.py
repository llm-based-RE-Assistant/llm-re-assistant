from typing import TYPE_CHECKING, Literal
from src.components.domain_discovery.domain_discovery import _label_to_key
from src.components.system_prompt.utils import (
    MIN_NFR_PER_CATEGORY,
    NFR_PROBE_HINTS,
    PHASE4_SECTIONS,
    MANDATORY_NFR_CATEGORIES
)
if TYPE_CHECKING:
    from src.components.conversation_state import ConversationState

# ---------------------------------------------------------------------------
# CONTEXT BLOCK BUILDERS — focused, one-target-at-a-time
# ---------------------------------------------------------------------------

def _build_scope_context(state: "ConversationState") -> str:
    """Phase 0: show which brief fields are filled and which are still empty."""
    BRIEF_FIELDS = [
        ("system_purpose",     "System Purpose",      "what problem does this system solve, purpose of the system?"),
        ("user_classes",       "User classes",        "Who uses the system and what is each person's primary goal?"),
        ("core_features",      "Core features",       "What are the main things the system must do?"),
        ("scale_and_context",  "Scale / context",     "How many users/devices? Home, enterprise, cloud?"),
        ("key_constraints",    "Known constraints",   "Any regulatory, legal, budget, or technical limits?"),
        ("integration_points", "Integration points",  "Does it connect to external systems, devices, or APIs?"),
        ("out_of_scope",       "Out of scope",        "What should the system explicitly NOT do?"),
    ]
    brief = getattr(state, "project_brief", {})
    scope_turn = getattr(state, "scope_turn_count", 0)

    filled   = [(key, label) for key, label, _ in BRIEF_FIELDS if brief.get(key)]
    empty    = [(key, label, hint) for key, label, hint in BRIEF_FIELDS if not brief.get(key)]

    lines = [
        f"SCOPE BRIEF PROGRESS: {len(filled)}/7 fields confirmed | Turns used: {scope_turn}/10",
        "",
    ]
    if filled:
        lines.append("CONFIRMED fields:")
        for key, label in filled:
            lines.append(f"  ✅ {label}: {brief[key]}")
        lines.append("")

    if empty:
        # Show the next empty field as the current target
        next_key, next_label, next_hint = empty[0]
        lines.append(f"NEXT FIELD TO FILL: {next_label}({next_key})")
        lines.append(f"  What to ask: {next_hint}")
        if len(empty) > 1:
            lines.append(f"  Still needed after this: {', '.join(l for _, l, _ in empty[1:])}")
    else:
        lines.append("All fields confirmed. Emit <SCOPE field=\"status\">complete</SCOPE> and transition.")

    return "\n".join(lines)


def _build_domain_context(state: "ConversationState") -> str:
    """FR phase: project brief + current domain + its reqs + coverage template + remaining list."""
    gate = state.domain_gate

    # ── Project brief block (from Phase 0) ───────────────────────────────────
    brief_block = state.format_brief_for_prompt() if hasattr(state, "format_brief_for_prompt") else ""

    if gate is None or not gate.seeded or not gate.domains:
        fallback = (
            "Domain discovery not yet complete. Begin by understanding what the "
            "system should do, then elicit requirements feature by feature."
        )
        return (brief_block + "\n\n" + fallback) if brief_block else fallback

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
    fr_lines  = [
        f"  [{r.req_id}] {r.text[:120]}" for r in domain_reqs if r.req_type.value == "functional"
    ]
    
    nfr_lines = [
        f"  [{r.req_id}] {r.text[:120]}" for r in domain_reqs if r.req_type.value == "non_functional"
    ]

    remaining = [
        d.label for d in gate.domains.values()
        if d.label != current_domain.label 
        and d.status not in ("confirmed", "excluded")
    ]

    # IT10: system complexity label (drives elicitation depth signal)
    complexity = getattr(state, 'system_complexity', '') or 'not yet assessed'

    domain_key = _label_to_key(current_domain.label) or 'not-yet-assessed'

    lines = []
    if brief_block:
        lines.append(brief_block)
        lines.append("")

    lines += [
        f'CURRENT FEATURE: "{current_domain.label}"',
        f"Feature's Category Key: {domain_key} | Probes so far: {current_domain.probe_count} | System complexity: {complexity}",
        "",
        f"Functional requirements written for this feature ({len(fr_lines)}):",
    ]
    lines += fr_lines or ["  (none yet)"]
    lines += ["", f"Non-functional requirements written for this feature ({len(nfr_lines)}):"]
    lines += nfr_lines or ["  (none yet — write the obvious NFRs for this feature now)"]

    # IT10: inject domain requirement coverage template when available
    domain_key = None
    for dk, dv in gate.domains.items():
        if dv is current_domain:
            domain_key = dk
            break
    domain_templates = getattr(state, 'domain_req_templates', {})
    template = domain_templates.get(domain_key, "") if domain_key else ""

    if template:
        lines += [
            "",
            "REQUIREMENT COVERAGE CHECKLIST FOR THIS FEATURE:",
            "  (Generated from the customer's description. Each dimension below must be",
            "   addressed before moving to the next feature. Cross off by writing <REQ> tags",
            "   for each one — do not leave any dimension unaddressed.)",
            "",
        ]
        for line in template.splitlines():
            lines.append(f"  {line}")
        lines += [
            "",
            "DIMENSION COVERAGE CROSS CHECK:",
            "   For each dimension in the REQUIREMENT COVERAGE CHECKLIST, assign exactly one status:",
            "   [COVERED]    — customer gave me sufficient information; I have written a <REQ> for it.",
            "   [PENDING]    — insufficient customer input yet; I will probe this in a future turn.",
            "   [OUT-OF-SCOPE] — this dimension belongs to a different feature; do not write it here.",
            "",
            "   Rule:"
            "   - Write <REQ> tags ONLY for [COVERED] dimensions.",
            "   - Do NOT write requirements for [PENDING] dimensions — probe them instead.",
            "   - Do NOT write requirements for [OUT-OF-SCOPE] dimensions under any circumstance.",
        ]
    else:
        lines += [
            "",
            "COVERAGE GUIDANCE (no template yet — apply standard RE dimensions):",
            "  Before moving on, ensure you have addressed:",
            "  - DATA: what information is stored, validated, and managed",
            "  - ACTOR ACTIONS: what each user role can do, with preconditions",
            "  - SYSTEM AUTOMATION: what happens automatically without user input",
            "  - BUSINESS RULES: validation logic, constraints, calculation policies",
            "  - ERROR & EDGE CASES: what happens with missing, invalid, or extreme inputs",
            "  - DOMAIN-SPECIFIC NFRs: performance, security, or compliance rules for this feature",
        ]

    lines += [""]

    if remaining:
        lines.append(f"Remaining features to elicit after this: {', '.join(remaining[:2])}" + 
                     (f", and {len(remaining)-2} more" if len(remaining) > 2 else ""))

    lines.append(f"\nDomain progress: {gate.done_count}/{gate.total} features complete")
    lines.append(f"Session totals: FR={state.functional_count}, NFR={state.nonfunctional_count}")
    return "\n".join(lines)


def _build_nfr_context(state: "ConversationState") -> str:
    """NFR phase: current NFR category + its reqs + all category statuses."""
    from src.components.domain_discovery.domain_discovery import NFR_CATEGORIES

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

def _build_brief_for_ieee(state: "ConversationState") -> str:
    brief_block = state.format_brief_for_prompt() if hasattr(state, "format_brief_for_prompt") else ""
    return brief_block


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
    return "\n".join(lines), brief_block


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

TaskType = Literal["elicitation", "srs_only"]
ElicitationPhase = Literal["scope", "fr", "nfr", "ieee"]

# Minimum fraction of seeded domains that must be confirmed before the
# FR phase is considered complete. Grounded in completeness coverage:
# we require at least 80% of identified domains to have been actively
# elicited before advancing. This prevents early phase transition when
# only a few domains are confirmed and the rest were never probed.
def determine_elicitation_phase(state: "ConversationState") -> ElicitationPhase:
    """Determine which elicitation phase the conversation is in.

    Phase order: scope → fr → nfr → ieee. All gates must pass before advancing.

    SCOPE gate — passes when scope_complete is True on the state.
      For srs_only task type: scope phase is skipped entirely.

    FR gate — two conditions must both be true:
      1. functional_count >= MIN_FUNCTIONAL_REQS.
      2. Domain gate satisfied: gate.is_satisfied is True OR no gate was seeded.

    NFR gate:
      All keys in MANDATORY_NFR_CATEGORIES have >= MIN_NFR_PER_CATEGORY reqs.

    IEEE gate:
      FR + NFR both satisfied.
    """
    # srs_only always skips scope and starts at ieee
    task_type = getattr(state, "task_type", "elicitation")
    if task_type == "srs_only":
        gate = state.domain_gate
        domain_ok = (gate is None) or gate.is_satisfied
        if not domain_ok:
            return "fr"
        nfr_done = all(
            state.nfr_coverage.get(c, 0) >= MIN_NFR_PER_CATEGORY
            for c in MANDATORY_NFR_CATEGORIES
        )
        return "ieee" if nfr_done else "nfr"

    # ── Scope gate ────────────────────────────────────────────────────────────
    if not getattr(state, "scope_complete", False):
        return "scope"

    gate = state.domain_gate

    # ── FR gate ──────────────────────────────────────────────────────────────
    if gate is None:
        domain_ok = True
    else:
        domain_ok = gate.is_satisfied

    if not domain_ok:
        return "fr"

    # ── NFR gate ─────────────────────────────────────────────────────────────
    nfr_done = all(
        state.nfr_coverage.get(c, 0) >= MIN_NFR_PER_CATEGORY
        for c in MANDATORY_NFR_CATEGORIES
    )
    if not nfr_done:
        return "nfr"

    # ── IEEE gate ─────────────────────────────────────────────────────────────
    return "ieee"