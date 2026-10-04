"""Read-only probe of the live Neo4j graph. Writes docs/audit/data/graph_schema.json. Nothing here writes to the database."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
logging.disable(logging.CRITICAL)

from app.core.config import get_settings  # noqa: E402
from app.graph.client import GraphClient  # noqa: E402


def main() -> None:
    g = GraphClient(get_settings())
    out: dict = {}
    out["labels"] = {r["l"]: r["c"] for r in g.read("MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS c ORDER BY c DESC")}
    out["node_props"] = {
        r["l"]: {"keys": sorted(r["keys"]), "n": r["n"]}
        for r in g.read("MATCH (n) WITH labels(n)[0] AS l, n UNWIND keys(n) AS k RETURN l, collect(DISTINCT k) AS keys, count(DISTINCT n) AS n")
    }
    out["node_status"] = [
        {"label": r["l"], "data_status": r["ds"], "provenance_type": r["pt"], "authoritative": r["af"], "n": r["n"]}
        for r in g.read("MATCH (n) RETURN labels(n)[0] AS l, n.data_status AS ds, n.provenance_type AS pt, n.authoritative_flag AS af, count(*) AS n ORDER BY l, ds")
    ]
    out["rels"] = [
        {"from": r["a"], "type": r["t"], "to": r["b"], "n": r["n"], "props": sorted(r["props"]), "edge_status": r["ds"]}
        for r in g.read(
            "MATCH (a)-[r]->(b) WITH labels(a)[0] AS a, type(r) AS t, labels(b)[0] AS b, r "
            "RETURN a, t, b, count(*) AS n, apoc.coll.toSet(apoc.coll.flatten(collect(keys(r)))) AS props, collect(DISTINCT r.data_status) AS ds ORDER BY t, a, b"
        )
    ] if False else []
    rels = g.read("MATCH (a)-[r]->(b) RETURN labels(a)[0] AS a, type(r) AS t, labels(b)[0] AS b, count(*) AS n, collect(DISTINCT r.data_status) AS ds ORDER BY t, a, b")
    keys = g.read("MATCH (a)-[r]->(b) WITH labels(a)[0] AS a, type(r) AS t, labels(b)[0] AS b, keys(r) AS k UNWIND k AS key RETURN a, t, b, collect(DISTINCT key) AS props")
    prop_map = {(r["a"], r["t"], r["b"]): sorted(r["props"]) for r in keys}
    out["rels"] = [{"from": r["a"], "type": r["t"], "to": r["b"], "n": r["n"], "edge_status": sorted(x or "NULL" for x in r["ds"]), "props": prop_map.get((r["a"], r["t"], r["b"]), [])} for r in rels]
    out["constraints"] = [{k: (v if not isinstance(v, (list, tuple)) else list(v)) for k, v in r.items() if k in ("name", "type", "entityType", "labelsOrTypes", "properties")} for r in g.read("SHOW CONSTRAINTS")]
    out["indexes"] = [{k: (v if not isinstance(v, (list, tuple)) else list(v)) for k, v in r.items() if k in ("name", "type", "entityType", "labelsOrTypes", "properties", "state")} for r in g.read("SHOW INDEXES")]
    out["locations"] = g.read("MATCH (l:Location) RETURN l.location_id AS id, l.name AS name, l.location_type AS type, l.country_code AS cc, l.data_status AS ds")
    out["regions"] = g.read("MATCH (r:Region) RETURN r.name AS name, keys(r) AS k LIMIT 3")
    out["dealer_cities"] = g.read("MATCH (d:Dealer) RETURN d.country_code AS cc, d.city AS city, count(*) AS n ORDER BY cc, city")
    out["supplier_cities"] = g.read("MATCH (s:Supplier) RETURN s.country_code AS cc, s.city AS city, count(*) AS n ORDER BY cc, city")
    out["warehouse_cities"] = g.read("MATCH (w:Warehouse) RETURN w.country_code AS cc, w.city AS city, w.name AS name")
    out["orders"] = g.read("MATCH (o:Order) RETURN o.order_id AS id, o.order_status AS status, o.data_status AS ds ORDER BY id")
    out["shipments"] = g.read("MATCH (s:Shipment) RETURN s.shipment_id AS id, s.shipment_status AS status, s.tracking_ref AS ref, s.data_status AS ds ORDER BY id")
    out["inventory_freshness"] = g.read("MATCH ()-[r:AVAILABLE_AT]->() RETURN count(r) AS n, count(r.last_updated) AS with_last_updated, count(r.available) AS with_qty, collect(DISTINCT keys(r))[0] AS keys")
    out["entity_properties_of_interest"] = {
        label: g.read(f"MATCH (n:`{label}`) RETURN properties(n) AS p LIMIT 1")[0]["p"]
        for label in ["Order", "Shipment", "TrackingEvent", "Customer", "ServicePlan", "OrderStatusEvent", "Carrier", "OrderLine", "Address", "Region", "SupplierBackorder", "DeliveryEstimate"]
    }
    out["has_labels"] = {name: name in out["labels"] for name in [
        "Part", "Machine", "MachineType", "MachineFamily", "Category", "Assembly", "Supplier", "Dealer", "DealerBranch", "Depot", "Warehouse", "City", "Country", "Location", "Region", "Address",
        "Inventory", "Customer", "PartsInquiry", "RequestedPart", "FulfilmentRequest", "FulfilmentOption", "Allocation", "Order", "Shipment", "ShipmentEvent", "TrackingEvent",
        "ServiceJob", "ServicePlan", "ComplianceRequirement", "Certification", "Alternative", "Supersession"]}
    (ROOT / "docs/audit/data").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs/audit/data/graph_schema.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("labels", len(out["labels"]), "rel patterns", len(out["rels"]), "constraints", len(out["constraints"]), "indexes", len(out["indexes"]))
    g.close()


if __name__ == "__main__":
    main()
