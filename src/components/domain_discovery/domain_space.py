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

    @property
    def decomposed(self) -> bool:
        """Backward-compat shim — True only when decomposed at least once."""
        return self.decompose_count > 0

    def to_dict(self) -> dict:
        return {"label":self.label,"req_ids":self.req_ids,"status":self.status,
                "probe_question":self.probe_question,
                "sub_dimensions":dict(self.sub_dimensions),
                "probe_count":self.probe_count,"decompose_count":self.decompose_count}

    @property
    def covered_subdim_count(self) -> int:
        return sum(1 for ids in self.sub_dimensions.values() if ids)

    @property
    def needs_deeper_probing(self) -> bool:
        if self.status in ("excluded","confirmed"):
            return False
        return len(self.req_ids) < 3