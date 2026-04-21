from __future__ import annotations
import json, sys, uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from src.components.conversation_state import ConversationState, RequirementType, create_session
from src.components.system_prompt.prompt_architect import PromptArchitect, TaskType
from src.components.system_prompt.utils import PHASE4_SECTIONS
from src.components.srs_template import SRSTemplate, create_template
from src.components.srs_formatter import generate_srs_document
from src.components.requirement_extractor import RequirementExtractor, create_extractor, parse_scope_tags
from src.components.gap_detector import GapDetector, create_gap_detector
from src.components.domain_discovery.domain_discovery import DomainDiscovery, create_domain_discovery
from src.components.domain_discovery.domain_gate import DomainGate
from src.components.conversation_manager.llm_provider import LLMProvider
from src.components.conversation_manager.session_logger import SessionLogger
from src.components.conversation_manager.utils import _message_similarity, SMART_CHECK_PROMPT

# ── Conversation Manager ──

MAX_HISTORY_TURNS = 10   # IT9: reduced from 20 to keep context tight

@dataclass
class ConversationManager:
    provider: LLMProvider
    log_dir: Path = field(default_factory=lambda: Path(__file__).parent / "logs")
    output_dir: Path = field(default_factory=lambda: Path(__file__).parent / "output")
    task_type: TaskType = "elicitation"

    temperature: float = 0.0
    gap_enabled: bool = True

    _architect: PromptArchitect = field(init=False)
    _srs_template: Optional[SRSTemplate] = field(default=None, init=False, repr=False)
    _extractor: RequirementExtractor = field(default_factory=create_extractor, init=False)
    _gap_detector: Optional[GapDetector] = field(default=None, init=False, repr=False)
    _domain_discovery: Optional[DomainDiscovery] = field(default=None, init=False, repr=False)
    _last_probed_domain: Optional[str] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self._architect = PromptArchitect(task_type=self.task_type)
        self._gap_detector = create_gap_detector(enabled=self.gap_enabled)
        self._domain_discovery = create_domain_discovery(self.provider)

    def start_session(self) -> tuple:
        session_id = str(uuid.uuid4())[:8]
        state = create_session(session_id)
        state.domain_gate = DomainGate()
        state.task_type = self.task_type
        self._srs_template = create_template(session_id)
        logger = SessionLogger(log_dir=self.log_dir, session_id=session_id)
        logger.log_event("session_start", {
            "session_id": session_id, "model": self.provider.model_name,
            "temperature": self.temperature, "gap_detection_enabled": self.gap_enabled,
            "task_type": self.task_type,
        })
        return session_id, state, logger, self._srs_template

    def inject_requirements(
        self,
        preprocessed_reqs: list,  # list of ProcessedRequirement
        state: ConversationState,
        logger: SessionLogger,
    ) -> int:
        """
        Load preprocessed requirements into state before conversation starts.
        Used for srs_only task type and when user uploads a requirements file.
        Returns count of requirements injected.
        """
        from src.components.domain_discovery.domain_discovery import NFR_CATEGORIES
        injected = 0
        existing_texts = {r.text.lower().strip() for r in state.requirements.values()}

        for pr in preprocessed_reqs:
            text_lower = pr.final_text.lower().strip()
            # Deduplicate
            if any(_message_similarity(text_lower, et) > 0.7 for et in existing_texts):
                continue

            # Map req_type
            if pr.req_type == "functional":
                rtype = RequirementType.FUNCTIONAL
            elif pr.req_type == "non_functional":
                rtype = RequirementType.NON_FUNCTIONAL
            else:
                rtype = RequirementType.CONSTRAINT

            req = state.add_requirement(
                req_type=rtype,
                text=pr.final_text,
                category=pr.category,
                raw_excerpt="[Uploaded by user]",
                source="uploaded",
            )

            # Track NFR coverage
            if rtype == RequirementType.NON_FUNCTIONAL and pr.category in NFR_CATEGORIES:
                state.increment_nfr_coverage(pr.category)

            existing_texts.add(text_lower)
            injected += 1

        logger.log_event("requirements_injected", {
            "count": injected,
            "functional": state.functional_count,
            "non_functional": state.nonfunctional_count,
        })
        return injected

    def seed_domains_from_preprocessed(
        self,
        preprocessed_reqs: list,
        state: ConversationState,
    ):
        """
        IT9: Seed domain gate from preprocessed requirement categories.
        Uses reseed if domains already exist, seed otherwise.
        """
        if not self._domain_discovery or not state.domain_gate:
            return

        # Collect unique functional domain labels
        nfr_keys = {"performance", "usability", "security_privacy",
                    "reliability", "compatibility", "maintainability", "constraint"}
        domain_labels = list({
            pr.category_label
            for pr in preprocessed_reqs
            if pr.req_type == "functional" and pr.category not in nfr_keys
        })

        if not domain_labels:
            return

        gate = state.domain_gate
        if gate.seeded and gate.total > 0:
            # Use reseed — domains already partially known
            self._domain_discovery.reseed(
                domain_labels, gate, state, turn_id=0)
        else:
            # Fresh seed from known domain list
            self._domain_discovery.seed_from_labels(
                domain_labels, gate, turn_id=0,
                project_name=state.project_name)

    def _run_smart_check(self, extracted: list, user_message: str) -> list:
        if not extracted:
            return extracted
        req_lines = "\n".join(f"{i+1}. [{e.req_type}] {e.text}"
                               for i, e in enumerate(extracted))
        prompt = SMART_CHECK_PROMPT.format(
            user_message=user_message[:800],
            requirements_list=req_lines)
        try:
            import re as _re
            raw = self.provider.chat(
                system_message="You are a Requirements Engineering QA expert. Return only valid JSON arrays.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0)
            text = _re.sub(r"```(?:json)?\s*", "", raw.strip()).strip().strip("`")
            m = _re.search(r"\[.*?\]", text, _re.DOTALL)
            if not m:
                return extracted
            results = json.loads(m.group(0))
            if not isinstance(results, list) or len(results) != len(extracted):
                return extracted
            for ext, res in zip(extracted, results):
                if res.get("rewritten") and res.get("final"):
                    ext.text = res["final"].strip()
                ext.smart_score = res.get("smart_score", 3)
            rewritten_count = sum(1 for r in results if r.get("rewritten"))
            avg_score = sum(r.get("smart_score", 3) for r in results) / len(results)
            print(f"[SMART Check] {len(extracted)} reqs | avg: {avg_score:.1f}/5 | rewritten: {rewritten_count}")
            return extracted
        except Exception as e:
            print(f"[SMART Check] Failed: {e}")
            return extracted

    def send_turn(
            self,
            user_message: str,
            state: ConversationState,
            logger: SessionLogger
        ) -> str:
        """Process one conversation turn.

        PRE-CALL block (steps 1-3): everything the system prompt depends on must be
        resolved BEFORE building it. This includes domain seeding, project name,
        system complexity, domain templates, and probe questions. Any of these that
        run post-call will be invisible to the current turn's system prompt and only
        benefit the NEXT turn — a one-turn lag on every context signal.

        POST-CALL block (steps 4-6): process what the LLM produced — extract and
        commit requirements, update domain statuses, run decomposition, sync
        templates, detect gaps, log.
        """

        # ── PRE-CALL: resolve all context the system prompt depends on ────────
        next_turn_id = state.turn_count + 1  # what turn_count will be after add_turn()
        if self._domain_discovery and state.domain_gate:

            # Only run domain operations after scope phase is complete
            scope_done = getattr(state, "scope_complete", False)
            task_type  = getattr(state, "task_type", "elicitation")
            # srs_only bypasses scope phase entirely
            if task_type == "srs_only":
                scope_done = True

            # Must run before system-prompt build so domain context is available.
            # turn_count is still the PREVIOUS count here (add_turn not called yet),
            # so "turn 1" == next_turn_id == 1, i.e. turn_count == 0.
            has_existing_domains = state.domain_gate.seeded and state.domain_gate.total > 0
            project_brief = getattr(state, "project_brief", {})

            # P1. Project name resolution
            if state.project_name_needs_llm and project_brief:
                name = self._domain_discovery.extract_project_name(project_brief)
                if name:
                    state.project_name = name
                    state.project_name_needs_llm = False

            # P2. Domain seeding / re-seeding.
            if scope_done:
                if not has_existing_domains and not state.domain_gate.seeded:
                    # Fresh seed on first FR turn: use project brief + message for richer context
                    seed_description = (user_message).strip()
                    self._domain_discovery.seed(
                        seed_description,
                        state.domain_gate,
                        next_turn_id,
                        project_name=state.project_name,
                        project_brief=project_brief
                    )
                elif has_existing_domains and not state.domain_gate.seeded:
                    # Pre-loaded domains (uploaded reqs): reseed with first message
                    self._domain_discovery.reseed(
                        description="",
                        gate=state.domain_gate,
                        state=state,
                        turn_id=next_turn_id,
                        project_brief=project_brief
                    )
                elif next_turn_id == DomainDiscovery.RESEED_TURN:
                    all_user_msgs = " ".join(t.user_message for t in state.turns) + "\n" + user_message
                    self._domain_discovery.reseed(
                        description=all_user_msgs,
                        gate=state.domain_gate,
                        state=state,
                        turn_id=next_turn_id,
                        project_brief=project_brief
                    )
                elif next_turn_id == DomainDiscovery.SECOND_RESEED_TURN:
                    all_user_msgs = " ".join(t.user_message for t in state.turns[-15:]) + "\n" + user_message
                    self._domain_discovery.reseed(
                        description=all_user_msgs,
                        gate=state.domain_gate,
                        state=state,
                        turn_id=next_turn_id,
                        project_brief=project_brief
                    )
                elif next_turn_id == DomainDiscovery.THIRD_RESEED_TURN:
                    _cx = getattr(state, "system_complexity", "")
                    if _cx in ("medium", "complex"):
                        all_user_msgs = " ".join(t.user_message for t in state.turns[-20:]) + "\n" + user_message
                        self._domain_discovery.reseed(
                            description=all_user_msgs,
                            gate=state.domain_gate,
                            state=state,
                            turn_id=next_turn_id,
                            project_brief=project_brief
                        )

            # P3–P6 only relevant once domain seeding is active (scope complete)
            if scope_done:
                # P3. System complexity classification (once, after seeding complete).
                if (not getattr(state, "system_complexity", "")
                        and state.domain_gate.seeded
                        and state.domain_gate.total >= 3
                        and project_brief):
                    _complexity = self._domain_discovery.classify_system_complexity(
                        project_name=state.project_name,
                        description=project_brief,
                        gate=state.domain_gate,
                        state=state,
                    )
                    state.system_complexity = _complexity
                    logger.log_event("system_complexity_classified", {
                        "complexity": _complexity,
                        "domain_count": state.domain_gate.total,
                    })

                # P4. Domain requirement coverage template.
                if state.domain_gate.seeded:
                    _cur_dk, _cur_dv = None, None
                    for _dk, _dv in state.domain_gate.domains.items():
                        if _dv.status not in ("confirmed", "excluded"):
                            _cur_dk, _cur_dv = _dk, _dv
                            break
                    _templates = getattr(state, "domain_req_templates", {})
                    if (_cur_dk and _cur_dk not in _templates and _cur_dv is not None
                            and _cur_dv.probe_count >= 0):
                        _existing_reqs = [
                            state.requirements[rid]
                            for rid in _cur_dv.req_ids
                            if rid in state.requirements
                        ]
                        _template = self._domain_discovery.generate_domain_req_template(
                            domain_label=_cur_dv.label,
                            project_name=state.project_name,
                            project_brief=project_brief,
                            existing_reqs=_existing_reqs,
                            complexity=getattr(state, "system_complexity", "") or "medium",
                        )
                        if _template:
                            state.domain_req_templates[_cur_dk] = _template
                            logger.log_event("domain_template_generated", {
                                "domain_key": _cur_dk,
                                "domain_label": _cur_dv.label,
                                "template_lines": len(_template.splitlines()),
                            })

                # P5. Probe question: ensure current domain has one before system-prompt build
                _nd = state.domain_gate.next_unprobed()
                if _nd and not _nd.probe_question:
                    self._domain_discovery.get_probe_question(_nd, state)

                # P6. Carry forward probe increment from last turn
                if self._domain_discovery and state.domain_gate and self._last_probed_domain:
                    dv = state.domain_gate.domains.get(self._last_probed_domain)
                    if dv and dv.status not in ("confirmed", "excluded"):
                        dv.probe_count += 1
                    self._last_probed_domain = None   # reset so it only fires once

        # ── CALL: build system prompt and invoke LLM ──────────────────────────

        # 1. Build system message (phase-aware, now has full pre-call context)
        system_msg = self._architect.build_system_message(state)
        print(f"System message: \n{system_msg}\n")
        current_phase = self._architect.get_current_phase(state)
        print(f"\n[Phase: {current_phase}] Turn {next_turn_id}\n[System prompt length: {len(system_msg)} chars]")

        # 2. Assemble message history — use only last MAX_HISTORY_TURNS turns
        history = state.get_message_history()[-(MAX_HISTORY_TURNS * 2):]
        messages_to_send = history + [{"role": "user", "content": user_message}]

        # 3. LLM call
        try:
            assistant_response = self.provider.chat(
                system_message=system_msg,
                messages=messages_to_send,
                temperature=self.temperature)
        except Exception as exc:
            raise RuntimeError(f"LLM API error: {exc}") from exc

        # ── POST-CALL: process LLM output and update state ────────────────────
        print(f"User message:\n{user_message}\n")
        print(f"Assistant response:\n{assistant_response}\n")
        # 4. Record turn (turn_count increments here)
        turn = state.add_turn(user_message, assistant_response)

        # 4-scope. Parse <SCOPE> tags (Phase 0 only)
        # Must run before anything else so scope_complete is set before
        # domain seeding on the NEXT turn's pre-call block.
        scope_tags = parse_scope_tags(assistant_response)
        if scope_tags:
            VALID_BRIEF_FIELDS = {
                "system_purpose", "user_classes", "core_features", "scale_and_context",
                "key_constraints", "integration_points", "out_of_scope",
            }
            for field, value in scope_tags.items():
                if field == "status" and value.lower() == "complete":
                    state.scope_complete = True
                    logger.log_event("scope_phase_complete", {
                        "turn_id": turn.turn_id,
                        "brief": dict(state.project_brief),
                    })
                elif field in VALID_BRIEF_FIELDS and value:
                    state.project_brief[field] = value
            state.scope_turn_count = getattr(state, "scope_turn_count", 0) + 1
            # Force completion after 6 scope turns regardless
            if state.scope_turn_count >= 6 and not state.scope_complete:
                state.scope_complete = True
                logger.log_event("scope_phase_forced_complete", {
                    "turn_id": turn.turn_id,
                    "reason": "max_scope_turns_reached",
                    "brief": dict(state.project_brief),
                })

        # 4a. Extract <REQ> tags from assistant response
        extracted = self._extractor.extract(assistant_response)

        # 4b. Extract <SECTION> tags (IEEE phase)
        sections_found = self._extractor.extract_sections(assistant_response)
        if sections_found:
            stored_ids = self._extractor.commit_sections(sections_found, state)
            if stored_ids:
                logger.log_event("phase4_sections_stored", {
                    "sections": stored_ids,
                    "phase4_progress": f"{len(state.phase4_sections_covered)}/{len(PHASE4_SECTIONS)}"
                })

        # 4c. SMART quality check — rewrite vague requirements before committing
        if extracted:
            extracted = self._run_smart_check(extracted, user_message)

        if extracted and self._domain_discovery and state.domain_gate:
            # 4d. Domain matching — map each requirement to its domain key
            for ext in extracted:
                cat_lower = ext.category.lower().replace(" ", "_").replace("-", "_")
                if cat_lower in state.domain_gate.domains:
                    ext.domain_label = cat_lower
                else:
                    matched_key = self._domain_discovery.match_requirement_to_domain(
                        ext.text, state.domain_gate)
                    if matched_key:
                        ext.domain_label = matched_key

            # 4e. NFR classification — classify and count each non-functional requirement
            for ext in extracted:
                if ext.req_type == "non_functional":
                    cat_key = self._domain_discovery.classify_nfr(ext)
                    if cat_key:
                        ext.category = cat_key
                        state.increment_nfr_coverage(cat_key)

            # 4f. Sub-dimension classification
            for ext in extracted:
                if ext.domain_label and ext.domain_label in state.domain_gate.domains:
                    subdim = self._domain_discovery.classify_subdimension(ext.text)
                    if subdim:
                        ext._subdim = subdim

            # 4g. Commit requirements to state
            new_ids = self._extractor.commit(extracted, state)

            # Tag sub-dimensions on committed requirements
            if new_ids:
                for ext, req_id in zip(extracted, new_ids):
                    subdim = getattr(ext, "_subdim", None)
                    if subdim and ext.domain_label:
                        self._domain_discovery.tag_subdimension(
                            req_id, subdim, ext.domain_label, state.domain_gate)

        # 4h. Update domain statuses (req counts changed by 4g)
        if self._domain_discovery and state.domain_gate:
            self._domain_discovery.update_domain_statuses(state.domain_gate, state)

        # 4i. Record which domain was just probed (increment happens next turn's PRE-CALL)
        if self._domain_discovery and state.domain_gate:
            nd = state.domain_gate.next_unprobed()
            if nd:
                for dk, dv in state.domain_gate.domains.items():
                    if dv is nd:
                        self._last_probed_domain = dk
                        break

        # 4j. Decomposition — generate missing requirements from coverage template.
        # Runs post-call so it sees the requirements just committed in 4g.
        # decompose_requirements() is re-entrant: re-runs when domain grows by >=3 reqs.
        # if self._domain_discovery and state.domain_gate:
        #     _complexity = getattr(state, "system_complexity", "")
        #     decomp_cap = 5 if _complexity == "complex" else 3
        #     decomp_count = 0
        #     for dk, dv in state.domain_gate.domains.items():
        #         if decomp_count >= decomp_cap:
        #             break
        #         _last_size = getattr(dv, "_last_decompose_size", 0)
        #         _should_decompose = (
        #             len(dv.req_ids) >= 2
        #             and dv.status != "excluded"
        #             and (dv.decompose_count == 0 or len(dv.req_ids) - _last_size >= 3)
        #         )
        #         if not _should_decompose:
        #             continue
        #         new_items = self._domain_discovery.decompose_requirements(
        #             dk, state.domain_gate, state)
        #         existing_texts = {r.text.lower().strip() for r in state.requirements.values()}
        #         added = 0
        #         for text, is_nfr in new_items:
        #             text_lower = text.lower().strip()
        #             if any(_message_similarity(text_lower, et) > 0.75 for et in existing_texts):
        #                 continue
        #             if is_nfr:
        #                 nfr_cat = self._domain_discovery.classify_nfr(
        #                     type("_R", (), {"text": text, "category": ""})()
        #                 ) or "performance"
        #                 state.add_requirement(
        #                     req_type=RequirementType.NON_FUNCTIONAL,
        #                     text=text, category=nfr_cat,
        #                     raw_excerpt=f"[Decomposed NFR from {dv.label}]",
        #                     domain_key=dk, source="decomposed")
        #                 state.increment_nfr_coverage(nfr_cat)
        #             else:
        #                 req = state.add_requirement(
        #                     req_type=RequirementType.FUNCTIONAL,
        #                     text=text, category=dk,
        #                     raw_excerpt=f"[Decomposed from {dv.label}]",
        #                     domain_key=dk, source="decomposed")
        #                 subdim = self._domain_discovery.classify_subdimension(text)
        #                 if subdim:
        #                     self._domain_discovery.tag_subdimension(
        #                         req.req_id, subdim, dk, state.domain_gate)
        #             existing_texts.add(text_lower)
        #             added += 1
        #         decomp_count += 1
        #         if added > 0:
        #             self._domain_discovery.update_domain_statuses(state.domain_gate, state)

            # 4k. Regenerate probe question for next turn
            nd = state.domain_gate.next_unprobed()
            if nd and (nd.probe_count > 0 or not nd.probe_question):
                self._domain_discovery.get_probe_question(nd, state)

        # 5. Sync SRS template
        if self._srs_template:
            self._srs_template.update_from_requirements(
                state.requirements, project_name=state.project_name)

        # 6. Gap detection
        gap_report = None
        if self._gap_detector:
            gap_report = self._gap_detector.analyse(state)

        # 7. Log turn
        logger.log_turn(
            turn_id=turn.turn_id,
            user_msg=user_message,
            assistant_msg=assistant_response,
            categories_updated=turn.categories_updated,
            gap_report_dict=gap_report.to_dict() if gap_report else None
        )

        return assistant_response

    def finalize_session(self, state, logger):
        if not self._srs_template:
            self._srs_template = create_template(state.session_id, state.project_name)

        self._srs_template.update_from_requirements(
            state.requirements, project_name=state.project_name)

        from srs_coverage import create_enricher
        enricher = create_enricher(provider=self.provider)
        filled_sections = enricher.enrich(self._srs_template, state)

        if filled_sections:
            phase4_count = sum(1 for s in filled_sections.values() if s == "phase4")
            llm_count = sum(1 for s in filled_sections.values() if s == "llm_synthesis")
            stub_count = sum(1 for s in filled_sections.values() if s == "stub")
            logger.log_event("srs_coverage_fill", {
                "sections_filled": list(filled_sections.keys()),
                "sources": filled_sections,
                "phase4_sections": phase4_count,
                "llm_synthesis_sections": llm_count,
                "stub_sections": stub_count,
            })
            print(f"[SRS Coverage] Filled {len(filled_sections)} sections: "
                  f"{phase4_count} Phase4, {llm_count} LLM, {stub_count} stubs.")

        srs_path = generate_srs_document(
            template=self._srs_template,
            state=state,
            output_dir=self.output_dir
        )
        logger.log_session_end(state)
        return srs_path