"""Organization-scoped identity: roles, invitations, isolation and the workspace. Synthetic people, temporary SQLite only."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from app.design_studio.discovery import blank_definition
from app.design_studio.local_app import create_local_app, seed_demo_directory
from app.orgs.catalogue import APPLICATIONS
from app.orgs.directory import DirectoryError, Forbidden, NoDirectory, NotFound, SqliteOrgDirectory
from app.orgs.permissions import GRANTABLE_BY, ORG_ROLES, PLATFORM_ROLES, SEPARATE_APPROVAL

W = "/api/v1/workspace"
S = "/api/v1/design-studio"
DK = "/api/v1/domain-knowledge"


@pytest.fixture
def directory(tmp_path: Path) -> SqliteOrgDirectory:
    found = SqliteOrgDirectory(tmp_path / "orgs.sqlite")
    seed_demo_directory(found)
    return found


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DESIGN_STUDIO_LOCAL_DEV", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    with TemporaryDirectory(prefix="noordveld-studio-") as root:
        with TestClient(create_local_app(Path(root) / "studio.sqlite")) as test_client:
            yield test_client


def login(client, user):
    assert client.post("/api/v1/auth/login", json={"user_id": user}).status_code == 200


def project(name: str, project_id: str) -> dict:
    raw = blank_definition().model_dump(mode="json")
    raw["id"] = project_id
    raw["metadata"]["name"] = name
    return raw


# ── the permission model itself ──











# ── API enforcement ──





def test_organizations_are_isolated(client):
    login(client, "studio-alice")
    assert client.post(f"{S}/projects", json=project("Noordveld secret", "app_secret")).status_code == 200
    login(client, "studio-gina")  # administrator of ANOTHER organization
    assert client.get(f"{S}/projects").json() == []
    assert client.get(f"{S}/projects/app_secret", headers={"X-Org-Id": "org_harbor"}).status_code == 404
    assert client.get(f"{S}/projects/app_secret", headers={"X-Org-Id": "org_noordveld"}).status_code == 403, "she is not a member there, whatever header she sends"
    assert client.post(f"{S}/projects", json=project("hijack", "app_secret"), headers={"X-Org-Id": "org_harbor"}).status_code == 409
    mine = client.post(f"{S}/projects", json=project("Harbor project", "app_harbor"), headers={"X-Org-Id": "org_harbor"})
    assert mine.status_code == 200
    login(client, "studio-alice")
    assert [item["id"] for item in client.get(f"{S}/projects").json()] == ["app_secret"]
    assert client.get(f"{S}/projects/app_harbor").status_code == 404
    assert client.get(f"{W}?org=org_harbor").status_code == 404, "the workspace of an organization you do not belong to does not exist for you"








