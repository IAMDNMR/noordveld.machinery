"""Canonical data commands.

  python backend/scripts/canonical.py export [--dataset NAME ...]   graph -> canonical files (read-only on the graph)
  python backend/scripts/canonical.py generate                      deterministic synthetic lifecycle + scenario files
  python backend/scripts/canonical.py network                       the Phase 2 global network, validated and expanded from reference/network_definition.json
  python backend/scripts/canonical.py validate [--dataset NAME ...] schema + references among the files (offline, no graph)
  python backend/scripts/canonical.py dry-run [--dataset NAME ...]  full plan against the graph, writes nothing
  python backend/scripts/canonical.py ingest --yes [--dataset ...]  MERGE into Neo4j (idempotent), then checksums and a report
  python backend/scripts/canonical.py verify [--dataset NAME ...]   re-plan: after an ingestion nothing is left to create or update
  python backend/scripts/canonical.py checksum                      dataset checksums, graph fingerprint, integrity baseline
  python backend/scripts/canonical.py lifecycle-report              Phase 3: counts, data-quality checks and the golden warranty scenarios against the graph (read-only)
  python backend/scripts/canonical.py migrate-lifecycle [--yes]     Phase 3: remove the superseded installation relationship names once their replacements exist (dry run without --yes)

Nothing is ever deleted (the one scoped exception is migrate-lifecycle, see app/lifecycle/audit.py). Protected and app-written graph records are only compared (see app/canonical/engine.py).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(1, str(BACKEND / "scripts" / "eu_foundation"))
logging.disable(logging.CRITICAL)

from app.canonical import SCHEMA_VERSION
from app.canonical.engine import Engine, write_report
from app.canonical.integrity import graph_fingerprint
from app.canonical.io import CANON_DIR, read_manifest, write_manifest
from app.canonical.registry import BY_NAME
from app.canonical.store import Neo4jStore
from app.core.config import get_settings

REPORTS = CANON_DIR / "reports"
INTEGRITY = CANON_DIR / "integrity.json"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def source_checksum() -> str:
    from audit_before import (
        source_checksum as sc,  # the existing SOURCE/DERIVED DATA INTEGRITY CHECKSUM, reused unchanged
    )
    return sc()


def baseline_checksum() -> str | None:
    p = BACKEND / "data" / "eu_foundation" / "audit_before.json"
    return json.loads(p.read_text(encoding="utf-8")).get("source_checksum") if p.exists() else None


def refresh_manifest(report: dict) -> None:
    entries = read_manifest().get("datasets", {})
    for d in report["datasets"]:
        if d["records_invalid"] == 0 and d["records_read"]:
            entries[d["dataset"]] = {"path": BY_NAME[d["dataset"]].path, "dataset_version": d["version"], "records": d["records_valid"], "checksum": d["checksum"]}
    write_manifest(entries, now())


def show(report: dict) -> None:
    cols = ["dataset", "records_read", "records_valid", "records_invalid", "nodes_to_create", "nodes_to_update", "relationships_to_create", "relationships_to_update",
            "records_verified", "records_extension_pending", "records_drift", "records_unchanged"]
    print(" | ".join(c.replace("records_", "").replace("relationships_", "rels_").replace("_to_", ">") for c in cols))
    for d in report["datasets"]:
        print(" | ".join(str(d[c]) for c in cols))
    t = report["totals"]
    print("TOTAL", {k: t.get(k, 0) for k in cols[1:]})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["export", "generate", "network", "validate", "dry-run", "ingest", "verify", "checksum", "lifecycle-report", "migrate-lifecycle"])
    ap.add_argument("--dataset", nargs="*", default=None)
    ap.add_argument("--yes", action="store_true", help="required for ingest: confirms writing to the configured Neo4j database")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    a = ap.parse_args()

    if a.command == "export":
        from app.canonical.export import export_all
        counts = export_all(CANON_DIR, now(), a.dataset)
        report = Engine(None).run(list(counts))
        refresh_manifest(report)
        print(json.dumps(counts, indent=1))
        return 0
    if a.command == "generate":
        from app.canonical.generate import generate
        counts = generate(CANON_DIR, now())
        report = Engine(None).run(list(counts))
        refresh_manifest(report)
        print(json.dumps(counts, indent=1))
        return 0
    if a.command == "network":
        from app.canonical.network import generate as generate_network
        counts = generate_network(CANON_DIR, now())
        report = Engine(None).run(list(counts))
        refresh_manifest(report)
        print(json.dumps(counts, indent=1))
        return 1 if any(d["records_invalid"] for d in report["datasets"]) else 0
    if a.command == "validate":
        report = Engine(None).run(a.dataset, dry_run=True)
        refresh_manifest(report) if not a.dataset else None
        show(report) if not a.json else print(json.dumps(report, indent=1))
        bad = sum(d["records_invalid"] for d in report["datasets"])
        print(f"\noffline validation: {report['totals'].get('records_read', 0)} records read, {bad} invalid, "
              f"{report['totals'].get('unresolved_graph_references', 0)} references to the graph not checked offline")
        return 1 if bad else 0

    settings = get_settings()
    if not settings.graph_configured:
        print("Neo4j is not configured (NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD)")
        return 2
    if a.command in ("lifecycle-report", "migrate-lifecycle"):
        import dataclasses

        from app.graph.client import GraphClient
        from app.lifecycle import audit
        g = GraphClient(dataclasses.replace(settings, neo4j_query_timeout=120.0))
        try:
            if a.command == "migrate-lifecycle":
                print(json.dumps(audit.migrate(g, apply=a.yes), indent=1))
                print("applied" if a.yes else "dry run: re-run with --yes to remove the superseded relationships")
                return 0
            report = {"generated_at": now(), "counts": audit.counts(g), "quality": audit.quality(g), "golden": audit.golden(audit.GraphReader(g))}
            REPORTS.mkdir(parents=True, exist_ok=True)
            path = REPORTS / "lifecycle_report.json"
            path.write_text(json.dumps(report, indent=1), encoding="utf-8")
            print(json.dumps({"counts": report["counts"], "quality_ok": report["quality"]["ok"], "failed_checks": [c for c in report["quality"]["checks"] if not c["ok"]],
                              "golden": [{k: x[k] for k in ("scenario_id", "expected", "outcome", "match")} for x in report["golden"]]}, indent=1))
            print(f"\nreport: {path.relative_to(BACKEND.parent)}")
            return 0 if report["quality"]["ok"] and all(x["match"] for x in report["golden"]) else 1
        finally:
            g.close()
    store = Neo4jStore(settings)
    try:
        if a.command == "checksum":
            print(json.dumps({"canonical_schema_version": SCHEMA_VERSION, "source_checksum": source_checksum(), "baseline_source_checksum": baseline_checksum(),
                              "graph_fingerprint": graph_fingerprint(store), "datasets": read_manifest().get("datasets", {}),
                              "integrity_baseline": json.loads(INTEGRITY.read_text(encoding="utf-8")) if INTEGRITY.exists() else None}, indent=1))
            return 0
        write = a.command == "ingest"
        if write and not a.yes:
            print("ingest writes to the configured Neo4j database: re-run with --yes")
            return 2
        before = source_checksum() if write else None
        report = Engine(store).run(a.dataset, dry_run=not write)
        label = "ingest" if write else "dry-run" if a.command == "dry-run" else "verify"
        if write:
            after = source_checksum()
            report["source_checksum_before"], report["source_checksum_after"], report["source_checksum_unchanged"] = before, after, before == after
            report["graph_fingerprint"] = graph_fingerprint(store)
            INTEGRITY.write_text(json.dumps({"canonical_schema_version": SCHEMA_VERSION, "updated_at": now(), "source_checksum": after, "graph_fingerprint": report["graph_fingerprint"],
                                             "datasets": {d["dataset"]: d["checksum"] for d in report["datasets"]}}, indent=1) + "\n", encoding="utf-8")
        path = write_report(report, REPORTS, label)
        show(report) if not a.json else print(json.dumps(report, indent=1))
        print(f"\nreport: {path.relative_to(BACKEND.parent)}")
        if write:
            print(f"source checksum unchanged: {report['source_checksum_unchanged']}   graph fingerprint: {report['graph_fingerprint'][:16]}…")
        if a.command == "verify":
            pending = report["totals"].get("nodes_to_create", 0) + report["totals"].get("nodes_to_update", 0) + report["totals"].get("relationships_to_create", 0) \
                + report["totals"].get("relationships_to_update", 0)
            print(f"verify: {pending} writes still pending")
            return 1 if pending else 0
        return 1 if any(d["records_invalid"] for d in report["datasets"]) else 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
