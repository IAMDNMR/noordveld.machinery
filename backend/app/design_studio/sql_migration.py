"""Exact, additive import of Studio snapshots; never edits the source stores."""

import base64
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

from app.schemas.application_definition import ApplicationDefinition
from app.design_studio.sql_retry import retry_serialization

TABLES = {
    "studio_drafts": ("id", "owner", "revision", "spec_json", "created_at", "updated_at"),
    "studio_projects": ("id", "owner", "current_revision"),
    "studio_revisions": (
        "project_id",
        "revision",
        "definition_json",
        "actor",
        "operation",
        "created_at",
    ),
    "studio_releases": (
        "owner",
        "project",
        "id",
        "revision",
        "created",
        "actor",
        "archive_sha256",
        "archive",
        "summary",
    ),
    "studio_release_tests": (
        "owner",
        "project",
        "release",
        "id",
        "actor",
        "started",
        "finished",
        "status",
        "result",
    ),
}


def digest(snapshot):
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def sqlite_rows(path, table):
    # table is selected by this module, never taken from an HTTP request.
    with closing(
        sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro", uri=True)
    ) as db:
        db.row_factory = sqlite3.Row
        with db:
            return [dict(row) for row in db.execute(f"SELECT * FROM {table}")]


def snapshot(documents, drafts_path, releases_path):
    graph = documents.read(
        lambda tx: {kind: documents.items(tx, kind) for kind in ("project", "revision")}
    )
    data = {table: [] for table in TABLES}
    data["studio_projects"] = [
        {"id": p["id"], "owner": p["owner"], "current_revision": p["revision"]}
        for p in graph["project"]
    ]
    for revision in graph["revision"]:
        definition = ApplicationDefinition.model_validate(revision["definition"])
        if definition.revision != revision["revision"]:
            raise ValueError("Source revision metadata does not match")
        data["studio_revisions"].append(
            {
                "project_id": definition.id,
                "revision": definition.revision,
                "definition_json": definition.model_dump_json(),
                "actor": revision["actor"],
                "operation": revision["operation"],
                "created_at": revision["at"],
            }
        )
    data["studio_drafts"] = sqlite_rows(drafts_path, "drafts")
    data["studio_releases"] = sqlite_rows(releases_path, "releases")
    data["studio_release_tests"] = sqlite_rows(releases_path, "release_tests")
    for release in data["studio_releases"]:
        if hashlib.sha256(release["archive"]).hexdigest() != release["archive_sha256"]:
            raise ValueError("Source release archive failed checksum verification")
        release["archive"] = base64.b64encode(release["archive"]).decode("ascii")
    validate(data)
    return data


def validate(data):
    projects = {p["id"]: p for p in data["studio_projects"]}
    if len(projects) != len(data["studio_projects"]):
        raise ValueError("Duplicate source project")
    revisions = {}
    for r in data["studio_revisions"]:
        definition = ApplicationDefinition.model_validate_json(r["definition_json"])
        if definition.id != r["project_id"] or definition.revision != r["revision"]:
            raise ValueError("Invalid revision metadata")
        if r["project_id"] not in projects:
            raise ValueError("Orphan revision")
        revisions.setdefault(r["project_id"], []).append(r["revision"])
    for p in projects.values():
        if sorted(revisions.get(p["id"], [])) != list(range(1, p["current_revision"] + 1)):
            raise ValueError("Incomplete source revision history")
    releases = set()
    for r in data["studio_releases"]:
        if r["project"] not in projects or projects[r["project"]]["owner"] != r["owner"]:
            raise ValueError("Release ownership does not match its project")
        if r["revision"] not in revisions[r["project"]]:
            raise ValueError("Release references an unknown revision")
        archive = base64.b64decode(r["archive"], validate=True)
        if hashlib.sha256(archive).hexdigest() != r["archive_sha256"]:
            raise ValueError("Release checksum mismatch")
        releases.add((r["owner"], r["project"], r["id"]))
    for t in data["studio_release_tests"]:
        if (t["owner"], t["project"], t["release"]) not in releases:
            raise ValueError("Test run references an unknown release")


def verify(connection, data):
    for table, columns in TABLES.items():
        actual = [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
        for row in actual:
            if table == "studio_releases":
                row["archive"] = base64.b64encode(row["archive"]).decode("ascii")

        # Strict equality includes owner, timestamps, immutable code bytes and audit actors.
        def canonical(rows):
            return sorted(json.dumps(r, sort_keys=True) for r in rows)

        if canonical(actual) != canonical(data[table]):
            raise ValueError(f"Target read-back differs for {table}; activation refused")


@retry_serialization
def import_snapshot(connect, data):
    validate(data)
    checksum = digest(data)
    with connect() as db:
        for key, expected in (
            ("schema_id", "noordveld-design-studio-postgres-v1"),
            ("release_schema_id", "studio-releases-v1"),
        ):
            marker = db.execute("SELECT value FROM studio_meta WHERE key=%s", (key,)).fetchone()
            if not marker or marker["value"] != expected:
                raise ValueError("Unknown target schema; import refused")
        previous = db.execute(
            "SELECT value FROM studio_meta WHERE key=%s", ("migration_sha256",)
        ).fetchone()
        if previous:
            if previous["value"] != checksum:
                raise ValueError("A different migration already exists; refusing to replace it")
            verify(db, data)
            return
        for table in TABLES:
            if db.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()["total"]:
                raise ValueError("Migration requires an empty target; source was not changed")
        for table, columns in TABLES.items():
            for row in data[table]:
                row = dict(row)
                if table == "studio_releases":
                    row["archive"] = base64.b64decode(row["archive"], validate=True)
                db.execute(
                    f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(['%s'] * len(columns))})",
                    tuple(row[column] for column in columns),
                )
        verify(db, data)
        db.execute(
            "INSERT INTO studio_meta(key,value) VALUES (%s,%s)", ("migration_sha256", checksum)
        )
        db.execute("INSERT INTO studio_meta(key,value) VALUES (%s,%s)", ("migration_complete", "1"))
