import base64
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import LEGACY_SECRET, create_app


def token(username: str = "student", role: str = "STUDENT") -> str:
    raw = f"{username}|{role}|{int(time.time()) + 3600}|{LEGACY_SECRET}"
    return base64.b64encode(raw.encode()).decode()


def headers(username: str = "student", role: str = "STUDENT") -> dict[str, str]:
    return {
        "Cookie": f"workshop_session={token(username, role)}",
        "Origin": "http://localhost:4200",
    }


def test_lists_seeded_tasks(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    with TestClient(app) as client:
        response = client.get("/api/tasks", headers=headers())
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_creates_task_and_summary(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            headers=headers(),
            json={"title": "Add tests", "description": "Improve coverage", "status": "TODO", "priority": "HIGH"},
        )
        summary = client.get("/api/summary", headers=headers())
    assert created.status_code == 201
    assert created.json()["owner"] == "student"
    assert summary.json()["total"] == 3


def test_uploads_requirement(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    app = create_app(str(tmp_path / "workshop.db"), str(upload_dir))
    with TestClient(app) as client:
        response = client.post(
            "/api/requirements",
            headers=headers(),
            files={"file": ("requirements.txt", b"Login must be accessible", "text/plain")},
        )
    assert response.status_code == 201
    assert (upload_dir / "requirements.txt").exists()


def test_rejects_invalid_session_cookie(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    with TestClient(app) as client:
        response = client.get("/api/tasks", headers={"Cookie": "workshop_session=invalid"})
    assert response.status_code == 401


def test_rejects_state_change_without_allowed_origin(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    request_headers = headers()
    request_headers.pop("Origin")
    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            headers=request_headers,
            json={"title": "Add tests"},
        )
    assert response.status_code == 403


def test_rejects_state_change_from_untrusted_origin(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    request_headers = headers()
    request_headers["Origin"] = "https://untrusted.example"
    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            headers=request_headers,
            json={"title": "Add tests"},
        )
    assert response.status_code == 403


def test_does_not_accept_legacy_bearer_header(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    with TestClient(app) as client:
        response = client.get(
            "/api/tasks",
            headers={"Authorization": f"Bearer {token()}"},
        )
    assert response.status_code == 401


def test_cors_allows_credentials_only_for_configured_origin(tmp_path: Path) -> None:
    app = create_app(
        str(tmp_path / "workshop.db"),
        str(tmp_path / "uploads"),
        allowed_origin="http://localhost:4200",
    )
    with TestClient(app) as client:
        allowed = client.options(
            "/api/tasks",
            headers={
                "Origin": "http://localhost:4200",
                "Access-Control-Request-Method": "GET",
            },
        )
        rejected = client.options(
            "/api/tasks",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:4200"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in rejected.headers
