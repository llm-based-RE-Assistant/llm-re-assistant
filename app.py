"""
app.py
======
RE Assistant — Iteration 6 | University of Hildesheim
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
    pip install flask flask-cors
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

# Flat project structure — all modules live next to app.py
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

from src.components.conversation_manager import ConversationManager, create_provider
from src.components.conversation_state import ConversationState
from src.components.gap_detector import GapDetector, create_gap_detector
from src.components.question_generator import ProactiveQuestionGenerator, create_question_generator
from src.components.domain_discovery import DomainGate
from src.components.prompt_architect import MIN_NFR_PER_CATEGORY
from src.components.domain_discovery import NFR_CATEGORIES


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

BASE_DIR   = Path(__file__).parent          # project root (same dir as app.py)
LOG_DIR    = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "output"

LOG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=str(BASE_DIR / "static"))
CORS(app)  # Allow cross-origin for local dev

# ---------------------------------------------------------------------------
# In-memory session store (keyed by session_id)
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

_provider_name: str = "stub"
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

    if state.domain_gate is None:
        state.domain_gate = DomainGate()

    _sessions[session_id] = {
        "manager":      manager,
        "state":        state,
        "logger":       logger,
        "template":     template,
        "gap_detector": gap_detector,
        "q_generator":  q_generator,
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
    session_id   = body.get("session_id", "")
    user_message = body.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "message is required"}), 400

    session, err = _require_session(session_id)
    if err:
        return err

    state: ConversationState   = session["state"]
    manager: ConversationManager = session["manager"]
    logger                      = session["logger"]
    gap_detector: GapDetector   = session["gap_detector"]
    q_generator: ProactiveQuestionGenerator = session["q_generator"]

    if state.session_complete:
        return jsonify({"error": "Session already complete. Generate SRS or start a new session."}), 400

    # Run gap detection BEFORE calling LLM (inject directive into prompt)
    pre_gap_report = gap_detector.analyse(state)
    q_set = q_generator.generate(pre_gap_report, state)

    if q_set.has_questions and hasattr(manager, "_architect"):
        injection = q_generator.build_injection_text(q_set)
        manager._architect.extra_context = injection

    # Send turn to LLM
    try:
        assistant_reply = manager.send_turn(user_message, state, logger)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    # Run gap detection AFTER turn to report updated state
    post_gap_report = gap_detector.analyse(state)

    # IT8: srs_ready — show the Generate SRS button when:
    #   (a) the RE assistant has explicitly offered SRS (all gates satisfied), OR
    #   (b) we hit the turn safety ceiling.
    # We do NOT hard-gate on is_ready_for_srs() here because that would prevent
    # the button appearing during Phase 4. Instead we expose it as soon as the
    # assistant's response contains an offer phrase, or at turn limit.
    MAX_TURNS = 60
    at_turn_limit = state.turn_count >= MAX_TURNS
    nfrs_at_depth = all(
        state.nfr_coverage.get(c, 0) >= MIN_NFR_PER_CATEGORY
        for c in NFR_CATEGORIES
    )
    domain_gate_ok = (
        state.domain_gate is None or
        not state.domain_gate.seeded or
        state.domain_gate.is_satisfied
    )
    srs_ready = (nfrs_at_depth and domain_gate_ok and state.functional_count >= 10) or at_turn_limit

    # Build coverage report with flat domain gate keys the frontend needs
    coverage_report = state.get_coverage_report()
    if state.domain_gate is not None and state.domain_gate.seeded:
        coverage_report["domain_gate_status"] = {
            k: v.status for k, v in state.domain_gate.domains.items()
        }
        coverage_report["domain_gate_labels"] = {
            k: v.label for k, v in state.domain_gate.domains.items()
        }
        coverage_report["domain_completeness_pct"] = state.domain_gate.completeness_pct
    else:
        coverage_report["domain_gate_status"] = {}
        coverage_report["domain_gate_labels"] = {}
        coverage_report["domain_completeness_pct"] = 0

    return jsonify({
        "session_id":          session_id,
        "assistant_reply":     assistant_reply,
        "turn_id":             state.turn_count,
        "gap_report":          post_gap_report.to_dict(),
        "follow_up_questions": [q.to_dict() for q in q_set.questions],
        "coverage_pct":        post_gap_report.coverage_pct,
        "coverage_report":     coverage_report,
        "srs_ready":           srs_ready,
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

    IT8: Generation is always allowed when explicitly requested — we do not
    re-check is_ready_for_srs() here. The RE assistant controls the offer;
    the user presses the button; we generate. Minimum bar: >= 5 functional reqs.
    """
    body = request.get_json(silent=True) or {}
    session_id = body.get("session_id", "")

    session, err = _require_session(session_id)
    if err:
        return err

    state: ConversationState     = session["state"]
    manager: ConversationManager = session["manager"]
    logger                       = session["logger"]

    if state.functional_count < 5:
        return jsonify({
            "error": f"Not enough requirements to generate SRS "
                     f"(have {state.functional_count} functional requirements, need at least 5).",
            "success": False,
        }), 400

    try:
        srs_path = manager.finalize_session(state, logger)
        if srs_path is None:
            return jsonify({"error": "SRS generation returned no output path.", "success": False}), 500
        session["srs_path"] = srs_path
        return jsonify({
            "session_id": session_id,
            "srs_path":   str(srs_path),
            "success":    True,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
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

    parser = argparse.ArgumentParser(description="RE Assistant Web UI — Iteration 8")
    parser.add_argument("--provider", choices=["openai", "stub", "ollama"], default="openai",
                        help="LLM provider (default: openai)")
    parser.add_argument("--model", default="gpt-4o", help="Model name (default: gpt-4o)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    _provider_name = args.provider
    if args.provider in ("openai", "ollama"):
        _provider_kwargs = {"model": args.model}

    print(f"\n{'═' * 60}")
    print(f"  RE Assistant — Iteration 8 | University of Hildesheim")
    print(f"  Web UI starting on http://{args.host}:{args.port}")
    print(f"  LLM Provider: {_provider_name}  Model: {_provider_kwargs.get('model', 'N/A')}")
    print(f"{'═' * 60}\n")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()