"""
Unit tests for SRSTemplate, SmartAnnotation, and SMART heuristic checker.

Tests cover:
- SmartAnnotation: score, quality_label, to_dict()
- _heuristic_smart_check(): SPECIFIC, MEASURABLE, TESTABLE, UNAMBIGUOUS, RELEVANT
- _infer_priority(): Must-have / Should-have / Nice-to-have
- _map_category_to_section(): category → IEEE-830 section
- SRSTemplate.update_from_requirements(): placement, idempotency, section tracking
- SRSTemplate.ingest_narrative(): string and list fields
- SRSTemplate.add_user_class(): deduplication
- SRSTemplate.add_open_issue() / add_conflict(): deduplication
- Coverage queries: functional_count, nfr_count, avg_smart_score, filled_sections
- Serialization: to_dict(), to_json()
- create_template() factory
"""

import sys
import types
import json

# Stubs — register BEFORE importing any src module.
# srs_template.py imports:
#   from src.components.conversation_state import Requirement, RequirementType
# conversation_state.py in turn imports prompt_architect, utils, domain_discovery.

if "src.components.domain_discovery.utils" not in sys.modules:
    _du = types.ModuleType("src.components.domain_discovery.utils")
    _du._DOMAIN_GATE_COVERAGE_FRACTION = 0.8
    sys.modules["src.components.domain_discovery.utils"] = _du

if "src.components.system_prompt.prompt_architect" not in sys.modules:
    _pa = types.ModuleType("src.components.system_prompt.prompt_architect")
    _pa.MIN_NFR_PER_CATEGORY = 2
    _pa.MIN_FUNCTIONAL_REQS  = 10
    _pa.IEEE830_CATEGORIES   = {
        "functional":       "Functional Requirements",
        "performance":      "Performance",
        "security_privacy": "Security & Privacy",
        "reliability":      "Reliability",
        "usability":        "Usability",
        "maintainability":  "Maintainability",
        "compatibility":    "Compatibility",
        "constraints":      "Design Constraints",
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

# Now import real classes
from src.components.conversation_state import RequirementType, Requirement  # noqa: E402
from src.components.srs_template import (                                    # noqa: E402
    SRSTemplate, SmartAnnotation, SmartFlag, AnnotatedRequirement,
    _heuristic_smart_check, _infer_priority, _map_category_to_section,
    create_template,
)


# Helpers

import time

def _req(req_id="FR-001", req_type=RequirementType.FUNCTIONAL,
         text="The system shall allow users to log in with email and password.",
         category="functional"):
    return Requirement(
        req_id=req_id, req_type=req_type, text=text,
        turn_id=1, category=category, raw_excerpt="",
    )


def _template(session_id="sess-001", project_name="Test Project"):
    return SRSTemplate(session_id=session_id, project_name=project_name)


# SmartAnnotation

class TestSmartAnnotation:

    def test_score_counts_core_dimensions(self):
        ann = SmartAnnotation()
        ann.satisfied = {
            SmartFlag.SPECIFIC, SmartFlag.MEASURABLE,
            SmartFlag.TESTABLE, SmartFlag.UNAMBIGUOUS, SmartFlag.RELEVANT,
        }
        assert ann.score == 5

    def test_score_excludes_achievable(self):
        ann = SmartAnnotation()
        ann.satisfied = {SmartFlag.ACHIEVABLE}
        assert ann.score == 0

    def test_quality_label_high(self):
        ann = SmartAnnotation()
        ann.satisfied = {
            SmartFlag.SPECIFIC, SmartFlag.MEASURABLE,
            SmartFlag.TESTABLE, SmartFlag.UNAMBIGUOUS, SmartFlag.RELEVANT,
        }
        assert "High Quality" in ann.quality_label

    def test_quality_label_acceptable(self):
        ann = SmartAnnotation()
        ann.satisfied = {SmartFlag.SPECIFIC, SmartFlag.TESTABLE, SmartFlag.RELEVANT}
        assert "Acceptable" in ann.quality_label

    def test_quality_label_needs_improvement(self):
        ann = SmartAnnotation()
        ann.satisfied = {SmartFlag.RELEVANT}
        assert "Needs Improvement" in ann.quality_label

    def test_to_dict_keys(self):
        ann = SmartAnnotation()
        assert set(ann.to_dict().keys()) == {
            "satisfied", "violated", "notes", "score", "quality_label"
        }

    def test_to_dict_satisfied_values(self):
        ann = SmartAnnotation()
        ann.satisfied = {SmartFlag.SPECIFIC}
        assert "specific" in ann.to_dict()["satisfied"]


# _heuristic_smart_check()

class TestHeuristicSmartCheck:

    def test_specific_actor_detected(self):
        ann = _heuristic_smart_check(
            "The system shall authenticate users via OAuth2.")
        assert SmartFlag.SPECIFIC in ann.satisfied

    def test_specific_missing_without_actor(self):
        ann = _heuristic_smart_check("Login should be fast.")
        assert SmartFlag.SPECIFIC in ann.violated

    def test_measurable_with_number(self):
        ann = _heuristic_smart_check(
            "The system shall respond within 200ms for 95% of requests.")
        assert SmartFlag.MEASURABLE in ann.satisfied

    def test_measurable_with_percentage(self):
        ann = _heuristic_smart_check(
            "The system shall achieve 99.9% uptime monthly.")
        assert SmartFlag.MEASURABLE in ann.satisfied

    def test_measurable_missing_without_number(self):
        ann = _heuristic_smart_check(
            "The system shall respond quickly to all requests.")
        assert SmartFlag.MEASURABLE in ann.violated

    def test_testable_with_shall(self):
        ann = _heuristic_smart_check(
            "The system shall encrypt all user data at rest.")
        assert SmartFlag.TESTABLE in ann.satisfied

    def test_testable_missing_without_shall(self):
        ann = _heuristic_smart_check("Users can log in.")
        assert SmartFlag.TESTABLE in ann.violated

    def test_unambiguous_no_vague_words(self):
        ann = _heuristic_smart_check(
            "The system shall process 1000 transactions per second.")
        assert SmartFlag.UNAMBIGUOUS in ann.satisfied

    def test_unambiguous_violated_with_vague_word(self):
        ann = _heuristic_smart_check(
            "The system shall be fast and intuitive for all users.")
        assert SmartFlag.UNAMBIGUOUS in ann.violated

    def test_relevant_always_set_for_nonempty(self):
        ann = _heuristic_smart_check(
            "The system shall allow admin users to manage accounts.")
        assert SmartFlag.RELEVANT in ann.satisfied

    def test_vague_words_noted(self):
        ann = _heuristic_smart_check(
            "The system shall provide a simple and intuitive experience.")
        assert len(ann.notes) > 0


# _infer_priority()

class TestInferPriority:

    def test_shall_gives_must_have(self):
        assert _infer_priority(_req(
            text="The system shall support two-factor authentication.")
        ) == "Must-have"

    def test_must_gives_must_have(self):
        assert _infer_priority(_req(
            text="The system must encrypt all stored passwords.")
        ) == "Must-have"

    def test_optional_gives_nice_to_have(self):
        assert _infer_priority(_req(
            text="The system may optionally provide dark mode.")
        ) == "Nice-to-have"

    def test_future_gives_nice_to_have(self):
        assert _infer_priority(_req(
            text="In the future the system could support mobile apps.")
        ) == "Nice-to-have"

    def test_neutral_gives_should_have(self):
        assert _infer_priority(_req(
            text="The system provides reporting capabilities.")
        ) == "Should-have"


# _map_category_to_section()

class TestMapCategoryToSection:

    def test_functional_maps_to_3_1(self):
        assert _map_category_to_section(
            _req(category="functional", req_type=RequirementType.FUNCTIONAL)
        ) == "3.1"

    def test_constraint_maps_to_3_5(self):
        assert _map_category_to_section(
            _req(category="constraints", req_type=RequirementType.CONSTRAINT)
        ) == "3.5"

    def test_performance_maps_to_3_3(self):
        assert _map_category_to_section(
            _req(category="performance", req_type=RequirementType.NON_FUNCTIONAL)
        ) == "3.3"

    def test_security_maps_to_3_6_3(self):
        assert _map_category_to_section(
            _req(category="security_privacy", req_type=RequirementType.NON_FUNCTIONAL)
        ) == "3.6.3"

    def test_usability_maps_to_3_6_6(self):
        assert _map_category_to_section(
            _req(category="usability", req_type=RequirementType.NON_FUNCTIONAL)
        ) == "3.6.6"

    def test_unknown_category_defaults_to_3_1(self):
        assert _map_category_to_section(
            _req(category="unknown_xyz", req_type=RequirementType.FUNCTIONAL)
        ) == "3.1"


# SRSTemplate.update_from_requirements()

class TestUpdateFromRequirements:

    def test_functional_placed_in_section3(self):
        tmpl = _template()
        tmpl.update_from_requirements({
            "FR-001": _req("FR-001", RequirementType.FUNCTIONAL,
                           "The system shall allow user login.")
        })
        assert tmpl.functional_count == 1

    def test_nfr_performance_placed_correctly(self):
        tmpl = _template()
        tmpl.update_from_requirements({
            "NFR-001": _req("NFR-001", RequirementType.NON_FUNCTIONAL,
                            "The system shall respond within 200ms.",
                            category="performance")
        })
        assert len(tmpl.section3.performance) == 1

    def test_nfr_security_placed_correctly(self):
        tmpl = _template()
        tmpl.update_from_requirements({
            "NFR-001": _req("NFR-001", RequirementType.NON_FUNCTIONAL,
                            "The system shall encrypt all user data using AES-256.",
                            category="security_privacy")
        })
        assert len(tmpl.section3.attributes.security) == 1

    def test_constraint_placed_correctly(self):
        tmpl = _template()
        tmpl.update_from_requirements({
            "CON-001": _req("CON-001", RequirementType.CONSTRAINT,
                            "The system shall only use AWS infrastructure.",
                            category="constraints")
        })
        assert len(tmpl.section3.design_constraints) == 1

    def test_idempotent_no_duplicates(self):
        tmpl = _template()
        reqs = {"FR-001": _req("FR-001", RequirementType.FUNCTIONAL,
                               "The system shall allow user login.")}
        tmpl.update_from_requirements(reqs)
        tmpl.update_from_requirements(reqs)
        assert tmpl.functional_count == 1

    def test_annotated_reqs_indexed_by_id(self):
        tmpl = _template()
        tmpl.update_from_requirements({
            "FR-001": _req("FR-001", RequirementType.FUNCTIONAL,
                           "The system shall allow user login.")
        })
        assert "FR-001" in tmpl.annotated_reqs

    def test_smart_annotation_applied(self):
        tmpl = _template()
        tmpl.update_from_requirements({
            "FR-001": _req("FR-001", RequirementType.FUNCTIONAL,
                           "The system shall allow user login.")
        })
        assert isinstance(tmpl.annotated_reqs["FR-001"].smart, SmartAnnotation)

    def test_section_filled_after_update(self):
        tmpl = _template()
        tmpl.update_from_requirements({
            "FR-001": _req("FR-001", RequirementType.FUNCTIONAL,
                           "The system shall allow user login.")
        })
        assert "section3.functional" in tmpl.filled_sections

    def test_project_name_updated(self):
        tmpl = _template(project_name="Old Name")
        tmpl.update_from_requirements({}, project_name="New Name")
        assert tmpl.project_name == "New Name"


# SRSTemplate.ingest_narrative()

class TestIngestNarrative:

    def test_sets_string_field(self):
        tmpl = _template()
        tmpl.ingest_narrative("section1.purpose", "This system manages tasks.")
        assert tmpl.section1.purpose == "This system manages tasks."

    def test_appends_to_list_field(self):
        tmpl = _template()
        tmpl.ingest_narrative("section2.assumptions", "Users have internet access.")
        tmpl.ingest_narrative("section2.assumptions", "Browsers are modern versions.")
        assert len(tmpl.section2.assumptions) == 2

    def test_no_duplicate_in_list(self):
        tmpl = _template()
        tmpl.ingest_narrative("section2.assumptions", "Users have internet access.")
        tmpl.ingest_narrative("section2.assumptions", "Users have internet access.")
        assert len(tmpl.section2.assumptions) == 1

    def test_invalid_key_does_not_raise(self):
        tmpl = _template()
        tmpl.ingest_narrative("nonexistent.field", "Some value.")


# SRSTemplate.add_user_class()

class TestAddUserClass:

    def test_adds_user_class(self):
        tmpl = _template()
        tmpl.add_user_class("Admin", "System administrator", "Expert")
        assert len(tmpl.section2.user_classes) == 1

    def test_deduplicates_by_name(self):
        tmpl = _template()
        tmpl.add_user_class("Admin", "System administrator")
        tmpl.add_user_class("admin", "Duplicate admin entry")
        assert len(tmpl.section2.user_classes) == 1

    def test_marks_section2_filled(self):
        tmpl = _template()
        tmpl.add_user_class("Manager", "Project manager role")
        assert "section2" in tmpl.filled_sections


# add_open_issue() / add_conflict()

class TestIssuesAndConflicts:

    def test_add_open_issue(self):
        tmpl = _template()
        tmpl.add_open_issue("Authentication method unclear.")
        assert len(tmpl.open_issues) == 1

    def test_open_issue_deduplication(self):
        tmpl = _template()
        tmpl.add_open_issue("Authentication method unclear.")
        tmpl.add_open_issue("Authentication method unclear.")
        assert len(tmpl.open_issues) == 1

    def test_add_conflict(self):
        tmpl = _template()
        tmpl.add_conflict("FR-001 contradicts FR-005 on auth method.")
        assert len(tmpl.conflicts) == 1

    def test_conflict_deduplication(self):
        tmpl = _template()
        tmpl.add_conflict("FR-001 contradicts FR-005 on auth method.")
        tmpl.add_conflict("FR-001 contradicts FR-005 on auth method.")
        assert len(tmpl.conflicts) == 1


# Coverage queries

class TestCoverageQueries:

    def _populated(self):
        tmpl = _template()
        tmpl.update_from_requirements({
            "FR-001": _req("FR-001", RequirementType.FUNCTIONAL,
                           "The system shall allow user login with email."),
            "NFR-001": _req("NFR-001", RequirementType.NON_FUNCTIONAL,
                            "The system shall respond within 200ms for 95% of requests.",
                            category="performance"),
            "CON-001": _req("CON-001", RequirementType.CONSTRAINT,
                            "The system shall only run on AWS.",
                            category="constraints"),
        })
        return tmpl

    def test_functional_count(self):
        assert self._populated().functional_count == 1

    def test_nfr_count(self):
        assert self._populated().nfr_count == 1

    def test_total_requirements(self):
        assert self._populated().total_requirements == 3

    def test_avg_smart_score_in_range(self):
        score = self._populated().avg_smart_score
        assert 0.0 <= score <= 5.0

    def test_is_section_empty_true_for_unfilled(self):
        assert _template().is_section_empty("section1.purpose") is True

    def test_is_section_empty_false_after_fill(self):
        assert self._populated().is_section_empty("section3.functional") is False

    def test_high_quality_count_gte_zero(self):
        assert self._populated().high_quality_count >= 0

    def test_needs_improvement_count_gte_zero(self):
        assert self._populated().needs_improvement_count >= 0


# Serialization

class TestSRSTemplateSerialization:

    def test_to_dict_has_required_keys(self):
        d = _template().to_dict()
        for key in ["session_id", "project_name", "total_requirements",
                    "functional_count", "nfr_count", "avg_smart_score",
                    "annotated_reqs", "filled_sections"]:
            assert key in d, f"Missing key: {key}"

    def test_to_json_is_valid(self):
        tmpl = _template()
        tmpl.update_from_requirements({
            "FR-001": _req("FR-001", RequirementType.FUNCTIONAL,
                           "The system shall allow user login.")
        })
        parsed = json.loads(tmpl.to_json())
        assert parsed["session_id"] == "sess-001"

    def test_annotated_reqs_in_to_dict(self):
        tmpl = _template()
        tmpl.update_from_requirements({
            "FR-001": _req("FR-001", RequirementType.FUNCTIONAL,
                           "The system shall allow user login.")
        })
        assert "FR-001" in tmpl.to_dict()["annotated_reqs"]


# Factory

def test_create_template_returns_instance():
    tmpl = create_template("test-session", "My Project")
    assert isinstance(tmpl, SRSTemplate)
    assert tmpl.project_name == "My Project"
    assert tmpl.session_id == "test-session"

def test_create_template_default_project_name():
    assert create_template("test-session").project_name == "Unknown Project"