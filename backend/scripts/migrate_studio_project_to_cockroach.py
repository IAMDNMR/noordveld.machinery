"""Copy ONE Studio project (every revision, its audit trail and saved releases) from the Neo4j project store into CockroachDB.

For a project created while the Studio ran on its rollback storage (DESIGN_STUDIO_STORAGE_BACKEND=disabled), which the one-time
migration of 2026-10-21 could not have covered. Dry run by default. Copy only: the Neo4j project and the local releases stay
untouched as the rollback source. Refuses a project that already exists in CockroachDB or that was permanently deleted there.
Pause every Studio writer before --apply, and never run it for a project that has been edited in CockroachDB.
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_source(namespace: str, project_id: str, releases: Path) -> dict:
    from app.core.config import get_settings
    from app.design_studio.neo4j_store import Neo4jDocuments, Neo4jProjectStore
    from app.graph.client import GraphClient

    settings = get_settings()
    graph = GraphClient(settings)
    try:
        documents = Neo4jDocuments(graph.driver, settings.neo4j_database, namespace)
        head = documents.read(lambda tx: documents.get(tx, "project", project_id))
        if head is None:
            raise SystemExit(f"{project_id} is not in the Neo4j namespace {namespace}")
        store = Neo4jProjectStore(documents)
        owner = head["owner"]
        stored = documents.read(
            lambda tx: [documents.get(tx, "revision", f"{project_id}/{r}") for r in range(1, head["revision"] + 1)]
        )
    finally:
        graph.close()
    revisions = [
        {
            "revision": item["revision"],
            "definition": item["definition"],
            "actor": item["actor"],
            "operation": item["operation"],
            "at": item["at"],
        }
        for item in stored
    ]
    data = {"project": {"id": project_id, "owner": owner, "current_revision": head["revision"]}, "revisions": revisions, "releases": [], "release_tests": []}
    if releases.is_file():
        with sqlite3.connect(releases) as db:
            db.row_factory = sqlite3.Row
            for row in db.execute("SELECT * FROM releases WHERE project=?", (project_id,)):
                data["releases"].append({**{k: row[k] for k in row.keys() if k != "archive"}, "archive": bytes(row["archive"]).hex()})
            for row in db.execute("SELECT * FROM release_tests WHERE project=?", (project_id,)):
                data["release_tests"].append(dict(row))
    return data


def connect():
    import certifi
    import psycopg
    from psycopg.rows import dict_row

    from app.core.config import get_settings

    get_settings()  # loads backend/.env
    ca = os.environ.get("DESIGN_STUDIO_PG_CA_FILE", "").strip('"')
    if not ca or not Path(ca).is_file():
        ca = certifi.where()  # certificate and hostname verification stay on; only the trust store differs
    return psycopg.connect(
        os.environ["DESIGN_STUDIO_DATABASE_URL"].strip('"'),
        sslmode="verify-full",
        sslrootcert=ca,
        connect_timeout=10,
        row_factory=dict_row,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="studio-local-site")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--releases", type=Path, default=Path(os.environ.get("LOCALAPPDATA", ".")) / "Noordveld" / "Studio" / "releases.sqlite")
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--writers-paused", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.writers_paused:
        parser.error("Pause Studio writers and supply --writers-paused before applying")

    data = read_source(args.namespace, args.project_id, args.releases)
    summary = {
        "project": args.project_id,
        "owner": data["project"]["owner"],
        "revisions": len(data["revisions"]),
        "releases": len(data["releases"]),
        "release_tests": len(data["release_tests"]),
        "sha256": digest(data),
    }
    with connect() as db:
        if db.execute("SELECT id FROM studio_projects WHERE id=%s", (args.project_id,)).fetchone():
            raise SystemExit("The project already exists in CockroachDB; nothing to copy")
        if db.execute("SELECT 1 FROM studio_meta WHERE key=%s", (f"deleted_project:{args.project_id}",)).fetchone():
            raise SystemExit("The project was permanently deleted in CockroachDB; its id cannot be reused")
    if not args.apply:
        print(json.dumps({**summary, "applied": False}))
        return 0

    args.backup.parent.mkdir(parents=True, exist_ok=True)
    with args.backup.open("x", encoding="utf-8") as backup:
        json.dump(data, backup, sort_keys=True)
    if digest(json.loads(args.backup.read_text(encoding="utf-8"))) != summary["sha256"]:
        raise SystemExit("Backup verification failed; nothing was written")

    owner = data["project"]["owner"]
    with connect() as db:  # one transaction: everything is written, verified, then committed together
        db.execute(
            "INSERT INTO studio_projects (id,owner,current_revision) VALUES (%s,%s,%s)",
            (args.project_id, owner, data["project"]["current_revision"]),
        )
        for item in data["revisions"]:
            db.execute(
                "INSERT INTO studio_revisions (project_id,revision,definition_json,actor,operation,created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                (args.project_id, item["revision"], json.dumps(item["definition"], ensure_ascii=False, separators=(",", ":")), item["actor"], item["operation"], item["at"]),
            )
        for item in data["releases"]:
            columns = list(item)
            db.execute(
                f"INSERT INTO studio_releases ({','.join(columns)}) VALUES ({','.join(['%s'] * len(columns))})",
                [bytes.fromhex(item[c]) if c == "archive" else item[c] for c in columns],
            )
        for item in data["release_tests"]:
            columns = list(item)
            db.execute(f"INSERT INTO studio_release_tests ({','.join(columns)}) VALUES ({','.join(['%s'] * len(columns))})", [item[c] for c in columns])
        stored = db.execute("SELECT revision, definition_json FROM studio_revisions WHERE project_id=%s ORDER BY revision", (args.project_id,)).fetchall()
        wanted = {r["revision"]: r["definition"] for r in data["revisions"]}
        if len(stored) != len(wanted) or any(json.loads(row["definition_json"]) != wanted[row["revision"]] for row in stored):
            raise SystemExit("Read-back verification failed; nothing was committed")
    print(json.dumps({**summary, "applied": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
