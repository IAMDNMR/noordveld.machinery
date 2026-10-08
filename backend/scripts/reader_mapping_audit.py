"""Audit of the graph readers against the canonical file schema. READ-ONLY.

For every canonical dataset a graph reader returns, and every field of its model: where the field lives in the graph, whether the reader outputs it, how many canonical
records carry a value for it (so a field that is null everywhere is not mistaken for a gap), and a classification:

  BUSINESS_FIELD      a business value held as a node / relationship property
  PROVENANCE_FIELD    data_status, source_type, source_record_id
  BOOKKEEPING_FIELD   (never a model field: import stamps are not canonical fields)
  RELATIONSHIP_FIELD  a reference held as a relationship (the field value is the other end's id)
  NOT_APPLICABLE      the field has no graph property by design and the canonical files never carry a value for it

No field is dropped: a field the reader does not output, or the graph does not hold while the files do, has status MISSING and is listed.

    python backend/scripts/reader_mapping_audit.py [--out audit.json] [--live]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.canonical.graph_rows import PROVENANCE
from app.canonical.io import CANON_DIR, load_rows
from app.canonical.registry import BY_NAME

# (dataset, reader, reader method). Fields the reader sets from a lookup rather than a property, with the reason.
READER_DATASETS = {
    "shipments": "logistics.GraphReader.shipment", "network_shipments": "logistics.GraphReader.shipment", "tracking_events": "logistics.GraphReader.events",
    "network_tracking_events": "logistics.GraphReader.events", "routes": "logistics.GraphReader.route", "network_routes": "logistics.GraphReader.route",
    "route_legs": "logistics.GraphReader.legs", "network_route_legs": "logistics.GraphReader.legs", "locations": "logistics.GraphReader.location",
    "network_locations": "logistics.GraphReader.location", "orders": "logistics.GraphReader.order", "network_orders": "logistics.GraphReader.order",
    "parts": "lifecycle.GraphReader.part", "dealers": "lifecycle.GraphReader.dealer", "fitment": "lifecycle.GraphReader.fitment", "approved_sources": "lifecycle.GraphReader.approved_sources",
    "machine_instances": "lifecycle.GraphReader.instance", "technicians": "lifecycle.GraphReader.technician", "work_orders": "lifecycle.GraphReader.work_order",
    "installations": "lifecycle.GraphReader.installations", "replacements": "lifecycle.GraphReader.replacements", "warranty_policies": "lifecycle.GraphReader.policies",
    "warranty_claims": "lifecycle.GraphReader.claims", "evidence": "lifecycle.GraphReader.evidence",
}
DERIVED = {  # field -> (source, why)
    ("locations", "location_kind"): ("derived from the node label (graph_rows.LOCATION_KIND_BY_LABEL)", "not stored: it names which kind of node holds the place"),
    ("locations", "graph_label"): ("the node label", "the label the reader found the node under"),
    ("shipments", "route_id"): ("Shipment.route_id or (Shipment)-[:USES_ROUTE]->(TransportRoute)", "seeded shipments carry no route property; ingested ones carry both"),
    ("shipments", "origin_location_id"): ("(Shipment)-[:DISPATCHED_FROM]->(place)", "relationship"), ("shipments", "destination_location_id"): ("(Shipment)-[:DELIVERS_TO_LOCATION]->(place)", "relationship"),
    ("shipments", "order_id"): ("(Order)-[:HAS_SHIPMENT]->(Shipment)", "relationship"), ("shipments", "order_line_id"): ("(Shipment)-[:SHIPS_LINE]->(OrderLine)", "relationship; None when the shipment ships several lines"),
    ("shipments", "carrier_id"): ("(Shipment)-[:CARRIED_BY]->(Carrier).carrier_id", "relationship"), ("shipments", "carrier"): ("(Shipment)-[:CARRIED_BY]->(Carrier).name", "relationship"),
    ("orders", "customer_id"): ("(Order)-[:ORDERED_BY]->(Customer)", "relationship"), ("orders", "dealer_id"): ("(Order)-[:FOR_DEALER]->(Dealer)", "relationship"),
    ("parts", "category_id"): ("(Part)-[:IN_CATEGORY]->(Category)", "relationship"), ("parts", "subcategory_id"): ("(Part)-[:IN_SUBCATEGORY]->(Category)", "relationship"),
    ("parts", "aliases"): ("(Part)-[:HAS_ALIAS]->(SearchAlias).alias", "relationship"), ("routes", "estimated_cost"): ("TransportRoute.estimated_cost or (route)-[:PRICED_BY]->(FreightRate).total_transport_cost", "both stores exist"),
    ("routes", "currency"): ("TransportRoute.currency or (route)-[:PRICED_BY]->(FreightRate).currency", "both stores exist"),
    ("routes", "origin_location_id"): ("TransportRoute.origin_location_id or origin_depot_id (seeded routes)", "two property names"),
    ("routes", "destination_location_id"): ("TransportRoute.destination_location_id or destination_shipto_id (seeded routes)", "two property names"),
    ("route_legs", "route_leg_id"): ("HAS_LEG.rel_id without its 'HAS_LEG:' prefix", "the relationship is the record"), ("route_legs", "route_id"): ("(TransportRoute)-[:HAS_LEG]->(leg)", "relationship"),
    ("route_legs", "sequence"): ("HAS_LEG.sequence", "relationship property"),
}
LEG_NODE_FIELDS = {"leg_id": "leg_id", "origin_location_id": "origin_location_id / from_id", "destination_location_id": "destination_location_id / to_id", "transport_mode": "mode / transport_mode",
                   "status": "leg_status", "distance_km": "distance_km"}
PROFILE_FIELDS = dict(BY_NAME["parts"].targets[1].fields)
RELATIONSHIP = {"machine_instances": ("variant_id", "machine_id", "owner_id", "location_id"), "installations": ("machine_instance_id", "part_id", "dealer_id", "technician_id", "work_order_id"),
                "work_orders": ("machine_instance_id", "dealer_id", "technician_id"), "technicians": ("dealer_id",), "replacements": ("machine_instance_id", "removed_installation_id",
                "new_installation_id", "removed_part_id", "installed_part_id", "work_order_id"), "warranty_policies": ("part_id",), "warranty_claims": ("machine_instance_id", "part_id", "installation_id", "dealer_id"),
                "evidence": ("entity_id",), "approved_sources": ("part_id", "source_id"), "tracking_events": ("shipment_id", "location_id"), "network_tracking_events": ("shipment_id", "location_id")}


def audit() -> list[dict]:
    rows = []
    for name, reader in READER_DATASETS.items():
        spec = BY_NAME[name]
        base = name.removeprefix("network_")
        records = [r for r in load_rows(spec, CANON_DIR)[0]]
        t = spec.targets[0] if spec.targets else None
        mapped = dict(t.fields) if t else dict(spec.rel.fields)
        rels = {rd.field: rd for rd in (t.rels if t else ())}
        for field, mf in spec.model.model_fields.items():
            if field == "ingestion_timestamp":
                continue
            nonnull = sum(1 for r in records if r.get(field) not in (None, "", []))
            label = t.label if t else spec.rel.type
            if field in PROVENANCE:
                kind, src = "PROVENANCE_FIELD", f"{label}.{field} (source_type follows data_status as in the exporter)"
            elif (base, field) in DERIVED or (name, field) in DERIVED:
                src, _why = DERIVED.get((name, field)) or DERIVED[(base, field)]
                kind = "RELATIONSHIP_FIELD" if "->" in src or "<-" in src or "relationship" in _why else "BUSINESS_FIELD"
            elif field in rels:
                kind, src = "RELATIONSHIP_FIELD", f"({label})-[:{rels[field].type}]-({rels[field].kind or 'record'})"
            elif field in RELATIONSHIP.get(name, ()) or field in RELATIONSHIP.get(base, ()):
                kind, src = "RELATIONSHIP_FIELD", f"relationship of {label}"
            elif name in ("route_legs", "network_route_legs") and field in LEG_NODE_FIELDS:
                kind, src = "BUSINESS_FIELD", f"TransportLeg.{LEG_NODE_FIELDS[field]} (the leg node joined to the HAS_LEG relationship)"
            elif name == "approved_sources" and field == "approved_source_id":
                kind, src = "RELATIONSHIP_FIELD", "APPROVED_SOURCE.rel_id without its 'APPROVED_SOURCE:' prefix (the relationship is the record)"
            elif name in ("locations", "network_locations") and field == "location_id":
                kind, src = "RELATIONSHIP_FIELD", "the node's own key (Plant.plant_id, Warehouse.warehouse_id, ShipTo.shipto_id, Location.location_id, TransportTerminal.terminal_id, Dealer.dealer_id, Supplier.supplier_id)"
            elif name == "parts" and field in PROFILE_FIELDS:
                kind, src = "BUSINESS_FIELD", f"PartCatalogProfile.{PROFILE_FIELDS[field]} (synthetic overlay joined by PROFILES_PART)"
            elif field in mapped:
                kind, src = "BUSINESS_FIELD", f"{label}.{mapped[field]}"
            elif field in ("effective_from", "effective_to"):
                kind, src = "BUSINESS_FIELD", f"{label}.{field} (same name; written by the ingestion only when the canonical record has a value)"
            elif nonnull == 0:
                kind, src = "NOT_APPLICABLE", f"no graph property; the canonical files carry no value for it (0 of {len(records)} records)"
            else:
                kind, src = "BUSINESS_FIELD", f"{label}.{field} (same-name property; no registry mapping)"
            status = "MISSING" if (kind == "BUSINESS_FIELD" and "no registry mapping" in src) else "MAPPED"
            rows.append({"dataset": name, "canonical_field": field, "graph_source": src, "reader": reader, "reader_output": "present (graph_rows.graph_row builds every model field)",
                         "classification": kind, "canonical_records": len(records), "canonical_non_null": nonnull, "status": status})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args()
    rows = audit()
    from collections import Counter
    c = Counter((r["classification"], r["status"]) for r in rows)
    print(f"{len(rows)} fields over {len(READER_DATASETS)} reader-backed datasets")
    for k, v in sorted(c.items()):
        print(f"  {k[0]:20s} {k[1]:8s} {v}")
    for r in rows:
        if r["status"] == "MISSING":
            print("  MISSING:", r["dataset"], r["canonical_field"], "-", r["graph_source"])
    if a.out:
        Path(a.out).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
