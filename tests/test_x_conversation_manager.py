"""
Tests for src/components/conversation_manager/conversation_manager.py

Uses the real StubProvider — no mocked LLM layer.
sys.modules stubs are registered before any project import to prevent
import-chain errors.

Import chain that must be stubbed before importing conversation_manager:
  conversation_manager.py imports:
    - src.components.system_prompt.prompt_architect  → PromptArchitect, TaskType
    - src.components.system_prompt.utils             → PHASE4_SECTIONS
    - src.components.domain_discovery.domain_discovery → DomainDiscovery, ...
    - src.components.domain_discovery.domain_gate    → DomainGate
    - src.components.srs_formatter                   → generate_srs_document
    - src.components.srs_template                    → SRSTemplate, create_template
    - src.components.gap_detector                    → GapDetector, create_gap_detector
    - src.components.requirement_extractor           → RequirementExtractor, create_extractor

  prompt_architect imports prompt_context which imports domain_discovery.utils
  srs_formatter imports domain_discovery.domain_discovery (NFR_CATEGORIES)
"""
from __future__ import annotations

import json
import sys
import types
from typing import Literal
from unittest.mock import MagicMock
from enum import Enum
import pytest

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
# Build a minimal GapSeverity enum (mirrors real one)
# ---------------------------------------------------------------------------
class GapSeverity(str, Enum):
    CRITICAL  = "critical"
    IMPORTANT = "important"
    OPTIONAL  = "optional"

# ---------------------------------------------------------------------------
# Helper: register a stub module only if not already present
# ---------------------------------------------------------------------------
def _ensure_stub(name: str, **attrs):
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    mod = sys.modules[name]
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod

# ---------------------------------------------------------------------------
# domain_discovery.utils — imported by prompt_context, gap_detector, domain_gate
# ---------------------------------------------------------------------------
_ensure_stub(
    "src.components.domain_discovery.utils",
    NFR_CATEGORIES={
        "performance":      "Performance",
        "usability":        "Usability",
        "security_privacy": "Security & Privacy",
        "reliability":      "Reliability",
        "compatibility":    "Compatibility",
        "maintainability":  "Maintainability",
        "availability":     "Availability",
    },
    COVERAGE_CHECKLIST={},
    DOMAIN_SUB_DIMENSIONS=["data","actions","constraints","automation","edge_cases"],
    _DOMAIN_GATE_COVERAGE_FRACTION=0.80,
    GapSeverity=GapSeverity,
    STRUCTURAL_CATEGORIES={},
    MIN_FUNCTIONAL_FOR_NFR=10,
    NFR_PROBE_HINTS={},
    # Prompt template strings that domain_discovery.py imports
    _SEED_PROMPT="",
    _RESEED_PROMPT="",
    _NFR_CLASSIFY_PROMPT="",
    _SUBDIM_CLASSIFY_PROMPT="",
    _DOMAIN_MATCH_PROMPT="",
    _DECOMPOSE_PROMPT="",
    _PROJECT_NAME_PROMPT="",
    _COMPLEXITY_PROMPT="",
    _DOMAIN_TEMPLATE_PROMPT="",
)

# ---------------------------------------------------------------------------
# system_prompt.prompt_architect — imported by conversation_manager directly
# Must expose: PromptArchitect, TaskType, IEEE830_CATEGORIES,
#              MANDATORY_NFR_CATEGORIES, MIN_FUNCTIONAL_REQS, PHASE4_SECTIONS
# ---------------------------------------------------------------------------
TaskType = Literal["elicitation", "srs_only"]

_ensure_stub(
    "src.components.system_prompt.prompt_architect",
    PromptArchitect=MagicMock,
    TaskType=TaskType,
    IEEE830_CATEGORIES={},
    MANDATORY_NFR_CATEGORIES=frozenset({
        "performance","usability","security_privacy",
        "reliability","compatibility","maintainability","availability",
    }),
    MIN_FUNCTIONAL_REQS=10,
    MIN_NFR_PER_CATEGORY=3,
    PHASE4_SECTIONS=[],
)

# ---------------------------------------------------------------------------
# system_prompt.utils — imported by conversation_manager (PHASE4_SECTIONS)
# ---------------------------------------------------------------------------
_ensure_stub(
    "src.components.system_prompt.utils",
    PHASE4_SECTIONS=[],
    MIN_FUNCTIONAL_REQS=10,
    MIN_NFR_PER_CATEGORY=3,
    MANDATORY_NFR_CATEGORIES=frozenset({
        "performance","usability","security_privacy",
        "reliability","compatibility","maintainability","availability",
    }),
    IEEE830_CATEGORIES={},
    NFR_PROBE_HINTS={},
    _COMMS_STYLE="",
    _REQ_FORMAT="",
    _SEC_FORMAT="",
    _ELICITATION_FR_ROLE="",
    _ELICITATION_NFR_ROLE="",
    _ELICITATION_IEEE_ROLE="",
    _SRS_ONLY_ROLE="",
    _PREPROCESS_SYSTEM="",
    _PREPROCESS_USER="",
    _SCOPE_PROMPT="",
    _PERSPECTIVE_PROMPT="",
    _PRODUCT_FUNCTIONS_DOMAIN_PROMPT="",
    _USER_CLASSES_PROMPT="",
    _GENERAL_CONSTRAINTS_PROMPT="",
    _ASSUMPTIONS_PROMPT="",
    _INTERFACES_PROMPT="",
    _CONSTRAINTS_STUB="",
    _DATABASE_STUB="",
    _SYSTEM_ROLE="",
)

# ---------------------------------------------------------------------------
# Now safe to import real project modules
# ---------------------------------------------------------------------------
from src.components.conversation_manager.llm_provider import StubProvider
from src.components.conversation_manager.conversation_manager import (
    ConversationManager, MAX_HISTORY_TURNS,
)
from src.components.conversation_state import ConversationState, RequirementType
from src.components.conversation_manager.session_logger import SessionLogger


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_manager(tmp_path, responses=None, gap_enabled=True):
    provider = StubProvider(responses=responses or ["Stub assistant reply."])
    return ConversationManager(
        provider=provider,
        log_dir=tmp_path / "logs",
        output_dir=tmp_path / "output",
        gap_enabled=gap_enabled,
    )


def _make_processed_req(text, req_type="functional",
                         category="auth", category_label="Authentication"):
    pr = MagicMock()
    pr.final_text = text
    pr.req_type = req_type
    pr.category = category
    pr.category_label = category_label
    return pr


# ---------------------------------------------------------------------------
# MAX_HISTORY_TURNS constant
# ---------------------------------------------------------------------------

class TestConstants:
    def test_max_history_turns_is_10(self):
        assert MAX_HISTORY_TURNS == 10


# ---------------------------------------------------------------------------
# ConversationManager initialisation
# ---------------------------------------------------------------------------

class TestInit:
    def test_provider_stored(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert isinstance(mgr.provider, StubProvider)

    def test_architect_created(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr._architect is not None

    def test_gap_detector_created_when_enabled(self, tmp_path):
        mgr = _make_manager(tmp_path, gap_enabled=True)
        assert mgr._gap_detector is not None

    def test_domain_discovery_created(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr._domain_discovery is not None

    def test_default_temperature(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.temperature == 0.0

    def test_default_task_type(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.task_type == "elicitation"


# ---------------------------------------------------------------------------
# start_session
# ---------------------------------------------------------------------------

class TestStartSession:
    def test_returns_four_tuple(self, tmp_path):
        assert len(_make_manager(tmp_path).start_session()) == 4

    def test_session_id_is_8_chars(self, tmp_path):
        session_id, _, _, _ = _make_manager(tmp_path).start_session()
        assert len(session_id) == 8

    def test_session_id_is_string(self, tmp_path):
        session_id, _, _, _ = _make_manager(tmp_path).start_session()
        assert isinstance(session_id, str)

    def test_state_is_conversation_state(self, tmp_path):
        _, state, _, _ = _make_manager(tmp_path).start_session()
        assert isinstance(state, ConversationState)

    def test_state_session_id_matches(self, tmp_path):
        session_id, state, _, _ = _make_manager(tmp_path).start_session()
        assert state.session_id == session_id

    def test_logger_is_session_logger(self, tmp_path):
        _, _, logger, _ = _make_manager(tmp_path).start_session()
        assert isinstance(logger, SessionLogger)

    def test_log_dir_created(self, tmp_path):
        _make_manager(tmp_path).start_session()
        assert (tmp_path / "logs").exists()

    def test_session_start_logged_to_file(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _, _, logger, _ = mgr.start_session()
        data = json.loads(logger.get_log_path().read_text(encoding="utf-8"))
        assert any(e["event_type"] == "session_start" for e in data)

    def test_session_start_contains_model_name(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _, _, logger, _ = mgr.start_session()
        data = json.loads(logger.get_log_path().read_text(encoding="utf-8"))
        start = next(e for e in data if e["event_type"] == "session_start")
        assert start["data"]["model"] == "stub-provider-v1"

    def test_unique_session_ids(self, tmp_path):
        mgr = _make_manager(tmp_path)
        ids = [mgr.start_session()[0] for _ in range(5)]
        assert len(set(ids)) == 5

    def test_srs_template_not_none(self, tmp_path):
        _, _, _, template = _make_manager(tmp_path).start_session()
        assert template is not None

    def test_domain_gate_set_on_state(self, tmp_path):
        _, state, _, _ = _make_manager(tmp_path).start_session()
        assert state.domain_gate is not None


# ---------------------------------------------------------------------------
# send_turn
# ---------------------------------------------------------------------------

class TestSendTurn:
    def _setup(self, tmp_path, responses=None):
        mgr = _make_manager(tmp_path, responses=responses or ["What would you like to build?"])
        _, state, logger, _ = mgr.start_session()
        return mgr, state, logger

    def test_returns_string(self, tmp_path):
        mgr, state, logger = self._setup(tmp_path)
        assert isinstance(mgr.send_turn("I want to build a library system.", state, logger), str)

    def test_returns_stub_response(self, tmp_path):
        mgr, state, logger = self._setup(tmp_path, responses=["Who are the primary users?"])
        result = mgr.send_turn("I want to build a library system.", state, logger)
        assert result == "Who are the primary users?"

    def test_turn_recorded_in_state(self, tmp_path):
        mgr, state, logger = self._setup(tmp_path)
        mgr.send_turn("Hello.", state, logger)
        assert state.turn_count == 1

    def test_multiple_turns_accumulate(self, tmp_path):
        mgr, state, logger = self._setup(tmp_path, responses=["A","B","C"])
        for msg in ["One.", "Two.", "Three."]:
            mgr.send_turn(msg, state, logger)
        assert state.turn_count == 3

    def test_turn_logged_to_file(self, tmp_path):
        mgr, state, logger = self._setup(tmp_path)
        mgr.send_turn("Some message.", state, logger)
        data = json.loads(logger.get_log_path().read_text(encoding="utf-8"))
        assert any(e["event_type"] == "turn" for e in data)

    def test_user_message_in_log(self, tmp_path):
        mgr, state, logger = self._setup(tmp_path)
        mgr.send_turn("I need a booking system.", state, logger)
        data = json.loads(logger.get_log_path().read_text(encoding="utf-8"))
        turn = next(e for e in data if e["event_type"] == "turn")
        assert "booking system" in turn["data"]["user_message"]

    def test_assistant_response_in_log(self, tmp_path):
        mgr, state, logger = self._setup(tmp_path, responses=["What features do you need?"])
        mgr.send_turn("I need a booking system.", state, logger)
        data = json.loads(logger.get_log_path().read_text(encoding="utf-8"))
        turn = next(e for e in data if e["event_type"] == "turn")
        assert "What features" in turn["data"]["assistant_message"]

    def test_llm_error_raises_runtime_error(self, tmp_path):
        mgr, state, logger = self._setup(tmp_path)
        mgr.provider = MagicMock()
        mgr.provider.chat.side_effect = Exception("Network timeout")
        with pytest.raises(RuntimeError, match="LLM API error"):
            mgr.send_turn("Hello", state, logger)

    def test_history_trimmed_to_max_turns(self, tmp_path):
        responses = [f"Reply {i}" for i in range(25)]
        mgr = _make_manager(tmp_path, responses=responses)
        _, state, logger, _ = mgr.start_session()
        captured = {}
        real_chat = mgr.provider.chat

        def spy(system_message, messages, temperature=0.0):
            captured["messages"] = messages
            return real_chat(system_message, messages, temperature)

        mgr.provider.chat = spy
        for i in range(15):
            mgr.send_turn(f"Turn {i}", state, logger)
        assert len(captured.get("messages", [])) <= MAX_HISTORY_TURNS * 2 + 1

    def test_srs_template_updated(self, tmp_path):
        mgr, state, logger = self._setup(tmp_path)
        mgr._srs_template = MagicMock()
        mgr.send_turn("I need a hospital system.", state, logger)
        mgr._srs_template.update_from_requirements.assert_called()

    def test_gap_detector_called(self, tmp_path):
        mgr, state, logger = self._setup(tmp_path)
        mgr._gap_detector.analyse = MagicMock(return_value=None)
        mgr.send_turn("Message.", state, logger)
        mgr._gap_detector.analyse.assert_called_once_with(state)


# ---------------------------------------------------------------------------
# inject_requirements — integration with real state
# ---------------------------------------------------------------------------

class TestInjectRequirements:
    def test_returns_count_of_injected(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _, state, logger, _ = mgr.start_session()
        # Use clearly distinct texts so Jaccard similarity stays well below 0.7
        reqs = [
            _make_processed_req("The system shall allow users to log in via email."),
            _make_processed_req("Administrators shall generate monthly billing invoices."),
            _make_processed_req("The platform shall send push notifications to mobile devices."),
        ]
        assert mgr.inject_requirements(reqs, state, logger) == 3

    def test_requirements_added_to_state(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _, state, logger, _ = mgr.start_session()
        mgr.inject_requirements(
            [_make_processed_req("The system shall allow users to log in.")], state, logger)
        assert state.functional_count == 1

    def test_deduplicates_near_identical(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _, state, logger, _ = mgr.start_session()
        text = "The system shall authenticate users via password"
        count = mgr.inject_requirements(
            [_make_processed_req(text), _make_processed_req(text)], state, logger)
        assert count == 1

    def test_functional_type_mapped(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _, state, logger, _ = mgr.start_session()
        mgr.inject_requirements(
            [_make_processed_req("FR req", req_type="functional")], state, logger)
        assert next(iter(state.requirements.values())).req_type == RequirementType.FUNCTIONAL

    def test_non_functional_type_mapped(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _, state, logger, _ = mgr.start_session()
        mgr.inject_requirements(
            [_make_processed_req("NFR req", req_type="non_functional",
                                  category="performance")], state, logger)
        assert next(iter(state.requirements.values())).req_type == RequirementType.NON_FUNCTIONAL

    def test_constraint_type_mapped(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _, state, logger, _ = mgr.start_session()
        mgr.inject_requirements(
            [_make_processed_req("Must use PostgreSQL.", req_type="constraint")], state, logger)
        assert next(iter(state.requirements.values())).req_type == RequirementType.CONSTRAINT

    def test_source_is_uploaded(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _, state, logger, _ = mgr.start_session()
        mgr.inject_requirements([_make_processed_req("A requirement.")], state, logger)
        assert next(iter(state.requirements.values())).source == "uploaded"

    def test_nfr_coverage_incremented(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _, state, logger, _ = mgr.start_session()
        mgr.inject_requirements(
            [_make_processed_req("Response < 1s.", req_type="non_functional",
                                  category="performance")], state, logger)
        assert state.nfr_coverage.get("performance", 0) == 1

    def test_empty_list_returns_zero(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _, state, logger, _ = mgr.start_session()
        assert mgr.inject_requirements([], state, logger) == 0

    def test_event_logged_to_file(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _, state, logger, _ = mgr.start_session()
        mgr.inject_requirements([_make_processed_req("Some req.")], state, logger)
        data = json.loads(logger.get_log_path().read_text(encoding="utf-8"))
        assert any(e["event_type"] == "requirements_injected" for e in data)


# ---------------------------------------------------------------------------
# _run_smart_check
# ---------------------------------------------------------------------------

class TestRunSmartCheck:
    def _ext(self, texts):
        return [MagicMock(text=t, req_type="functional", category="general") for t in texts]

    def test_empty_list_unchanged(self, tmp_path):
        assert _make_manager(tmp_path)._run_smart_check([], "msg") == []

    def test_rewrite_applied(self, tmp_path):
        import json as _json
        mgr = _make_manager(tmp_path)
        extracted = self._ext(["The system shall be fast"])
        resp = _json.dumps([{
            "original": "The system shall be fast",
            "final": "The system shall respond within 200ms for 95% of requests",
            "smart_score": 4, "rewritten": True,
            "specific": True, "measurable": True,
            "testable": True, "unambiguous": True, "relevant": True,
        }])
        mgr.provider = StubProvider(responses=[resp])
        assert "200ms" in mgr._run_smart_check(extracted, "msg")[0].text

    def test_no_rewrite_when_flag_false(self, tmp_path):
        import json as _json
        mgr = _make_manager(tmp_path)
        original = "Users must log in with email and password"
        extracted = self._ext([original])
        resp = _json.dumps([{
            "original": original, "final": original,
            "smart_score": 5, "rewritten": False,
            "specific": True, "measurable": True,
            "testable": True, "unambiguous": True, "relevant": True,
        }])
        mgr.provider = StubProvider(responses=[resp])
        assert mgr._run_smart_check(extracted, "msg")[0].text == original

    def test_count_mismatch_returns_original(self, tmp_path):
        import json as _json
        mgr = _make_manager(tmp_path)
        extracted = self._ext(["req1", "req2"])
        resp = _json.dumps([{"original": "req1", "final": "req1",
                              "smart_score": 3, "rewritten": False}])
        mgr.provider = StubProvider(responses=[resp])
        assert len(mgr._run_smart_check(extracted, "msg")) == 2

    def test_invalid_json_returns_original(self, tmp_path):
        mgr = _make_manager(tmp_path)
        extracted = self._ext(["some requirement"])
        mgr.provider = StubProvider(responses=["not json"])
        assert mgr._run_smart_check(extracted, "msg")[0].text == "some requirement"

    def test_smart_score_set(self, tmp_path):
        import json as _json
        mgr = _make_manager(tmp_path)
        extracted = self._ext(["some req"])
        resp = _json.dumps([{
            "original": "some req", "final": "some req",
            "smart_score": 4, "rewritten": False,
            "specific": True, "measurable": True,
            "testable": True, "unambiguous": True, "relevant": True,
        }])
        mgr.provider = StubProvider(responses=[resp])
        assert mgr._run_smart_check(extracted, "msg")[0].smart_score == 4


# ---------------------------------------------------------------------------
# Full end-to-end conversation flow
# ---------------------------------------------------------------------------

class TestFullFlow:
    def test_start_and_send_turn(self, tmp_path):
        mgr = _make_manager(tmp_path, responses=["Great! Who are the primary users?"])
        session_id, state, logger, _ = mgr.start_session()
        response = mgr.send_turn("I want to build a library management system.", state, logger)
        assert isinstance(response, str) and len(response) > 0
        data = json.loads(logger.get_log_path().read_text(encoding="utf-8"))
        types_ = [e["event_type"] for e in data]
        assert "session_start" in types_ and "turn" in types_

    def test_project_name_extracted_on_first_turn(self, tmp_path):
        mgr = _make_manager(tmp_path, responses=["Tell me more."])
        _, state, logger, _ = mgr.start_session()
        mgr.send_turn("I am building a SmartHome System.", state, logger)
        assert state.project_name != "Unknown Project"

    def test_stub_responses_cycle(self, tmp_path):
        mgr = _make_manager(tmp_path, responses=["Alpha", "Beta"])

        mgr._run_smart_check = lambda extracted, msg: extracted

        _, state, logger, _ = mgr.start_session()

        r = [mgr.send_turn(f"Turn {i}", state, logger) for i in range(4)]

        # Ensure cycling pattern regardless of offset
        unique = list(dict.fromkeys(r))  # preserves order
        assert set(unique) == {"Alpha", "Beta"}
        assert len(unique) == 2

    def test_message_history_grows(self, tmp_path):
        mgr = _make_manager(tmp_path, responses=["A", "B", "C"])
        _, state, logger, _ = mgr.start_session()
        for msg in ["One", "Two", "Three"]:
            mgr.send_turn(msg, state, logger)
        assert len(state.get_message_history()) == 6