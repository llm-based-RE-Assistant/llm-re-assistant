"""
gap_detector.py
===============
RE Assistant — Iteration 3 | University of Hildesheim
Requirements Coverage Checklist & Gap Detection Component

Research Question (Iteration 3)
--------------------------------
Can the RE Assistant reliably detect missing requirements and proactively
query the user for them?

Responsibilities
----------------
- Define the full IEEE-830 / Volere requirements coverage checklist
- After each conversation turn, compute which categories are still uncovered
- Classify gaps by severity (critical / important / optional)
- Produce a structured GapReport that the ProactiveQuestionGenerator consumes
- Support ablation study: gap_detection ON vs. OFF flag

Architecture
------------
  ConversationState  →  GapDetector.analyse()  →  GapReport
  GapReport          →  ProactiveQuestionGenerator  →  follow-up questions
  GapReport          →  UI CoveragePanel (via REST / direct call)

Design notes
------------
- The checklist is data-driven (CHECKLIST dict), not hard-coded logic, so
  categories can be added/removed without touching detection code.
- Coverage is determined by heuristic keyword scan (same as Iteration 2
  ConversationState) PLUS an LLM-based semantic check when available.
- Every GapReport is serialisable to JSON for session logging and ablation
  study comparison.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from conversation_state import ConversationState


# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------

class GapSeverity(str, Enum):
    CRITICAL  = "critical"   # Must be covered before SRS generation
    IMPORTANT = "important"  # Strongly recommended
    OPTIONAL  = "optional"   # Nice to have


# ---------------------------------------------------------------------------
# IEEE-830 / Volere unified coverage checklist
# ---------------------------------------------------------------------------
# Each entry defines:
#   label        : human-readable name shown in UI and reports
#   severity     : how critical this gap is
#   keywords     : heuristic keyword list for coverage detection
#   description  : short explanation shown in the coverage panel
#   volere_ref   : corresponding Volere shell section (for academic traceability)
#   ieee830_ref  : corresponding IEEE-830 section (for academic traceability)
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
    "functional": {
        "label":       "Functional Requirements",
        "severity":    GapSeverity.CRITICAL,
        "keywords":    [
            "shall", "must", "should", "feature", "function", "capability",
            "allow", "enable", "provide", "support", "manage", "process",
            "create", "update", "delete", "view", "display", "notify",
            "authenticate", "search", "filter", "export", "import",
        ],
        "description": "What must the system do? Core features and behaviours.",
        "volere_ref":  "Section 9 — Functional Requirements",
        "ieee830_ref": "3.1 Functional Requirements",
    },
    "use_cases": {
        "label":       "Use Cases & User Stories",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "use case", "user story", "as a", "i want", "so that",
            "scenario", "workflow", "flow", "step", "sequence",
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
            "ux", "ui", "user interface", "user experience", "learnability",
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
        "severity":    GapSeverity.CRITICAL,
        "keywords":    [
            "compatible", "compatibility", "browser", "platform", "os",
            "operating system", "windows", "linux", "macos", "ios", "android",
            "mobile", "tablet", "desktop", "api", "integration", "interoperability",
        ],
        "description": "Which platforms, browsers, or systems must this work with?",
        "volere_ref":  "Section 14 — Portability Requirements",
        "ieee830_ref": "3.7 Portability Requirements",
    },
    "maintainability": {
        "label":       "Maintainability & Extensibility",
        "severity":    GapSeverity.CRITICAL,
        "keywords":    [
            "maintainable", "maintainability", "extensible", "extensibility",
            "modular", "module", "plugin", "upgrade", "update", "patch",
            "technical debt", "code quality", "documentation", "support",
        ],
        "description": "How easy must it be to maintain, extend, or modify the system?",
        "volere_ref":  "Section 12 — Maintainability",
        "ieee830_ref": "3.8 Maintainability Requirements",
    },
    "scalability": {
        "label":       "Scalability Requirements",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "scalable", "scalability", "scale", "grow", "growth",
            "elastic", "auto-scale", "horizontal", "vertical", "cloud",
            "peak", "traffic spike", "users growth",
        ],
        "description": "How must the system scale as usage grows?",
        "volere_ref":  "Section 12 — Performance Requirements (growth)",
        "ieee830_ref": "3.2 Performance Requirements (scalability)",
    },

    # ── Section 4: System Interfaces ─────────────────────────────────────────
    "interfaces": {
        "label":       "External Interfaces",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "interface", "api", "rest", "graphql", "webhook", "integration",
            "third party", "third-party", "external system", "database",
            "payment", "email", "sms", "notification", "oauth", "sso",
        ],
        "description": "What external systems, APIs, or services must the system integrate with?",
        "volere_ref":  "Section 9 — External Interface Requirements",
        "ieee830_ref": "2.2 External Interface Requirements",
    },
    "data_requirements": {
        "label":       "Data Requirements",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "data", "database", "storage", "store", "persist", "record",
            "entity", "model", "schema", "field", "attribute", "relationship",
            "migration", "import", "export", "backup", "retention",
        ],
        "description": "What data must the system store, manage, and protect?",
        "volere_ref":  "Section 8 — The Scope of the Product (data)",
        "ieee830_ref": "2.2 Product Functions (data)",
    },

    # ── Section 5: Constraints & Assumptions ──────────────────────────────────
    "constraints": {
        "label":       "Design & Implementation Constraints",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "constraint", "technology", "tech stack", "framework", "language",
            "budget", "timeline", "deadline", "resource", "team size",
            "infrastructure", "cloud", "on-premise", "legacy",
        ],
        "description": "What technology, budget, or team constraints exist?",
        "volere_ref":  "Section 16 — Off-the-Shelf Solutions",
        "ieee830_ref": "2.5 Constraints",
    },
    "assumptions": {
        "label":       "Assumptions & Dependencies",
        "severity":    GapSeverity.OPTIONAL,
        "keywords":    [
            "assume", "assumption", "depend", "dependency", "prerequisite",
            "given that", "provided that", "expect", "anticipated",
        ],
        "description": "What assumptions are being made? What does the system depend on?",
        "volere_ref":  "Section 17 — New Problems",
        "ieee830_ref": "2.5 Assumptions and Dependencies",
    },

    # ── Section 6: Quality & Operations ──────────────────────────────────────
    "testability": {
        "label":       "Testability & Verifiability",
        "severity":    GapSeverity.OPTIONAL,
        "keywords":    [
            "test", "testable", "verifiable", "verify", "validate", "qa",
            "quality assurance", "acceptance", "criteria", "measurable",
        ],
        "description": "How will requirements be verified? Are acceptance criteria defined?",
        "volere_ref":  "Section 20 — Solution Constraints",
        "ieee830_ref": "3.9 Other Requirements",
    },
    "deployment": {
        "label":       "Deployment & Operations",
        "severity":    GapSeverity.OPTIONAL,
        "keywords":    [
            "deploy", "deployment", "ci/cd", "devops", "docker", "kubernetes",
            "container", "server", "hosting", "cloud", "aws", "azure", "gcp",
            "release", "rollback", "monitoring", "logging", "alerting",
        ],
        "description": "How will the system be deployed and operated in production?",
        "volere_ref":  "Section 16 — Off-the-Shelf Solutions (operations)",
        "ieee830_ref": "3.2 Deployment Constraints",
    },
}


# ---------------------------------------------------------------------------
# Gap data structures
# ---------------------------------------------------------------------------

@dataclass
class CategoryGap:
    """Represents a single uncovered or partially-covered category."""
    category_key:  str
    label:         str
    severity:      GapSeverity
    description:   str
    volere_ref:    str
    ieee830_ref:   str
    is_partial:    bool = False   # True if some keywords matched but coverage is thin

    def to_dict(self) -> dict:
        return {
            "category_key": self.category_key,
            "label":        self.label,
            "severity":     self.severity.value,
            "description":  self.description,
            "volere_ref":   self.volere_ref,
            "ieee830_ref":  self.ieee830_ref,
            "is_partial":   self.is_partial,
        }


@dataclass
class GapReport:
    """
    Full gap analysis produced after each conversation turn.
    Consumed by ProactiveQuestionGenerator and the UI coverage panel.
    """
    session_id:          str
    turn_id:             int
    timestamp:           float = field(default_factory=time.time)

    # Coverage metrics
    total_categories:    int = 0
    covered_count:       int = 0
    partial_count:       int = 0
    uncovered_count:     int = 0
    coverage_pct:        float = 0.0

    # Categorised gaps
    critical_gaps:       list[CategoryGap] = field(default_factory=list)
    important_gaps:      list[CategoryGap] = field(default_factory=list)
    optional_gaps:       list[CategoryGap] = field(default_factory=list)

    # All categories with status for full checklist display
    all_categories:      dict[str, str] = field(default_factory=dict)  # key → "covered"|"partial"|"uncovered"

    # Convenience
    @property
    def all_gaps(self) -> list[CategoryGap]:
        return self.critical_gaps + self.important_gaps + self.optional_gaps

    @property
    def has_critical_gaps(self) -> bool:
        return len(self.critical_gaps) > 0

    @property
    def priority_gaps(self) -> list[CategoryGap]:
        """Critical gaps first, then important — used by question generator."""
        return self.critical_gaps + self.important_gaps

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

    Usage
    -----
        detector = GapDetector()
        gap_report = detector.analyse(state)

    Ablation study support
    ----------------------
        GapDetector(enabled=False) → always returns a "no gaps" report
        (used as the OFF branch in the ablation study).
    """

    def __init__(self, enabled: bool = True, checklist: Optional[dict] = None):
        """
        Parameters
        ----------
        enabled   : If False, gap detection is disabled (ablation OFF branch).
        checklist : Override the default COVERAGE_CHECKLIST (for testing).
        """
        self.enabled   = enabled
        self.checklist = checklist or COVERAGE_CHECKLIST

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self, state: "ConversationState") -> GapReport:
        """
        Run gap analysis on the current conversation state.

        Parameters
        ----------
        state : ConversationState — the live session state after the latest turn.

        Returns
        -------
        GapReport with all metrics and categorised gaps.
        """
        if not self.enabled:
            return self._empty_report(state)

        # Build the combined text corpus from the whole conversation
        corpus = self._build_corpus(state)

        report = GapReport(
            session_id      = state.session_id,
            turn_id         = state.turn_count,
            total_categories= len(self.checklist),
        )

        for key, spec in self.checklist.items():
            status = self._classify_coverage(key, spec, corpus, state)
            report.all_categories[key] = status

            if status == "covered":
                report.covered_count += 1
            elif status == "partial":
                report.partial_count  += 1
                gap = self._make_gap(key, spec, is_partial=True)
                self._add_gap(gap, spec["severity"], report)
            else:  # uncovered
                report.uncovered_count += 1
                gap = self._make_gap(key, spec, is_partial=False)
                self._add_gap(gap, spec["severity"], report)

        # Coverage % counts partial as half
        effective = report.covered_count + (report.partial_count * 0.5)
        report.coverage_pct = round(
            (effective / report.total_categories) * 100, 1
        ) if report.total_categories else 0.0

        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_corpus(self, state: "ConversationState") -> str:
        """
        Concatenate all user + assistant messages for keyword scanning.
        Lower-cased for case-insensitive matching.
        """
        parts: list[str] = []
        for turn in state.turns:
            parts.append(turn.user_message)
            parts.append(turn.assistant_message)
        # Also include extracted requirement texts
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
    ) -> str:
        """
        Returns "covered" | "partial" | "uncovered".

        Logic
        -----
        1. If the category key appears in state.covered_categories → "covered"
        2. If ≥3 distinct keywords match in corpus → "covered"
        3. If 1–2 keywords match → "partial"
        4. Otherwise → "uncovered"
        """
        # Direct state check (from existing heuristic scanner in ConversationState)
        if hasattr(state, "covered_categories") and key in state.covered_categories:
            return "covered"

        keywords = spec.get("keywords", [])
        matched = sum(1 for kw in keywords if kw in corpus)

        if matched >= 3:
            return "covered"
        elif matched >= 1:
            return "partial"
        else:
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
        """Return a fully-covered report (used when gap detection is disabled)."""
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
    """Factory function — mirrors create_* pattern from other modules."""
    return GapDetector(enabled=enabled)