"""Retained local release packages and append-only independent test runs.

No request-supplied paths. Deployments must supply a durable store dependency;
serverless temporary files are deliberately never selected as release storage.
"""

from contextlib import closing, contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from fastapi import HTTPException
from app.design_studio.sql_retry import retry_serialization


def now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(files):
    return hashlib.sha256(
        json.dumps(
            {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def retain_package(store, owner, project, revision, actor, files, summary=None):
    from app.design_studio.codegen import zip_files

    return store.retain(
        owner,
        project,
        revision,
        actor,
        files,
        zip_files(files),
        summary or {"files_count": len(files)},
    )


class ReleaseStore:
    def __init__(self, path: Path, *, initialize=True):
        self.path = path
        if not initialize:
            if not path.is_file():
                raise ValueError("The release database does not exist")
            with self.connection() as db:
                db.execute("SELECT owner,project,id,archive,archive_sha256 FROM releases LIMIT 0")
                db.execute(
                    "SELECT owner,project,release,id,status,result FROM release_tests LIMIT 0"
                )
            return
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS releases (
                    owner TEXT NOT NULL, project TEXT NOT NULL, id TEXT NOT NULL,
                    revision INTEGER NOT NULL, created TEXT NOT NULL, actor TEXT NOT NULL,
                    archive_sha256 TEXT NOT NULL, archive BLOB NOT NULL,
                    summary TEXT NOT NULL, PRIMARY KEY(owner,project,id)
                );
                CREATE TABLE IF NOT EXISTS release_tests (
                    owner TEXT NOT NULL, project TEXT NOT NULL, release TEXT NOT NULL,
                    id TEXT PRIMARY KEY, actor TEXT NOT NULL, started TEXT NOT NULL,
                    finished TEXT, status TEXT NOT NULL, result TEXT,
                    FOREIGN KEY(owner,project,release) REFERENCES releases(owner,project,id)
                );
            """)

    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.path, timeout=20)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            yield db

    @retry_serialization
    def retain(self, owner, project, revision, actor, files, archive, summary):
        if len(archive) > 50 * 1024 * 1024:
            raise HTTPException(
                413,
                detail={
                    "code": "release_too_large",
                    "message": "Release exceeds the 50 MB local archive limit.",
                },
            )
        release = fingerprint(files)
        with self.connection() as db:
            db.execute(
                """INSERT INTO releases
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(owner,project,id) DO NOTHING""",
                (
                    owner,
                    project,
                    release,
                    revision,
                    now(),
                    actor,
                    hashlib.sha256(archive).hexdigest(),
                    archive,
                    json.dumps(summary),
                ),
            )
        return self.get(owner, project, release)

    @staticmethod
    def describe(row):
        return {
            key: row[key] for key in ("id", "revision", "created", "actor", "archive_sha256")
        } | {"summary": json.loads(row["summary"])}

    @retry_serialization
    def get(self, owner, project, release, *, test_limit=10):
        with self.connection() as db:
            # Local workers have a 120-second deadline. A lost worker must not
            # remain "running" forever after a crash or backend restart.
            db.execute(
                """UPDATE release_tests SET status='interrupted',finished=?,result=?
                WHERE owner=? AND project=? AND release=? AND status='running' AND started<?""",
                (
                    now(),
                    json.dumps(
                        {
                            "passed": False,
                            "ran": 0,
                            "passed_count": 0,
                            "failed_count": 0,
                            "skipped_count": 0,
                            "cases": [],
                            "seconds": 0,
                            "output_tail": "The test worker did not finish before its deadline. Retry the run.",
                        }
                    ),
                    owner,
                    project,
                    release,
                    (datetime.now(timezone.utc) - timedelta(seconds=150)).isoformat(),
                ),
            )
            row = db.execute(
                "SELECT id,revision,created,actor,archive_sha256,summary FROM releases WHERE owner=? AND project=? AND id=?",
                (owner, project, release),
            ).fetchone()
            if row is None:
                raise KeyError(release)
            result = self.describe(row)
            tests = db.execute(
                """SELECT * FROM release_tests WHERE owner=? AND project=?
                AND release=? ORDER BY started DESC, id DESC LIMIT ?""",
                (owner, project, release, test_limit),
            ).fetchall()
            result["tests"] = [
                {key: test[key] for key in ("id", "actor", "started", "finished", "status")}
                | {"result": json.loads(test["result"]) if test["result"] else None}
                for test in tests
            ]
            return result

    @retry_serialization
    def list(self, owner, project):
        with self.connection() as db:
            rows = db.execute(
                """SELECT id FROM releases WHERE owner=? AND project=?
                ORDER BY created DESC, id DESC LIMIT 50""",
                (owner, project),
            ).fetchall()
        return [self.get(owner, project, row["id"]) for row in rows]

    @retry_serialization
    def latest_summary(self, owner, project, revision):
        with self.connection() as db:
            row = db.execute(
                """SELECT id FROM releases WHERE owner=? AND project=? AND revision=?
                ORDER BY created DESC,id DESC LIMIT 1""",
                (owner, project, revision),
            ).fetchone()
        if not row:
            return None
        release = self.get(owner, project, row["id"], test_limit=1)
        return {
            "id": release["id"],
            "revision": release["revision"],
            "created": release["created"],
            "test_status": release["tests"][0]["status"] if release["tests"] else "not_tested",
        }

    @retry_serialization
    def archive(self, owner, project, release):
        with self.connection() as db:
            row = db.execute(
                "SELECT archive,archive_sha256 FROM releases WHERE owner=? AND project=? AND id=?",
                (owner, project, release),
            ).fetchone()
            if row is None:
                raise KeyError(release)
            if hashlib.sha256(row["archive"]).hexdigest() != row["archive_sha256"]:
                raise ValueError("Stored release failed its integrity check")
            return row["archive"]

    def backup(self, destination: Path):
        """Consistent SQLite backup to a new file; never overwrite a restore point."""
        destination = destination.resolve()
        with destination.open("xb"):
            pass
        try:
            with self.connection() as source:
                with closing(sqlite3.connect(destination)) as target:
                    source.backup(target)
                    if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("Release backup failed its integrity check")
            count = self._backup_releases(destination)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return {"archive_count": count, "verified": True}

    @staticmethod
    def _backup_releases(path):
        with closing(sqlite3.connect(path)) as db:
            count = 0
            for archive, digest in db.execute("SELECT archive,archive_sha256 FROM releases"):
                if hashlib.sha256(archive).hexdigest() != digest:
                    raise ValueError("Release backup contains an archive with a mismatched digest")
                count += 1
            return count

    @retry_serialization
    def start_test(self, owner, project, release, actor):
        run = uuid4().hex
        with self.connection() as db:
            db.execute(
                "INSERT INTO release_tests VALUES (?,?,?,?,?,?,NULL,'running',NULL)",
                (owner, project, release, run, actor, now()),
            )
        return run

    @retry_serialization
    def finish_test(self, owner, project, run, result):
        if "ran" not in result:
            result = {
                "ran": 0,
                "passed_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "cases": [],
                "seconds": 0,
                "output_tail": result.get("error", "Test worker failed."),
                **result,
            }
        status = "passed" if result.get("passed") else "failed"
        if result.get("passed") and result.get("skipped_count", 0):
            status = "partial"
        with self.connection() as db:
            changed = db.execute(
                """UPDATE release_tests SET status=?,finished=?,result=?
                WHERE owner=? AND project=? AND id=? AND status='running'""",
                (status, now(), json.dumps(result), owner, project, run),
            ).rowcount
            if changed != 1:
                raise ValueError("Test run is missing or already finished")


def get_release_store() -> ReleaseStore:
    from app.design_studio.postgres_activation import configured_release_store

    store = configured_release_store()
    if store is not None:
        from app.core.demo_access import public_studio_enabled

        if public_studio_enabled():
            from app.design_studio.visitors import SharedWorkspace

            return SharedWorkspace(store)  # saved versions belong to the shared demo workspace, like its projects
        return store
    raise HTTPException(
        503,
        detail={
            "code": "release_storage_unavailable",
            "message": "Durable release storage has not been configured for this environment.",
        },
    )
