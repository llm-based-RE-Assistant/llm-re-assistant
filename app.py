from __future__ import annotations
import argparse
import json
import os
import sys
import uuid
import time
from pathlib import Path
from typing import Optional
sys.path.insert(0, str(Path(__file__).parent))
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from src.components.conversation_manager.conversation_manager import ConversationManager
from src.components.conversation_manager.llm_provider import create_provider
from src.components.conversation_state import ConversationState
from src.components.gap_detector import GapDetector, create_gap_detector
from src.components.system_prompt.prompt_architect import MIN_NFR_PER_CATEGORY
from src.components.system_prompt.utils import PHASE4_SECTIONS
from src.components.domain_discovery.domain_discovery import NFR_CATEGORIES, _label_to_key, DomainSpec
from src.components.domain_discovery.domain_gate import  DomainGate
from src.components.requirement_preprocessor import parse_requirements_file, create_preprocessor

BASE_DIR   = Path(__file__).parent
LOG_DIR    = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "output"
PROJECTS_DIR = BASE_DIR / "projects"

for d in (LOG_DIR, OUTPUT_DIR, PROJECTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=str(BASE_DIR / "static"))
CORS(app)

_sessions: dict[str, dict] = {}

_provider_name: str = "stub"
_provider_kwargs: dict = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session(session_id: str) -> Optional[dict]:
    return _sessions.get(session_id)


def _require_session(session_id: str):
    s = _get_session(session_id)
    if s is None:
        return None, (jsonify({"error": f"Session '{session_id}' not found"}), 404)
    return s, None


def _build_manager(task_type: str = "elicitation") -> ConversationManager:
    return ConversationManager(
        provider=create_provider(_provider_name, **_provider_kwargs),
        log_dir=LOG_DIR,
        output_dir=OUTPUT_DIR,
        task_type=task_type,
    )


def _project_path(project_id: str) -> Path:
    return PROJECTS_DIR / f"{project_id}.json"


def _load_project(project_id: str) -> Optional[dict]:
    p = _project_path(project_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_project(project: dict):
    p = _project_path(project["id"])
    p.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")


def _list_projects() -> list[dict]:
    projects = []
    for f in sorted(PROJECTS_DIR.glob("*.json"), key=lambda x: -x.stat().st_mtime):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            projects.append(data)
        except Exception:
            pass
    return projects


def _build_coverage_payload(state: ConversationState, gap_detector: GapDetector) -> dict:
    """Shared helper for coverage + domain gate payload."""
    post_gap_report = gap_detector.analyse(state)
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
    return post_gap_report, coverage_report


def _is_srs_ready(state: ConversationState) -> bool:
    MAX_TURNS = 60
    if state.turn_count >= MAX_TURNS:
        return True
    nfrs_at_depth = all(
        state.nfr_coverage.get(c, 0) >= MIN_NFR_PER_CATEGORY for c in NFR_CATEGORIES
    )
    domain_gate_ok = (
        state.domain_gate is None or
        not state.domain_gate.seeded or
        state.domain_gate.is_satisfied
    )
    task_type = getattr(state, 'task_type', 'elicitation')
    if task_type == "srs_only":
        # SRS-only: ready once all IEEE sections filled
        return len(state.phase4_sections_covered) >= len(PHASE4_SECTIONS)
    return (nfrs_at_depth and domain_gate_ok and state.functional_count >= 10)


# ---------------------------------------------------------------------------
# Routes — Projects
# ---------------------------------------------------------------------------

@app.route("/api/projects", methods=["GET"])
def list_projects():
    projects = _list_projects()
    # Return lightweight card data
    cards = []
    for p in projects:
        cards.append({
            "id": p.get("id"),
            "name": p.get("name", "Untitled"),
            "description": p.get("description", ""),
            "task_type": p.get("task_type", "elicitation"),
            "created_at": p.get("created_at", ""),
            "updated_at": p.get("updated_at", ""),
            "session_id": p.get("session_id"),
            "req_count": p.get("req_count", 0),
        })
    return jsonify({"projects": cards})


@app.route("/api/projects/create", methods=["POST"])
def create_project():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    description = (body.get("description") or "").strip()
    task_type = body.get("task_type", "elicitation")

    if not name:
        return jsonify({"error": "Project name is required"}), 400
    if task_type not in ("elicitation", "srs_only"):
        return jsonify({"error": "task_type must be 'elicitation' or 'srs_only'"}), 400

    project_id = str(uuid.uuid4())[:12]
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    project = {
        "id": project_id,
        "name": name,
        "description": description,
        "task_type": task_type,
        "created_at": now,
        "updated_at": now,
        "session_id": None,
        "req_count": 0,
        "srs_path": None,
    }
    _save_project(project)
    return jsonify({"project": project})


@app.route("/api/projects/<project_id>", methods=["GET"])
def get_project(project_id: str):
    p = _load_project(project_id)
    if not p:
        return jsonify({"error": "Project not found"}), 404
    return jsonify({"project": p})


@app.route("/api/projects/<project_id>", methods=["PUT"])
def update_project(project_id: str):
    p = _load_project(project_id)
    if not p:
        return jsonify({"error": "Project not found"}), 404
    body = request.get_json(silent=True) or {}
    if "name" in body:
        p["name"] = body["name"].strip()
    if "description" in body:
        p["description"] = body["description"].strip()
    p["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _save_project(p)
    return jsonify({"project": p})


@app.route("/api/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id: str):
    p = _project_path(project_id)
    if p.exists():
        p.unlink()
    return jsonify({"deleted": project_id})


# ---------------------------------------------------------------------------
# Routes — Session lifecycle
# ---------------------------------------------------------------------------

@app.route("/api/session/start", methods=["POST"])
def start_session():
    body = request.get_json(silent=True) or {}
    gap_detection_enabled = body.get("gap_detection", True)
    task_type = body.get("task_type", "elicitation")
    project_id = body.get("project_id")

    if task_type not in ("elicitation", "srs_only"):
        task_type = "elicitation"

    try:
        manager = _build_manager(task_type=task_type)
    except Exception as e:
        return jsonify({"error": f"Could not initialise LLM provider: {e}"}), 500

    session_id, state, logger, template = manager.start_session()
    gap_detector = create_gap_detector(enabled=gap_detection_enabled)

    if state.domain_gate is None:
        state.domain_gate = DomainGate()

    _sessions[session_id] = {
        "manager":      manager,
        "state":        state,
        "logger":       logger,
        "template":     template,
        "gap_detector": gap_detector,
        "srs_path":     None,
        "gap_detection_enabled": gap_detection_enabled,
        "task_type":    task_type,
        "project_id":   project_id,
    }

    # Update project with session_id
    if project_id:
        p = _load_project(project_id)
        if p:
            p["session_id"] = session_id
            p["task_type"] = task_type
            p["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _save_project(p)
            # Use project name/description for context
            if p.get("name"):
                state.project_name = p["name"]
                state.project_name_needs_llm = False
            if p.get("description"):
                state.project_description = p.get("description", "")

    if task_type == "elicitation":
        opening = (
            "Hello! I'm your Requirements Engineering assistant. I'll help you build a complete, "
            "structured Software Requirements Specification (SRS) following IEEE 830-1998 standards.\n\n"
            "To get started, please describe the software system you want to build — "
            "its main purpose, who will use it, and any key features you have in mind."
        )
    else:
        opening = (
            "Hello! I can see you've uploaded your requirements list. I'll now help you complete "
            "the IEEE 830-1998 Software Requirements Specification by gathering the remaining "
            "documentation sections (scope, user classes, operating environment, interfaces, etc.).\n\n"
            "First, can you briefly confirm what this system is and who the primary users are?"
        )

    return jsonify({
        "session_id":      session_id,
        "opening_message": opening,
        "gap_detection":   gap_detection_enabled,
        "provider":        _provider_name,
        "task_type":       task_type,
    })


@app.route("/api/session/upload_requirements", methods=["POST"])
def upload_requirements():
    """
    Upload a .txt or .json requirements file.
    Preprocesses with LLM: quality check, rewrite, assign type+category.
    Injects into session state and seeds domain gate.
    """
    body = request.get_json(silent=True) or {}
    session_id = body.get("session_id", "")
    filename = body.get("filename", "requirements.txt")
    content = body.get("content", "")  # file content as string

    if not content:
        return jsonify({"error": "No file content provided"}), 400

    session, err = _require_session(session_id)
    if err:
        return err

    state: ConversationState = session["state"]
    manager: ConversationManager = session["manager"]
    logger = session["logger"]

    # Parse file
    raw_reqs, parse_error = parse_requirements_file(content, filename)
    if parse_error:
        return jsonify({"error": parse_error}), 400

    if not raw_reqs:
        return jsonify({"error": "No requirements found in file"}), 400

    # LLM preprocessing
    preprocessor = create_preprocessor(manager.provider)
    project_ctx = f"{state.project_name}: {getattr(state, 'project_description', '')}"
    result = preprocessor.process(raw_reqs, project_context=project_ctx)

    if result.error:
        return jsonify({"error": result.error}), 500

    # Inject into session state
    injected = manager.inject_requirements(result.requirements, state, logger)

    # Seed domain gate from discovered categories
    manager.seed_domains_from_preprocessed(result.requirements, state)

    # Update project req count
    project_id = session.get("project_id")
    if project_id:
        p = _load_project(project_id)
        if p:
            p["req_count"] = state.total_requirements
            p["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _save_project(p)

    # Build domain gate response
    gate_status = {}
    gate_labels = {}
    if state.domain_gate and state.domain_gate.seeded:
        gate_status = {k: v.status for k, v in state.domain_gate.domains.items()}
        gate_labels = {k: v.label for k, v in state.domain_gate.domains.items()}

    return jsonify({
        "session_id":     session_id,
        "injected":       injected,
        "total_input":    result.total_input,
        "total_output":   result.total_output,
        "rewritten":      result.rewritten_count,
        "split":          result.split_count,
        "domains_found":  result.domains_found,
        "nfr_cats_found": result.nfr_categories_found,
        "functional_count": state.functional_count,
        "nfr_count":      state.nonfunctional_count,
        "domain_gate_status": gate_status,
        "domain_gate_labels": gate_labels,
        "requirements_preview": [r.to_dict() for r in result.requirements[:20]],
    })


@app.route("/api/session/turn", methods=["POST"])
def send_turn():
    body = request.get_json(silent=True) or {}
    session_id   = body.get("session_id", "")
    user_message = body.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "message is required"}), 400

    session, err = _require_session(session_id)
    if err:
        return err

    state: ConversationState     = session["state"]
    manager: ConversationManager = session["manager"]
    logger                       = session["logger"]
    gap_detector: GapDetector    = session["gap_detector"]

    if state.session_complete:
        return jsonify({"error": "Session complete. Generate SRS or start a new session."}), 400

    try:
        assistant_reply = manager.send_turn(user_message, state, logger)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    post_gap_report, coverage_report = _build_coverage_payload(state, gap_detector)
    srs_ready = _is_srs_ready(state)

    # Current elicitation phase
    current_phase = manager._architect.get_current_phase(state)

    # Update project req count
    project_id = session.get("project_id")
    if project_id:
        p = _load_project(project_id)
        if p:
            p["req_count"] = state.total_requirements
            p["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _save_project(p)

    return jsonify({
        "session_id":      session_id,
        "assistant_reply": assistant_reply,
        "turn_id":         state.turn_count,
        "gap_report":      post_gap_report.to_dict(),
        "coverage_report": coverage_report,
        "srs_ready":       srs_ready,
        "current_phase":   current_phase,
        "task_type":       session.get("task_type", "elicitation"),
    })


@app.route("/api/session/status", methods=["GET"])
def session_status():
    session_id = request.args.get("session_id", "")
    session, err = _require_session(session_id)
    if err:
        return err
    state: ConversationState = session["state"]
    gap_detector: GapDetector = session["gap_detector"]
    gap_report = gap_detector.analyse(state)
    coverage_report = state.get_coverage_report()
    return jsonify({
        "session_id":       session_id,
        "turn_count":       state.turn_count,
        "session_complete": state.session_complete,
        "coverage_report":  coverage_report,
        "gap_report":       gap_report.to_dict(),
        "gap_detection":    session["gap_detection_enabled"],
        "task_type":        session.get("task_type", "elicitation"),
        "current_phase":    session["manager"]._architect.get_current_phase(state),
    })


@app.route("/api/session/generate_srs", methods=["POST"])
def generate_srs():
    body = request.get_json(silent=True) or {}
    session_id = body.get("session_id", "")
    session, err = _require_session(session_id)
    if err:
        return err

    state: ConversationState     = session["state"]
    manager: ConversationManager = session["manager"]
    logger                       = session["logger"]
    task_type = session.get("task_type", "elicitation")

    # For srs_only, lower the bar
    min_reqs = 1 if task_type == "srs_only" else 5
    if state.total_requirements < min_reqs:
        return jsonify({
            "error": f"Not enough requirements (have {state.total_requirements}, need ≥{min_reqs}).",
            "success": False,
        }), 400

    try:
        srs_path = manager.finalize_session(state, logger)
        if srs_path is None:
            return jsonify({"error": "SRS generation returned no output.", "success": False}), 500
        session["srs_path"] = srs_path

        # Save SRS path to project
        project_id = session.get("project_id")
        if project_id:
            p = _load_project(project_id)
            if p:
                p["srs_path"] = str(srs_path)
                p["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                _save_project(p)

        return jsonify({"session_id": session_id, "srs_path": str(srs_path), "success": True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "success": False}), 500


@app.route("/api/session/download_srs", methods=["GET"])
def download_srs():
    session_id = request.args.get("session_id", "")
    session, err = _require_session(session_id)
    if err:
        return err
    srs_path = session.get("srs_path")
    if not srs_path or not Path(srs_path).exists():
        return jsonify({"error": "SRS not yet generated"}), 404
    return send_file(srs_path, as_attachment=True, download_name=Path(srs_path).name)


@app.route("/api/session/download_log", methods=["GET"])
def download_log():
    """
    Download the conversation log JSON file.
    Works for both live sessions (in-memory) and past sessions (reads from logs/ dir).
    """
    session_id = request.args.get("session_id", "")
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    # Try live session first
    live = _get_session(session_id)
    if live:
        log_path = live["logger"].get_log_path()
        if log_path.exists():
            return send_file(str(log_path), as_attachment=True,
                             download_name=log_path.name)

    # Fall back to disk (past session)
    safe_sid = "".join(c for c in session_id if c.isalnum() or c == "-")[:40]
    log_path = LOG_DIR / f"session_{safe_sid}.json"
    if log_path.exists():
        return send_file(str(log_path), as_attachment=True,
                         download_name=log_path.name)

    return jsonify({"error": f"Log for session '{session_id}' not found"}), 404


# ---------------------------------------------------------------------------
# Routes — Domain management
# ---------------------------------------------------------------------------

@app.route("/api/domain/add", methods=["POST"])
def domain_add():
    """Add a custom functional domain to the active session's domain gate."""
    body = request.get_json(silent=True) or {}
    session_id = body.get("session_id", "")
    label = (body.get("label") or "").strip()

    if not label:
        return jsonify({"error": "Domain label is required"}), 400

    session, err = _require_session(session_id)
    if err:
        return err

    state: ConversationState = session["state"]
    if state.domain_gate is None:
        state.domain_gate = DomainGate()

    key = _label_to_key(label)
    if key in state.domain_gate.domains:
        return jsonify({"error": f"Domain '{label}' already exists"}), 409

    state.domain_gate.domains[key] = DomainSpec(label=label, status="unprobed")
    if not state.domain_gate.seeded:
        state.domain_gate.seeded = True

    return jsonify({
        "added": key,
        "label": label,
        "domain_gate_status":  {k: v.status for k, v in state.domain_gate.domains.items()},
        "domain_gate_labels":  {k: v.label  for k, v in state.domain_gate.domains.items()},
    })


@app.route("/api/domain/update", methods=["PUT"])
def domain_update():
    """Rename a domain."""
    body = request.get_json(silent=True) or {}
    session_id = body.get("session_id", "")
    key = body.get("key", "")
    new_label = (body.get("label") or "").strip()

    if not key or not new_label:
        return jsonify({"error": "key and label are required"}), 400

    session, err = _require_session(session_id)
    if err:
        return err

    state: ConversationState = session["state"]
    if not state.domain_gate or key not in state.domain_gate.domains:
        return jsonify({"error": f"Domain '{key}' not found"}), 404

    state.domain_gate.domains[key].label = new_label
    return jsonify({
        "updated": key,
        "label": new_label,
        "domain_gate_labels": {k: v.label for k, v in state.domain_gate.domains.items()},
    })


@app.route("/api/domain/delete", methods=["DELETE"])
def domain_delete():
    """Delete a domain from the gate."""
    body = request.get_json(silent=True) or {}
    session_id = body.get("session_id", "")
    key = body.get("key", "")

    if not key:
        return jsonify({"error": "key is required"}), 400

    session, err = _require_session(session_id)
    if err:
        return err

    state: ConversationState = session["state"]
    if not state.domain_gate or key not in state.domain_gate.domains:
        return jsonify({"error": f"Domain '{key}' not found"}), 404

    del state.domain_gate.domains[key]
    return jsonify({
        "deleted": key,
        "domain_gate_status": {k: v.status for k, v in state.domain_gate.domains.items()},
        "domain_gate_labels": {k: v.label  for k, v in state.domain_gate.domains.items()},
    })


@app.route("/api/domain/mark_complete", methods=["PUT"])
def domain_mark_complete():
    """Mark a domain as confirmed or excluded by the user."""
    body = request.get_json(silent=True) or {}
    session_id = body.get("session_id", "")
    key = body.get("key", "")
    status = body.get("status", "confirmed")  # "confirmed" | "excluded"

    if status not in ("confirmed", "excluded", "unprobed", "partial"):
        return jsonify({"error": "status must be confirmed, excluded, unprobed, or partial"}), 400

    session, err = _require_session(session_id)
    if err:
        return err

    state: ConversationState = session["state"]
    if not state.domain_gate or key not in state.domain_gate.domains:
        return jsonify({"error": f"Domain '{key}' not found"}), 404

    state.domain_gate.domains[key].status = status
    return jsonify({
        "key": key,
        "status": status,
        "domain_gate_status": {k: v.status for k, v in state.domain_gate.domains.items()},
        "domain_completeness_pct": state.domain_gate.completeness_pct,
    })


# ---------------------------------------------------------------------------
# Routes — Logs
# ---------------------------------------------------------------------------

@app.route("/api/logs", methods=["GET"])
def list_logs():
    """
    Scan the logs/ directory and return metadata for every session log file.

    Query params (all optional):
      active_session_id  — the currently live session; always included even if 0 turns
      project_id         — if supplied, only return logs whose session_id is linked to
                           this project (checks projects/<pid>.json and all project files
                           whose session_id matches). This restricts the list to logs
                           that belong to the current project.
    """
    active_sid  = request.args.get("active_session_id", "")
    project_id  = request.args.get("project_id", "")

    # Build a set of session_ids that belong to this project.
    # A session belongs to the project if:
    #   (a) it IS the active session for the project (project.session_id), OR
    #   (b) its log file contains a session_start event whose project_id matches.
    # For simplicity we use approach (a) — check every project JSON and collect
    # all session_ids that are linked to the requested project_id.
    allowed_sids: set | None = None
    if project_id:
        allowed_sids = set()
        # Always include the active session
        if active_sid:
            allowed_sids.add(active_sid)
        # Walk all project files to find sessions belonging to this project
        for pf in PROJECTS_DIR.glob("*.json"):
            try:
                pdata = json.loads(pf.read_text(encoding="utf-8"))
            except Exception:
                continue
            if pdata.get("id") == project_id and pdata.get("session_id"):
                allowed_sids.add(pdata["session_id"])

    logs_meta = []
    for log_file in sorted(LOG_DIR.glob("session_*.json"),
                           key=lambda p: -p.stat().st_mtime):
        try:
            raw = json.loads(log_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not isinstance(raw, list):
            continue

        # Extract session_id from filename: session_<sid>.json
        sid = log_file.stem.replace("session_", "", 1)

        # Count turn events and collect req ids
        turn_count = 0
        req_ids_seen: set = set()
        project_name = "Unknown Project"
        started_at = None
        updated_at = None

        for entry in raw:
            ts = entry.get("timestamp")
            if ts:
                if started_at is None:
                    started_at = ts
                updated_at = ts

            evt = entry.get("event_type", "")
            data = entry.get("data", {})

            if evt == "turn":
                turn_count += 1

            if evt == "session_start":
                pass  # project_name extracted from session_end/turn events below

            if evt in ("session_end", "turn"):
                # Grab project name from coverage report or turn data
                cr = data.get("coverage_report") or {}
                if cr.get("project_name") and cr["project_name"] != "Unknown Project":
                    project_name = cr["project_name"]
                # Count requirements from session_end snapshot
                if evt == "session_end" and "total_requirements" in cr:
                    req_ids_seen = set(range(cr["total_requirements"]))  # use count as proxy

            if evt == "requirements_injected":
                # uploaded reqs session
                cnt = data.get("count", 0)
                if cnt:
                    req_ids_seen |= set(range(cnt))

        # Also try to read req count from the live in-memory session if available
        live_session = _sessions.get(sid)
        if live_session:
            live_state = live_session.get("state")
            if live_state:
                turn_count = live_state.turn_count
                req_count = live_state.total_requirements
                project_name = live_state.project_name
            else:
                req_count = len(req_ids_seen)
        else:
            req_count = len(req_ids_seen)

        # Filter by project: skip logs not belonging to the current project
        if allowed_sids is not None and sid not in allowed_sids:
            continue

        # Skip zero-turn logs that are not the active session
        if turn_count == 0 and sid != active_sid:
            continue

        logs_meta.append({
            "session_id":   sid,
            "turn_count":   turn_count,
            "req_count":    req_count,
            "project_name": project_name,
            "started_at":   started_at,
            "updated_at":   updated_at,
            "filename":     log_file.name,
            "is_active":    sid == active_sid,
        })

    # Sort: active first, then by updated_at descending
    logs_meta.sort(key=lambda x: (not x["is_active"], -(x["updated_at"] or 0)))

    return jsonify({"logs": logs_meta, "total": len(logs_meta)})



@app.route("/api/logs/<session_id>/replay", methods=["GET"])
def replay_log(session_id: str):
    """
    Return the conversation turns from a log file so the UI can render them.

    Response:
      {
        "session_id": "...",
        "project_name": "...",
        "turn_count": N,
        "req_count": N,
        "turns": [
          {"turn_id": 1, "user_message": "...", "assistant_message": "..."},
          ...
        ],
        "domain_gate": { ... } | null,
        "nfr_coverage": { ... }
      }
    """
    safe_sid = "".join(c for c in session_id if c.isalnum() or c == "-")[:40]

    # Try live in-memory session first — gives most up-to-date data
    live = _sessions.get(safe_sid)
    if live:
        state: ConversationState = live["state"]
        turns_out = [
            {
                "turn_id":          t.turn_id,
                "user_message":     t.user_message,
                "assistant_message": t.assistant_message,
                "requirements_added": t.requirements_added,
            }
            for t in state.turns
        ]
        gate_out = None
        if state.domain_gate and state.domain_gate.seeded:
            gate_out = {
                k: {"label": v.label, "status": v.status, "req_count": len(v.req_ids)}
                for k, v in state.domain_gate.domains.items()
            }
        return jsonify({
            "session_id":   safe_sid,
            "project_name": state.project_name,
            "turn_count":   state.turn_count,
            "req_count":    state.total_requirements,
            "turns":        turns_out,
            "domain_gate":  gate_out,
            "nfr_coverage": dict(state.nfr_coverage),
            "source":       "live",
        })

    # Fall back to reading the log file from disk
    log_path = LOG_DIR / f"session_{safe_sid}.json"
    if not log_path.exists():
        return jsonify({"error": f"Log for session '{safe_sid}' not found"}), 404

    try:
        raw = json.loads(log_path.read_text(encoding="utf-8"))
    except Exception as e:
        return jsonify({"error": f"Could not read log: {e}"}), 500

    turns_out = []
    project_name = "Unknown Project"
    req_count = 0
    nfr_coverage: dict = {}

    for entry in raw:
        evt  = entry.get("event_type", "")
        data = entry.get("data", {})

        if evt == "turn":
            turns_out.append({
                "turn_id":           data.get("turn_id", len(turns_out) + 1),
                "user_message":      data.get("user_message", ""),
                "assistant_message": data.get("assistant_message", ""),
                "requirements_added": [],
            })
            # Try to pick up project name from coverage report inside turn
            cr = data.get("gap_report") or {}
            if cr.get("project_name") and cr["project_name"] != "Unknown Project":
                project_name = cr["project_name"]

        if evt == "session_end":
            cr = data.get("coverage_report") or data or {}
            if cr.get("project_name") and cr["project_name"] != "Unknown Project":
                project_name = cr["project_name"]
            req_count = cr.get("total_requirements", req_count)
            nfr_coverage = cr.get("nfr_coverage") or cr.get("nfr_depth") or {}

        if evt == "requirements_injected":
            req_count = max(req_count, data.get("count", 0))

    return jsonify({
        "session_id":   safe_sid,
        "project_name": project_name,
        "turn_count":   len(turns_out),
        "req_count":    req_count,
        "turns":        turns_out,
        "domain_gate":  None,
        "nfr_coverage": nfr_coverage,
        "source":       "disk",
    })


@app.route("/api/logs/<session_id>/download", methods=["GET"])
def download_log_by_id(session_id: str):
    """Download any log file by session_id directly (no active session required)."""
    # Sanitise — session_ids are 8-char hex strings
    safe_sid = "".join(c for c in session_id if c.isalnum() or c == "-")[:40]
    log_path = LOG_DIR / f"session_{safe_sid}.json"
    if not log_path.exists():
        return jsonify({"error": f"Log for session '{safe_sid}' not found"}), 404
    return send_file(str(log_path), as_attachment=True, download_name=log_path.name)


# ---------------------------------------------------------------------------
# Routes — Utility
# ---------------------------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "provider": _provider_name, "version": "iteration-9"})


@app.route("/", methods=["GET"])
def index():
    ui_path = Path(__file__).parent / "index.html"
    if ui_path.exists():
        return send_file(str(ui_path))
    return "<h1>RE Assistant API</h1><p>UI not found.</p>"


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
    parser = argparse.ArgumentParser(description="RE Assistant Web UI — Iteration 9")
    parser.add_argument("--provider", choices=["openai", "stub", "ollama"], default="openai")
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    _provider_name = args.provider
    if args.provider in ("openai", "ollama"):
        _provider_kwargs = {"model": args.model}

    print(f"\n{'═'*60}")
    print(f"  RE Assistant — Iteration 9 | University of Hildesheim")
    print(f"  http://{args.host}:{args.port}")
    print(f"  LLM: {_provider_name}  Model: {_provider_kwargs.get('model','N/A')}")
    print(f"  Projects dir: {PROJECTS_DIR}")
    print(f"{'═'*60}\n")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()