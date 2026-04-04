"""
src/components/srs_coverage.py — Iteration 5
University of Hildesheim

SRS Section Completion Module
==============================
Fills the IEEE-830 SRS sections that the elicitation interview does not
naturally produce.  Triggered once ALL gates are satisfied (domain gate +
all mandatory NFR categories) and the session is ready for SRS generation.

WHY THIS MODULE EXISTS
----------------------
The elicitation conversation reliably produces Functional Requirements (§3.1)
and the six mandatory NFR categories (§3.3, §3.6.x).  However the following
IEEE-830 sections are structurally required but cannot be elicited in plain
dialogue without breaking conversation flow:

  §1.2   Scope
  §2.1   Product Perspective
  §2.2   Product Functions         ← synthesis, not invention
  §2.3   User Classes              ← synthesis from conversation
  §2.4   Operating Environment     ← never asked
  §2.6   User Documentation        ← never asked
  §2.7   Assumptions & Dependencies ← partially implicit in NFRs
  §3.2   External Interface Reqs   ← UI / HW / SW / Comms
  §3.4   Logical Database Reqs     ← never asked
  §3.5   Design Constraints        ← never asked

HALLUCINATION RISK CLASSIFICATION
----------------------------------
Each section falls into one of three risk tiers:

  LOW RISK — Synthesis from elicited data only
    §1.2, §2.1, §2.2, §2.3, §2.5
    → LLM is given ONLY the actual requirements + conversation excerpts.
    → Prompt explicitly bans adding facts not present in the source.
    → Output is grounded and verifiable.

  MEDIUM RISK — Reasonable inference from domain + NFRs
    §2.4, §2.6, §3.2.1, §3.2.3, §3.2.4
    → LLM is given requirements + domain type as context.
    → Prompt instructs LLM to state what is TYPICAL for this domain class
      and mark every sentence as "[inferred]" when not directly stated.
    → Reviewer can easily spot and correct inferences.

  HIGH RISK — No elicited data, structural stub required
    §3.2.2 Hardware Interfaces, §3.4 Logical Database Reqs, §3.5 Design Constraints
    → LLM is NOT asked to fill these freely.
    → Instead: a formal stub is generated with a checklist of items the
      architect MUST confirm before development begins.
    → The stub is clearly marked [REQUIRES ARCHITECT REVIEW].

INTEGRATION POINTS
------------------
  Called from ConversationManager.finalize_session() BEFORE SRSFormatter runs:

      from srs_coverage import SRSCoverageEnricher
      enricher = SRSCoverageEnricher(provider=self.provider)
      enricher.enrich(template, state)          # mutates template in-place
      srs_path = generate_srs_document(template, state, output_dir)

  The SRSFormatter already checks `if s2.product_perspective:` etc., so any
  non-empty string written here will appear in the final document.

OUTPUT CONTRACT
---------------
Every generated string:
  - Is written into the correct SRSTemplate field (Section1, Section2, etc.)
  - Uses formal IEEE-830 language: "The system shall…" / "It is assumed that…"
  - Is prefixed with [INFERRED] or [ARCHITECT REVIEW REQUIRED] where the
    content is not directly derived from elicited requirements.
  - Never invents stakeholder names, technology choices, or business rules
    that were not mentioned in the conversation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from conversation_state import ConversationState
    from srs_template import SRSTemplate, Section1, Section2, UserClass

# ---------------------------------------------------------------------------
# Section-level prompts
# ---------------------------------------------------------------------------

_SYSTEM_ROLE = """\
You are a senior Requirements Engineer completing formal IEEE 830-1998 SRS \
sections from a completed stakeholder elicitation session.

ABSOLUTE RULES — violating any of these invalidates the output:
1. NEVER invent facts not present in the provided requirements or transcript.
2. If something was not stated, write [INFERRED] before the sentence and note \
   it is a reasonable assumption for this type of system.
3. Write in formal, third-person technical prose. No bullet summaries unless \
   the section structure explicitly requires them.
4. Use IEEE "shall" language for requirements; "is assumed that" for assumptions.
5. Keep each section self-contained and professional — it will appear verbatim \
   in a document handed to a development team.
6. Return ONLY the section text with no preamble, explanation, or JSON wrapper. \
   Do not repeat the section heading.
"""

# --------------- §1.2 Scope -------------------------------------------------

_SCOPE_PROMPT = """\
Write the IEEE 830 §1.2 Scope section for the system described below.

The scope must cover:
(a) What the system IS — its name and primary purpose in one sentence.
(b) What it DOES — the major functional areas it covers (derive from the FR list).
(c) What it DOES NOT DO — list every explicitly excluded feature mentioned in the transcript.
(d) The primary benefit and objective the system delivers to its users.

Do NOT mention development methodology, implementation technology, or anything \
not evidenced by the requirements or transcript.

PROJECT NAME: {project_name}

ELICITED FUNCTIONAL REQUIREMENTS ({fr_count} total):
{fr_list}

EXPLICITLY EXCLUDED SCOPE ITEMS (from conversation):
{exclusions}
"""

# --------------- §2.1 Product Perspective -----------------------------------

_PERSPECTIVE_PROMPT = """\
Write the IEEE 830 §2.1 Product Perspective section.

This section must explain:
(a) Whether the system is standalone, part of a larger system, or a replacement \
    for an existing product — derive this only from the requirements.
(b) Which external systems or physical devices the system interacts with \
    (derive from compatibility/interface requirements).
(c) How the system fits into the user's environment (home, enterprise, mobile, etc.)

PROJECT NAME: {project_name}
DOMAIN: {domain_summary}

ALL REQUIREMENTS:
{all_reqs}
"""

# --------------- §2.2 Product Functions -------------------------------------

_PRODUCT_FUNCTIONS_DOMAIN_PROMPT = """\
Write the IEEE 830 §2.2 Product Functions entry for ONE functional domain of \
the system described below.

This is a high-level narrative description of what the system does in this \
domain — NOT a list of raw requirements. Write 2–4 sentences of formal, \
third-person technical prose that synthesises the requirements into a coherent \
capability statement a non-technical reader would understand.

Rules:
1. Derive ONLY from the functional requirements provided. Do not add capabilities \
   not evidenced by the list.
2. Do NOT reproduce requirement text verbatim. Synthesise into natural prose.
3. Do NOT use "shall" language — this is a summary, not a requirement.
4. Start the description with the domain name in bold, e.g. **Remote Heating Monitoring:**
5. Return only the paragraph — no preamble, no heading.

PROJECT NAME: {project_name}
DOMAIN: {domain_label}
DOMAIN STATUS: {domain_status}

FUNCTIONAL REQUIREMENTS FOR THIS DOMAIN ({req_count} total):
{domain_reqs}
"""

# --------------- §2.3 User Classes ------------------------------------------

_USER_CLASSES_PROMPT = """\
Write the IEEE 830 §2.3 User Classes and Characteristics section as a \
well-structured paragraph followed by a Markdown table.

Table columns: | User Class | Description | Technical Level | Primary Tasks |

DERIVE ONLY from the conversation transcript below. If only one user class \
is evident, say so. Do not invent roles not mentioned.

TRANSCRIPT EXCERPTS (user turns only):
{user_turns}

STAKEHOLDER REQUIREMENTS:
{stakeholder_reqs}
"""

# --------------- §2.4 Operating Environment ---------------------------------

_OPERATING_ENV_PROMPT = """\
Write the IEEE 830 §2.4 Operating Environment section.

Cover:
(a) Client platforms (mobile OS, desktop OS) — derive from compatibility NFRs.
(b) Network environment (internet-dependent, LAN, offline-capable) — derive from \
    reliability/connectivity requirements.
(c) Physical environment of use (home, office, mobile/remote) — derive from context.

Mark every sentence that is not directly supported by a requirement with [INFERRED].

COMPATIBILITY REQUIREMENTS:
{compat_reqs}

RELIABILITY REQUIREMENTS:
{reliability_reqs}

FUNCTIONAL CONTEXT:
{fr_summary}
"""

# --------------- §2.5 Assumptions & Dependencies ----------------------------

_ASSUMPTIONS_PROMPT = """\
Write the IEEE 830 §2.5 Assumptions and Dependencies section as a numbered list.

Derive assumptions from:
- Requirements that imply third-party services (e.g. push notifications → assumes \
  internet connectivity and a notification service provider)
- Compatibility requirements that imply platform vendor stability
- Security requirements that assume user responsibility for credentials
- Any explicit "I assume" or "I expect" statements in the conversation

Mark every item that is not directly stated with [INFERRED].
Limit to 6–10 items. Be specific.

ALL REQUIREMENTS:
{all_reqs}

USER TURNS (for context):
{user_turns_short}
"""

# --------------- §2.6 User Documentation ------------------------------------

_USER_DOCS_PROMPT = """\
Write the IEEE 830 §2.6 User Documentation section.

This section specifies what documentation or help the system should provide \
to its users. Derive from:
- Any "help", "manual", "documentation", "tutorial" mentions in the conversation
- The technical level of users described (novice users need more help)
- Usability requirements that mention ease-of-use or no-manual-needed goals

If nothing was explicitly elicited, write one short paragraph marked [INFERRED] \
describing what a system of this type and user profile would typically need.

USABILITY REQUIREMENTS:
{usability_reqs}

USER PROFILE CONTEXT:
{user_context}
"""

# --------------- §3.2 External Interface Requirements -----------------------

_INTERFACES_PROMPT = """\
Write the content for ONE IEEE 830 interface sub-section: {interface_type}.

Interface type descriptions:
- User Interfaces: screens, controls, visual layout, accessibility
- Software Interfaces: third-party APIs, operating system services, libraries
- Communication Interfaces: network protocols, data formats, message channels

RULES:
- Derive ONLY from elicited requirements and context below.
- Mark every inference with [INFERRED].
- For items with NO elicited data at all, return exactly this string:
  "[ARCHITECT REVIEW REQUIRED] No {interface_type} details were elicited. \
   The architect must specify: {architect_checklist}"
- Do NOT fabricate specific technology names (e.g. "React Native", "REST API") \
  unless explicitly mentioned.

RELEVANT REQUIREMENTS:
{relevant_reqs}

SYSTEM CONTEXT:
{system_context}
"""

# --------------- §3.5 Design Constraints (stub only) -----------------------

_CONSTRAINTS_STUB = """\
[ARCHITECT REVIEW REQUIRED] Design and implementation constraints were not \
elicited during the stakeholder interview. The system architect must review and \
complete this section before development begins.

Checklist of items to confirm:
1. Programming language(s) and framework(s) to be used
2. Required development methodology (Agile, waterfall, etc.)
3. Target deployment environment (cloud provider, on-premise, device-local)
4. Required compliance standards (GDPR, HIPAA, SOC2, etc.)
5. Third-party component or licensing restrictions
6. Performance budgets or resource constraints (memory, battery, bandwidth)
7. Required build/CI/CD toolchain or approval gates
8. Code quality standards (coverage thresholds, static analysis tools)
"""

# --------------- §3.4 Logical Database Requirements (stub only) -----------

_DATABASE_STUB = """\
[ARCHITECT REVIEW REQUIRED] Logical database requirements were not elicited \
during the stakeholder interview. The architect must determine and document:

1. What persistent data entities the system must store \
   (e.g. user accounts, device states, event logs, schedules)
2. Retention periods for historical data (event logs, energy usage records)
3. Data privacy requirements — which entities contain personal data under GDPR or \
   equivalent regulation
4. Volume estimates: expected rows/records per entity over 12 months
5. Backup and recovery requirements (RPO/RTO)
6. Whether a relational, document, time-series, or other store is appropriate

Note: The following elicited requirements imply data persistence and should \
inform the database design:
{implied_data_reqs}
"""

# ---------------------------------------------------------------------------
# Helper: extract requirement texts by category
# ---------------------------------------------------------------------------

def _reqs_by_category(state: "ConversationState", *categories: str, max_items: int = 30) -> str:
    """Return a numbered list of requirement texts matching any of the given categories."""
    lines = []
    for req in state.requirements.values():
        if req.category in categories or req.req_type.value in categories:
            lines.append(f"- [{req.req_id}] {req.text}")
        if len(lines) >= max_items:
            break
    return "\n".join(lines) if lines else "(none elicited)"


def _all_reqs_text(state: "ConversationState", max_items: int = 40) -> str:
    lines = []
    for req in state.requirements.values():
        lines.append(f"- [{req.req_id}|{req.req_type.value}|{req.category}] {req.text}")
        if len(lines) >= max_items:
            break
    return "\n".join(lines)


def _fr_list_text(state: "ConversationState", max_items: int = 25) -> str:
    from conversation_state import RequirementType
    lines = []
    for req in state.requirements.values():
        if req.req_type == RequirementType.FUNCTIONAL:
            lines.append(f"- [{req.req_id}] {req.text}")
        if len(lines) >= max_items:
            break
    return "\n".join(lines)


def _user_turns_text(state: "ConversationState", max_turns: int = 12, max_chars: int = 150) -> str:
    lines = []
    for turn in state.turns[:max_turns]:
        excerpt = turn.user_message.strip()[:max_chars].replace("\n", " ")
        lines.append(f"Turn {turn.turn_id}: {excerpt}")
    return "\n".join(lines)


def _exclusions_text(state: "ConversationState") -> str:
    from conversation_state import RequirementType
    lines = []
    for req in state.requirements.values():
        if req.req_type == RequirementType.CONSTRAINT and (
            "out of scope" in req.text.lower() or
            "shall not" in req.text.lower() or
            "permanently" in req.text.lower()
        ):
            lines.append(f"- {req.text}")
    return "\n".join(lines) if lines else "(no explicit exclusions recorded)"


def _domain_summary(state: "ConversationState") -> str:
    if state.domain_gate and state.domain_gate.seeded:
        labels = [d.label for d in state.domain_gate.domains.values()
                  if d.status != "excluded"]
        return ", ".join(labels) if labels else "general software system"
    return "general software system"


def _implied_data_reqs(state: "ConversationState") -> str:
    """Find requirements that strongly imply data persistence."""
    keywords = {"history", "log", "record", "store", "save", "schedule",
                "account", "profile", "report", "track", "monitor", "daily"}
    lines = []
    for req in state.requirements.values():
        if any(kw in req.text.lower() for kw in keywords):
            lines.append(f"- [{req.req_id}] {req.text}")
        if len(lines) >= 10:
            break
    return "\n".join(lines) if lines else "(none identified)"


# ---------------------------------------------------------------------------
# SRSCoverageEnricher
# ---------------------------------------------------------------------------

@dataclass
class SRSCoverageEnricher:
    """
    Fills empty IEEE-830 SRS sections using the LLM.

    Call enrich(template, state) BEFORE SRSFormatter.to_markdown().
    The method mutates template in-place and returns a dict of section keys
    that were filled, along with their risk tier (for audit purposes).
    """

    provider: object   # LLMProvider — typed as object to avoid circular import
    temperature: float = 0.1   # Slightly > 0 for natural prose; still deterministic-ish
    skip_high_risk_llm: bool = True   # If True, high-risk sections get stubs, not LLM fill

    def enrich(
        self,
        template: "SRSTemplate",
        state: "ConversationState",
    ) -> dict[str, str]:
        """
        Fill all empty SRS sections.  Returns a dict of {section_key: risk_tier}.

        Parameters
        ----------
        template  : SRSTemplate to mutate in-place
        state     : ConversationState with all elicited data

        Returns
        -------
        dict mapping section key → "low" | "medium" | "high" (risk tier)
        """
        filled: dict[str, str] = {}

        # ── LOW RISK: synthesis from elicited data ────────────────────────

        if not template.section1.scope:
            template.section1.scope = self._fill_scope(state)
            filled["§1.2 Scope"] = "low"

        if not template.section2.product_perspective:
            template.section2.product_perspective = self._fill_perspective(state)
            filled["§2.1 Product Perspective"] = "low"

        if not template.section2.product_functions:
            # One LLM call per confirmed domain — each domain becomes a
            # formal prose description of that product feature.
            template.section2.product_functions = self._fill_product_functions(state)
            filled["§2.2 Product Functions"] = "low"

        if not template.section2.user_classes:
            uc_text = self._fill_user_classes(state)
            # Store as a prose + table block in product_perspective addendum
            # (Section2 has user_classes as list[UserClass], but we can't
            # parse an LLM table into typed objects reliably — so we store
            # the full text as a single UserClass with name="Summary")
            from srs_template import UserClass
            template.section2.user_classes = [
                UserClass(
                    name="User Classes Summary",
                    description=uc_text,
                    proficiency="See description"
                )
            ]
            filled["§2.3 User Classes"] = "low"

        if not template.section2.assumptions:
            template.section2.assumptions = self._fill_assumptions(state)
            filled["§2.5 Assumptions & Dependencies"] = "low"

        # ── MEDIUM RISK: reasonable inference ─────────────────────────────

        # §2.4 Operating Environment — stored as a general_constraints item
        # Section2.general_constraints is list[str] — safe for string sentinels.
        _ENV_SENTINEL = "__operating_environment__"
        env_already_set = any(
            isinstance(c, str) and _ENV_SENTINEL in c
            for c in template.section2.general_constraints
        )
        if not env_already_set:
            env_text = self._fill_operating_environment(state)
            template.section2.general_constraints.insert(0, f"{_ENV_SENTINEL}\n{env_text}")
            filled["§2.4 Operating Environment"] = "medium"

        # §2.6 User Documentation — stored as a general_constraints addendum
        _DOCS_SENTINEL = "__user_documentation__"
        docs_already_set = any(
            isinstance(c, str) and _DOCS_SENTINEL in c
            for c in template.section2.general_constraints
        )
        if not docs_already_set:
            docs_text = self._fill_user_documentation(state)
            template.section2.general_constraints.append(f"{_DOCS_SENTINEL}\n{docs_text}")
            filled["§2.6 User Documentation"] = "medium"

        # §3.2.1 User Interfaces
        if not template.section3.interfaces.user_interfaces:
            ui_text = self._fill_interface(state, "User Interfaces",
                "screen layouts, navigation patterns, accessibility, input methods")
            template.section3.interfaces.user_interfaces = [ui_text]
            filled["§3.2.1 User Interfaces"] = "medium"

        # §3.2.3 Software Interfaces
        if not template.section3.interfaces.software_interfaces:
            sw_text = self._fill_interface(state, "Software Interfaces",
                "operating system APIs, notification services, authentication providers, "
                "third-party data services")
            template.section3.interfaces.software_interfaces = [sw_text]
            filled["§3.2.3 Software Interfaces"] = "medium"

        # §3.2.4 Communication Interfaces
        if not template.section3.interfaces.communication_interfaces:
            comm_text = self._fill_interface(state, "Communication Interfaces",
                "network protocols (HTTP/HTTPS, WebSocket, MQTT), data formats (JSON, XML), "
                "push notification channels, email delivery")
            template.section3.interfaces.communication_interfaces = [comm_text]
            filled["§3.2.4 Communication Interfaces"] = "medium"

        # ── HIGH RISK: stubs only — no LLM fabrication ────────────────────

        # §3.2.2 Hardware Interfaces
        # InterfaceRequirements.hardware_interfaces is list[str] — safe to append strings.
        if not template.section3.interfaces.hardware_interfaces:
            template.section3.interfaces.hardware_interfaces = [
                "[ARCHITECT REVIEW REQUIRED] Hardware interface requirements were not "
                "elicited during the stakeholder interview. The architect must specify:\n"
                "1. Physical sensor or actuator interfaces (e.g. thermostat, door sensor, camera)\n"
                "2. Communication protocols at the hardware level (e.g. Z-Wave, Zigbee, Wi-Fi)\n"
                "3. Power requirements and constraints\n"
                "4. Hardware certifications required (CE, FCC, etc.)"
            ]
            filled["§3.2.2 Hardware Interfaces"] = "high"

        # §3.4 Logical Database Requirements
        # Section3.database is list[str] — the correct field for free-text database notes.
        # Never write strings into design_constraints (that field is list[AnnotatedRequirement]).
        if not template.section3.database:
            template.section3.database = [_implied_data_reqs_stub(state)]
            filled["§3.4 Logical Database Requirements"] = "high"

        # §3.5 Design Constraints
        # design_constraints is list[AnnotatedRequirement] populated by _place_requirement().
        # We MUST NOT write strings into it.  Instead we store the stub text in
        # section1.references — a list[str] field that is always rendered and whose
        # content readers expect to be supplementary notes.  We use a clearly
        # labelled sentinel entry so the formatter can emit it under §3.5.
        _CON_SENTINEL = "DESIGN_CONSTRAINTS_STUB::"
        con_already_set = any(
            isinstance(r, str) and r.startswith(_CON_SENTINEL)
            for r in template.section1.references
        )
        if not con_already_set and not template.section3.design_constraints:
            # No elicited CON requirements AND no stub yet — add stub marker
            template.section1.references.append(_CON_SENTINEL + _CONSTRAINTS_STUB)
            filled["§3.5 Design Constraints"] = "high"

        return filled

    # ------------------------------------------------------------------
    # Low-risk LLM fills (synthesis from elicited data)
    # ------------------------------------------------------------------

    def _fill_scope(self, state: "ConversationState") -> str:
        from conversation_state import RequirementType
        fr_count = sum(1 for r in state.requirements.values()
                       if r.req_type == RequirementType.FUNCTIONAL)
        prompt = _SCOPE_PROMPT.format(
            project_name=state.project_name,
            fr_count=fr_count,
            fr_list=_fr_list_text(state),
            exclusions=_exclusions_text(state),
        )
        return self._call_llm(prompt, max_tokens=400)

    def _fill_perspective(self, state: "ConversationState") -> str:
        prompt = _PERSPECTIVE_PROMPT.format(
            project_name=state.project_name,
            domain_summary=_domain_summary(state),
            all_reqs=_all_reqs_text(state),
        )
        return self._call_llm(prompt, max_tokens=350)

    def _fill_product_functions(self, state: "ConversationState") -> list[str]:
        """
        Generate a formal §2.2 Product Functions entry for each confirmed or
        partially-elicited domain in the domain gate.

        Strategy
        --------
        The domain gate provides the natural grouping of features — each domain
        IS a product feature.  For each non-excluded domain we:
          1. Collect all FRs whose domain_key matches (or fall back to category).
          2. Ask the LLM to write a 2–4 sentence formal prose description
             synthesising those FRs into one coherent capability statement.
          3. Collect results as a list[str] that SRSFormatter renders as
             subsections under §2.2.

        This is low-risk: the LLM is constrained to only the FRs for that
        domain, so it cannot invent capabilities that were not elicited.

        Fallback
        --------
        If the domain gate was never seeded (should not happen post-gate-check
        but handled defensively), falls back to one representative FR per
        unique category key — same as the old Python-only behaviour.
        """
        from conversation_state import RequirementType

        gate = state.domain_gate

        # ── Path A: domain gate seeded — one LLM call per domain ─────────
        if gate is not None and gate.seeded and gate.total > 0:
            results: list[str] = []
            for domain_key, domain in gate.domains.items():
                if domain.status == "excluded":
                    continue  # excluded features do not appear in §2.2

                # Collect FRs for this domain
                domain_reqs = [
                    req for req in state.requirements.values()
                    if (req.req_type == RequirementType.FUNCTIONAL and
                        (req.domain_key == domain_key or
                         req.category == domain_key))
                ]

                if not domain_reqs:
                    # Domain was confirmed but requirements ended up in a
                    # different category key — do a looser match on label words
                    label_words = set(domain.label.lower().split())
                    domain_reqs = [
                        req for req in state.requirements.values()
                        if (req.req_type == RequirementType.FUNCTIONAL and
                            any(w in req.text.lower() for w in label_words
                                if len(w) > 4))
                    ][:8]

                if not domain_reqs:
                    # Nothing matched at all — skip rather than hallucinate
                    continue

                req_lines = "\n".join(
                    f"- [{r.req_id}] {r.text}" for r in domain_reqs
                )
                prompt = _PRODUCT_FUNCTIONS_DOMAIN_PROMPT.format(
                    project_name=state.project_name,
                    domain_label=domain.label,
                    domain_status=domain.status,
                    req_count=len(domain_reqs),
                    domain_reqs=req_lines,
                )
                description = self._call_llm(prompt, max_tokens=200)
                results.append(description)

            if results:
                return results

        # ── Path B: fallback — one representative FR per category key ─────
        category_reps: dict[str, str] = {}
        for req in state.requirements.values():
            if req.req_type != RequirementType.FUNCTIONAL:
                continue
            dk = req.domain_key or req.category
            if dk not in category_reps:
                category_reps[dk] = req.text
        return list(category_reps.values())[:10]

    def _fill_user_classes(self, state: "ConversationState") -> str:
        stakeholder_reqs = _reqs_by_category(state, "stakeholders")
        user_turns = _user_turns_text(state, max_turns=8, max_chars=200)
        prompt = _USER_CLASSES_PROMPT.format(
            user_turns=user_turns,
            stakeholder_reqs=stakeholder_reqs,
        )
        return self._call_llm(prompt, max_tokens=500)

    def _fill_assumptions(self, state: "ConversationState") -> list[str]:
        all_reqs = _all_reqs_text(state)
        user_turns = _user_turns_text(state, max_turns=6, max_chars=120)
        prompt = _ASSUMPTIONS_PROMPT.format(
            all_reqs=all_reqs,
            user_turns_short=user_turns,
        )
        raw = self._call_llm(prompt, max_tokens=500)
        # Split numbered list into individual items
        items = re.split(r"\n\s*\d+\.\s+", "\n" + raw.strip())
        items = [i.strip() for i in items if i.strip()]
        return items if items else [raw]

    # ------------------------------------------------------------------
    # Medium-risk LLM fills (inference, marked [INFERRED])
    # ------------------------------------------------------------------

    def _fill_operating_environment(self, state: "ConversationState") -> str:
        compat_reqs = _reqs_by_category(state, "compatibility")
        reliability_reqs = _reqs_by_category(state, "reliability")
        fr_summary = _fr_list_text(state, max_items=8)
        prompt = _OPERATING_ENV_PROMPT.format(
            compat_reqs=compat_reqs,
            reliability_reqs=reliability_reqs,
            fr_summary=fr_summary,
        )
        return self._call_llm(prompt, max_tokens=400)

    def _fill_user_documentation(self, state: "ConversationState") -> str:
        usability_reqs = _reqs_by_category(state, "usability")
        user_context = _user_turns_text(state, max_turns=5, max_chars=150)
        prompt = _USER_DOCS_PROMPT.format(
            usability_reqs=usability_reqs,
            user_context=user_context,
        )
        return self._call_llm(prompt, max_tokens=350)

    def _fill_interface(
        self,
        state: "ConversationState",
        interface_type: str,
        architect_checklist: str,
    ) -> str:
        # Find requirements relevant to this interface type
        keywords = {
            "User Interfaces":          ["usability", "ui", "screen", "display", "app",
                                         "notification", "mobile", "interface"],
            "Software Interfaces":      ["compatibility", "security_privacy", "api",
                                         "authentication", "maintainability"],
            "Communication Interfaces": ["performance", "reliability", "notification",
                                         "email", "network", "communication"],
        }
        relevant_cats = keywords.get(interface_type, [])
        relevant_reqs_lines = []
        for req in state.requirements.values():
            if (req.category in relevant_cats or
                    any(kw in req.text.lower() for kw in relevant_cats)):
                relevant_reqs_lines.append(f"- [{req.req_id}] {req.text}")
            if len(relevant_reqs_lines) >= 15:
                break
        relevant_reqs = "\n".join(relevant_reqs_lines) or "(none elicited)"
        system_context = (f"Project: {state.project_name}. "
                          f"Domains: {_domain_summary(state)}.")
        prompt = _INTERFACES_PROMPT.format(
            interface_type=interface_type,
            architect_checklist=architect_checklist,
            relevant_reqs=relevant_reqs,
            system_context=system_context,
        )
        return self._call_llm(prompt, max_tokens=400)

    # ------------------------------------------------------------------
    # LLM call wrapper
    # ------------------------------------------------------------------

    def _call_llm(self, user_prompt: str, max_tokens: int = 400) -> str:
        """
        Call the LLM provider with the shared SYSTEM_ROLE and the given user prompt.

        Applies a soft token budget hint in the system message but does not
        enforce it at the API level (providers vary in how they handle max_tokens
        for non-completion endpoints).
        """
        try:
            response = self.provider.chat(
                system_message=_SYSTEM_ROLE,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=self.temperature,
            )
            return response.strip()
        except Exception as exc:
            # Graceful degradation: return a clearly marked stub
            return (
                f"[GENERATION FAILED — {exc}] "
                "This section could not be generated automatically. "
                "Please complete it manually."
            )


# ---------------------------------------------------------------------------
# High-risk stubs (pure Python — no LLM)
# ---------------------------------------------------------------------------

def _implied_data_reqs_stub(state: "ConversationState") -> str:
    implied = _implied_data_reqs(state)
    return _DATABASE_STUB.format(implied_data_reqs=implied)


# ---------------------------------------------------------------------------
# SRSFormatter integration helper
# ---------------------------------------------------------------------------

def render_section2_extras(lines: list[str], template: "SRSTemplate") -> None:
    """
    Called by SRSFormatter._render_section2() to emit the §2.4 and §2.6
    blocks stored as sentinel-prefixed general_constraints items.

    Usage in SRSFormatter._render_section2() — add after §2.5 block:
        from srs_coverage import render_section2_extras
        render_section2_extras(lines, template)
    """
    _ENV_SENTINEL  = "__operating_environment__"
    _DOCS_SENTINEL = "__user_documentation__"

    for item in template.section2.general_constraints:
        if not isinstance(item, str):
            continue
        if item.startswith(_ENV_SENTINEL):
            lines.append("### 2.4 Operating Environment")
            lines.append("")
            lines.append(item[len(_ENV_SENTINEL):].strip())
            lines.append("")
        elif item.startswith(_DOCS_SENTINEL):
            lines.append("### 2.6 User Documentation")
            lines.append("")
            lines.append(item[len(_DOCS_SENTINEL):].strip())
            lines.append("")


def render_section35_stub(lines: list[str], template: "SRSTemplate") -> bool:
    """
    Called by SRSFormatter._render_s35_constraints() to emit the design
    constraints stub when no CON requirements were elicited.

    Returns True if a stub was rendered (so the formatter can skip its
    own _empty_section_note), False otherwise.

    Usage in SRSFormatter._render_s35_constraints():
        from srs_coverage import render_section35_stub
        cons = template.section3.design_constraints
        if cons:
            for ann in cons:
                lines += _render_req_block(ann, self.show_smart)
        elif not render_section35_stub(lines, template):
            lines += _empty_section_note()
        lines.append("")
    """
    _CON_SENTINEL = "DESIGN_CONSTRAINTS_STUB::"
    for ref in template.section1.references:
        if isinstance(ref, str) and ref.startswith(_CON_SENTINEL):
            stub_text = ref[len(_CON_SENTINEL):]
            lines.append(stub_text.strip())
            lines.append("")
            return True
    return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_enricher(provider) -> SRSCoverageEnricher:
    """Create an SRSCoverageEnricher with the given LLM provider."""
    return SRSCoverageEnricher(provider=provider)