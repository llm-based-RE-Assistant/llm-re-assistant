"""
src/components/conversation_manager.py
========================
RE Assistant — Iteration 3 (fixed) | University of Hildesheim
Core Conversation Loop: User → LLM → Response with History

Fix log (applied before Iteration 4)
--------------------------------------
FIX-W1  GapDetector and ProactiveQuestionGenerator are now WIRED into send_turn().
        In the original iteration-3 code, both components were implemented but
        never called.  The gap_detector.analyse() + question_generator.generate()
        pipeline is now executed after every turn, and the result is injected
        into PromptArchitect.extra_context BEFORE the next turn's system message
        is built.

FIX-W2  QuestionTracker is created in start_session() and carried throughout
        the session so repeated questions are avoided.

FIX-W3  The question_generator is created with the same LLM provider as the
        main conversation loop, enabling LLM-generated context-aware questions
        (see question_generator.py FIX-B).

FIX-W4  extra_context injection timing: the directive is set on self._architect
        AFTER the current turn's state update so the NEXT turn's system message
        contains the fresh directive — not the stale one from the previous turn.
        This matches the one-shot injection design in PromptArchitect.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import requests

sys.path.insert(0, str(Path(__file__).parent))

from conversation_state import ConversationState, RequirementType, create_session
from prompt_architect import PromptArchitect, IEEE830_CATEGORIES
from srs_template import SRSTemplate, create_template
from srs_formatter import SRSFormatter, generate_srs_document
from requirement_extractor import RequirementExtractor, create_extractor
# FIX-W1: import the two new components
from gap_detector import GapDetector, create_gap_detector
from question_generator import (
    ProactiveQuestionGenerator, QuestionTracker, create_question_generator,
)


# ---------------------------------------------------------------------------
# LLM Provider abstraction
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    @abstractmethod
    def chat(
        self,
        system_message: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str = "gpt-4o", timeout: int = 30):
        try:
            import openai
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY environment variable not set.")
        self._client = openai.OpenAI(api_key=api_key, timeout=timeout)
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    def chat(self, system_message, messages, temperature=0.0) -> str:
        full_messages = [{"role": "system", "content": system_message}] + messages
        response = self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""


class OllamaProvider(LLMProvider):
    def __init__(self, model: str = "llama3.1:8b", timeout: int = 90):
        api_key = os.getenv("OLLAMA_API_KEY")
        if not api_key:
            raise EnvironmentError("OLLAMA_API_KEY environment variable not set.")
        base_url = os.getenv("OLLAMA_BASE_URL", "https://genai-01.uni-hildesheim.de/ollama")
        self.base_url = base_url
        self._model = model
        self.api_endpoint = f"{base_url}/api/chat"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        self.timeout = timeout

    @property
    def model_name(self) -> str:
        return self._model

    def chat(self, system_message, messages, temperature=0.0) -> str:
        full_messages = [{"role": "system", "content": system_message}] + messages
        response = requests.post(
            url=self.api_endpoint,
            headers=self.headers,
            json={
                "model": self._model,
                "messages": full_messages,
                "options": {"temperature": temperature},
                "stream": False,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"] or ""


class StubProvider(LLMProvider):
    def __init__(self, responses: Optional[list[str]] = None):
        self._responses = responses or [
            "Thank you for describing your project. Could you tell me more about who the primary users will be and what they need to accomplish?",
            "Great. What are the three most important things a user must be able to DO with the system?",
            "Understood. What performance requirements does the system need to meet? For example, how quickly should it respond?",
            "Good. Now, regarding security and privacy — will the system handle any sensitive personal data?",
            "Noted. What reliability requirements do you have? For example, expected uptime?",
            "Thank you. I believe I now have sufficient information to generate the SRS. Shall I proceed?",
        ]
        self._index = 0

    @property
    def model_name(self) -> str:
        return "stub-provider-v1"

    def chat(self, system_message, messages, temperature=0.0) -> str:
        response = self._responses[self._index % len(self._responses)]
        self._index += 1
        return response


def create_provider(provider_name: str = "ollama", **kwargs) -> LLMProvider:
    if provider_name == "openai":
        return OpenAIProvider(**kwargs)
    elif provider_name == "ollama":
        return OllamaProvider(**kwargs)
    elif provider_name == "stub":
        return StubProvider(**kwargs)
    raise ValueError(f"Unknown provider: {provider_name!r}. Choose 'openai', 'ollama', or 'stub'.")


# ---------------------------------------------------------------------------
# Session Logger
# ---------------------------------------------------------------------------

class SessionLogger:
    def __init__(self, log_dir: Path, session_id: str):
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = log_dir / f"session_{session_id}.json"
        self._entries: list[dict] = []

    def log_event(self, event_type: str, data: dict) -> None:
        entry = {
            "timestamp": time.time(),
            "event_type": event_type,
            "data": data,
        }
        self._entries.append(entry)
        self._flush()

    def log_turn(self, turn_id: int, user_msg: str, assistant_msg: str,
                 categories_updated: list[str], gap_report_dict: Optional[dict] = None) -> None:
        data = {
            "turn_id":            turn_id,
            "user_message":       user_msg,
            "assistant_message":  assistant_msg,
            "categories_updated": categories_updated,
        }
        if gap_report_dict:
            data["gap_report"] = gap_report_dict   # FIX-W1: log gap report per turn
        self.log_event("turn", data)

    def log_session_end(self, state: ConversationState) -> None:
        self.log_event("session_end", state.to_dict())

    def _flush(self) -> None:
        with open(self._log_path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, indent=2, ensure_ascii=False)

    @property
    def log_path(self) -> Path:
        return self._log_path


# ---------------------------------------------------------------------------
# SRS trigger phrases
# ---------------------------------------------------------------------------

_SRS_TRIGGER_PHRASES = {
    "generate srs", "generate the srs", "create srs", "create the srs",
    "produce srs", "write the srs", "write srs", "i'm done", "i am done",
    "we are done", "that's all", "that is all", "end session",
    "end the session", "export srs", "export the srs",
}

_CONTRADICTION_PHRASES = {"actually", "wait", "no actually", "i meant", "correction"}


# ---------------------------------------------------------------------------
# Conversation Manager
# ---------------------------------------------------------------------------

@dataclass
class ConversationManager:
    """
    Orchestrates the full elicitation session.

    Parameters
    ----------
    provider   : LLMProvider — the main LLM backend.
    log_dir    : Path for session logs.
    output_dir : Path for SRS output files.
    temperature: LLM temperature (0.0 for reproducibility).
    gap_enabled: If False, gap detection is disabled (ablation OFF branch).
    """

    provider:    LLMProvider
    log_dir:     Path  = field(default_factory=lambda: Path(__file__).parent.parent / "logs")
    output_dir:  Path  = field(default_factory=lambda: Path(__file__).parent.parent / "output")
    temperature: float = 0.0
    gap_enabled: bool  = True   # set False for ablation study OFF branch

    _architect:          PromptArchitect = field(default_factory=PromptArchitect, init=False)
    _srs_template:       SRSTemplate     = field(default=None, init=False, repr=False)
    _extractor:          RequirementExtractor = field(default_factory=create_extractor, init=False)
    # FIX-W1: gap detector and question generator are now proper class members
    _gap_detector:       GapDetector          = field(default=None, init=False, repr=False)
    _question_generator: ProactiveQuestionGenerator = field(default=None, init=False, repr=False)
    _question_tracker:   QuestionTracker       = field(default=None, init=False, repr=False)

    def __post_init__(self):
        # FIX-W1: create gap detector
        self._gap_detector = create_gap_detector(enabled=self.gap_enabled)
        # FIX-W3: pass the same LLM provider to question_generator for LLM-mode questions
        self._question_generator = create_question_generator(
            max_questions_per_turn=1,
            mode="llm",
            llm_provider=self.provider,
        )

    def start_session(self) -> tuple[str, ConversationState, SessionLogger, SRSTemplate]:
        session_id = str(uuid.uuid4())[:8]
        state = create_session(session_id)
        self._srs_template = create_template(session_id)
        # FIX-W2: fresh tracker per session
        self._question_tracker = QuestionTracker()
        logger = SessionLogger(log_dir=self.log_dir, session_id=session_id)
        logger.log_event("session_start", {
            "session_id": session_id,
            "model": self.provider.model_name,
            "temperature": self.temperature,
            "gap_detection_enabled": self.gap_enabled,
        })
        return session_id, state, logger, self._srs_template

    def send_turn(
        self,
        user_message: str,
        state: ConversationState,
        logger: SessionLogger,
    ) -> str:
        """
        Process one user turn.

        Sequence (FIX-W1/W4):
          1.  Build system message — uses extra_context from PREVIOUS turn's gap directive
          2.  Assemble full message history + new user message
          3.  Call LLM
          4.  Update conversation state (heuristic coverage scan)
          4a. Extract and commit formalised requirements
          4b. Sync SRS template
          5.  Run GapDetector → GapReport
          6.  Run QuestionGenerator → QuestionSet (LLM-generated question)
          7.  Inject new gap directive into architect.extra_context for NEXT turn
          8.  Log the turn (including gap report)
          9.  Return assistant response
        """
        # 1. Build system message with directive from previous turn
        system_msg = self._architect.build_system_message(state)

        # 2. Assemble messages
        history = state.get_message_history()
        messages_to_send = history + [{"role": "user", "content": user_message}]

        # 3. LLM call
        try:
            assistant_response = self.provider.chat(
                system_message=system_msg,
                messages=messages_to_send,
                temperature=self.temperature,
            )
        except Exception as exc:
            raise RuntimeError(f"LLM API error: {exc}") from exc

        # 4. Update conversation state
        turn = state.add_turn(user_message, assistant_response)

        # 4a. Extract requirements
        extracted = self._extractor.extract(assistant_response)
        if extracted:
            self._extractor.commit(extracted, state)

        # 4b. Sync SRS template
        if self._srs_template is not None:
            self._srs_template.update_from_requirements(
                state.requirements,
                project_name=state.project_name,
            )

        # 5. Run gap detection (FIX-W1)
        gap_report = None
        if self._gap_detector is not None and self._question_tracker is not None:
            gap_report = self._gap_detector.analyse(state)

            # 6. Generate a context-aware follow-up question
            question_set = self._question_generator.generate(
                gap_report=gap_report,
                state=state,
                tracker=self._question_tracker,
            )

            # 7. FIX-W4: inject directive for the NEXT turn
            if question_set.has_questions:
                self._architect.extra_context = (
                    self._question_generator.build_injection_text(question_set)
                )

        # 8. Log
        logger.log_turn(
            turn_id=turn.turn_id,
            user_msg=user_message,
            assistant_msg=assistant_response,
            categories_updated=turn.categories_updated,
            gap_report_dict=gap_report.to_dict() if gap_report else None,
        )

        return assistant_response

    def finalize_session(
        self,
        state: ConversationState,
        logger: SessionLogger,
    ) -> Path:
        state.session_complete = True

        if self._srs_template is None:
            self._srs_template = create_template(state.session_id, state.project_name)
        self._srs_template.update_from_requirements(
            state.requirements,
            project_name=state.project_name,
        )

        srs_path = generate_srs_document(
            template=self._srs_template,
            state=state,
            output_dir=self.output_dir,
        )
        logger.log_session_end(state)
        return srs_path