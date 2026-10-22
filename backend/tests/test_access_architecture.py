"""Unified access: project-level assignment, teams, application administrators, invitations that carry access, audit, and the
application gate. Synthetic people and temporary SQLite only; nothing here touches a shared database."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.app_access import require_app
from app.api.dependencies import get_orders
from app.core.session import COOKIE, sign
from app.design_studio.discovery import blank_definition
from app.design_studio.local_app import create_local_app, seed_demo_directory
from app.design_studio.sqlite_store import SqliteProjectStore, SqliteStudioStore
from app.domain_knowledge.store import SqliteDomainStore
from app.orgs.directory import DirectoryError, Forbidden, NotFound, SqliteOrgDirectory
from app.services.orders import User
from app.core.roles import Role

W = "/api/v1/workspace"
S = "/api/v1/design-studio"
ORG = "org_acme"


@pytest.fixture
def world(monkeypatch):
    """A local Studio with the demo directory plus an organization (Acme) on the default, least-privilege policy."""
    monkeypatch.setenv("DESIGN_STUDIO_LOCAL_DEV", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    with TemporaryDirectory(prefix="noordveld-studio-") as root:
        path = Path(root) / "studio.sqlite"
        directory = SqliteOrgDirectory(path.with_name("orgs.sqlite"))
        directory.seed_organization(ORG, "Acme Machinery (synthetic)")  # default policy: assigned
        for user, role in (("studio-alice", "project_owner"), ("studio-bob", "business_approver"), ("studio-carol", "org_admin"), ("studio-dave", "designer")):
            directory.seed_membership(user, ORG, role)
        persistence = (SqliteStudioStore(path), SqliteProjectStore(path), SqliteDomainStore(path.with_name("domain.sqlite")), directory)
        with TestClient(create_local_app(path, persistence=persistence)) as client:
            yield client, directory


def login(client, user: str):
    assert client.post("/api/v1/auth/login", json={"user_id": user}).status_code == 200


def create_project(client, project_id: str) -> None:
    raw = blank_definition().model_dump(mode="json")
    raw["id"], raw["metadata"]["name"] = project_id, project_id
    response = client.post(f"{S}/projects", json=raw, headers={"X-Org-Id": ORG})
    assert response.status_code == 200, response.text


def get_project(client, project_id: str):
    return client.get(f"{S}/projects/{project_id}", headers={"X-Org-Id": ORG})


ACT = {"actions": [{"type": "add_requirement", "statement": "Records can be searched.", "priority": "should"}]}


def act(client, project_id: str):
    revision = client.get(f"{S}/projects/{project_id}/studio/state", headers={"X-Org-Id": ORG}).json().get("revision", 1)
    return client.post(f"{S}/projects/{project_id}/studio/act", json={"expected_revision": revision, **ACT}, headers={"X-Org-Id": ORG})


def assign(client, project_id: str, subject: str, subject_id: str, level: str):
    return client.put(f"{W}/organizations/{ORG}/projects/{project_id}/access", json={"subject": subject, "id": subject_id, "level": level})


# ── project-level access ──

def test_a_project_is_reachable_only_by_people_assigned_to_it_and_strangers_learn_nothing(world):
    client, _ = world
    login(client, "studio-alice"); create_project(client, "app_one")
    assert get_project(client, "app_one").status_code == 200, "the creator owns it"
    for person in ("studio-bob", "studio-dave"):
        login(client, person)
        refused = get_project(client, "app_one")
        assert refused.status_code == 404 and refused.json()["error"]["code"] == "project_not_found", "unassigned members cannot tell it exists"
    assert get_project(client, "app_unknown").status_code == 404 and get_project(client, "app_unknown").json() == get_project(client, "app_one").json(), "same answer as for a project that does not exist"
    login(client, "studio-carol")  # the organization administrator administers access; that is not content access
    assert get_project(client, "app_one").status_code == 404
    listing = client.get(f"{W}/organizations/{ORG}/projects/app_one/access")
    assert listing.status_code == 200 and listing.json()["access"] == [{"subject": "user", "id": "studio-alice", "level": "owner"}] and listing.json()["policy"] == "assigned"


def test_levels_grant_exactly_their_capabilities(world):
    client, _ = world
    login(client, "studio-alice"); create_project(client, "app_two")
    assert assign(client, "app_two", "user", "studio-dave", "viewer").status_code == 200
    login(client, "studio-dave")
    assert get_project(client, "app_two").status_code == 200
    forbidden = act(client, "app_two")
    assert forbidden.status_code == 403 and forbidden.json()["error"]["code"] == "project_access_required", "a viewer cannot edit even with the organization's edit permission"
    login(client, "studio-alice")
    assert assign(client, "app_two", "user", "studio-dave", "editor").status_code == 200
    login(client, "studio-dave")
    assert act(client, "app_two").status_code == 200
    # the reviewer level carries approval, not editing; and an editor cannot change who has access
    login(client, "studio-dave")
    assert assign(client, "app_two", "user", "studio-bob", "editor").status_code == 403
    login(client, "studio-alice")
    assert assign(client, "app_two", "user", "studio-bob", "reviewer").status_code == 200
    login(client, "studio-bob")
    assert get_project(client, "app_two").status_code == 200 and act(client, "app_two").status_code == 403








# ── invitations, onboarding and the two journeys ──











# ── the application gate ──

def gated_app(directory: SqliteOrgDirectory) -> TestClient:
    from app.orgs.directory import get_org_directory
    app = FastAPI()
    users = {"studio-frank": User("studio-frank", "Frank", "frank@example.invalid", Role.END_USER), "studio-alice": User("studio-alice", "Alice", "alice@example.invalid", Role.END_USER),
             "studio-gina": User("studio-gina", "Gina", "gina@example.invalid", Role.END_USER)}

    class Orders:
        def user(self, user_id):
            return users.get(user_id or "")

    app.dependency_overrides[get_orders] = lambda: Orders()
    app.dependency_overrides[get_org_directory] = lambda: directory

    @app.get("/shop", dependencies=[Depends(require_app("agentic_shopping"))])
    def read():
        return {"ok": True}

    @app.post("/shop", dependencies=[Depends(require_app("agentic_shopping"))])
    def write():
        return {"ok": True}

    return TestClient(app)




