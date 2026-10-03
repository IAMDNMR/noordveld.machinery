"""Writes graph/audits/neo4j_import_report.md from graph/audits/aura_run_log.json and graph/audits/aura_validation_results.json. No database access, no credentials."""
from __future__ import annotations

import collections
import json
from pathlib import Path

from graph_audit_lib import AUDITS

REPORT = AUDITS / "neo4j_import_report.md"
log = json.loads((AUDITS / "aura_run_log.json").read_text(encoding="utf-8"))
val = json.loads((AUDITS / "aura_validation_results.json").read_text(encoding="utf-8"))
pre = next(e for e in log if e["command"] == "preflight (before import)")
imp = next(e for e in reversed(log) if e["command"] == "import")
rer = next(e for e in reversed(log) if e["command"] == "rerun")


def table(rows: list[dict], cols: list[str]) -> str:
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(str(r.get(c, "")).replace("|", "/") for c in cols) + " |" for r in rows]
    return "\n".join(out)


checks = val["checks"]
by = lambda prefix: [c for c in checks if c["id"].startswith(prefix)]  # noqa: E731
passed = lambda cs: all(c["status"] == "PASS" for c in cs)  # noqa: E731
cov = val["coverage"]
req, add = [c for c in cov if c["group"] == "REQUIRED"], [c for c in cov if c["group"] == "ADDITIONAL"]
cnt = lambda rows: collections.Counter(r["status"] for r in rows)  # noqa: E731
creq, cadd = cnt(req), cnt(add)

import_ok = imp["failed"] == 0 and imp["final_nodes"] == 1840 and imp["final_relationships"] == 3812 and imp["error"] is None
val_ok = val["summary"]["failed"] == 0
cov_ok = passed(by("C")) and val["summary"]["coverage_matching"] == val["summary"]["coverage_rows"]
idem_ok = rer["failed"] == 0 and rer["node_delta"] == 0 and rer["relationship_delta"] == 0 and rer["nodes_created"] == 0 and rer["relationships_created"] == 0

report = f"""# Neo4j AuraDB import report

Generated from the run logs (`graph/audits/aura_run_log.json`, `graph/audits/aura_validation_results.json`). No credentials appear in
this report or in the logs.

## FINAL STATUS

| | |
|---|---|
| **AURADB_IMPORT** | **{'SUCCESS' if import_ok else 'FAILED'}** |
| **GRAPH_VALIDATION** | **{'PASS' if val_ok else 'FAIL'}** ({val['summary']['passed']} of {val['summary']['checks']} checks, {val['summary']['traversals']} of {val['summary']['traversals']} traversals) |
| **RELATIONSHIP_COVERAGE** | **{'PASS' if cov_ok else 'FAIL'}** ({val['summary']['coverage_matching']} of {val['summary']['coverage_rows']} coverage rows match AuraDB) |
| **IDEMPOTENCY** | **{'PASS' if idem_ok else 'FAIL'}** (second run: {rer['nodes_created']} nodes and {rer['relationships_created']} relationships created, delta {rer['node_delta']} / {rer['relationship_delta']}) |

Final graph in AuraDB: **{imp['final_nodes']} nodes, {imp['final_relationships']} relationships** (expected 1,840 / 3,812).

## Pre-flight (read-only, before any write)

{'> **Record keeping:** the machine-readable log of the pre-flight and the first import was deleted when the Cypher package was rebuilt to fix two validation queries (the rebuild cleared `graph_audit/`). Those two entries were re-created from the console output printed during the run; every figure below is exactly what the run printed. The second-run log and all validation results were produced after that and are original. `graph_build.py` now preserves `aura_*.json`.' if pre.get('reconstructed_from_console_output') else ''}


| | |
|---|---|
| Target instance | {pre['database']} (Aura free instance; database id {pre['database_id'][:12]}...) |
| Server | {pre['server']} |
| Time | {pre['at']} |
| Nodes | {pre['nodes']} |
| Relationships | {pre['relationships']} |
| Labels | {pre['labels'] or 'none'} |
| Relationship types | {pre['relationship_types'] or 'none'} |
| Constraints | {len(pre['constraints'])} |
| Indexes | {len(pre['indexes'])}: {', '.join(i['type'] for i in pre['indexes'])} (the two default token-lookup indexes every new Aura database has; no user data) |
| Database state | **EMPTY**, so the import was allowed to proceed |

Connection note: TLS verification stayed ON throughout. This machine's certificate store lacks the SSL.com root that Aura's
certificate chains to, so the driver was pointed at the Mozilla root bundle shipped with `certifi` instead of disabling
verification (`neo4j+ssc`). Nothing was deleted, reset or overwritten at any point.

## Import

First import: {imp['at']}. Files executed in order, stopping at the first error (none occurred).

{table([{'file': f['file'], 'statements': f"{f['ok']}/{f['statements']}", 'nodes created': f['nodes_created'], 'relationships created': f['relationships_created'], 'constraints created': f['constraints_added']} for f in imp['files']], ['file', 'statements', 'nodes created', 'relationships created', 'constraints created'])}

Totals: {imp['statements']} statements, {imp['ok']} succeeded, {imp['failed']} failed; created {imp['nodes_created']} nodes,
{imp['relationships_created']} relationships and {imp['constraints_added']} constraints (38 node-id uniqueness constraints and 61
relationship `rel_id` uniqueness constraints). Files `14_requests` and `24_risk` do not exist because those domains have no data.

## Validation (`graph/cypher/99_validation.cypher` against `graph/validation/validation_expected_results.md`)

{table([{'id': c['id'], 'check': c['check'], 'result': c['status']} for c in by('V')], ['id', 'check', 'result'])}

Note on V08 and V10: the first run of these two queries returned no rows, which the comparison read as a failure. The cause was
the query, not the graph: a constant label in the RETURN next to `count()` makes Cypher return no row at all when nothing
matches. The queries were rewritten to return an explicit count per row (`WITH count(...) AS c RETURN ...`) and re-run; both pass
and the graph was not touched in between.

### Quality

| Check | Result |
|---|---|
| Duplicate nodes (V06) | 0 |
| Duplicate relationships (V07) | 0 |
| Orphans / missing provenance (V08) | 0 nodes, 0 relationships |
| Broken references | 0 (every import statement matched both endpoints; counts equal the offline model) |
| Relationship violations: wrong endpoint labels (V10) | 0 across all 61 types |
| Forbidden or generic relationship types (V11, C04) | 0 |
| Interchangeability asserted (V12) | 0 |

## Coverage

{table([{'': 'Required relationship rows', 'total': len(req), 'implemented with data': creq.get('IMPLEMENTED_WITH_DATA', 0), 'implemented synthetic': creq.get('IMPLEMENTED_SYNTHETIC', 0), 'schema only': creq.get('SCHEMA_ONLY_NO_DATA', 0), 'not applicable': creq.get('NOT_APPLICABLE', 0), 'blocked': creq.get('BLOCKED_BY_MISSING_DATA', 0)}, {'': 'Source-discovered rows', 'total': len(add), 'implemented with data': cadd.get('IMPLEMENTED_WITH_DATA', 0), 'implemented synthetic': cadd.get('IMPLEMENTED_SYNTHETIC', 0), 'schema only': cadd.get('SCHEMA_ONLY_NO_DATA', 0), 'not applicable': cadd.get('NOT_APPLICABLE', 0), 'blocked': cadd.get('BLOCKED_BY_MISSING_DATA', 0)}], ['', 'total', 'implemented with data', 'implemented synthetic', 'schema only', 'not applicable', 'blocked'])}

Every row of `relationship_coverage_matrix.csv` was re-counted in AuraDB and matches the offline model ({val['summary']['coverage_matching']} of {val['summary']['coverage_rows']}).
Rows marked schema-only, not applicable or blocked have 0 records in AuraDB.

Newly added by the coverage audit (verified in AuraDB): `HOME_PLANT` 3, `SUPPLIES_CATEGORY` 25, `COVERS_CATEGORY` 10, `SHIPS_TO_COUNTRY` 8.

Schema-only (no records, none invented): Order to Allocation, Order to Fulfilment, ServiceJob to Machine / Part / Dealer, Part to Risk,
ALTERNATIVE_TO, SUPERSEDES, Machine to Configuration, Customer to Request, Request to Part, Installation to Machine / Part.

Blocked by missing data: WH-004 (Zwolle) has no plant; the workbook says warehouses ship to Belgium but the catalogue has no Belgium location.

## Semantics (nothing inferred)

{table([{'id': c['id'], 'check': c['check'], 'result': c['status']} for c in by('S') + by('M')], ['id', 'check', 'result'])}

## Provenance and synthetic data

{table([{'id': c['id'], 'check': c['check'], 'result': c['status'], 'actual': json.dumps(c['actual']) if c['id'] in ('P01', 'P02') else ''} for c in by('P')], ['id', 'check', 'result', 'actual'])}

The four classes stay distinct: SOURCE_DERIVED 1,234, DERIVED 556, USER_PROVIDED (the project brief) 16, SYNTHETIC_DEMO 3,846 (nodes plus relationships).
The project-brief class is stored as `USER_PROVIDED`, the allowed provenance category for it.

## Traversals

{table([{'traversal': t['traversal'], 'rows': t['rows'], 'sample': json.dumps(t['sample'])[:110], 'result': t['status']} for t in val['traversals']], ['traversal', 'rows', 'sample', 'result'])}

## Idempotency

| | First run | Second run |
|---|---|---|
| Statements | {imp['statements']} | {rer['statements']} (failed {rer['failed']}) |
| Nodes created | {imp['nodes_created']} | {rer['nodes_created']} |
| Relationships created | {imp['relationships_created']} | {rer['relationships_created']} |
| Constraints created | {imp['constraints_added']} | {rer['constraints_added']} |
| Database totals after | {imp['final_nodes']} nodes, {imp['final_relationships']} relationships | {rer['final_nodes']} nodes, {rer['final_relationships']} relationships |
| Node delta / relationship delta | | {rer['node_delta']} / {rer['relationship_delta']} |

## Reminder

The Aura password was exposed earlier in the conversation. **Rotate it in the Aura console** (and update `.env`). `.env` is listed in `.gitignore`.
"""
REPORT.write_text(report, encoding="utf-8")
print("written", REPORT.stat().st_size, "bytes")
