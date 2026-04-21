from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional
from src.components.domain_discovery.domain_space import DomainSpec
from src.components.domain_discovery.utils import DOMAIN_GATE_COVERAGE_FRACTION

@dataclass
class DomainGate:
    domains: dict[str, DomainSpec] = field(default_factory=dict)
    seeded: bool = False
    seed_turn: int = 0
    reseed_turn: int = 0
    last_updated: float = field(default_factory=time.time)

    @property
    def total(self) -> int:
        return len(self.domains)

    @property
    def active_count(self) -> int:
        """In-scope domains: total minus excluded."""
        return sum(1 for d in self.domains.values() if d.status != "excluded")

    @property
    def confirmed_count(self) -> int:
        """Domains that are confirmed (actively elicited + sufficient reqs)."""
        return sum(1 for d in self.domains.values() if d.status == "confirmed")

    @property
    def done_count(self) -> int:
        """Legacy: confirmed + excluded (used by completeness_pct and to_dict)."""
        return sum(1 for d in self.domains.values()
                   if d.status in ("confirmed", "excluded"))

    @property
    def is_satisfied(self) -> bool:
        """True when the domain gate can be considered complete.

        Requires ALL of:
        1. Gate has been seeded and has at least one domain.
        2. At least _DOMAIN_GATE_COVERAGE_FRACTION of in-scope (non-excluded)
           domains are confirmed. Excluded domains do not count toward the
           denominator — they were explicitly ruled out of scope.
        3. Every in-scope, unconfirmed domain has been probed at least once
           (probe_count >= 1), ensuring no domain was silently skipped.

        This property is the single source of truth for domain gate satisfaction.
        Both determine_elicitation_phase() and is_ready_for_srs() must use it
        so the two checks stay in sync.
        """
        if not self.seeded or self.total == 0:
            return False
        active = self.active_count
        if active == 0:
            return True  # all domains excluded — nothing to elicit
        confirmed = self.confirmed_count
        coverage_ok = (confirmed / active) >= DOMAIN_GATE_COVERAGE_FRACTION
        all_probed = all(
            d.probe_count >= 1 or d.status in ("confirmed", "excluded")
            for d in self.domains.values()
        )
        return coverage_ok and all_probed

    @property
    def completeness_pct(self) -> int:
        active = self.active_count
        if active == 0:
            return 100
        return round(self.confirmed_count / active * 100)

    def next_unprobed(self) -> Optional[DomainSpec]:
        """Return the next domain that needs elicitation.

        Priority: never-probed (unprobed) first, then partially-covered domains
        that still need deeper probing. Returns None when all in-scope domains
        are confirmed or excluded.
        """
        for d in self.domains.values():
            if d.status == "unprobed":
                return d
        for d in self.domains.values():
            if d.status == "partial" and d.needs_deeper_probing:
                return d
        return None

    def to_dict(self) -> dict:
        return {
            "seeded": self.seeded,
            "seed_turn": self.seed_turn,
            "reseed_turn": self.reseed_turn,
            "total": self.total,
            "active_count": self.active_count,
            "confirmed_count": self.confirmed_count,
            "done_count": self.done_count,
            "is_satisfied": self.is_satisfied,
            "completeness_pct": self.completeness_pct,
            "domains": {k: v.to_dict() for k, v in self.domains.items()},
        }