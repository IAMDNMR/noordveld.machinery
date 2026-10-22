"""The public Design Studio demo on a deployed site: anyone may open it without signing in, each browser gets its own private
workspace, and the switch is off unless explicitly set. Drives the real app as a Vercel deployment would see it."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routes.design_studio import get_design_store, get_project_store
from app.core.config import get_settings
from app.design_studio.discovery import blank_definition
from app.design_studio.releases import ReleaseStore, get_release_store
from app.design_studio.sqlite_store import SqliteProjectStore, SqliteStudioStore
from app.design_studio.visitors import INSTANCE_PER_HOUR, MAX_PROJECTS, VISITOR_PER_HOUR, check_rate, new_visitor_id
from app.main import create_app

SITE = "https://noordveldmachinery.vercel.app"


def deployed_app(monkeypatch, tmp_path, *, public: bool):
    for name, value in {
        "VERCEL": "1",
        "APP_ENV": "production",
        "SESSION_SECRET": "x" * 40,
        "DESIGN_KNOWLEDGE_SOURCE": "local",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("DESIGN_STUDIO_LOCAL_DEV", raising=False)
    if public:
        monkeypatch.setenv("DESIGN_STUDIO_PUBLIC_DEMO", "1")
    else:
        monkeypatch.delenv("DESIGN_STUDIO_PUBLIC_DEMO", raising=False)
    get_settings.cache_clear()
    app = create_app()
    database = tmp_path / "studio.sqlite"
    app.dependency_overrides[get_design_store] = lambda: SqliteStudioStore(database)
    projects = SqliteProjectStore(database)
    from app.design_studio.visitors import LimitedProjects

    app.dependency_overrides[get_project_store] = lambda: LimitedProjects(projects)
    releases = ReleaseStore(tmp_path / "releases.sqlite")
    app.dependency_overrides[get_release_store] = lambda: releases
    return app


def test_the_switch_is_off_by_default_so_a_deployed_studio_stays_closed(monkeypatch, tmp_path):
    with TestClient(deployed_app(monkeypatch, tmp_path, public=False), base_url=SITE) as client:
        assert client.post("/api/v1/studio-session/demo").status_code == 404
        assert client.get("/api/v1/design-studio/projects").status_code == 503


def test_each_visitor_gets_a_private_workspace_with_no_sign_in_and_cannot_reach_anything_else(monkeypatch, tmp_path):
    app = deployed_app(monkeypatch, tmp_path, public=True)
    with TestClient(app, base_url=SITE) as first, TestClient(app, base_url=SITE) as second:
        me = first.post("/api/v1/studio-session/demo")
        assert me.status_code == 200 and me.json()["id"].startswith("visitor-") and me.json()["role"] == "END_USER"
        assert first.post("/api/v1/studio-session/demo").json()["id"] == me.json()["id"], "the same browser keeps its workspace"
        assert second.post("/api/v1/studio-session/demo").json()["id"] != me.json()["id"]

        body = blank_definition().model_dump(mode="json")
        for _ in range(MAX_PROJECTS):
            created = first.post("/api/v1/design-studio/projects", json={**body, "id": f"app_{new_visitor_id()[-12:]}"})
            assert created.status_code == 200, created.text
        over = first.post("/api/v1/design-studio/projects", json={**body, "id": "app_overlimit0001"})
        assert over.status_code == 409 and over.json()["error"]["code"] == "demo_project_limit"

        assert len(first.get("/api/v1/design-studio/projects").json()) == MAX_PROJECTS
        assert second.get("/api/v1/design-studio/projects").json() == [], "another visitor sees none of it"
        first_project = first.get("/api/v1/design-studio/projects").json()[0]["id"]
        assert second.get(f"/api/v1/design-studio/projects/{first_project}").status_code in (403, 404)

        # Shared knowledge cannot be changed, the commerce sign-in stays closed, and running an app needs a local Studio.
        assert second.post("/api/v1/domain-knowledge/versions/x/1/transition", json={"to": "approved", "reason": "x"}).status_code in (403, 404, 405, 422)
        assert second.post("/api/v1/auth/login", json={"user_id": "USR-EU-001"}).status_code == 404
        launch = first.post(f"/api/v1/design-studio/projects/{first_project}/runtime/launch", json={})
        assert launch.status_code == 409 and launch.json()["error"]["code"] == "runtime_local_only"


def test_requests_that_cost_money_are_bounded_per_visitor_and_per_instance():
    from fastapi import HTTPException

    visitor = new_visitor_id()
    for _ in range(VISITOR_PER_HOUR):
        check_rate(visitor, now=1000.0)
    try:
        check_rate(visitor, now=1001.0)
    except HTTPException as refusal:
        assert refusal.status_code == 429 and refusal.detail["code"] == "demo_rate_limited"
    else:
        raise AssertionError("the 41st request in the hour should be refused")
    check_rate(visitor, now=1000.0 + 3601)  # the window has passed
    assert INSTANCE_PER_HOUR > VISITOR_PER_HOUR


def test_the_switch_reads_the_usual_ways_of_writing_on_and_nothing_else(monkeypatch):
    from app.core.demo_access import public_studio_enabled

    for value, expected in [("1", True), ("true", True), ('"True"', True), (" yes ", True), ("on", True), ("0", False), ("false", False), ("", False), ("enabled?", False)]:
        monkeypatch.setenv("DESIGN_STUDIO_PUBLIC_DEMO", value)
        assert public_studio_enabled() is expected, value
    monkeypatch.delenv("DESIGN_STUDIO_PUBLIC_DEMO")
    assert public_studio_enabled() is False
