"""
Unit tests for GapDetector.

Tests cover:
- GapReport structure and all_gaps aggregation
- CategoryGap to_dict() serialization
- GapDetector disabled mode (returns full coverage)
- NFR category coverage classification (uncovered / partial / covered)
- Domain gate gap injection for unprobed and partial domains
- _classify_functional_coverage() static method
- Coverage percentage calculation
- create_gap_detector() factory
"""

import sys
import types
from enum import Enum

# Stubs — register BEFORE importing any src module.
# gap_detector.py imports:
#   from src.components.domain_discovery.utils import NFR_CATEGORIES, COVERAGE_CHECKLIST, GapSeverity
#   from src.components.system_prompt.prompt_architect import MIN_NFR_PER_CATEGORY
# We must provide real-enough values for those.

# --- GapSeverity (mirrors real enum) ---
class GapSeverity(Enum):
    CRITICAL  = "critical"
    IMPORTANT = "important"
    OPTIONAL  = "optional"

NFR_CATEGORIES = [
    "performance", "security_privacy", "reliability",
    "usability", "maintainability", "compatibility",
]

COVERAGE_CHECKLIST = {
    "performance": {
        "label": "Performance",
        "severity": GapSeverity.CRITICAL,
        "description": "No performance requirements elicited.",
        "ieee830_ref": "§3.3",
    },
    "security_privacy": {
        "label": "Security & Privacy",
        "severity": GapSeverity.CRITICAL,
        "description": "No security requirements elicited.",
        "ieee830_ref": "§3.6",
    },
    "reliability": {
        "label": "Reliability",
        "severity": GapSeverity.IMPORTANT,
        "description": "No reliability requirements elicited.",
        "ieee830_ref": "§3.6",
    },
    "usability": {
        "label": "Usability",
        "severity": GapSeverity.IMPORTANT,
        "description": "No usability requirements elicited.",
        "ieee830_ref": "§3.6",
    },
    "maintainability": {
        "label": "Maintainability",
        "severity": GapSeverity.OPTIONAL,
        "description": "No maintainability requirements elicited.",
        "ieee830_ref": "§3.6",
    },
    "compatibility": {
        "label": "Compatibility",
        "severity": GapSeverity.OPTIONAL,
        "description": "No compatibility requirements elicited.",
        "ieee830_ref": "§3.6",
    },
}

# Register domain_discovery.utils stub — always update attrs in case already registered
if "src.components.domain_discovery.utils" not in sys.modules:
    sys.modules["src.components.domain_discovery.utils"] = types.ModuleType(
        "src.components.domain_discovery.utils"
    )
_du = sys.modules["src.components.domain_discovery.utils"]
_du._DOMAIN_GATE_COVERAGE_FRACTION = 0.8
_du.NFR_CATEGORIES     = NFR_CATEGORIES
_du.COVERAGE_CHECKLIST = COVERAGE_CHECKLIST
_du.GapSeverity        = GapSeverity

# Register prompt_architect stub — always update attrs
if "src.components.system_prompt.prompt_architect" not in sys.modules:
    sys.modules["src.components.system_prompt.prompt_architect"] = types.ModuleType(
        "src.components.system_prompt.prompt_architect"
    )
_pa = sys.modules["src.components.system_prompt.prompt_architect"]
_pa.MIN_NFR_PER_CATEGORY = 2
_pa.MIN_FUNCTIONAL_REQS  = 10
_pa.IEEE830_CATEGORIES   = {}
_pa.PHASE4_SECTIONS      = set()

# Now import the real classes
from src.components.gap_detector import (   # noqa: E402
    GapDetector, GapReport, CategoryGap, create_gap_detector,
)


# Minimal state mock

class _MockDomain:
    def __init__(self, label, status="unprobed", probe_count=0, req_ids=None):
        self.label       = label
        self.status      = status
        self.probe_count = probe_count
        self.req_ids     = req_ids or []
        self.probe_question      = f"Tell me more about {label}."
        self.needs_deeper_probing = (
            status == "partial" and len(self.req_ids) < 3
        )


class _MockGate:
    def __init__(self, seeded=True, domains=None, is_satisfied=False):
        self.seeded       = seeded
        self.domains      = domains or {}
        self.is_satisfied = is_satisfied


class _MockState:
    def __init__(self, session_id="sess-001", nfr_coverage=None,
                 functional_count=0, gate=None, reqs=None):
        self.session_id         = session_id
        self.nfr_coverage       = nfr_coverage or {}
        self._functional_count  = functional_count
        self.domain_gate        = gate
        self.requirements       = reqs or {}
        self.srs_section_content     = {}
        self.phase4_sections_covered = set()
        self.domain_req_templates    = {}

    @property
    def turn_count(self):        return 1
    @property
    def functional_count(self):  return self._functional_count
    @property
    def covered_categories(self): return set()


# CategoryGap

class TestCategoryGap:

    def test_to_dict_has_correct_keys(self):
        gap = CategoryGap(
            category_key="performance",
            label="Performance",
            severity=GapSeverity.CRITICAL,
            description="No perf reqs",
        )
        assert set(gap.to_dict().keys()) == {
            "category_key", "label", "severity",
            "description", "ieee830_ref", "is_partial",
        }

    def test_severity_value_serialized(self):
        gap = CategoryGap(
            category_key="performance",
            label="Performance",
            severity=GapSeverity.CRITICAL,
            description="No perf reqs",
        )
        assert gap.to_dict()["severity"] == "critical"


# GapReport

class TestGapReport:

    def _sample(self):
        return GapReport(
            session_id="s1", turn_id=3,
            total_categories=6, covered_count=3, coverage_pct=50.0,
        )

    def test_all_gaps_aggregates_lists(self):
        r = self._sample()
        r.critical_gaps  = [CategoryGap("perf", "Perf", GapSeverity.CRITICAL,  "desc")]
        r.important_gaps = [CategoryGap("rel",  "Rel",  GapSeverity.IMPORTANT, "desc")]
        r.optional_gaps  = [CategoryGap("comp", "Comp", GapSeverity.OPTIONAL,  "desc")]
        assert len(r.all_gaps) == 3

    def test_to_dict_has_required_keys(self):
        d = self._sample().to_dict()
        for k in ["session_id", "turn_id", "total_categories",
                  "covered_count", "coverage_pct",
                  "critical_gaps", "important_gaps", "optional_gaps"]:
            assert k in d

    def test_coverage_pct_in_dict(self):
        assert self._sample().to_dict()["coverage_pct"] == 50.0


# GapDetector — disabled mode

class TestGapDetectorDisabled:

    def test_disabled_returns_100_percent(self):
        state  = _MockState()
        report = GapDetector(enabled=False).analyse(state)
        assert report.coverage_pct == 100.0

    def test_disabled_no_gaps(self):
        state  = _MockState()
        report = GapDetector(enabled=False).analyse(state)
        assert report.all_gaps == []

    def test_disabled_all_categories_covered(self):
        state  = _MockState()
        report = GapDetector(enabled=False).analyse(state)
        assert all(v == "covered" for v in report.all_categories.values())


# GapDetector — NFR coverage classification

class TestNFRCoverageClassification:

    def test_zero_nfr_is_uncovered(self):
        state  = _MockState(nfr_coverage={})
        report = GapDetector(enabled=True).analyse(state)
        assert report.all_categories.get("performance") == "uncovered"

    def test_one_nfr_is_partial(self):
        # MIN_NFR_PER_CATEGORY=2, count=1 → partial
        state  = _MockState(nfr_coverage={"performance": 1})
        report = GapDetector(enabled=True).analyse(state)
        assert report.all_categories.get("performance") == "partial"

    def test_two_nfrs_is_covered(self):
        nfr    = {cat: 2 for cat in NFR_CATEGORIES}
        state  = _MockState(nfr_coverage=nfr)
        report = GapDetector(enabled=True).analyse(state)
        for cat in NFR_CATEGORIES:
            assert report.all_categories.get(cat) == "covered", f"{cat} not covered"

    def test_partial_nfr_appears_in_gaps(self):
        state  = _MockState(nfr_coverage={"performance": 1})
        report = GapDetector(enabled=True).analyse(state)
        gap_keys = {g.category_key for g in report.all_gaps}
        assert "performance" in gap_keys

    def test_covered_nfr_not_in_gaps(self):
        nfr    = {cat: 2 for cat in NFR_CATEGORIES}
        state  = _MockState(nfr_coverage=nfr)
        report = GapDetector(enabled=True).analyse(state)
        gap_keys = {g.category_key for g in report.all_gaps}
        for cat in NFR_CATEGORIES:
            assert cat not in gap_keys


# GapDetector — domain gate gap injection

class TestDomainGateGapInjection:

    def _full_nfr(self):
        return {cat: 2 for cat in NFR_CATEGORIES}

    def test_unprobed_domain_injected_as_critical(self):
        gate  = _MockGate(seeded=True, domains={
            "authentication": _MockDomain("User Authentication",
                                          status="unprobed", probe_count=0),
        })
        state  = _MockState(nfr_coverage=self._full_nfr(), gate=gate)
        report = GapDetector(enabled=True).analyse(state)
        keys   = {g.category_key for g in report.critical_gaps}
        assert "domain_authentication" in keys

    def test_partial_domain_injected_as_critical(self):
        gate  = _MockGate(seeded=True, domains={
            "reporting": _MockDomain("Reporting",
                                     status="partial", probe_count=1,
                                     req_ids=["FR-001"]),
        })
        state  = _MockState(nfr_coverage=self._full_nfr(), gate=gate)
        report = GapDetector(enabled=True).analyse(state)
        keys   = {g.category_key for g in report.critical_gaps}
        assert "domain_reporting" in keys

    def test_excluded_domain_not_injected(self):
        gate  = _MockGate(seeded=True, domains={
            "legacy": _MockDomain("Legacy Module", status="excluded"),
        })
        state  = _MockState(nfr_coverage=self._full_nfr(), gate=gate)
        report = GapDetector(enabled=True).analyse(state)
        keys   = {g.category_key for g in report.critical_gaps}
        assert "domain_legacy" not in keys

    def test_confirmed_domain_not_injected(self):
        gate  = _MockGate(seeded=True, domains={
            "auth": _MockDomain("Authentication", status="confirmed",
                                probe_count=2,
                                req_ids=["FR-001", "FR-002", "FR-003"]),
        })
        state  = _MockState(nfr_coverage=self._full_nfr(), gate=gate)
        report = GapDetector(enabled=True).analyse(state)
        keys   = {g.category_key for g in report.critical_gaps}
        assert "domain_auth" not in keys

    def test_no_gate_produces_no_domain_gaps(self):
        state  = _MockState(nfr_coverage=self._full_nfr(), gate=None)
        report = GapDetector(enabled=True).analyse(state)
        domain_keys = [g.category_key for g in report.critical_gaps
                       if g.category_key.startswith("domain_")]
        assert domain_keys == []

    def test_unseeded_gate_produces_no_domain_gaps(self):
        gate  = _MockGate(seeded=False, domains={
            "auth": _MockDomain("Auth", status="unprobed"),
        })
        state  = _MockState(nfr_coverage=self._full_nfr(), gate=gate)
        report = GapDetector(enabled=True).analyse(state)
        domain_keys = [g.category_key for g in report.critical_gaps
                       if g.category_key.startswith("domain_")]
        assert domain_keys == []


# _classify_functional_coverage static method

class TestClassifyFunctionalCoverage:

    def test_zero_functional_is_uncovered(self):
        state  = _MockState(functional_count=0)
        result = GapDetector._classify_functional_coverage(state)
        assert result == "uncovered"

    def test_some_functional_no_gate_is_partial(self):
        state  = _MockState(functional_count=2)
        result = GapDetector._classify_functional_coverage(state)
        assert result in ("partial", "covered")

    def test_enough_functional_no_unprobed_is_covered(self):
        gate  = _MockGate(seeded=True, domains={
            "auth": _MockDomain("Auth", status="confirmed", probe_count=1),
        })
        state  = _MockState(functional_count=5, gate=gate)
        result = GapDetector._classify_functional_coverage(state)
        assert result == "covered"

    def test_unprobed_domain_keeps_partial(self):
        gate  = _MockGate(seeded=True, domains={
            "auth":      _MockDomain("Auth",      status="confirmed", probe_count=1),
            "reporting": _MockDomain("Reporting", status="unprobed",  probe_count=0),
        })
        state  = _MockState(functional_count=5, gate=gate)
        result = GapDetector._classify_functional_coverage(state)
        assert result == "partial"


# Coverage percentage

class TestCoveragePct:

    def test_zero_when_all_uncovered(self):
        state  = _MockState(nfr_coverage={})
        report = GapDetector(enabled=True).analyse(state)
        assert report.coverage_pct == 0.0

    def test_100_when_disabled(self):
        state  = _MockState()
        report = GapDetector(enabled=False).analyse(state)
        assert report.coverage_pct == 100.0


# Factory

def test_create_gap_detector_enabled():
    assert create_gap_detector(enabled=True).enabled is True

def test_create_gap_detector_disabled():
    assert create_gap_detector(enabled=False).enabled is False