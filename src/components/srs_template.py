"""
src/components/srs_template.py
================
IEEE-830 SRS Template: populated progressively during the elicitation conversation.

Purpose
-------
This module owns the *data* side of SRS generation:
  - A structured template that mirrors IEEE 830-1998 sections exactly
  - Progressive population: each conversation turn can write into any section
  - A live extraction call: after each assistant turn, the LLM reads its own
    response and extracts structured data into the correct section
  - SMART quality tagging: every requirement is annotated with which SMART
    criteria it satisfies or violates

Why a separate module?
  The previous implementation embedded SRS rendering directly inside
  `generate_srs()` in `conversation_manager.py`.  This meant:
    - Requirements only appeared in the SRS if manually added via add_requirement()
    - The template had no concept of "live" vs "empty" sections
    - There was no way to inspect template state mid-session
    - The formatter and the data were inseparable (not testable independently)

  This module separates *what we know* (SRSTemplate) from *how we render it*
  (SRSFormatter in srs_formatter.py).  The ConversationManager calls
  SRSTemplate.ingest_turn() after every exchange; by session end the template
  is fully populated and the formatter just renders it.

IEEE-830 Section Map
--------------------
  §1   Introduction
       1.1  Purpose
       1.2  Scope
       1.3  Definitions, Acronyms, Abbreviations
       1.4  References
       1.5  Overview
  §2   Overall Description
       2.1  Product Perspective
       2.2  Product Functions (feature summary)
       2.3  User Characteristics
       2.4  General Constraints
       2.5  Assumptions and Dependencies
  §3   Specific Requirements
       3.1  Functional Requirements (grouped by feature/actor)
       3.2  External Interface Requirements
            3.2.1  User Interfaces
            3.2.2  Hardware Interfaces
            3.2.3  Software Interfaces
            3.2.4  Communication Interfaces
       3.3  Performance Requirements
       3.4  Logical Database Requirements
       3.5  Design Constraints
       3.6  Software System Attributes
            3.6.1  Reliability
            3.6.2  Availability
            3.6.3  Security
            3.6.4  Maintainability
            3.6.5  Portability / Compatibility
            3.6.6  Usability
  §4   Appendices
       A    Traceability Matrix
       B    Coverage & Quality Report
       C    Conversation Transcript Summary
"""

from __future__ import annotations
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from src.components.conversation_state import Requirement, RequirementType


# ---------------------------------------------------------------------------
# SMART quality tagging
# ---------------------------------------------------------------------------

class SmartFlag(str, Enum):
    """Which SMART+U dimension a requirement satisfies or fails."""
    SPECIFIC    = "specific"
    MEASURABLE  = "measurable"
    ACHIEVABLE  = "achievable"
    RELEVANT    = "relevant"
    TESTABLE    = "testable"
    UNAMBIGUOUS = "unambiguous"


@dataclass
class SmartAnnotation:
    """
    Per-requirement SMART quality annotation.

    satisfied : set of SMART dimensions clearly met
    violated  : set of SMART dimensions clearly violated
    notes     : human-readable explanation (populated by the extraction LLM)
    score     : 0–5 (number of satisfied dimensions out of 5 core ones)
    """
    satisfied:  set[SmartFlag] = field(default_factory=set)
    violated:   set[SmartFlag] = field(default_factory=set)
    notes:      str = ""

    @property
    def score(self) -> int:
        core = {SmartFlag.SPECIFIC, SmartFlag.MEASURABLE,
                SmartFlag.TESTABLE, SmartFlag.UNAMBIGUOUS, SmartFlag.RELEVANT}
        return len(self.satisfied & core)

    @property
    def quality_label(self) -> str:
        if self.score >= 5:
            return "✅ High Quality"
        elif self.score >= 3:
            return "⚠️  Acceptable"
        else:
            return "❌ Needs Improvement"

    def to_dict(self) -> dict:
        return {
            "satisfied":     [f.value for f in self.satisfied],
            "violated":      [f.value for f in self.violated],
            "notes":         self.notes,
            "score":         self.score,
            "quality_label": self.quality_label,
        }


# ---------------------------------------------------------------------------
# Annotated requirement
# ---------------------------------------------------------------------------

@dataclass
class AnnotatedRequirement:
    """
    A requirement from ConversationState augmented with SMART annotation
    and the IEEE-830 section it belongs to.
    """
    requirement:  Requirement
    smart:        SmartAnnotation = field(default_factory=SmartAnnotation)
    ieee_section: str = ""        # e.g. "3.1", "3.3", "3.6.3"
    priority:     str = "Should-have"  # Must-have | Should-have | Nice-to-have

    @property
    def req_id(self) -> str:
        return self.requirement.req_id

    @property
    def text(self) -> str:
        return self.requirement.text

    @property
    def turn_id(self) -> int:
        return self.requirement.turn_id

    def to_dict(self) -> dict:
        return {
            **self.requirement.to_dict(),
            "smart":        self.smart.to_dict(),
            "ieee_section": self.ieee_section,
            "priority":     self.priority,
        }


# ---------------------------------------------------------------------------
# Section data containers
# ---------------------------------------------------------------------------

@dataclass
class Section1:
    """§1 Introduction"""
    purpose:     str = ""   # Why does this system exist?
    scope:       str = ""   # What does it do / not do?
    definitions: dict[str, str] = field(default_factory=dict)  # term → definition
    references:  list[str] = field(default_factory=list)
    overview:    str = ""


@dataclass
class UserClass:
    name:        str = ""
    description: str = ""
    proficiency: str = ""   # technical level


@dataclass
class Section2:
    """§2 Overall Description"""
    product_perspective: str = ""
    product_functions:   list[str] = field(default_factory=list)  # bullet summaries
    user_classes:        list[UserClass] = field(default_factory=list)
    general_constraints: list[str] = field(default_factory=list)
    assumptions:         list[str] = field(default_factory=list)


@dataclass
class InterfaceRequirements:
    """§3.2 External Interface Requirements"""
    user_interfaces:          list[str] = field(default_factory=list)
    hardware_interfaces:      list[str] = field(default_factory=list)
    software_interfaces:      list[str] = field(default_factory=list)
    communication_interfaces: list[str] = field(default_factory=list)


@dataclass
class SystemAttributes:
    """§3.6 Software System Attributes"""
    reliability:   list[AnnotatedRequirement] = field(default_factory=list)
    availability:  list[AnnotatedRequirement] = field(default_factory=list)
    security:      list[AnnotatedRequirement] = field(default_factory=list)
    maintainability: list[AnnotatedRequirement] = field(default_factory=list)
    portability:   list[AnnotatedRequirement] = field(default_factory=list)
    usability:     list[AnnotatedRequirement] = field(default_factory=list)


@dataclass
class Section3:
    """§3 Specific Requirements"""
    functional:      list[AnnotatedRequirement] = field(default_factory=list)
    interfaces:      InterfaceRequirements = field(default_factory=InterfaceRequirements)
    performance:     list[AnnotatedRequirement] = field(default_factory=list)
    database:        list[str] = field(default_factory=list)
    design_constraints: list[AnnotatedRequirement] = field(default_factory=list)
    attributes:      SystemAttributes = field(default_factory=SystemAttributes)


# ---------------------------------------------------------------------------
# The living SRS Template
# ---------------------------------------------------------------------------

@dataclass
class SRSTemplate:
    """
    The IEEE-830 SRS template, populated progressively during elicitation.

    This is the single data object that the SRSFormatter renders.
    It is updated after every conversation turn via update_from_requirements().

    Attributes
    ----------
    session_id      : Ties template to a session log.
    project_name    : Set from ConversationState.
    created_at      : ISO timestamp of session start.
    last_updated_at : Updated on every ingest.
    section1/2/3    : IEEE-830 sections.
    open_issues     : Ambiguities, conflicts, unresolved questions.
    conflicts       : Detected contradictions between requirements.
    annotated_reqs  : Master list of all AnnotatedRequirements (indexed by req_id).
    _section_filled : Which sections have non-empty content (for coverage display).
    """

    session_id:      str
    project_name:    str = "Unknown Project"
    created_at:      str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    last_updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))

    section1: Section1 = field(default_factory=Section1)
    section2: Section2 = field(default_factory=Section2)
    section3: Section3 = field(default_factory=Section3)

    open_issues: list[str] = field(default_factory=list)
    conflicts:   list[str] = field(default_factory=list)

    # Master index: req_id → AnnotatedRequirement
    annotated_reqs: dict[str, AnnotatedRequirement] = field(default_factory=dict)

    # Internal tracking
    _section_filled: set[str] = field(default_factory=set)

    # ------------------------------------------------------------------
    # Population API — called by ConversationManager after each turn
    # ------------------------------------------------------------------

    def update_from_requirements(
        self,
        requirements: dict[str, Requirement],
        project_name: str = "",
    ) -> None:
        """
        Sync the template with the current ConversationState requirement store.

        For every requirement in the store:
          1. Create or update an AnnotatedRequirement
          2. Run SMART heuristic annotation
          3. Assign to the correct IEEE-830 section

        This is deliberately idempotent — it can be called after every turn
        without creating duplicates.
        """
        if project_name:
            self.project_name = project_name

        for req_id, req in requirements.items():
            if req_id not in self.annotated_reqs:
                ann = AnnotatedRequirement(requirement=req)
                ann.smart = _heuristic_smart_check(req.text)
                ann.ieee_section = _map_category_to_section(req)
                ann.priority = _infer_priority(req)
                self.annotated_reqs[req_id] = ann
                self._place_requirement(ann)

        self.last_updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self._refresh_filled_sections()

    def ingest_narrative(
        self,
        field_key: str,
        value: str,
        append: bool = False,
    ) -> None:
        """
        Write a free-text value into a named template field.

        field_key examples:
          "section1.purpose", "section1.scope", "section2.product_perspective",
          "section2.assumptions", "section2.product_functions"

        Used by the extraction pipeline to populate narrative fields
        that are not captured as formal requirements.
        """
        parts = field_key.split(".", 1)
        if len(parts) != 2:
            return
        section_name, attr = parts[0], parts[1]

        target = getattr(self, section_name, None)
        if target is None:
            return

        current = getattr(target, attr, None)
        if isinstance(current, list):
            if value and value not in current:
                current.append(value)
        elif isinstance(current, str):
            if append and current:
                setattr(target, attr, current + " " + value)
            else:
                setattr(target, attr, value)

        self._section_filled.add(section_name)
        self.last_updated_at = time.strftime("%Y-%m-%d %H:%M:%S")

    def add_user_class(self, name: str, description: str, proficiency: str = "") -> None:
        """Add a stakeholder / user class to §2.3."""
        # Avoid duplicates by name
        existing = {uc.name.lower() for uc in self.section2.user_classes}
        if name.lower() not in existing:
            self.section2.user_classes.append(
                UserClass(name=name, description=description, proficiency=proficiency)
            )
            self._section_filled.add("section2")

    def add_open_issue(self, issue: str) -> None:
        """Record an ambiguity or unresolved question."""
        if issue and issue not in self.open_issues:
            self.open_issues.append(issue)

    def add_conflict(self, conflict: str) -> None:
        """Record a detected contradiction."""
        if conflict and conflict not in self.conflicts:
            self.conflicts.append(conflict)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _place_requirement(self, ann: AnnotatedRequirement) -> None:
        """Place an AnnotatedRequirement into the correct §3 sub-section."""
        req = ann.requirement

        # Avoid duplicates
        existing_ids = {r.req_id for r in self._all_section3_reqs()}
        if ann.req_id in existing_ids:
            return

        cat = req.category
        rtype = req.req_type

        if rtype == RequirementType.FUNCTIONAL:
            self.section3.functional.append(ann)
            self._section_filled.add("section3.functional")

        elif rtype == RequirementType.CONSTRAINT:
            self.section3.design_constraints.append(ann)
            self._section_filled.add("section3.design_constraints")

        elif rtype == RequirementType.NON_FUNCTIONAL:
            if cat == "performance":
                self.section3.performance.append(ann)
                self._section_filled.add("section3.performance")
            elif cat == "reliability":
                self.section3.attributes.reliability.append(ann)
                self._section_filled.add("section3.attributes.reliability")
            elif cat in ("security_privacy", "security"):
                self.section3.attributes.security.append(ann)
                self._section_filled.add("section3.attributes.security")
            elif cat == "maintainability":
                self.section3.attributes.maintainability.append(ann)
                self._section_filled.add("section3.attributes.maintainability")
            elif cat in ("compatibility", "portability"):
                self.section3.attributes.portability.append(ann)
                self._section_filled.add("section3.attributes.portability")
            elif cat == "usability":
                self.section3.attributes.usability.append(ann)
                self._section_filled.add("section3.attributes.usability")
            elif cat == "availability":
                self.section3.attributes.availability.append(ann)
                self._section_filled.add("section3.attributes.availability")
            elif cat == "interfaces":
                # Infer sub-type from text heuristic
                text_lower = req.text.lower()
                if any(w in text_lower for w in ["ui", "screen", "dashboard", "page", "button"]):
                    self.section3.interfaces.user_interfaces.append(req.text)
                elif any(w in text_lower for w in ["api", "rest", "soap", "webhook", "http"]):
                    self.section3.interfaces.software_interfaces.append(req.text)
                elif any(w in text_lower for w in ["hardware", "device", "sensor", "printer"]):
                    self.section3.interfaces.hardware_interfaces.append(req.text)
                else:
                    self.section3.interfaces.communication_interfaces.append(req.text)
                self._section_filled.add("section3.interfaces")
            else:
                # Catch-all: add to design_constraints
                self.section3.design_constraints.append(ann)

    def _all_section3_reqs(self) -> list[AnnotatedRequirement]:
        """Flat list of all AnnotatedRequirements across §3."""
        result: list[AnnotatedRequirement] = []
        result += self.section3.functional
        result += self.section3.performance
        result += self.section3.design_constraints
        result += self.section3.attributes.reliability
        result += self.section3.attributes.availability
        result += self.section3.attributes.security
        result += self.section3.attributes.maintainability
        result += self.section3.attributes.portability
        result += self.section3.attributes.usability
        return result

    def _refresh_filled_sections(self) -> None:
        if self.section1.purpose:        self._section_filled.add("section1.purpose")
        if self.section1.scope:          self._section_filled.add("section1.scope")
        if self.section2.user_classes:   self._section_filled.add("section2.user_classes")
        if self.section3.functional:     self._section_filled.add("section3.functional")
        if self.section3.performance:    self._section_filled.add("section3.performance")
        if self.section3.attributes.security: self._section_filled.add("section3.attributes.security")

    # ------------------------------------------------------------------
    # Coverage & quality queries
    # ------------------------------------------------------------------

    @property
    def filled_sections(self) -> set[str]:
        return set(self._section_filled)

    @property
    def total_requirements(self) -> int:
        return len(self.annotated_reqs)

    @property
    def functional_count(self) -> int:
        return len(self.section3.functional)

    @property
    def nfr_count(self) -> int:
        attrs = self.section3.attributes
        return (len(self.section3.performance) +
                len(attrs.reliability) + len(attrs.availability) +
                len(attrs.security) + len(attrs.maintainability) +
                len(attrs.portability) + len(attrs.usability))

    @property
    def avg_smart_score(self) -> float:
        scores = [ann.smart.score for ann in self.annotated_reqs.values()]
        return round(sum(scores) / len(scores), 2) if scores else 0.0

    @property
    def high_quality_count(self) -> int:
        return sum(1 for ann in self.annotated_reqs.values() if ann.smart.score >= 4)

    @property
    def needs_improvement_count(self) -> int:
        return sum(1 for ann in self.annotated_reqs.values() if ann.smart.score < 3)

    def is_section_empty(self, section_key: str) -> bool:
        return section_key not in self._section_filled

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "session_id":       self.session_id,
            "project_name":     self.project_name,
            "created_at":       self.created_at,
            "last_updated_at":  self.last_updated_at,
            "total_requirements": self.total_requirements,
            "functional_count": self.functional_count,
            "nfr_count":        self.nfr_count,
            "avg_smart_score":  self.avg_smart_score,
            "open_issues":      self.open_issues,
            "conflicts":        self.conflicts,
            "filled_sections":  sorted(self._section_filled),
            "annotated_reqs":   {k: v.to_dict() for k, v in self.annotated_reqs.items()},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# SMART heuristic checker
# ---------------------------------------------------------------------------

# Vague words that indicate a requirement is NOT measurable / specific
_VAGUE_WORDS = {
    "simple", "easy", "fast", "quickly", "good", "better", "best", "nice",
    "friendly", "modern", "clean", "robust", "scalable", "flexible",
    "intuitive", "seamless", "powerful", "efficient", "effective",
    "comprehensive", "appropriate", "adequate", "reasonable", "suitable",
}

# Measurable patterns — numbers, units, percentages
_MEASURABLE_PATTERNS = [
    r"\d+\s*(?:second|millisecond|minute|hour|ms|s\b)",
    r"\d+\s*%",
    r"\d+\s*(?:MB|GB|KB|TB|users|requests|transactions)",
    r"within\s+\d+",
    r"at\s+least\s+\d+",
    r"no\s+more\s+than\s+\d+",
    r"less\s+than\s+\d+",
    r"greater\s+than\s+\d+",
    r"\d{4}",     # year
]

# "shall" pattern — IEEE-830 canonical form
_SHALL_PATTERN = re.compile(r"\bshall\b", re.IGNORECASE)
_ACTOR_PATTERN = re.compile(
    r"^(?:the\s+)?(?:system|user|admin|administrator|application|service|module)\b",
    re.IGNORECASE,
)


def _heuristic_smart_check(text: str) -> SmartAnnotation:
    """
    Apply lightweight heuristic SMART checks to a requirement text.

    This is NOT a full NLP analysis — it catches the most obvious issues
    that the Iteration 1 baseline consistently failed on.
    Full quality enforcement (Iteration 4) will replace this with an LLM call.

    Rules
    -----
    SPECIFIC    → starts with a defined actor ("The system shall", "Users shall")
    MEASURABLE  → contains a numeric value or measurable unit
    TESTABLE    → contains "shall" (IEEE form) OR a clear pass/fail criterion
    UNAMBIGUOUS → does NOT contain vague adjectives from the blocklist
    RELEVANT    → heuristically assume True unless clearly a meta-comment
    """
    ann = SmartAnnotation()
    lower = text.lower().strip()
    words = set(lower.split())

    # SPECIFIC: actor-subject present
    if _ACTOR_PATTERN.match(text.strip()):
        ann.satisfied.add(SmartFlag.SPECIFIC)
    else:
        ann.violated.add(SmartFlag.SPECIFIC)

    # MEASURABLE: contains numeric constraint
    if any(re.search(p, text, re.IGNORECASE) for p in _MEASURABLE_PATTERNS):
        ann.satisfied.add(SmartFlag.MEASURABLE)
    else:
        ann.violated.add(SmartFlag.MEASURABLE)

    # TESTABLE: uses "shall" canonical form
    if _SHALL_PATTERN.search(text):
        ann.satisfied.add(SmartFlag.TESTABLE)
    else:
        ann.violated.add(SmartFlag.TESTABLE)
        ann.notes += "Requirement is not in IEEE 'shall' form. "

    # UNAMBIGUOUS: no vague words
    vague_found = _VAGUE_WORDS & words
    if not vague_found:
        ann.satisfied.add(SmartFlag.UNAMBIGUOUS)
    else:
        ann.violated.add(SmartFlag.UNAMBIGUOUS)
        ann.notes += f"Vague terms detected: {', '.join(sorted(vague_found))}. "

    # RELEVANT: assume True for all non-empty requirements
    if text.strip():
        ann.satisfied.add(SmartFlag.RELEVANT)

    # ACHIEVABLE: cannot heuristically assess — leave unset
    # (Iteration 4 will use LLM to check feasibility)

    ann.notes = ann.notes.strip()
    return ann


# ---------------------------------------------------------------------------
# Category → IEEE-830 section mapping
# ---------------------------------------------------------------------------

_CATEGORY_TO_SECTION: dict[str, str] = {
    "purpose":          "1.1",
    "scope":            "1.2",
    "stakeholders":     "2.3",
    "functional":       "3.1",
    "interfaces":       "3.2",
    "performance":      "3.3",
    "reliability":      "3.6.1",
    "availability":     "3.6.2",
    "security_privacy": "3.6.3",
    "maintainability":  "3.6.4",
    "compatibility":    "3.6.5",
    "usability":        "3.6.6",
    "constraints":      "3.5",
}


def _map_category_to_section(req: Requirement) -> str:
    if req.req_type == RequirementType.CONSTRAINT:
        return "3.5"
    return _CATEGORY_TO_SECTION.get(req.category, "3.1")


# ---------------------------------------------------------------------------
# Priority inference
# ---------------------------------------------------------------------------

_MUST_KEYWORDS = {"shall", "must", "required", "mandatory", "critical", "essential"}
_NICE_KEYWORDS = {"nice", "optionally", "optional", "consider", "future", "later"}

_NICE_PATTERN = re.compile(
    r"\b(?:nice|optionally|optional|consider|future|later)\b", re.IGNORECASE
)
_MUST_PATTERN = re.compile(
    r"\b(?:shall|must|required|mandatory|critical|essential)\b", re.IGNORECASE
)


def _infer_priority(req: Requirement) -> str:
    text = req.text
    if _MUST_PATTERN.search(text):
        return "Must-have"
    if _NICE_PATTERN.search(text):
        return "Nice-to-have"
    return "Should-have"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_template(session_id: str, project_name: str = "") -> SRSTemplate:
    """Create a fresh SRSTemplate for a new session."""
    return SRSTemplate(session_id=session_id, project_name=project_name or "Unknown Project")