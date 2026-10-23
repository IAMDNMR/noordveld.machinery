"""PostgreSQL adapter. Requires an explicit connection factory and v1 schema.

The opt-in dependency factory selects it only when configured. It never creates or migrates tables.
The caller must provide connections with dictionary rows and transaction context
semantics (e.g. psycopg 3 with dict_row). No connection string is logged.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable, Protocol, Any
from uuid import uuid4

from pydantic import ValidationError

from app.design_studio.projects import OPERATIONS, preserve_lifecycle, update_context
from app.design_studio.store import DraftForbidden, DraftMissing, RevisionConflict, StorageCorrupt
from app.design_studio.sql_retry import retry_serialization
from app.schemas.application_definition import ApplicationDefinition
from app.schemas.design_studio import DesignDraft, ScreenSpec

SCHEMA_ID = "noordveld-design-studio-postgres-v1"


class Connection(Protocol):
    def __enter__(self) -> Connection: ...
    def __exit__(self, exc_type, exc, tb) -> Any: ...
    def execute(self, query: str, params: tuple = ()) -> Any: ...


class PostgresStudioStore:
    def __init__(self, connect: Callable[[], Connection]):
        self._connect = connect
        with self._connection() as db:
            try:
                row = db.execute(
                    "SELECT value FROM studio_meta WHERE key=%s", ("schema_id",)
                ).fetchone()
            except Exception as exc:
                raise StorageCorrupt("Approved Design Studio schema is missing") from exc
            if row is None or row["value"] != SCHEMA_ID:
                raise StorageCorrupt("Unknown Design Studio schema; no migration was attempted")
            try:
                for table in ("studio_drafts", "studio_projects", "studio_revisions"):
                    db.execute(f"SELECT * FROM {table} LIMIT 0")
            except Exception as exc:
                raise StorageCorrupt("Incomplete Design Studio schema") from exc

    @contextmanager
    def _connection(self):
        try:
            with self._connect() as db:
                yield db
        except (DraftMissing, DraftForbidden, RevisionConflict, StorageCorrupt):
            raise
        except Exception as exc:
            raise StorageCorrupt("Design Studio storage is unavailable") from exc

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _owner(db: Connection, table: str, owner: str, record_id: str, lock: bool = False):
        # table and lock are fixed internal choices, not request values.
        row = db.execute(
            f"SELECT * FROM {table} WHERE id=%s" + (" FOR UPDATE" if lock else ""), (record_id,)
        ).fetchone()
        if row is None:
            raise DraftMissing()
        if row["owner"] != owner:
            raise DraftForbidden()
        return row

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

    @retry_serialization
    def list(self, owner: str) -> list[DesignDraft]:
        with self._connection() as db:
            return [
                self._draft(row)
                for row in db.execute(
                    "SELECT * FROM studio_drafts WHERE owner=%s ORDER BY updated_at DESC, id",
                    (owner,),
                )
            ]

    @retry_serialization
    def get(self, owner: str, draft_id: str) -> DesignDraft:
        with self._connection() as db:
            return self._draft(self._owner(db, "studio_drafts", owner, draft_id))

    @retry_serialization
    def save(
        self,
        owner: str,
        spec: ScreenSpec,
        draft_id: str | None = None,
        expected_revision: int | None = None,
    ) -> DesignDraft:
        spec = ScreenSpec.model_validate(spec.model_dump(mode="json"))
        with self._connection() as db:
            now = self._now()
            if draft_id is None:
                draft_id = uuid4().hex
                db.execute(
                    "INSERT INTO studio_drafts (id,owner,revision,spec_json,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s)",
                    (draft_id, owner, 1, spec.model_dump_json(), now, now),
                )
            else:
                previous = self._owner(db, "studio_drafts", owner, draft_id, lock=True)
                if expected_revision is None or expected_revision != previous["revision"]:
                    raise RevisionConflict()
                db.execute(
                    "UPDATE studio_drafts SET spec_json=%s,revision=%s,updated_at=%s WHERE id=%s",
                    (spec.model_dump_json(), previous["revision"] + 1, now, draft_id),
                )
            return self._draft(
                db.execute("SELECT * FROM studio_drafts WHERE id=%s", (draft_id,)).fetchone()
            )

    @retry_serialization
    def list_projects(self, owner: str) -> list[ApplicationDefinition]:
        with self._connection() as db:
            count = db.execute(
                "SELECT count(*) AS total FROM studio_projects WHERE owner=%s", (owner,)
            ).fetchone()["total"]
            rows = db.execute(
                "SELECT r.* FROM studio_projects p JOIN studio_revisions r ON r.project_id=p.id AND r.revision=p.current_revision WHERE p.owner=%s ORDER BY r.created_at DESC, p.id",
                (owner,),
            )
            items = [self._definition(row) for row in rows]
            if len(items) != count:
                raise StorageCorrupt("A current project revision is missing")
            return items

    @retry_serialization
    def create(self, owner: str, definition: ApplicationDefinition) -> ApplicationDefinition:
        first = ApplicationDefinition.model_validate(
            {**definition.model_dump(mode="json"), "revision": 1}
        )
        with self._connection() as db:
            if db.execute(
                "SELECT value FROM studio_meta WHERE key=%s", (f"deleted_project:{first.id}",)
            ).fetchone():
                raise RevisionConflict()
            inserted = db.execute(
                "INSERT INTO studio_projects (id,owner,current_revision) VALUES (%s,%s,1) ON CONFLICT DO NOTHING RETURNING id",
                (first.id, owner),
            ).fetchone()
            if inserted is None:
                raise RevisionConflict()
            db.execute(
                "INSERT INTO studio_revisions (project_id,revision,definition_json,actor,operation,created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                (first.id, 1, first.model_dump_json(), owner, "create", self._now()),
            )
            return first

    @retry_serialization
    def current(self, owner: str, project_id: str) -> ApplicationDefinition:
        with self._connection() as db:
            project = self._owner(db, "studio_projects", owner, project_id)
            row = db.execute(
                "SELECT * FROM studio_revisions WHERE project_id=%s AND revision=%s",
                (project_id, project["current_revision"]),
            ).fetchone()
            if row is None:
                raise StorageCorrupt("Current project revision is missing")
            return self._definition(row)

    @retry_serialization
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
            project = self._owner(db, "studio_projects", owner, project_id, lock=True)
            if definition.id != project_id or expected_revision != project["current_revision"]:
                raise RevisionConflict()
            stored = db.execute(
                "SELECT * FROM studio_revisions WHERE project_id=%s AND revision=%s",
                (project_id, expected_revision),
            ).fetchone()
            if stored is None:
                raise StorageCorrupt("Current project revision is missing")
            if operation == "assistant:context":
                updated = update_context(self._definition(stored), definition)
                db.execute("UPDATE studio_revisions SET definition_json=%s WHERE project_id=%s AND revision=%s", (updated.model_dump_json(), project_id, expected_revision))
                return updated
            definition = preserve_lifecycle(self._definition(stored), definition, operation)
            updated = ApplicationDefinition.model_validate(
                {**definition.model_dump(mode="json"), "revision": expected_revision + 1}
            )
            db.execute(
                "INSERT INTO studio_revisions (project_id,revision,definition_json,actor,operation,created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    project_id,
                    updated.revision,
                    updated.model_dump_json(),
                    actor_id or owner,
                    operation,
                    self._now(),
                ),
            )
            db.execute(
                "UPDATE studio_projects SET current_revision=%s WHERE id=%s",
                (updated.revision, project_id),
            )
            return updated

    @retry_serialization
    def history(self, owner: str, project_id: str) -> list[ApplicationDefinition]:
        with self._connection() as db:
            self._owner(db, "studio_projects", owner, project_id)
            return [
                self._definition(row)
                for row in db.execute(
                    "SELECT * FROM studio_revisions WHERE project_id=%s ORDER BY revision",
                    (project_id,),
                )
            ]

    @retry_serialization
    def audit_trail(self, owner: str, project_id: str) -> list[dict]:
        with self._connection() as db:
            self._owner(db, "studio_projects", owner, project_id)
            return [
                {
                    "revision": row["revision"],
                    "actor": row["actor"],
                    "operation": row["operation"],
                    "at": row["created_at"],
                }
                for row in db.execute(
                    "SELECT revision, actor, operation, created_at FROM studio_revisions WHERE project_id=%s ORDER BY revision",
                    (project_id,),
                )
            ]

    @retry_serialization
    def delete_permanently(self, owner, project_id, expected_revision, name, actor):
        """Delete only a confirmed trashed project, including all retained releases.

        One SQL transaction removes child rows and history. A minimal deletion
        receipt prevents ID reuse and stale organization grants being inherited.
        """
        from datetime import timedelta

        with self._connection() as db:
            project = self._owner(db, "studio_projects", owner, project_id, lock=True)
            if project["current_revision"] != expected_revision:
                raise RevisionConflict()
            row = db.execute(
                "SELECT * FROM studio_revisions WHERE project_id=%s AND revision=%s",
                (project_id, expected_revision),
            ).fetchone()
            definition = self._definition(row)
            if (
                not definition.project_lifecycle
                or definition.project_lifecycle.status != "trashed"
                or definition.metadata.name != name
            ):
                raise RevisionConflict()
            running = db.execute(
                "SELECT id FROM studio_release_tests WHERE owner=%s AND project=%s AND status='running' AND started>%s LIMIT 1",
                (
                    owner,
                    project_id,
                    (datetime.now(timezone.utc) - timedelta(seconds=150)).isoformat(),
                ),
            ).fetchone()
            if running:
                raise RevisionConflict("Wait for generated tests to finish before deleting")
            db.execute(
                "DELETE FROM studio_release_tests WHERE owner=%s AND project=%s",
                (owner, project_id),
            )
            db.execute(
                "DELETE FROM studio_releases WHERE owner=%s AND project=%s", (owner, project_id)
            )
            db.execute("DELETE FROM studio_revisions WHERE project_id=%s", (project_id,))
            db.execute("DELETE FROM studio_projects WHERE owner=%s AND id=%s", (owner, project_id))
            db.execute(
                "INSERT INTO studio_meta(key,value) VALUES (%s,%s)",
                (
                    f"deleted_project:{project_id}",
                    json.dumps({"owner": owner, "actor": actor, "at": self._now()}),
                ),
            )


class PostgresProjectStore(PostgresStudioStore):
    def list(self, owner: str) -> list[ApplicationDefinition]:
        return self.list_projects(owner)
