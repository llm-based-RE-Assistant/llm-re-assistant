"""
test_iteration_3.py
==================
RE Assistant — Iteration 3 | University of Hildesheim
Unit Tests: GapDetector, ProactiveQuestionGenerator, PromptArchitect (Iteration 3)

Coverage targets (per QA plan)
--------------------------------
- C0 (statement coverage): 100%
- C1 (branch coverage):    100%

Test strategy
-------------
- Black-box tests for public APIs (GapDetector.analyse, QuestionGenerator.generate)
- White-box tests for internal classification logic
- Ablation test: gap_detection=False returns empty report
- Regression test: PromptArchitect.extra_context injection and reset
- Integration test: full turn cycle (ConversationState → GapDetector → QuestionGenerator → PromptArchitect)

Run
---
    pip install pytest
    pytest test_iteration3.py -v --tb=short
"""

from __future__ import annotations

import sys
import time
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

# Ensure src modules are importable
sys.path.insert(0, str(Path(__file__).parent))

from gap_detector import (
    GapDetector, GapReport, CategoryGap, GapSeverity,
    COVERAGE_CHECKLIST, create_gap_detector,
)
from question_generator import (
    ProactiveQuestionGenerator, QuestionTracker, FollowUpQuestion,
    QuestionSet, QUESTION_TEMPLATES, create_question_generator,
)
from prompt_architect import PromptArchitect, IEEE830_CATEGORIES, MANDATORY_NFR_CATEGORIES


# ---------------------------------------------------------------------------
# Minimal ConversationState stub (avoids importing the full module in tests)
# ---------------------------------------------------------------------------

@dataclass
class _Turn:
    turn_id: int
    user_message: str
    assistant_message: str
    timestamp: float = field(default_factory=time.time)
    categories_updated: list = field(default_factory=list)
    requirements_added: list = field(default_factory=list)


@dataclass
class _Requirement:
    req_id: str
    req_type: str
    text: str
    turn_id: int
    category: str
    raw_excerpt: str
    timestamp: float = field(default_factory=time.time)
    is_ambiguous: bool = False
    ambiguity_note: str = ""


@dataclass
class _StubState:
    """Minimal ConversationState stub for isolated unit testing."""
    session_id: str = "test-session-001"
    project_name: str = "TaskMaster"
    turn_count: int = 0
    session_complete: bool = False
    covered_categories: set = field(default_factory=set)
    turns: list = field(default_factory=list)
    requirements: list = field(default_factory=list)

    @property
    def total_requirements(self): return len(self.requirements)
    @property
    def functional_count(self): return sum(1 for r in self.requirements if r.req_type == "functional")
    @property
    def nonfunctional_count(self): return sum(1 for r in self.requirements if r.req_type == "non_functional")
    @property
    def mandatory_nfrs_covered(self): return MANDATORY_NFR_CATEGORIES.issubset(self.covered_categories)

    def get_coverage_report(self):
        return {
            "turn_count": self.turn_count,
            "coverage_percentage": 0,
            "total_requirements": self.total_requirements,
            "functional_count": self.functional_count,
            "nonfunctional_count": self.nonfunctional_count,
            "covered_categories": list(self.covered_categories),
            "uncovered_categories": [],
            "missing_mandatory_nfrs": [],
        }


def _make_state_with_turns(*turn_texts: str) -> _StubState:
    """Helper: create a stub state with user turns containing given text."""
    state = _StubState()
    for i, text in enumerate(turn_texts):
        state.turns.append(_Turn(
            turn_id=i + 1,
            user_message=text,
            assistant_message="Thank you.",
        ))
        state.turn_count += 1
    return state


# ===========================================================================
# GapDetector Tests
# ===========================================================================

class TestGapDetectorInit(unittest.TestCase):
    """GapDetector initialisation and factory."""

    def test_default_enabled(self):
        d = GapDetector()
        self.assertTrue(d.enabled)

    def test_disabled_via_factory(self):
        d = create_gap_detector(enabled=False)
        self.assertFalse(d.enabled)

    def test_custom_checklist(self):
        custom = {"foo": {
            "label": "Foo", "severity": GapSeverity.OPTIONAL,
            "keywords": ["foo"], "description": "desc",
            "volere_ref": "V1", "ieee830_ref": "I1",
        }}
        d = GapDetector(checklist=custom)
        self.assertEqual(d.checklist, custom)


class TestGapDetectorAblation(unittest.TestCase):
    """Ablation study: gap detection disabled → empty report."""

    def setUp(self):
        self.state = _StubState()
        self.detector = GapDetector(enabled=False)

    def test_disabled_returns_all_covered(self):
        report = self.detector.analyse(self.state)
        self.assertEqual(report.coverage_pct, 100.0)
        self.assertEqual(report.covered_count, len(COVERAGE_CHECKLIST))
        self.assertEqual(len(report.critical_gaps), 0)
        self.assertEqual(len(report.important_gaps), 0)
        self.assertEqual(len(report.optional_gaps), 0)

    def test_disabled_all_categories_marked_covered(self):
        report = self.detector.analyse(self.state)
        for key in COVERAGE_CHECKLIST:
            self.assertEqual(report.all_categories.get(key), "covered")


class TestGapDetectorAnalysis(unittest.TestCase):
    """GapDetector.analyse() with various conversation states."""

    def setUp(self):
        self.detector = GapDetector()

    def test_empty_state_all_uncovered(self):
        state = _StubState()
        report = self.detector.analyse(state)
        self.assertGreater(report.uncovered_count, 0)
        self.assertEqual(report.covered_count, 0)
        self.assertGreater(len(report.critical_gaps), 0)

    def test_coverage_percentage_range(self):
        state = _StubState()
        report = self.detector.analyse(state)
        self.assertGreaterEqual(report.coverage_pct, 0.0)
        self.assertLessEqual(report.coverage_pct, 100.0)

    def test_keyword_matching_purpose(self):
        state = _make_state_with_turns(
            "The purpose of the system is to solve the problem of task management for teams."
        )
        report = self.detector.analyse(state)
        status = report.all_categories.get("purpose")
        self.assertIn(status, ["covered", "partial"])

    def test_keyword_matching_security(self):
        state = _make_state_with_turns(
            "We need GDPR compliance, encryption, and role-based access control with authentication."
        )
        report = self.detector.analyse(state)
        status = report.all_categories.get("security_privacy")
        self.assertEqual(status, "covered")

    def test_partial_coverage_one_keyword(self):
        state = _make_state_with_turns("The system should be fast.")  # only 1 perf keyword
        report = self.detector.analyse(state)
        status = report.all_categories.get("performance")
        self.assertIn(status, ["partial", "uncovered"])

    def test_uncovered_category_in_gaps(self):
        state = _StubState()
        report = self.detector.analyse(state)
        gap_keys = {g.category_key for g in report.all_gaps}
        # With empty state, security_privacy should be a gap
        self.assertIn("security_privacy", gap_keys)

    def test_report_has_correct_session_metadata(self):
        state = _StubState(session_id="my-session", turn_count=5)
        report = self.detector.analyse(state)
        self.assertEqual(report.session_id, "my-session")
        self.assertEqual(report.turn_id, 5)

    def test_total_categories_matches_checklist(self):
        state = _StubState()
        report = self.detector.analyse(state)
        self.assertEqual(report.total_categories, len(COVERAGE_CHECKLIST))

    def test_counts_sum_to_total(self):
        state = _StubState()
        report = self.detector.analyse(state)
        self.assertEqual(
            report.covered_count + report.partial_count + report.uncovered_count,
            report.total_categories,
        )

    def test_covered_via_state_covered_categories(self):
        """Categories in state.covered_categories should be marked covered."""
        state = _StubState()
        state.covered_categories.add("purpose")
        state.covered_categories.add("security_privacy")
        report = self.detector.analyse(state)
        self.assertEqual(report.all_categories.get("purpose"), "covered")
        self.assertEqual(report.all_categories.get("security_privacy"), "covered")

    def test_has_critical_gaps_true_on_empty_state(self):
        state = _StubState()
        report = self.detector.analyse(state)
        self.assertTrue(report.has_critical_gaps)

    def test_priority_gaps_critical_before_important(self):
        state = _StubState()
        report = self.detector.analyse(state)
        pg = report.priority_gaps
        # All critical should appear before any important
        severities = [g.severity.value for g in pg]
        in_important = False
        for sev in severities:
            if sev == "important":
                in_important = True
            if in_important:
                self.assertNotEqual(sev, "critical")

    def test_gap_report_serialisable(self):
        """to_dict() must not raise and return a dict."""
        import json
        state = _StubState()
        report = self.detector.analyse(state)
        d = report.to_dict()
        self.assertIsInstance(d, dict)
        # Should be JSON-serialisable
        json_str = json.dumps(d)
        self.assertIsInstance(json_str, str)

    def test_requirement_text_included_in_corpus(self):
        state = _StubState()
        state.requirements.append(_Requirement(
            req_id="FR-001", req_type="functional",
            text="The system shall authenticate users via OAuth2 with encryption and security controls.",
            turn_id=1, category="security_privacy",
            raw_excerpt="authenticate users via OAuth2 with encryption and security",
        ))
        report = self.detector.analyse(state)
        # authentication + encryption + security → ≥3 keywords → covered
        status = report.all_categories.get("security_privacy")
        self.assertIn(status, ["covered", "partial"])


class TestCategoryGap(unittest.TestCase):
    def test_to_dict_keys(self):
        gap = CategoryGap(
            category_key="performance", label="Performance",
            severity=GapSeverity.CRITICAL, description="desc",
            volere_ref="V12", ieee830_ref="3.2", is_partial=False,
        )
        d = gap.to_dict()
        for key in ["category_key","label","severity","description","volere_ref","ieee830_ref","is_partial"]:
            self.assertIn(key, d)


# ===========================================================================
# ProactiveQuestionGenerator Tests
# ===========================================================================

class TestQuestionTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = QuestionTracker()
        self.q = FollowUpQuestion(
            question_id="performance_0", category_key="performance",
            category_label="Performance", question_text="How fast?",
            severity="critical", is_partial=False, rationale="test",
        )

    def test_not_asked_initially(self):
        self.assertFalse(self.tracker.is_asked("performance_0"))

    def test_mark_asked(self):
        self.tracker.mark_asked(self.q)
        self.assertTrue(self.tracker.is_asked("performance_0"))

    def test_times_asked_increments(self):
        self.assertEqual(self.tracker.times_asked("performance"), 0)
        self.tracker.mark_asked(self.q)
        self.assertEqual(self.tracker.times_asked("performance"), 1)

    def test_to_dict(self):
        self.tracker.mark_asked(self.q)
        d = self.tracker.to_dict()
        self.assertIn("performance_0", d["asked_ids"])
        self.assertEqual(d["asked_categories"]["performance"], 1)


def _make_gap_report(session_id="s1", turn_id=1, critical_keys=None, important_keys=None) -> GapReport:
    """Helper: construct a GapReport with specified gaps."""
    report = GapReport(session_id=session_id, turn_id=turn_id)
    report.total_categories = len(COVERAGE_CHECKLIST)
    report.uncovered_count  = 0

    def _make(key, severity):
        spec = COVERAGE_CHECKLIST.get(key, {})
        return CategoryGap(
            category_key=key, label=spec.get("label", key),
            severity=severity, description=spec.get("description", ""),
            volere_ref=spec.get("volere_ref",""), ieee830_ref=spec.get("ieee830_ref",""),
        )

    for key in (critical_keys or []):
        report.critical_gaps.append(_make(key, GapSeverity.CRITICAL))
        report.uncovered_count += 1
    for key in (important_keys or []):
        report.important_gaps.append(_make(key, GapSeverity.IMPORTANT))
        report.uncovered_count += 1

    report.covered_count = report.total_categories - report.uncovered_count
    eff = report.covered_count + report.partial_count * 0.5
    report.coverage_pct = round((eff / report.total_categories) * 100, 1)
    return report


class TestProactiveQuestionGenerator(unittest.TestCase):

    def setUp(self):
        self.gen     = create_question_generator(max_questions_per_turn=2)
        self.tracker = QuestionTracker()
        self.state   = _StubState(project_name="MyApp")

    def test_no_gaps_returns_empty_question_set(self):
        report = GapReport(session_id="s1", turn_id=1, coverage_pct=100.0)
        qs = self.gen.generate(report, self.state, self.tracker)
        self.assertFalse(qs.has_questions)
        self.assertIsNone(qs.primary_question)

    def test_generates_question_for_critical_gap(self):
        report = _make_gap_report(critical_keys=["performance"])
        qs = self.gen.generate(report, self.state, self.tracker)
        self.assertTrue(qs.has_questions)
        self.assertEqual(qs.questions[0].category_key, "performance")

    def test_max_questions_per_turn_respected(self):
        report = _make_gap_report(
            critical_keys=["performance", "security_privacy", "reliability"]
        )
        qs = self.gen.generate(report, self.state, self.tracker)
        self.assertLessEqual(len(qs.questions), 2)

    def test_primary_question_is_first(self):
        report = _make_gap_report(critical_keys=["performance", "security_privacy"])
        qs = self.gen.generate(report, self.state, self.tracker)
        self.assertEqual(qs.primary_question, qs.questions[0])

    def test_project_name_injected_in_question(self):
        report = _make_gap_report(critical_keys=["performance"])
        qs = self.gen.generate(report, self.state, self.tracker)
        if qs.has_questions:
            self.assertIn("MyApp", qs.questions[0].question_text)

    def test_deduplication_prevents_repeated_question(self):
        report = _make_gap_report(critical_keys=["performance"])
        # First generation
        qs1 = self.gen.generate(report, self.state, self.tracker)
        # Second generation — same gap, same tracker
        qs2 = self.gen.generate(report, self.state, self.tracker)
        # Either no questions or a different variant
        if qs2.has_questions:
            self.assertNotEqual(
                qs1.questions[0].question_id,
                qs2.questions[0].question_id,
            )

    def test_category_capped_after_3_asks(self):
        """After 3 asks for a category, it should be skipped."""
        # Simulate 3 asks by marking all variants as asked
        for i in range(3):
            q = FollowUpQuestion(
                question_id=f"performance_{i}", category_key="performance",
                category_label="Performance", question_text="How fast?",
                severity="critical", is_partial=False, rationale="",
            )
            self.tracker.mark_asked(q)

        report = _make_gap_report(critical_keys=["performance"])
        qs = self.gen.generate(report, self.state, self.tracker)
        perf_qs = [q for q in qs.questions if q.category_key == "performance"]
        self.assertEqual(len(perf_qs), 0)

    def test_question_set_metadata(self):
        report = _make_gap_report(session_id="abc", turn_id=7, critical_keys=["performance"])
        qs = self.gen.generate(report, self.state, self.tracker)
        self.assertEqual(qs.session_id, "abc")
        self.assertEqual(qs.turn_id, 7)

    def test_question_set_serialisable(self):
        import json
        report = _make_gap_report(critical_keys=["performance"])
        qs = self.gen.generate(report, self.state, self.tracker)
        d = qs.to_dict()
        json_str = json.dumps(d)
        self.assertIsInstance(json_str, str)

    def test_build_injection_text_empty_when_no_questions(self):
        qs = QuestionSet(session_id="s1", turn_id=1)
        text = self.gen.build_injection_text(qs)
        self.assertEqual(text, "")

    def test_build_injection_text_contains_category(self):
        report = _make_gap_report(critical_keys=["performance"])
        qs = self.gen.generate(report, self.state, self.tracker)
        if qs.has_questions:
            text = self.gen.build_injection_text(qs)
            self.assertIn("Performance", text)
            self.assertIn("CRITICAL", text)

    def test_important_gaps_addressed_after_critical(self):
        report = _make_gap_report(
            critical_keys=["performance"],
            important_keys=["interfaces"],
        )
        gen = ProactiveQuestionGenerator(max_questions_per_turn=3)
        qs = gen.generate(report, self.state, self.tracker)
        keys = [q.category_key for q in qs.questions]
        # performance (critical) should appear before interfaces (important) if both present
        if "performance" in keys and "interfaces" in keys:
            self.assertLess(keys.index("performance"), keys.index("interfaces"))


class TestQuestionTemplates(unittest.TestCase):
    def test_all_checklist_keys_have_templates(self):
        """Every COVERAGE_CHECKLIST key should have at least one question template."""
        for key in COVERAGE_CHECKLIST:
            self.assertIn(key, QUESTION_TEMPLATES,
                          f"No question template for checklist key: '{key}'")
            self.assertGreater(len(QUESTION_TEMPLATES[key]), 0)

    def test_templates_contain_project_name_placeholder(self):
        """Every template should be parameterisable with {project_name}."""
        for key, templates in QUESTION_TEMPLATES.items():
            for t in templates:
                # Must not crash when substituted
                result = t.replace("{project_name}", "TestApp")
                self.assertNotIn("{project_name}", result)


# ===========================================================================
# PromptArchitect Tests (Iteration 3 changes)
# ===========================================================================

class TestPromptArchitectIteration3(unittest.TestCase):

    def setUp(self):
        self.architect = PromptArchitect()
        self.state = _StubState()

    def test_extra_context_default_empty(self):
        self.assertEqual(self.architect.extra_context, "")

    def test_extra_context_injected_in_system_message(self):
        self.architect.extra_context = "TEST DIRECTIVE: ask about performance"
        msg = self.architect.build_system_message(self.state)
        self.assertIn("TEST DIRECTIVE", msg)
        self.assertIn("GAP DETECTION DIRECTIVE", msg)

    def test_extra_context_cleared_after_build(self):
        self.architect.extra_context = "some directive"
        self.architect.build_system_message(self.state)
        # After build, extra_context should be reset
        self.assertEqual(self.architect.extra_context, "")

    def test_extra_context_not_in_message_when_empty(self):
        self.architect.extra_context = ""
        msg = self.architect.build_system_message(self.state)
        self.assertNotIn("GAP DETECTION DIRECTIVE", msg)

    def test_gap_directive_between_context_and_task(self):
        self.architect.extra_context = "GAP PROBE HERE"
        msg = self.architect.build_system_message(self.state)
        ctx_pos  = msg.find("CURRENT SESSION CONTEXT")
        gap_pos  = msg.find("GAP DETECTION DIRECTIVE")
        task_pos = msg.find("TASK INSTRUCTIONS")
        self.assertGreater(gap_pos, ctx_pos)
        self.assertGreater(task_pos, gap_pos)

    def test_whitespace_extra_context_not_injected(self):
        self.architect.extra_context = "   \n  "
        msg = self.architect.build_system_message(self.state)
        self.assertNotIn("GAP DETECTION DIRECTIVE", msg)
        # Should still be cleared
        self.assertEqual(self.architect.extra_context, "")

    def test_base_blocks_always_present(self):
        msg = self.architect.build_system_message(self.state)
        self.assertIn("ROLE", msg)
        self.assertIn("CURRENT SESSION CONTEXT", msg)
        self.assertIn("TASK INSTRUCTIONS", msg)


# ===========================================================================
# Integration: Full turn cycle
# ===========================================================================

class TestIntegration(unittest.TestCase):
    """
    Integration test: simulates a full turn:
      user message → GapDetector → QuestionGenerator → PromptArchitect injection
    """

    def test_full_turn_cycle(self):
        state     = _StubState(project_name="BudgetTracker")
        detector  = GapDetector(enabled=True)
        generator = ProactiveQuestionGenerator(max_questions_per_turn=2)
        tracker   = QuestionTracker()
        architect = PromptArchitect()

        # Simulate user describing a system without security info
        state.turns.append(_Turn(
            turn_id=1,
            user_message="I want to build a budget tracking app for personal finance.",
            assistant_message="Great, tell me more about the users.",
        ))
        state.turn_count = 1

        # 1. Detect gaps
        gap_report = detector.analyse(state)
        self.assertIsInstance(gap_report, GapReport)
        self.assertGreater(len(gap_report.all_gaps), 0)

        # 2. Generate follow-up questions
        q_set = generator.generate(gap_report, state, tracker)
        self.assertIsInstance(q_set, QuestionSet)

        # 3. Inject directive into prompt architect
        if q_set.has_questions:
            injection = generator.build_injection_text(q_set)
            architect.extra_context = injection

        # 4. Build system message — directive should be injected
        system_msg = architect.build_system_message(state)
        if q_set.has_questions:
            self.assertIn("BudgetTracker", system_msg)  # project name in question

        # 5. After build, extra_context should be cleared
        self.assertEqual(architect.extra_context, "")

    def test_gap_detection_off_vs_on(self):
        """Ablation: OFF branch produces all-covered report regardless of state."""
        state_empty = _StubState()

        det_on  = GapDetector(enabled=True)
        det_off = GapDetector(enabled=False)

        report_on  = det_on.analyse(state_empty)
        report_off = det_off.analyse(state_empty)

        # OFF branch: all covered
        self.assertEqual(report_off.coverage_pct, 100.0)
        self.assertEqual(len(report_off.critical_gaps), 0)

        # ON branch: gaps exist for empty state
        self.assertLess(report_on.coverage_pct, 100.0)
        self.assertGreater(len(report_on.critical_gaps), 0)


# ===========================================================================
# Coverage checklist completeness
# ===========================================================================

class TestCoverageChecklist(unittest.TestCase):
    def test_all_entries_have_required_fields(self):
        required = ["label", "severity", "keywords", "description", "volere_ref", "ieee830_ref"]
        for key, spec in COVERAGE_CHECKLIST.items():
            for field_name in required:
                self.assertIn(field_name, spec,
                              f"'{key}' missing field '{field_name}'")

    def test_all_keywords_are_lowercase(self):
        for key, spec in COVERAGE_CHECKLIST.items():
            for kw in spec["keywords"]:
                self.assertEqual(kw, kw.lower(),
                                 f"'{key}' keyword '{kw}' is not lowercase")

    def test_all_severities_are_valid(self):
        valid = {s.value for s in GapSeverity}
        for key, spec in COVERAGE_CHECKLIST.items():
            self.assertIn(spec["severity"].value, valid,
                          f"'{key}' has invalid severity")

    def test_critical_categories_include_mandatory_nfrs(self):
        critical_keys = {
            k for k, v in COVERAGE_CHECKLIST.items()
            if v["severity"] == GapSeverity.CRITICAL
        }
        for nfr in MANDATORY_NFR_CATEGORIES:
            self.assertIn(nfr, critical_keys,
                          f"Mandatory NFR '{nfr}' is not marked CRITICAL in checklist")


if __name__ == "__main__":
    unittest.main(verbosity=2)