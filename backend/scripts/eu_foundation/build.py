"""Assemble the whole European foundation in memory (deterministic) and report exactly what it would add. Writes nothing to Neo4j.

  python build.py plan     counts of every node label and relationship type that apply would create
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from typing import Any

from build_entities import (Geo, build_customers, build_dealers, build_depots, build_reference, build_service_centres, build_suppliers, build_territories)
from build_supply import build_dealer_parts, build_inventory, build_part_service, build_supplier_parts
from build_transport import Place, build_options_and_carriers, build_routes, build_terminals, emit_routes
from common import BATCH, SOURCE_FILE, SOURCE_ID, SOURCE_NAME, TODAY, dump, read
from model import Model, load_existing, node_props


def build() -> tuple[Model, dict[str, Any]]:
    ex = load_existing()
    m = Model()
    geo = Geo(m, ex)
    shipto_rows = read("MATCH (s:ShipTo) WHERE coalesce(s.enrichment_batch, '') <> $b RETURN s.shipto_id AS id, s.city AS city, s.country_code AS cc, s.latitude AS lat, s.longitude AS lon ORDER BY id", b=BATCH)
    existing_dist = {(r["w"], r["s"]): r["km"] for r in read("MATCH (w:Warehouse)-[r:DISTANCE_TO]->(s:ShipTo) WHERE coalesce(r.enrichment_batch, '') <> $b RETURN w.warehouse_id AS w, s.shipto_id AS s, r.distance_km AS km", b=BATCH)}

    if SOURCE_ID not in ex.all_ids["DataSource"]:
        m.node("DataSource", SOURCE_ID, {**node_props("data_sources", SOURCE_ID, {}), "name": "European operational data foundation (deterministic generator)", "layer": "Synthetic European operations",
                                         "verification": "Validated by scripts/eu_foundation/validate.py; additive only, idempotent",
                                         "limitations": "Synthetic demonstration data. Not real company, dealer, supplier, customer, inventory, freight, order or shipment data."})
    build_reference(m, ex)
    depots = build_depots(m, ex, geo)
    dealers = build_dealers(m, ex, geo)
    build_service_centres(m, dealers, geo)
    build_territories(m, dealers, geo)
    suppliers = build_suppliers(m, ex, geo, ex.parts)
    customers = build_customers(m, ex, geo, shipto_rows)
    build_inventory(m, ex, depots)
    build_supplier_parts(m, ex, suppliers, depots)
    build_dealer_parts(m, ex, dealers, depots)
    build_part_service(m, ex)

    option_ids = build_options_and_carriers(m, ex)
    terminals, by_key, graph = build_terminals(m, geo)
    shiptos = [Place(r["id"], r["id"], r["cc"], r["lat"], r["lon"]) for r in shipto_rows] + \
              [Place(sid, sid, p["country_code"], p["latitude"], p["longitude"]) for sid, p in m.nodes["ShipTo"].items()]
    result = build_routes(m, ex, depots, shiptos, terminals, by_key, graph, option_ids, existing_dist)
    stats = emit_routes(m, result, option_ids, existing_dist)

    # no new node may reuse an id that already exists in the graph
    clashes = [(label, i) for label, rows in m.nodes.items() for i in rows if i in ex.all_ids.get(label, set()) and label != "DataSource"]
    if clashes:
        raise SystemExit(f"id collision with existing graph nodes: {clashes[:5]}")
    meta = {"depots": len(depots), "dealers": len(dealers), "suppliers": len(suppliers), "customers_new": len(customers), "shiptos_total": len(shiptos), "terminals": len(terminals), **stats}
    return m, meta


def summary(m: Model, meta: dict[str, Any]) -> dict[str, Any]:
    nodes, rels = m.counts()
    return {"batch": BATCH, "source_id": SOURCE_ID, "nodes_total": sum(nodes.values()), "relationships_total": sum(rels.values()), "nodes": dict(sorted(nodes.items())),
            "relationships": dict(sorted(rels.items())), "meta": meta}


if __name__ == "__main__":
    model, meta = build()
    s = summary(model, meta)
    dump("plan_summary.json", s)
    print(json.dumps(s, indent=1))
