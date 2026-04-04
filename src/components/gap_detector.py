"""
src/components/gap_detector.py
===============
RE Assistant — Iteration 5 | University of Hildesheim
Requirements Coverage Checklist & Gap Detection Component

Iteration 5 changes
--------------------------------------
IT5-G1  _inject_domain_gate_gaps() now includes domains that have requirements
        but need deeper probing (needs_deeper_probing property).

IT5-G2  Added gap entries for user_roles and documentation if not yet covered
        in the final phase of elicitation.
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
    CRITICAL  = "critical"
    IMPORTANT = "important"
    OPTIONAL  = "optional"


# ---------------------------------------------------------------------------
# IEEE-830 / Volere unified coverage checklist
# ---------------------------------------------------------------------------

COVERAGE_CHECKLIST: dict[str, dict] = {
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
            "end user", "who will use", "technician", "master user",
        ],
        "description": "Who are the users and stakeholders of the system?",
        "volere_ref":  "Section 3 — The Client, the Customer, and Other Stakeholders",
        "ieee830_ref": "2.2 User Classes and Characteristics",
    },
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
        "description": "How reliable must the system be? What happens when it fails?",
        "volere_ref":  "Section 14 — Reliability Requirements",
        "ieee830_ref": "3.5 Reliability Requirements",
    },
    "compatibility": {
        "label":       "Compatibility & Portability",
        "severity":    GapSeverity.CRITICAL,
        "keywords":    [
            "compatible", "compatibility", "platform", "os", "windows", "linux",
            "macos", "ios", "android", "browser", "chrome", "firefox", "safari",
            "integration", "interoperability", "portability", "migrate",
        ],
        "description": "What platforms must the system run on? What must it integrate with?",
        "volere_ref":  "Section 16 — Portability Requirements",
        "ieee830_ref": "3.7 Portability Requirements",
    },
    "maintainability": {
        "label":       "Maintainability & Extensibility",
        "severity":    GapSeverity.CRITICAL,
        "keywords":    [
            "maintain", "maintenance", "maintainable", "extensible", "modular",
            "plugin", "update", "upgrade", "patch", "version", "deprecate",
            "documentation", "code quality", "test", "testable",
        ],
        "description": "How will the system be maintained, updated, and extended over time?",
        "volere_ref":  "Section 17 — Maintenance Requirements",
        "ieee830_ref": "3.8 Maintainability Requirements",
    },
    "interfaces": {
        "label":       "External Interfaces",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "interface", "api", "rest", "graphql", "soap", "web service",
            "import", "export", "integration", "external system", "third party",
            "gateway", "sensor", "device", "hardware", "wireless", "protocol",
        ],
        "description": "What external systems, devices, or APIs must the system interact with?",
        "volere_ref":  "Section 8 — Interfaces",
        "ieee830_ref": "3.1 External Interface Requirements",
    },
    "constraints": {
        "label":       "Design & Implementation Constraints",
        "severity":    GapSeverity.IMPORTANT,
        "keywords":    [
            "constraint", "technology", "framework", "language", "database",
            "cloud", "on-premise", "budget", "timeline", "deadline",
            "standard", "regulation", "compliance",
        ],
        "description": "What constraints exist on the design or implementation?",
        "volere_ref":  "Section 5 — Design Constraints",
        "ieee830_ref": "3.4 Design Constraints",
    },
}


# ---------------------------------------------------------------------------
# Gap report structures
# ---------------------------------------------------------------------------

@dataclass
class CategoryGap:
    category_key: str
    label:        str
    severity:     GapSeverity
    description:  str
    volere_ref:   str = ""
    ieee830_ref:  str = ""
    is_partial:   bool = False

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

        corpus = self._build_corpus(state)

        report = GapReport(
            session_id       = state.session_id,
            turn_id          = state.turn_count,
            total_categories = len(COVERAGE_CHECKLIST),
            covered_count    = 0,
            coverage_pct     = 0.0,
        )

        for key, spec in COVERAGE_CHECKLIST.items():
            status = self._classify_coverage(key, spec, corpus, state)
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
        gate = getattr(state, "domain_gate", None)
        if gate is None or not gate.seeded:
            return

        existing_keys = {g.category_key for g in report.critical_gaps + report.important_gaps}

        for key, domain in gate.domains.items():
            # IT6-G1: also include domains that need deeper probing
            if domain.status in ("unprobed", "partial") or domain.needs_deeper_probing:
                if domain.status == "excluded":
                    continue

                synthetic_key = f"domain_{key}"
                if synthetic_key in existing_keys:
                    continue

                probe = domain.probe_question or f"Can you tell me more about {domain.label}?"
                gap = CategoryGap(
                    category_key = synthetic_key,
                    label        = domain.label,
                    severity     = GapSeverity.CRITICAL,
                    description  = probe,
                    volere_ref   = "Dynamic Domain Gate",
                    ieee830_ref  = "§3.1 / §3.2 Functional Requirements",
                    is_partial   = (domain.status != "unprobed"),
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
    ) -> str:
        from domain_discovery import NFR_CATEGORIES

        # Mandatory NFR categories — use requirement-driven signal
        if key in NFR_CATEGORIES:
            covered = getattr(state, "covered_categories", set())
            if key in covered:
                return "covered"
            nfr_cov = getattr(state, "nfr_coverage", {})
            if nfr_cov.get(key, 0) >= 1:
                return "covered"
            keywords = spec.get("keywords", [])
            if any(kw in corpus for kw in keywords):
                return "partial"
            return "uncovered"

        # functional: use requirement store + domain gate
        if key == "functional" and spec.get("_use_req_store"):
            return self._classify_functional_coverage(state)

        # structural categories
        covered_cats = getattr(state, "covered_categories", set())
        if key in covered_cats:
            return "covered"

        keywords = spec.get("keywords", [])
        matched = sum(1 for kw in keywords if kw in corpus)

        if spec.get("severity") == GapSeverity.CRITICAL:
            threshold = self.COVERED_THRESHOLD_CRITICAL
        else:
            threshold = self.COVERED_THRESHOLD_OTHER

        if matched >= threshold:
            return "covered"
        elif matched >= 1:
            return "partial"
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