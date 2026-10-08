"""Lifecycle inspection, relationship migration, data-quality checks and the golden-scenario run, against the graph. Read-only except `migrate(apply=True)`.

The migration is the one deliberate deletion of this phase: the Phase 1 relationship names on installations were replaced by the lifecycle vocabulary. A relationship
is removed only when (a) it carries the canonical ingestion's own source id (a synthetic record this system wrote) and (b) its replacement already exists between the same
two nodes. Nothing protected, app-written or without a replacement is touched.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.canonical.io import CANON_DIR
from app.graph.client import GraphClient
from app.lifecycle import rules
from app.lifecycle.context import WarrantyContextBuilder
from app.lifecycle.readers import GraphReader, LifecycleReader

CANON = "SRC-CANON"
RENAMES = (("OF_PART", "INSTALLED_PART"), ("INSTALLED_BY_DEALER", "PERFORMED_AT"), ("INSTALLED_BY_TECHNICIAN", "PERFORMED_BY"), ("UNDER_WORK_ORDER", "RECORDED_IN"))
LIFECYCLE_LABELS = ("MachineInstance", "Technician", "WorkOrder", "InstallationEvent", "ReplacementEvent", "WarrantyPolicy", "WarrantyClaim", "Evidence")
LIFECYCLE_RELS = ("HAS_INSTALLATION", "INSTALLED_PART", "PERFORMED_BY", "PERFORMED_AT", "RECORDED_IN", "HAS_WORK_ORDER", "PERFORMED_BY_DEALER", "ASSIGNED_TO", "HAS_REPLACEMENT",
                  "REMOVED_INSTALLATION", "NEW_INSTALLATION", "HAS_CLAIM", "CLAIM_ON_INSTALLATION", "CLAIM_FOR_PART", "FILED_BY_DEALER", "SUPPORTS", "WARRANTY_FOR_PART", "EMPLOYED_BY")
GOLDEN = CANON_DIR / "reference" / "lifecycle_scenarios.json"


def counts(g: GraphClient) -> dict[str, Any]:
    nodes = {label: g.read(f"MATCH (n:`{label}`) RETURN count(n) AS n")[0]["n"] for label in LIFECYCLE_LABELS}
    rels = {t: g.read(f"MATCH ()-[r:`{t}`]->() RETURN count(r) AS n")[0]["n"] for t in (*LIFECYCLE_RELS, *(old for old, _ in RENAMES))}
    return {"nodes": nodes, "relationships": {k: v for k, v in rels.items() if v}}


def migrate(g: GraphClient, apply: bool = False) -> dict[str, Any]:
    """Remove the superseded relationship names. Reports what each rename would remove, and what stays because its replacement is missing."""
    out: dict[str, Any] = {}
    for old, new in RENAMES:
        match = f"MATCH (a)-[o:`{old}`]->(b) WHERE o.source_id = $src"
        total = g.read(f"{match} RETURN count(o) AS n", src=CANON)[0]["n"]
        replaced = g.read(f"{match} AND (a)-[:`{new}`]->(b) RETURN count(o) AS n", src=CANON)[0]["n"]
        other = g.read(f"MATCH ()-[o:`{old}`]->() WHERE coalesce(o.source_id, '') <> $src RETURN count(o) AS n", src=CANON)[0]["n"]
        removed = 0
        if apply and replaced:
            removed = g.write(f"{match} AND (a)-[:`{new}`]->(b) DELETE o RETURN count(*) AS n", src=CANON)[0]["n"]
        out[old] = {"replacement": new, "canonical_relationships": total, "have_replacement": replaced, "kept_no_replacement": total - replaced, "not_ours_untouched": other, "removed": removed}
    return out


def _zero(g: GraphClient, name: str, query: str, **params: Any) -> dict[str, Any]:
    n = g.read(query, **params)[0]["n"]
    return {"check": name, "violations": n, "ok": n == 0}


def quality(g: GraphClient, reader: LifecycleReader | None = None) -> dict[str, Any]:
    """Data-quality checks; every one must be 0 violations. `INCOMPLETE` installations are legitimate records with a stated reason, not violations."""
    checks = [
        _zero(g, "installations not attached to a machine", "MATCH (i:InstallationEvent) WHERE NOT ()-[:HAS_INSTALLATION]->(i) RETURN count(i) AS n"),
        _zero(g, "installations without a part", "MATCH (i:InstallationEvent) WHERE NOT (i)-[:INSTALLED_PART]->(:Part) RETURN count(i) AS n"),
        _zero(g, "installations without a dealer", "MATCH (i:InstallationEvent) WHERE NOT (i)-[:PERFORMED_AT]->(:Dealer) RETURN count(i) AS n"),
        _zero(g, "VALID installations without a technician or work order",
              "MATCH (i:InstallationEvent {validation_status: 'VALID'}) WHERE NOT (i)-[:PERFORMED_BY]->(:Technician) OR NOT (i)-[:RECORDED_IN]->(:WorkOrder) RETURN count(i) AS n"),
        _zero(g, "installations with no validation_status", "MATCH (i:InstallationEvent) WHERE i.validation_status IS NULL RETURN count(i) AS n"),
        _zero(g, "installation status contradicts removal date",
              "MATCH (i:InstallationEvent) WHERE (i.status = 'CURRENT' AND i.removal_date IS NOT NULL) OR (i.status = 'REMOVED' AND i.removal_date IS NULL) RETURN count(i) AS n"),
        _zero(g, "technician works for a different dealer than the installation",
              "MATCH (i:InstallationEvent)-[:PERFORMED_BY]->(t:Technician)-[:EMPLOYED_BY]->(d:Dealer) WHERE NOT (i)-[:PERFORMED_AT]->(d) RETURN count(i) AS n"),
        _zero(g, "work orders without a machine", "MATCH (w:WorkOrder) WHERE NOT ()-[:HAS_WORK_ORDER]->(w) RETURN count(w) AS n"),
        _zero(g, "work orders without a dealer", "MATCH (w:WorkOrder) WHERE NOT (w)-[:PERFORMED_BY_DEALER]->(:Dealer) RETURN count(w) AS n"),
        _zero(g, "work orders recording no event", "MATCH (w:WorkOrder) WHERE NOT ()-[:RECORDED_IN]->(w) RETURN count(w) AS n"),
        _zero(g, "replacements without a removed or new installation",
              "MATCH (r:ReplacementEvent) WHERE NOT (r)-[:REMOVED_INSTALLATION]->(:InstallationEvent) OR NOT (r)-[:NEW_INSTALLATION]->(:InstallationEvent) RETURN count(r) AS n"),
        _zero(g, "replacements not attached to a machine", "MATCH (r:ReplacementEvent) WHERE NOT ()-[:HAS_REPLACEMENT]->(r) RETURN count(r) AS n"),
        _zero(g, "claims without a machine, part or installation",
              "MATCH (c:WarrantyClaim) WHERE NOT ()-[:HAS_CLAIM]->(c) OR NOT (c)-[:CLAIM_FOR_PART]->(:Part) OR NOT (c)-[:CLAIM_ON_INSTALLATION]->(:InstallationEvent) RETURN count(c) AS n"),
        _zero(g, "evidence supporting nothing", "MATCH (e:Evidence) WHERE NOT (e)-[:SUPPORTS]->() RETURN count(e) AS n"),
        _zero(g, "warranty policies without a part", "MATCH (w:WarrantyPolicy) WHERE NOT (w)-[:WARRANTY_FOR_PART]->(:Part) RETURN count(w) AS n"),
        _zero(g, "superseded relationship names still present on canonical records",
              "MATCH ()-[o]->() WHERE type(o) IN ['OF_PART','INSTALLED_BY_DEALER','INSTALLED_BY_TECHNICIAN','UNDER_WORK_ORDER'] AND o.source_id = $src RETURN count(o) AS n", src=CANON),
        _zero(g, "duplicate relationships between the same two nodes",
              "MATCH (a)-[r]->(b) WHERE type(r) IN $types WITH a, b, type(r) AS t, count(*) AS c WHERE c > 1 RETURN count(*) AS n", types=list(LIFECYCLE_RELS)),
    ]
    for label, key in (("MachineInstance", "machine_instance_id"), ("Technician", "technician_id"), ("WorkOrder", "work_order_id"), ("InstallationEvent", "installation_id"),
                       ("ReplacementEvent", "replacement_id"), ("WarrantyPolicy", "warranty_policy_id"), ("WarrantyClaim", "claim_id"), ("Evidence", "evidence_id")):
        checks.append(_zero(g, f"duplicate {key}", f"MATCH (n:`{label}`) WITH n.{key} AS id, count(*) AS c WHERE c > 1 RETURN count(*) AS n"))

    reader = reader or GraphReader(g)
    issues: list[str] = []
    for mid in reader.instance_ids():
        instance, installs = reader.instance(mid), reader.installations(mid)
        by_id = {i["installation_id"]: i for i in installs}
        for i in installs:
            status, found = rules.validate_installation(i, instance, reader.part(i["part_id"]), reader.dealer(i["dealer_id"]) if i["dealer_id"] else None,
                                                        reader.technician(i["technician_id"]) if i["technician_id"] else None,
                                                        reader.work_order(i["work_order_id"]) if i["work_order_id"] else None)
            if (status, found) != (i["validation_status"], i["validation_issues"]):
                issues.append(f"{i['installation_id']}: stored validation differs from the rules ({i['validation_status']} {i['validation_issues']} vs {status} {found})")
        for r in reader.replacements(mid):
            errs = rules.replacement_chronology_errors(r, by_id.get(r["removed_installation_id"]), by_id.get(r["new_installation_id"]))
            if errs:
                issues.append(f"{r['replacement_id']}: {', '.join(errs)}")
        slots: dict[str, list[str]] = {}
        for i in rules.current_installations(installs):
            slots.setdefault(i["part_id"], []).append(i["installation_id"])
        # the same part may legitimately be fitted twice (two units); a part with a REPLACEMENT chain has exactly one current installation per chain end
        for r in reader.replacements(mid):
            if r["removed_installation_id"] in by_id and not by_id[r["removed_installation_id"]].get("removal_date"):
                issues.append(f"{r['replacement_id']}: the removed installation has no removal date")
        for c in reader.claims(mid):
            if c["status"] in ("APPROVED", "REJECTED"):
                ctx = WarrantyContextBuilder(reader).for_claim(c["claim_id"])
                if rules.claim_status_for(ctx.outcome)[0] != c["status"]:
                    issues.append(f"{c['claim_id']}: recorded {c['status']} but the rules give {ctx.outcome}")
    checks.append({"check": "chronology, validation and decided claims agree with the rules", "violations": len(issues), "ok": not issues, "issues": issues})
    return {"checks": checks, "ok": all(c["ok"] for c in checks)}


def golden(reader: LifecycleReader) -> list[dict[str, Any]]:
    """Evaluate every golden scenario and compare with the outcome the scenario file states."""
    builder = WarrantyContextBuilder(reader)
    out = []
    for s in json.loads(Path(GOLDEN).read_text(encoding="utf-8"))["scenarios"]:
        ctx = builder.for_claim(s["claim_id"])
        out.append({"scenario_id": s["scenario_id"], "claim_id": s["claim_id"], "expected": s["expected_outcome"], "outcome": ctx.outcome, "match": ctx.outcome == s["expected_outcome"],
                    "reasons": ctx.reasons, "coverage": [ctx.coverage_start, ctx.coverage_end], "evidence": [e["evidence_id"] for e in ctx.evidence], "missing": ctx.missing})
    return out
