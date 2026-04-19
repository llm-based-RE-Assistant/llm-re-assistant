"""
Unit tests for ConversationState.

Tests cover:
- Session creation and defaults
- add_turn() with project name extraction
- add_requirement() with correct ID generation (FR/NFR/CON)
- Requirement counters (functional, nonfunctional, constraint)
- increment_nfr_coverage()
- _extract_project_name() heuristic
- _is_poor_project_name() heuristic
- to_dict() / to_json() serialization
- get_message_history() ordering
"""

import sys
import types
import json

# Stubs — register BEFORE importing conversation_state.
# conversation_state.py imports from:
#   src.components.system_prompt.prompt_architect  (MIN_NFR_PER_CATEGORY, etc.)
#   src.components.system_prompt.utils             (PHASE4_SECTIONS)
#   src.components.domain_discovery.domain_discovery (NFR_CATEGORIES, compute_structural_coverage)

if "src.components.domain_discovery.utils" not in sys.modules:
    _du = types.ModuleType("src.components.domain_discovery.utils")
    _du._DOMAIN_GATE_COVERAGE_FRACTION = 0.8
    sys.modules["src.components.domain_discovery.utils"] = _du

if "src.components.system_prompt.prompt_architect" not in sys.modules:
    _pa = types.ModuleType("src.components.system_prompt.prompt_architect")
    _pa.MIN_NFR_PER_CATEGORY  = 2
    _pa.MIN_FUNCTIONAL_REQS   = 10
    _pa.IEEE830_CATEGORIES    = {
        "functional":       "Functional Requirements",
        "performance":      "Performance",
        "security_privacy": "Security & Privacy",
    }
    _pa.PHASE4_SECTIONS = {"1.2", "2.1", "2.3"}
    sys.modules["src.components.system_prompt.prompt_architect"] = _pa

if "src.components.system_prompt.utils" not in sys.modules:
    _pu = types.ModuleType("src.components.system_prompt.utils")
    _pu.PHASE4_SECTIONS = {"1.2", "2.1", "2.3"}
    sys.modules["src.components.system_prompt.utils"] = _pu

if "src.components.domain_discovery.domain_discovery" not in sys.modules:
    _dd = types.ModuleType("src.components.domain_discovery.domain_discovery")
    _dd.NFR_CATEGORIES = [
        "performance", "security_privacy", "reliability",
        "usability", "maintainability", "compatibility",
    ]
    _dd.compute_structural_coverage = lambda state: set()
    sys.modules["src.components.domain_discovery.domain_discovery"] = _dd

# Now import the real classes
from src.components.conversation_state import (   # noqa: E402
    ConversationState, RequirementType,
    _extract_project_name, _is_poor_project_name,
    create_session,
)


# Helpers

def _state(session_id="sess-001"):
    state = ConversationState(session_id=session_id)
    state.domain_gate = None
    return state


def _add_turn(state, user="Hello", assistant="Hi there!"):
    return state.add_turn(user, assistant)


def _add_fr(state, text="The system shall allow user login with email and password."):
    return state.add_requirement(RequirementType.FUNCTIONAL, text, "authentication")


def _add_nfr(state, text="The system shall respond within 200ms for 95% of API calls."):
    return state.add_requirement(RequirementType.NON_FUNCTIONAL, text, "performance")


def _add_con(state, text="The system shall be deployed exclusively on AWS infrastructure."):
    return state.add_requirement(RequirementType.CONSTRAINT, text, "constraints")


# Creation & defaults

class TestConversationStateCreation:

    def test_create_session_returns_state(self):
        state = create_session("abc-123")
        assert isinstance(state, ConversationState)
        assert state.session_id == "abc-123"

    def test_default_project_name(self):
        assert _state().project_name == "Unknown Project"

    def test_default_turn_count_zero(self):
        assert _state().turn_count == 0

    def test_default_total_requirements_zero(self):
        assert _state().total_requirements == 0

    def test_default_nfr_coverage_empty(self):
        assert _state().nfr_coverage == {}

    def test_session_complete_defaults_false(self):
        assert _state().session_complete is False


# add_turn()

class TestAddTurn:

    def test_adds_turn(self):
        state = _state()
        _add_turn(state)
        assert state.turn_count == 1

    def test_turn_count_increments(self):
        state = _state()
        _add_turn(state)
        _add_turn(state, "Second message", "Second reply")
        assert state.turn_count == 2

    def test_turn_has_correct_messages(self):
        state = _state()
        state.add_turn("user msg", "assistant msg")
        assert state.turns[0].user_message == "user msg"
        assert state.turns[0].assistant_message == "assistant msg"

    def test_first_turn_extracts_project_name(self):
        state = _state()
        state.add_turn("I want to build a Library Management System", "Great!")
        assert state.project_name != "Unknown Project"

    def test_project_name_not_overwritten_on_second_turn(self):
        state = _state()
        state.add_turn("I want to build a Library Management System", "Great!")
        first_name = state.project_name
        state.add_turn("I also need inventory tracking features.", "Understood!")
        assert state.project_name == first_name


# add_requirement()

class TestAddRequirement:

    def test_functional_gets_fr_id(self):
        state = _state()
        _add_turn(state)
        req = _add_fr(state)
        assert req.req_id.startswith("FR-")

    def test_nfr_gets_nfr_id(self):
        state = _state()
        _add_turn(state)
        req = _add_nfr(state)
        assert req.req_id.startswith("NFR-")

    def test_constraint_gets_con_id(self):
        state = _state()
        _add_turn(state)
        req = _add_con(state)
        assert req.req_id.startswith("CON-")

    def test_ids_increment(self):
        state = _state()
        _add_turn(state)
        r1 = _add_fr(state, "The system shall allow user login.")
        r2 = _add_fr(state, "The system shall allow user logout with session cleanup.")
        assert r1.req_id == "FR-001"
        assert r2.req_id == "FR-002"

    def test_requirement_stored_in_dict(self):
        state = _state()
        _add_turn(state)
        req = _add_fr(state)
        assert req.req_id in state.requirements

    def test_req_added_to_latest_turn(self):
        state = _state()
        _add_turn(state)
        req = _add_fr(state)
        assert req.req_id in state.turns[-1].requirements_added


# Requirement type counters

class TestRequirementCounters:

    def test_functional_count(self):
        state = _state()
        _add_turn(state)
        _add_fr(state, "The system shall allow user registration with email verification.")
        _add_fr(state, "The system shall allow password reset via email link.")
        assert state.functional_count == 2

    def test_nonfunctional_count(self):
        state = _state()
        _add_turn(state)
        _add_nfr(state)
        assert state.nonfunctional_count == 1

    def test_constraint_count(self):
        state = _state()
        _add_turn(state)
        _add_con(state)
        assert state.constraint_count == 1

    def test_total_requirements(self):
        state = _state()
        _add_turn(state)
        _add_fr(state, "The system shall allow user login.")
        _add_nfr(state, "The system shall respond within 200ms for all requests.")
        _add_con(state, "The system shall comply with GDPR data retention policies.")
        assert state.total_requirements == 3

    def test_mixed_types_counted_separately(self):
        state = _state()
        _add_turn(state)
        _add_fr(state, "The system shall support multi-language interfaces.")
        _add_nfr(state, "The system shall achieve 99.9% uptime measured quarterly.")
        _add_con(state, "The system shall use only open-source dependencies.")
        assert state.functional_count == 1
        assert state.nonfunctional_count == 1
        assert state.constraint_count == 1


# NFR coverage

class TestNFRCoverage:

    def test_increment_starts_at_zero(self):
        state = _state()
        state.increment_nfr_coverage("performance")
        assert state.nfr_coverage["performance"] == 1

    def test_increment_accumulates(self):
        state = _state()
        state.increment_nfr_coverage("performance")
        state.increment_nfr_coverage("performance")
        assert state.nfr_coverage["performance"] == 2

    def test_multiple_categories_independent(self):
        state = _state()
        state.increment_nfr_coverage("performance")
        state.increment_nfr_coverage("security_privacy")
        assert state.nfr_coverage["performance"] == 1
        assert state.nfr_coverage["security_privacy"] == 1


# _extract_project_name()

class TestExtractProjectName:

    def test_extracts_from_build_pattern(self):
        name = _extract_project_name("I want to build a Library Management System")
        assert len(name) > 0
        assert name != "Unknown Project"

    def test_extracts_quoted_name(self):
        name = _extract_project_name('We are building "SmartHome Controller" for IoT')
        assert "SmartHome" in name or "Controller" in name

    def test_falls_back_to_first_line(self):
        name = _extract_project_name("inventory tracking app for warehouses")
        assert len(name) > 0

    def test_handles_empty_string(self):
        name = _extract_project_name("")
        assert isinstance(name, str)


# _is_poor_project_name()

class TestIsPoorProjectName:

    def test_unknown_project_is_poor(self):
        assert _is_poor_project_name("Unknown Project") is True

    def test_unnamed_project_is_poor(self):
        assert _is_poor_project_name("Unnamed Project") is True

    def test_hi_prefix_is_poor(self):
        assert _is_poor_project_name("hi there, I want to build") is True

    def test_long_name_is_poor(self):
        assert _is_poor_project_name("A" * 41) is True

    def test_good_name_is_not_poor(self):
        assert _is_poor_project_name("Library Management System") is False

    def test_empty_string_is_poor(self):
        assert _is_poor_project_name("") is True

    def test_none_is_poor(self):
        assert _is_poor_project_name(None) is True


# Serialization

class TestSerialization:

    def test_to_dict_contains_session_id(self):
        state = _state("test-session")
        from src.components.domain_discovery.domain_gate import DomainGate
        state.domain_gate = DomainGate()
        assert state.to_dict()["session_id"] == "test-session"

    def test_to_dict_contains_turns_and_requirements(self):
        state = _state()
        from src.components.domain_discovery.domain_gate import DomainGate
        state.domain_gate = DomainGate()
        _add_turn(state)
        _add_fr(state, "The system shall allow users to view their profile.")
        d = state.to_dict()
        assert len(d["turns"]) == 1
        assert len(d["requirements"]) == 1

    def test_to_json_is_valid_json(self):
        state = _state()
        from src.components.domain_discovery.domain_gate import DomainGate
        state.domain_gate = DomainGate()
        _add_turn(state)
        parsed = json.loads(state.to_json())
        assert parsed["session_id"] == state.session_id


# get_message_history()

class TestMessageHistory:

    def test_alternates_user_assistant(self):
        state = _state()
        state.add_turn("user msg 1", "assistant msg 1")
        state.add_turn("user msg 2", "assistant msg 2")
        history = state.get_message_history()
        assert history[0] == {"role": "user",      "content": "user msg 1"}
        assert history[1] == {"role": "assistant",  "content": "assistant msg 1"}
        assert history[2] == {"role": "user",      "content": "user msg 2"}
        assert history[3] == {"role": "assistant",  "content": "assistant msg 2"}

    def test_empty_history_returns_empty_list(self):
        assert _state().get_message_history() == []