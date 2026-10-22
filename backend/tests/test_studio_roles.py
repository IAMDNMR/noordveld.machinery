"""The Design Studio roles, independent approval, isolation between organizations, teams, projects and applications, and the audit of protected
actions. Synthetic people and temporary SQLite only. Builds on the existing directory, gate and invitation flow; nothing here is a second model."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from app.core.roles import PERMISSIONS, Role
from app.design_studio.discovery import blank_definition
from app.design_studio.local_app import create_local_app
from app.design_studio.sqlite_store import SqliteProjectStore, SqliteStudioStore
from app.domain_knowledge.store import SqliteDomainStore
from app.orgs.catalogue import APPLICATIONS
from app.orgs.directory import SqliteOrgDirectory
from app.orgs.permissions import ORG_PERMISSIONS, ORG_ROLES

W = "/api/v1/workspace"
S = "/api/v1/design-studio"
ORG, OTHER = "org_acme", "org_beta"


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv("DESIGN_STUDIO_LOCAL_DEV", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    with TemporaryDirectory(prefix="noordveld-studio-") as root:
        path = Path(root) / "studio.sqlite"
        directory = SqliteOrgDirectory(path.with_name("orgs.sqlite"))
        for org, name in ((ORG, "Acme Machinery (synthetic)"), (OTHER, "Beta Freight (synthetic)")):
            directory.seed_organization(org, name)  # least-privilege default policy
        for user, org, role in (("studio-alice", ORG, "project_owner"), ("studio-bob", ORG, "business_approver"), ("studio-carol", ORG, "org_admin"), ("studio-dave", ORG, "designer"),
                                ("studio-frank", ORG, "reviewer"), ("studio-gina", ORG, "project_owner"), ("studio-gina", ORG, "business_approver"),
                                ("studio-erin", OTHER, "org_admin")):
            directory.seed_membership(user, org, role)
        persistence = (SqliteStudioStore(path), SqliteProjectStore(path), SqliteDomainStore(path.with_name("domain.sqlite")), directory)
        with TestClient(create_local_app(path, persistence=persistence)) as client:
            yield client, directory


def login(client, user: str):
    assert client.post("/api/v1/auth/login", json={"user_id": user}).status_code == 200


def org(headers_org: str = ORG) -> dict:
    return {"X-Org-Id": headers_org}


def create_project(client, project_id: str, org_id: str = ORG):
    raw = blank_definition().model_dump(mode="json")
    raw["id"], raw["metadata"]["name"] = project_id, project_id
    response = client.post(f"{S}/projects", json=raw, headers=org(org_id))
    assert response.status_code == 200, response.text


def assign(client, project_id: str, subject: str, who: str, level: str):
    response = client.put(f"{W}/organizations/{ORG}/projects/{project_id}/access", json={"subject": subject, "id": who, "level": level})
    assert response.status_code == 200, response.text


def access(client, project_id: str, org_id: str = ORG):
    return client.get(f"{S}/projects/{project_id}/studio/access", headers=org(org_id))


def approve(client, project_id: str, org_id: str = ORG):
    return client.post(f"{S}/projects/{project_id}/approve", json={"expected_revision": 1, "scope": "process"}, headers=org(org_id))


# ── the three Design Studio roles ──

def test_each_studio_role_gets_exactly_its_permissions(world):
    client, _ = world
    login(client, "studio-alice"); create_project(client, "app_roles")
    assign(client, "app_roles", "user", "studio-dave", "editor")
    assign(client, "app_roles", "user", "studio-bob", "reviewer")
    assign(client, "app_roles", "user", "studio-frank", "viewer")
    expected = {  # person: (studio role, edit, generate, review, approve, launch, manage access)
        "studio-alice": (["creator"], True, True, True, False, True, True),   # the creator builds and generates, but cannot approve her own project
        "studio-dave": (["creator"], True, False, False, False, True, False),  # a designer edits; generation is a separate right
        "studio-bob": (["approver"], False, False, True, True, True, False),   # the approver reviews and approves someone else's work
        "studio-frank": (["reviewer"], False, False, False, False, True, False),  # read-only: reads and previews, changes nothing
    }
    for person, (roles, edit, generate, review, approve_, launch, manage) in expected.items():
        login(client, person)
        summary = access(client, "app_roles").json()
        assert summary["studio_roles"] == roles, person
        assert summary["can"] == {"edit": edit, "generate": generate, "review": review, "approve": approve_, "launch": launch, "manage_access": manage}, person
        assert all(isinstance(text, str) and text for text in summary["denied"].values())
    login(client, "studio-dave")
    assert "generation" in access(client, "app_roles").json()["denied"]["generate"].lower()
    login(client, "studio-alice")
    assert "approver role" in access(client, "app_roles").json()["denied"]["approve"], "a creator without the approver role is told what the right is"
    login(client, "studio-gina"); create_project(client, "app_both")  # holds both roles: the reason is independence, not the missing role
    assert "created this project" in access(client, "app_both").json()["denied"]["approve"]
    login(client, "studio-frank")
    assert "read-only" in access(client, "app_roles").json()["denied"]["edit"] or "does not include" in access(client, "app_roles").json()["denied"]["edit"]






# ── independent approval, and who may approve what ──





# ── isolation: organization, team, project, application ──





# ── one person, both journeys ──





# ── audit ──



# ── business roles stay intact and separate ──



