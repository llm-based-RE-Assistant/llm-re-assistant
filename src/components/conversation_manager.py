"""
src/components/conversation_manager.py — Iteration 4
University of Hildesheim

"""
from __future__ import annotations
import json,os,sys,time,uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import requests

sys.path.insert(0, str(Path(__file__).parent))

from conversation_state import ConversationState, RequirementType, create_session
from prompt_architect import PromptArchitect, PHASE4_SECTIONS
from srs_template import SRSTemplate, create_template
from srs_formatter import SRSFormatter, generate_srs_document
from requirement_extractor import RequirementExtractor, create_extractor
from gap_detector import GapDetector, create_gap_detector
from question_generator import ProactiveQuestionGenerator, create_question_generator
from domain_discovery import DomainDiscovery, DomainGate, create_domain_discovery


# ── LLM Providers (unchanged) ──

class LLMProvider(ABC):
    @abstractmethod
    def chat(self, system_message:str, messages:list[dict[str,str]],
             temperature:float=0.0) -> str: ...
    @property
    @abstractmethod
    def model_name(self) -> str: ...

class OpenAIProvider(LLMProvider):
    def __init__(self, model="gpt-4o", timeout=120):
        import openai
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key: raise EnvironmentError("OPENAI_API_KEY not set.")
        self._client = openai.OpenAI(api_key=api_key, timeout=timeout)
        self._model = model
    @property
    def model_name(self): return self._model
    def chat(self, system_message, messages, temperature=0.0):
        full = [{"role":"system","content":system_message}] + messages
        r = self._client.chat.completions.create(model=self._model,messages=full,temperature=temperature)
        return r.choices[0].message.content or ""

class OllamaProvider(LLMProvider):
    def __init__(self, model="llama3.1:8b", timeout=120):
        api_key = os.getenv("OLLAMA_API_KEY")
        if not api_key: raise EnvironmentError("OLLAMA_API_KEY not set.")
        base_url = os.getenv("OLLAMA_BASE_URL","https://genai-01.uni-hildesheim.de/ollama")
        self._model = model
        self.api_endpoint = f"{base_url}/api/chat"
        self.headers = {"Content-Type":"application/json","Authorization":f"Bearer {api_key}"}
        self.timeout = timeout
    @property
    def model_name(self): return self._model
    def chat(self, system_message, messages, temperature=0.0):
        full = [{"role":"system","content":system_message}] + messages
        r = requests.post(self.api_endpoint, headers=self.headers,
            json={"model":self._model,"messages":full,
                  "options":{"temperature":temperature},"stream":False},
            timeout=self.timeout)
        r.raise_for_status()
        return r.json()["message"]["content"] or ""

class StubProvider(LLMProvider):
    def __init__(self, responses=None):
        self._responses = responses or [
            "Thank you. Who are the primary users?",
            "What are the most important features?",
            "How quickly should it respond?",
            "How should users authenticate?",
            "What happens if the system goes offline?",
            "Is there anything else?",
        ]
        self._index = 0
    @property
    def model_name(self): return "stub-provider-v1"
    def chat(self, system_message, messages, temperature=0.0):
        r = self._responses[self._index % len(self._responses)]
        self._index += 1
        return r

def create_provider(name="ollama", **kwargs):
    if name == "openai": return OpenAIProvider(**kwargs)
    elif name == "ollama": return OllamaProvider(**kwargs)
    elif name == "stub": return StubProvider(**kwargs)
    raise ValueError(f"Unknown provider: {name!r}")


# ── Session Logger ──

class SessionLogger:
    def __init__(self, log_dir: Path, session_id: str):
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = log_dir / f"session_{session_id}.json"
        self._entries: list[dict] = []

    def log_event(self, event_type, data):
        self._entries.append({"timestamp":time.time(),"event_type":event_type,"data":data})
        self._flush()

    def log_turn(self, turn_id, user_msg, assistant_msg, categories_updated,
                 gap_report_dict=None):
        data = {"turn_id":turn_id,"user_message":user_msg,
                "assistant_message":assistant_msg,"categories_updated":categories_updated}
        if gap_report_dict: data["gap_report"] = gap_report_dict
        self._entries.append({"timestamp":time.time(),"event_type":"turn","data":data})
        self._flush()

    def log_session_end(self, state):
        self.log_event("session_end", state.get_coverage_report())

    def _flush(self):
        try:
            with open(self._log_path,"w",encoding="utf-8") as f:
                json.dump(self._entries,f,indent=2,ensure_ascii=False)
        except Exception: pass


# ── FIX-LOOP: Duplicate detection helper ──

def _message_similarity(a: str, b: str) -> float:
    """Quick Jaccard similarity on word sets."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb: return 0.0
    return len(wa & wb) / len(wa | wb)


# ── Conversation Manager ──

@dataclass
class ConversationManager:
    provider: LLMProvider
    log_dir: Path = field(default_factory=lambda: Path(__file__).parent / "logs")
    output_dir: Path = field(default_factory=lambda: Path(__file__).parent / "output")
    
    temperature: float = 0.0
    gap_enabled: bool = True

    _architect: PromptArchitect = field(default_factory=PromptArchitect, init=False)
    _srs_template: Optional[SRSTemplate] = field(default=None, init=False, repr=False)
    _extractor: RequirementExtractor = field(default_factory=create_extractor, init=False)
    _gap_detector: Optional[GapDetector] = field(default=None, init=False, repr=False)
    _question_generator: Optional[ProactiveQuestionGenerator] = field(default=None, init=False, repr=False)
    _domain_discovery: Optional[DomainDiscovery] = field(default=None, init=False, repr=False)
    _last_probed_domain: Optional[str] = field(default=None, init=False, repr=False)

    SECOND_RESEED_TURN = 8

    def __post_init__(self):
        self._gap_detector = create_gap_detector(enabled=self.gap_enabled)
        self._question_generator = create_question_generator(
            max_questions_per_turn=1, mode="llm", llm_provider=self.provider)
        self._domain_discovery = create_domain_discovery(self.provider)

    def start_session(self):
        session_id = str(uuid.uuid4())[:8]
        state = create_session(session_id)
        state.domain_gate = DomainGate()
        self._srs_template = create_template(session_id)
        logger = SessionLogger(log_dir=self.log_dir, session_id=session_id)
        logger.log_event("session_start", {
            "session_id":session_id,"model":self.provider.model_name,
            "temperature":self.temperature,"gap_detection_enabled":self.gap_enabled})
        return session_id, state, logger, self._srs_template

    def send_turn(self, user_message: str, state: ConversationState,
                  logger: SessionLogger) -> str:

        # FIX-LOOP: detect duplicate user messages
        for prev_turn in state.turns:
            if _message_similarity(user_message, prev_turn.user_message) > 0.8:
                # Skip this duplicate — force advance to next domain
                turn = state.add_turn(user_message, "(duplicate detected — advancing)")
                # Force-advance: mark current domain as confirmed if stuck
                if state.domain_gate and state.domain_gate.seeded:
                    nd = state.domain_gate.next_unprobed()
                    if nd and nd.probe_count >= 2:
                        nd.status = "confirmed"
                # Re-run the turn with the system generating a fresh question
                break
        else:
            pass  # not a duplicate — proceed normally

        # 1. Build system message
        system_msg = self._architect.build_system_message(state)

        # 2. Assemble messages — use only last 20 turns to avoid context overflow
        history = state.get_message_history()[-40:]  # 20 turns = 40 messages
        messages_to_send = history + [{"role":"user","content":user_message}]

        # 3. LLM call
        try:
            assistant_response = self.provider.chat(
                system_message=system_msg,messages=messages_to_send,
                temperature=self.temperature)
        except Exception as exc:
            raise RuntimeError(f"LLM API error: {exc}") from exc

        # 4. Update state
        turn = state.add_turn(user_message, assistant_response)

        # 4a. Extract requirements
        extracted = self._extractor.extract(assistant_response)

        # IT8-PHASE4: extract <SECTION> tags from Phase 4 responses
        sections_found = self._extractor.extract_sections(assistant_response)
        if sections_found:
            stored_ids = self._extractor.commit_sections(sections_found, state)
            if stored_ids:
                logger.log_event("phase4_sections_stored", {
                    "sections": stored_ids,
                    "phase4_progress": f"{len(state.phase4_sections_covered)}/{len(PHASE4_SECTIONS)}"
                })

        if extracted and self._domain_discovery and state.domain_gate:
            # 4b. FIX-MATCH: LLM-based domain matching
            for ext in extracted:
                matched_key = self._domain_discovery.match_requirement_to_domain(
                    ext.text, state.domain_gate)
                if matched_key:
                    ext.domain_label = matched_key

            # 4c. Classify NFRs
            for ext in extracted:
                if ext.req_type == "non_functional":
                    cat_key = self._domain_discovery.classify_nfr(ext.text)
                    if cat_key:
                        ext.category = cat_key
                        state.increment_nfr_coverage(cat_key)

            # 4d. Classify sub-dimensions
            for ext in extracted:
                if ext.domain_label and ext.domain_label in state.domain_gate.domains:
                    subdim = self._domain_discovery.classify_subdimension(ext.text)
                    if subdim:
                        ext._subdim = subdim

            # 4e. Commit
            new_ids = self._extractor.commit(extracted, state)

            # Tag sub-dimensions
            if new_ids:
                for ext, req_id in zip(extracted, new_ids):
                    subdim = getattr(ext, '_subdim', None)
                    if subdim and ext.domain_label:
                        self._domain_discovery.tag_subdimension(
                            req_id, subdim, ext.domain_label, state.domain_gate)

        # 4f. Domain seeding / re-seeding
        if self._domain_discovery and state.domain_gate:
            if state.turn_count == 1:
                self._domain_discovery.seed(user_message, state.domain_gate, state.turn_count)
            elif state.turn_count == DomainDiscovery.RESEED_TURN:
                first_msg = state.turns[0].user_message if state.turns else user_message
                self._domain_discovery.reseed(first_msg, state.domain_gate, state, state.turn_count)
            elif state.turn_count == self.SECOND_RESEED_TURN:
                if state.domain_gate.reseed_turn < self.SECOND_RESEED_TURN:
                    first_msg = state.turns[0].user_message if state.turns else user_message
                    state.domain_gate.reseed_turn = 0
                    self._domain_discovery.reseed(first_msg, state.domain_gate, state, state.turn_count)

            # 4g. Project name
            if state.project_name_needs_llm and state.turn_count == 1:
                name = self._domain_discovery.extract_project_name(user_message)
                if name:
                    state.project_name = name
                    state.project_name_needs_llm = False

            # 4h. Update domain statuses
            self._domain_discovery.update_domain_statuses(state.domain_gate, state)

            # 4i. Track probe count
            nd = state.domain_gate.next_unprobed()
            if nd:
                cdk = None
                for dk,dv in state.domain_gate.domains.items():
                    if dv is nd: cdk = dk; break
                if cdk and cdk == self._last_probed_domain:
                    nd.probe_count += 1
                elif cdk:
                    self._last_probed_domain = cdk

            # 4j. FIX-CAP: Decomposition — max 3 domains per turn
            decomp_count = 0
            for dk, dv in state.domain_gate.domains.items():
                if decomp_count >= 3: break
                if len(dv.req_ids) >= 2 and not dv.decomposed and dv.status != "excluded":
                    new_texts = self._domain_discovery.decompose_requirements(
                        dk, state.domain_gate, state)

                    # FIX-DEDUP: check semantic overlap before adding
                    existing_texts = {r.text.lower().strip() for r in state.requirements.values()}
                    for text in new_texts:
                        text_lower = text.lower().strip()
                        # Skip if >60% similar to any existing requirement
                        is_dup = False
                        for et in existing_texts:
                            if _message_similarity(text_lower, et) > 0.6:
                                is_dup = True; break
                        if not is_dup:
                            req = state.add_requirement(
                                req_type=RequirementType.FUNCTIONAL,
                                text=text, category=dk,
                                raw_excerpt=f"[Decomposed from {dv.label}]",
                                domain_key=dk, source="decomposed")
                            subdim = self._domain_discovery.classify_subdimension(text)
                            if subdim:
                                self._domain_discovery.tag_subdimension(
                                    req.req_id, subdim, dk, state.domain_gate)
                            existing_texts.add(text_lower)
                    decomp_count += 1

                    self._domain_discovery.update_domain_statuses(state.domain_gate, state)

            # 4k. Regenerate probe
            nd = state.domain_gate.next_unprobed()
            if nd and (nd.probe_count > 0 or not nd.probe_question):
                self._domain_discovery.get_probe_question(nd, state)

        # 4l. Sync SRS template
        if self._srs_template:
            self._srs_template.update_from_requirements(
                state.requirements, project_name=state.project_name)

        # 5-7. Gap detection & question generation
        gap_report = None
        if self._gap_detector:
            gap_report = self._gap_detector.analyse(state)
            q_set = self._question_generator.generate(
                gap_report=gap_report, state=state, project_name=state.project_name)
            if q_set.has_questions:
                self._architect.extra_context = self._question_generator.build_injection_text(q_set)

        # 8. Log
        logger.log_turn(turn_id=turn.turn_id, user_msg=user_message,
                       assistant_msg=assistant_response,
                       categories_updated=turn.categories_updated,
                       gap_report_dict=gap_report.to_dict() if gap_report else None)

        return assistant_response

    def finalize_session(self, state, logger):
        # if fr less than 5, mark as incomplete and skip SRS generation
        if state.functional_count < 5:
            logger.log_event("session_incomplete", {
                "reason":"Too few functional requirements elicited",
                "functional_count":state.functional_count})
            print("[Session Finalized] Incomplete session — too few functional requirements elicited.")
            return None
        state.session_complete = True
        if not self._srs_template:
            self._srs_template = create_template(state.session_id, state.project_name)
 
        # Step 1: populate template from elicited requirements (unchanged)
        self._srs_template.update_from_requirements(
            state.requirements, project_name=state.project_name)
 
        # Step 2: NEW — fill empty IEEE-830 sections using srs_coverage enricher
        # This runs ONLY when all gates are satisfied (already enforced upstream).
        # Imports here to avoid circular deps at module level.
        from srs_coverage import create_enricher
        enricher = create_enricher(provider=self.provider)
        filled_sections = enricher.enrich(self._srs_template, state)
 
        # Log which sections were filled and from what source (phase4 / llm_synthesis / stub)
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
                  f"{phase4_count} from Phase 4 customer answers, "
                  f"{llm_count} LLM synthesis, {stub_count} stubs.")
 
        # Step 3: write the document (unchanged)
        srs_path = generate_srs_document(
            template=self._srs_template, state=state, output_dir=self.output_dir)
        logger.log_session_end(state)
        return srs_path