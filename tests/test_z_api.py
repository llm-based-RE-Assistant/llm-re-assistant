"""
Integration tests for the Flask REST API (app.py).

Uses Flask's built-in test client with the stub LLM provider — no real API
key or network calls are needed.

Tests cover:
- GET  /api/health
- GET  /api/projects
- POST /api/projects/create (valid, missing name, invalid task_type)
- GET  /api/projects/<id>   (found, not found)
- PUT  /api/projects/<id>   (update name/description)
- DELETE /api/projects/<id>
- POST /api/session/start   (elicitation, gap_detection flag)
- GET  /api/session/status
- POST /api/session/turn
"""

import pytest
import sys
import json
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Remove ALL stub modules AND any cached app/src imports so that when
# test_api.py runs after other test files, it gets fresh real imports.
_MODS_TO_CLEAR = [m for m in list(sys.modules.keys())
                  if m == "app" or m.startswith("src.")]
for _mod in _MODS_TO_CLEAR:
    sys.modules.pop(_mod, None)

# Point the app at a temp directory so tests don't pollute the real project

@pytest.fixture(scope="session", autouse=True)
def _tmp_dirs(tmp_path_factory):
    """Redirect logs/, output/, projects/ to temp dirs for the test session."""
    base = tmp_path_factory.mktemp("re_assistant_test")
    for subdir in ("logs", "output", "projects"):
        (base / subdir).mkdir()
    # Patch app-level path constants before importing app
    import app as _app_mod
    _app_mod.LOG_DIR     = base / "logs"
    _app_mod.OUTPUT_DIR  = base / "output"
    _app_mod.PROJECTS_DIR = base / "projects"
    yield base


# App fixture

@pytest.fixture(scope="session")
def flask_app():
    """Return the Flask app configured for testing with the stub provider."""
    import app as _app_mod
    _app_mod._provider_name   = "stub"
    _app_mod._provider_kwargs = {}
    _app_mod.app.config["TESTING"] = True
    return _app_mod.app


@pytest.fixture
def client(flask_app):
    """Return a test client."""
    with flask_app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_sessions(flask_app):
    """Clear in-memory sessions between tests to avoid cross-test bleed."""
    import app as _app_mod
    _app_mod._sessions.clear()
    yield
    _app_mod._sessions.clear()


# Helpers

def _post(client, url, body=None):
    return client.post(url, json=body or {}, content_type="application/json")


def _create_project(client, name="Test Project", task_type="elicitation"):
    return _post(client, "/api/projects/create",
                 {"name": name, "task_type": task_type})


def _start_session(client, project_id=None, gap_detection=True, task_type="elicitation"):
    body = {"gap_detection": gap_detection, "task_type": task_type}
    if project_id:
        body["project_id"] = project_id
    return _post(client, "/api/session/start", body)


# /api/health

class TestHealth:

    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"

    def test_health_returns_provider(self, client):
        resp = client.get("/api/health")
        data = resp.get_json()
        assert "provider" in data

    def test_health_returns_version(self, client):
        resp = client.get("/api/health")
        data = resp.get_json()
        assert "version" in data


# /api/projects

class TestProjects:

    def test_list_projects_empty(self, client):
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "projects" in data
        assert isinstance(data["projects"], list)

    def test_create_project_success(self, client):
        resp = _create_project(client, "Smart Home System")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "project" in data
        assert data["project"]["name"] == "Smart Home System"

    def test_create_project_has_id(self, client):
        resp = _create_project(client)
        data = resp.get_json()
        assert "id" in data["project"]
        assert len(data["project"]["id"]) > 0

    def test_create_project_missing_name_returns_400(self, client):
        resp = _post(client, "/api/projects/create", {"task_type": "elicitation"})
        assert resp.status_code == 400

    def test_create_project_invalid_task_type_returns_400(self, client):
        resp = _post(client, "/api/projects/create",
                     {"name": "Test", "task_type": "invalid"})
        assert resp.status_code == 400

    def test_create_project_srs_only_task_type(self, client):
        resp = _create_project(client, "Upload Project", task_type="srs_only")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["project"]["task_type"] == "srs_only"

    def test_get_project_found(self, client):
        create_resp = _create_project(client, "Library System")
        project_id = create_resp.get_json()["project"]["id"]
        resp = client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["project"]["name"] == "Library System"

    def test_get_project_not_found_returns_404(self, client):
        resp = client.get("/api/projects/nonexistent-id-12345")
        assert resp.status_code == 404

    def test_update_project_name(self, client):
        create_resp = _create_project(client, "Old Name")
        project_id = create_resp.get_json()["project"]["id"]
        resp = client.put(
            f"/api/projects/{project_id}",
            json={"name": "New Name"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["project"]["name"] == "New Name"

    def test_update_project_not_found_returns_404(self, client):
        resp = client.put(
            "/api/projects/nonexistent-id",
            json={"name": "New Name"},
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_delete_project(self, client):
        create_resp = _create_project(client, "To Delete")
        project_id = create_resp.get_json()["project"]["id"]
        resp = client.delete(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["deleted"] == project_id

    def test_delete_project_then_get_returns_404(self, client):
        create_resp = _create_project(client, "Temporary")
        project_id = create_resp.get_json()["project"]["id"]
        client.delete(f"/api/projects/{project_id}")
        resp = client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 404

    def test_list_projects_after_create(self, client):
        _create_project(client, "Alpha Project")
        _create_project(client, "Beta Project")
        resp = client.get("/api/projects")
        data = resp.get_json()
        names = [p["name"] for p in data["projects"]]
        assert "Alpha Project" in names
        assert "Beta Project" in names


# /api/session/start

class TestSessionStart:

    def test_start_session_returns_session_id(self, client):
        resp = _start_session(client)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "session_id" in data
        assert len(data["session_id"]) > 0

    def test_start_session_returns_opening_message(self, client):
        resp = _start_session(client)
        data = resp.get_json()
        assert "opening_message" in data
        assert isinstance(data["opening_message"], str)

    def test_start_session_returns_task_type(self, client):
        resp = _start_session(client, task_type="elicitation")
        data = resp.get_json()
        assert data.get("task_type") == "elicitation"

    def test_start_session_gap_detection_true(self, client):
        resp = _start_session(client, gap_detection=True)
        data = resp.get_json()
        assert data.get("gap_detection") is True

    def test_start_session_gap_detection_false(self, client):
        resp = _start_session(client, gap_detection=False)
        data = resp.get_json()
        assert data.get("gap_detection") is False

    def test_start_session_provider_in_response(self, client):
        resp = _start_session(client)
        data = resp.get_json()
        assert "provider" in data


# /api/session/status

class TestSessionStatus:

    def test_status_returns_200_for_valid_session(self, client):
        start_resp = _start_session(client)
        session_id = start_resp.get_json()["session_id"]
        resp = client.get(f"/api/session/status?session_id={session_id}")
        assert resp.status_code == 200

    def test_status_contains_coverage_report(self, client):
        start_resp = _start_session(client)
        session_id = start_resp.get_json()["session_id"]
        resp = client.get(f"/api/session/status?session_id={session_id}")
        data = resp.get_json()
        assert "coverage_report" in data

    def test_status_invalid_session_returns_404(self, client):
        resp = client.get("/api/session/status?session_id=nonexistent-session-id")
        assert resp.status_code == 404

    def test_status_missing_session_id_returns_400(self, client):
        resp = client.get("/api/session/status")
        assert resp.status_code in (400, 404)


# /api/session/turn

class TestSessionTurn:

    def test_turn_returns_assistant_reply(self, client):
        start_resp = _start_session(client)
        session_id = start_resp.get_json()["session_id"]
        resp = _post(client, "/api/session/turn",
                     {"session_id": session_id,
                      "message": "I want to build a library management system."})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "assistant_reply" in data
        assert isinstance(data["assistant_reply"], str)

    def test_turn_returns_turn_id(self, client):
        start_resp = _start_session(client)
        session_id = start_resp.get_json()["session_id"]
        resp = _post(client, "/api/session/turn",
                     {"session_id": session_id, "message": "Hello."})
        data = resp.get_json()
        assert "turn_id" in data
        assert data["turn_id"] == 1

    def test_turn_id_increments(self, client):
        start_resp = _start_session(client)
        session_id = start_resp.get_json()["session_id"]
        _post(client, "/api/session/turn",
              {"session_id": session_id, "message": "First message."})
        resp = _post(client, "/api/session/turn",
                     {"session_id": session_id, "message": "Second message."})
        data = resp.get_json()
        assert data["turn_id"] == 2

    def test_turn_returns_gap_report(self, client):
        start_resp = _start_session(client)
        session_id = start_resp.get_json()["session_id"]
        resp = _post(client, "/api/session/turn",
                     {"session_id": session_id, "message": "Hello."})
        data = resp.get_json()
        assert "gap_report" in data

    def test_turn_returns_coverage_report(self, client):
        start_resp = _start_session(client)
        session_id = start_resp.get_json()["session_id"]
        resp = _post(client, "/api/session/turn",
                     {"session_id": session_id, "message": "Hello."})
        data = resp.get_json()
        assert "coverage_report" in data

    def test_turn_returns_current_phase(self, client):
        start_resp = _start_session(client)
        session_id = start_resp.get_json()["session_id"]
        resp = _post(client, "/api/session/turn",
                     {"session_id": session_id, "message": "Hello."})
        data = resp.get_json()
        assert "current_phase" in data

    def test_turn_invalid_session_returns_404(self, client):
        resp = _post(client, "/api/session/turn",
                     {"session_id": "bad-session-id", "message": "Hello."})
        assert resp.status_code == 404

    def test_turn_missing_session_id_returns_400(self, client):
        resp = _post(client, "/api/session/turn", {"message": "Hello."})
        assert resp.status_code in (400, 404)

    def test_turn_missing_message_returns_400(self, client):
        start_resp = _start_session(client)
        session_id = start_resp.get_json()["session_id"]
        resp = _post(client, "/api/session/turn", {"session_id": session_id})
        assert resp.status_code in (400, 422)