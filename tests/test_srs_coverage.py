"""
Tests for src/components/srs_coverage.py

Uses the real StubProvider for LLM calls inside SRSCoverageEnricher.
sys.modules stubs are registered before any project import following
the same pattern as test_gap_detector.py and test_prompt_architect.py.

Import chain:
  srs_coverage.py imports:
    - src.components.conversation_state      (RequirementType)
    - src.components.srs_template            (UserClass)
    - src.components.system_prompt.utils     (prompts)
  srs_formatter.py (imported by srs_template tests etc.) imports:
    - src.components.system_prompt.prompt_architect (IEEE830_CATEGORIES, ...)
    - src.components.domain_discovery.domain_discovery (NFR_CATEGORIES)
"""
from __future__ import annotations

import sys
import types
from enum import Enum
from typing import Literal
from unittest.mock import MagicMock
import pytest

# ---------------------------------------------------------------------------
# GapSeverity (mirrors real enum, needed by gap_detector stub)
# ---------------------------------------------------------------------------
class GapSeverity(str, Enum):
    CRITICAL  = "critical"
    IMPORTANT = "important"
    OPTIONAL  = "optional"

# ---------------------------------------------------------------------------
# Helper: register stub only if not already present, always update attrs
# ---------------------------------------------------------------------------
def _ensure_stub(name: str, **attrs):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
    mod = sys.modules[name]
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod

# ---------------------------------------------------------------------------
# domain_discovery.utils
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
# system_prompt.prompt_architect (needed by srs_formatter and gap_detector)
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
# system_prompt.utils (imported by srs_coverage directly)
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
    _DATABASE_STUB="[ARCHITECT REVIEW REQUIRED] {implied_data_reqs}",
    _SYSTEM_ROLE="",
)

# ---------------------------------------------------------------------------
# Now safe to import project modules
# ---------------------------------------------------------------------------
from src.components.conversation_manager.llm_provider import StubProvider
from src.components.srs_coverage import (
    _reqs_by_category,
    _all_reqs_text,
    _fr_list_text,
    _user_turns_text,
    _exclusions_text,
    _domain_summary,
    _implied_data_reqs,
    _implied_data_reqs_stub,
    render_section2_extras,
    render_section35_stub,
    SRSCoverageEnricher,
    create_enricher,
)
from src.components.conversation_state import ConversationState, RequirementType
from src.components.srs_template import SRSTemplate, UserClass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _req(req_id, text, req_type=RequirementType.FUNCTIONAL,
         category="auth", domain_key=""):
    r = MagicMock()
    r.req_id = req_id
    r.text = text

    # Dummy req_type that behaves like an Enum
    dummy_type = MagicMock()
    dummy_type.value = req_type.value

    # ✅ Make equality checks work (critical)
    dummy_type.__eq__.side_effect = lambda other: other == req_type

    r.req_type = dummy_type
    r.category = category
    r.domain_key = domain_key
    return r

def _state(reqs=None, turns=None, project_name="TestProject",
           srs_section_content=None, domain_gate=None):
    s = MagicMock()
    s.project_name = project_name
    s.requirements = reqs or {}
    s.turns = turns or []
    s.srs_section_content = srs_section_content or {}
    s.domain_gate = domain_gate
    return s


def _turn(turn_id, user_message):
    t = MagicMock()
    t.turn_id = turn_id
    t.user_message = user_message
    return t


def _template():
    return SRSTemplate(session_id="s1", project_name="TestProject")


def _enricher(response="Generated prose content."):
    """Create an SRSCoverageEnricher backed by a real StubProvider."""
    return SRSCoverageEnricher(provider=StubProvider(responses=[response]))


# ---------------------------------------------------------------------------
# _reqs_by_category
# ---------------------------------------------------------------------------

class TestReqsByCategory:
    def test_matches_category(self):
        reqs = {"r1": _req("r1", "Login req", category="auth")}
        assert "Login req" in _reqs_by_category(_state(reqs=reqs), "auth")

    def test_no_match_returns_none_elicited(self):
        assert "none" in _reqs_by_category(_state(), "auth").lower()

    def test_max_items_cap(self):
        reqs = {f"r{i}": _req(f"r{i}", f"Req {i}", category="auth") for i in range(10)}
        result = _reqs_by_category(_state(reqs=reqs), "auth", max_items=3)
        assert result.count("- [") <= 3

    def test_matches_req_type_value(self):
        reqs = {"r1": _req("r1", "NFR req",
                            req_type=RequirementType.NON_FUNCTIONAL, category="perf")}
        assert "NFR req" in _reqs_by_category(_state(reqs=reqs), "non_functional")


# ---------------------------------------------------------------------------
# _all_reqs_text
# ---------------------------------------------------------------------------

class TestAllReqsText:
    def test_includes_req_id_and_category(self):
        reqs = {"r1": _req("r1", "Some req", category="auth")}
        result = _all_reqs_text(_state(reqs=reqs))
        assert "r1" in result and "auth" in result

    def test_max_items_cap(self):
        reqs = {f"r{i}": _req(f"r{i}", f"Req {i}") for i in range(50)}
        assert _all_reqs_text(_state(reqs=reqs), max_items=5).count("- [") <= 5


# ---------------------------------------------------------------------------
# _fr_list_text
# ---------------------------------------------------------------------------

class TestFRListText:
    def test_only_functional_included(self):
        reqs = {
            "fr1": _req("fr1", "FR one", RequirementType.FUNCTIONAL),
            "nfr1": _req("nfr1", "NFR one", RequirementType.NON_FUNCTIONAL),
        }
        result = _fr_list_text(_state(reqs=reqs))
        assert "FR one" in result and "NFR one" not in result

    def test_empty_returns_empty_string(self):
        assert _fr_list_text(_state()) == ""

    def test_max_items_cap(self):
        reqs = {f"r{i}": _req(f"r{i}", f"FR {i}") for i in range(30)}
        assert _fr_list_text(_state(reqs=reqs), max_items=5).count("- [") <= 5


# ---------------------------------------------------------------------------
# _user_turns_text
# ---------------------------------------------------------------------------

class TestUserTurnsText:
    def test_includes_user_message(self):
        turns = [_turn(1, "I need a login system")]
        assert "login system" in _user_turns_text(_state(turns=turns))

    def test_max_turns_respected(self):
        turns = [_turn(i, f"Message {i}") for i in range(20)]
        assert _user_turns_text(_state(turns=turns), max_turns=3).count("Turn") <= 3

    def test_truncates_long_messages(self):
        turns = [_turn(1, "X" * 500)]
        for line in _user_turns_text(_state(turns=turns), max_chars=50).split("\n"):
            assert len(line) < 200


# ---------------------------------------------------------------------------
# _exclusions_text
# ---------------------------------------------------------------------------

class TestExclusionsText:
    def test_detects_shall_not_constraint(self):
        reqs = {"c1": _req("c1", "The system shall not support batch imports.",
                            RequirementType.CONSTRAINT)}
        assert "batch imports" in _exclusions_text(_state(reqs=reqs))

    def test_no_exclusions_returns_note(self):
        assert "no explicit" in _exclusions_text(_state()).lower()

    def test_functional_not_included(self):
        reqs = {"f1": _req("f1", "Users can log in", RequirementType.FUNCTIONAL)}
        assert "log in" not in _exclusions_text(_state(reqs=reqs))


# ---------------------------------------------------------------------------
# _domain_summary
# ---------------------------------------------------------------------------

class TestDomainSummary:
    def test_no_gate_returns_general(self):
        assert "general" in _domain_summary(_state(domain_gate=None)).lower()

    def test_unseeded_gate_returns_general(self):
        gate = MagicMock(); gate.seeded = False
        assert "general" in _domain_summary(_state(domain_gate=gate)).lower()

    def test_returns_domain_labels(self):
        d1 = MagicMock(); d1.label = "Authentication"; d1.status = "confirmed"
        d2 = MagicMock(); d2.label = "Payments"; d2.status = "confirmed"
        gate = MagicMock(); gate.seeded = True
        gate.domains = {"auth": d1, "payment": d2}
        result = _domain_summary(_state(domain_gate=gate))
        assert "Authentication" in result and "Payments" in result

    def test_excluded_domains_filtered(self):
        d = MagicMock(); d.label = "Excluded Feature"; d.status = "excluded"
        gate = MagicMock(); gate.seeded = True; gate.domains = {"excl": d}
        assert "Excluded Feature" not in _domain_summary(_state(domain_gate=gate))


# ---------------------------------------------------------------------------
# _implied_data_reqs
# ---------------------------------------------------------------------------

class TestImpliedDataReqs:
    def test_finds_keyword_match(self):
        reqs = {"r1": _req("r1", "The system shall store user profile data.")}
        assert "r1" in _implied_data_reqs(_state(reqs=reqs))

    def test_no_match_returns_none_identified(self):
        assert "none" in _implied_data_reqs(_state()).lower()

    def test_caps_at_10(self):
        reqs = {f"r{i}": _req(f"r{i}", "The system shall store records.") for i in range(20)}
        assert _implied_data_reqs(_state(reqs=reqs)).count("- [") <= 10


# ---------------------------------------------------------------------------
# _implied_data_reqs_stub
# ---------------------------------------------------------------------------

class TestImpliedDataReqsStub:
    def test_contains_architect_review(self):
        assert "ARCHITECT" in _implied_data_reqs_stub(_state())

    def test_contains_data_keyword(self):
        reqs = {"r1": _req("r1", "The system shall store user data.")}
        result = _implied_data_reqs_stub(_state(reqs=reqs))
        assert "data" in result.lower() or "database" in result.lower()


# ---------------------------------------------------------------------------
# render_section2_extras
# ---------------------------------------------------------------------------

class TestRenderSection2Extras:
    def test_operating_env_sentinel_rendered(self):
        tmpl = _template()
        tmpl.section2.general_constraints = ["__operating_environment__Requires Linux 22.04"]
        lines = []
        render_section2_extras(lines, tmpl)
        combined = "\n".join(lines)
        assert "Operating Environment" in combined and "Linux" in combined

    def test_docs_sentinel_rendered(self):
        tmpl = _template()
        tmpl.section2.general_constraints = ["__user_documentation__User manual required"]
        lines = []
        render_section2_extras(lines, tmpl)
        assert "User Documentation" in "\n".join(lines)

    def test_plain_string_skipped(self):
        tmpl = _template()
        tmpl.section2.general_constraints = ["Just a plain constraint"]
        lines = []
        render_section2_extras(lines, tmpl)
        assert lines == []

    def test_non_string_skipped(self):
        tmpl = _template()
        tmpl.section2.general_constraints = [42, None]  # type: ignore
        lines = []
        render_section2_extras(lines, tmpl)
        assert lines == []


# ---------------------------------------------------------------------------
# render_section35_stub
# ---------------------------------------------------------------------------

class TestRenderSection35Stub:
    def test_returns_true_when_stub_present(self):
        tmpl = _template()
        tmpl.section1.references.append("DESIGN_CONSTRAINTS_STUB::Some stub content here")
        lines = []
        assert render_section35_stub(lines, tmpl) is True
        assert len(lines) > 0

    def test_returns_false_when_absent(self):
        tmpl = _template()
        lines = []
        assert render_section35_stub(lines, tmpl) is False
        assert lines == []

    def test_stub_text_written(self):
        tmpl = _template()
        tmpl.section1.references.append("DESIGN_CONSTRAINTS_STUB::Architect must review.")
        lines = []
        render_section35_stub(lines, tmpl)
        assert any("Architect" in l for l in lines)


# ---------------------------------------------------------------------------
# SRSCoverageEnricher._call_llm — uses real StubProvider
# ---------------------------------------------------------------------------

class TestCallLLM:
    def test_returns_stub_response(self):
        result = _enricher("This is the generated scope section.")._call_llm("Generate scope.")
        assert result == "This is the generated scope section."

    def test_strips_whitespace(self):
        result = _enricher("  content with spaces  ")._call_llm("prompt")
        assert result == "content with spaces"

    def test_exception_returns_stub_message(self):
        p = MagicMock(); p.chat.side_effect = RuntimeError("network error")
        result = SRSCoverageEnricher(provider=p)._call_llm("prompt")
        assert "GENERATION FAILED" in result or "manually" in result.lower()

    def test_stub_cycles_for_multiple_calls(self):
        enricher = _enricher("Consistent response.")
        assert enricher._call_llm("p1") == enricher._call_llm("p2") == "Consistent response."


# ---------------------------------------------------------------------------
# SRSCoverageEnricher.enrich — phase4 content wins
# ---------------------------------------------------------------------------

class TestEnrichPhase4Priority:
    def test_scope_uses_phase4_content(self):
        state = _state(srs_section_content={"1.2": "Phase4 scope content."})
        tmpl = _template()
        filled = _enricher("LLM fallback should not appear").enrich(tmpl, state)
        assert tmpl.section1.scope == "Phase4 scope content."
        assert filled.get("§1.2 Scope") == "phase4"

    def test_perspective_uses_phase4_content(self):
        state = _state(srs_section_content={"2.1": "Phase4 perspective."})
        tmpl = _template()
        filled = _enricher("LLM").enrich(tmpl, state)
        assert tmpl.section2.product_perspective == "Phase4 perspective."
        assert filled.get("§2.1 Product Perspective") == "phase4"

    def test_user_classes_phase4(self):
        state = _state(srs_section_content={"2.3": "Phase4 user classes."})
        tmpl = _template()
        filled = _enricher("LLM").enrich(tmpl, state)
        assert filled.get("§2.3 User Classes") == "phase4"

    def test_ui_interface_phase4(self):
        state = _state(srs_section_content={"3.1.1": "Phase4 UI content."})
        tmpl = _template()
        filled = _enricher("LLM").enrich(tmpl, state)
        assert filled.get("§3.1.1 User Interfaces") == "phase4"

    def test_sw_interface_phase4(self):
        state = _state(srs_section_content={"3.1.3": "Phase4 SW content."})
        tmpl = _template()
        filled = _enricher("LLM").enrich(tmpl, state)
        assert filled.get("§3.1.3 Software Interfaces") == "phase4"

    def test_comm_interface_phase4(self):
        state = _state(srs_section_content={"3.1.4": "Phase4 Comm content."})
        tmpl = _template()
        filled = _enricher("LLM").enrich(tmpl, state)
        assert filled.get("§3.1.4 Communication Interfaces") == "phase4"


# ---------------------------------------------------------------------------
# SRSCoverageEnricher.enrich — LLM fallback via StubProvider
# ---------------------------------------------------------------------------

class TestEnrichLLMFallback:
    def test_scope_llm_synthesis_when_no_phase4(self):
        state = _state()
        tmpl = _template()
        enricher = _enricher("LLM scope content generated here.")
        filled = enricher.enrich(tmpl, state)
        assert filled.get("§1.2 Scope") == "llm_synthesis"
        assert "LLM scope content" in tmpl.section1.scope

    def test_perspective_llm_synthesis(self):
        state = _state()
        tmpl = _template()
        filled = _enricher("Perspective content from LLM.").enrich(tmpl, state)
        assert filled.get("§2.1 Product Perspective") == "llm_synthesis"

    def test_general_constraints_always_filled(self):
        state = _state()
        tmpl = _template()
        filled = _enricher("1. Constraint A\n2. Constraint B").enrich(tmpl, state)
        assert "§2.4 General Constraints" in filled

    def test_user_classes_llm_when_no_phase4(self):
        state = _state()
        tmpl = _template()
        filled = _enricher("User classes description.").enrich(tmpl, state)
        assert "§2.3 User Classes" in filled
        assert filled["§2.3 User Classes"] == "llm_synthesis"


# ---------------------------------------------------------------------------
# SRSCoverageEnricher.enrich — always-stub sections
# ---------------------------------------------------------------------------

class TestEnrichAlwaysStub:
    def test_hardware_interfaces_always_stub(self):
        state = _state()
        tmpl = _template()
        filled = _enricher("llm content").enrich(tmpl, state)
        assert filled.get("§3.1.2 Hardware Interfaces") == "stub"
        hw = tmpl.section3.interfaces.hardware_interfaces
        assert len(hw) > 0 and "ARCHITECT" in hw[0]

    def test_database_always_stub(self):
        state = _state()
        tmpl = _template()
        filled = _enricher("llm content").enrich(tmpl, state)
        assert filled.get("§3.4 Logical Database Requirements") == "stub"
        assert len(tmpl.section3.database) > 0

    def test_design_constraints_stub_when_no_con_reqs(self):
        state = _state()
        tmpl = _template()
        filled = _enricher("llm content").enrich(tmpl, state)
        assert filled.get("§3.5 Design Constraints") == "stub"


# ---------------------------------------------------------------------------
# SRSCoverageEnricher.enrich — idempotent
# ---------------------------------------------------------------------------

class TestEnrichIdempotent:
    def test_does_not_overwrite_existing_scope(self):
        state = _state()
        tmpl = _template()
        tmpl.section1.scope = "Already filled scope."
        _enricher("Should not replace.").enrich(tmpl, state)
        assert tmpl.section1.scope == "Already filled scope."

    def test_scope_not_in_filled_when_already_set(self):
        state = _state()
        tmpl = _template()
        tmpl.section1.scope = "Existing scope."
        filled = _enricher("New").enrich(tmpl, state)
        assert "§1.2 Scope" not in filled

    def test_user_classes_not_overwritten(self):
        state = _state()
        tmpl = _template()
        tmpl.section2.user_classes = [UserClass("Admin", "Manages system")]
        _enricher("LLM classes").enrich(tmpl, state)
        assert len(tmpl.section2.user_classes) == 1
        assert tmpl.section2.user_classes[0].name == "Admin"

    def test_perspective_not_overwritten(self):
        state = _state()
        tmpl = _template()
        tmpl.section2.product_perspective = "Existing perspective."
        _enricher("New perspective.").enrich(tmpl, state)
        assert tmpl.section2.product_perspective == "Existing perspective."


# ---------------------------------------------------------------------------
# create_enricher
# ---------------------------------------------------------------------------

class TestCreateEnricher:
    def test_returns_instance(self):
        p = StubProvider()
        assert isinstance(create_enricher(p), SRSCoverageEnricher)

    def test_provider_stored(self):
        p = StubProvider()
        assert create_enricher(p).provider is p

    def test_enricher_can_call_llm(self):
        p = StubProvider(responses=["Generated content here."])
        result = create_enricher(p)._call_llm("Some prompt")
        assert result == "Generated content here."
