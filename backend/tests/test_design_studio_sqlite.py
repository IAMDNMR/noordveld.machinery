"""Isolated temp-file persistence tests; never connect to Neo4j or production storage."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from zipfile import ZipFile
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import current_user, get_orders_repository
from app.api.routes.design_studio import get_design_store, get_project_store
from app.design_studio.service import template
from app.design_studio.sqlite_store import SqliteProjectStore, SqliteStudioStore
from app.design_studio.store import RevisionConflict, StorageCorrupt
from app.main import app
from app.schemas.application_definition import convert_v1
from app.services.orders import User
from app.core.roles import Role
from tests.support.fake_orders import FakeRepo


@pytest.fixture()
def isolated(tmp_path):
    path = tmp_path / "new-studio.sqlite"
    drafts = SqliteStudioStore(path)
    projects = SqliteProjectStore(path)
    actor = {"id": "alice"}
    app.dependency_overrides[current_user] = lambda: User(actor["id"], "Tester", "test@example.invalid", Role.END_USER)
    app.dependency_overrides[get_design_store] = lambda: drafts
    app.dependency_overrides[get_project_store] = lambda: projects
    yield TestClient(app), actor, path
    for dependency in (current_user, get_design_store, get_project_store):
        app.dependency_overrides.pop(dependency, None)




def test_projects_immutable_history_owner_export_and_restart(isolated):
    client, actor, path = isolated
    definition = convert_v1(template("machine-specification")).model_dump(mode="json")
    original_name = definition["metadata"]["name"]
    created = client.post("/api/v1/design-studio/projects", json=definition)
    assert created.status_code == 200 and created.json()["revision"] == 1
    assert [item["id"] for item in client.get("/api/v1/design-studio/projects").json()] == [definition["id"]]
    definition["metadata"]["name"] = "Revised machine"
    updated = client.put(f"/api/v1/design-studio/projects/{definition['id']}", json={"expected_revision": 1, "definition": definition})
    assert updated.status_code == 200 and updated.json()["revision"] == 2
    assert client.put(f"/api/v1/design-studio/projects/{definition['id']}", json={"expected_revision": 1, "definition": definition}).status_code == 409
    invalid = {**definition, "screens": []}
    assert client.put(f"/api/v1/design-studio/projects/{definition['id']}", json={"expected_revision": 2, "definition": invalid}).status_code == 422
    history = SqliteProjectStore(path).history("alice", definition["id"])
    assert [item.metadata.name for item in history] == [original_name, "Revised machine"]
    archive = client.get(f"/api/v1/design-studio/projects/{definition['id']}/export")
    assert archive.status_code == 200
    with ZipFile(BytesIO(archive.content)) as zip_file:
        assert set(zip_file.namelist()) == {"README.md", "index.html", "manifest.json", "package.json", "tsconfig.json", "src/App.tsx", "src/main.tsx", "src/definition.json"}
    actor["id"] = "bob"
    assert client.get("/api/v1/design-studio/projects").json() == []
    for suffix in ("", "/history", "/export"):
        assert client.get(f"/api/v1/design-studio/projects/{definition['id']}{suffix}").status_code == 403
    assert client.put(f"/api/v1/design-studio/projects/{definition['id']}", json={"expected_revision": 2, "definition": definition}).status_code == 403


def test_concurrent_updates_allow_one_winner(tmp_path):
    path = tmp_path / "concurrent.sqlite"
    store = SqliteProjectStore(path)
    definition = store.create("alice", convert_v1(template("supplier-onboarding")))
    def update(_):
        try:
            return SqliteProjectStore(path).update("alice", definition.id, 1, definition).revision
        except RevisionConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update, (1, 2)), key=str) == [2, "conflict"]
    assert [item.revision for item in store.history("alice", definition.id)] == [1, 2]






