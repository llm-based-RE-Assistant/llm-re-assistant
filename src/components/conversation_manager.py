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
import sys
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import markdown

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
        return markdown.markdown(response.choices[0].message.content) or ""

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

        return markdown.markdown(data["message"]["content"]) or ""


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
# SRS Generator (minimal for Iteration 2)
# ---------------------------------------------------------------------------
 
def generate_srs(state: ConversationState, output_dir: Path) -> Path:
    """
    Generate an IEEE-830 compliant SRS document in Markdown format.
    Satisfies FR-S01, FR-S02, FR-S03, FR-S04.
 
    The generator renders the Requirement Store directly — no LLM call needed.
    All requirements trace back to their source turn (FR-S05 partial).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    filename = f"SRS_{state.session_id}_{timestamp_str}.md"
    output_path = output_dir / filename
 
    lines: list[str] = []
 
    def w(text: str = "") -> None:
        lines.append(text)
 
    # Helpers for section grouping
    frs  = [r for r in state.requirements.values() if r.req_type == RequirementType.FUNCTIONAL]
    nfrs = [r for r in state.requirements.values() if r.req_type == RequirementType.NON_FUNCTIONAL]
    cons = [r for r in state.requirements.values() if r.req_type == RequirementType.CONSTRAINT]
 
    # ---- Header ----
    w(f"# Software Requirements Specification")
    w(f"## {state.project_name}")
    w()
    w(f"| Field | Value |")
    w(f"|-------|-------|")
    w(f"| Document | SRS — {state.project_name} |")
    w(f"| Standard | IEEE 830-1998 (adapted) |")
    w(f"| Version | v0.1 (generated by RE Assistant Iteration 2) |")
    w(f"| Status | Draft |")
    w(f"| Session ID | `{state.session_id}` |")
    w(f"| Generated | {time.strftime('%Y-%m-%d %H:%M:%S')} |")
    w(f"| Elicitation Turns | {state.turn_count} |")
    w()
 
    # ---- §1 Introduction ----
    w("---")
    w()
    w("## 1. Introduction")
    w()
    w("### 1.1 Purpose")
    w(f"This document specifies the software requirements for **{state.project_name}**. "
      f"It was generated by the RE Assistant through a structured elicitation session "
      f"and serves as the primary reference for development, testing, and stakeholder validation.")
    w()
    w("### 1.2 Scope")
    w(f"The system described in this document is **{state.project_name}**. "
      f"Requirements were elicited via a {state.turn_count}-turn conversational session.")
    w()
    w("### 1.3 Definitions and Abbreviations")
    w("| Term | Definition |")
    w("|------|------------|")
    w("| FR   | Functional Requirement |")
    w("| NFR  | Non-Functional Requirement |")
    w("| CON  | Constraint |")
    w("| SRS  | Software Requirements Specification |")
    w("| IEEE 830 | IEEE Standard for Software Requirements Specifications (1998) |")
    w()
    w("### 1.4 Document Conventions")
    w("Each requirement is assigned a unique ID (FR-NNN, NFR-NNN, CON-NNN) and references the "
      "conversation turn from which it was derived (Turn N).")
    w()
 
    # ---- §2 Overall Description ----
    w("---")
    w()
    w("## 2. Overall Description")
    w()
    w("### 2.1 Product Perspective")
    w(f"*{state.project_name}* is a standalone software system elicited through the RE Assistant. "
      f"See conversation log `session_{state.session_id}.json` for full elicitation transcript.")
    w()
    w("### 2.2 User Classes and Characteristics")
    stakeholder_reqs = [r for r in state.requirements.values() if r.category == "stakeholders"]
    if stakeholder_reqs:
        for r in stakeholder_reqs:
            w(f"- {r.text} *(Turn {r.turn_id})*")
    else:
        w("*No stakeholder roles explicitly elicited. See conversation log for context.*")
    w()
    w("### 2.3 Operating Environment")
    compat_reqs = [r for r in state.requirements.values() if r.category == "compatibility"]
    if compat_reqs:
        for r in compat_reqs:
            w(f"- {r.text} *(Turn {r.turn_id})*")
    else:
        w("*Compatibility and operating environment not fully elicited.*")
    w()
    w("### 2.4 Design and Implementation Constraints")
    if cons:
        for r in cons:
            w(f"- **{r.req_id}**: {r.text} *(Turn {r.turn_id})*")
    else:
        w("*No explicit constraints elicited.*")
    w()
    w("### 2.5 Assumptions and Dependencies")
    w("*To be confirmed with stakeholders during review.*")
    w()
 
    # ---- §3 Functional Requirements ----
    w("---")
    w()
    w("## 3. Functional Requirements")
    w()
    if frs:
        # Group by category
        categories_seen: dict[str, list] = {}
        for r in frs:
            label = IEEE830_CATEGORIES.get(r.category, r.category)
            categories_seen.setdefault(label, []).append(r)
        for label, reqs in categories_seen.items():
            w(f"### 3.x {label}")
            w()
            for r in reqs:
                ambig = " ⚠️ *[Contains unresolved ambiguity]*" if r.is_ambiguous else ""
                w(f"**{r.req_id}**: {r.text}{ambig}")
                w(f"> *Source: Turn {r.turn_id} | Raw excerpt: \"{r.raw_excerpt}\"*")
                w()
    else:
        w("*No functional requirements were formally extracted during this session.*")
        w()
        w("**Note for evaluators**: This is a known Iteration 2 limitation. "
          "The Requirement Extractor component is not yet connected to the conversation loop. "
          "Requirements were elicited conversationally but not automatically structured. "
          "See session log for full transcript. Iteration 3 will add automatic extraction.*")
    w()
 
    # ---- §4 Non-Functional Requirements ----
    w("---")
    w()
    w("## 4. Non-Functional Requirements")
    w()
 
    nfr_categories = [
        ("performance",      "4.1 Performance Requirements"),
        ("usability",        "4.2 Usability Requirements"),
        ("security_privacy", "4.3 Security and Privacy Requirements"),
        ("reliability",      "4.4 Reliability and Availability Requirements"),
        ("compatibility",    "4.5 Compatibility and Portability Requirements"),
        ("maintainability",  "4.6 Maintainability Requirements"),
    ]
 
    for cat_key, section_title in nfr_categories:
        w(f"### {section_title}")
        cat_nfrs = [r for r in nfrs if r.category == cat_key]
        covered = cat_key in state.covered_categories
        if cat_nfrs:
            for r in cat_nfrs:
                w(f"**{r.req_id}**: {r.text} *(Turn {r.turn_id})*")
                w()
        elif covered:
            w(f"*This category was discussed in the session (see log) but no formal NFR was extracted.*")
            w()
        else:
            w(f"⚠️ **NOT ELICITED** — This mandatory NFR category was not covered during the session.")
            w()
 
    # ---- §5 External Interfaces ----
    w("---")
    w()
    w("## 5. External Interface Requirements")
    w()
    iface_reqs = [r for r in state.requirements.values() if r.category == "interfaces"]
    if iface_reqs:
        for r in iface_reqs:
            w(f"**{r.req_id}**: {r.text} *(Turn {r.turn_id})*")
    else:
        w("*External interfaces not explicitly elicited.*")
    w()
 
    # ---- §6 Coverage Report ----
    w("---")
    w()
    w("## 6. Elicitation Coverage Report")
    w()
    w("*This section is generated by the RE Assistant for evaluation purposes.*")
    w()
    report = state.get_coverage_report()
    w(f"| Metric | Value |")
    w(f"|--------|-------|")
    w(f"| Total turns | {report['turn_count']} |")
    w(f"| Requirements elicited | {report['total_requirements']} |")
    w(f"| Functional | {report['functional_count']} |")
    w(f"| Non-functional | {report['nonfunctional_count']} |")
    w(f"| IEEE-830 category coverage | {report['coverage_percentage']}% |")
    w(f"| Mandatory NFRs covered | {'✓ Yes' if report['mandatory_nfrs_covered'] else '✗ No'} |")
    w()
    if report["uncovered_categories"]:
        w("**Uncovered IEEE-830 categories:**")
        for cat in report["uncovered_categories"]:
            label = IEEE830_CATEGORIES.get(cat, cat)
            w(f"- {label}")
        w()
    if report["missing_mandatory_nfrs"]:
        w("**⚠️ Missing mandatory NFR categories:**")
        for cat in report["missing_mandatory_nfrs"]:
            w(f"- {cat}")
        w()
 
    # ---- Appendix ----
    w("---")
    w()
    w("## Appendix A — Requirement Traceability Matrix")
    w()
    w("| ID | Type | Category | Turn | Text |")
    w("|----|------|----------|------|------|")
    for req in sorted(state.requirements.values(), key=lambda r: r.req_id):
        cat_label = IEEE830_CATEGORIES.get(req.category, req.category)
        short_text = req.text[:80] + ("..." if len(req.text) > 80 else "")
        w(f"| {req.req_id} | {req.req_type.value} | {cat_label} | T{req.turn_id} | {short_text} |")
    w()
    w(f"*Full session transcript: `logs/session_{state.session_id}.json`*")
 
    # Write file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
 
    return output_path
 
 
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
    log_dir:     Path = field(default_factory=lambda:  Path(__file__).parent.parent / "logs")
    output_dir:  Path = field(default_factory=lambda: Path(__file__).parent.parent / "output")
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

        # 4a. Extract and commit formalised requirements from assistant response [Iteration 3]
 
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
 
        Uses the living SRSTemplate (kept in sync by send_turn) and the
        SRSFormatter to produce a full IEEE-830 Markdown document.
        Falls back to creating a fresh template if start_session was not called
        (e.g. in tests that drive finalize_session directly).
        """
        state.session_complete = True
 
        # Ensure template exists and is up-to-date
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
 
 
# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
 
_WELCOME_BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║          RE Assistant — Iteration 2 Prototype v0.1              ║
║          University of Hildesheim | DSR Project                  ║
╠══════════════════════════════════════════════════════════════════╣
║  Commands:                                                        ║
║    Type your message and press Enter to continue.                ║
║    Type 'generate srs' or 'done' to end the session.            ║
║    Type 'status' to see current coverage.                        ║
║    Type 'quit' to exit without generating SRS.                   ║
╚══════════════════════════════════════════════════════════════════╝
"""
 
_OPENING_PROMPT = (
    "Hello! I'm your Requirements Engineering assistant. I'll help you create a complete, "
    "structured Software Requirements Specification (SRS) for your software project.\n\n"
    "To get started, please describe the software system you want to build. "
    "Include its main purpose, who will use it, and any key features you have in mind."
)
 
 
def _print_coverage_status(state: ConversationState) -> None:
    """Print a formatted coverage summary to the terminal."""
    report = state.get_coverage_report()
    print(f"\n{'─' * 60}")
    print(f"  SESSION STATUS — Turn {report['turn_count']} | "
          f"Coverage: {report['coverage_percentage']}%")
    print(f"  Requirements: {report['total_requirements']} total "
          f"({report['functional_count']} FR, {report['nonfunctional_count']} NFR)")
    covered = report['covered_categories']
    missing = report['uncovered_categories']
    print(f"  Covered categories ({len(covered)}): "
          + (", ".join(covered) if covered else "none"))
    if report['missing_mandatory_nfrs']:
        print(f"  ⚠️  Missing MANDATORY NFRs: "
              + ", ".join(report['missing_mandatory_nfrs']))
    print(f"{'─' * 60}\n")
 
 
def run_session(
    provider_name: str = "openai",
    log_dir: Optional[str] = None,
    output_dir: Optional[str] = None,
    **provider_kwargs,
) -> None:
    """
    Run an interactive elicitation session from the CLI.
 
    Parameters
    ----------
    provider_name : "openai" | "stub"
    log_dir       : Directory for session logs (default: ./logs)
    output_dir    : Directory for SRS output (default: ./output)
    """
    _log_dir    = Path(log_dir)    if log_dir    else Path(__file__).parent.parent / "logs"
    _output_dir = Path(output_dir) if output_dir else Path(__file__).parent.parent / "output"
 
    print(_WELCOME_BANNER)
 
    # Initialise provider
    try:
        provider = create_provider(provider_name, **provider_kwargs)
        print(f"  LLM provider: {provider.model_name}\n")
    except (ImportError, EnvironmentError) as e:
        print(f"ERROR: Could not initialise LLM provider: {e}")
        print("Falling back to stub provider for demonstration.\n")
        provider = StubProvider()
 
    manager = ConversationManager(
        provider=provider,
        log_dir=_log_dir,
        output_dir=_output_dir,
    )
 
    session_id, state, logger, template = manager.start_session()
    print(f"  Session ID: {session_id}")
    print(f"  Logs: {logger.log_path}\n")
 
    # Show opening message
    print(f"\nAssistant:\n{_OPENING_PROMPT}\n")
 
    # Main conversation loop
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n[Session interrupted — no SRS generated]")
            break
 
        if not user_input:
            continue
 
        # Special commands
        lower = user_input.lower()
        if lower == "quit":
            print("\n[Exiting without generating SRS]")
            break
 
        if lower == "status":
            _print_coverage_status(state)
            continue
 
        # Send turn to LLM
        print()
        try:
            response = manager.send_turn(user_input, state, logger)
        except RuntimeError as e:
            print(f"[ERROR] {e}")
            print("[Retrying is recommended. Type 'quit' to exit.]")
            continue
 
        print(f"Assistant:\n{response}\n")
 
        # Check if we should generate the SRS
        if manager._should_generate_srs(user_input, state):
            _print_coverage_status(state)
            print("\n[Generating SRS document...]")
            try:
                srs_path = manager.finalize_session(state, logger)
                print(f"\n✅ SRS generated successfully: {srs_path}")
                print(f"   Session log: {logger.log_path}")
            except Exception as e:
                print(f"[ERROR] SRS generation failed: {e}")
            break
 
    print("\n[Session ended]")
 
 
# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------
 
if __name__ == "__main__":
    import argparse
 
    parser = argparse.ArgumentParser(
        description="RE Assistant — Iteration 2 Prototype v0.1"
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "stub", "ollama"],
        default="openai",
        help="LLM provider (default: openai)",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="Model name (for OpenAI provider)",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help="Directory for session logs",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for SRS output",
    )
    args = parser.parse_args()
 
    run_session(
        provider_name=args.provider,
        log_dir=args.log_dir,
        output_dir=args.output_dir,
        model=args.model,
    )