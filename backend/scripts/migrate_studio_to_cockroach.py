"""Back up and migrate local Studio projects/releases to a dedicated CockroachDB.

Dry run by default. Pause Studio writers before --apply. Source stores remain
unchanged. Never prints credentials or database driver error messages.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.design_studio.sql_migration import digest, import_snapshot, snapshot, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--drafts", type=Path, required=True)
    parser.add_argument("--releases", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--database", default="noordveld_studio")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--writers-paused", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.writers_paused:
        parser.error("Pause Studio writers and supply --writers-paused before applying")
    if args.database != "noordveld_studio":
        parser.error("This migration targets only the isolated noordveld_studio database")
    from app.core.config import get_settings
    from app.graph.client import GraphClient
    from app.design_studio.neo4j_store import Neo4jDocuments

    settings = get_settings()
    graph = GraphClient(settings)
    try:
        data = snapshot(
            Neo4jDocuments(graph.driver, settings.neo4j_database, args.namespace),
            args.drafts,
            args.releases,
        )
    finally:
        graph.close()
    summary = {"counts": {table: len(rows) for table, rows in data.items()}, "sha256": digest(data)}
    if not args.apply:
        print(json.dumps({**summary, "applied": False}))
        return
    args.backup.parent.mkdir(parents=True, exist_ok=True)
    with args.backup.open("x", encoding="utf-8") as backup:
        json.dump(data, backup, sort_keys=True)
    if digest(json.loads(args.backup.read_text(encoding="utf-8"))) != summary["sha256"]:
        raise ValueError("Backup verification failed")

    import os
    import psycopg
    from psycopg.rows import dict_row
    from psycopg import sql

    options = {
        "sslmode": "verify-full",
        "sslrootcert": os.environ["DESIGN_STUDIO_PG_CA_FILE"].strip('"'),
        "connect_timeout": 10,
        "row_factory": dict_row,
    }
    dsn = os.environ["DESIGN_STUDIO_DATABASE_URL"].strip('"')
    with psycopg.connect(dsn, autocommit=True, **options) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE IF NOT EXISTS {}").format(sql.Identifier(args.database))
        )

    def connect():
        return psycopg.connect(dsn, dbname=args.database, **options)

    with connect() as db:
        existing = db.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        ).fetchall()
    tables = {r["table_name"] for r in existing}
    expected = {"studio_meta", *data}
    if tables and tables != expected:
        raise ValueError("Target has unexpected or incomplete tables; refusing to alter them")
    if not tables:
        schema_dir = Path(__file__).resolve().parents[1] / "app" / "design_studio"
        with psycopg.connect(dsn, dbname=args.database, autocommit=True, **options) as db:
            for name in ("postgres_schema.sql", "postgres_release_schema.sql"):
                db.execute((schema_dir / name).read_text(encoding="utf-8"), prepare=False)
    import_snapshot(connect, data)
    with connect() as db:
        verify(db, data)
    print(json.dumps({**summary, "applied": True, "verified": True, "backup": str(args.backup)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Provider errors may contain the server address or connection credentials.
        print(
            json.dumps(
                {
                    "applied": False,
                    "error_type": type(error).__name__,
                    "sqlstate": getattr(error, "sqlstate", None),
                }
            )
        )
        raise SystemExit(1) from None
