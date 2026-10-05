"""Write the European foundation to Neo4j AuraDB. Additive and idempotent: nodes and relationships are MERGEd on their unique ids and only
SET when created; nothing is deleted, no existing property is overwritten.

  python seed.py plan        constraints and counts only (no write)
  python seed.py apply       constraints, nodes, relationships; verifies the source checksum before and after
  Run `apply` twice: the second run must create nothing.
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from typing import Any

from audit_before import source_checksum
from build import build, summary
from common import BATCH, dump, read
from model import KEYS, Model
from neo4j import WRITE_ACCESS

from common import client, get_settings

NEW_INDEXES = [("TransportRoute", "origin_depot_id"), ("TransportRoute", "destination_shipto_id"), ("ShipTo", "country_code"), ("Customer", "country_code"),
               ("Dealer", "country_code"), ("Supplier", "country_code"), ("TransportTerminal", "terminal_type")]


def run(query: str, **params: Any) -> tuple[dict[str, int], list[dict[str, Any]]]:
    with client().driver.session(database=get_settings().neo4j_database, default_access_mode=WRITE_ACCESS) as s:
        def work(tx):
            result = tx.run(query, params)
            data = result.data()
            c = result.consume().counters
            return {"nodes": c.nodes_created, "rels": c.relationships_created, "props": c.properties_set}, data
        return s.execute_write(work)


def constraints(m: Model) -> list[str]:
    stmts = []
    for label in sorted(m.nodes):
        if m.nodes[label]:
            stmts.append(f"CREATE CONSTRAINT {''.join('_' + c.lower() if c.isupper() else c for c in label).lstrip('_')}_id_unique IF NOT EXISTS FOR (n:`{label}`) REQUIRE n.{KEYS[label]} IS UNIQUE")
    for t in sorted(m.rels):
        if m.rels[t]:
            stmts.append(f"CREATE CONSTRAINT rel_{t.lower()}_id_unique IF NOT EXISTS FOR ()-[r:`{t}`]-() REQUIRE r.rel_id IS UNIQUE")
    for label, prop in NEW_INDEXES:
        stmts.append(f"CREATE INDEX {label.lower()}_{prop}_idx IF NOT EXISTS FOR (n:`{label}`) ON (n.{prop})")
    return stmts


def prune_stale(m: Model) -> dict[str, int]:
    """Remove records of THIS batch that the current generator no longer produces (e.g. after a routing rule was tightened). Never touches other batches or source data."""
    out: dict[str, int] = {}
    for label in ("TransportRoute", "TransportLeg", "FreightRate"):
        key = KEYS[label]
        ids = list(m.nodes[label])
        c, _ = run(f"MATCH (n:`{label}`) WHERE n.enrichment_batch = $b AND NOT n.{key} IN $ids DETACH DELETE n", b=BATCH, ids=ids)
        out[label] = read(f"MATCH (n:`{label}`) WHERE n.enrichment_batch = $b RETURN count(n) AS n", b=BATCH)[0]["n"]
    for t in ("DISTANCE_TO", "HAS_TRANSPORT_OPTION"):
        ids = list(m.rels[t])
        run(f"MATCH ()-[r:`{t}`]->() WHERE r.enrichment_batch = $b AND NOT r.rel_id IN $ids DELETE r", b=BATCH, ids=ids)
        out[t] = read(f"MATCH ()-[r:`{t}`]->() WHERE r.enrichment_batch = $b RETURN count(r) AS n", b=BATCH)[0]["n"]
    return out


def apply(m: Model, batch: int = 400) -> dict[str, Any]:
    out: dict[str, Any] = {"constraints": 0, "nodes_created": 0, "rels_created": 0, "node_batches": 0, "rel_batches": 0, "missing_endpoints": []}
    for stmt in constraints(m):
        run(stmt)
        out["constraints"] += 1
    for label, rows in m.nodes.items():
        if not rows:
            continue
        key = KEYS[label]
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for id_, props in rows.items():
            groups[m.extra_labels.get((label, id_), ())].append({"id": id_, "props": props})
        for extras, items in groups.items():
            extra_cypher = "".join(f"SET n:`{x}` " for x in extras)
            q = f"UNWIND $rows AS row MERGE (n:`{label}` {{{key}: row.id}}) ON CREATE SET n += row.props {('WITH n, row ' + extra_cypher) if extras else ''}"
            for i in range(0, len(items), batch):
                c, _ = run(q, rows=items[i:i + batch])
                out["nodes_created"] += c["nodes"]
                out["node_batches"] += 1
        print(f"  nodes {label}: {len(rows)}", flush=True)
    for t, rows in m.rels.items():
        if not rows:
            continue
        groups2: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for r in rows.values():
            groups2[(r["a_label"], r["b_label"])].append({"a": r["a_id"], "b": r["b_id"], "rel_id": r["rel_id"], "props": r["props"]})
        for (al, bl), items in groups2.items():
            q = (f"UNWIND $rows AS row MATCH (a:`{al}` {{{KEYS[al]}: row.a}}) MATCH (b:`{bl}` {{{KEYS[bl]}: row.b}}) "
                 f"MERGE (a)-[r:`{t}` {{rel_id: row.rel_id}}]->(b) ON CREATE SET r += row.props RETURN count(r) AS matched")
            matched = 0
            for i in range(0, len(items), batch):
                c, data = run(q, rows=items[i:i + batch])
                out["rels_created"] += c["rels"]
                out["rel_batches"] += 1
                matched += data[0]["matched"] if data else 0
            if matched != len(items):
                out["missing_endpoints"].append({"type": t, "from": al, "to": bl, "expected": len(items), "matched": matched})
        print(f"  rels  {t}: {len(rows)}", flush=True)
    return out


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
    model, meta = build()
    s = summary(model, meta)
    print(f"planned: {s['nodes_total']} nodes, {s['relationships_total']} relationships; {len(constraints(model))} schema statements")
    if mode == "plan":
        sys.exit(0)
    before = source_checksum()
    t0 = time.time()
    result = apply(model)
    if not result["missing_endpoints"]:
        result["after_prune_counts"] = prune_stale(model)
    after = source_checksum()
    result |= {"source_checksum_before": before, "source_checksum_after": after, "source_data_unchanged": before == after, "seconds": round(time.time() - t0)}
    dump(f"seed_run_{int(time.time())}.json", result)
    print(json.dumps(result, indent=1))
    if before != after:
        raise SystemExit("SOURCE DATA CHANGED: stop and investigate")
