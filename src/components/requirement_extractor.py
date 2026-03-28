"""
src/components/requirement_extractor.py
========================
RE Assistant — Iteration 3 | University of Hildesheim
Automatic Requirement Extraction from LLM Responses

Extraction Strategy (Iteration 3 — revised)
--------------------------------------------
The LLM is instructed (via TASK_BLOCK Rule 7 in prompt_architect.py) to wrap
every formalised requirement in explicit XML-style delimiters:

    <REQ type="functional" category="functional">
    The system shall allow the user to record water intake in litres.
    </REQ>

This is the PRIMARY extraction strategy. It reliably captures multi-line
requirements with bullet sub-items intact, and gives us type + category
without regex inference.

Two FALLBACK strategies are kept for backward-compatibility:
  - PATTERN: explicit "Requirement N (Type):" numbered format
  - SHALL:    "The system shall ..." sentence

Root Cause of the original bug
--------------------------------
The old extractor used a single-line regex that captured only the first line:
    "The system shall deliver the following reminders at the specified times:"
and discarded the bullet sub-lines. The REQ-tag approach solves this by design:
everything between <REQ> and </REQ> is captured, including all sub-items.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conversation_state import ConversationState


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# PRIMARY: REQ tag — DOTALL captures multi-line content including bullet items
_PATTERN_REQ_TAG = re.compile(
    r'<REQ\s+type=["\']([^"\']+)["\']\s+category=["\']([^"\']+)["\']\s*>'
    r'\s*(.*?)\s*</REQ>',
    re.DOTALL | re.IGNORECASE,
)

# FALLBACK 1: "**Requirement N (Type):** text" — single line
_PATTERN_EXPLICIT = re.compile(
    r'(?:\*\*)?Requirement\s+\d+\s*\(([^)]+)\)\s*:?\*?\*?\s*([^\n]+)',
    re.IGNORECASE,
)

# FALLBACK 2: "The system shall ..." — single line
_PATTERN_SHALL = re.compile(
    r'(?:The\s+(?:system|app|application|user|platform)\s+shall|Users?\s+shall)\s+'
    r'([^\n.]{10,200}[.!?]?)',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Normalisation maps
# ---------------------------------------------------------------------------

_TYPE_NORM = {
    "functional": "functional",
    "non-functional": "non_functional",
    "non_functional": "non_functional",   # underscore variant from tag attribute
    "nonfunctional": "non_functional",
    "non functional": "non_functional",
    "constraint": "constraint",
    "constraints": "constraint",
    "performance": "non_functional",
    "security": "non_functional",
    "usability": "non_functional",
    "reliability": "non_functional",
    "compatibility": "non_functional",
    "maintainability": "non_functional",
}

_VALID_CATEGORIES = {
    "functional", "performance", "usability", "security_privacy",
    "reliability", "compatibility", "maintainability",
    "interfaces", "constraints", "stakeholders", "scope", "purpose",
}

_CATEGORY_INFERENCE = [
    ("performance",      ["response time", "latency", "throughput", "millisecond", "second",
                          "concurrent", "fast", "load", "speed"]),
    ("usability",        ["usability", "easy to use", "intuitive", "accessibility", "user experience"]),
    ("security_privacy", ["authentication", "authoriz", "authoris", "encrypt", "security",
                          "privacy", "gdpr", "password", "access control"]),
    ("reliability",      ["uptime", "availability", "failover", "backup", "recover",
                          "downtime", "fault", "sla", "reliab"]),
    ("compatibility",    ["android", "ios", "browser", "platform", "operating system", "compat"]),
    ("maintainability",  ["maintainab", "update", "upgrade", "modular", "extensib"]),
    ("interfaces",       ["api", "third-party", "external system", "webhook"]),
    ("functional",       ["shall", "must", "allow", "enable", "provide", "record",
                          "track", "display", "notify", "create", "edit", "delete"]),
]


def _infer_category(text: str) -> str:
    lower = text.lower()
    for cat, kws in _CATEGORY_INFERENCE:
        if any(kw in lower for kw in kws):
            return cat
    return "functional"


def _norm_type(raw: str) -> str:
    return _TYPE_NORM.get(raw.lower().strip(), "functional")


def _norm_category(raw: str) -> str:
    n = raw.lower().strip().replace("-", "_").replace(" ", "_")
    return n if n in _VALID_CATEGORIES else ""


def _clean(text: str) -> str:
    """Remove markdown formatting, preserve internal structure."""
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'^\s*#+\s*', '', text, flags=re.MULTILINE)
    return text.strip()


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class ExtractedReq:
    text:        str
    req_type:    str   # "functional" | "non_functional" | "constraint"
    category:    str   # IEEE-830 category key
    raw_excerpt: str   # for traceability
    source:      str   # "tag" | "pattern" | "shall"

    def __str__(self):
        return f"[{self.req_type.upper()}|{self.category}] {self.text[:70].replace(chr(10),' ')}"


# ---------------------------------------------------------------------------
# RequirementExtractor
# ---------------------------------------------------------------------------

class RequirementExtractor:
    """
    Extracts formalised requirements from an LLM assistant response.

    Primary:   <REQ type="..." category="..."> ... </REQ>  (captures full multi-line text)
    Fallback1: Requirement N (Type): ...                   (single line, backward compat)
    Fallback2: The system shall ...                        (single line, last resort)
    """

    def __init__(self, min_text_length: int = 15):
        self.min_text_length = min_text_length

    def extract(self, assistant_response: str) -> list[ExtractedReq]:
        results: list[ExtractedReq] = []
        seen: set[str] = set()

        def _add(req: ExtractedReq) -> None:
            key = re.sub(r'\s+', ' ', req.text.strip().lower())
            if key not in seen and len(req.text.strip()) >= self.min_text_length:
                seen.add(key)
                results.append(req)

        # ── Strategy 1: REQ tags ─────────────────────────────────────
        tag_matches = _PATTERN_REQ_TAG.findall(assistant_response)
        for raw_type, raw_cat, raw_text in tag_matches:
            req_type = _norm_type(raw_type)
            category = _norm_category(raw_cat) or _infer_category(raw_text)
            text     = _clean(raw_text)
            excerpt  = f'<REQ type="{raw_type}" category="{raw_cat}">\n{raw_text.strip()}\n</REQ>'
            _add(ExtractedReq(text=text, req_type=req_type,
                              category=category, raw_excerpt=excerpt, source="tag"))

        # ── Strategy 2: numbered "Requirement N (Type):" (fallback) ──
        if not tag_matches:
            for m in _PATTERN_EXPLICIT.finditer(assistant_response):
                text     = _clean(m.group(2).rstrip("*").strip())
                req_type = _norm_type(m.group(1))
                category = _infer_category(text)
                _add(ExtractedReq(text=text, req_type=req_type,
                                  category=category, raw_excerpt=m.group(0).strip(),
                                  source="pattern"))

        # ── Strategy 3: "The system shall ..." (last resort) ─────────
        if not tag_matches and not any(r.source == "pattern" for r in results):
            for m in _PATTERN_SHALL.finditer(assistant_response):
                text     = _clean(m.group(0).strip())
                category = _infer_category(text)
                _add(ExtractedReq(text=text, req_type="functional",
                                  category=category, raw_excerpt=text, source="shall"))

        return results

    def commit(self, extracted: list[ExtractedReq], state: "ConversationState") -> list[str]:
        """Commit extracted requirements to state. Returns new req IDs."""
        from conversation_state import RequirementType

        existing: set[str] = {
            re.sub(r'\s+', ' ', r.text.strip().lower())
            for r in state.requirements.values()
        }

        added: list[str] = []
        for ext in extracted:
            key = re.sub(r'\s+', ' ', ext.text.strip().lower())
            if key in existing:
                continue
            rt = (RequirementType.FUNCTIONAL   if ext.req_type == "functional" else
                  RequirementType.NON_FUNCTIONAL if ext.req_type == "non_functional" else
                  RequirementType.CONSTRAINT)
            req = state.add_requirement(
                req_type=rt, text=ext.text,
                category=ext.category, raw_excerpt=ext.raw_excerpt,
            )
            added.append(req.req_id)
            existing.add(key)
        return added


def create_extractor() -> RequirementExtractor:
    return RequirementExtractor()