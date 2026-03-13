"""
conversation_state.py
======================
RE Assistant — Iteration 2 | University of Hildesheim
Conversation State Management

Responsibilities
----------------
- Track which IEEE-830 categories have been covered during elicitation
- Store all elicited requirements (FRs and NFRs) with metadata
- Maintain turn history with timestamps
- Detect coverage gaps so the prompt architect can inject them into the system message
- Provide session summary for evaluation / SRS generation

This module addresses Failure Mode 3 (Premature Closure):
  In Iteration 1 the baseline LLM used a fixed 3-turn template regardless of complexity.
  By maintaining explicit state, the RE Assistant knows what is still missing and
  will not offer to generate the SRS until mandatory categories are covered.

Design notes
------------
- No database; in-memory Python dataclasses + JSON serialisation for logs.
- All state is serialisable so sessions can be saved and reloaded.
- ConversationState is the single source of truth for the prompt architect,
  the SRS generator, and the session logger.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class RequirementType(str, Enum):
    FUNCTIONAL     = "functional"
    NON_FUNCTIONAL = "non_functional"
    CONSTRAINT     = "constraint"
    UNKNOWN        = "unknown"


class CoverageStatus(str, Enum):
    NOT_STARTED = "not_started"
    PARTIALLY   = "partially_covered"
    COVERED     = "covered"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Requirement:
    """A single structured requirement extracted from the conversation."""
    req_id:      str
    req_type:    RequirementType
    text:        str
    turn_id:     int
    category:    str           # IEEE-830 category key
    raw_excerpt: str           # verbatim user phrase that triggered this requirement
    timestamp:   float = field(default_factory=time.time)
    is_ambiguous: bool = False
    ambiguity_note: str = ""

    def to_dict(self) -> dict:
        return {
            "req_id":         self.req_id,
            "req_type":       self.req_type.value,
            "text":           self.text,
            "turn_id":        self.turn_id,
            "category":       self.category,
            "raw_excerpt":    self.raw_excerpt,
            "timestamp":      self.timestamp,
            "is_ambiguous":   self.is_ambiguous,
            "ambiguity_note": self.ambiguity_note,
        }


@dataclass
class Turn:
    """A single exchange: one user message + one assistant message."""
    turn_id:           int
    user_message:      str
    assistant_message: str
    timestamp:         float = field(default_factory=time.time)
    categories_updated: list[str] = field(default_factory=list)
    requirements_added: list[str] = field(default_factory=list)  # req_ids

    def to_dict(self) -> dict:
        return {
            "turn_id":            self.turn_id,
            "user_message":       self.user_message,
            "assistant_message":  self.assistant_message,
            "timestamp":          self.timestamp,
            "categories_updated": self.categories_updated,
            "requirements_added": self.requirements_added,
        }


# ---------------------------------------------------------------------------
# Keyword maps for lightweight heuristic coverage detection
# ---------------------------------------------------------------------------
# The conversation state uses a two-layer detection approach:
#   1. Heuristic keyword scan (cheap, runs every turn)
#   2. Manual mark_category_covered() calls from the conversation manager
#      when the LLM explicitly addresses a category.
# This is intentionally simple for Iteration 2; Iteration 3 will add
# proper gap detection via a dedicated Gap Detector component.

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "purpose":          ["purpose", "goal", "objective", "aim", "problem", "why", "motivation"],
    "scope":            ["scope", "boundary", "out of scope", "include", "exclude", "limit"],
    "stakeholders":     ["stakeholder", "user", "role", "actor", "admin", "customer", "operator"],
    "functional":       ["shall", "must", "feature", "function", "capability", "able to", "allow"],
    "performance":      ["performance", "speed", "response time", "latency", "throughput",
                         "fast", "slow", "seconds", "milliseconds", "concurrent", "load"],
    "usability":        ["usability", "easy to use", "intuitive", "accessibility", "ux",
                         "user experience", "simple", "learn", "onboard"],
    "security_privacy": ["security", "privacy", "authentication", "authorisation", "authorization",
                         "gdpr", "encrypt", "password", "login", "access control", "data protection",
                         "personal data", "sensitive", "hipaa", "compliance"],
    "reliability":      ["reliability", "uptime", "availability", "failover", "backup", "recover",
                         "downtime", "fault", "error rate", "sla"],
    "compatibility":    ["compatibility", "platform", "browser", "operating system", "os",
                         "android", "ios", "windows", "linux", "integration", "api", "interop"],
    "maintainability":  ["maintainability", "maintainable", "update", "upgrade", "documentation",
                         "modular", "extensible", "support", "open standard"],
    "constraints":      ["constraint", "budget", "timeline", "technology stack", "language",
                         "framework", "regulation", "legal", "standard", "must use"],
    "interfaces":       ["interface", "api", "external system", "third party", "webhook",
                         "database", "file format", "import", "export", "protocol"],
}


# ---------------------------------------------------------------------------
# ConversationState
# ---------------------------------------------------------------------------

@dataclass
class ConversationState:
    """
    The authoritative state object for one elicitation session.

    Attributes
    ----------
    session_id      : Unique identifier (used for log filenames).
    project_name    : Name of the system being elicited (set after first user message).
    turns           : Ordered list of all Turn objects.
    requirements    : Dict mapping req_id → Requirement.
    covered_categories : Set of IEEE-830 category keys confirmed as addressed.
    category_status : Detailed coverage status per category.
    _fr_counter     : Internal counter for FR IDs.
    _nfr_counter    : Internal counter for NFR IDs.
    _con_counter    : Internal counter for constraint IDs.
    session_complete : True when user or assistant has signalled session end.
    """

    session_id:          str
    project_name:        str = "Unknown Project"
    turns:               list[Turn] = field(default_factory=list)
    requirements:        dict[str, Requirement] = field(default_factory=dict)
    covered_categories:  set[str] = field(default_factory=set)
    category_status:     dict[str, CoverageStatus] = field(
        default_factory=lambda: {
            k: CoverageStatus.NOT_STARTED for k in _CATEGORY_KEYWORDS
        }
    )
    session_complete:    bool = False

    _fr_counter:  int = field(default=0, repr=False)
    _nfr_counter: int = field(default=0, repr=False)
    _con_counter: int = field(default=0, repr=False)

    # ------------------------------------------------------------------
    # Properties (derived from state)
    # ------------------------------------------------------------------

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def total_requirements(self) -> int:
        return len(self.requirements)

    @property
    def functional_count(self) -> int:
        return sum(1 for r in self.requirements.values()
                   if r.req_type == RequirementType.FUNCTIONAL)

    @property
    def nonfunctional_count(self) -> int:
        return sum(1 for r in self.requirements.values()
                   if r.req_type == RequirementType.NON_FUNCTIONAL)

    @property
    def constraint_count(self) -> int:
        return sum(1 for r in self.requirements.values()
                   if r.req_type == RequirementType.CONSTRAINT)

    @property
    def uncovered_categories(self) -> list[str]:
        from prompt_architect import IEEE830_CATEGORIES
        return [k for k in IEEE830_CATEGORIES if k not in self.covered_categories]

    @property
    def coverage_percentage(self) -> float:
        from prompt_architect import IEEE830_CATEGORIES
        total = len(IEEE830_CATEGORIES)
        if total == 0:
            return 0.0
        return round(len(self.covered_categories) / total * 100, 1)

    @property
    def mandatory_nfrs_covered(self) -> bool:
        from prompt_architect import MANDATORY_NFR_CATEGORIES
        return MANDATORY_NFR_CATEGORIES.issubset(self.covered_categories)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_fr_id(self) -> str:
        self._fr_counter += 1
        return f"FR-{self._fr_counter:03d}"

    def _next_nfr_id(self) -> str:
        self._nfr_counter += 1
        return f"NFR-{self._nfr_counter:03d}"

    def _next_con_id(self) -> str:
        self._con_counter += 1
        return f"CON-{self._con_counter:03d}"

    # ------------------------------------------------------------------
    # Turn management
    # ------------------------------------------------------------------

    def add_turn(
        self,
        user_message: str,
        assistant_message: str,
    ) -> Turn:
        """
        Record a completed exchange. Runs heuristic coverage scan on both messages.
        Returns the created Turn.
        """
        turn_id = self.turn_count + 1
        categories_updated: list[str] = []

        # Heuristic scan of USER MESSAGE ONLY.
        #
        # Critical: do NOT scan the assistant response here.
        # The assistant routinely lists IEEE-830 category names in its questions
        # (e.g. "Let me ask about Security & Privacy..."), which would falsely mark
        # those categories as covered after the very first turn.
        # Coverage is only credited when the *user* provides relevant information.
        user_text_lower = user_message.lower()
        for category, keywords in _CATEGORY_KEYWORDS.items():
            if category not in self.covered_categories:
                if any(kw in user_text_lower for kw in keywords):
                    self.mark_category_covered(category)
                    categories_updated.append(category)

        # Extract project name from first turn if not yet set
        if turn_id == 1 and self.project_name == "Unknown Project":
            self.project_name = _extract_project_name(user_message)

        turn = Turn(
            turn_id=turn_id,
            user_message=user_message,
            assistant_message=assistant_message,
            categories_updated=categories_updated,
        )
        self.turns.append(turn)
        return turn

    # ------------------------------------------------------------------
    # Category management
    # ------------------------------------------------------------------

    def mark_category_covered(self, category: str) -> None:
        """Mark an IEEE-830 category as covered. Idempotent."""
        self.covered_categories.add(category)
        self.category_status[category] = CoverageStatus.COVERED

    def mark_category_partial(self, category: str) -> None:
        """Mark a category as partially addressed (still needs follow-up)."""
        if category not in self.covered_categories:
            self.category_status[category] = CoverageStatus.PARTIALLY

    # ------------------------------------------------------------------
    # Requirement management
    # ------------------------------------------------------------------

    def add_requirement(
        self,
        req_type: RequirementType,
        text: str,
        category: str,
        raw_excerpt: str = "",
        is_ambiguous: bool = False,
        ambiguity_note: str = "",
    ) -> Requirement:
        """
        Add a structured requirement to the store.
        Automatically assigns ID based on type and marks the category as covered.
        """
        if req_type == RequirementType.FUNCTIONAL:
            req_id = self._next_fr_id()
        elif req_type == RequirementType.NON_FUNCTIONAL:
            req_id = self._next_nfr_id()
        else:
            req_id = self._next_con_id()

        turn_id = self.turn_count  # current turn

        req = Requirement(
            req_id=req_id,
            req_type=req_type,
            text=text,
            turn_id=turn_id,
            category=category,
            raw_excerpt=raw_excerpt,
            is_ambiguous=is_ambiguous,
            ambiguity_note=ambiguity_note,
        )
        self.requirements[req_id] = req
        self.mark_category_covered(category)

        # Also tag the current turn with this requirement
        if self.turns:
            self.turns[-1].requirements_added.append(req_id)

        return req

    # ------------------------------------------------------------------
    # Coverage gap analysis
    # ------------------------------------------------------------------

    def get_coverage_report(self) -> dict:
        """Return a structured coverage report for evaluation / logging."""
        from prompt_architect import IEEE830_CATEGORIES, MANDATORY_NFR_CATEGORIES
        return {
            "session_id":              self.session_id,
            "project_name":            self.project_name,
            "turn_count":              self.turn_count,
            "total_requirements":      self.total_requirements,
            "functional_count":        self.functional_count,
            "nonfunctional_count":     self.nonfunctional_count,
            "constraint_count":        self.constraint_count,
            "coverage_percentage":     self.coverage_percentage,
            "mandatory_nfrs_covered":  self.mandatory_nfrs_covered,
            "covered_categories":      sorted(self.covered_categories),
            "uncovered_categories":    self.uncovered_categories,
            "missing_mandatory_nfrs":  [
                IEEE830_CATEGORIES[c]
                for c in MANDATORY_NFR_CATEGORIES
                if c not in self.covered_categories
            ],
            "category_status": {
                k: v.value for k, v in self.category_status.items()
            },
        }

    def get_next_priority_category(self) -> Optional[str]:
        """
        Return the highest-priority uncovered category for the LLM to address next.
        Priority order: mandatory NFRs first, then remaining categories.
        """
        from prompt_architect import IEEE830_CATEGORIES, MANDATORY_NFR_CATEGORIES
        # Mandatory NFRs first
        for cat in MANDATORY_NFR_CATEGORIES:
            if cat not in self.covered_categories:
                return cat
        # Then remaining IEEE-830 categories
        for cat in IEEE830_CATEGORIES:
            if cat not in self.covered_categories:
                return cat
        return None

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "session_id":           self.session_id,
            "project_name":         self.project_name,
            "session_complete":     self.session_complete,
            "turns":                [t.to_dict() for t in self.turns],
            "requirements":         {k: v.to_dict() for k, v in self.requirements.items()},
            "covered_categories":   sorted(self.covered_categories),
            "category_status":      {k: v.value for k, v in self.category_status.items()},
            "coverage_report":      self.get_coverage_report(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # History for LLM
    # ------------------------------------------------------------------

    def get_message_history(self) -> list[dict[str, str]]:
        """
        Return the full conversation as an OpenAI-compatible messages list.
        This is passed to the LLM on every turn to maintain context.
        """
        messages: list[dict[str, str]] = []
        for turn in self.turns:
            messages.append({"role": "user",      "content": turn.user_message})
            messages.append({"role": "assistant", "content": turn.assistant_message})
        return messages


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_project_name(text: str) -> str:
    """
    Best-effort extraction of a project / product name from the user's first message.
    Falls back to a truncated version of the message.
    """
    # Common patterns: "I want to build a X", "We are developing X", etc.
    patterns = [
        r"(?:build|develop|create|make|design)\s+(?:a|an|the)\s+([A-Z][A-Za-z0-9 \-]+)",
        r"(?:called|named)\s+[\"']?([A-Z][A-Za-z0-9 \-]+)[\"']?",
        r"(?:for|about)\s+(?:a|an|the)\s+([A-Z][A-Za-z0-9 \-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if 3 <= len(name) <= 60:
                return name

    # Fallback: first 50 chars
    cleaned = text.strip().split("\n")[0][:50]
    return cleaned if cleaned else "Unnamed Project"


def create_session(session_id: str) -> ConversationState:
    """Factory function — create a fresh ConversationState."""
    return ConversationState(session_id=session_id)