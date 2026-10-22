"""Explicitly constructed, isolated SQLite adapter for local verification only.

No production dependency selects this adapter: serverless filesystem durability and
trusted sign-in have not been established. Never point it at an existing v1 DB.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.design_studio.projects import OPERATIONS, preserve_lifecycle
from app.design_studio.store import DraftForbidden, DraftMissing, RevisionConflict, StorageCorrupt
from app.schemas.application_definition import ApplicationDefinition
from app.schemas.design_studio import DesignDraft, ScreenSpec

SCHEMA_ID = "noordveld-design-studio-isolated-v1"


class SqliteStudioStore:
    """Transactions serialize writers; revision checks reject stale updates."""

    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.exists():
            with self._connection() as db:
                try:
                    row = db.execute(
                        "SELECT value FROM studio_meta WHERE key='schema_id'"
                    ).fetchone()
                except sqlite3.DatabaseError as exc:
                    raise StorageCorrupt("Unknown or damaged Design Studio database") from exc
                if row is None or row[0] != SCHEMA_ID:
                    raise StorageCorrupt(
                        "Unknown Design Studio database; no migration was attempted"
                    )
                self._check(db)
        else:
            if not self.path.parent.is_dir():
                raise FileNotFoundError(self.path.parent)
            with self._connection() as db:
                db.executescript("""
                    CREATE TABLE studio_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    INSERT INTO studio_meta VALUES ('schema_id', 'noordveld-design-studio-isolated-v1');
                    CREATE TABLE drafts (id TEXT PRIMARY KEY, owner TEXT NOT NULL, revision INTEGER NOT NULL,
                        spec_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                    CREATE INDEX drafts_owner ON drafts(owner);
                    CREATE TABLE projects (id TEXT PRIMARY KEY, owner TEXT NOT NULL, current_revision INTEGER NOT NULL);
                    CREATE INDEX projects_owner ON projects(owner);
                    CREATE TABLE project_revisions (project_id TEXT NOT NULL, revision INTEGER NOT NULL,
                        definition_json TEXT NOT NULL, actor TEXT NOT NULL, operation TEXT NOT NULL, created_at TEXT NOT NULL,
                        PRIMARY KEY(project_id, revision), FOREIGN KEY(project_id) REFERENCES projects(id));
                """)
                self._check(db)

    @contextmanager
    def _connection(self):
        try:
            db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=5000")
            try:
                yield db
            finally:
                db.close()
        except sqlite3.DatabaseError as exc:
            raise StorageCorrupt("Design Studio storage is unavailable or damaged") from exc

    @staticmethod
    def _check(db):
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise StorageCorrupt("Design Studio database integrity check failed")
        required = {"studio_meta", "drafts", "projects", "project_revisions"}
        actual = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required.issubset(actual):
            raise StorageCorrupt("Incomplete Design Studio database schema")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise StorageCorrupt("Design Studio revision references are damaged")

    @staticmethod
    def _draft(row) -> DesignDraft:
        try:
            return DesignDraft.model_validate(
                {
                    "id": row["id"],
                    "owner_id": row["owner"],
                    "revision": row["revision"],
                    "spec": json.loads(row["spec_json"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        except (ValueError, TypeError, ValidationError) as exc:
            raise StorageCorrupt("Stored draft failed validation") from exc

    @staticmethod
    def _definition(row) -> ApplicationDefinition:
        try:
            definition = ApplicationDefinition.model_validate_json(row["definition_json"])
            if definition.id != row["project_id"] or definition.revision != row["revision"]:
                raise ValueError("Revision metadata mismatch")
            return definition
        except (ValueError, ValidationError) as exc:
            raise StorageCorrupt("Stored project revision failed validation") from exc

    @staticmethod
    def _owner(db, table: str, owner: str, record_id: str, key: str = "id"):
        # table/key are internal constants, never client-controlled.
        row = db.execute(f"SELECT * FROM {table} WHERE {key}=?", (record_id,)).fetchone()
        if row is None:
            raise DraftMissing()
        if row["owner"] != owner:
            raise DraftForbidden()
        return row

    def list(self, owner: str) -> list[DesignDraft]:
        with self._connection() as db:
            return [
                self._draft(row)
                for row in db.execute(
                    "SELECT * FROM drafts WHERE owner=? ORDER BY updated_at DESC, id", (owner,)
                )
            ]

    def get(self, owner: str, draft_id: str) -> DesignDraft:
        with self._connection() as db:
            return self._draft(self._owner(db, "drafts", owner, draft_id))

    def save(
        self,
        owner: str,
        spec: ScreenSpec,
        draft_id: str | None = None,
        expected_revision: int | None = None,
    ) -> DesignDraft:
        spec = ScreenSpec.model_validate(spec.model_dump(mode="json"))
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                previous = self._owner(db, "drafts", owner, draft_id) if draft_id else None
                if draft_id and (
                    expected_revision is None or expected_revision != previous["revision"]
                ):
                    raise RevisionConflict()
                now = datetime.now(timezone.utc).isoformat()
                if previous:
                    db.execute(
                        "UPDATE drafts SET spec_json=?, revision=?, updated_at=? WHERE id=?",
                        (spec.model_dump_json(), previous["revision"] + 1, now, draft_id),
                    )
                    result_id = draft_id
                else:
                    result_id = uuid4().hex
                    db.execute(
                        "INSERT INTO drafts VALUES (?,?,?,?,?,?)",
                        (result_id, owner, 1, spec.model_dump_json(), now, now),
                    )
                result = self._draft(
                    db.execute("SELECT * FROM drafts WHERE id=?", (result_id,)).fetchone()
                )
                db.execute("COMMIT")
                return result
            except Exception:
                db.execute("ROLLBACK")
                raise

    def list_projects(self, owner: str) -> list[ApplicationDefinition]:
        with self._connection() as db:
            count = db.execute("SELECT count(*) FROM projects WHERE owner=?", (owner,)).fetchone()[
                0
            ]
            rows = db.execute(
                "SELECT r.* FROM projects p JOIN project_revisions r ON r.project_id=p.id AND r.revision=p.current_revision WHERE p.owner=? ORDER BY r.created_at DESC, p.id",
                (owner,),
            )
            items = [self._definition(row) for row in rows]
            if len(items) != count:
                raise StorageCorrupt("A current project revision is missing")
            return items

    def create(self, owner: str, definition: ApplicationDefinition) -> ApplicationDefinition:
        first = ApplicationDefinition.model_validate(
            {**definition.model_dump(mode="json"), "revision": 1}
        )
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if db.execute("SELECT 1 FROM projects WHERE id=?", (first.id,)).fetchone():
                    raise RevisionConflict()
                db.execute("INSERT INTO projects VALUES (?,?,1)", (first.id, owner))
                db.execute(
                    "INSERT INTO project_revisions VALUES (?,?,?,?,?,?)",
                    (
                        first.id,
                        1,
                        first.model_dump_json(),
                        owner,
                        "create",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                db.execute("COMMIT")
                return first
            except Exception:
                db.execute("ROLLBACK")
                raise

    def current(self, owner: str, project_id: str) -> ApplicationDefinition:
        with self._connection() as db:
            project = self._owner(db, "projects", owner, project_id)
            row = db.execute(
                "SELECT * FROM project_revisions WHERE project_id=? AND revision=?",
                (project_id, project["current_revision"]),
            ).fetchone()
            if row is None:
                raise StorageCorrupt("Current project revision is missing")
            return self._definition(row)

    def update(
        self,
        owner: str,
        project_id: str,
        expected_revision: int,
        definition: ApplicationDefinition,
        operation: str = "update",
        actor_id: str | None = None,
    ) -> ApplicationDefinition:
        if operation not in OPERATIONS:
            raise ValueError("Unknown operation")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                project = self._owner(db, "projects", owner, project_id)
                if definition.id != project_id or expected_revision != project["current_revision"]:
                    raise RevisionConflict()
                stored = db.execute(
                    "SELECT * FROM project_revisions WHERE project_id=? AND revision=?",
                    (project_id, expected_revision),
                ).fetchone()
                if stored is None:
                    raise StorageCorrupt("Current project revision is missing")
                definition = preserve_lifecycle(self._definition(stored), definition, operation)
                updated = ApplicationDefinition.model_validate(
                    {**definition.model_dump(mode="json"), "revision": expected_revision + 1}
                )
                db.execute(
                    "INSERT INTO project_revisions VALUES (?,?,?,?,?,?)",
                    (
                        project_id,
                        updated.revision,
                        updated.model_dump_json(),
                        actor_id or owner,
                        operation,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                db.execute(
                    "UPDATE projects SET current_revision=? WHERE id=?",
                    (updated.revision, project_id),
                )
                db.execute("COMMIT")
                return updated
            except Exception:
                db.execute("ROLLBACK")
                raise

    def history(self, owner: str, project_id: str) -> list[ApplicationDefinition]:
        with self._connection() as db:
            self._owner(db, "projects", owner, project_id)
            return [
                self._definition(row)
                for row in db.execute(
                    "SELECT * FROM project_revisions WHERE project_id=? ORDER BY revision",
                    (project_id,),
                )
            ]

    def audit_trail(self, owner: str, project_id: str) -> list[dict]:
        with self._connection() as db:
            self._owner(db, "projects", owner, project_id)
            return [
                {
                    "revision": row["revision"],
                    "actor": row["actor"],
                    "operation": row["operation"],
                    "at": row["created_at"],
                }
                for row in db.execute(
                    "SELECT revision, actor, operation, created_at FROM project_revisions WHERE project_id=? ORDER BY revision",
                    (project_id,),
                )
            ]


class SqliteProjectStore(SqliteStudioStore):
    def list(self, owner: str) -> list[ApplicationDefinition]:
        return self.list_projects(owner)
