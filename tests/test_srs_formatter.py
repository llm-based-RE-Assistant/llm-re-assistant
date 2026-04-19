"""
Unit tests for SRSFormatter.

Tests cover:
- _badge(): SMART score → badge string
- _priority_badge(): priority label → emoji
- _coverage_tick(): bool → tick emoji
- _render_req_block(): Markdown lines for a single requirement
- SRSFormatter.to_markdown(): full document contains required sections
- SRSFormatter.to_plain_text(): strips Markdown formatting
- SRSFormatter.write(): writes file to disk and returns correct path
- show_smart=False suppresses SMART badges
- show_transcript_summary=False suppresses Appendix C
"""

import sys
import types
from pathlib import Path

# Stubs — register BEFORE importing any src module.
# srs_formatter.py imports:
#   src.components.srs_template
#   src.components.conversation_state
#   src.components.system_prompt.prompt_architect
#   src.components.domain_discovery.domain_discovery
#   src.components.srs_coverage

if "src.components.domain_discovery.utils" not in sys.modules:
    sys.modules["src.components.domain_discovery.utils"] = types.ModuleType(
        "src.components.domain_discovery.utils"
    )
_du = sys.modules["src.components.domain_discovery.utils"]
_du._DOMAIN_GATE_COVERAGE_FRACTION = 0.8

if "src.components.system_prompt.prompt_architect" not in sys.modules:
    sys.modules["src.components.system_prompt.prompt_architect"] = types.ModuleType(
        "src.components.system_prompt.prompt_architect"
    )
_pa = sys.modules["src.components.system_prompt.prompt_architect"]
_pa.MIN_NFR_PER_CATEGORY   = 2
_pa.MIN_FUNCTIONAL_REQS    = 10
_pa.IEEE830_CATEGORIES     = {
    "functional":       "Functional Requirements",
    "performance":      "Performance",
    "security_privacy": "Security & Privacy",
    "reliability":      "Reliability",
    "usability":        "Usability",
    "maintainability":  "Maintainability",
    "compatibility":    "Compatibility",
    "constraints":      "Design Constraints",
}
_pa.MANDATORY_NFR_CATEGORIES = [
    "performance", "security_privacy", "reliability",
    "usability", "maintainability", "compatibility",
]
_pa.PHASE4_SECTIONS = {"1.2", "2.1", "2.3"}

if "src.components.system_prompt.utils" not in sys.modules:
    sys.modules["src.components.system_prompt.utils"] = types.ModuleType(
        "src.components.system_prompt.utils"
    )
_pu = sys.modules["src.components.system_prompt.utils"]
_pu.PHASE4_SECTIONS = {"1.2", "2.1", "2.3"}

if "src.components.domain_discovery.domain_discovery" not in sys.modules:
    sys.modules["src.components.domain_discovery.domain_discovery"] = types.ModuleType(
        "src.components.domain_discovery.domain_discovery"
    )
_dd = sys.modules["src.components.domain_discovery.domain_discovery"]
_dd.NFR_CATEGORIES = {
    "performance":      "Performance",
    "security_privacy": "Security & Privacy",
    "reliability":      "Reliability",
    "usability":        "Usability",
    "maintainability":  "Maintainability",
    "compatibility":    "Compatibility",
}
_dd.compute_structural_coverage = lambda state: set()

if "src.components.srs_coverage" not in sys.modules:
    sys.modules["src.components.srs_coverage"] = types.ModuleType(
        "src.components.srs_coverage"
    )
_sc = sys.modules["src.components.srs_coverage"]
_sc.render_section2_extras  = lambda tmpl, state: []
_sc.render_section35_stub   = lambda: [
    "*Hardware interfaces require architect review.*", ""
]

# Now import real classes
from src.components.conversation_state import RequirementType, Requirement  # noqa: E402
from src.components.srs_template import (                                    # noqa: E402
    SRSTemplate, SmartAnnotation, SmartFlag, AnnotatedRequirement,
    _heuristic_smart_check, _infer_priority,
)
from src.components.srs_formatter import (                                   # noqa: E402
    SRSFormatter, _badge, _priority_badge, _coverage_tick, _render_req_block,
)


# Minimal ConversationState mock

class _MockGate:
    seeded           = False
    total            = 0
    done_count       = 0
    completeness_pct = 0
    is_satisfied     = False
    domains          = {}


class _MockState:
    def __init__(self, session_id="sess-001", project_name="Test Project"):
        self.session_id              = session_id
        self.project_name            = project_name
        self.turns                   = []
        self.requirements            = {}
        self.nfr_coverage            = {}
        self.domain_gate             = _MockGate()
        self.srs_section_content     = {}
        self.phase4_sections_covered = set()
        self.domain_req_templates    = {}
        self.system_complexity       = ""

    @property
    def turn_count(self):         return len(self.turns)
    @property
    def functional_count(self):
        return sum(1 for r in self.requirements.values()
                   if r.req_type == RequirementType.FUNCTIONAL)
    @property
    def covered_categories(self): return set()
    @property
    def coverage_percentage(self): return 0.0

    def get_coverage_report(self):
        return {
            "session_id":               self.session_id,
            "project_name":             self.project_name,
            "turn_count":               self.turn_count,
            "total_requirements":       0,
            "functional_count":         0,
            "nonfunctional_count":      0,
            "constraint_count":         0,
            "coverage_percentage":      0.0,
            "covered_categories":       [],
            "uncovered_categories":     [],
            "mandatory_nfrs_covered":   False,
            "missing_mandatory_nfrs":   [],
            "nfr_coverage":             {},
            "nfr_depth":                {},
            "nfr_min_threshold":        2,
            "phase4_sections_covered":  [],
            "phase4_progress":          "0/3",
            "phase4_complete":          False,
            "domain_gate":              {},
            "domain_completeness_score": "0/0",
            "domain_completeness_pct":  0,
            "domain_gate_satisfied":    False,
        }
    def get_message_history(self):
        return []


# Helpers

def _req(req_id="FR-001", req_type=RequirementType.FUNCTIONAL,
         text="The system shall allow users to log in with email and password.",
         category="functional"):
    return Requirement(
        req_id=req_id, req_type=req_type, text=text,
        turn_id=1, category=category, raw_excerpt="",
    )


def _annotated(req_id="FR-001",
               text="The system shall allow users to log in.",
               category="functional",
               req_type=RequirementType.FUNCTIONAL,
               priority="Must-have"):
    req = _req(req_id=req_id, req_type=req_type, text=text, category=category)
    ann = AnnotatedRequirement(requirement=req)
    ann.smart        = _heuristic_smart_check(text)
    ann.priority     = priority
    ann.ieee_section = "3.1"
    return ann


def _populated_template():
    tmpl = SRSTemplate(session_id="sess-001", project_name="Library System")
    tmpl.update_from_requirements({
        "FR-001":  _req("FR-001",  RequirementType.FUNCTIONAL,
                        "The system shall allow user login with email.",
                        "functional"),
        "NFR-001": _req("NFR-001", RequirementType.NON_FUNCTIONAL,
                        "The system shall respond within 200ms for 95% of requests.",
                        "performance"),
        "CON-001": _req("CON-001", RequirementType.CONSTRAINT,
                        "The system shall only be deployed on AWS infrastructure.",
                        "constraints"),
    }, project_name="Library System")
    return tmpl


def _state():
    return _MockState()


def _formatter(**kwargs):
    return SRSFormatter(**kwargs)


# _badge()

class TestBadge:

    def test_score_5(self):   assert "5/5" in _badge(5)
    def test_score_4(self):   assert "4/5" in _badge(4)
    def test_score_3(self):   assert "3/5" in _badge(3)
    def test_score_2(self):   assert "2/5" in _badge(2)
    def test_score_1(self):   assert "1/5" in _badge(1)
    def test_score_0(self):   assert "1/5" in _badge(0)


# _priority_badge()

class TestPriorityBadge:

    def test_must_have(self):      assert _priority_badge("Must-have")    == "🔴"
    def test_should_have(self):    assert _priority_badge("Should-have")  == "🟡"
    def test_nice_to_have(self):   assert _priority_badge("Nice-to-have") == "🟢"
    def test_unknown_empty(self):  assert _priority_badge("Unknown")      == ""


# _coverage_tick()

class TestCoverageTick:

    def test_true_checkmark(self):  assert _coverage_tick(True)  == "✅"
    def test_false_cross(self):     assert _coverage_tick(False) == "❌"


# _render_req_block()

class TestRenderReqBlock:

    def test_contains_req_id(self):
        text = "\n".join(_render_req_block(_annotated("FR-001"), show_smart=True))
        assert "FR-001" in text

    def test_contains_requirement_text(self):
        ann  = _annotated(text="The system shall allow users to log in.")
        text = "\n".join(_render_req_block(ann, show_smart=True))
        assert "The system shall allow users to log in." in text

    def test_smart_badge_present_when_enabled(self):
        text = "\n".join(_render_req_block(_annotated(), show_smart=True))
        assert "★" in text or "☆" in text

    def test_no_smart_badge_when_disabled(self):
        text = "\n".join(_render_req_block(_annotated(), show_smart=False))
        assert "★" not in text

    def test_contains_source_metadata(self):
        text = "\n".join(_render_req_block(_annotated(), show_smart=True))
        assert "Turn" in text

    def test_contains_smart_dimensions(self):
        text = "\n".join(_render_req_block(_annotated(), show_smart=True))
        assert "Specific" in text
        assert "Measurable" in text

    def test_priority_icon_present(self):
        ann  = _annotated(priority="Must-have")
        text = "\n".join(_render_req_block(ann, show_smart=True))
        assert "🔴" in text


# SRSFormatter.to_markdown()

class TestToMarkdown:

    def _render(self, show_smart=True, show_transcript=True):
        return _formatter(
            show_smart=show_smart,
            show_transcript_summary=show_transcript,
        ).to_markdown(_populated_template(), _state())

    def test_contains_srs_title(self):
        assert "Software Requirements Specification" in self._render()

    def test_contains_project_name(self):
        assert "Library System" in self._render()

    def test_contains_session_id(self):
        assert "sess-001" in self._render()

    def test_contains_section1(self):
        assert "Introduction" in self._render()

    def test_contains_section2(self):
        assert "Overall Description" in self._render()

    def test_contains_section3(self):
        assert "Specific Requirements" in self._render()

    def test_contains_appendix_a(self):
        md = self._render()
        assert "Appendix A" in md or "Traceability" in md

    def test_contains_appendix_b(self):
        md = self._render()
        assert "Appendix B" in md or "Coverage" in md

    def test_appendix_c_present_when_enabled(self):
        md = self._render(show_transcript=True)
        assert "Appendix C" in md or "Transcript" in md

    def test_appendix_c_absent_when_disabled(self):
        assert "Appendix C" not in self._render(show_transcript=False)

    def test_smart_badges_present(self):
        md = self._render(show_smart=True)
        assert "★" in md or "☆" in md

    def test_fr_id_in_output(self):
        assert "FR-001" in self._render()

    def test_nfr_id_in_output(self):
        assert "NFR-001" in self._render()

    def test_requirement_text_in_output(self):
        assert "The system shall allow user login with email." in self._render()


# SRSFormatter.to_plain_text()

class TestToPlainText:

    def _plain(self):
        return _formatter().to_plain_text(_populated_template(), _state())

    def test_no_bold_markdown(self):
        assert "**" not in self._plain()

    def test_no_heading_hashes(self):
        for line in self._plain().splitlines():
            assert not line.startswith("#"), f"Found heading: {line}"

    def test_no_blockquote_markers(self):
        for line in self._plain().splitlines():
            assert not line.startswith(">"), f"Found blockquote: {line}"

    def test_content_still_present(self):
        plain = self._plain()
        assert "Library System" in plain
        assert "FR-001" in plain


# SRSFormatter.write()

class TestWrite:

    def test_creates_file(self, tmp_path):
        path = _formatter().write(_populated_template(), _state(), tmp_path)
        assert path.exists()

    def test_returns_path_object(self, tmp_path):
        path = _formatter().write(_populated_template(), _state(), tmp_path)
        assert isinstance(path, Path)

    def test_filename_contains_session_id(self, tmp_path):
        path = _formatter().write(_populated_template(), _state(), tmp_path)
        assert "sess-001" in path.name

    def test_custom_filename(self, tmp_path):
        path = _formatter().write(
            _populated_template(), _state(), tmp_path, filename="custom.md"
        )
        assert path.name == "custom.md"

    def test_file_content_is_markdown(self, tmp_path):
        path = _formatter().write(_populated_template(), _state(), tmp_path)
        assert "Software Requirements Specification" in path.read_text(encoding="utf-8")

    def test_creates_output_dir_if_missing(self, tmp_path):
        new_dir = tmp_path / "nested" / "output"
        path = _formatter().write(_populated_template(), _state(), new_dir)
        assert path.exists()