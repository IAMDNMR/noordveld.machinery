"""Read-only audit of the live graph before anything is generated. Writes data/eu_foundation/audit_before.json."""
from __future__ import annotations

import hashlib
import json

from common import dump, read


# What the running app stamps on every record it writes (backend/app/graph/queries/orders.py PROVENANCE). Anything else is seed data.
APP_WRITTEN_SOURCE_ID = "APP-SESSION"

# A record is protected when it is SOURCE_DERIVED, DERIVED or REAL, or when it is USER_PROVIDED but was NOT written by the running app
# (e.g. the plants, the data-source entry and the original order statuses that came with the supplied brief, source_id SRC-BRIEF).
_PROTECTED = "(x.data_status IN ['SOURCE_DERIVED','DERIVED','REAL'] OR (x.data_status = 'USER_PROVIDED' AND coalesce(x.source_id, '') <> $app))"
NODE_QUERY = f"""MATCH (x) WHERE {_PROTECTED}
                 RETURN labels(x)[0] AS l, properties(x) AS p, coalesce(x.source_record_id,'') AS k ORDER BY l, k, elementId(x)"""
REL_QUERY = f"""MATCH (a)-[x]->(b) WHERE {_PROTECTED}
                RETURN type(x) AS t, properties(x) AS p, coalesce(x.rel_id,'') AS k ORDER BY t, k"""


def fingerprint(nodes: list[dict], rels: list[dict]) -> str:
    """SHA-256 over the given node rows ({l, p}) and relationship rows ({t, p}) in the order supplied, every property included."""
    h = hashlib.sha256()
    for r in nodes:
        h.update(json.dumps({"l": r["l"], "p": r["p"]}, sort_keys=True, default=str).encode())
    for r in rels:
        h.update(json.dumps({"t": r["t"], "p": r["p"]}, sort_keys=True, default=str).encode())
    return h.hexdigest()


def protected_rows() -> tuple[list[dict], list[dict]]:
    return read(NODE_QUERY, app=APP_WRITTEN_SOURCE_ID), read(REL_QUERY, app=APP_WRITTEN_SOURCE_ID)


def source_checksum() -> str:
    """SOURCE/DERIVED DATA INTEGRITY CHECKSUM: a SHA-256 over every record that is part of the supplied data, every property included. It must be identical
    after seeding and after any use of the app.

    Protected:      SOURCE_DERIVED, DERIVED and REAL nodes and relationships (the supplied catalogue and what is derived from it), and USER_PROVIDED
                    records that are not app-written (source_id other than 'APP-SESSION': the supplied plants, data-source entry and original order statuses).
    Not protected:  records the running app itself writes (source_id = 'APP-SESSION': orders, carts, the order-status vocabulary added for the direct-order
                    flow, status events). They change in normal use by design.
    `source_checksum_incl_user_provided` and `source_checksum_source_derived_only` in audit_before.json keep the values of the two earlier definitions."""
    return fingerprint(*protected_rows())


def main() -> dict:
    o: dict = {}
    o["nodes"] = read("MATCH (n) RETURN count(n) AS n")[0]["n"]
    o["relationships"] = read("MATCH ()-[r]->() RETURN count(r) AS n")[0]["n"]
    o["labels"] = {r["l"]: r["c"] for r in read("MATCH (n) WITH labels(n)[0] AS l RETURN l, count(*) AS c ORDER BY c DESC")}
    o["relationship_types"] = {r["t"]: r["c"] for r in read("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY c DESC")}
    o["node_status"] = {str(r["ds"]): r["n"] for r in read("MATCH (n) RETURN n.data_status AS ds, count(*) AS n")}
    o["relationship_status"] = {str(r["ds"]): r["n"] for r in read("MATCH ()-[r]->() RETURN r.data_status AS ds, count(*) AS n")}
    o["data_sources"] = read("MATCH (d:DataSource) RETURN properties(d) AS p ORDER BY d.source_id")
    o["parts"] = read("MATCH (p:Part) RETURN count(p) AS n")[0]["n"]
    o["machines"] = read("MATCH (m:Machine) RETURN count(m) AS n")[0]["n"]
    o["fitments"] = read("MATCH ()-[f:FITS]->() RETURN count(f) AS n")[0]["n"]
    o["specifications"] = read("MATCH (s:PartSpecification) RETURN count(s) AS n")[0]["n"]
    o["suppliers"] = read("MATCH (s:Supplier) RETURN s.supplier_id AS id, s.name AS name, s.city AS city, s.country_code AS cc, s.data_status AS ds ORDER BY id")
    o["dealers"] = read("MATCH (d:Dealer) RETURN d.dealer_id AS id, d.name AS name, d.city AS city, d.country_code AS cc, d.dealer_type AS type, d.data_status AS ds ORDER BY id")
    o["warehouses"] = read("MATCH (w:Warehouse) RETURN w.warehouse_id AS id, w.name AS name, w.city AS city, w.country_code AS cc, w.data_status AS ds, [(w)-[:LOCATED_AT_PLANT]->(p) | p.name] AS plant ORDER BY id")
    o["plants"] = read("MATCH (p:Plant) RETURN p.plant_id AS id, p.name AS name, [(p)-[:LOCATED_AT_ADDRESS]->(a) | a.city] AS city, p.data_status AS ds ORDER BY id")
    o["business_units"] = read("MATCH (b:BusinessUnit) RETURN b.name AS name, b.data_status AS ds, [(b)-[:HOME_PLANT]->(p) | p.name] AS plant ORDER BY name")
    o["machine_plants"] = read("MATCH (m:Machine)-[:MANUFACTURED_AT]->(p:Plant) RETURN p.name AS plant, collect(m.model_code) AS machines ORDER BY plant")
    o["service_plans"] = read("MATCH (s:ServicePlan) RETURN count(s) AS n, collect(DISTINCT s.name) AS names")[0]
    o["orders"] = read("MATCH (o:Order) RETURN o.order_id AS id, o.order_status AS status, o.data_status AS ds ORDER BY id")
    o["shipments"] = read("MATCH (s:Shipment) RETURN count(s) AS n, collect(DISTINCT s.shipment_status) AS statuses")[0]
    o["tracking_events"] = read("MATCH (e:TrackingEvent) RETURN count(e) AS n, collect(DISTINCT e.event_status) AS statuses")[0]
    o["order_statuses"] = read("MATCH (s:OrderStatus) RETURN properties(s) AS p ORDER BY s.sequence")
    o["locations"] = read("MATCH (l:Location) RETURN l.location_id AS id, l.name AS name, l.location_type AS type, l.country_code AS cc ORDER BY id")
    o["regions"] = read("MATCH (r:Region) RETURN r.region_id AS id, r.name AS name, r.country_code AS cc ORDER BY id")
    o["address_countries"] = {str(r["cc"]): r["n"] for r in read("MATCH (a:Address) RETURN a.country_code AS cc, count(*) AS n ORDER BY cc")}
    o["customers"] = read("MATCH (c:Customer) RETURN count(c) AS n")[0]["n"]
    o["carriers"] = read("MATCH (c:Carrier) RETURN properties(c) AS p")
    o["shipping_rates"] = read("MATCH (r:ShippingRate) RETURN properties(r) AS p ORDER BY r.shipping_rate_id")
    o["delivery_estimates"] = read("MATCH (d:DeliveryEstimate) RETURN count(d) AS n, collect(DISTINCT keys(d))[0] AS keys")[0]
    o["delivery_estimate_sample"] = read("MATCH (d:DeliveryEstimate) RETURN properties(d) AS p LIMIT 1")
    o["delivery_estimate_links"] = read("MATCH (d:DeliveryEstimate)-[r]->(x) RETURN type(r) AS t, labels(x)[0] AS l, count(*) AS n ORDER BY t")
    o["prices"] = read("MATCH (p:Price) RETURN count(p) AS n, collect(DISTINCT p.currency) AS currencies, collect(DISTINCT p.price_status) AS statuses, min(p.list_price_ex_vat) AS lo, max(p.list_price_ex_vat) AS hi")[0]
    o["transport_labels_present"] = [l for l in o["labels"] if any(k in l for k in ("Transport", "Terminal", "Route", "Freight", "Port", "Rail", "Air"))]
    o["inventory"] = read("MATCH ()-[r:AVAILABLE_AT]->() RETURN r.stock_status AS s, count(*) AS n, sum(CASE WHEN r.available IS NULL THEN 1 ELSE 0 END) AS null_qty ORDER BY s")
    o["stocked_by"] = read("MATCH ()-[r:STOCKED_BY]->() RETURN r.stocking_status AS s, count(*) AS n ORDER BY s")
    o["supplied_by_per_part"] = read("MATCH (p:Part)-[:SUPPLIED_BY]->(s) RETURN min(c) AS lo, max(c) AS hi FROM")  if False else None
    o["constraints"] = len(read("SHOW CONSTRAINTS YIELD name RETURN name"))
    o["indexes"] = len(read("SHOW INDEXES YIELD name RETURN name"))
    o["constraint_list"] = [r["name"] for r in read("SHOW CONSTRAINTS YIELD name RETURN name ORDER BY name")]
    o["source_checksum"] = source_checksum()
    o["batches_present"] = {str(r["b"]): r["n"] for r in read("MATCH (n) WHERE n.enrichment_batch IS NOT NULL RETURN n.enrichment_batch AS b, count(*) AS n")}
    dump("audit_before.json", o)
    return o


if __name__ == "__main__":
    o = main()
    print(json.dumps({k: o[k] for k in ("nodes", "relationships", "parts", "machines", "fitments", "specifications", "customers", "constraints", "indexes", "batches_present", "source_checksum")}, indent=1))
    print("labels:", o["labels"])
    print("transport-ish labels already present:", o["transport_labels_present"])
