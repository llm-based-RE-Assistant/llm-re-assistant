from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from src.components.system_prompt.utils import (
    MIN_NFR_PER_CATEGORY,
    MANDATORY_NFR_CATEGORIES,
    ELICITATION_FR_ROLE,
    PHASE0_SCOPE_ROLE,
    ELICITATION_IEEE_ROLE,
    ELICITATION_NFR_ROLE,
    COMMS_STYLE,
    REQ_FORMAT,
    SEC_FORMAT,
    SRS_ONLY_ROLE,
    IEEE830_CATEGORIES,
    MIN_FUNCTIONAL_REQS
)
from src.components.system_prompt.prompt_context import (
    _build_domain_context,
    _build_nfr_context,
    _build_ieee_section_context,
    _build_requirements_summary,
    _build_scope_context,
    determine_elicitation_phase,
    _build_brief_for_ieee,
    ElicitationPhase,
    TaskType
)
if TYPE_CHECKING:
    from src.components.conversation_state import ConversationState


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
        project_name = state.project_name or "(project name is not defined yet)"

        if phase == "scope":
            scope_ctx = _build_scope_context(state)
            role = PHASE0_SCOPE_ROLE.format(
                project_name=project_name,
                scope_context=scope_ctx,
            )
            phase_label = "=== CURRENT PHASE 0: PROJECT SCOPE CLARIFICATION ==="

        elif phase == "fr":
            domain_ctx = _build_domain_context(state)
            role = ELICITATION_FR_ROLE.format(
                project_name=project_name,
                comms_style=COMMS_STYLE,
                req_format=REQ_FORMAT,
            )
            phase_label = f"=== CURRENT PHASE 1: ELICIT AND AUTHOR REQUIREMENTS FOR CURRENT FEATURE ===\n{domain_ctx}"

        elif phase == "nfr":
            nfr_ctx = _build_nfr_context(state)
            role = ELICITATION_NFR_ROLE.format(
                project_name=project_name,
                nfr_context=nfr_ctx,
                min_nfr=MIN_NFR_PER_CATEGORY,
                comms_style=COMMS_STYLE,
                req_format=REQ_FORMAT,
            )
            phase_label = "=== CURRENT PHASE 2: NON-FUNCTIONAL REQUIREMENTS — GAP COVERAGE ==="

        else:  # ieee
            sec_ctx = _build_ieee_section_context(state)
            project_brief = _build_brief_for_ieee(state)
            role = ELICITATION_IEEE_ROLE.format(
                project_name=project_name,
                section_context=sec_ctx,
                comms_style=COMMS_STYLE,
                sec_format=SEC_FORMAT,
                project_brief=project_brief
            )
            phase_label = "=== CURRENT PHASE 3: IEEE-830 DOCUMENTATION SECTIONS ==="

        parts = [
            f"=== ROLE & INSTRUCTIONS ===\n{role}",
            f"{phase_label}",
        ]
        if self.extra_context:
            parts.append(f"=== ADDITIONAL CONTEXT ===\n{self.extra_context}")
        return "\n\n".join(parts)

    def _build_srs_only_message(self, state: "ConversationState") -> str:
        sec_ctx     = _build_ieee_section_context(state)
        req_summary = _build_requirements_summary(state)
        role = SRS_ONLY_ROLE.format(
            project_name=state.project_name,
            section_context=sec_ctx,
            comms_style=COMMS_STYLE,
            req_format=REQ_FORMAT,
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