from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class DomainSpec:
    label: str
    req_ids: list[str] = field(default_factory=list)
    status: str = "unprobed"
    probe_question: str = ""
    sub_dimensions: dict[str, list[str]] = field(default_factory=dict)
    probe_count: int = 0
    decompose_count: int = 0
    user_locked: bool = False  # True when status was set manually via UI

    # Stores coverage check result — keys are dimension labels,
    # values are "covered" | "pending". Persists across turns.
    # Set by DomainDiscovery.check_domain_coverage() after each update.
    covered_dimensions: dict[str, str] = field(default_factory=dict)

    @property
    def decomposed(self) -> bool:
        return self.decompose_count > 0

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "req_ids": self.req_ids,
            "status": self.status,
            "probe_question": self.probe_question,
            "sub_dimensions": dict(self.sub_dimensions),
            "probe_count": self.probe_count,
            "decompose_count": self.decompose_count,
            "user_locked": self.user_locked,
            "covered_dimensions": dict(self.covered_dimensions),
        }

    @property
    def covered_subdim_count(self) -> int:
        return sum(1 for ids in self.sub_dimensions.values() if ids)

    @property
    def needs_deeper_probing(self) -> bool:
        if self.status in ("excluded", "confirmed"):
            return False
        return len(self.req_ids) < 3

    @property
    def uncovered_dimensions(self) -> list[str]:
        """Return dimension labels that are still pending."""
        return [
            dim for dim, state in self.covered_dimensions.items()
            if state == "pending"
        ]

    @property
    def coverage_fraction(self) -> float:
        """Fraction of dimensions marked covered. 0.0 if no check run yet."""
        if not self.covered_dimensions:
            return 0.0
        covered = sum(1 for s in self.covered_dimensions.values() if s == "covered" or s == "deferred" or s == "out_of_scope" or s == "excluded")
        return covered / len(self.covered_dimensions)