"""
src/components/gap_detector.py
===============
RE Assistant — Iteration 3 | University of Hildesheim
Requirements Coverage Checklist & Gap Detection Component

"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from conversation_state import ConversationState

from prompt_architect import (
    compute_domain_gate,
    DOMAIN_STATUS_UNPROBED,
    DOMAIN_STATUS_PARTIAL,
)


# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------

class GapSeverity(str, Enum):
    CRITICAL  = "critical"
    IMPORTANT = "important"
    OPTIONAL  = "optional"


# ---------------------------------------------------------------------------
# IEEE-830 / Volere unified coverage checklist
# ---------------------------------------------------------------------------

COVERAGE_CHECKLIST: dict[str, dict] = {
    # ── Section 1: Product Overview ──────────────────────────────────────────
    "purpose": {
        "label":       "System Purpose & Goals",
        "severity":    GapSeverity.CRITICAL,
        "keywords":    [
            "purpose", "goal", "objective", "aim", "vision", "mission",
            "problem", "solve", "we want", "we need", "the system should",
        ],
        "description": "What problem does the system solve and why does it exist?",
        "volere_ref":  "Section 1 — The Purpose of the Project",
        "ieee830_ref": "1.1 Purpose",
    },
    "scope": {
        "label":       "System Scope & Boundaries",
        "severity":    GapSeverity.CRITICAL,
        "keywords":    [
            "scope", "boundary", "in scope", "out of scope", "limit",
            "include", "exclude", "not include", "beyond", "within",
        ],
        "description": "What is inside and outside the system boundary?",
        "volere_ref":  "Section 1 — The Scope of the Work",
        "ieee830_ref": "1.2 Scope",
    },
    "stakeholders": {
        "label":       "Stakeholders & User Classes",
        "severity":    GapSeverity.CRITICAL,
        "keywords":    [
            "user", "stakeholder", "actor", "admin", "administrator",
            "customer", "client", "operator", "manager", "role", "persona",
            "end user", "who will use",
        ],
        "description": "Who are the users and stakeholders of the system?",
        "volere_ref":  "Section 3 — The Client, the Customer, and Other Stakeholders",
        "ieee830_ref": "2.2 User Classes and Characteristics",
    },

    # ── Section 2: Functional Requirements ───────────────────────────────────
    # FIX-G1/G2: functional coverage is now driven by the requirement store,
    # not keyword counting alone.  Keywords are still used for partial detection.
    "functional": {
        "label":       "Functional Requirements",
        "severity":    GapSeverity.CRITICAL,
        "keywords":    [
            "shall", "must do", "the system will", "feature", "capability",
            "allow users to", "enable users to", "the user can", "provide",
            "support the ability", "manage", "process", "create", "update",
            "delete", "view", "display", "notify", "authenticate", "search",
            "filter", "export", "import", "record", "track", "submit",
        ],
        "description": "What must the system do? Core features and behaviours.",
        "volere_ref":  "Section 9 — Functional Requirements",
        "ieee830_ref": "3.1 Functional Requirements",
        # Extra threshold: use requirement store count, not just keywords
        "_use_req_store": True,
    },
    "use_cases": {
        "label":       "Use Cases & User Stories",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "use case", "user story", "as a", "i want", "so that",
            "scenario", "workflow", "flow", "step", "sequence", "journey",
        ],
        "description": "How do users interact with the system step-by-step?",
        "volere_ref":  "Section 9 — Functional Requirements (scenarios)",
        "ieee830_ref": "3.1 Functional Requirements (scenarios)",
    },
    "business_rules": {
        "label":       "Business Rules & Constraints",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "rule", "policy", "regulation", "law", "compliance", "gdpr",
            "hipaa", "pci", "iso", "standard", "constraint", "restriction",
            "must not", "forbidden", "prohibited",
        ],
        "description": "What business rules and legal constraints must the system respect?",
        "volere_ref":  "Section 15 — Business Rules",
        "ieee830_ref": "2.5 Assumptions and Dependencies",
    },

    # ── Section 3: Non-Functional Requirements ────────────────────────────────
    "performance": {
        "label":       "Performance Requirements",
        "severity":    GapSeverity.CRITICAL,
        "keywords":    [
            "performance", "speed", "response time", "latency", "throughput",
            "tps", "requests per second", "load", "concurrent", "fast",
            "slow", "millisecond", "second", "minute", "benchmark",
        ],
        "description": "How fast must the system respond? What load must it handle?",
        "volere_ref":  "Section 12 — Performance Requirements",
        "ieee830_ref": "3.2 Performance Requirements",
    },
    "usability": {
        "label":       "Usability & Accessibility",
        "severity":    GapSeverity.CRITICAL,
        "keywords":    [
            "usability", "usable", "easy to use", "intuitive", "accessibility",
            "wcag", "ada", "screen reader", "keyboard", "mobile", "responsive",
            "ux", "user interface", "user experience", "learnability",
        ],
        "description": "How easy must the system be to use? Any accessibility requirements?",
        "volere_ref":  "Section 11 — Look and Feel Requirements",
        "ieee830_ref": "3.3 Usability Requirements",
    },
    "security_privacy": {
        "label":       "Security & Privacy Requirements",
        "severity":    GapSeverity.CRITICAL,
        "keywords":    [
            "security", "secure", "authentication", "authorisation", "authorization",
            "access control", "permission", "role-based", "rbac", "encryption",
            "ssl", "tls", "https", "privacy", "gdpr", "data protection",
            "personal data", "sensitive", "audit", "log", "intrusion",
        ],
        "description": "How must the system protect data and prevent unauthorised access?",
        "volere_ref":  "Section 13 — Security Requirements",
        "ieee830_ref": "3.6 Security Requirements",
    },
    "reliability": {
        "label":       "Reliability & Availability",
        "severity":    GapSeverity.CRITICAL,
        "keywords":    [
            "reliability", "available", "availability", "uptime", "downtime",
            "fault", "failure", "recovery", "backup", "redundancy", "failover",
            "sla", "service level", "99", "mtbf", "mttr", "resilient",
        ],
        "description": "How reliable must the system be? Expected uptime / recovery time?",
        "volere_ref":  "Section 12 — Reliability & Availability",
        "ieee830_ref": "3.4 Reliability Requirements",
    },
    "compatibility": {
        "label":       "Compatibility & Portability",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "compatibility", "compatible", "platform", "browser", "operating system",
            "windows", "mac", "linux", "android", "ios", "interoperability",
            "legacy", "migration", "integration",
        ],
        "description": "What platforms, browsers, and external systems must it support?",
        "volere_ref":  "Section 14 — Portability Requirements",
        "ieee830_ref": "3.5 Portability Requirements",
    },
    "maintainability": {
        "label":       "Maintainability",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "maintainability", "maintainable", "update", "upgrade",
            "documentation", "modular", "extensible", "support", "open standard",
            "code quality", "testing standard",
        ],
        "description": "How easy must the system be to maintain and extend?",
        "volere_ref":  "Section 14 — Maintainability",
        "ieee830_ref": "3.5 Maintainability",
    },
    "scalability": {
        "label":       "Scalability",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "scalab", "scale", "grow", "growth", "traffic spike", "seasonal",
            "auto-scaling", "horizontal", "vertical",
        ],
        "description": "How must the system handle growth in users or data volume?",
        "volere_ref":  "Section 12 — Scalability",
        "ieee830_ref": "3.2 Performance (scalability sub-section)",
    },
    "interfaces": {
        "label":       "External Interfaces",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "api", "external system", "third-party", "webhook", "integration",
            "email", "sms", "push notification", "payment", "identity provider",
        ],
        "description": "What external services and APIs must the system integrate with?",
        "volere_ref":  "Section 7 — Requirements on the Environment",
        "ieee830_ref": "2.1 External Interfaces",
    },
    "data_requirements": {
        "label":       "Data Requirements",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "data", "database", "store", "retain", "retention", "archive",
            "import", "export", "migration", "schema", "model",
        ],
        "description": "What data must the system create, store, and manage?",
        "volere_ref":  "Section 8 — Data Requirements",
        "ieee830_ref": "3.1 (data sub-section)",
    },
    "constraints": {
        "label":       "Design & Implementation Constraints",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "constraint", "budget", "timeline", "technology stack", "language",
            "framework", "regulation", "legal", "must use", "mandated",
        ],
        "description": "What technical, legal, or resource constraints apply?",
        "volere_ref":  "Section 4 — Constraints",
        "ieee830_ref": "2.5 Constraints",
    },
    "assumptions": {
        "label":       "Assumptions & Dependencies",
        "severity":    GapSeverity.OPTIONAL,
        "keywords":    [
            "assume", "assumption", "depend", "dependency", "prerequisite",
            "given that", "provided that",
        ],
        "description": "What assumptions could invalidate requirements if wrong?",
        "volere_ref":  "Section 6 — Assumptions",
        "ieee830_ref": "2.5 Assumptions and Dependencies",
    },
    "testability": {
        "label":       "Testability & Acceptance Criteria",
        "severity":    GapSeverity.OPTIONAL,
        "keywords":    [
            "test", "acceptance", "verify", "validate", "criterion", "criteria",
            "qa", "quality assurance", "pass", "fail", "measurable",
        ],
        "description": "How will requirements be verified? What are the acceptance criteria?",
        "volere_ref":  "Section 9 — Fit Criteria",
        "ieee830_ref": "3.1 (fit criteria)",
    },
    "deployment": {
        "label":       "Deployment & Operations",
        "severity":    GapSeverity.OPTIONAL,
        "keywords":    [
            "deploy", "deployment", "cloud", "on-premise", "rollout", "release",
            "monitoring", "logging", "alerting", "devops", "ci/cd",
        ],
        "description": "Where and how will the system be deployed and operated?",
        "volere_ref":  "Section 14 — Deployment",
        "ieee830_ref": "3.5 (deployment sub-section)",
    },
}


# ---------------------------------------------------------------------------
# GapReport data structures
# ---------------------------------------------------------------------------

@dataclass
class CategoryGap:
    """Represents a single uncovered or partially-covered category."""
    category_key:  str
    label:         str
    severity:      GapSeverity
    description:   str
    volere_ref:    str = ""
    ieee830_ref:   str = ""
    is_partial:    bool = False

    def to_dict(self) -> dict:
        return {
            "category_key": self.category_key,
            "label":        self.label,
            "severity":     self.severity.value,
            "description":  self.description,
            "is_partial":   self.is_partial,
        }


@dataclass
class GapReport:
    """Aggregated gap analysis result for one conversation turn."""
    session_id:       str   = ""
    turn_id:          int   = 0
    timestamp:        float = field(default_factory=time.time)
    total_categories: int   = 0
    covered_count:    int   = 0
    partial_count:    int   = 0
    uncovered_count:  int   = 0
    coverage_pct:     float = 0.0
    critical_gaps:    list[CategoryGap] = field(default_factory=list)
    important_gaps:   list[CategoryGap] = field(default_factory=list)
    optional_gaps:    list[CategoryGap] = field(default_factory=list)
    all_categories:   dict[str, str]   = field(default_factory=dict)  # key → "covered"|"partial"|"uncovered"

    @property
    def all_gaps(self) -> list[CategoryGap]:
        return self.critical_gaps + self.important_gaps + self.optional_gaps

    @property
    def priority_gaps(self) -> list[CategoryGap]:
        """Gaps ordered by severity: critical first."""
        return self.critical_gaps + self.important_gaps + self.optional_gaps

    def to_dict(self) -> dict:
        return {
            "session_id":       self.session_id,
            "turn_id":          self.turn_id,
            "timestamp":        self.timestamp,
            "total_categories": self.total_categories,
            "covered_count":    self.covered_count,
            "partial_count":    self.partial_count,
            "uncovered_count":  self.uncovered_count,
            "coverage_pct":     self.coverage_pct,
            "critical_gaps":    [g.to_dict() for g in self.critical_gaps],
            "important_gaps":   [g.to_dict() for g in self.important_gaps],
            "optional_gaps":    [g.to_dict() for g in self.optional_gaps],
            "all_categories":   self.all_categories,
        }


# ---------------------------------------------------------------------------
# Gap Detector
# ---------------------------------------------------------------------------

class GapDetector:
    """
    Analyses a ConversationState and returns a GapReport.

    Ablation study support
    ----------------------
        GapDetector(enabled=False) → always returns a "no gaps" report.
    """

    # FIX-G3: raised thresholds for CRITICAL categories
    COVERED_THRESHOLD_CRITICAL  = 4   # was 3
    COVERED_THRESHOLD_OTHER     = 3   # unchanged for non-critical

    def __init__(self, enabled: bool = True, checklist: Optional[dict] = None):
        self.enabled   = enabled
        self.checklist = checklist or COVERAGE_CHECKLIST

    def analyse(self, state: "ConversationState", domain_gate: dict[str, dict] | None = None) -> GapReport:
        if not self.enabled:
            return self._empty_report(state)

        corpus = self._build_corpus(state)

        report = GapReport(
            session_id      = state.session_id,
            turn_id         = state.turn_count,
            total_categories= len(self.checklist),
        )

        for key, spec in self.checklist.items():
            status = self._classify_coverage(key, spec, corpus, state, domain_gate)
            report.all_categories[key] = status

            if status == "covered":
                report.covered_count += 1
            elif status == "partial":
                report.partial_count += 1
                gap = self._make_gap(key, spec, is_partial=True)
                self._add_gap(gap, spec["severity"], report)
            else:
                report.uncovered_count += 1
                gap = self._make_gap(key, spec, is_partial=False)
                self._add_gap(gap, spec["severity"], report)

        # IT4-G1: Inject domain gate gaps as CRITICAL gaps when unprobed
        self._inject_domain_gate_gaps(state, report, domain_gate)

        effective = report.covered_count + (report.partial_count * 0.5)
        report.coverage_pct = round(
            (effective / report.total_categories) * 100, 1
        ) if report.total_categories else 0.0

        return report

    def _inject_domain_gate_gaps(
        self, state: "ConversationState", report: GapReport, domain_gate: dict[str, dict] | None = None
    ) -> None:
        """
        IT4-G1: Synthesise domain gate status into the GapReport as
        CRITICAL CategoryGap entries. This allows the question_generator's
        domain-first priority pass (IT4-A) to receive matching gap objects.

        Only adds a gap if the domain is UNPROBED or PARTIAL and has not
        already been added by the standard checklist scan (avoids duplicates
        by checking category_key prefix "domain_").
        """
        if domain_gate is None:
            return  # No domain gate to inject

        gate_status = compute_domain_gate(state, domain_gate)
        existing_keys = {g.category_key for g in report.critical_gaps + report.important_gaps}

        for domain_key, status in gate_status.items():
            if status not in (DOMAIN_STATUS_UNPROBED, DOMAIN_STATUS_PARTIAL):
                continue

            synthetic_key = f"domain_{domain_key}"
            if synthetic_key in existing_keys:
                continue

            spec = domain_gate[domain_key]
            gap = CategoryGap(
                category_key = synthetic_key,
                label        = spec["label"],
                severity     = GapSeverity.CRITICAL,
                description  = spec["fallback_probe"],
                volere_ref   = "Domain Coverage Gate",
                ieee830_ref  = "§3.1 / §3.2 Functional Requirements",
                is_partial   = (status == DOMAIN_STATUS_PARTIAL),
            )
            report.critical_gaps.append(gap)
            existing_keys.add(synthetic_key)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_corpus(self, state: "ConversationState") -> str:
        parts: list[str] = []
        for turn in state.turns:
            parts.append(turn.user_message)
            parts.append(turn.assistant_message)
        reqs = state.requirements.values() if isinstance(state.requirements, dict) else state.requirements
        for req in reqs:
            parts.append(req.text)
            parts.append(req.raw_excerpt)
        return " ".join(parts).lower()

    def _classify_coverage(
        self,
        key: str,
        spec: dict,
        corpus: str,
        state: "ConversationState",
        domain_gate: dict[str, dict] | None = None
    ) -> str:
        """
        Returns "covered" | "partial" | "uncovered".

        FIX-G1/G2: For the "functional" category we consult the requirement store
        directly instead of relying on keyword counts alone.
        FIX-G3: Raised keyword threshold for CRITICAL categories.
        """
        # Direct state check (from heuristic scanner in ConversationState)
        if hasattr(state, "covered_categories") and key in state.covered_categories:
            # For "functional", validate against the actual store count (FIX-G2)
            if key == "functional":
                return self._classify_functional_coverage(state, domain_gate)
            return "covered"

        # FIX-G2: functional uses requirement store as primary signal
        if key == "functional" and spec.get("_use_req_store"):
            return self._classify_functional_coverage(state, domain_gate)

        keywords = spec.get("keywords", [])
        matched = sum(1 for kw in keywords if kw in corpus)

        # FIX-G3: higher threshold for CRITICAL
        if spec.get("severity") == GapSeverity.CRITICAL:
            threshold = self.COVERED_THRESHOLD_CRITICAL
        else:
            threshold = self.COVERED_THRESHOLD_OTHER

        if matched >= threshold:
            return "covered"
        elif matched >= 1:
            return "partial"
        else:
            return "uncovered"

    @staticmethod
    def _classify_functional_coverage(state: "ConversationState", domain_gate: dict[str, dict] | None = None) -> str:
        """
        FIX-G2 / IT4-G3: Classify functional coverage using:
          1. The actual FR count in state (existing).
          2. Domain gate completeness (new): if any domain is UNPROBED,
             functional coverage is at most "partial" even if FR count ≥ 3.
             This prevents the gap detector from declaring functional coverage
             "covered" when entire feature domains were never surfaced.
        """
        count = state.functional_count
        if count == 0:
            return "uncovered"

        if domain_gate:
            gate_status = compute_domain_gate(state, domain_gate)
            any_unprobed = any(s == DOMAIN_STATUS_UNPROBED for s in gate_status.values())
        else:
            any_unprobed = False

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
            volere_ref   = spec.get("volere_ref", ""),
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