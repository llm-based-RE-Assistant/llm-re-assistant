from __future__ import annotations
from dataclasses import dataclass, field
from src.components.domain_discovery.utils import NFR_CATEGORIES, COVERAGE_CHECKLIST, GapSeverity
from src.components.system_prompt.prompt_architect import MIN_NFR_PER_CATEGORY
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.components.conversation_state import ConversationState


# ---------------------------------------------------------------------------
# Gap report structures
# ---------------------------------------------------------------------------

@dataclass
class CategoryGap:
    category_key: str
    label:        str
    severity:     GapSeverity
    description:  str
    ieee830_ref:  str = ""
    is_partial:   bool = False

    def to_dict(self) -> dict:
        return {
            "category_key": self.category_key,
            "label":        self.label,
            "severity":     self.severity.value,
            "description":  self.description,
            "ieee830_ref":  self.ieee830_ref,
            "is_partial":   self.is_partial,
        }


@dataclass
class GapReport:
    session_id:      str
    turn_id:         int
    total_categories: int
    covered_count:   int
    coverage_pct:    float
    critical_gaps:   list[CategoryGap] = field(default_factory=list)
    important_gaps:  list[CategoryGap] = field(default_factory=list)
    optional_gaps:   list[CategoryGap] = field(default_factory=list)
    all_categories:  dict[str, str]    = field(default_factory=dict)

    @property
    def all_gaps(self) -> list[CategoryGap]:
        return self.critical_gaps + self.important_gaps + self.optional_gaps

    def to_dict(self) -> dict:
        return {
            "session_id":       self.session_id,
            "turn_id":          self.turn_id,
            "total_categories": self.total_categories,
            "covered_count":    self.covered_count,
            "coverage_pct":     self.coverage_pct,
            "critical_gaps":    [g.to_dict() for g in self.critical_gaps],
            "important_gaps":   [g.to_dict() for g in self.important_gaps],
            "optional_gaps":    [g.to_dict() for g in self.optional_gaps],
            "all_categories":   self.all_categories,
        }


# ---------------------------------------------------------------------------
# GapDetector
# ---------------------------------------------------------------------------

class GapDetector:

    COVERED_THRESHOLD_CRITICAL = 3
    COVERED_THRESHOLD_OTHER    = 2

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def analyse(self, state: "ConversationState") -> GapReport:
        if not self.enabled:
            return self._empty_report(state)

        report = GapReport(
            session_id       = state.session_id,
            turn_id          = state.turn_count,
            total_categories = len(COVERAGE_CHECKLIST),
            covered_count    = 0,
            coverage_pct     = 0.0,
        )

        for key, spec in COVERAGE_CHECKLIST.items():
            status = self._classify_coverage(key, spec, state)
            report.all_categories[key] = status
            if status == "covered":
                report.covered_count += 1
            elif status in ("partial", "uncovered"):
                gap = self._make_gap(key, spec, is_partial=(status == "partial"))
                self._add_gap(gap, spec["severity"], report)

        report.coverage_pct = round(
            report.covered_count / report.total_categories * 100, 1
        ) if report.total_categories > 0 else 0.0

        # Inject domain gate gaps
        self._inject_domain_gate_gaps(state, report)

        return report

    # ------------------------------------------------------------------
    # Domain gate gap injection — IT6-G1
    # ------------------------------------------------------------------

    def _inject_domain_gate_gaps(
        self, state: "ConversationState", report: GapReport
    ) -> None:
        """IT10b: Template-aware domain gap injection.

        When a domain req template exists for an unfinished domain, the gap
        description now lists the specific RE dimensions still uncovered rather
        than a generic probe question. This makes the gap report actionable —
        the developer reading the session log can see exactly what was missed,
        and the RE assistant's system prompt already uses the same template to
        guide elicitation.
        """
        gate = getattr(state, "domain_gate", None)
        if gate is None or not gate.seeded:
            return

        domain_templates = getattr(state, "domain_req_templates", {})
        existing_keys = {g.category_key for g in report.critical_gaps + report.important_gaps}

        for key, domain in gate.domains.items():
            if domain.status == "excluded":
                continue
            if not (domain.status in ("unprobed", "partial") or domain.needs_deeper_probing):
                continue

            synthetic_key = f"domain_{key}"
            if synthetic_key in existing_keys:
                continue

            # Build description: use template dimensions if available
            template = domain_templates.get(key, "")
            if template:
                # Summarise uncovered dimensions from the template
                template_lines = [ln.strip() for ln in template.splitlines() if ln.strip()]
                # Heuristic: a dimension is "covered" if a req for this domain
                # mentions any keyword from that line
                req_texts = " ".join(
                    state.requirements[rid].text.lower()
                    for rid in domain.req_ids
                    if rid in state.requirements
                )
                uncovered = []
                for line in template_lines:
                    # Extract first significant noun/phrase from line as probe keyword
                    probe_kw = line.split(":")[0].strip().lower() if ":" in line else line[:40].lower()
                    if probe_kw and probe_kw not in req_texts:
                        uncovered.append(line)
                if uncovered:
                    description = (
                        f"Coverage template dimensions not yet addressed for '{domain.label}':\n"
                        + "\n".join(f"  • {ln}" for ln in uncovered[:6])
                    )
                else:
                    description = (
                        f"Domain '{domain.label}' has a template but all dimensions appear "
                        f"covered — verify requirements are specific and measurable."
                    )
            else:
                description = domain.probe_question or f"Can you tell me more about {domain.label}?"

            gap = CategoryGap(
                category_key = synthetic_key,
                label        = domain.label,
                severity     = GapSeverity.CRITICAL,
                description  = description,
                ieee830_ref  = "§3.2 Functional Requirements",
                is_partial   = (domain.status != "unprobed"),
            )
            report.critical_gaps.append(gap)
            existing_keys.add(synthetic_key)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _classify_coverage(
        self,
        key: str,
        spec: dict,
        state: "ConversationState",
    ) -> str:
        if key in NFR_CATEGORIES:
            count = state.nfr_coverage.get(key, 0)
            if count >= MIN_NFR_PER_CATEGORY:
                return "covered"
            elif count >= 1:
                return "partial"
            return "uncovered"
        
        if key == "constraints":
            # Special case for constraints: if any reqs are tagged with "constraint" category, consider it covered.
            for req in state.requirements.values():
                if req.category and "constraint" in req.category.lower():
                    return "partial"
            return "uncovered"
        
        if key == "functional":
            # Special case for functional: if any reqs are tagged as functional, consider it covered.
            if state.domain_gate.is_satisfied:
                return "covered"
            else:
                for req in state.requirements.values():
                    if req.req_type == "functional":
                        return "partial"
                return "uncovered"

        # Special case for Sections Coverage.
        sections_ids = ["1.1", "1.2", "2.1", "2.3", "2.4", "2.5", "3.1.1", "3.1.3", "3.1.4"]
        sections = state.srs_section_content        
        if sections:
            for sec_id, content in sections:
                if spec["ieee830_ref"] == sec_id:
                    if len(content) >= 20:  # heuristic: if section has substantive content, consider it covered
                        return "covered"
                    else:
                        return "partial"
        else:
            for id in sections_ids:
                if spec["ieee830_ref"] == id:
                    return "uncovered"

    @staticmethod
    def _classify_functional_coverage(state: "ConversationState") -> str:
        count = state.functional_count
        if count == 0:
            return "uncovered"

        gate = getattr(state, "domain_gate", None)
        any_unprobed = False
        if gate is not None and gate.seeded:
            any_unprobed = any(
                d.status == "unprobed" for d in gate.domains.values()
            )

        if count >= 3 and not any_unprobed:
            return "covered"
        elif count >= 1:
            return "partial"
        return "uncovered"

    @staticmethod
    def _make_gap(key: str, spec: dict, is_partial: bool) -> CategoryGap:
        return CategoryGap(
            category_key = key,
            label        = spec["label"],
            severity     = spec["severity"],
            description  = spec["description"],
            ieee830_ref  = spec.get("ieee830_ref", ""),
            is_partial   = is_partial,
        )

    @staticmethod
    def _add_gap(gap: CategoryGap, severity: GapSeverity, report: GapReport) -> None:
        if severity == GapSeverity.CRITICAL:
            report.critical_gaps.append(gap)
        elif severity == GapSeverity.IMPORTANT:
            report.important_gaps.append(gap)
        else:
            report.optional_gaps.append(gap)

    @staticmethod
    def _empty_report(state: "ConversationState") -> GapReport:
        report = GapReport(
            session_id      = state.session_id,
            turn_id         = state.turn_count,
            total_categories= len(COVERAGE_CHECKLIST),
            covered_count   = len(COVERAGE_CHECKLIST),
            coverage_pct    = 100.0,
        )
        report.all_categories = {k: "covered" for k in COVERAGE_CHECKLIST}
        return report


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_gap_detector(enabled: bool = True) -> GapDetector:
    return GapDetector(enabled=enabled)