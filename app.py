"""
app.py
======
RE Assistant — Iteration 3 | University of Hildesheim
Web UI Backend (Flask)

Responsibilities
----------------
- Serve the single-page HTML/JS UI
- Expose a REST API consumed by the UI:
    POST /api/session/start         → start a new elicitation session
    POST /api/session/turn          → send a user message, get assistant reply
    GET  /api/session/status        → current coverage + gap report
    POST /api/session/generate_srs  → finalise session, generate SRS
    GET  /api/session/download_srs  → download the generated SRS file
    GET  /api/health                → health check
- Integrate with: ConversationManager, GapDetector, ProactiveQuestionGenerator
- Support ablation study: gap_detection ON/OFF via query param

Architecture
------------
  Browser ←→ Flask REST API ←→ ConversationManager
                              ↓
                          GapDetector
                              ↓
                     ProactiveQuestionGenerator
                              ↓
                          PromptArchitect (context injection)

Run
---
    pip install flask
    python app.py

    # With a specific LLM provider:
    OPENAI_API_KEY=sk-... python app.py --provider openai
    python app.py --provider stub    # for testing without API key
    python app.py --provider ollama  # local Ollama
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

# Ensure src modules are importable when running from project root
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

from src.components.conversation_manager import ConversationManager, create_provider, StubProvider
from src.components.conversation_state import ConversationState
from src.components.gap_detector import GapDetector, create_gap_detector
from src.components.question_generator import ProactiveQuestionGenerator, QuestionTracker, create_question_generator


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

BASE_DIR   = Path(__file__).parent.parent
LOG_DIR    = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "output"

LOG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=str(Path(__file__).parent / "static"))
CORS(app)  # Allow cross-origin for local dev

# ---------------------------------------------------------------------------
# In-memory session store (keyed by session_id)
# In production this would be Redis or a database.
# ---------------------------------------------------------------------------

_sessions: dict[str, dict] = {}


def _get_session(session_id: str) -> Optional[dict]:
    return _sessions.get(session_id)


def _require_session(session_id: str):
    s = _get_session(session_id)
    if s is None:
        return None, (jsonify({"error": f"Session '{session_id}' not found"}), 404)
    return s, None


# ---------------------------------------------------------------------------
# Global components (shared across sessions)
# ---------------------------------------------------------------------------

_provider_name: str = "stub"   # overridden at startup
_provider_kwargs: dict = {}


def _build_manager() -> ConversationManager:
    return ConversationManager(
        provider   = create_provider(_provider_name, **_provider_kwargs),
        log_dir    = LOG_DIR,
        output_dir = OUTPUT_DIR,
    )


# ---------------------------------------------------------------------------
# Routes — Session lifecycle
# ---------------------------------------------------------------------------

@app.route("/api/session/start", methods=["POST"])
def start_session():
    """
    Start a new elicitation session.

    Body (JSON):
        { "gap_detection": true }   # optional; default true
    """
    body = request.get_json(silent=True) or {}
    gap_detection_enabled = body.get("gap_detection", True)

    try:
        manager = _build_manager()
    except Exception as e:
        return jsonify({"error": f"Could not initialise LLM provider: {e}"}), 500

    session_id, state, logger, template = manager.start_session()

    gap_detector = create_gap_detector(enabled=gap_detection_enabled)
    q_generator  = create_question_generator(max_questions_per_turn=2)
    q_tracker    = QuestionTracker()

    _sessions[session_id] = {
        "manager":      manager,
        "state":        state,
        "logger":       logger,
        "template":     template,
        "gap_detector": gap_detector,
        "q_generator":  q_generator,
        "q_tracker":    q_tracker,
        "srs_path":     None,
        "gap_detection_enabled": gap_detection_enabled,
    }

    opening = (
        "Hello! I'm your Requirements Engineering assistant. I'll help you create a complete, "
        "structured Software Requirements Specification (SRS) for your software project.\n\n"
        "To get started, please describe the software system you want to build — "
        "its main purpose, who will use it, and any key features you have in mind."
    )

    return jsonify({
        "session_id":        session_id,
        "opening_message":   opening,
        "gap_detection":     gap_detection_enabled,
        "provider":          _provider_name,
    })


@app.route("/api/session/turn", methods=["POST"])
def send_turn():
    """
    Send one user message and receive the assistant's reply + gap report.

    Body (JSON):
        {
            "session_id": "...",
            "message":    "I want to build a task management app..."
        }
    """
    body = request.get_json(silent=True) or {}
    session_id  = body.get("session_id", "")
    user_message = body.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "message is required"}), 400

    session, err = _require_session(session_id)
    if err:
        return err

    state: ConversationState = session["state"]
    manager: ConversationManager = session["manager"]
    logger = session["logger"]
    gap_detector: GapDetector = session["gap_detector"]
    q_generator: ProactiveQuestionGenerator = session["q_generator"]
    q_tracker: QuestionTracker = session["q_tracker"]

    if state.session_complete:
        return jsonify({"error": "Session already complete. Generate SRS or start a new session."}), 400

    # --- Run gap detection BEFORE calling LLM (to inject directive into prompt) ---
    pre_gap_report = gap_detector.analyse(state)
    q_set = q_generator.generate(pre_gap_report, state, q_tracker)

    # Inject proactive question directive into manager's prompt architect
    if q_set.has_questions and hasattr(manager, "_prompt_architect"):
        injection = q_generator.build_injection_text(q_set)
        manager._prompt_architect.extra_context = injection

    # --- Send turn to LLM ---
    try:
        assistant_reply = manager.send_turn(user_message, state, logger)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    # --- Run gap detection AFTER turn to report updated state ---
    post_gap_report = gap_detector.analyse(state)

    # --- Check if SRS should be generated ---
    should_generate = manager._should_generate_srs(user_message, state)
    srs_ready = False
    if should_generate:
        try:
            srs_path = manager.finalize_session(state, logger)
            session["srs_path"] = srs_path
            srs_ready = True
        except Exception as e:
            pass  # SRS generation failure is non-fatal for the API response

    return jsonify({
        "session_id":      session_id,
        "assistant_reply": assistant_reply,
        "turn_id":         state.turn_count,
        "srs_ready":       srs_ready,
        "gap_report":      post_gap_report.to_dict(),
        "follow_up_questions": [q.to_dict() for q in q_set.questions],
        "coverage_pct":    post_gap_report.coverage_pct,
    })


@app.route("/api/session/status", methods=["GET"])
def session_status():
    """
    Return current coverage status and gap report for the session.

    Query params:
        session_id=...
    """
    session_id = request.args.get("session_id", "")
    session, err = _require_session(session_id)
    if err:
        return err

    state: ConversationState = session["state"]
    gap_detector: GapDetector = session["gap_detector"]
    gap_report = gap_detector.analyse(state)

    coverage_report = state.get_coverage_report()

    return jsonify({
        "session_id":        session_id,
        "turn_count":        state.turn_count,
        "session_complete":  state.session_complete,
        "coverage_report":   coverage_report,
        "gap_report":        gap_report.to_dict(),
        "gap_detection":     session["gap_detection_enabled"],
    })


@app.route("/api/session/generate_srs", methods=["POST"])
def generate_srs():
    """
    Manually trigger SRS generation for a session.

    Body (JSON):
        { "session_id": "..." }
    """
    body = request.get_json(silent=True) or {}
    session_id = body.get("session_id", "")

    session, err = _require_session(session_id)
    if err:
        return err

    state: ConversationState = session["state"]
    manager: ConversationManager = session["manager"]
    logger = session["logger"]

    try:
        srs_path = manager.finalize_session(state, logger)
        session["srs_path"] = srs_path
        return jsonify({
            "session_id": session_id,
            "srs_path":   str(srs_path),
            "success":    True,
        })
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500


@app.route("/api/session/download_srs", methods=["GET"])
def download_srs():
    """
    Download the generated SRS file.

    Query params:
        session_id=...
    """
    session_id = request.args.get("session_id", "")
    session, err = _require_session(session_id)
    if err:
        return err

    srs_path = session.get("srs_path")
    if not srs_path or not Path(srs_path).exists():
        return jsonify({"error": "SRS not yet generated"}), 404

    return send_file(
        srs_path,
        as_attachment=True,
        download_name=Path(srs_path).name,
    )


# ---------------------------------------------------------------------------
# Routes — Utility
# ---------------------------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "provider": _provider_name})


@app.route("/", methods=["GET"])
def index():
    """Serve the main index.html file for the UI."""
    ui_path = Path(__file__).parent / "index.html"
    if ui_path.exists():
        return send_file(str(ui_path))
    return "<h1>RE Assistant API</h1><p>UI not found. Run with index.html in the same directory.</p>"


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    global _provider_name, _provider_kwargs

    parser = argparse.ArgumentParser(description="RE Assistant Web UI — Iteration 3")
    parser.add_argument("--provider", choices=["openai", "stub", "ollama"], default="openai",
                        help="LLM provider (default: stub)")
    parser.add_argument("--model", default="gpt-4o", help="Model name (default: gpt-4o)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    _provider_name = args.provider
    if args.provider == "openai":
        _provider_kwargs = {"model": args.model}
    elif args.provider == "ollama":
        _provider_kwargs = {"model": args.model}

    print(f"\n{'═' * 60}")
    print(f"  RE Assistant — Iteration 3 | University of Hildesheim")
    print(f"  Web UI starting on http://{args.host}:{args.port}")
    print(f"  LLM Provider: {_provider_name} Model: {_provider_kwargs.get('model', 'N/A')}")
    print(f"{'═' * 60}\n")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()