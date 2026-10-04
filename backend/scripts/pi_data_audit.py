"""Read-only Neo4j data-completeness audit for Parts Intelligence.

Usage (from backend/):  python scripts/pi_data_audit.py [label]
Writes graph/audits/pi_data_audit_<label>.json (label defaults to "current"). Never writes to the graph.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.graph.client import GraphClient  # noqa: E402

AUDITS = ROOT / "graph" / "audits"

CHECKS = {
    "labels": "MATCH (n) UNWIND labels(n) AS l RETURN l AS key, count(*) AS n ORDER BY key",
    "relationships": "MATCH ()-[r]->() RETURN type(r) AS key, count(*) AS n ORDER BY key",
    "node_data_status": "MATCH (n) RETURN coalesce(n.data_status, 'MISSING') AS key, count(*) AS n ORDER BY key",
    "rel_data_status": "MATCH ()-[r]->() RETURN coalesce(r.data_status, 'MISSING') AS key, count(*) AS n ORDER BY key",
}
# part coverage: how many of the parts have each relationship (missing = not connected, never zero)
PART_COVERAGE = """
MATCH (p:Part)
RETURN count(p) AS parts,
  sum(CASE WHEN EXISTS { (p)-[:FITS]->(:Machine) } THEN 1 ELSE 0 END) AS fitment,
  sum(CASE WHEN EXISTS { (p)-[:IN_CATEGORY]->(:Category) } THEN 1 ELSE 0 END) AS category,
  sum(CASE WHEN EXISTS { (p)-[:SUPPLIED_BY]->(:Supplier) } THEN 1 ELSE 0 END) AS supplier,
  sum(CASE WHEN EXISTS { (p)-[:STOCKED_BY]->(:Dealer) } THEN 1 ELSE 0 END) AS dealer,
  sum(CASE WHEN EXISTS { (p)-[:AVAILABLE_AT]->(:Warehouse) } THEN 1 ELSE 0 END) AS warehouse,
  sum(CASE WHEN EXISTS { (p)-[:PART_OF]->(:Assembly) } THEN 1 ELSE 0 END) AS assembly,
  sum(CASE WHEN EXISTS { (p)-[:HAS_COMPLIANCE]->() } THEN 1 ELSE 0 END) AS compliance,
  sum(CASE WHEN EXISTS { (:PartCatalogProfile)-[:PROFILES_PART]->(p) } THEN 1 ELSE 0 END) AS profile,
  sum(CASE WHEN EXISTS { ()-[:PRICES_PART]->(p) } THEN 1 ELSE 0 END) AS price,
  sum(CASE WHEN EXISTS { (p)-[:HAS_LEGACY_REFERENCE]->() } THEN 1 ELSE 0 END) AS legacy,
  sum(CASE WHEN EXISTS { (p)-[:HAS_SPECIFICATION]->() } THEN 1 ELSE 0 END) AS specification,
  sum(CASE WHEN EXISTS { (p)-[:RELATED_COMPONENT|CO_ORDERED_WITH|SAME_NAME_GROUP_AS]-(:Part) } THEN 1 ELSE 0 END) AS related,
  sum(CASE WHEN EXISTS { (:ServicePlan)-[:REQUIRES_PART]->(p) } THEN 1 ELSE 0 END) AS service_plan,
  sum(CASE WHEN EXISTS { (:OrderLine)-[:REFERENCES_PART]->(p) } THEN 1 ELSE 0 END) AS ordered,
  sum(CASE WHEN p.name IS NULL OR p.name = '' THEN 1 ELSE 0 END) AS missing_name,
  sum(CASE WHEN p.data_status IS NULL THEN 1 ELSE 0 END) AS missing_data_status
"""
OTHER_COVERAGE = {
    "machines_without_parts": "MATCH (m:Machine) WHERE NOT EXISTS { (:Part)-[:FITS]->(m) } RETURN collect(m.model_code) AS v",
    "machines_without_family": "MATCH (m:Machine) WHERE NOT EXISTS { (m)-[:MEMBER_OF_FAMILY]->() } RETURN collect(m.model_code) AS v",
    "machines_without_plant": "MATCH (m:Machine) WHERE NOT EXISTS { (m)-[:MANUFACTURED_AT]->() } RETURN collect(m.model_code) AS v",
    "suppliers_without_parts": "MATCH (s:Supplier) WHERE NOT EXISTS { (:Part)-[:SUPPLIED_BY]->(s) } RETURN collect(s.name) AS v",
    "dealers_without_parts": "MATCH (d:Dealer) WHERE NOT EXISTS { (:Part)-[:STOCKED_BY]->(d) } RETURN collect(d.name) AS v",
    "dealers_without_city": "MATCH (d:Dealer) WHERE d.city IS NULL RETURN collect(d.name) AS v",
    "suppliers_without_city": "MATCH (s:Supplier) WHERE s.city IS NULL RETURN collect(s.name) AS v",
    "assemblies_without_parts": "MATCH (a:Assembly) WHERE NOT EXISTS { (:Part)-[:PART_OF]->(a) } RETURN collect(a.name) AS v",
    "orders_without_lines": "MATCH (o:Order) WHERE NOT EXISTS { (o)-[:CONTAINS_LINE]->() } RETURN collect(o.order_id) AS v",
    "shipments_without_events": "MATCH (s:Shipment) WHERE NOT EXISTS { (s)-[:HAS_TRACKING_EVENT]->() } RETURN collect(s.shipment_id) AS v",
    "fits_without_status": "MATCH (:Part)-[f:FITS]->(:Machine) WHERE f.fitment_status IS NULL RETURN count(f) AS v",
    "rels_without_rel_id": "MATCH ()-[r]->() WHERE r.rel_id IS NULL RETURN count(r) AS v",
    "duplicate_part_numbers": "MATCH (p:Part) WITH p.part_number AS k, count(*) AS c WHERE c > 1 RETURN collect(k) AS v",
    "duplicate_model_codes": "MATCH (m:Machine) WITH m.model_code AS k, count(*) AS c WHERE c > 1 RETURN collect(k) AS v",
    "orphan_nodes": "MATCH (n) WHERE NOT (n)--() RETURN count(n) AS v",
    "synthetic_nodes_without_label": "MATCH (n) WHERE n.data_status = 'SYNTHETIC_DEMO' AND NOT any(k IN keys(n) WHERE k IN ['name','part_number','model_code','order_id','shipment_id','service_plan_id','compliance_id','assembly_id','warehouse_id','dealer_id','supplier_id','event_id','line_id','address_id','user_id','cart_id','profile_id','price_id']) RETURN count(n) AS v",
}


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "current"
    g = GraphClient(get_settings())
    out: dict = {}
    for name, q in CHECKS.items():
        out[name] = {r["key"]: r["n"] for r in g.read(q)}
    out["part_coverage"] = g.read(PART_COVERAGE)[0]
    out["gaps"] = {name: g.read(q)[0]["v"] for name, q in OTHER_COVERAGE.items()}
    g.close()
    AUDITS.mkdir(parents=True, exist_ok=True)
    path = AUDITS / f"pi_data_audit_{label}.json"
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
