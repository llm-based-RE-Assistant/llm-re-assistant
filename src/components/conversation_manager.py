"""
conversation_manager.py — Iteration 9
University of Hildesheim

Key changes (IT9):
- task_type parameter: "elicitation" | "srs_only"
- PromptArchitect initialized with task_type
- Context limited to 10 turns (20 messages) instead of 20 turns
- Domain seeding: uses reseed if domains already known (from uploaded reqs)
- inject_requirements: loads preprocessed reqs into state before first turn
- Project persistence helpers: save/load session to JSON file
"""
from __future__ import annotations
import json, os, sys, time, uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import requests

sys.path.insert(0, str(Path(__file__).parent))

from conversation_state import ConversationState, RequirementType, create_session
from prompt_architect import PromptArchitect, PHASE4_SECTIONS, TaskType
from srs_template import SRSTemplate, create_template
from srs_formatter import SRSFormatter, generate_srs_document
from requirement_extractor import RequirementExtractor, create_extractor
from gap_detector import GapDetector, create_gap_detector
from question_generator import ProactiveQuestionGenerator, create_question_generator
from domain_discovery import DomainDiscovery, DomainGate, create_domain_discovery


# ── LLM Providers ──

class LLMProvider(ABC):
    @abstractmethod
    def chat(self, system_message: str, messages: list[dict[str, str]],
             temperature: float = 0.0) -> str: ...
    @property
    @abstractmethod
    def model_name(self) -> str: ...


class OpenAIProvider(LLMProvider):
    def __init__(self, model="gpt-4o", timeout=120):
        import openai
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY not set.")
        self._client = openai.OpenAI(api_key=api_key, timeout=timeout)
        self._model = model

    @property
    def model_name(self):
        return self._model

    def chat(self, system_message, messages, temperature=0.0):
        full = [{"role": "system", "content": system_message}] + messages
        r = self._client.chat.completions.create(
            model=self._model, messages=full, temperature=temperature)
        return r.choices[0].message.content or ""


class OllamaProvider(LLMProvider):
    def __init__(self, model="llama3.1:8b", timeout=120):
        api_key = os.getenv("OLLAMA_API_KEY")
        if not api_key:
            raise EnvironmentError("OLLAMA_API_KEY not set.")
        base_url = os.getenv("OLLAMA_BASE_URL", "https://genai-01.uni-hildesheim.de/ollama")
        self._model = model
        self.api_endpoint = f"{base_url}/api/chat"
        self.headers = {"Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}"}
        self.timeout = timeout

    @property
    def model_name(self):
        return self._model

    def chat(self, system_message, messages, temperature=0.0):
        full = [{"role": "system", "content": system_message}] + messages
        r = requests.post(
            self.api_endpoint, headers=self.headers,
            json={"model": self._model, "messages": full,
                  "options": {"temperature": temperature}, "stream": False},
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
    def model_name(self):
        return "stub-provider-v1"

    def chat(self, system_message, messages, temperature=0.0):
        r = self._responses[self._index % len(self._responses)]
        self._index += 1
        return r


def create_provider(name="ollama", **kwargs):
    if name == "openai":
        return OpenAIProvider(**kwargs)
    elif name == "ollama":
        return OllamaProvider(**kwargs)
    elif name == "stub":
        return StubProvider(**kwargs)
    raise ValueError(f"Unknown provider: {name!r}")


# ── Session Logger ──

class SessionLogger:
    def __init__(self, log_dir: Path, session_id: str):
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = log_dir / f"session_{session_id}.json"
        self._entries: list[dict] = []

    def log_event(self, event_type, data):
        self._entries.append({"timestamp": time.time(),
                               "event_type": event_type, "data": data})
        self._flush()

    def log_turn(self, turn_id, user_msg, assistant_msg, categories_updated,
                 gap_report_dict=None):
        data = {"turn_id": turn_id, "user_message": user_msg,
                "assistant_message": assistant_msg,
                "categories_updated": categories_updated}
        if gap_report_dict:
            data["gap_report"] = gap_report_dict
        self._entries.append({"timestamp": time.time(),
                               "event_type": "turn", "data": data})
        self._flush()

    def log_session_end(self, state):
        self.log_event("session_end", state.get_coverage_report())

    def get_log_path(self) -> Path:
        return self._log_path

    def _flush(self):
        try:
            with open(self._log_path, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, indent=2, ensure_ascii=False)
        except Exception:
            pass


# ── Duplicate detection helper ──

def _message_similarity(a: str, b: str) -> float:
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


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
        from domain_discovery import NFR_CATEGORIES
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
        preprocessed_reqs: list,  # list of ProcessedRequirement
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

    # ── SMART Quality Check ──

    _SMART_CHECK_PROMPT = """\
You are an expert Requirements Engineer performing a SMART quality check.

CUSTOMER MESSAGE (context):
{user_message}

EXTRACTED REQUIREMENTS:
{requirements_list}

For EACH requirement, evaluate SMART criteria (Specific, Measurable, Testable, Unambiguous, Relevant).
- If it passes all 5, keep as-is.
- If it fails Measurable or Specific, REWRITE to add concrete numbers or remove vague terms.

Return a JSON array with one object per requirement:
{{
  "original": "<original text>",
  "final": "<rewritten or same>",
  "smart_score": <1-5>,
  "specific": true/false,
  "measurable": true/false,
  "testable": true/false,
  "unambiguous": true/false,
  "relevant": true/false,
  "rewritten": true/false
}}
Return ONLY the JSON array. No markdown, no explanation."""

    def _run_smart_check(self, extracted: list, user_message: str) -> list:
        if not extracted:
            return extracted
        req_lines = "\n".join(f"{i+1}. [{e.req_type}] {e.text}"
                               for i, e in enumerate(extracted))
        prompt = self._SMART_CHECK_PROMPT.format(
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

    def send_turn(self, user_message: str, state: ConversationState,
                  logger: SessionLogger) -> str:

        # 1. Build system message (phase-aware)
        system_msg = self._architect.build_system_message(state)
        current_phase = self._architect.get_current_phase(state)
        print(f"\n[Phase: {current_phase}] Turn {state.turn_count + 1}\n[System prompt length: {len(system_msg)} chars]")

        # 2. Assemble messages — use only last MAX_HISTORY_TURNS turns
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

        # 4. Update state
        turn = state.add_turn(user_message, assistant_response)

        # 4a. Extract requirements
        extracted = self._extractor.extract(assistant_response)

        # 4a2. Extract <SECTION> tags (Phase IEEE)
        sections_found = self._extractor.extract_sections(assistant_response)
        if sections_found:
            stored_ids = self._extractor.commit_sections(sections_found, state)
            if stored_ids:
                logger.log_event("phase4_sections_stored", {
                    "sections": stored_ids,
                    "phase4_progress": f"{len(state.phase4_sections_covered)}/{len(PHASE4_SECTIONS)}"
                })

        # 4b. SMART quality check
        if extracted:
            extracted = self._run_smart_check(extracted, user_message)

        if extracted and self._domain_discovery and state.domain_gate:
            # 4c. LLM-based domain matching
            for ext in extracted:
                cat_lower = ext.category.lower().replace(" ", "_").replace("-", "_")
                if cat_lower in state.domain_gate.domains:
                    ext.domain_label = cat_lower
                else:
                    matched_key = self._domain_discovery.match_requirement_to_domain(
                        ext.text, state.domain_gate)
                    if matched_key:
                        ext.domain_label = matched_key

            # 4d. Classify NFRs
            for ext in extracted:
                if ext.req_type == "non_functional":
                    cat_key = self._domain_discovery.classify_nfr(ext)
                    if cat_key:
                        ext.category = cat_key
                        state.increment_nfr_coverage(cat_key)

            # 4e. Classify sub-dimensions
            for ext in extracted:
                if ext.domain_label and ext.domain_label in state.domain_gate.domains:
                    subdim = self._domain_discovery.classify_subdimension(ext.text)
                    if subdim:
                        ext._subdim = subdim

            # 4f. Commit
            new_ids = self._extractor.commit(extracted, state)

            # Tag sub-dimensions
            if new_ids:
                for ext, req_id in zip(extracted, new_ids):
                    subdim = getattr(ext, '_subdim', None)
                    if subdim and ext.domain_label:
                        self._domain_discovery.tag_subdimension(
                            req_id, subdim, ext.domain_label, state.domain_gate)

        # 4g. Domain seeding / re-seeding
        if self._domain_discovery and state.domain_gate:
            has_existing_domains = state.domain_gate.seeded and state.domain_gate.total > 0

            if state.turn_count == 1 and not has_existing_domains:
                # Fresh seed on first turn (no pre-loaded domains)
                self._domain_discovery.seed(
                    user_message, state.domain_gate, state.turn_count,
                    project_name=state.project_name)
            elif state.turn_count == 1 and has_existing_domains:
                # IT9: domains already seeded from uploaded reqs — do reseed instead
                all_msgs = [user_message]
                self._domain_discovery.reseed(
                    all_msgs, state.domain_gate, state, state.turn_count)
            elif state.turn_count == DomainDiscovery.RESEED_TURN:
                all_user_msgs = [t.user_message for t in state.turns] + ['\n'] + [user_message]
                self._domain_discovery.reseed(
                    all_user_msgs, state.domain_gate, state, state.turn_count)
            elif state.turn_count == DomainDiscovery.SECOND_RESEED_TURN:
                if state.domain_gate.reseed_turn < DomainDiscovery.SECOND_RESEED_TURN:
                    all_user_msgs = [t.user_message for t in state.turns[-10:]] + ['\n'] + [user_message]
                    state.domain_gate.reseed_turn = 0
                    self._domain_discovery.reseed(
                        all_user_msgs, state.domain_gate, state, state.turn_count)

            # 4h. Project name extraction
            if state.project_name_needs_llm and state.turn_count == 1:
                name = self._domain_discovery.extract_project_name(user_message)
                if name:
                    state.project_name = name
                    state.project_name_needs_llm = False

            # 4i. Update domain statuses
            self._domain_discovery.update_domain_statuses(state.domain_gate, state)

            # 4j. Track probe count
            nd = state.domain_gate.next_unprobed()
            if nd:
                cdk = None
                for dk, dv in state.domain_gate.domains.items():
                    if dv is nd:
                        cdk = dk
                        break
                if cdk and cdk == self._last_probed_domain:
                    nd.probe_count += 1
                elif cdk:
                    self._last_probed_domain = cdk

            # 4k. Decomposition — max 3 domains per turn
            decomp_count = 0
            for dk, dv in state.domain_gate.domains.items():
                if decomp_count >= 3:
                    break
                if len(dv.req_ids) >= 2 and not dv.decomposed and dv.status != "excluded":
                    new_texts = self._domain_discovery.decompose_requirements(
                        dk, state.domain_gate, state)
                    existing_texts = {r.text.lower().strip() for r in state.requirements.values()}
                    for text in new_texts:
                        text_lower = text.lower().strip()
                        is_dup = any(_message_similarity(text_lower, et) > 0.6
                                     for et in existing_texts)
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

            # 4l. Regenerate probe
            nd = state.domain_gate.next_unprobed()
            if nd and (nd.probe_count > 0 or not nd.probe_question):
                self._domain_discovery.get_probe_question(nd, state)

        # 4m. Sync SRS template
        if self._srs_template:
            self._srs_template.update_from_requirements(
                state.requirements, project_name=state.project_name)

        # 5. Gap detection
        gap_report = None
        if self._gap_detector:
            gap_report = self._gap_detector.analyse(state)

        # 6. Log turn
        logger.log_turn(turn_id=turn.turn_id, user_msg=user_message,
                        assistant_msg=assistant_response,
                        categories_updated=turn.categories_updated,
                        gap_report_dict=gap_report.to_dict() if gap_report else None)

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
            template=self._srs_template, state=state, output_dir=self.output_dir)
        logger.log_session_end(state)
        return srs_path