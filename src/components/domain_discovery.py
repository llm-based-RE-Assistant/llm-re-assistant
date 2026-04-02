"""
src/components/domain_discovery.py — Iteration 5
University of Hildesheim

Fixes: FIX-1 seed prompt implicit subsystems, FIX-2 plain-language probes,
FIX-3 decomp dedup, FIX-4 LLM domain matching, FIX-5 confirmation threshold,
FIX-6 fallback probe with example
"""
from __future__ import annotations
import json, re, time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from conversation_state import ConversationState

NFR_CATEGORIES: dict[str, str] = {
    "performance":     "Performance Requirements",
    "usability":       "Usability & Accessibility Requirements",
    "security_privacy":"Security & Privacy Requirements",
    "reliability":     "Reliability & Availability Requirements",
    "compatibility":   "Compatibility & Portability Requirements",
    "maintainability": "Maintainability Requirements",
}
STRUCTURAL_CATEGORIES: dict[str, str] = {
    "purpose":"System Purpose & Goals","scope":"System Scope & Boundaries",
    "stakeholders":"Stakeholders & User Classes","functional":"Functional Requirements",
    "interfaces":"External Interfaces","constraints":"Design & Implementation Constraints",
}
MIN_FUNCTIONAL_FOR_NFR = 10
DOMAIN_SUB_DIMENSIONS = ["data","actions","constraints","automation","edge_cases"]

# ── SEED — FIX-1: device→function mapping ──
_SEED_PROMPT = """\
You are a requirements engineering expert.

A stakeholder described their software system:
---
{description}
---

Identify the FUNCTIONAL DOMAINS for a complete SRS.

CRITICAL:
1. Include domains the stakeholder EXPLICITLY mentioned.
2. For EVERY physical device or sensor mentioned, create a domain for the
   CONTROL FUNCTION it implies (not just connectivity):
   - thermostat → "Temperature Control"
   - dehumidifier/humidistat → "Humidity Control"
   - door locks → "Door Lock Control"
   - lights → "Lighting Control"
   - alarm/security panel → "Security Alarm Management"
   - appliances/coffee maker → "Appliance Control"
   - cameras → "Security Camera Monitoring"
3. Also include TYPICAL system domains:
   - User account/role management
   - Planning and scheduling (presets, time-based automation)
   - Reporting and history (monthly reports, data export)
   - Alerts and notifications
   - User documentation and help
4. Domain names: 2-5 words, title-case, USER-FACING function names.
5. Aim for 8-12 domains. Do NOT include NFRs. Return ONLY a JSON array.

Your JSON array:"""

_RESEED_PROMPT = """\
You are a requirements engineering expert. Mid-session coverage check.

SYSTEM DESCRIPTION: {description}

REQUIREMENTS SO FAR ({req_count} total):
{req_sample}

CURRENT DOMAINS: {current_domains}

Identify MISSING functional domains. For every device/sensor in requirements
without a dedicated control domain, add one. Also add typical system domains
that are missing. Return ONLY a JSON array of NEW domains (may be empty: [])."""

_NFR_CLASSIFY_PROMPT = """\
Classify this requirement into one IEEE-830 NFR category:
  performance, usability, security_privacy, reliability, compatibility, maintainability

Requirement: "{text}"
Reply with ONLY the category key."""

_SUBDIM_CLASSIFY_PROMPT = """\
Classify into one: data, actions, constraints, automation, edge_cases
Requirement: "{text}"
Reply with ONLY one word."""

_DOMAIN_MATCH_PROMPT = """\
Which domain does this requirement belong to?

Requirement: "{req_text}"

Domains:
{domain_list}

Reply with ONLY the domain key (text before the colon). If none fit, reply "none"."""

_DECOMPOSE_PROMPT = """\
You are a requirements engineering expert. Generate MISSING atomic requirements
for the "{domain_label}" domain of a "{project_name}" system.

EXISTING REQUIREMENTS FOR THIS DOMAIN:
{existing_reqs}

ALL OTHER REQUIREMENTS ALREADY CAPTURED:
{all_other_reqs}

Generate 2-5 requirements that are COMPLETELY MISSING. Focus on:
1. Specific numbers, ranges, capacities, units
2. Scheduling/planning: time slots, granularity
3. Override behaviour: manual vs scheduled, expiry
4. Data storage: retention period, reporting
5. Error/edge cases: failure handling

Rules:
- Each: ONE atomic "The system shall..." statement with specific numbers
- Do NOT repeat ANY existing requirement
- Return ONLY a JSON array of strings"""

_PROJECT_NAME_PROMPT = """\
A stakeholder described their system: "{message}"
What is the system name (2-5 words)? Reply with ONLY the name."""


@dataclass
class DomainSpec:
    label: str
    req_ids: list[str] = field(default_factory=list)
    status: str = "unprobed"
    probe_question: str = ""
    sub_dimensions: dict[str, list[str]] = field(default_factory=dict)
    probe_count: int = 0
    decomposed: bool = False

    def to_dict(self) -> dict:
        return {"label":self.label,"req_ids":self.req_ids,"status":self.status,
                "probe_question":self.probe_question,
                "sub_dimensions":dict(self.sub_dimensions),
                "probe_count":self.probe_count,"decomposed":self.decomposed}

    @property
    def covered_subdim_count(self) -> int:
        return sum(1 for ids in self.sub_dimensions.values() if ids)

    @property
    def needs_deeper_probing(self) -> bool:
        if self.status in ("excluded","confirmed"):
            return False
        return len(self.req_ids) < 3


@dataclass
class DomainGate:
    domains: dict[str, DomainSpec] = field(default_factory=dict)
    seeded: bool = False
    seed_turn: int = 0
    reseed_turn: int = 0
    last_updated: float = field(default_factory=time.time)

    @property
    def total(self) -> int: return len(self.domains)
    @property
    def done_count(self) -> int:
        return sum(1 for d in self.domains.values() if d.status in ("confirmed","excluded"))
    @property
    def is_satisfied(self) -> bool:
        return self.seeded and self.total > 0 and self.done_count == self.total
    @property
    def completeness_pct(self) -> int:
        return round(self.done_count/self.total*100) if self.total else 0

    def next_unprobed(self) -> Optional[DomainSpec]:
        for d in self.domains.values():
            if d.status == "unprobed": return d
        for d in self.domains.values():
            if d.status == "partial" and d.needs_deeper_probing: return d
        return None

    def to_dict(self) -> dict:
        return {"seeded":self.seeded,"seed_turn":self.seed_turn,
                "reseed_turn":self.reseed_turn,"total":self.total,
                "done_count":self.done_count,"is_satisfied":self.is_satisfied,
                "completeness_pct":self.completeness_pct,
                "domains":{k:v.to_dict() for k,v in self.domains.items()}}


class DomainDiscovery:
    RESEED_TURN = 4

    def __init__(self, llm_provider) -> None:
        self._provider = llm_provider

    def seed(self, description, gate, turn_id):
        if gate.seeded: return
        for label in self._call_seed(description):
            key = _label_to_key(label)
            if key not in gate.domains:
                gate.domains[key] = DomainSpec(label=label)
        gate.seeded = True
        gate.seed_turn = turn_id

    def reseed(self, description, gate, state, turn_id):
        if gate.reseed_turn > 0: return
        current = [d.label for d in gate.domains.values()]
        for label in self._call_reseed(description, state.total_requirements,
                                       _build_req_sample(state), current):
            key = _label_to_key(label)
            if key not in gate.domains:
                gate.domains[key] = DomainSpec(label=label, status="unprobed")
        gate.reseed_turn = turn_id

    # FIX-5: threshold = 2 reqs
    def update_domain_statuses(self, gate, state):
        req_map = {k: [] for k in gate.domains}
        for rid, req in state.requirements.items():
            dk = getattr(req, "domain_key", None)
            if dk and dk in gate.domains:
                req_map[dk].append(rid)
        for key, domain in gate.domains.items():
            if domain.status == "excluded": continue
            domain.req_ids = req_map.get(key, [])
            if len(domain.req_ids) >= 3:
                domain.status = "confirmed"
            elif len(domain.req_ids) >= 1:
                domain.status = "partial"

    def classify_subdimension(self, req_text):
        return self._call_classify_subdim(req_text)

    def tag_subdimension(self, req_id, subdim, domain_key, gate):
        if domain_key not in gate.domains: return
        d = gate.domains[domain_key]
        if subdim not in d.sub_dimensions: d.sub_dimensions[subdim] = []
        if req_id not in d.sub_dimensions[subdim]:
            d.sub_dimensions[subdim].append(req_id)

    def classify_nfr(self, req_text):
        return self._call_classify_nfr(req_text)

    def get_probe_question(self, domain, state):
        if domain.probe_question and domain.probe_count == 0:
            return domain.probe_question
        q = self._generate_probe(domain, state)
        domain.probe_question = q
        return q

    # FIX-3: full dedup context
    def decompose_requirements(self, domain_key, gate, state):
        if domain_key not in gate.domains: return []
        domain = gate.domains[domain_key]
        if domain.decomposed: return []
        own = [f"- {state.requirements[rid].text}" for rid in domain.req_ids
               if rid in state.requirements]
        if not own:
            domain.decomposed = True; return []
        other = [f"- {r.text[:100]}" for rid,r in state.requirements.items()
                 if rid not in domain.req_ids]
        result = self._call_decompose(domain.label, state.project_name,
                                      "\n".join(own), "\n".join(other[:20]) or "(none)")
        domain.decomposed = True
        return result

    # FIX-4: LLM domain matching
    def match_requirement_to_domain(self, req_text, gate):
        if not gate.seeded or not gate.domains: return None
        dlist = "\n".join(f"  {k}: {d.label}" for k,d in gate.domains.items())
        prompt = _DOMAIN_MATCH_PROMPT.format(req_text=req_text[:200], domain_list=dlist)
        try:
            raw = self._provider.chat(
                system_message="Match requirements to domains. Reply with only the domain key.",
                messages=[{"role":"user","content":prompt}], temperature=0.0)
            key = raw.strip().lower().split()[0].rstrip(".,;:")
            if key in gate.domains: return key
            for dk in gate.domains:
                if dk.startswith(key) or key.startswith(dk[:6]): return dk
        except Exception: pass
        return None

    def extract_project_name(self, msg):
        try:
            raw = self._provider.chat(
                system_message="Extract system names. Reply with only the name.",
                messages=[{"role":"user","content":_PROJECT_NAME_PROMPT.format(message=msg[:500])}],
                temperature=0.0)
            name = raw.strip().strip('"\'').strip()
            return name if 2 <= len(name) <= 80 else None
        except Exception: return None

    # ── Internal LLM calls ──

    def _call_seed(self, desc):
        try:
            raw = self._provider.chat(
                system_message="Requirements engineering expert. Return only valid JSON.",
                messages=[{"role":"user","content":_SEED_PROMPT.format(description=desc[:2000])}],
                temperature=0.0)
            return _parse_json_list(raw)
        except Exception: return []

    def _call_reseed(self, desc, req_count, req_sample, current):
        try:
            raw = self._provider.chat(
                system_message="Requirements engineering expert. Return only valid JSON.",
                messages=[{"role":"user","content":_RESEED_PROMPT.format(
                    description=desc[:1000], req_count=req_count,
                    req_sample=req_sample, current_domains=json.dumps(current))}],
                temperature=0.0)
            return _parse_json_list(raw)
        except Exception: return []

    def _call_classify_nfr(self, text):
        try:
            raw = self._provider.chat(
                system_message="Classify requirements. One category key only.",
                messages=[{"role":"user","content":_NFR_CLASSIFY_PROMPT.format(text=text[:300])}],
                temperature=0.0)
            k = raw.strip().lower().split()[0].rstrip(".,;:")
            if k in NFR_CATEGORIES: return k
            for ck in NFR_CATEGORIES:
                if ck in k or k in ck: return ck
            return None
        except Exception: return None

    def _call_classify_subdim(self, text):
        try:
            raw = self._provider.chat(
                system_message="Classify requirements. One word only.",
                messages=[{"role":"user","content":_SUBDIM_CLASSIFY_PROMPT.format(text=text[:300])}],
                temperature=0.0)
            k = raw.strip().lower().split()[0].rstrip(".,;:")
            valid = {"data","actions","constraints","automation","edge_cases"}
            if k in valid: return k
            for v in valid:
                if v in k or k in v: return v
            return "actions"
        except Exception: return "actions"

    def _call_decompose(self, domain_label, project_name, existing, all_other):
        try:
            raw = self._provider.chat(
                system_message="Requirements engineering expert. Return only valid JSON.",
                messages=[{"role":"user","content":_DECOMPOSE_PROMPT.format(
                    domain_label=domain_label, project_name=project_name,
                    existing_reqs=existing, all_other_reqs=all_other)}],
                temperature=0.2)
            return [r.strip() for r in _parse_json_list(raw) if len(r.strip())>=20][:5]
        except Exception: return []

    # FIX-2: plain language probes with examples
    def _generate_probe(self, domain, state):
        history = "\n".join(
            f"User: {t.user_message[:150]}\nAssistant: {t.assistant_message[:150]}"
            for t in state.turns[-3:]) or "(no turns yet)"
        covered = [d for d,ids in domain.sub_dimensions.items() if ids]
        missing = [d for d in DOMAIN_SUB_DIMENSIONS if d not in covered]
        focus = ""
        if domain.probe_count > 0 and missing:
            hints = {"constraints":"specific numbers — how many, what range, min/max",
                     "automation":"things that happen automatically — schedules, timers",
                     "edge_cases":"what happens when something goes wrong or the user overrides a setting",
                     "data":"what information gets stored, for how long, and any reports needed",
                     "actions":"what specific things the user can do"}
            focus = f"\nFocus on: {hints.get(missing[0],'')}"

        prompt = (
            f"You are interviewing a NON-TECHNICAL person about their system.\n\n"
            f"System: {state.project_name}\n"
            f"Recent conversation:\n{history}\n\n"
            f"Topic to ask about: {domain.label}\n"
            f"Requirements captured so far: {len(domain.req_ids)}{focus}\n\n"
            f"RULES:\n"
            f"1. Use PLAIN EVERYDAY LANGUAGE — no technical terms.\n"
            f"2. NEVER put the domain label in your question.\n"
            f"   BAD: 'Tell me about Error Detection & Recovery'\n"
            f"   GOOD: 'What should happen if something breaks — like if a sensor stops working or the internet goes out?'\n"
            f"3. ALWAYS include a concrete example from their system.\n"
            f"4. Ask for specific numbers where relevant.\n"
            f"5. ONE sentence ending in '?'\n\n"
            f"Question:")
        try:
            raw = self._provider.chat(
                system_message="You are a friendly interviewer using simple everyday language.",
                messages=[{"role":"user","content":prompt}], temperature=0.3)
            q = raw.strip().strip('"\'')
            return q if q.endswith("?") else q.rstrip(".")+  "?"
        except Exception:
            return (f"I'd like to understand more about how you'd use the "
                    f"{domain.label.lower()} features — for example, "
                    f"how often would you use them and what's most important to you?")


# ── Structural coverage ──
_MIN_FR_FOR_FUNCTIONAL_COVERAGE = 3

def compute_structural_coverage(state) -> set[str]:
    covered = set()
    from conversation_state import RequirementType
    if sum(1 for r in state.requirements.values()
           if r.req_type==RequirementType.FUNCTIONAL) >= _MIN_FR_FOR_FUNCTIONAL_COVERAGE:
        covered.add("functional")
    if state.project_name and state.project_name not in ("Unknown Project","Unnamed Project"):
        covered.add("purpose")
    if state.turn_count >= 2: covered.add("scope")
    text = " ".join(r.text.lower() for r in state.requirements.values())
    if any(kw in text for kw in ["user","admin","technician","role","account",
           "stakeholder","operator","manager","customer"]): covered.add("stakeholders")
    if any(kw in text for kw in ["interface","api","gateway","sensor","device",
           "wireless","mobile","web","browser","app","thermostat","switch"]): covered.add("interfaces")
    if sum(1 for r in state.requirements.values()
           if r.req_type==RequirementType.CONSTRAINT) >= 1: covered.add("constraints")
    return covered

def _label_to_key(label):
    return re.sub(r"[^a-z0-9]+","_",label.lower().strip()).strip("_")

def _parse_json_list(raw):
    text = re.sub(r"```(?:json)?\s*","",raw.strip()).strip().strip("`")
    m = re.search(r"\[.*?\]",text,re.DOTALL)
    if not m: return []
    try:
        result = json.loads(m.group(0))
        return [str(i).strip() for i in result if str(i).strip()] if isinstance(result,list) else []
    except json.JSONDecodeError: return []

def _build_req_sample(state):
    reqs = list(state.requirements.values())[:15]
    return "\n".join(f"- {r.text[:120]}" for r in reqs) if reqs else "(none yet)"

def create_domain_discovery(llm_provider):
    return DomainDiscovery(llm_provider=llm_provider)