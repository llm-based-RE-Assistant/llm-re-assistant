"""
requirement_preprocessor.py
============================
RE Assistant — Iteration 9 | University of Hildesheim

Handles uploaded requirement files (.txt / .json).
Pipeline:
  1. Parse file (txt = one req per line, json = array of strings or objects)
  2. LLM call: quality check, rewrite if needed, atomize, assign type + category
  3. Return structured list ready for domain seeding and session injection

The LLM returns each requirement in a <REQ> tag (same contract as elicitation)
plus a JSON summary used to seed the domain gate.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from conversation_manager import LLMProvider

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ProcessedRequirement:
    original_text: str
    final_text: str
    req_type: str          # "functional" | "non_functional" | "constraint"
    category: str          # functional domain key OR nfr category key
    category_label: str    # human-readable label
    smart_score: int = 3
    was_rewritten: bool = False
    was_split: bool = False   # True if this was split from a compound req
    atomic_index: int = 0     # index within split (0 = only child or first)

    def to_dict(self):
        return {
            "original_text": self.original_text,
            "final_text": self.final_text,
            "req_type": self.req_type,
            "category": self.category,
            "category_label": self.category_label,
            "smart_score": self.smart_score,
            "was_rewritten": self.was_rewritten,
            "was_split": self.was_split,
        }


@dataclass
class PreprocessResult:
    requirements: list[ProcessedRequirement] = field(default_factory=list)
    domains_found: list[str] = field(default_factory=list)     # unique functional domain labels
    nfr_categories_found: list[str] = field(default_factory=list)
    total_input: int = 0
    total_output: int = 0     # may differ if splits happened
    rewritten_count: int = 0
    split_count: int = 0
    error: Optional[str] = None

    def to_dict(self):
        return {
            "requirements": [r.to_dict() for r in self.requirements],
            "domains_found": self.domains_found,
            "nfr_categories_found": self.nfr_categories_found,
            "total_input": self.total_input,
            "total_output": self.total_output,
            "rewritten_count": self.rewritten_count,
            "split_count": self.split_count,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# LLM Prompt
# ---------------------------------------------------------------------------

_PREPROCESS_SYSTEM = """\
You are a senior Requirements Engineer. Your job is to take a raw list of requirements \
and return a high-quality, structured version of each one.

You must:
1. Check if each requirement is ATOMIC (expresses exactly one testable need).
   If it is compound (contains "and", "or", multiple verbs/actions), SPLIT it into
   separate atomic requirements.
2. Check SMART quality (Specific, Measurable, Achievable, Relevant, Testable).
   If vague terms exist ("fast", "easy", "good"), REWRITE to add concrete values.
3. Assign REQ_TYPE: "functional", "non_functional", or "constraint".
4. Assign CATEGORY:
   - For functional reqs: assign the most fitting functional domain label
     (e.g., "User Authentication", "Booking Management", "Notification System",
      "Reporting & Analytics", "Payment Processing", "Search & Discovery", etc.)
   - For non_functional reqs: assign one of these exact keys:
     performance | usability | security_privacy | reliability | compatibility | maintainability
   - For constraints: use "constraint"
5. Assign SMART_SCORE (1-5).

Return ONLY a JSON array. Each element must have:
{
  "original": "<original text>",
  "final": "<rewritten or same>",
  "req_type": "functional|non_functional|constraint",
  "category": "<domain label or nfr key>",
  "category_label": "<human readable label>",
  "smart_score": 1-5,
  "was_rewritten": true/false,
  "was_split": true/false,
  "atomic_index": 0
}

If a requirement was split, produce multiple objects all with "was_split": true,
with atomic_index 0, 1, 2... and the same "original" value.

Return ONLY the JSON array. No markdown, no explanation. No code fences."""

_PREPROCESS_USER = """\
Project context: {project_context}

Requirements to process ({count} items):
{req_list}

Return the JSON array now."""


# ---------------------------------------------------------------------------
# File parser
# ---------------------------------------------------------------------------

def parse_requirements_file(content: str, filename: str) -> tuple[list[str], Optional[str]]:
    """
    Parse uploaded file content into a list of requirement strings.
    Returns (requirements, error_message).
    Supports .txt (one per line) and .json (array of str or {text:...} objects).
    """
    filename_lower = filename.lower()

    if filename_lower.endswith(".json"):
        try:
            data = json.loads(content)
            if not isinstance(data, list):
                return [], "JSON file must contain a top-level array."
            reqs = []
            for item in data:
                if isinstance(item, str):
                    reqs.append(item.strip())
                elif isinstance(item, dict):
                    # Accept {"text":..., "requirement":..., "description":...}
                    for key in ("text", "requirement", "description", "req"):
                        if key in item and isinstance(item[key], str):
                            reqs.append(item[key].strip())
                            break
            reqs = [r for r in reqs if r]
            if not reqs:
                return [], "No requirements found in JSON array."
            return reqs, None
        except json.JSONDecodeError as e:
            return [], f"Invalid JSON: {e}"

    elif filename_lower.endswith(".txt"):
        lines = [l.strip() for l in content.splitlines()]
        reqs = []
        for line in lines:
            # Skip blank lines, comment lines
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            # Strip common bullet/numbering: "1.", "-", "*", "•"
            line = re.sub(r"^[\d]+[\.\)]\s*", "", line)
            line = re.sub(r"^[-*•]\s*", "", line).strip()
            if len(line) > 5:
                reqs.append(line)
        if not reqs:
            return [], "No requirements found in .txt file."
        return reqs, None

    else:
        return [], "Unsupported file type. Only .txt and .json are accepted."


# ---------------------------------------------------------------------------
# Core preprocessor
# ---------------------------------------------------------------------------

class RequirementPreprocessor:
    """LLM-powered requirement quality checker and domain classifier."""

    BATCH_SIZE = 30   # max reqs per LLM call (to avoid context overflow)

    def __init__(self, provider: "LLMProvider"):
        self._provider = provider

    def process(
        self,
        raw_requirements: list[str],
        project_context: str = "Unknown project",
    ) -> PreprocessResult:
        """
        Full pipeline: parse → LLM quality check → structured output.
        Processes in batches if needed.
        """
        result = PreprocessResult(total_input=len(raw_requirements))
        if not raw_requirements:
            result.error = "Empty requirements list."
            return result

        # Process in batches
        all_processed: list[ProcessedRequirement] = []
        for i in range(0, len(raw_requirements), self.BATCH_SIZE):
            batch = raw_requirements[i: i + self.BATCH_SIZE]
            batch_result = self._process_batch(batch, project_context)
            all_processed.extend(batch_result)

        # Deduplicate by final text (case-insensitive)
        seen: set[str] = set()
        deduped: list[ProcessedRequirement] = []
        for r in all_processed:
            key = r.final_text.lower().strip()
            if key not in seen:
                seen.add(key)
                deduped.append(r)

        result.requirements = deduped
        result.total_output = len(deduped)
        result.rewritten_count = sum(1 for r in deduped if r.was_rewritten)
        result.split_count = sum(1 for r in deduped if r.was_split)

        # Collect unique domains and NFR categories
        nfr_keys = {"performance", "usability", "security_privacy",
                    "reliability", "compatibility", "maintainability", "constraint"}
        result.domains_found = sorted({
            r.category_label for r in deduped
            if r.req_type == "functional" and r.category not in nfr_keys
        })
        result.nfr_categories_found = sorted({
            r.category for r in deduped
            if r.req_type == "non_functional" and r.category in nfr_keys
        })

        return result

    def _process_batch(
        self,
        batch: list[str],
        project_context: str,
    ) -> list[ProcessedRequirement]:
        """Run one LLM call on a batch of up to BATCH_SIZE requirements."""
        req_list = "\n".join(f"{i+1}. {r}" for i, r in enumerate(batch))
        prompt = _PREPROCESS_USER.format(
            project_context=project_context[:200],
            count=len(batch),
            req_list=req_list,
        )
        try:
            raw = self._provider.chat(
                system_message=_PREPROCESS_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            # Strip any accidental code fences
            text = re.sub(r"```(?:json)?\s*", "", raw.strip()).strip().strip("`")
            m = re.search(r"\[.*\]", text, re.DOTALL)
            if not m:
                return self._fallback_batch(batch)
            items = json.loads(m.group(0))
            if not isinstance(items, list):
                return self._fallback_batch(batch)

            processed: list[ProcessedRequirement] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                original = item.get("original", "")
                final = item.get("final", original) or original
                req_type = item.get("req_type", "functional")
                category = item.get("category", "general")
                category_label = item.get("category_label", category.replace("_", " ").title())
                smart_score = int(item.get("smart_score", 3))
                was_rewritten = bool(item.get("was_rewritten", False))
                was_split = bool(item.get("was_split", False))
                atomic_index = int(item.get("atomic_index", 0))

                processed.append(ProcessedRequirement(
                    original_text=original,
                    final_text=final.strip(),
                    req_type=req_type,
                    category=category,
                    category_label=category_label,
                    smart_score=smart_score,
                    was_rewritten=was_rewritten,
                    was_split=was_split,
                    atomic_index=atomic_index,
                ))
            return processed if processed else self._fallback_batch(batch)

        except Exception as e:
            print(f"[RequirementPreprocessor] LLM call failed: {e}")
            return self._fallback_batch(batch)

    def _fallback_batch(self, batch: list[str]) -> list[ProcessedRequirement]:
        """If LLM fails, return passthrough requirements with defaults."""
        return [
            ProcessedRequirement(
                original_text=r,
                final_text=r,
                req_type="functional",
                category="general",
                category_label="General",
                smart_score=3,
            )
            for r in batch
        ]


def create_preprocessor(provider: "LLMProvider") -> RequirementPreprocessor:
    return RequirementPreprocessor(provider)