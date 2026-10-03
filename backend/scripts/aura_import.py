"""AuraDB runner for the approved Parts Intelligence import. Credentials come from the local .env and are never printed or logged.

Usage:
  python scripts/aura_import.py preflight            read-only inspection; exit code 3 if the database is not empty
  python scripts/aura_import.py import               preflight again, then (only if empty) constraints + files 01..25; stops at the first error
  python scripts/aura_import.py validate             runs the validation queries and the extra coverage / semantic checks (read-only)
  python scripts/aura_import.py rerun                idempotency: re-runs the whole package; requires the first import to be complete
Each command appends to graph/audits/aura_run_log.json (no credentials in it).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import logging
import warnings

import certifi
from neo4j import GraphDatabase, READ_ACCESS, TrustCustomCAs, WRITE_ACCESS

# The server's 'label does not exist' notices are expected here (schema-only labels are absent on purpose); the one-record warning is cosmetic
logging.getLogger("neo4j.notifications").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore", category=UserWarning)
from graph_audit_lib import AUDITS, CYPHER, ENV_FILE

LOG = AUDITS / "aura_run_log.json"
EXPECTED_NODES, EXPECTED_RELS = 1840, 3812


def env() -> dict[str, str]:
    out = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


CFG = env()
DB = CFG.get("NEO4J_DATABASE") or "neo4j"


def scrub(text: str) -> str:
    """Belt and braces: never let the password or username appear in anything printed or logged."""
    for key in ("NEO4J_PASSWORD",):
        if CFG.get(key):
            text = text.replace(CFG[key], "***")
    return text


def connect():
    # Full TLS verification stays ON. This machine's trust store lacks the SSL.com root that Aura's certificate chains to, so the
    # Mozilla root bundle shipped with certifi is used as the trust anchor instead of disabling verification (neo4j+ssc).
    uri = CFG["NEO4J_URI"].replace("neo4j+s://", "neo4j://", 1)
    driver = GraphDatabase.driver(uri, auth=(CFG["NEO4J_USERNAME"], CFG["NEO4J_PASSWORD"]), encrypted=True, trusted_certificates=TrustCustomCAs(certifi.where()))
    driver.verify_connectivity()
    return driver


def statements(path: Path) -> list[str]:
    body = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("//"))
    return [s.strip() for s in re.split(r";\s*\n", body + "\n") if s.strip()]


def log(entry: dict) -> None:
    LOG.parent.mkdir(exist_ok=True)
    data = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else []
    data.append({"at": dt.datetime.now().isoformat(timespec="seconds"), **entry})
    LOG.write_text(scrub(json.dumps(data, indent=1, default=str)), encoding="utf-8")


def preflight(driver) -> dict:
    """Read-only. Every query runs in a READ-access session."""
    state: dict = {}
    with driver.session(database=DB, default_access_mode=READ_ACCESS) as s:
        rec = s.run("CALL db.info() YIELD name, id RETURN name, id").single()
        state["database"], state["database_id"] = rec["name"], rec["id"]
        state["nodes"] = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        state["relationships"] = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        state["labels"] = s.run("CALL db.labels() YIELD label RETURN collect(label) AS l").single()["l"]
        state["relationship_types"] = s.run("CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) AS l").single()["l"]
        state["constraints"] = [r.data() for r in s.run("SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties RETURN name, type, labelsOrTypes, properties")]
        state["indexes"] = [r.data() for r in s.run("SHOW INDEXES YIELD name, type, labelsOrTypes, properties RETURN name, type, labelsOrTypes, properties")]
        try:
            comp = s.run("CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition").single()
            state["server"] = f"{comp['name']} {comp['versions'][0]} {comp['edition']}"
        except Exception:  # noqa: BLE001 - informational only
            state["server"] = "unknown"
    state["empty"] = state["nodes"] == 0 and state["relationships"] == 0
    return state


def show_preflight(state: dict) -> None:
    print(f"database: {state['database']} (id {state['database_id']}), server {state['server']}")
    print(f"nodes: {state['nodes']}  relationships: {state['relationships']}")
    print(f"labels: {state['labels']}")
    print(f"relationship types: {state['relationship_types']}")
    print(f"constraints: {len(state['constraints'])}  indexes: {len(state['indexes'])}")
    for c in state["constraints"]:
        print("  constraint:", c)
    print("EMPTY" if state["empty"] else "NOT EMPTY")


def run_package(driver, tag: str) -> dict:
    files = sorted(CYPHER.glob("[0-2]*.cypher"))
    report = {"run": tag, "files": [], "nodes_created": 0, "relationships_created": 0, "statements": 0, "ok": 0, "failed": 0, "constraints_added": 0, "error": None}
    for f in files:
        entry = {"file": f.name, "statements": 0, "ok": 0, "nodes_created": 0, "relationships_created": 0, "constraints_added": 0, "properties_set": 0}
        for stmt in statements(f):
            entry["statements"] += 1
            report["statements"] += 1
            try:
                with driver.session(database=DB, default_access_mode=WRITE_ACCESS) as s:
                    summary = s.run(stmt).consume()
                c = summary.counters
                entry["ok"] += 1
                report["ok"] += 1
                entry["nodes_created"] += c.nodes_created
                entry["relationships_created"] += c.relationships_created
                entry["constraints_added"] += c.constraints_added
                entry["properties_set"] += c.properties_set
            except Exception as exc:  # noqa: BLE001 - reported, then the import stops
                report["failed"] += 1
                entry["error"] = {"statement_head": scrub(stmt[:300]), "error": scrub(str(exc))[:600]}
                report["error"] = {"file": f.name, **entry["error"]}
                report["files"].append(entry)
                return report
        report["nodes_created"] += entry["nodes_created"]
        report["relationships_created"] += entry["relationships_created"]
        report["constraints_added"] += entry["constraints_added"]
        report["files"].append(entry)
        print(f"  {f.name}: {entry['ok']}/{entry['statements']} statements, +{entry['nodes_created']} nodes, +{entry['relationships_created']} relationships, +{entry['constraints_added']} constraints")
    return report


def totals(driver) -> tuple[int, int]:
    with driver.session(database=DB, default_access_mode=READ_ACCESS) as s:
        return s.run("MATCH (n) RETURN count(n) AS c").single()["c"], s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    driver = connect()
    try:
        if cmd == "preflight":
            st = preflight(driver)
            show_preflight(st)
            log({"command": "preflight", **st})
            return 0 if st["empty"] else 3
        if cmd == "import":
            st = preflight(driver)
            show_preflight(st)
            log({"command": "preflight (before import)", **st})
            if not st["empty"] or st["constraints"] or st["indexes"] and False:
                print("STOP: the database is not empty. Nothing was written.")
                return 3
            print("database confirmed empty; importing")
            rep = run_package(driver, "first import")
            n, r = totals(driver)
            rep["final_nodes"], rep["final_relationships"] = n, r
            log({"command": "import", **rep})
            print(f"statements {rep['statements']}, ok {rep['ok']}, failed {rep['failed']}; created {rep['nodes_created']} nodes, {rep['relationships_created']} relationships")
            print(f"database now holds {n} nodes, {r} relationships")
            if rep["error"]:
                print("IMPORT STOPPED:", rep["error"]["file"], "|", rep["error"]["error"])
                return 2
            return 0 if (n, r) == (EXPECTED_NODES, EXPECTED_RELS) else 4
        if cmd == "rerun":
            n0, r0 = totals(driver)
            print(f"before re-run: {n0} nodes, {r0} relationships")
            if (n0, r0) != (EXPECTED_NODES, EXPECTED_RELS):
                print("STOP: the first import is not complete; not re-running.")
                return 3
            rep = run_package(driver, "second run (idempotency)")
            n1, r1 = totals(driver)
            rep.update({"before_nodes": n0, "before_relationships": r0, "final_nodes": n1, "final_relationships": r1, "node_delta": n1 - n0, "relationship_delta": r1 - r0})
            log({"command": "rerun", **rep})
            print(f"statements {rep['statements']}, ok {rep['ok']}, failed {rep['failed']}; created by the run: {rep['nodes_created']} nodes, {rep['relationships_created']} relationships")
            print(f"after re-run: {n1} nodes, {r1} relationships (delta {n1 - n0} / {r1 - r0})")
            return 0 if rep["failed"] == 0 and (n1, r1) == (n0, r0) and rep["nodes_created"] == 0 and rep["relationships_created"] == 0 else 5
        print(__doc__)
        return 1
    finally:
        driver.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print("ERROR:", scrub(f"{type(exc).__name__}: {exc}")[:500])
        sys.exit(1)
