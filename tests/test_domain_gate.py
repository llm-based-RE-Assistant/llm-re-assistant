"""
Unit tests for DomainGate and DomainSpec.

Tests cover:
- Domain status transitions (unprobed → partial → confirmed → excluded)
- is_satisfied logic (80% coverage fraction + all-probed requirement)
- completeness_pct calculation
- active_count / confirmed_count / done_count properties
- next_unprobed() priority ordering
- Edge cases: empty gate, all-excluded gate, unseeded gate
- to_dict() serialization
"""

import sys
import types

# Stub only what domain_gate.py imports that we can't easily satisfy
# Register BEFORE importing real modules

# Stub utils constant — domain_gate only needs _DOMAIN_GATE_COVERAGE_FRACTION
if "src.components.domain_discovery.utils" not in sys.modules:
    _utils = types.ModuleType("src.components.domain_discovery.utils")
    _utils._DOMAIN_GATE_COVERAGE_FRACTION = 0.8
    sys.modules["src.components.domain_discovery.utils"] = _utils

# Now import the real classes (both have no other heavy dependencies)
from src.components.domain_discovery.domain_space import DomainSpec   # noqa: E402
from src.components.domain_discovery.domain_gate import DomainGate    # noqa: E402


# Helpers
def _make_domain(label, status="unprobed", req_count=0, probe_count=0):
    d = DomainSpec(label=label)
    d.status = status
    d.req_ids = [f"FR-{i:03d}" for i in range(req_count)]
    d.probe_count = probe_count
    return d


def _gate(**kv):
    """
    _gate(auth=("confirmed", 3, 1), reporting=("unprobed", 0, 0))
    Each value: (status, req_count, probe_count)
    """
    gate = DomainGate(seeded=True)
    for key, (status, req_count, probe_count) in kv.items():
        gate.domains[key] = _make_domain(key, status, req_count, probe_count)
    return gate


# DomainSpec
class TestDomainSpec:

    def test_default_status_is_unprobed(self):
        d = DomainSpec(label="auth")
        assert d.status == "unprobed"

    def test_decomposed_false_by_default(self):
        d = DomainSpec(label="auth")
        assert d.decomposed is False

    def test_decomposed_true_after_increment(self):
        d = DomainSpec(label="auth")
        d.decompose_count = 1
        assert d.decomposed is True

    def test_needs_deeper_probing_true_when_few_reqs(self):
        d = _make_domain("auth", status="partial", req_count=2)
        assert d.needs_deeper_probing is True

    def test_needs_deeper_probing_false_when_confirmed(self):
        d = _make_domain("auth", status="confirmed", req_count=3)
        assert d.needs_deeper_probing is False

    def test_needs_deeper_probing_false_when_excluded(self):
        d = _make_domain("auth", status="excluded", req_count=0)
        assert d.needs_deeper_probing is False

    def test_needs_deeper_probing_false_when_three_or_more_reqs(self):
        d = _make_domain("auth", status="partial", req_count=3)
        assert d.needs_deeper_probing is False

    def test_covered_subdim_count(self):
        d = DomainSpec(label="auth")
        d.sub_dimensions = {
            "data": ["FR-001"],
            "actions": [],
            "constraints": ["FR-002"],
        }
        assert d.covered_subdim_count == 2

    def test_to_dict_has_correct_keys(self):
        d = DomainSpec(label="auth")
        assert set(d.to_dict().keys()) == {
            "label", "req_ids", "status", "probe_question",
            "sub_dimensions", "probe_count", "decompose_count",
        }


# DomainGate — counts
class TestDomainGateCounts:

    def test_total_counts_all(self):
        gate = _gate(auth=("confirmed", 3, 1), reporting=("unprobed", 0, 0))
        assert gate.total == 2

    def test_active_count_excludes_excluded(self):
        gate = _gate(auth=("confirmed", 3, 1), legacy=("excluded", 0, 0))
        assert gate.active_count == 1

    def test_confirmed_count(self):
        gate = _gate(
            auth=("confirmed", 3, 1),
            reporting=("partial", 1, 1),
            billing=("confirmed", 4, 1),
        )
        assert gate.confirmed_count == 2

    def test_done_count_includes_confirmed_and_excluded(self):
        gate = _gate(
            auth=("confirmed", 3, 1),
            legacy=("excluded", 0, 0),
            reporting=("partial", 1, 1),
        )
        assert gate.done_count == 2

    def test_empty_gate_total_zero(self):
        gate = DomainGate(seeded=True)
        assert gate.total == 0


# DomainGate — completeness_pct
class TestCompletenessPct:

    def test_all_confirmed_is_100(self):
        gate = _gate(auth=("confirmed", 3, 1), reporting=("confirmed", 3, 1))
        assert gate.completeness_pct == 100

    def test_half_confirmed_is_50(self):
        gate = _gate(auth=("confirmed", 3, 1), reporting=("partial", 1, 1))
        assert gate.completeness_pct == 50

    def test_all_excluded_returns_100(self):
        gate = _gate(auth=("excluded", 0, 0))
        assert gate.completeness_pct == 100

    def test_none_confirmed_is_0(self):
        gate = _gate(auth=("unprobed", 0, 0), reporting=("partial", 1, 1))
        assert gate.completeness_pct == 0

    def test_excluded_not_in_denominator(self):
        gate = _gate(
            auth=("confirmed", 3, 1),
            reporting=("partial", 1, 1),
            legacy=("excluded", 0, 0),
        )
        assert gate.completeness_pct == 50


# DomainGate — is_satisfied
class TestIsSatisfied:

    def test_false_when_not_seeded(self):
        gate = DomainGate(seeded=False)
        gate.domains["auth"] = _make_domain("auth", "confirmed", 3, 1)
        assert gate.is_satisfied is False

    def test_false_when_empty(self):
        assert DomainGate(seeded=True).is_satisfied is False

    def test_true_when_all_excluded(self):
        assert _gate(auth=("excluded", 0, 0)).is_satisfied is True

    def test_true_at_exactly_80_percent_all_probed(self):
        gate = _gate(
            a=("confirmed", 3, 1),
            b=("confirmed", 3, 1),
            c=("confirmed", 3, 1),
            d=("confirmed", 3, 1),
            e=("partial",   1, 1),
        )
        assert gate.is_satisfied is True

    def test_false_below_80_percent(self):
        gate = _gate(
            a=("confirmed", 3, 1),
            b=("confirmed", 3, 1),
            c=("confirmed", 3, 1),
            d=("partial",   1, 1),
            e=("partial",   1, 1),
        )
        assert gate.is_satisfied is False

    def test_false_when_unprobed_domain_exists(self):
        gate = _gate(
            a=("confirmed", 3, 1),
            b=("confirmed", 3, 1),
            c=("confirmed", 3, 1),
            d=("confirmed", 3, 1),
            e=("unprobed",  0, 0),
        )
        assert gate.is_satisfied is False

    def test_true_when_unconfirmed_but_probed(self):
        gate = _gate(
            a=("confirmed", 3, 1),
            b=("confirmed", 3, 1),
            c=("confirmed", 3, 1),
            d=("confirmed", 3, 1),
            e=("partial",   1, 1),
        )
        assert gate.is_satisfied is True

    def test_excluded_probe_count_zero_does_not_block(self):
        gate = _gate(
            a=("confirmed", 3, 1),
            b=("confirmed", 3, 1),
            c=("confirmed", 3, 1),
            d=("confirmed", 3, 1),
            legacy=("excluded", 0, 0),
        )
        assert gate.is_satisfied is True

    def test_all_confirmed_is_satisfied(self):
        gate = _gate(auth=("confirmed", 3, 1), reporting=("confirmed", 4, 2))
        assert gate.is_satisfied is True


# DomainGate — next_unprobed
class TestNextUnprobed:

    def test_returns_unprobed_first(self):
        gate = _gate(auth=("unprobed", 0, 0), reporting=("partial", 1, 1))
        result = gate.next_unprobed()
        assert result is not None
        assert result.label == "auth"

    def test_returns_partial_when_no_unprobed(self):
        gate = _gate(auth=("confirmed", 3, 1), reporting=("partial", 1, 1))
        result = gate.next_unprobed()
        assert result is not None
        assert result.label == "reporting"

    def test_returns_none_when_all_confirmed(self):
        gate = _gate(auth=("confirmed", 3, 1), reporting=("confirmed", 4, 1))
        assert gate.next_unprobed() is None

    def test_returns_none_when_all_excluded(self):
        gate = _gate(auth=("excluded", 0, 0))
        assert gate.next_unprobed() is None

    def test_partial_with_enough_reqs_not_returned(self):
        gate = _gate(auth=("confirmed", 3, 1), reporting=("partial", 3, 1))
        assert gate.next_unprobed() is None


# DomainGate — to_dict
class TestToDictGate:

    def test_to_dict_has_required_keys(self):
        gate = _gate(auth=("confirmed", 3, 1))
        d = gate.to_dict()
        for key in ["seeded", "seed_turn", "reseed_turn", "total",
                    "active_count", "confirmed_count", "done_count",
                    "is_satisfied", "completeness_pct", "domains"]:
            assert key in d, f"Missing key: {key}"

    def test_to_dict_domains_serialized(self):
        gate = _gate(auth=("confirmed", 3, 1))
        d = gate.to_dict()
        assert "auth" in d["domains"]
        assert d["domains"]["auth"]["status"] == "confirmed"