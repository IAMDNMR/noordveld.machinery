"""The release contract on an explicitly migrated PostgreSQL database."""

from contextlib import contextmanager
import re

from app.design_studio.releases import ReleaseStore


class Queries:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, values=()):
        query = re.sub(r"\brelease_tests\b", "studio_release_tests", query)
        query = re.sub(r"\breleases\b", "studio_releases", query)
        return self.connection.execute(query.replace("?", "%s"), values)


class PostgresReleaseStore(ReleaseStore):
    def __init__(self, connect):
        self._connect = connect
        with self.connection() as db:
            row = db.execute(
                "SELECT value FROM studio_meta WHERE key=?", ("release_schema_id",)
            ).fetchone()
            if not row or row["value"] != "studio-releases-v1":
                raise ValueError("The isolated release schema is missing or unknown")
            db.execute("SELECT * FROM releases LIMIT 0")
            db.execute("SELECT * FROM release_tests LIMIT 0")

    @contextmanager
    def connection(self):
        with self._connect() as connection:
            yield Queries(connection)

    def backup(self, destination):
        raise ValueError(
            "Use PostgreSQL/provider backup tooling; SQLite release backups apply only to local storage."
        )
