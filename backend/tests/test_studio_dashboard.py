"""Dashboard controls use real revisions, preserve history, and enforce project access."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from app.design_studio.local_app import create_local_app
from app.design_studio.discovery import blank_definition
from app.design_studio import approval
from app.schemas.application_definition import ApplicationDefinition, ProjectLifecycle

BASE = "/api/v1/design-studio"


@pytest.fixture
def dashboard_client(monkeypatch):
    monkeypatch.setenv("DESIGN_KNOWLEDGE_SOURCE", "local")
    monkeypatch.setenv("DESIGN_STUDIO_LOCAL_DEV", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    with TemporaryDirectory(prefix="noordveld-studio-dashboard-") as root:
        with TestClient(create_local_app(Path(root) / "studio.sqlite")) as client:
            client.post("/api/v1/auth/login", json={"user_id": "studio-alice"})
            response = client.post(
                BASE + "/projects", json=blank_definition().model_dump(mode="json")
            )
            assert response.status_code == 200, response.text
            yield client, response.json()


def test_recoverable_lifecycle_and_conflicts(dashboard_client):
    client, project = dashboard_client
    endpoint = f"{BASE}/projects/{project['id']}"
    dashboard = client.get(BASE + "/project-dashboard")
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["counts"]["active"] == 1
    row = dashboard.json()["projects"][0]
    assert row["can_edit"] and row["revision"] == 1
    assert row["errors"] >= 0 and row["stage"] == "brief"
    revision = 1
    for action, status in [
        ("archive", "archived"),
        ("trash", "trashed"),
        ("restore", "archived"),
        ("restore", "active"),
    ]:
        response = client.post(
            endpoint + "/manage", json={"expected_revision": revision, "action": action}
        )
        assert response.status_code == 200, response.text
        revision += 1
        assert response.json() == {"id": project["id"], "revision": revision, "status": status}
        assert client.get(BASE + "/project-dashboard").json()["counts"][status] == 1
    assert len(client.get(endpoint + "/history").json()) == revision
    assert (
        client.post(
            endpoint + "/manage", json={"expected_revision": 1, "action": "trash"}
        ).status_code
        == 409
    )
    renamed = client.post(
        endpoint + "/manage",
        json={"expected_revision": revision, "action": "rename", "name": "  Operations Hub  "},
    )
    assert renamed.status_code == 200, renamed.text
    assert client.get(endpoint).json()["metadata"]["name"] == "Operations Hub"
    assert (
        client.post(
            endpoint + "/manage",
            json={"expected_revision": revision + 1, "action": "rename", "name": "   "},
        ).status_code
        == 422
    )
    assert (
        client.get(BASE + "/project-dashboard").json()["activity"][0]["operation"]
        == "project:rename"
    )






