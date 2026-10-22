"""Remove ONE Studio project's old copy from the Neo4j project store, once CockroachDB holds it.

Neo4j keeps reusable knowledge; Studio projects live in CockroachDB. This removes only the project head and revision documents of
the named project inside the Studio namespace (nothing else in Neo4j). It refuses to run unless CockroachDB already holds every
revision with identical content (or the project was permanently deleted there) and the migration backup file exists.

Dry run by default. Permanent: run it yourself, after you are sure you want the old copy gone.
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from migrate_studio_project_to_cockroach import connect, read_source  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="studio-local-site")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--backup", type=Path, required=True, help="the file the copy to CockroachDB wrote")
    parser.add_argument("--confirm-name", help="the project's exact name; required with --apply")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.backup.is_file():
        raise SystemExit("The migration backup file does not exist; nothing was removed")
    data = read_source(args.namespace, args.project_id, Path("."))
    name = data["revisions"][-1]["definition"]["metadata"]["name"]

    with connect() as db:
        deleted = db.execute("SELECT 1 FROM studio_meta WHERE key=%s", (f"deleted_project:{args.project_id}",)).fetchone()
        stored = {
            row["revision"]: json.loads(row["definition_json"])
            for row in db.execute("SELECT revision, definition_json FROM studio_revisions WHERE project_id=%s", (args.project_id,))
        }
    if not deleted:
        wanted = {item["revision"]: item["definition"] for item in data["revisions"]}
        # Moving to Trash in CockroachDB adds revisions after the copy; every copied revision must still be identical.
        if any(stored.get(revision) != definition for revision, definition in wanted.items()):
            raise SystemExit("CockroachDB does not hold an identical copy of every revision; nothing was removed")
    print(json.dumps({"project": args.project_id, "name": name, "neo4j_revisions": len(data["revisions"]), "cockroach_copy_verified": not deleted, "permanently_deleted_in_cockroach": bool(deleted), "applied": False}))
    if not args.apply:
        return 0
    if args.confirm_name != name:
        raise SystemExit(f"Type the exact project name with --confirm-name \"{name}\" to remove it")

    from app.core.config import get_settings
    from app.graph.client import GraphClient

    settings = get_settings()
    graph = GraphClient(settings)
    try:
        with graph.driver.session(database=settings.neo4j_database) as session:
            result = session.run(
                "MATCH (n:DSDocument {namespace:$ns}) "
                "WHERE (n.kind='project' AND n.document_id=$id) OR (n.kind='revision' AND n.document_id STARTS WITH $prefix) "
                "DETACH DELETE n RETURN count(n) AS removed",
                ns=args.namespace, id=args.project_id, prefix=f"{args.project_id}/",
            ).single()
    finally:
        graph.close()
    print(json.dumps({"removed_documents": result["removed"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
