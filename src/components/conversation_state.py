"""
src/components/conversation_state.py — Iteration 5
University of Hildesheim

FIX-NFR: is_ready_for_srs() now ALWAYS requires mandatory_nfrs_covered.
"""
from __future__ import annotations
import json, re, time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class RequirementType(str, Enum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    CONSTRAINT = "constraint"
    UNKNOWN = "unknown"

class CoverageStatus(str, Enum):
    NOT_STARTED = "not_started"
    PARTIALLY = "partially_covered"
    COVERED = "covered"

@dataclass
class Requirement:
    req_id: str
    req_type: RequirementType
    text: str
    turn_id: int
    category: str
    raw_excerpt: str
    timestamp: float = field(default_factory=time.time)
    is_ambiguous: bool = False
    ambiguity_note: str = ""
    domain_key: str = ""
    source: str = "elicited"

    def to_dict(self):
        return {"req_id":self.req_id,"req_type":self.req_type.value,"text":self.text,
                "turn_id":self.turn_id,"category":self.category,"raw_excerpt":self.raw_excerpt,
                "timestamp":self.timestamp,"is_ambiguous":self.is_ambiguous,
                "ambiguity_note":self.ambiguity_note,"domain_key":self.domain_key,
                "source":self.source}

@dataclass
class Turn:
    turn_id: int
    user_message: str
    assistant_message: str
    timestamp: float = field(default_factory=time.time)
    categories_updated: list[str] = field(default_factory=list)
    requirements_added: list[str] = field(default_factory=list)

    def to_dict(self):
        return {"turn_id":self.turn_id,"user_message":self.user_message,
                "assistant_message":self.assistant_message,"timestamp":self.timestamp,
                "categories_updated":self.categories_updated,
                "requirements_added":self.requirements_added}

@dataclass
class ConversationState:
    session_id: str
    project_name: str = "Unknown Project"
    turns: list[Turn] = field(default_factory=list)
    requirements: dict[str, Requirement] = field(default_factory=dict)
    domain_gate: object = field(default=None)
    nfr_coverage: dict[str, int] = field(default_factory=dict)
    session_complete: bool = False
    project_name_needs_llm: bool = field(default=False, repr=False)
    _fr_counter: int = field(default=0, repr=False)
    _nfr_counter: int = field(default=0, repr=False)
    _con_counter: int = field(default=0, repr=False)

    @property
    def turn_count(self): return len(self.turns)
    @property
    def total_requirements(self): return len(self.requirements)
    @property
    def functional_count(self):
        return sum(1 for r in self.requirements.values() if r.req_type==RequirementType.FUNCTIONAL)
    @property
    def nonfunctional_count(self):
        return sum(1 for r in self.requirements.values() if r.req_type==RequirementType.NON_FUNCTIONAL)
    @property
    def constraint_count(self):
        return sum(1 for r in self.requirements.values() if r.req_type==RequirementType.CONSTRAINT)

    @property
    def covered_categories(self):
        covered = set()
        try:
            from domain_discovery import compute_structural_coverage
            covered |= compute_structural_coverage(self)
        except ImportError: pass
        for ck, cnt in self.nfr_coverage.items():
            if cnt >= 1: covered.add(ck)
        return covered

    @property
    def coverage_percentage(self):
        from prompt_architect import IEEE830_CATEGORIES
        total = len(IEEE830_CATEGORIES)
        return round(len(self.covered_categories)/total*100, 1) if total else 0.0

    @property
    def mandatory_nfrs_covered(self):
        from domain_discovery import NFR_CATEGORIES
        return all(self.nfr_coverage.get(c,0)>=1 for c in NFR_CATEGORIES)

    @property
    def uncovered_categories(self):
        from prompt_architect import IEEE830_CATEGORIES
        return [k for k in IEEE830_CATEGORIES if k not in self.covered_categories]

    def _next_fr_id(self):
        self._fr_counter += 1; return f"FR-{self._fr_counter:03d}"
    def _next_nfr_id(self):
        self._nfr_counter += 1; return f"NFR-{self._nfr_counter:03d}"
    def _next_con_id(self):
        self._con_counter += 1; return f"CON-{self._con_counter:03d}"

    def add_turn(self, user_message, assistant_message):
        turn_id = self.turn_count + 1
        if turn_id == 1 and self.project_name == "Unknown Project":
            name = _extract_project_name(user_message)
            self.project_name = name
            if _is_poor_project_name(name):
                self.project_name_needs_llm = True
        turn = Turn(turn_id=turn_id, user_message=user_message,
                    assistant_message=assistant_message)
        self.turns.append(turn)
        return turn

    def add_requirement(self, req_type, text, category, raw_excerpt="",
                        is_ambiguous=False, ambiguity_note="", domain_key="",
                        source="elicited"):
        if req_type == RequirementType.FUNCTIONAL: req_id = self._next_fr_id()
        elif req_type == RequirementType.NON_FUNCTIONAL: req_id = self._next_nfr_id()
        else: req_id = self._next_con_id()
        req = Requirement(req_id=req_id, req_type=req_type, text=text,
                          turn_id=self.turn_count, category=category,
                          raw_excerpt=raw_excerpt, is_ambiguous=is_ambiguous,
                          ambiguity_note=ambiguity_note, domain_key=domain_key,
                          source=source)
        self.requirements[req_id] = req
        if self.turns: self.turns[-1].requirements_added.append(req_id)
        return req

    def increment_nfr_coverage(self, category_key):
        self.nfr_coverage[category_key] = self.nfr_coverage.get(category_key,0)+1

    def get_coverage_report(self):
        from prompt_architect import IEEE830_CATEGORIES
        from domain_discovery import NFR_CATEGORIES
        covered = self.covered_categories
        missing_nfrs = [IEEE830_CATEGORIES.get(c,c) for c in NFR_CATEGORIES
                        if self.nfr_coverage.get(c,0)<1]
        dg = {}; dcs = "0/0"; dcp = 0; dgs = False
        if self.domain_gate:
            dg = self.domain_gate.to_dict()
            dcs = f"{self.domain_gate.done_count}/{self.domain_gate.total}"
            dcp = self.domain_gate.completeness_pct
            dgs = self.domain_gate.is_satisfied
        return {
            "session_id":self.session_id,"project_name":self.project_name,
            "turn_count":self.turn_count,"total_requirements":self.total_requirements,
            "functional_count":self.functional_count,
            "nonfunctional_count":self.nonfunctional_count,
            "constraint_count":self.constraint_count,
            "coverage_percentage":self.coverage_percentage,
            "covered_categories":sorted(covered),
            "uncovered_categories":self.uncovered_categories,
            "mandatory_nfrs_covered":self.mandatory_nfrs_covered,
            "missing_mandatory_nfrs":missing_nfrs,
            "nfr_coverage":dict(self.nfr_coverage),
            "domain_gate":dg,"domain_completeness_score":dcs,
            "domain_completeness_pct":dcp,"domain_gate_satisfied":dgs,
        }

    def get_next_priority_category(self):
        from domain_discovery import NFR_CATEGORIES
        for c in NFR_CATEGORIES:
            if self.nfr_coverage.get(c,0)<1: return c
        return None

    # FIX-NFR: ALWAYS require mandatory NFRs before SRS
    def is_ready_for_srs(self):
        from prompt_architect import MIN_FUNCTIONAL_REQS
        if self.functional_count < MIN_FUNCTIONAL_REQS: return False
        if not self.mandatory_nfrs_covered: return False
        if self.domain_gate and self.domain_gate.seeded:
            return self.domain_gate.is_satisfied
        return True

    def to_dict(self):
        return {"session_id":self.session_id,"project_name":self.project_name,
                "session_complete":self.session_complete,
                "turns":[t.to_dict() for t in self.turns],
                "requirements":{k:v.to_dict() for k,v in self.requirements.items()},
                "nfr_coverage":dict(self.nfr_coverage),
                "coverage_report":self.get_coverage_report()}

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def get_message_history(self):
        msgs = []
        for t in self.turns:
            msgs.append({"role":"user","content":t.user_message})
            msgs.append({"role":"assistant","content":t.assistant_message})
        return msgs

def _extract_project_name(text):
    patterns = [
        r"(?:build|develop|create|make|design)\s+(?:a|an|the)\s+([A-Z][A-Za-z0-9 \-]+)",
        r"(?:called|named)\s+[\"']?([A-Z][A-Za-z0-9 \-]+)[\"']?",
        r"(?:for|about)\s+(?:a|an|the)\s+([A-Z][A-Za-z0-9 \-]+)",
        r"\"([A-Za-z][A-Za-z0-9 \-]+)\"", r"\'([A-Za-z][A-Za-z0-9 \-]+)\'",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if 3 <= len(name) <= 60: return name
    cleaned = text.strip().split("\n")[0][:50]
    return cleaned if cleaned else "Unnamed Project"

def _is_poor_project_name(name):
    if not name or name in ("Unknown Project","Unnamed Project"): return True
    if len(name) > 40: return True
    lower = name.lower()
    for bs in ["hi","hello","hey","well","i'm","my ","i ","we ",
               "okay","ok ","so ","um ","basically"]:
        if lower.startswith(bs): return True
    return False

def create_session(session_id):
    return ConversationState(session_id=session_id)