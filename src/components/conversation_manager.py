"""
conversation_manager.py
========================
RE Assistant — Iteration 2 | University of Hildesheim
Core Conversation Loop: User → LLM → Response with History
 
Responsibilities
----------------
- LLMProvider: Abstract interface + OpenAI / stub implementations
- ConversationManager: Orchestrates the session loop, calls prompt architect,
  maintains history, routes to SRS generation
- run_session(): CLI entry point for a single elicitation session
- SessionLogger: Writes JSON session log for evaluation and traceability
 
Architecture
------------
The conversation loop follows this sequence on every turn:
 
  1. Receive user input (CLI)
  2. Build system message via PromptArchitect (dynamic context injected)
  3. Assemble messages = [system] + full_history + [new user turn]
  4. Call LLMProvider.chat()
  5. Receive assistant response
  6. Update ConversationState (add_turn → heuristic coverage scan)
  7. Log the turn (SessionLogger)
  8. Check stop conditions (user typed "generate srs", coverage complete, etc.)
  9. Display assistant response → repeat
 
This guarantees that:
  - Full context is passed on every turn (no memory loss)
  - System prompt is dynamically updated with coverage state (no premature closure)
  - Every exchange is logged to JSON for evaluation (traceability)
"""
 
from __future__ import annotations
 
import json
import os
import re
import sys
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
 
# Local modules
# (when running as a script from /src, add parent to path)
sys.path.insert(0, str(Path(__file__).parent))
 
from conversation_state import ConversationState, RequirementType, create_session
from prompt_architect import PromptArchitect, IEEE830_CATEGORIES
from srs_template import SRSTemplate, create_template
from srs_formatter import SRSFormatter, generate_srs_document
 
 
# ---------------------------------------------------------------------------
# LLM Provider abstraction
# ---------------------------------------------------------------------------
 
class LLMProvider(ABC):
    """
    Abstract interface for LLM backends.
    Implementations: OpenAIProvider, StubProvider (for testing).
    """
 
    @abstractmethod
    def chat(
        self,
        system_message: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> str:
        """
        Send a conversation to the LLM and return the assistant's response.
 
        Parameters
        ----------
        system_message : The system prompt (role + context + task blocks).
        messages       : Full history as [{"role": "user"/"assistant", "content": ...}, ...].
        temperature    : 0.0 for reproducible evaluation runs (NFR-05).
        """
        ...
 
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable model identifier for logs."""
        ...
 
 
class OpenAIProvider(LLMProvider):
    """
    OpenAI GPT-4o provider.
    Reads API key from OPENAI_API_KEY environment variable.
    """
 
    def __init__(self, model: str = "gpt-4o", timeout: int = 30):
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package not installed. Run: pip install openai"
            )
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY environment variable not set."
            )
        self._client = openai.OpenAI(api_key=api_key, timeout=timeout)
        self._model = model
 
    @property
    def model_name(self) -> str:
        return self._model
 
    def chat(
        self,
        system_message: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> str:
        full_messages = [{"role": "system", "content": system_message}] + messages
        response = self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,  # type: ignore[arg-type]
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

class OllamaProvider(LLMProvider):
    """
    Ollama llama3.1 provider.
    Reads API key from OLLAMA_API_KEY environment variable.
    """

    def __init__(self, model: str = "llama3.1:8b", timeout: int = 90):
        api_key = os.getenv("OLLAMA_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OLLAMA_API_KEY environment variable not set."
            )
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

    def chat(
        self,
        system_message: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> str:
        full_messages = [{"role": "system", "content": system_message}] + messages
        #print(f"Full message: \n{full_messages}\n")  # Debug print to check message format before API call
        response = requests.post(
            url=self.api_endpoint,
            headers=self.headers,
            json={
                "model": self._model,
                "messages": full_messages,
                "options": {
                    "temperature": temperature
                },
                "stream": False
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()

        return data["message"]["content"] or ""

class StubProvider(LLMProvider):
    """
    Deterministic stub for unit testing — returns scripted responses
    without making real API calls.
    """

    def __init__(self, responses: Optional[list[str]] = None):
        self._responses = responses or [
            "Thank you for describing your project. Could you tell me more about who the primary users will be?",
            "Understood. What performance requirements does the system need to meet? For example, how quickly should it respond?",
            "Good. Now, regarding security and privacy — will the system handle any sensitive personal data? Are there GDPR or similar regulatory requirements?",
            "Noted. What reliability requirements do you have? For example, expected uptime percentage or acceptable downtime window?",
            "Thank you. I believe I now have sufficient information to generate the SRS. Shall I proceed?",
        ]
        self._index = 0

    @property
    def model_name(self) -> str:
        return "stub-provider-v1"

    def chat(
        self,
        system_message: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> str:
        response = self._responses[self._index % len(self._responses)]
        self._index += 1
        return response


def create_provider(provider_name: str = "ollama", **kwargs) -> LLMProvider:
    """
    Factory function. Reads provider from settings or argument.

    Parameters
    ----------
    provider_name : "openai" | "stub" | "ollama"
    """
    if provider_name == "openai":
        return OpenAIProvider(**kwargs)
    elif provider_name == "stub":
        return StubProvider(**kwargs)
    elif provider_name == "ollama":
        return OllamaProvider(**kwargs)
    else:
        raise ValueError(f"Unknown LLM provider: '{provider_name}'")


@dataclass
class SessionLogger:
    """
    Writes all turns, requirements, and coverage data to a JSON log file.
    Each session gets its own file, named by session_id.
    Satisfies NFR-06 (Traceability) and NFR-05 (Reproducibility).
    """
 
    log_dir: Path
    session_id: str
    _log_path: Path = field(init=False)
    _entries: list[dict] = field(default_factory=list)
 
    def __post_init__(self):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self.log_dir / f"session_{self.session_id}.json"
 
    def log_event(self, event_type: str, data: dict) -> None:
        entry = {
            "timestamp": time.time(),
            "event_type": event_type,
            "data": data,
        }
        self._entries.append(entry)
        self._flush()
 
    def log_turn(self, turn_id: int, user_msg: str, assistant_msg: str,
                 categories_updated: list[str]) -> None:
        self.log_event("turn", {
            "turn_id":            turn_id,
            "user_message":       user_msg,
            "assistant_message":  assistant_msg,
            "categories_updated": categories_updated,
        })
 
    def log_session_end(self, state: ConversationState) -> None:
        self.log_event("session_end", state.to_dict())
 
    def _flush(self) -> None:
        with open(self._log_path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, indent=2, ensure_ascii=False)
 
    @property
    def log_path(self) -> Path:
        return self._log_path
 
 
# ---------------------------------------------------------------------------
# LLM-based Requirement Extractor
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM_PROMPT = """You are a Requirements Engineering expert.
Your task is to analyse a completed elicitation conversation and extract ALL
software requirements discussed.

You MUST respond with ONLY a valid JSON object — no prose, no markdown fences,
no explanation before or after.  The schema is:

{
  "project_name": "<name of the system being built>",
  "requirements": [
    {
      "type": "functional" | "non_functional" | "constraint",
      "category": "<one of: purpose, scope, stakeholders, functional, performance, usability, security_privacy, reliability, compatibility, maintainability, constraints, interfaces>",
      "text": "<complete, self-contained requirement in IEEE 'The system shall...' form>",
      "turn_id": <integer — the conversation turn the requirement was first mentioned>,
      "raw_excerpt": "<verbatim phrase from the conversation that led to this requirement>"
    }
  ]
}

Rules:
1. ONLY extract what the USER described as requirements — ignore assistant questions.
2. Every requirement text MUST begin with "The system shall".
3. Be specific: expand vague user statements into clear, testable requirements
   using the measurable values the user provided (e.g. "respond within 2 seconds",
   "support 500 concurrent users").
4. Do NOT invent requirements not grounded in the conversation.
5. Do NOT include assistant questions or clarifications as requirements.
6. Cover ALL IEEE-830 categories that were discussed: functional, performance,
   usability, security_privacy, reliability, compatibility, maintainability,
   constraints, interfaces, stakeholders.
7. If a requirement is ambiguous or vague, still include it but add a note in
   the text such as "(exact threshold to be confirmed with stakeholder)".
"""


def _build_extraction_prompt(state: "ConversationState") -> str:
    """
    Build the user-turn prompt for the one-shot extraction call.
    Formats the full conversation transcript for the LLM.
    """
    lines = [
        f"Extract all requirements from the following elicitation session "
        f"for the project: '{state.project_name}'.",
        "",
        "=== CONVERSATION TRANSCRIPT ===",
        "",
    ]
    for turn in state.turns:
        lines.append(f"[Turn {turn.turn_id} — User]")
        lines.append(turn.user_message.strip())
        lines.append("")
        lines.append(f"[Turn {turn.turn_id} — Assistant]")
        lines.append(turn.assistant_message.strip())
        lines.append("")

    lines.append("=== END OF TRANSCRIPT ===")
    lines.append("")
    lines.append(
        "Now extract ALL requirements discussed above. "
        "Respond with ONLY the JSON object described in your instructions."
    )
    return "\n".join(lines)


def _extract_requirements_via_llm(
    provider: "LLMProvider",
    state: "ConversationState",
) -> list[dict]:
    """
    Call the LLM once with the full conversation transcript and ask it to
    extract all requirements as structured JSON.

    Returns a list of raw requirement dicts (validated against expected keys).
    Falls back to an empty list on any parse failure, so SRS generation
    always proceeds — the document will note that extraction failed.
    """
    prompt = _build_extraction_prompt(state)
    try:
        raw_response = provider.chat(
            system_message=_EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
    except Exception as exc:
        print(f"[WARN] LLM extraction call failed: {exc}")
        return []

    # Strip any accidental markdown fences the LLM may have added
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        print(f"[WARN] Could not parse extraction JSON: {exc}")
        print(f"       Raw response (first 400 chars): {cleaned[:400]}")
        return []

    # Update project name if the LLM found a better one
    llm_name = data.get("project_name", "").strip()
    if llm_name and llm_name != "Unknown Project":
        state.project_name = llm_name

    reqs = data.get("requirements", [])
    if not isinstance(reqs, list):
        return []

    # Validate each entry has required keys
    valid = []
    required_keys = {"type", "category", "text", "turn_id"}
    for r in reqs:
        if isinstance(r, dict) and required_keys.issubset(r.keys()):
            valid.append(r)

    return valid


def _populate_state_from_llm_extraction(
    extracted: list[dict],
    state: "ConversationState",
) -> None:
    """
    Take the validated extraction output and load it into ConversationState.
    Maps the LLM's type strings to RequirementType enum values.
    """
    type_map = {
        "functional":     RequirementType.FUNCTIONAL,
        "non_functional": RequirementType.NON_FUNCTIONAL,
        "nonfunctional":  RequirementType.NON_FUNCTIONAL,
        "constraint":     RequirementType.CONSTRAINT,
    }

    for item in extracted:
        req_type = type_map.get(item["type"].lower(), RequirementType.FUNCTIONAL)
        state.add_requirement(
            req_type=req_type,
            text=item["text"].strip(),
            category=item.get("category", "functional"),
            raw_excerpt=item.get("raw_excerpt", "")[:200],
        )
        # Back-fill the correct turn_id (add_requirement uses turn_count,
        # which is correct at session end, but we want the original turn)
        req_id = max(state.requirements.keys(),
                     key=lambda k: state.requirements[k].timestamp)
        state.requirements[req_id].turn_id = int(item.get("turn_id", state.turn_count))


# ---------------------------------------------------------------------------
# Conversation Manager
# ---------------------------------------------------------------------------
 
# Phrases that signal the USER explicitly wants to end the session and generate the SRS.
#
# Rules:
#  - Multi-word phrases only, or unambiguous single words ("quit", "exit").
#  - NO single common words like "done", "complete", "finish" — these appear
#    constantly in normal conversation and assistant responses, causing false triggers.
#  - Checked against the USER's message only, never the assistant response.
_SRS_TRIGGER_PHRASES = {
    "generate srs",
    "generate the srs",
    "create srs",
    "create the srs",
    "produce srs",
    "write the srs",
    "write srs",
    "i'm done",
    "i am done",
    "we are done",
    "that's all",
    "that is all",
    "end session",
    "end the session",
    "export srs",
    "export the srs",
}
 
# Keywords that signal explicit contradiction flagging by user
_CONTRADICTION_PHRASES = {"actually", "wait", "no actually", "i meant", "correction"}
 
 
@dataclass
class ConversationManager:
    """
    Orchestrates the full elicitation session.
 
    Parameters
    ----------
    provider   : LLMProvider — the LLM backend to use.
    log_dir    : Path for session logs.
    output_dir : Path for SRS output files.
    temperature: LLM temperature (0.0 for reproducibility).
    """
 
    provider:    LLMProvider
    log_dir:     Path = field(default_factory=lambda: Path("logs"))
    output_dir:  Path = field(default_factory=lambda: Path("output"))
    temperature: float = 0.0
 
    _architect:    PromptArchitect = field(default_factory=PromptArchitect, init=False)
    _srs_template: SRSTemplate     = field(default=None,   init=False, repr=False)  # type: ignore[assignment]
 
    def start_session(self) -> tuple[str, ConversationState, SessionLogger, SRSTemplate]:
        """
        Initialise a new session. Returns (session_id, state, logger, template).
        The SRSTemplate is created here and updated after every turn.
        """
        session_id = str(uuid.uuid4())[:8]
        state = create_session(session_id)
        self._srs_template = create_template(session_id)
        logger = SessionLogger(log_dir=self.log_dir, session_id=session_id)
        logger.log_event("session_start", {
            "session_id": session_id,
            "model": self.provider.model_name,
            "temperature": self.temperature,
        })
        return session_id, state, logger, self._srs_template
 
    def send_turn(
        self,
        user_message: str,
        state: ConversationState,
        logger: SessionLogger,
    ) -> str:
        """
        Process one user turn:
          1. Build system message (dynamic context)
          2. Assemble full message history
          3. Call LLM
          4. Update state
          5. Log the turn
          6. Return assistant response
 
        This is the core of the conversation loop.
        Raises RuntimeError on LLM failure (for graceful handling upstream).
        """
        # 1. Dynamic system message with current coverage state
        system_msg = self._architect.build_system_message(state)
 
        # 2. Full history + new user message
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
 
        # 4. Update conversation state (also runs heuristic coverage scan)
        turn = state.add_turn(user_message, assistant_response)
 
        # 4b. Sync SRS template with any new requirements added this turn
        if self._srs_template is not None:
            self._srs_template.update_from_requirements(
                state.requirements,
                project_name=state.project_name,
            )
 
        # 5. Log
        logger.log_turn(
            turn_id=turn.turn_id,
            user_msg=user_message,
            assistant_msg=assistant_response,
            categories_updated=turn.categories_updated,
        )
 
        return assistant_response
 
    def _should_generate_srs(self, user_message: str, state: ConversationState) -> bool:
        """
        Determine whether to generate the SRS after this turn.
 
        Two triggers:
          A) EXPLICIT: the user typed a recognised end-session phrase.
          B) AUTOMATIC: mandatory NFR coverage is complete AND enough FRs exist.
 
        Guards:
          - Explicit trigger requires the phrase to be in the USER's message
            (never checked against assistant text).
          - Automatic trigger requires at least 3 turns (prevents auto-close
            after a single turn where the assistant listed all category names).
          - Automatic trigger requires at least 1 FR actually extracted.
        """
        lowered = user_message.lower().strip().rstrip(".")
        explicit_request = any(phrase in lowered for phrase in _SRS_TRIGGER_PHRASES)
 
        # Automatic trigger: only after ≥3 turns AND at least 1 formal FR recorded
        MIN_TURNS_FOR_AUTO_CLOSE = 3
        coverage_complete = (
            state.mandatory_nfrs_covered
            and state.functional_count >= 1
            and state.turn_count >= MIN_TURNS_FOR_AUTO_CLOSE
        )
        return explicit_request or coverage_complete
 
    def finalize_session(
        self,
        state: ConversationState,
        logger: SessionLogger,
    ) -> Path:
        """
        Close the session and write the SRS document to disk.

        Steps
        -----
        1. Call the LLM once with the full conversation transcript to extract
           all requirements as structured JSON (the one-shot extractor).
        2. Populate ConversationState.requirements from the extraction output.
        3. Sync the SRSTemplate with the now-populated requirement store.
        4. Render and write the IEEE-830 Markdown document via SRSFormatter.
        5. Log the session end event.

        The LLM extraction step (1) is the key improvement over the heuristic
        approach: the model understands context and can distinguish user
        statements from assistant questions, producing clean, testable
        requirement texts in IEEE 'shall' form.
        """
        state.session_complete = True

        # 1 & 2. LLM extraction — populate state.requirements
        print("\n[Extracting requirements from conversation via LLM...]")
        extracted = _extract_requirements_via_llm(self.provider, state)
        if extracted:
            _populate_state_from_llm_extraction(extracted, state)
            print(f"    → Extracted {len(extracted)} requirement(s) from transcript.")
        else:
            print("    ⚠️  LLM extraction returned no requirements. "
                  "SRS will be generated with empty requirement sections.")

        # 3. Sync SRS template
        if self._srs_template is None:
            self._srs_template = create_template(state.session_id, state.project_name)
        self._srs_template.update_from_requirements(
            state.requirements,
            project_name=state.project_name,
        )

        # 4. Render and write SRS
        srs_path = generate_srs_document(
            template=self._srs_template,
            state=state,
            output_dir=self.output_dir,
        )

        # 5. Log
        logger.log_session_end(state)
        return srs_path