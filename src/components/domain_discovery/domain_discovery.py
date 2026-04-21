from __future__ import annotations
import json, re
from src.components.domain_discovery.domain_space import DomainSpec
from src.components.domain_discovery.utils import (
    NFR_CATEGORIES,
    SEED_PROMPT,
    RESEED_PROMPT,
    NFR_CLASSIFY_PROMPT,
    SUBDIM_CLASSIFY_PROMPT,
    DOMAIN_MATCH_PROMPT,
    DECOMPOSE_PROMPT,
    PROJECT_NAME_PROMPT,
    COMPLEXITY_PROMPT,
    DOMAIN_TEMPLATE_PROMPT
)

class DomainDiscovery:
    RESEED_TURN = 10
    SECOND_RESEED_TURN = 20
    THIRD_RESEED_TURN = 30

    def __init__(self, llm_provider) -> None:
        self._provider = llm_provider

    def seed(
            self,
            description,
            gate,
            turn_id,
            project_name="the system",
            project_brief=None
        ):
        """Seed the domain gate from either a structured project brief (Phase 0 output)
        or a raw description string (fallback for srs_only / upload flows).

        When project_brief is provided it takes priority — the structured fields
        give the seed prompt far richer, unambiguous signal than a raw first message.
        description is still accepted as a fallback and is appended as extra context.
        """
        if gate.seeded:
            return
        generated_domains_list = self._call_seed(
            description,
            project_name=project_name,
            project_brief=project_brief or {}
        )
        for label in generated_domains_list:
            key = _label_to_key(label)
            if key not in gate.domains:
                gate.domains[key] = DomainSpec(label=label)
        gate.seeded = True
        gate.seed_turn = turn_id

    def reseed(
            self,
            description,
            gate,
            state,
            turn_id,
            project_brief=None
        ):
        """IT10: Guard revised — allows multiple reseeds for complex systems.
        Instead of blocking after the first reseed (which caused permanent domain blindness
        in long sessions), we allow another reseed whenever the turn_id is strictly later
        than the last recorded reseed turn. The conversation_manager already gates reseed
        calls to RESEED_TURN and SECOND_RESEED_TURN, so this method no longer needs to
        enforce a once-only constraint itself.
        """
        if gate.reseed_turn >= turn_id:
            return  # already reseeded at or after this turn — skip
        current = [d.label for d in gate.domains.values()]
        complexity = getattr(state, "system_complexity", "") or "not yet assessed"
        generated_domains_list = self._call_reseed(
            description,
            state.total_requirements,
            _build_req_sample(state),
            current,
            project_name=state.project_name,
            complexity=complexity,
            project_brief=project_brief
        )
        for label in generated_domains_list:
            key = _label_to_key(label)
            if key not in gate.domains:
                gate.domains[key] = DomainSpec(label=label, status="unprobed")
        gate.reseed_turn = turn_id

    def seed_from_labels(self, domain_labels: list, gate, turn_id: int, project_name: str = "the system"):
        """IT9: Seed domain gate directly from a known list of domain labels (no LLM call needed).
        Used when domains are derived from uploaded requirements file."""
        if gate.seeded:
            return
        for label in domain_labels:
            key = _label_to_key(label)
            if key not in gate.domains:
                gate.domains[key] = DomainSpec(label=label, status="unprobed")
        if gate.domains:
            gate.seeded = True
            gate.seed_turn = turn_id
            print(f"[DomainDiscovery] Seeded {len(gate.domains)} domains from uploaded reqs labels")

    def update_domain_statuses(self, gate, state):
        """Update each domain's status based on requirement count AND probe history.

        IT10b: A domain is "confirmed" only when it has >= 3 requirements AND has
        been actively probed at least once (probe_count >= 1). This prevents
        decomposed or inferred requirements from silently confirming a domain that
        the RE assistant has never actually asked the customer about. Without this
        guard, domains accumulate requirements from domain-matching of unrelated
        elicitation and get confirmed before a single question is asked about them,
        which causes determine_elicitation_phase() to see is_satisfied=True
        prematurely and advance to NFR or IEEE phase after only a few turns.
        """
        req_map = {k: [] for k in gate.domains}
        for rid, req in state.requirements.items():
            dk = getattr(req, "domain_key", None)
            if dk and dk in gate.domains:
                req_map[dk].append(rid)
        for key, domain in gate.domains.items():
            if domain.status == "excluded":
                continue
            domain.req_ids = req_map.get(key, [])
            req_count = len(domain.req_ids)
            if req_count >= 3 and domain.probe_count >= 1:
                # Actively elicited AND has sufficient requirements
                domain.status = "confirmed"
            elif req_count >= 1:
                # Has some requirements but not yet fully elicited
                domain.status = "partial"
            else:
                # No requirements yet — keep as unprobed
                if domain.status not in ("confirmed",):
                    domain.status = "unprobed"

    def classify_subdimension(self, req_text):
        return self._call_classify_subdim(req_text)

    def tag_subdimension(self, req_id, subdim, domain_key, gate):
        if domain_key not in gate.domains: return
        d = gate.domains[domain_key]
        if subdim not in d.sub_dimensions: d.sub_dimensions[subdim] = []
        if req_id not in d.sub_dimensions[subdim]:
            d.sub_dimensions[subdim].append(req_id)

    def classify_nfr(self, req):
        # check if req.category is already a valid NFR category key, else call LLM
        cat_lower = req.category.lower().replace(" ","_").replace("-","_") if req.category else None
        if cat_lower is not None and cat_lower in NFR_CATEGORIES:
            return cat_lower
        return self._call_classify_nfr(req.text)

    def get_probe_question(self, domain, state):
        if domain.probe_question and domain.probe_count == 0:
            return domain.probe_question
        q = self._generate_probe(domain, state)
        domain.probe_question = q
        return q

    # IT10b: template-aware decomposition with re-run support
    def decompose_requirements(self, domain_key, gate, state):
        """Generate missing requirements for a domain using the coverage template as guide.

        IT10b changes vs previous:
        - decompose_count (int) replaces decomposed (bool): allows re-decomposition when
          the domain has grown since the last pass and new template dimensions are uncovered.
        - Guards: only re-decompose if req_ids has grown by >=3 since last run.
        - Passes domain_req_template to DECOMPOSE_PROMPT so generation targets the specific
          RE dimensions still missing, not a generic IoT-centric focus list.
        - Returns typed results: tuples of (text, is_nfr) so caller can store correctly.
        - Anti-duplication context increased from 20 to 40 requirements.
        """
        if domain_key not in gate.domains:
            return []
        domain = gate.domains[domain_key]

        own = [state.requirements[rid].text for rid in domain.req_ids
               if rid in state.requirements]
        if not own:
            domain.decompose_count += 1
            return []

        # Re-decompose guard: allow re-run if domain has grown by >=3 reqs since last pass.
        # This ensures that as elicitation deepens a domain, decomposition can fill new gaps
        # revealed by the coverage template, without firing on every single turn.
        last_size = getattr(domain, '_last_decompose_size', 0)
        if domain.decompose_count > 0 and len(own) - last_size < 3:
            return []

        # Build anti-duplication context from ALL other requirements (up to 40)
        other_texts = [r.text[:120] for rid, r in state.requirements.items()
                       if rid not in domain.req_ids]
        # Sample evenly by category for breadth
        from collections import defaultdict
        by_cat: dict = defaultdict(list)
        for rid, r in state.requirements.items():
            if rid not in domain.req_ids:
                by_cat[r.category or "general"].append(r.text[:120])
        per_cat = max(1, 40 // max(len(by_cat), 1))
        other_sample: list = []
        for cat_reqs in by_cat.values():
            other_sample.extend(cat_reqs[:per_cat])
        other_sample = other_sample[:40]

        # Coverage guidance: use domain template if available, else standard RE dimensions
        domain_templates = getattr(state, "domain_req_templates", {})
        template = domain_templates.get(domain_key, "")
        if template:
            coverage_guidance = (
                "COVERAGE TEMPLATE — generate requirements for any dimensions below "
                "not already addressed by the EXISTING REQUIREMENTS list above:\n"
                + "\n".join(f"  {line}" for line in template.splitlines())
            )
        else:
            coverage_guidance = (
                "STANDARD RE COVERAGE DIMENSIONS — generate requirements for any "
                "of these not yet addressed:\n"
                "  1. DATA: what information is stored, validated, and its retention rules\n"
                "  2. ACTOR ACTIONS: what each user role can do, with preconditions\n"
                "  3. SYSTEM AUTOMATION: what happens automatically without user input\n"
                "  4. BUSINESS RULES: validation logic, constraints, calculation policies\n"
                "  5. ERROR & EDGE CASES: missing inputs, invalid data, boundary conditions\n"
                "  6. INTEGRATION POINTS: external systems, APIs, or devices this domain touches\n"
                "  7. DOMAIN-SPECIFIC NFRs: performance, security, or compliance rules"
            )

        results = self._call_decompose(
            domain.label, state.project_name,
            "\n".join(f"- {t}" for t in own),
            "\n".join(f"- {t}" for t in other_sample) or "(none)",
            coverage_guidance=coverage_guidance,
        )
        domain.decompose_count += 1
        domain._last_decompose_size = len(own)
        return results

    # FIX-4: LLM domain matching
    def match_requirement_to_domain(self, req_text, gate):
        if not gate.seeded or not gate.domains: return None
        dlist = "\n".join(f"  {k}: {d.label}" for k,d in gate.domains.items())
        prompt = DOMAIN_MATCH_PROMPT.format(
            req_text=req_text[:200],
            domain_list=dlist
        )
        try:
            raw = self._provider.chat(
                system_message="Match requirements to domains. Reply with only the domain key.",
                messages=[
                    {
                        "role":"user",
                        "content":prompt
                    }
                ], temperature=0.0
            )
            key = raw.strip().lower().split()[0].rstrip(".,;:")
            if key in gate.domains: return key
            for dk in gate.domains:
                if dk.startswith(key) or key.startswith(dk[:6]): return dk
        except Exception: pass
        return None

    def extract_project_name(self, project_brief):
        brief = project_brief or {}
        brief_block = self._format_brief_block(brief)
        try:
            raw = self._provider.chat(
                system_message="Extract system names. Reply with only the name.",
                messages=[
                    {
                        "role":"user",
                        "content":PROJECT_NAME_PROMPT.format(
                            project_brief=brief_block
                        )
                    }
                ],
                temperature=0.0)
            name = raw.strip().strip('"\'').strip()
            return name if 2 <= len(name) <= 80 else None
        except Exception: return None

    def classify_system_complexity(
            self,
            project_name: str,
            project_brief: str,
            gate,
            state
        ) -> str:
        """IT10: Classify system complexity as 'simple', 'medium', or 'complex'.

        Uses RE-grounded heuristics (domain count, stakeholder diversity, integration
        depth) to guide elicitation depth. No arbitrary numeric thresholds are used in
        the user-facing system prompt — classification is based on structural properties
        of the described system, as recognised in IEEE 830 and standard RE practice.
        """
        domain_count = gate.total if gate and gate.seeded else 0

        req_text = " ".join(r.text.lower() for r in state.requirements.values())
        description_lower = (project_brief or "").lower()
        combined = req_text + " " + description_lower
        brief = project_brief or {}
        # Build the brief block for prompt injection
        if brief:
            brief_block = self._format_brief_block(brief)
        else:
            brief_block = ""
        stakeholder_indicators = [
            kw for kw in [
                "admin", "manager", "employer", "employee", "recruiter", "technician",
                "operator", "tenant", "guest", "moderator", "analyst", "supplier",
                "partner", "regulator", "auditor",
            ] if kw in combined
        ]
        integration_indicators = [
            kw for kw in [
                "api", "payment", "stripe", "paypal", "oauth", "google", "linkedin",
                "sensor", "iot", "device", "mqtt", "webhook", "gdpr", "hipaa",
                "pci", "government", "database", "third-party", "ai", "ml",
                "machine learning", "recommendation", "matching algorithm",
                "real-time", "streaming", "microservice",
            ] if kw in combined
        ]

        stakeholder_hints = ", ".join(stakeholder_indicators) or "none detected"
        integration_hints  = ", ".join(integration_indicators)  or "none detected"

        try:
            raw = self._provider.chat(
                system_message=(
                    "You are an expert Requirements Engineer. "
                    "Reply with ONLY one word: simple, medium, or complex."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": COMPLEXITY_PROMPT.format(
                            project_name=project_name,
                            project_brief=brief_block,
                            domain_count=domain_count,
                            stakeholder_hints=stakeholder_hints,
                            integration_hints=integration_hints,
                        )
                    }
                ],
                temperature=0.0,
            )
            level = raw.strip().lower().split()[0].rstrip(".,;:")
            if level in ("simple", "medium", "complex"):
                return level
        except Exception:
            pass
        # Fallback: infer from domain count and integration breadth
        if domain_count >= 10 or len(integration_indicators) >= 4:
            return "complex"
        if domain_count >= 6 or len(stakeholder_indicators) >= 2:
            return "medium"
        return "simple"

    def generate_domain_req_template(
            self,
            domain_label: str,
            project_name: str,
            project_brief: str,
            existing_reqs: list,
            complexity: str
        ) -> str:
        """IT10: Generate a requirement coverage checklist for a specific domain.

        Called once per domain, after the first user response about that domain.
        The checklist is stored in ConversationState.domain_req_templates and
        injected into the FR system prompt so the RE assistant knows every
        dimension it must cover — without relying on arbitrary numeric targets.
        """
        existing_text = "\n".join(f"- {r.text[:120]}" for r in existing_reqs) or "(none yet)"
        brief = project_brief or {}
        # Build the brief block for prompt injection
        if brief:
            brief_block = self._format_brief_block(brief)
        else:
            brief_block = "(Not available)"
        try:
            raw = self._provider.chat(
                system_message=(
                    "You are an expert Requirements Engineer. "
                    "Return only a plain numbered checklist, no preamble."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": DOMAIN_TEMPLATE_PROMPT.format(
                            project_brief=brief_block,
                            domain_label=domain_label,
                            project_name=project_name,
                            complexity=complexity,
                            existing_reqs=existing_text,
                        )
                    }
                ],
                temperature=0.1,
            )
            template = raw.strip()
            if template:
                return template
        except Exception:
            pass
        return ""


    # ── Internal LLM calls ──

    def _call_seed(
            self,
            desc,
            project_name="the system",
            project_brief=None
        ):
        """Call the LLM to produce a list of functional domain labels.

        If project_brief is provided (Phase 0 complete), the structured brief is
        injected into the prompt as the primary signal. The raw description is
        appended as supplementary context only.
        If no brief is available (srs_only / upload fallback), the raw description
        is used directly as before.
        """
        brief = project_brief or {}
        # Build the brief block for prompt injection
        if brief:
            brief_block = self._format_brief_block(brief)
            # supplementary raw description (customer's literal first message)
            extra = f"\nCUSTOMER'S OPENING MESSAGE (supplementary context):\n{desc[:800]}" if desc else ""
        else:
            brief_block = "(not available — using raw description below)"
            extra = ""

        try:
            raw = self._provider.chat(
                system_message="You are an expert Requirements Engineer. Return only valid JSON arrays.",
                messages=[
                    {
                        "role": "user",
                        "content": SEED_PROMPT.format(
                            project_name=project_name,
                            project_brief=brief_block,
                            extra_context=extra
                        )
                    }
                ],
                temperature=0.0
            )
            return _parse_json_list(raw)
        except Exception:
            return []

    def _call_reseed(
            self,
            desc,
            req_count,
            req_sample,
            current,
            project_name="the system",
            complexity="not yet assessed",
            project_brief=None
        ):
        """IT10: Added complexity param so reseed prompt can reference system type context."""
        brief = project_brief or {}
        # Build the brief block for prompt injection
        if brief:
            brief_block = self._format_brief_block(brief)
            extra = f"\nCUSTOMER'S OPENING MESSAGE (supplementary context):\n{desc[:800]}" if desc else ""
        else:
            brief_block = "(not available — using raw description below)"
            extra = f"\nCUSTOMER'S OPENING MESSAGE (supplementary context):\n{desc[:800]}" if desc else ""
        try:
            raw = self._provider.chat(
                system_message="You are an expert Requirements Engineer. Return only valid JSON arrays.",
                messages=[
                    {
                        "role":"user",
                        "content":RESEED_PROMPT.format(
                            description=extra,
                            req_count=req_count,
                            req_sample=req_sample,
                            current_domains=json.dumps(current),
                            project_name=project_name,
                            project_brief=brief_block,
                            complexity=complexity
                        )
                    }
                ],
                temperature=0.0
            )
            return _parse_json_list(raw)
        except Exception: return []

    def _call_classify_nfr(self, text):
        try:
            raw = self._provider.chat(
                system_message="Classify requirements. One category key only.",
                messages=[
                    {
                        "role":"user",
                        "content":NFR_CLASSIFY_PROMPT.format(text=text)
                    }
                ],
                temperature=0.0
            )
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
                messages=[
                    {
                        "role":"user",
                        "content":SUBDIM_CLASSIFY_PROMPT.format(text=text)
                    }
                ],
                temperature=0.0)
            k = raw.strip().lower().split()[0].rstrip(".,;:")
            valid = {"data","actions","constraints","automation","edge_cases"}
            if k in valid: return k
            for v in valid:
                if v in k or k in v: return v
            return "actions"
        except Exception: return "actions"

    def _call_decompose(
            self,
            domain_label,
            project_name,
            existing,
            all_other,
            coverage_guidance: str = ""
        ) -> list:
        """IT10b: Returns list of (text, is_nfr) tuples.
        The [NFR] prefix in generated text signals quality-attribute requirements
        so the caller can store them with the correct type and update NFR coverage.
        coverage_guidance is injected from the domain template when available.
        """
        try:
            raw = self._provider.chat(
                system_message=(
                    "You are a requirements engineering expert. "
                    "Return only valid JSON arrays of strings."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": DECOMPOSE_PROMPT.format(
                            domain_label=domain_label,
                            project_name=project_name,
                            existing_reqs=existing,
                            all_other_reqs=all_other,
                            coverage_guidance=coverage_guidance,
                        )
                    }
                ],
                temperature=0.2,
            )
            raw_list = _parse_json_list(raw)
            results = []
            for item in raw_list:
                text = item.strip()
                if len(text) < 20:
                    continue
                is_nfr = text.upper().startswith("[NFR]")
                if is_nfr:
                    text = text[5:].strip()  # strip the [NFR] prefix
                results.append((text, is_nfr))
            return results  # no hard cap — caller decides how many to use
        except Exception:
            return []

    def _generate_probe(self, domain, state):
        return (
            f"I'd like to understand more about how you'd use the "
            f"{domain.label.lower()} features — for example, "
            f"how often would you use them and what's most important to you?"
        )
        # history = "\n".join(
        #     f"User: {t.user_message[:150]} \n Assistant: {t.assistant_message[:150]}"
        #     for t in state.turns[-3:]
        # ) or "(no turns yet)"
        # covered = [d for d,ids in domain.sub_dimensions.items() if ids]
        # missing = [d for d in DOMAIN_SUB_DIMENSIONS if d not in covered]
        # focus = ""
        # if domain.probe_count > 0 and missing:
        #     hints = {
        #         "constraints":"specific numbers — how many, what range, min/max",
        #         "automation":"things that happen automatically — schedules, timers",
        #         "edge_cases":"what happens when something goes wrong or the user overrides a setting",
        #         "data":"what information gets stored, for how long, and any reports needed",
        #         "actions":"what specific things the user can do"
        #     }
        #     focus = f"\nFocus on: {hints.get(missing[0],'')}"

        # prompt = (
        #     f"You are interviewing a NON-TECHNICAL person about their system.\n\n"
        #     f"System: {state.project_name}\n"
        #     f"Recent conversation:\n{history}\n\n"
        #     f"Topic to ask about: {domain.label}\n"
        #     f"Requirements captured so far: {len(domain.req_ids)}{focus}\n\n"
        #     f"RULES:\n"
        #     f"1. Use PLAIN EVERYDAY LANGUAGE — no technical terms.\n"
        #     f"2. NEVER put the domain label in your question.\n"
        #     f"   BAD: 'Tell me about Error Detection & Recovery'\n"
        #     f"   GOOD: 'What should happen if something breaks — like if a sensor stops working or the internet goes out?'\n"
        #     f"3. ALWAYS include a concrete example from their system.\n"
        #     f"4. Ask for specific numbers where relevant.\n"
        #     f"5. ONE sentence ending in '?'\n\n"
        #     f"Question:")
        # try:
        #     raw = self._provider.chat(
        #         system_message="You are a friendly interviewer using simple everyday language.",
        #         messages=[
        #             {
        #                 "role":"user",
        #                 "content":prompt
        #             }
        #         ],
        #         temperature=0.3
        #     )
        #     q = raw.strip().strip('"\'')
        #     return q if q.endswith("?") else q.rstrip(".")+  "?"
        # except Exception:
        #     return (f"I'd like to understand more about how you'd use the "
        #             f"{domain.label.lower()} features — for example, "
        #             f"how often would you use them and what's most important to you?")

    def _format_brief_block(self, brief: str):
        brief_lines = [
                f"  System Purpose    : {brief.get('system_purpose', '(not specified)')}",
                f"  User classes      : {brief.get('user_classes', '(not specified)')}",
                f"  Core features     : {brief.get('core_features', '(not specified)')}",
                f"  Scale / context   : {brief.get('scale_and_context', '(not specified)')}",
                f"  Known constraints : {brief.get('key_constraints', '(not specified)')}",
                f"  Integration points: {brief.get('integration_points', '(not specified)')}",
                f"  Out of scope      : {brief.get('out_of_scope', '(not specified)')}",
            ]
        brief_block = "\n".join(brief_lines)
        return brief_block

# ── Structural coverage ──
_MIN_REQS_FOR_CONSTRAINT_COVERAGE = 3

def compute_structural_coverage(state) -> set[str]:
    covered = set()
    from src.components.conversation_state import RequirementType
    if state.domain_gate.is_satisfied:
        covered.add("functional")
    if sum(1 for r in state.requirements.values()
           if r.req_type==RequirementType.CONSTRAINT) >= _MIN_REQS_FOR_CONSTRAINT_COVERAGE: covered.add("constraints")
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

def _build_req_sample(state, max_reqs: int = 40):
    """IT10: Increased from 15 to 40 so reseed sees enough signal in complex systems.
    Requirements are sampled evenly across domain categories to give signal breadth,
    not just the first requirements written (which skew toward early-mentioned domains).
    """
    all_reqs = list(state.requirements.values())
    if not all_reqs:
        return "(none yet)"
    if len(all_reqs) <= max_reqs:
        sample = all_reqs
    else:
        # Sample evenly by domain category to maximise signal breadth
        from collections import defaultdict
        by_cat: dict = defaultdict(list)
        for r in all_reqs:
            by_cat[r.category or "general"].append(r)
        per_cat = max(1, max_reqs // max(len(by_cat), 1))
        sample = []
        for cat_reqs in by_cat.values():
            sample.extend(cat_reqs[:per_cat])
        sample = sample[:max_reqs]
    return "\n".join(f"- {r.text[:120]}" for r in sample)

def create_domain_discovery(llm_provider):
    return DomainDiscovery(llm_provider=llm_provider)