from __future__ import annotations
import re
from dataclasses import dataclass
from src.components.conversation_state import RequirementType
from src.components.srs_template import UserClass
from src.components.system_prompt.utils import (
    SYSTEM_ROLE,
    SCOPE_PROMPT,
    PERSPECTIVE_PROMPT,
    PRODUCT_FUNCTIONS_DOMAIN_PROMPT,
    USER_CLASSES_PROMPT,
    GENERAL_CONSTRAINTS_PROMPT,
    ASSUMPTIONS_PROMPT,
    INTERFACES_PROMPT,
    CONSTRAINTS_STUB,
    DATABASE_STUB
)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.components.conversation_state import ConversationState
    from src.components.srs_template import SRSTemplate


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


def _brief_block(state: "ConversationState") -> str:
    """Render the project brief as a labelled block for injection into enricher prompts.
    Returns empty string when no brief was collected (srs_only / upload flows).
    """
    brief = getattr(state, "project_brief", {})
    if not brief:
        return ""
    LABELS = {
        "user_classes":       "User classes",
        "core_features":      "Core features",
        "scale_and_context":  "Scale / context",
        "key_constraints":    "Known constraints",
        "integration_points": "Integration points",
        "out_of_scope":       "Out of scope",
    }
    lines = ["PROJECT BRIEF (confirmed with customer before elicitation):"]
    for key, label in LABELS.items():
        value = brief.get(key, "")
        if value:
            lines.append(f"  {label:<22}: {value}")
    return "\n".join(lines)


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
        Fill all empty SRS sections.

        IT8 CONSUMER-FIRST STRATEGY:
        1. For every section in PHASE4_SECTIONS, check state.srs_section_content first.
           If content exists (customer answered during Phase 4), use it directly.
        2. For sections still empty after Phase 4 content applied, fall back to
           LLM synthesis (low-risk sections only).
        3. High-risk sections (hardware interfaces, DB reqs, design constraints)
           always get stubs — never LLM fabrication.

        Returns dict mapping section label → source ("phase4" | "llm_synthesis" | "stub")
        """
        filled: dict[str, str] = {}
        sec = state.srs_section_content  # shorthand

        # ── PHASE 4 CONTENT: apply customer-provided section content first ───

        # §1.2 Scope
        if not template.section1.scope:
            if sec.get("1.2"):
                template.section1.scope = sec["1.2"]
                filled["§1.2 Scope"] = "phase4"
            else:
                template.section1.scope = self._fill_scope(state)
                filled["§1.2 Scope"] = "llm_synthesis"

        # §2.1 Product Perspective
        if not template.section2.product_perspective:
            if sec.get("2.1"):
                template.section2.product_perspective = sec["2.1"]
                filled["§2.1 Product Perspective"] = "phase4"
            else:
                template.section2.product_perspective = self._fill_perspective(state)
                filled["§2.1 Product Perspective"] = "llm_synthesis"

        # §2.2 Product Functions — always LLM synthesis (not a Phase 4 section)
        if not template.section2.product_functions:
            template.section2.product_functions = self._fill_product_functions(state)
            filled["§2.2 Product Functions"] = "llm_synthesis"

        # §2.3 User Classes
        if not template.section2.user_classes:
            if sec.get("2.3"):
                uc_text = sec["2.3"]
                filled["§2.3 User Classes"] = "phase4"
            else:
                uc_text = self._fill_user_classes(state)
                filled["§2.3 User Classes"] = "llm_synthesis"
            template.section2.user_classes = [
                UserClass(name="User Classes Summary", description=uc_text,
                          proficiency="See description")
            ]
        
        # §2.4 General Constraints — always LLM synthesis
        if not template.section2.general_constraints:
            if sec.get("2.4"):
                gc_text = sec["2.4"]
                filled["§2.4 General Constraints"] = "phase4"
            else:
                gc_text = self._fill_general_constraints(state)
                filled["§2.4 General Constraints"] = "llm_synthesis"
            template.section2.general_constraints = [gc_text]

        # §2.5 Assumptions & Dependencies
        if not template.section2.assumptions:
            if sec.get("2.5"):
                # Phase 4 content is already prose; split into list items if possible
                raw = sec["2.5"]
                items = re.split(r"\n\s*\d+\.\s+", "\n" + raw.strip())
                items = [i.strip() for i in items if i.strip()]
                template.section2.assumptions = items if items else [raw]
                filled["§2.5 Assumptions & Dependencies"] = "phase4"
            else:
                template.section2.assumptions = self._fill_assumptions(state)
                filled["§2.5 Assumptions & Dependencies"] = "llm_synthesis"

        # §3.1.1 User Interfaces
        if not template.section3.interfaces.user_interfaces:
            if sec.get("3.1.1"):
                template.section3.interfaces.user_interfaces = [sec["3.1.1"]]
                filled["§3.1.1 User Interfaces"] = "phase4"
            else:
                ui_text = self._fill_interface(state, "User Interfaces",
                    "screen layouts, navigation patterns, accessibility, input methods")
                template.section3.interfaces.user_interfaces = [ui_text]
                filled["§3.1.1 User Interfaces"] = "llm_synthesis"

        # §3.1.2 Hardware Interfaces — always stub (high risk)
        if not template.section3.interfaces.hardware_interfaces:
            template.section3.interfaces.hardware_interfaces = [
                "[ARCHITECT REVIEW REQUIRED] Hardware interface requirements were not "
                "elicited during the stakeholder interview. The architect must specify:\n"
                "1. Physical sensor or actuator interfaces (e.g. thermostat, door sensor, camera)\n"
                "2. Communication protocols at the hardware level (e.g. Z-Wave, Zigbee, Wi-Fi)\n"
                "3. Power requirements and constraints\n"
                "4. Hardware certifications required (CE, FCC, etc.)"
            ]
            filled["§3.1.2 Hardware Interfaces"] = "stub"

        # §3.1.3 Software Interfaces
        if not template.section3.interfaces.software_interfaces:
            if sec.get("3.1.3"):
                template.section3.interfaces.software_interfaces = [sec["3.1.3"]]
                filled["§3.1.3 Software Interfaces"] = "phase4"
            else:
                sw_text = self._fill_interface(state, "Software Interfaces",
                    "operating system APIs, notification services, authentication providers, "
                    "third-party data services")
                template.section3.interfaces.software_interfaces = [sw_text]
                filled["§3.1.3 Software Interfaces"] = "llm_synthesis"

        # §3.1.4 Communication Interfaces
        if not template.section3.interfaces.communication_interfaces:
            if sec.get("3.1.4"):
                template.section3.interfaces.communication_interfaces = [sec["3.1.4"]]
                filled["§3.1.4 Communication Interfaces"] = "phase4"
            else:
                comm_text = self._fill_interface(state, "Communication Interfaces",
                    "network protocols (HTTP/HTTPS, WebSocket, MQTT), data formats (JSON, XML), "
                    "push notification channels, email delivery")
                template.section3.interfaces.communication_interfaces = [comm_text]
                filled["§3.1.4 Communication Interfaces"] = "llm_synthesis"

        # §3.4 Logical Database Requirements — always stub (high risk)
        if not template.section3.database:
            template.section3.database = [_implied_data_reqs_stub(state)]
            filled["§3.4 Logical Database Requirements"] = "stub"

        # §3.5 Design Constraints — stub if no CON requirements elicited
        _CON_SENTINEL = "DESIGN_CONSTRAINTS_STUB::"
        con_already_set = any(
            isinstance(r, str) and r.startswith(_CON_SENTINEL)
            for r in template.section1.references
        )
        if not con_already_set and not template.section3.design_constraints:
            template.section1.references.append(_CON_SENTINEL + CONSTRAINTS_STUB)
            filled["§3.5 Design Constraints"] = "stub"

        return filled

    # ------------------------------------------------------------------
    # Low-risk LLM fills (synthesis from elicited data)
    # ------------------------------------------------------------------

    def _fill_scope(self, state: "ConversationState") -> str:
        fr_count = sum(1 for r in state.requirements.values()
                       if r.req_type == RequirementType.FUNCTIONAL)
        prompt = SCOPE_PROMPT.format(
            project_name=state.project_name,
            project_brief=_brief_block(state),
            fr_count=fr_count,
            fr_list=_fr_list_text(state),
            exclusions=_exclusions_text(state),
        )
        return self._call_llm(prompt, max_tokens=400)

    def _fill_perspective(self, state: "ConversationState") -> str:
        prompt = PERSPECTIVE_PROMPT.format(
            project_name=state.project_name,
            project_brief=_brief_block(state),
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
                prompt = PRODUCT_FUNCTIONS_DOMAIN_PROMPT.format(
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
        prompt = USER_CLASSES_PROMPT.format(
            project_brief=_brief_block(state),
            user_turns=user_turns,
            stakeholder_reqs=stakeholder_reqs,
        )
        return self._call_llm(prompt, max_tokens=500)
    
    def _fill_general_constraints(self, state: "ConversationState") -> str:
        all_reqs = _all_reqs_text(state)
        prompt = GENERAL_CONSTRAINTS_PROMPT.format(
            project_brief=_brief_block(state),
            all_reqs=all_reqs,
        )
        raw = self._call_llm(prompt, max_tokens=500)
        items = re.split(r"\n\s*\d+\.\s+", "\n" + raw.strip())
        items = [i.strip() for i in items if i.strip()]
        return "\n".join(items) if items else raw

    def _fill_assumptions(self, state: "ConversationState") -> list[str]:
        all_reqs = _all_reqs_text(state)
        user_turns = _user_turns_text(state, max_turns=6, max_chars=120)
        prompt = ASSUMPTIONS_PROMPT.format(
            project_brief=_brief_block(state),
            all_reqs=all_reqs,
            user_turns_short=user_turns,
        )
        raw = self._call_llm(prompt, max_tokens=500)
        items = re.split(r"\n\s*\d+\.\s+", "\n" + raw.strip())
        items = [i.strip() for i in items if i.strip()]
        return items if items else [raw]

    # ------------------------------------------------------------------
    # Medium-risk LLM fills (inference, marked [INFERRED])
    # ------------------------------------------------------------------
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
        system_context = (
            f"Project: {state.project_name}. "
            f"Domains: {_domain_summary(state)}."
        )
        brief = _brief_block(state)
        prompt = INTERFACES_PROMPT.format(
            interface_type=interface_type,
            architect_checklist=architect_checklist,
            relevant_reqs=relevant_reqs,
            system_context=system_context,
            project_brief=brief,
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
                system_message=SYSTEM_ROLE,
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
    return DATABASE_STUB.format(implied_data_reqs=implied)


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