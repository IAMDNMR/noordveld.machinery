"""Preview or copy a compatible runtime database into a new revision.

The source is always read-only. Breaking changes require an explicit custom
migration; this tool never drops fields, rewrites business data, or overwrites a
target. Keep the previous package/database together for rollback.
"""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from validation import validate_record


def changes(old, new):
    blocked = []
    if old["project_id"] != new["project_id"]:
        blocked.append("Schemas belong to different projects.")
    if not new.get("approved") or new.get("source_reference_only"):
        blocked.append("The target specification is not approved for execution.")
    if old.get("runtime_version") != new.get("runtime_version"):
        blocked.append("The runtime storage version changed.")
    for group in (
        "workflows",
        "rules",
        "roles",
        "references",
        "imports",
        "integrations",
        "decisions",
    ):
        if old.get(group) != new.get(group):
            blocked.append(
                f"{group} changed; review a custom migration before carrying operational data forward."
            )
    entities = {entity["id"]: entity for entity in new["entities"]}
    additions = []
    for entity in old["entities"]:
        target = entities.get(entity["id"])
        if target is None:
            blocked.append(f"Entity {entity['id']} was removed.")
            continue
        previous = {field["id"]: field for field in entity["validation"]}
        current = {field["id"]: field for field in target["validation"]}
        for field, rule in previous.items():
            if current.get(field) != rule:
                blocked.append(f"Field {entity['id']}.{field} changed or was removed.")
        for field, rule in current.items():
            if field not in previous:
                if rule["required"] or rule.get("key"):
                    blocked.append(f"New field {entity['id']}.{field} requires a backfill.")
                else:
                    additions.append(f"{entity['id']}.{field}")
        if entity.get("owner_role_id") != target.get("owner_role_id"):
            blocked.append(f"Ownership changed for {entity['id']}.")
    return {"compatible": not blocked, "blocked": blocked, "optional_fields_added": additions}


def migrate(old, new, source: Path, target: Path | None = None, actor="operator"):
    plan = changes(old, new)
    source = source.resolve(strict=True)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as db:
        spec = db.execute("SELECT value FROM metadata WHERE key='specification'").fetchone()
        if not spec or spec[0] != old["fingerprint"]:
            raise ValueError("Source database does not match the previous package.")
        counts = {
            table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("records", "instances", "events")
        }
        plan["preserved_rows"] = counts
        if not plan["compatible"] or target is None:
            return plan
        # Validate all stored values against the target without treating existing
        # system-generated keys as a new user submission.
        entities = {entity["id"]: entity for entity in new["entities"]}
        for entity, record in db.execute("SELECT entity,data FROM records"):
            rules = [{**rule, "system_managed": False} for rule in entities[entity]["validation"]]
            if validate_record(rules, json.loads(record)):
                raise ValueError(f"Stored values do not satisfy the target entity {entity}.")
        target = target.resolve()
        # Exclusive create prevents replacing an existing revision or rollback DB.
        with target.open("xb"):
            pass
        try:
            with closing(sqlite3.connect(target)) as copied, copied:
                db.backup(copied)
                copied.execute(
                    "UPDATE metadata SET value=? WHERE key='specification'", (new["fingerprint"],)
                )
                copied.execute("DELETE FROM sessions")
                copied.execute(
                    """INSERT INTO events(tenant,actor,resource,action,data,at)
                    SELECT DISTINCT tenant,?,?,?, ?,? FROM (
                        SELECT tenant FROM records UNION SELECT tenant FROM instances
                    )""",
                    (
                        actor,
                        "database",
                        "migration.apply",
                        json.dumps(
                            {
                                "from": old["fingerprint"],
                                "to": new["fingerprint"],
                                "source_preserved": True,
                            }
                        ),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                if copied.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Migrated database failed its integrity check.")
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    return {**plan, "applied": True, "sessions_cleared": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-schema", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=Path(__file__).with_name("schema.json"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--actor", default="operator")
    args = parser.parse_args()
    if args.apply and args.target is None:
        parser.error("--apply requires a new --target path")
    try:
        result = migrate(
            json.loads(args.previous_schema.read_text(encoding="utf-8")),
            json.loads(args.schema.read_text(encoding="utf-8")),
            args.source,
            args.target if args.apply else None,
            args.actor,
        )
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["compatible"] else 1)
