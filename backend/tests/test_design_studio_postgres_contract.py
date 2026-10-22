"""Offline PostgreSQL adapter contract using an isolated SQL shim, not a live server."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.design_studio.activation import storage_candidate
from app.api.dependencies import current_user
from app.api.routes.design_studio import (
    get_design_store,
    get_project_store,
    require_studio_identity,
)
from app.core.roles import Role
from app.main import app
from app.services.orders import User
from app.design_studio.postgres_store import PostgresProjectStore, PostgresStudioStore
from app.design_studio.service import template
from app.design_studio.store import (
    DisabledDraftStore,
    DraftForbidden,
    RevisionConflict,
    StorageCorrupt,
)
from app.design_studio.projects import DisabledProjectStore
from app.schemas.application_definition import convert_v1


class SqlShim:
    """Exercise adapter SQL and transaction boundaries without external storage."""

    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=5)
        self.db.row_factory = sqlite3.Row

    def __enter__(self):
        self.db.execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.db.rollback() if exc_type else self.db.commit()
        finally:
            self.db.close()

    def execute(self, query, params=()):
        return self.db.execute(query.replace("%s", "?").replace(" FOR UPDATE", ""), params)


@pytest.fixture()
def adapter(tmp_path):
    path = tmp_path / "postgres-contract.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE studio_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO studio_meta VALUES ('schema_id', 'noordveld-design-studio-postgres-v1');
            CREATE TABLE studio_drafts (id TEXT PRIMARY KEY, owner TEXT, revision INTEGER, spec_json TEXT, created_at TEXT, updated_at TEXT);
            CREATE TABLE studio_projects (id TEXT PRIMARY KEY, owner TEXT, current_revision INTEGER);
            CREATE TABLE studio_revisions (project_id TEXT, revision INTEGER, definition_json TEXT, actor TEXT, operation TEXT, created_at TEXT, PRIMARY KEY(project_id, revision));
        """)
    def connect():
        return SqlShim(path)
    return PostgresStudioStore(connect), PostgresProjectStore(connect), path


def test_postgres_adapter_drafts_versions_ownership_and_conflicts(adapter):
    drafts, projects, _ = adapter
    created = drafts.save("alice", template("supplier-onboarding"))
    assert created.revision == 1
    assert drafts.get("alice", created.id).spec.name == created.spec.name
    assert drafts.save("alice", created.spec, created.id, 1).revision == 2
    with pytest.raises(RevisionConflict):
        drafts.save("alice", created.spec, created.id, 1)
    with pytest.raises(DraftForbidden):
        drafts.get("bob", created.id)
    assert drafts.list("bob") == []
    definition = convert_v1(template("machine-specification"))
    first = projects.create("alice", definition)
    assert first.revision == 1
    updated = projects.update("alice", first.id, 1, definition)
    assert updated.revision == 2
    assert [item.revision for item in projects.history("alice", first.id)] == [1, 2]
    assert [item.id for item in projects.list("alice")] == [first.id]
    assert projects.list("bob") == []
    with pytest.raises(DraftForbidden):
        projects.current("bob", first.id)
    with pytest.raises(RevisionConflict):
        projects.update("alice", first.id, 1, definition)
















