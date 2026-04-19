"""
Tests for src/components/system_prompt/prompt_architect.py

Uses the real PromptArchitect — no MagicMock stub for this module.
sys.modules stubs are registered before any project import to prevent
import-chain errors.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock
import pytest

# ---------------------------------------------------------------------------
# Safe module cache clearing — must happen before imports
# Clears any MagicMock stub for prompt_architect registered by earlier tests
# Uses pop() instead of del to avoid KeyError if key is absent
# ---------------------------------------------------------------------------
_to_clear = [
    "src.components.srs_coverage",
    "src.components.system_prompt.prompt_architect",
    "src.components.system_prompt.prompt_context",
    "src.components.system_prompt.utils",
    "src.components.domain_discovery.domain_discovery",
    "src.components.conversation_manager.conversation_manager",
    "src.components.conversation_manager.llm_provider",
]
for _key in _to_clear:
    sys.modules.pop(_key, None)
# ---------------------------------------------------------------------------
# sys.modules stubs — must come BEFORE any project import
# ---------------------------------------------------------------------------

def _stub_module(name: str, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


if "src.components.domain_discovery.utils" not in sys.modules:
    _stub_module(
        "src.components.domain_discovery.utils",
        NFR_CATEGORIES={
            "performance": "Performance",
            "usability": "Usability",
            "security_privacy": "Security & Privacy",
            "reliability": "Reliability",
            "compatibility": "Compatibility",
            "maintainability": "Maintainability",
            "availability": "Availability",
        },
        COVERAGE_CHECKLIST={},
        DOMAIN_SUB_DIMENSIONS=["data", "actions", "constraints", "automation", "edge_cases"],
        _DOMAIN_GATE_COVERAGE_FRACTION=0.80,
        GapSeverity=MagicMock(),
        STRUCTURAL_CATEGORIES={},
        MIN_FUNCTIONAL_FOR_NFR=10,
        _SEED_PROMPT="",
        _RESEED_PROMPT="",
        _NFR_CLASSIFY_PROMPT="",
        _SUBDIM_CLASSIFY_PROMPT="",
        _DOMAIN_MATCH_PROMPT="",
        _DECOMPOSE_PROMPT="",
        _PROJECT_NAME_PROMPT="",
        _COMPLEXITY_PROMPT="",
        _DOMAIN_TEMPLATE_PROMPT="",
        NFR_PROBE_HINTS={},
    )

# ---------------------------------------------------------------------------
# Now safe to import the REAL project modules
# ---------------------------------------------------------------------------

from src.components.conversation_manager.llm_provider import StubProvider
from src.components.system_prompt.prompt_architect import PromptArchitect
from src.components.system_prompt.utils import (
    IEEE830_CATEGORIES, MANDATORY_NFR_CATEGORIES, MIN_FUNCTIONAL_REQS,
    MIN_NFR_PER_CATEGORY, PHASE4_SECTIONS,
)
from src.components.system_prompt.prompt_context import determine_elicitation_phase
from src.components.conversation_state import ConversationState, RequirementType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(functional=0, nfr_coverage=None, phase4_covered=None,
           domain_gate=None, project_name="TestProject"):
    s = ConversationState(session_id="s1", project_name=project_name)
    s.domain_gate = domain_gate
    if nfr_coverage:
        s.nfr_coverage = nfr_coverage
    if phase4_covered:
        s.phase4_sections_covered = phase4_covered
    s.add_turn("setup", "ok")
    for i in range(functional):
        s.add_requirement(RequirementType.FUNCTIONAL,
                          f"The system shall do task {i} within 2 seconds.", "auth")
    return s


def _satisfied_gate():
    gate = MagicMock()
    gate.is_satisfied = True
    gate.seeded = True
    gate.domains = {}
    gate.done_count = 0
    gate.total = 0
    return gate


def _unsatisfied_gate():
    gate = MagicMock()
    gate.is_satisfied = False
    gate.seeded = True
    gate.domains = {}
    gate.done_count = 0
    gate.total = 0
    return gate


def _nfr_met():
    return {k: MIN_NFR_PER_CATEGORY for k in MANDATORY_NFR_CATEGORIES}


def _all_phase4():
    return {sid for sid, *_ in PHASE4_SECTIONS}


# ---------------------------------------------------------------------------
# PromptArchitect — defaults and initialisation
# ---------------------------------------------------------------------------

class TestDefaults:
    def test_default_task_type(self):
        assert PromptArchitect().task_type == "elicitation"

    def test_default_extra_context_empty(self):
        assert PromptArchitect().extra_context == ""

    def test_custom_task_type(self):
        assert PromptArchitect(task_type="srs_only").task_type == "srs_only"

    def test_custom_extra_context(self):
        a = PromptArchitect(extra_context="Extra info")
        assert a.extra_context == "Extra info"


# ---------------------------------------------------------------------------
# build_system_message — FR phase
# ---------------------------------------------------------------------------

class TestBuildSystemMessageFRPhase:
    def test_returns_string(self):
        a = PromptArchitect()
        s = _state(domain_gate=_unsatisfied_gate())
        result = a.build_system_message(s)
        assert isinstance(result, str)

    def test_contains_role_header(self):
        a = PromptArchitect()
        s = _state(domain_gate=_unsatisfied_gate())
        result = a.build_system_message(s)
        assert "ROLE" in result.upper()

    def test_contains_project_name(self):
        a = PromptArchitect()
        s = _state(domain_gate=_unsatisfied_gate(), project_name="LibrarySystem")
        result = a.build_system_message(s)
        assert "LibrarySystem" in result

    def test_fr_phase_label_present(self):
        a = PromptArchitect()
        s = _state(domain_gate=_unsatisfied_gate())
        result = a.build_system_message(s)
        assert "PHASE 1" in result or "ELICIT" in result.upper()

    def test_extra_context_injected(self):
        a = PromptArchitect(extra_context="IMPORTANT: Focus on security.")
        s = _state(domain_gate=_unsatisfied_gate())
        result = a.build_system_message(s)
        assert "IMPORTANT: Focus on security." in result

    def test_no_extra_context_section_when_empty(self):
        a = PromptArchitect(extra_context="")
        s = _state(domain_gate=_unsatisfied_gate())
        result = a.build_system_message(s)
        assert "ADDITIONAL CONTEXT" not in result


# ---------------------------------------------------------------------------
# build_system_message — NFR phase
# ---------------------------------------------------------------------------

class TestBuildSystemMessageNFRPhase:
    def test_nfr_phase_label_present(self):
        a = PromptArchitect()
        s = _state(functional=MIN_FUNCTIONAL_REQS, domain_gate=_satisfied_gate(), nfr_coverage={})
        result = a.build_system_message(s)
        assert "PHASE 2" in result or "NON-FUNCTIONAL" in result.upper()

    def test_nfr_context_in_message(self):
        a = PromptArchitect()
        s = _state(functional=MIN_FUNCTIONAL_REQS, domain_gate=_satisfied_gate(), nfr_coverage={})
        result = a.build_system_message(s)
        assert "Performance" in result or "NFR" in result.upper()

    def test_returns_string(self):
        a = PromptArchitect()
        s = _state(functional=MIN_FUNCTIONAL_REQS, domain_gate=_satisfied_gate(), nfr_coverage={})
        assert isinstance(a.build_system_message(s), str)


# ---------------------------------------------------------------------------
# build_system_message — IEEE phase
# ---------------------------------------------------------------------------

class TestBuildSystemMessageIEEEPhase:
    def test_ieee_phase_label_present(self):
        a = PromptArchitect()
        s = _state(functional=MIN_FUNCTIONAL_REQS, domain_gate=_satisfied_gate(),
                   nfr_coverage=_nfr_met(), phase4_covered=set())
        result = a.build_system_message(s)
        assert "PHASE 3" in result or "IEEE" in result.upper()

    def test_returns_string(self):
        a = PromptArchitect()
        s = _state(functional=MIN_FUNCTIONAL_REQS, domain_gate=_satisfied_gate(),
                   nfr_coverage=_nfr_met())
        assert isinstance(a.build_system_message(s), str)


# ---------------------------------------------------------------------------
# build_system_message — srs_only task type
# ---------------------------------------------------------------------------

class TestBuildSRSOnlyMessage:
    def test_contains_srs_task_label(self):
        a = PromptArchitect(task_type="srs_only")
        result = a.build_system_message(_state())
        assert "SRS" in result.upper()

    def test_contains_role_header(self):
        a = PromptArchitect(task_type="srs_only")
        result = a.build_system_message(_state())
        assert "ROLE" in result.upper()

    def test_returns_string(self):
        a = PromptArchitect(task_type="srs_only")
        assert isinstance(a.build_system_message(_state()), str)

    def test_requirements_section_present_when_reqs_exist(self):
        a = PromptArchitect(task_type="srs_only")
        result = a.build_system_message(_state(functional=5))
        assert "PROVIDED REQUIREMENTS" in result or "REQUIREMENTS" in result

    def test_no_requirements_section_when_empty(self):
        a = PromptArchitect(task_type="srs_only")
        s = ConversationState(session_id="s1")
        s.domain_gate = None
        result = a.build_system_message(s)
        assert "PROVIDED REQUIREMENTS" not in result


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

class TestPublicHelpers:
    def test_get_category_labels_returns_dict(self):
        assert isinstance(PromptArchitect().get_category_labels(), dict)

    def test_get_category_labels_matches_ieee830(self):
        assert PromptArchitect().get_category_labels() == dict(IEEE830_CATEGORIES)

    def test_get_category_labels_is_copy(self):
        a = PromptArchitect()
        labels = a.get_category_labels()
        labels["injected"] = "bad"
        assert "injected" not in a.get_category_labels()

    def test_get_mandatory_nfr_categories(self):
        result = PromptArchitect().get_mandatory_nfr_categories()
        assert isinstance(result, frozenset)
        assert result == MANDATORY_NFR_CATEGORIES

    def test_get_min_functional_reqs(self):
        assert PromptArchitect().get_min_functional_reqs() == MIN_FUNCTIONAL_REQS

    def test_is_srs_permitted_true(self):
        a = PromptArchitect()
        s = _state(functional=MIN_FUNCTIONAL_REQS, domain_gate=_satisfied_gate(),
                   nfr_coverage=_nfr_met(), phase4_covered=_all_phase4())
        assert a.is_srs_generation_permitted(s) is True

    def test_is_srs_permitted_false_insufficient_fr(self):
        a = PromptArchitect()
        s = _state(functional=0, domain_gate=None)
        assert a.is_srs_generation_permitted(s) is False

    def test_is_srs_permitted_false_unsatisfied_gate(self):
        a = PromptArchitect()
        s = _state(functional=MIN_FUNCTIONAL_REQS, domain_gate=_unsatisfied_gate(),
                   nfr_coverage=_nfr_met(), phase4_covered=_all_phase4())
        assert a.is_srs_generation_permitted(s) is False


# ---------------------------------------------------------------------------
# get_current_phase
# ---------------------------------------------------------------------------

class TestGetCurrentPhase:
    def test_srs_only_always_ieee(self):
        assert PromptArchitect(task_type="srs_only").get_current_phase(_state()) == "ieee"

    def test_elicitation_fr_when_gate_not_satisfied(self):
        a = PromptArchitect(task_type="elicitation")
        assert a.get_current_phase(_state(domain_gate=_unsatisfied_gate())) == "fr"

    def test_elicitation_nfr_when_gate_satisfied_no_nfr(self):
        a = PromptArchitect(task_type="elicitation")
        s = _state(functional=MIN_FUNCTIONAL_REQS, domain_gate=_satisfied_gate(), nfr_coverage={})
        assert a.get_current_phase(s) == "nfr"

    def test_elicitation_ieee_when_all_satisfied(self):
        a = PromptArchitect(task_type="elicitation")
        s = _state(functional=MIN_FUNCTIONAL_REQS, domain_gate=_satisfied_gate(),
                   nfr_coverage=_nfr_met())
        assert a.get_current_phase(s) == "ieee"


# ---------------------------------------------------------------------------
# determine_elicitation_phase (direct)
# ---------------------------------------------------------------------------

class TestDetermineElicitationPhase:
    def test_fr_when_gate_none_and_no_nfr(self):
        s = _state(domain_gate=None, nfr_coverage={})
        assert determine_elicitation_phase(s) == "nfr"

    def test_fr_when_gate_not_satisfied(self):
        s = _state(domain_gate=_unsatisfied_gate())
        assert determine_elicitation_phase(s) == "fr"

    def test_nfr_when_gate_satisfied_nfr_empty(self):
        s = _state(domain_gate=_satisfied_gate(), nfr_coverage={})
        assert determine_elicitation_phase(s) == "nfr"

    def test_ieee_when_all_gates_pass(self):
        s = _state(functional=MIN_FUNCTIONAL_REQS, domain_gate=_satisfied_gate(),
                   nfr_coverage=_nfr_met())
        assert determine_elicitation_phase(s) == "ieee"

    def test_nfr_when_one_category_short(self):
        coverage = _nfr_met()
        first = next(iter(MANDATORY_NFR_CATEGORIES))
        coverage[first] = MIN_NFR_PER_CATEGORY - 1
        s = _state(domain_gate=_satisfied_gate(), nfr_coverage=coverage)
        assert determine_elicitation_phase(s) == "nfr"

    def test_gate_none_treated_as_domain_ok(self):
        s = _state(domain_gate=None, nfr_coverage=_nfr_met())
        assert determine_elicitation_phase(s) == "ieee"