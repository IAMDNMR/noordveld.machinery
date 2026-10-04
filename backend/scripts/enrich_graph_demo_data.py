"""Synthetic demo enrichment of the Noordveld graph: deterministic, additive and idempotent.

Usage (from backend/):
  python scripts/enrich_graph_demo_data.py audit      read-only; writes graph/audits/demo_enrichment_audit.{json,md}
  python scripts/enrich_graph_demo_data.py plan       read-only; prints what apply would create (nothing is written)
  python scripts/enrich_graph_demo_data.py apply      audit -> stages in dependency order -> validate -> report (stops at the first failing stage)
  python scripts/enrich_graph_demo_data.py validate   read-only validation of the whole graph and of this enrichment batch

Rules this script keeps:
  * Never deletes, never removes a relationship, never overwrites a value: nodes and relationships are MERGEd on their unique ids
    (every relationship carries a unique rel_id, as in the original import); properties are only SET where they are null.
  * Never touches SOURCE_DERIVED / DERIVED / USER_PROVIDED records except to attach new synthetic records to them.
  * Every new node and relationship carries the project's provenance fields with data_status = provenance_type = SYNTHETIC_DEMO,
    source_id SRC-004 and enrichment_batch, so it can always be told apart from the catalogue.
  * Invents no engineering facts (no weights, pressures, ratings, interchangeability) and no fitment: assemblies, requests and
    orders only use parts that the catalogue already says FIT the machine involved; orders only use VERIFIED, orderable parts.
  * Same graph + same seed = same data. Credentials come from backend/.env and are never printed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)

from neo4j import READ_ACCESS, WRITE_ACCESS  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.graph.client import GraphClient  # noqa: E402

AUDITS = ROOT / "graph" / "audits"
SEED = 20261003
BATCH = "ENRICH-2026-10-03"
SOURCE_ID = "SRC-004"
SOURCE_NAME = f"enrich_graph_demo_data.py (seed {SEED})"
TODAY = "2026-10-03"

# ── connection ────────────────────────────────────────────────────────────────────────────────────
_client = GraphClient(get_settings())


def read(query: str, **params: Any) -> list[dict[str, Any]]:
    with _client.driver.session(database=get_settings().neo4j_database, default_access_mode=READ_ACCESS) as s:
        return s.execute_read(lambda tx: tx.run(query, params).data())


def write(query: str, **params: Any) -> dict[str, int]:
    with _client.driver.session(database=get_settings().neo4j_database, default_access_mode=WRITE_ACCESS) as s:
        def work(tx):
            summary = tx.run(query, params).consume()
            c = summary.counters
            return {"nodes": c.nodes_created, "rels": c.relationships_created, "props": c.properties_set, "deleted": c.nodes_deleted + c.relationships_deleted}
        return s.execute_write(work)


def prov(sheet: str, record_id: str) -> dict[str, Any]:
    return {
        "data_status": "SYNTHETIC_DEMO", "provenance_type": "SYNTHETIC_DEMO", "source_id": SOURCE_ID, "source_name": SOURCE_NAME,
        "source_file": "backend/scripts/enrich_graph_demo_data.py", "source_sheet": sheet, "source_record_id": record_id,
        "confidence": "NOT_STATED", "authoritative_flag": False, "last_updated": TODAY, "enrichment_batch": BATCH,
    }


# ── audit ─────────────────────────────────────────────────────────────────────────────────────────
def audit() -> dict[str, Any]:
    out: dict[str, Any] = {"taken_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
    out["totals"] = {"nodes": read("MATCH (n) RETURN count(n) AS n")[0]["n"], "relationships": read("MATCH ()-[r]->() RETURN count(r) AS n")[0]["n"]}
    out["labels"] = {r["l"]: {"count": r["c"], "data_status": sorted(x or "NULL" for x in r["ds"])}
                     for r in read("MATCH (n) WITH labels(n)[0] AS l, n RETURN l, count(*) AS c, collect(DISTINCT n.data_status) AS ds ORDER BY l")}
    out["relationships"] = [{"from": r["a"], "type": r["t"], "to": r["b"], "count": r["c"], "data_status": sorted(x or "NULL" for x in r["ds"])}
                            for r in read("MATCH (a)-[r]->(b) RETURN labels(a)[0] AS a, type(r) AS t, labels(b)[0] AS b, count(*) AS c, collect(DISTINCT r.data_status) AS ds ORDER BY t, a, b")]
    out["provenance"] = {
        "nodes": {r["ds"] or "NULL": r["n"] for r in read("MATCH (n) RETURN n.data_status AS ds, count(*) AS n")},
        "relationships": {r["ds"] or "NULL": r["n"] for r in read("MATCH ()-[r]->() RETURN r.data_status AS ds, count(*) AS n")},
    }
    out["constraints"] = len(read("SHOW CONSTRAINTS YIELD name RETURN name"))
    out["source_checksum"] = source_checksum()
    # schema-only domains: labels the schema documents that hold no data
    schema_labels = set()
    schema_file = ROOT / "graph" / "schema" / "node_schema.csv"
    if schema_file.exists():
        for line in schema_file.read_text(encoding="utf-8").splitlines()[1:]:
            if line.strip():
                schema_labels.add(line.split(",")[0].strip())
    out["schema_only_labels"] = sorted(schema_labels - set(out["labels"]))
    g = {}
    g["machines_without_profile_fields"] = read("MATCH (m:Machine) WHERE NOT (m)<-[:PROFILES_MACHINE]-() RETURN collect(m.model_code) AS v")[0]["v"]
    g["machines_without_fitted_parts"] = read("MATCH (m:Machine) WHERE NOT (m)<-[:FITS]-() RETURN collect(m.model_code) AS v")[0]["v"]
    g["parts_without_assembly"] = read("MATCH (p:Part) WHERE NOT (p)-[:PART_OF]->() RETURN count(p) AS v")[0]["v"]
    g["parts_without_service_plan"] = read("MATCH (p:Part) WHERE NOT (p)<-[:REQUIRES_PART]-() RETURN count(p) AS v")[0]["v"]
    g["parts_without_supplier"] = read("MATCH (p:Part) WHERE NOT (p)-[:SUPPLIED_BY]->() RETURN count(p) AS v")[0]["v"]
    g["parts_without_inventory"] = read("MATCH (p:Part) WHERE NOT (p)-[:AVAILABLE_AT]->() RETURN count(p) AS v")[0]["v"]
    g["parts_without_dealer"] = read("MATCH (p:Part) WHERE NOT (p)-[:STOCKED_BY]->() RETURN count(p) AS v")[0]["v"]
    g["parts_without_compliance"] = read("MATCH (p:Part) WHERE NOT (p)-[:HAS_COMPLIANCE]->() RETURN count(p) AS v")[0]["v"]
    g["parts_in_any_order"] = read("MATCH (p:Part) WHERE (p)<-[:REFERENCES_PART]-(:OrderLine) RETURN count(p) AS v")[0]["v"]
    g["profile_fields_missing"] = read("""MATCH (c:PartCatalogProfile) RETURN sum(CASE WHEN c.application IS NULL THEN 1 ELSE 0 END) AS application,
        sum(CASE WHEN c.maintenance_class IS NULL THEN 1 ELSE 0 END) AS maintenance_class, sum(CASE WHEN c.criticality IS NULL THEN 1 ELSE 0 END) AS criticality""")[0]
    g["warehouse_fields_missing"] = read("""MATCH (w:Warehouse) RETURN sum(CASE WHEN w.warehouse_type IS NULL THEN 1 ELSE 0 END) AS warehouse_type,
        sum(CASE WHEN w.operating_status IS NULL THEN 1 ELSE 0 END) AS operating_status""")[0]
    g["customer_requests"] = read("MATCH (r:CustomerRequest) RETURN count(r) AS v")[0]["v"]
    g["orders"] = read("MATCH (o:Order) RETURN count(o) AS v")[0]["v"]
    g["inventory_rows_zero_but_in_stock"] = read("MATCH ()-[r:AVAILABLE_AT]->() WHERE coalesce(r.available, 0) = 0 AND r.stock_status = 'IN_STOCK' RETURN count(r) AS v")[0]["v"]
    out["gaps"] = g
    out["enrichment_batch_present"] = read("MATCH (n {enrichment_batch: $b}) RETURN count(n) AS v", b=BATCH)[0]["v"]
    return out


def source_checksum() -> str:
    """A fingerprint of every non-synthetic node and relationship with all their properties: it must not change."""
    h = hashlib.sha256()
    for r in read("""MATCH (n) WHERE n.data_status IN ['SOURCE_DERIVED', 'DERIVED', 'USER_PROVIDED', 'REAL']
                     RETURN labels(n)[0] AS l, properties(n) AS p ORDER BY l, coalesce(n.source_record_id, ''), elementId(n)"""):
        h.update(json.dumps(r, sort_keys=True, default=str).encode())
    for r in read("""MATCH (a)-[r]->(b) WHERE r.data_status IN ['SOURCE_DERIVED', 'DERIVED', 'USER_PROVIDED', 'REAL']
                     RETURN type(r) AS t, properties(r) AS p ORDER BY t, coalesce(r.rel_id, '')"""):
        h.update(json.dumps(r, sort_keys=True, default=str).encode())
    return h.hexdigest()


# ── plan (pure: graph state in, records out) ──────────────────────────────────────────────────────
APPLICATION_BY_TYPE = {
    "Skid Steer Loader": ("Compact earthmoving, site clean-up and material handling in confined spaces", "Construction and landscaping sites"),
    "Compact Wheel Loader": ("Loading and carrying bulk material on smaller sites", "Municipal, agricultural and building-supply yards"),
    "Wheel Loader": ("Aggregate and industrial loading", "Quarries, recycling plants and bulk handling terminals"),
    "Telehandler": ("Lifting and placing loads at height and reach", "Construction, agriculture and industrial maintenance"),
    "Articulated Loader": ("Loading and carrying on uneven or soft ground", "Agriculture, forestry and landscaping"),
    "Electric Forklift": ("Indoor pallet handling and truck loading", "Warehouses and distribution centres"),
    "Reach Truck": ("High-bay pallet storage and retrieval", "Narrow-aisle warehouses"),
    "Pallet Truck": ("Horizontal pallet movement over short distances", "Warehouse floors and loading docks"),
    "Loader Arm Unit": ("Lifting module for integrated handling equipment", "OEM equipment builders"),
    "Stacker Crane": ("Automated storage and retrieval of unit loads", "Automated high-bay warehouses"),
    "Belt Conveyor Module": ("Continuous transport of bulk or unit goods", "Production and logistics lines"),
    "Loader Arm Assembly (machine)": ("Lifting arm module for material handling machinery", "OEM equipment builders"),
    "Roller Conveyor": ("Transport of cartons and pallets on driven rollers", "Distribution and packaging lines"),
    "Transfer Cart": ("Moving loads between production cells or rail lines", "Factories and storage systems"),
    "Pallet Elevator": ("Vertical transport of pallets between levels", "Multi-level warehouses and production"),
}
SYSTEM_BY_CATEGORY = {
    "Hydraulics": "Hydraulic system", "Drivetrain": "Drivetrain", "Structural": "Frame and structure", "Filtration": "Filtration system",
    "Attachments": "Attachment interface", "Electrical": "Electrical system", "Brakes": "Braking system", "Cooling": "Cooling system",
    "Cab & Controls": "Operator controls", "Lubrication": "Lubrication system",
}
WEAR_WORDS = ("seal", "filter", "pad", "hose", "bearing", "belt", "brush", "wiper", "bushing", "cutting edge", "tooth", "teeth", "o-ring", "lining")
CRITICALITY_BY_CATEGORY = {"Brakes": "HIGH", "Hydraulics": "HIGH", "Drivetrain": "HIGH", "Electrical": "MEDIUM", "Cooling": "MEDIUM", "Cab & Controls": "MEDIUM"}
ORDER_PLAN = [  # (status, number of lines): one order in each state, so every workflow step can be shown
    ("NEW", 1), ("CONFIRMED", 2), ("PROCESSING", 2), ("ALLOCATED", 1), ("SHIPPED", 2), ("DELIVERED", 3),
]
STATUS_SEQ = ["NEW", "CONFIRMED", "PROCESSING", "ALLOCATED", "SHIPPED", "DELIVERED"]
ALLOCATION_BY_STATUS = {"NEW": "NOT_YET_ALLOCATED", "CONFIRMED": "NOT_YET_ALLOCATED", "PROCESSING": "NOT_YET_ALLOCATED", "ALLOCATED": "RESERVED", "SHIPPED": "SHIPPED", "DELIVERED": "SHIPPED"}


def _next_id(prefix: str, existing: list[str], width: int) -> callable:
    nums = [int(x[len(prefix):]) for x in existing if x and x.startswith(prefix) and x[len(prefix):].isdigit()]
    counter = [max(nums, default=0)]

    def nxt() -> str:
        counter[0] += 1
        return f"{prefix}{counter[0]:0{width}d}"
    return nxt


def plan() -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(SEED)
    machines = read("""MATCH (m:Machine) OPTIONAL MATCH (m)-[:MEMBER_OF_FAMILY]->(f)
                       RETURN m.machine_id AS id, m.model_code AS code, m.machine_type AS type, m.name AS name, f.name AS family ORDER BY id""")
    parts = read("""MATCH (p:Part) OPTIONAL MATCH (c:PartCatalogProfile)-[:PROFILES_PART]->(p) OPTIONAL MATCH (pr:Price)-[:PRICES_PART]->(p)
                    RETURN p.part_id AS id, p.part_number AS pn, p.name AS name, p.category AS category, p.subcategory AS subcategory,
                           c.profile_id AS profile, c.part_status AS status, c.orderable AS orderable, pr.list_price_ex_vat AS price,
                           [(p)-[:FITS]->(m:Machine) | m.machine_id] AS machines,
                           exists { MATCH (p)-[r:PART_OF]->() WHERE r.enrichment_batch IS NULL OR r.enrichment_batch <> $b } AS in_assembly,
                           [(p)-[a:AVAILABLE_AT]->(w:Warehouse) WHERE a.available > 0 | {w: w.warehouse_id, available: a.available}] AS stock
                    ORDER BY id""", b=BATCH)
    family_of = {m["id"]: m["family"] for m in machines}
    p: dict[str, list[dict[str, Any]]] = defaultdict(list)

    # stage: reference
    p["data_source"].append({"source_id": SOURCE_ID, "props": {**prov("data_sources", SOURCE_ID), "name": "Demo enrichment script (seed 20261003)", "layer": "Synthetic enrichment",
                                                                  "verification": "Validated by enrich_graph_demo_data.py validate; additive only",
                                                                  "limitations": "Synthetic demonstration data. Not real company, supplier, inventory, order or shipment data."}})
    # stage: machine profiles (descriptive, never engineering figures)
    for i, m in enumerate(machines):
        application, context = APPLICATION_BY_TYPE.get(m["type"], ("General material handling", "Industrial sites"))
        year = 2014 + rng.randrange(0, 10)
        pid = f"MPR-{m['id']}"
        p["machine_profiles"].append({"id": pid, "machine_id": m["id"], "rel_id": f"PROFILES_MACHINE:{pid}", "props": {
            **prov("machine_profiles", pid), "machine_profile_id": pid, "application": application, "operating_context": context,
            "lifecycle_status": "ACTIVE" if year >= 2017 else "MATURE", "introduction_year": year,
            "description": f"{m['name']} (demo description): {application.lower()}."}})
    # stage: part profile fields (only where empty; the profile is already a synthetic record)
    for pt in parts:
        if not pt["profile"]:
            continue
        sub = (pt["subcategory"] or pt["name"] or "").lower()
        maintenance = "WEAR_PART" if any(w in sub for w in WEAR_WORDS) else "STRUCTURAL" if pt["category"] in ("Structural", "Attachments") else "SERVICE_PART"
        p["part_profiles"].append({"profile_id": pt["profile"], "fields": {
            "application": SYSTEM_BY_CATEGORY.get(pt["category"], "General"), "maintenance_class": maintenance,
            "criticality": CRITICALITY_BY_CATEGORY.get(pt["category"], "STANDARD")}})
    # stage: warehouse classification
    for w in read("MATCH (w:Warehouse) RETURN w.warehouse_id AS id, w.name AS name ORDER BY id"):
        p["warehouses"].append({"id": w["id"], "fields": {"warehouse_type": "CENTRAL_DC" if "Central" in (w["name"] or "") else "REGIONAL_DEPOT", "operating_status": "OPERATIONAL"}})

    # stage: assemblies for parts not yet in one, grouped by category within the machine family they fit (groups of 2+ only)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for pt in parts:
        if pt["in_assembly"] or not pt["machines"]:
            continue
        fam = Counter(family_of[mid] for mid in pt["machines"] if family_of.get(mid)).most_common(1)
        if fam:
            groups[(fam[0][0], pt["category"])].append(pt)
    asm_ids = _next_id("ASM-", [r["v"] for r in read("MATCH (n:Assembly) WHERE (n.enrichment_batch IS NULL OR n.enrichment_batch <> $b) RETURN n.assembly_id AS v", b=BATCH)] + ["ASM-100"], 3)
    acp = 0
    for (family, category), members in sorted(groups.items()):
        if len(members) < 2:
            continue  # a single part is no assembly; it stays NOT_CONNECTED on purpose
        aid = asm_ids()
        p["assemblies"].append({"id": aid, "props": {**prov("assemblies", aid), "assembly_id": aid, "name": f"{category} module, {family} (demo)", "bom_status": "DEMO_BOM"}})
        for pt in members[:6]:
            acp += 1
            rid = f"ENR-ACP-{acp:04d}"
            p["part_of"].append({"part_id": pt["id"], "assembly_id": aid, "rel_id": f"PART_OF:{rid}", "props": {**prov("assembly_components", rid), "quantity": rng.choice([1, 1, 2, 4]),
                                                                                                             "basis": "DEMO_BOM_CATEGORY_AND_FAMILY"}})

    # stage: customer requests (only for a part that FITS the machine named)
    customers = read("""MATCH (c:Customer) OPTIONAL MATCH (c)-[:LOCATED_AT_ADDRESS]->(a:Address)
                        RETURN c.customer_id AS id, c.city AS city, a.address_id AS address ORDER BY id""")
    fitting = [(pt, mid) for pt in parts for mid in pt["machines"]]
    rng.shuffle(fitting)
    code_of = {m["id"]: m["code"] for m in machines}
    chosen: list[tuple[dict, str]] = []
    for pt, mid in fitting:
        if len(chosen) >= 6:
            break
        if all(pt["id"] != c[0]["id"] for c in chosen) and (pt["status"] != "VERIFIED" or sum(1 for c in chosen if c[0]["status"] == "VERIFIED") < 4):
            chosen.append((pt, mid))
    for i, (pt, mid) in enumerate(chosen, 1):
        rid = f"REQ-DEMO-{i:03d}"
        cust = customers[(i * 3) % len(customers)]
        status = ["OPEN", "QUOTED", "OPEN", "CLOSED", "QUOTED", "OPEN"][i - 1]
        p["requests"].append({"id": rid, "customer_id": cust["id"], "machine_id": mid, "part_id": pt["id"], "props": {
            **prov("customer_requests", rid), "request_id": rid, "request_text": f"Need {pt['name'][0].lower() + pt['name'][1:]} for {code_of[mid]} (demo request)",
            "request_status": status, "requested_on": (dt.date(2026, 9, 14) + dt.timedelta(days=2 * i)).isoformat(), "part_status_at_request": pt["status"]}})

    # stage: orders (verified, orderable parts with recorded stock only)
    orderable = [pt for pt in parts if pt["status"] == "VERIFIED" and pt["orderable"] is True and pt["price"] is not None and pt["stock"]]
    anchor = next((pt for pt in orderable if pt["pn"] == "NVM-1010-HY"), None)
    order_ids = _next_id("ORD-", [r["v"] for r in read("MATCH (n:Order) WHERE (n.enrichment_batch IS NULL OR n.enrichment_batch <> $b) RETURN n.order_id AS v", b=BATCH)], 4)
    line_ids = _next_id("OI-", [r["v"] for r in read("MATCH (n:OrderLine) WHERE (n.enrichment_batch IS NULL OR n.enrichment_batch <> $b) RETURN n.order_line_id AS v", b=BATCH)], 4)
    event_ids = _next_id("OSH-", [r["v"] for r in read("MATCH (n:OrderStatusEvent) WHERE (n.enrichment_batch IS NULL OR n.enrichment_batch <> $b) RETURN n.status_event_id AS v", b=BATCH)], 4)
    ship_ids = _next_id("SHP-", [r["v"] for r in read("MATCH (n:Shipment) WHERE (n.enrichment_batch IS NULL OR n.enrichment_batch <> $b) RETURN n.shipment_id AS v", b=BATCH)], 4)
    track_ids = _next_id("EVT-", [r["v"] for r in read("MATCH (n:TrackingEvent) WHERE (n.enrichment_batch IS NULL OR n.enrichment_batch <> $b) RETURN n.tracking_event_id AS v", b=BATCH)], 4)
    carrier = read("MATCH (c:Carrier) RETURN c.carrier_id AS id ORDER BY id LIMIT 1")[0]["id"]
    wh_city = {r["id"]: r["city"] for r in read("MATCH (w:Warehouse) RETURN w.warehouse_id AS id, w.city AS city")}
    for n, (status, n_lines) in enumerate(ORDER_PLAN):
        oid = order_ids()
        cust = customers[(n * 7 + 2) % len(customers)]
        day = dt.date(2026, 9, 12) + dt.timedelta(days=3 * n)
        picks = rng.sample(orderable, n_lines)
        if anchor and n in (1, 4) and anchor not in picks:
            picks[0] = anchor  # NVM-1010-HY appears in two orders, so "which orders contain this part" has a real answer
        lines, subtotal = [], 0.0
        for k, pt in enumerate(picks, 1):
            qty = rng.choice([1, 1, 2, 3])
            wh = max(pt["stock"], key=lambda s: (s["available"], s["w"]))["w"]
            total = round(pt["price"] * qty, 2)
            subtotal += total
            lid = line_ids()
            lines.append({"id": lid, "part_id": pt["id"], "warehouse_id": wh, "props": {
                **prov("order_lines", lid), "order_line_id": lid, "line_no": k, "quantity": qty, "unit_price_eur": pt["price"], "line_total_eur": total,
                "allocation_status": ALLOCATION_BY_STATUS[status]}})
        subtotal = round(subtotal, 2)
        vat = round((subtotal + 19.0) * 0.21, 2)
        order = {"id": oid, "customer_id": cust["id"], "address_id": cust["address"], "lines": lines, "status": status, "props": {
            **prov("orders", oid), "order_id": oid, "order_date": day.isoformat(), "order_status": status, "channel": "DEMO_WEB_STORE", "currency": "EUR",
            "shipping_method": "STANDARD", "shipping_ex_vat": 19.0, "subtotal_ex_vat": subtotal, "vat_rate": 0.21, "vat_amount": vat,
            "order_total_incl_vat": round(subtotal + 19.0 + vat, 2)}}
        order["events"] = [{"id": (eid := event_ids()), "status": s, "props": {**prov("order_status_history", eid), "status_event_id": eid, "sequence": q, "order_status": s}}
                           for q, s in enumerate(STATUS_SEQ[: STATUS_SEQ.index(status) + 1], 1)]
        if status in ("SHIPPED", "DELIVERED"):
            sid = ship_ids()
            origin = lines[0]["warehouse_id"]
            events = [("PICKED", wh_city.get(origin) or "Warehouse (demo)"), ("IN_TRANSIT", "Linehaul hub (demo)")]
            if status == "DELIVERED":
                events.append(("DELIVERED", cust["city"] or "Customer site (demo)"))
            order["shipment"] = {"id": sid, "warehouse_id": origin, "props": {
                **prov("shipments", sid), "shipment_id": sid, "shipment_status": status, "tracking_ref": f"DEMO-TRACK-{sid[4:]}"},
                "events": [{"id": (tid := track_ids()), "props": {**prov("shipment_events", tid), "tracking_event_id": tid, "event_seq": q, "event_status": s,
                                                                   "event_location": loc, "event_date": (day + dt.timedelta(days=q)).isoformat()}}
                           for q, (s, loc) in enumerate(events, 1)]}
        p["orders"].append(order)
    p["carrier"] = [{"id": carrier}]
    return p


# ── apply ─────────────────────────────────────────────────────────────────────────────────────────
NEW_CONSTRAINTS = [
    "CREATE CONSTRAINT machine_profile_id_unique IF NOT EXISTS FOR (n:MachineProfile) REQUIRE n.machine_profile_id IS UNIQUE",
    "CREATE CONSTRAINT customer_request_id_unique IF NOT EXISTS FOR (n:CustomerRequest) REQUIRE n.request_id IS UNIQUE",
    "CREATE CONSTRAINT rel_profiles_machine_id_unique IF NOT EXISTS FOR ()-[r:PROFILES_MACHINE]-() REQUIRE r.rel_id IS UNIQUE",
]


def _rel(rtype: str, sheet: str, rid: str) -> dict[str, Any]:
    return {**prov(sheet, rid), "rel_id": f"{rtype}:{rid}"}


def stages(p: dict[str, list[dict[str, Any]]]) -> list[tuple[str, list[tuple[str, dict[str, Any]]]]]:
    """(stage name, [(cypher, params)]) in dependency order. Every statement is a MERGE on a unique id; nothing is overwritten."""
    S: list[tuple[str, list[tuple[str, dict[str, Any]]]]] = []
    S.append(("1 constraints for the new labels", [(c, {}) for c in NEW_CONSTRAINTS]))
    S.append(("2 reference: data source", [("MERGE (s:DataSource {source_id: $id}) ON CREATE SET s += $props", {"id": d["source_id"], "props": d["props"]}) for d in p["data_source"]]))
    S.append(("3 machine profiles", [("""UNWIND $rows AS r MATCH (m:Machine {machine_id: r.machine_id})
        MERGE (mp:MachineProfile {machine_profile_id: r.id}) ON CREATE SET mp += r.props
        MERGE (mp)-[x:PROFILES_MACHINE {rel_id: r.rel_id}]->(m) ON CREATE SET x += r.rel""",
                                      {"rows": [{**r, "rel": _rel("PROFILES_MACHINE", "machine_profiles", r["id"])} for r in p["machine_profiles"]]})]))
    S.append(("4 part profile fields (null only)", [("""UNWIND $rows AS r MATCH (c:PartCatalogProfile {profile_id: r.profile_id})
        WITH c, r, [k IN keys(r.fields) WHERE c[k] IS NULL] AS empty WHERE size(empty) > 0
        SET c += apoc.map.submap(r.fields, empty, null, false)
        SET c.enriched_fields = apoc.coll.toSet(coalesce(c.enriched_fields, []) + empty), c.enrichment_source_id = $src, c.enrichment_batch = $batch""",
                                                      {"rows": p["part_profiles"], "src": SOURCE_ID, "batch": BATCH})]))
    S.append(("5 warehouse classification (null only)", [("""UNWIND $rows AS r MATCH (w:Warehouse {warehouse_id: r.id})
        WITH w, r, [k IN keys(r.fields) WHERE w[k] IS NULL] AS empty WHERE size(empty) > 0
        SET w += apoc.map.submap(r.fields, empty, null, false)
        SET w.enriched_fields = apoc.coll.toSet(coalesce(w.enriched_fields, []) + empty), w.enrichment_source_id = $src""",
                                                          {"rows": p["warehouses"], "src": SOURCE_ID})]))
    S.append(("6 assemblies", [
        ("UNWIND $rows AS r MERGE (a:Assembly {assembly_id: r.id}) ON CREATE SET a += r.props", {"rows": p["assemblies"]}),
        ("""UNWIND $rows AS r MATCH (pt:Part {part_id: r.part_id}) MATCH (a:Assembly {assembly_id: r.assembly_id})
            MERGE (pt)-[x:PART_OF {rel_id: r.rel_id}]->(a) ON CREATE SET x += r.props""", {"rows": p["part_of"]}),
    ]))
    S.append(("7 customer requests", [("""UNWIND $rows AS r
        MATCH (c:Customer {customer_id: r.customer_id}) MATCH (m:Machine {machine_id: r.machine_id}) MATCH (pt:Part {part_id: r.part_id})
        WHERE (pt)-[:FITS]->(m)
        MERGE (q:CustomerRequest {request_id: r.id}) ON CREATE SET q += r.props
        MERGE (q)-[a:OPENED_BY {rel_id: 'OPENED_BY:' + r.id}]->(c) ON CREATE SET a += r.rel
        MERGE (q)-[b:FOR_MACHINE {rel_id: 'FOR_MACHINE:' + r.id}]->(m) ON CREATE SET b += r.rel
        MERGE (q)-[d:REQUIRES_PART {rel_id: 'REQUIRES_PART:' + r.id}]->(pt) ON CREATE SET d += r.rel""",
                                       {"rows": [{**r, "rel": prov("customer_requests", r["id"])} for r in p["requests"]]})]))
    orders = p["orders"]
    S.append(("8 orders", [("""UNWIND $rows AS r MATCH (c:Customer {customer_id: r.customer_id})
        MERGE (o:Order {order_id: r.id}) ON CREATE SET o += r.props
        MERGE (o)-[a:ORDERED_BY {rel_id: 'ORDERED_BY:' + r.id}]->(c) ON CREATE SET a += r.rel
        WITH o, r OPTIONAL MATCH (ad:Address {address_id: r.address_id})
        FOREACH (_ IN CASE WHEN ad IS NULL THEN [] ELSE [1] END |
          MERGE (o)-[d:DELIVERS_TO_ADDRESS {rel_id: 'DELIVERS_TO_ADDRESS:' + r.id}]->(ad) ON CREATE SET d += r.rel)""",
                            {"rows": [{"id": o["id"], "customer_id": o["customer_id"], "address_id": o["address_id"], "props": o["props"], "rel": prov("orders", o["id"])} for o in orders]})]))
    lines = [{**ln, "order_id": o["id"], "status": o["status"], "rel": prov("order_lines", ln["id"])} for o in orders for ln in o["lines"]]
    S.append(("9 order lines", [("""UNWIND $rows AS r MATCH (o:Order {order_id: r.order_id}) MATCH (pt:Part {part_id: r.part_id}) MATCH (w:Warehouse {warehouse_id: r.warehouse_id})
        MERGE (l:OrderLine {order_line_id: r.id}) ON CREATE SET l += r.props
        MERGE (o)-[a:CONTAINS_LINE {rel_id: 'CONTAINS_LINE:' + r.id}]->(l) ON CREATE SET a += r.rel
        MERGE (l)-[b:REFERENCES_PART {rel_id: 'REFERENCES_PART:' + r.id}]->(pt) ON CREATE SET b += r.rel
        FOREACH (_ IN CASE WHEN r.status IN ['ALLOCATED', 'SHIPPED', 'DELIVERED'] THEN [1] ELSE [] END |
          MERGE (l)-[x:ALLOCATED_FROM {rel_id: 'ALLOCATED_FROM:' + r.id}]->(w) ON CREATE SET x += r.rel, x.allocation_status = r.props.allocation_status)
        FOREACH (_ IN CASE WHEN r.status = 'PROCESSING' THEN [1] ELSE [] END |
          MERGE (l)-[y:PLANNED_FULFILMENT_FROM {rel_id: 'PLANNED_FULFILMENT_FROM:' + r.id}]->(w) ON CREATE SET y += r.rel)""", {"rows": lines})]))
    events = [{**e, "order_id": o["id"], "rel": prov("order_status_history", e["id"])} for o in orders for e in o["events"]]
    S.append(("10 order status history", [("""UNWIND $rows AS r MATCH (o:Order {order_id: r.order_id}) MATCH (s:OrderStatus {order_status_code: r.status})
        MERGE (e:OrderStatusEvent {status_event_id: r.id}) ON CREATE SET e += r.props
        MERGE (o)-[a:HAS_STATUS_EVENT {rel_id: 'HAS_STATUS_EVENT:' + r.id}]->(e) ON CREATE SET a += r.rel
        MERGE (e)-[b:RECORDS_STATUS {rel_id: 'RECORDS_STATUS:' + r.id}]->(s) ON CREATE SET b += r.rel""", {"rows": events})]))
    ships = [{"id": o["shipment"]["id"], "order_id": o["id"], "customer_id": o["customer_id"], "warehouse_id": o["shipment"]["warehouse_id"], "carrier_id": p["carrier"][0]["id"],
              "props": o["shipment"]["props"], "lines": [ln["id"] for ln in o["lines"]], "rel": prov("shipments", o["shipment"]["id"])} for o in orders if o.get("shipment")]
    S.append(("11 shipments", [("""UNWIND $rows AS r MATCH (o:Order {order_id: r.order_id}) MATCH (c:Customer {customer_id: r.customer_id})
        MATCH (w:Warehouse {warehouse_id: r.warehouse_id}) MATCH (ca:Carrier {carrier_id: r.carrier_id})
        MERGE (s:Shipment {shipment_id: r.id}) ON CREATE SET s += r.props
        MERGE (o)-[a:HAS_SHIPMENT {rel_id: 'HAS_SHIPMENT:' + r.id}]->(s) ON CREATE SET a += r.rel
        MERGE (s)-[b:DISPATCHED_FROM {rel_id: 'DISPATCHED_FROM:' + r.id}]->(w) ON CREATE SET b += r.rel
        MERGE (s)-[d:CARRIED_BY {rel_id: 'CARRIED_BY:' + r.id}]->(ca) ON CREATE SET d += r.rel
        MERGE (s)-[e:DELIVERS_TO_CUSTOMER {rel_id: 'DELIVERS_TO_CUSTOMER:' + r.id}]->(c) ON CREATE SET e += r.rel
        WITH s, r UNWIND r.lines AS lid MATCH (l:OrderLine {order_line_id: lid})
        MERGE (s)-[f:SHIPS_LINE {rel_id: 'SHIPS_LINE:' + r.id + ':' + lid}]->(l) ON CREATE SET f += r.rel""", {"rows": ships})]))
    tracks = [{**e, "shipment_id": o["shipment"]["id"], "rel": prov("shipment_events", e["id"])} for o in orders if o.get("shipment") for e in o["shipment"]["events"]]
    S.append(("12 tracking events", [("""UNWIND $rows AS r MATCH (s:Shipment {shipment_id: r.shipment_id})
        MERGE (t:TrackingEvent {tracking_event_id: r.id}) ON CREATE SET t += r.props
        MERGE (s)-[a:HAS_TRACKING_EVENT {rel_id: 'HAS_TRACKING_EVENT:' + r.id}]->(t) ON CREATE SET a += r.rel""", {"rows": tracks})]))
    return S


# ── validation ────────────────────────────────────────────────────────────────────────────────────
ID_KEYS = {"Part": "part_id", "Machine": "machine_id", "Supplier": "supplier_id", "Dealer": "dealer_id", "Warehouse": "warehouse_id", "Assembly": "assembly_id",
           "Order": "order_id", "OrderLine": "order_line_id", "Shipment": "shipment_id", "TrackingEvent": "tracking_event_id", "ServicePlan": "service_plan_id",
           "Customer": "customer_id", "MachineProfile": "machine_profile_id", "CustomerRequest": "request_id", "OrderStatusEvent": "status_event_id"}
ALLOWED_DATA_STATUS = ["REAL", "SOURCE_DERIVED", "DERIVED", "SYNTHETIC_DEMO", "USER_PROVIDED", "TEST_DATA", "INTERNAL_REFERENCE_ONLY", "UNKNOWN", "NOT_CONNECTED"]


def validate() -> dict[str, Any]:
    v: dict[str, Any] = {}
    v["duplicate_nodes"] = sum(read(f"MATCH (n:{l}) WITH n.{k} AS id, count(*) AS c WHERE id IS NOT NULL AND c > 1 RETURN count(*) AS d")[0]["d"] for l, k in ID_KEYS.items())
    v["duplicate_relationship_ids"] = read("MATCH ()-[r]->() WHERE r.rel_id IS NOT NULL WITH r.rel_id AS id, count(*) AS c WHERE c > 1 RETURN count(*) AS d")[0]["d"]
    v["relationships_without_rel_id"] = read("MATCH ()-[r]->() WHERE r.rel_id IS NULL RETURN count(r) AS d")[0]["d"]
    v["duplicate_fitments"] = read("MATCH (p:Part)-[r:FITS]->(m:Machine) WITH p, m, count(r) AS c WHERE c > 1 RETURN count(*) AS d")[0]["d"]
    v["duplicate_supplier_links"] = read("MATCH (p:Part)-[r:SUPPLIED_BY]->(s:Supplier) WITH p, s, count(r) AS c WHERE c > 1 RETURN count(*) AS d")[0]["d"]
    v["duplicate_dealer_links"] = read("MATCH (p:Part)-[r:STOCKED_BY]->(d:Dealer) WITH p, d, count(r) AS c WHERE c > 1 RETURN count(*) AS d")[0]["d"]
    v["duplicate_assembly_links"] = read("MATCH (p:Part)-[r:PART_OF]->(a:Assembly) WITH p, a, count(r) AS c WHERE c > 1 RETURN count(*) AS d")[0]["d"]
    v["duplicate_order_lines"] = read("MATCH (o:Order)-[:CONTAINS_LINE]->(l:OrderLine)-[:REFERENCES_PART]->(p:Part) WITH o, p, count(l) AS c WHERE c > 1 RETURN count(*) AS d")[0]["d"]
    v["orphan_nodes"] = read("MATCH (n) WHERE NOT (n)--() AND NOT n:DataSource AND NOT n:OrderStatus RETURN count(n) AS d")[0]["d"]
    v["orphan_nodes_by_label"] = {r["l"]: r["c"] for r in read("MATCH (n) WHERE NOT (n)--() RETURN labels(n)[0] AS l, count(*) AS c")}
    v["order_lines_without_part"] = read("MATCH (l:OrderLine) WHERE NOT (l)-[:REFERENCES_PART]->(:Part) RETURN count(l) AS d")[0]["d"]
    v["orders_without_customer"] = read("MATCH (o:Order) WHERE NOT (o)-[:ORDERED_BY]->(:Customer) RETURN count(o) AS d")[0]["d"]
    v["shipments_without_order"] = read("MATCH (s:Shipment) WHERE NOT (:Order)-[:HAS_SHIPMENT]->(s) RETURN count(s) AS d")[0]["d"]
    v["invalid_data_status"] = read("MATCH (n) WHERE NOT coalesce(n.data_status, 'NULL') IN $ok RETURN count(n) AS d", ok=ALLOWED_DATA_STATUS)[0]["d"] + \
        read("MATCH ()-[r]->() WHERE NOT coalesce(r.data_status, 'NULL') IN $ok RETURN count(r) AS d", ok=ALLOWED_DATA_STATUS)[0]["d"]
    v["batch_nodes_missing_provenance"] = read("""MATCH (n {enrichment_batch: $b}) WHERE n.data_status <> 'SYNTHETIC_DEMO' AND NOT n:PartCatalogProfile
        OR n.enrichment_batch = $b AND (n.source_id IS NULL OR n.provenance_type IS NULL) RETURN count(n) AS d""", b=BATCH)[0]["d"]
    v["batch_relationships_missing_provenance"] = read("""MATCH ()-[r {enrichment_batch: $b}]->() WHERE r.data_status <> 'SYNTHETIC_DEMO' OR r.source_id <> $src OR r.rel_id IS NULL
        RETURN count(r) AS d""", b=BATCH, src=SOURCE_ID)[0]["d"]
    v["synthetic_fitments_created"] = read("MATCH ()-[r:FITS {enrichment_batch: $b}]->() RETURN count(r) AS d", b=BATCH)[0]["d"]
    v["requests_for_parts_that_do_not_fit"] = read("MATCH (q:CustomerRequest)-[:REQUIRES_PART]->(p), (q)-[:FOR_MACHINE]->(m) WHERE NOT (p)-[:FITS]->(m) RETURN count(q) AS d")[0]["d"]
    v["batch_orders_with_non_verified_parts"] = read("""MATCH (o:Order {enrichment_batch: $b})-[:CONTAINS_LINE]->(:OrderLine)-[:REFERENCES_PART]->(p)<-[:PROFILES_PART]-(c)
        WHERE c.part_status <> 'VERIFIED' OR c.orderable <> true RETURN count(*) AS d""", b=BATCH)[0]["d"]
    v["contradictory_inventory"] = read("MATCH ()-[r:AVAILABLE_AT]->() WHERE coalesce(r.available, 0) = 0 AND r.stock_status = 'IN_STOCK' RETURN count(r) AS d")[0]["d"]
    v["contradictory_order_shipment"] = read("""MATCH (o:Order)-[:HAS_SHIPMENT]->(s:Shipment)
        WHERE o.order_status IN ['NEW', 'CONFIRMED', 'PROCESSING', 'ALLOCATED', 'CANCELLED'] OR (o.order_status = 'SHIPPED' AND s.shipment_status = 'DELIVERED')
           OR (o.order_status = 'DELIVERED' AND s.shipment_status <> 'DELIVERED') RETURN count(*) AS d""")[0]["d"]
    v["shipped_orders_without_shipment"] = read("MATCH (o:Order) WHERE o.order_status IN ['SHIPPED', 'DELIVERED'] AND NOT (o)-[:HAS_SHIPMENT]->() RETURN count(o) AS d")[0]["d"]
    v["status_history_gaps"] = read("""MATCH (o:Order) WITH o, [(o)-[:HAS_STATUS_EVENT]->(e) | e.order_status] AS seen
        WHERE NOT o.order_status IN seen RETURN count(o) AS d""")[0]["d"]
    v["tracking_out_of_order"] = read("""MATCH (s:Shipment)-[:HAS_TRACKING_EVENT]->(t) WITH s, t ORDER BY t.event_seq WITH s, collect(t.event_date) AS d
        WHERE any(i IN range(0, size(d) - 2) WHERE d[i] > d[i + 1]) RETURN count(s) AS c""")[0]["c"]
    v["delivered_shipments_without_delivered_event"] = read("""MATCH (s:Shipment {shipment_status: 'DELIVERED'}) WHERE NOT (s)-[:HAS_TRACKING_EVENT]->(:TrackingEvent {event_status: 'DELIVERED'})
        RETURN count(s) AS d""")[0]["d"]
    v["batch_records"] = {
        "nodes": read("MATCH (n {enrichment_batch: $b}) WHERE n.data_status = 'SYNTHETIC_DEMO' AND NOT n:PartCatalogProfile RETURN count(n) AS d", b=BATCH)[0]["d"],
        "relationships": read("MATCH ()-[r {enrichment_batch: $b}]->() RETURN count(r) AS d", b=BATCH)[0]["d"],
        "enriched_existing_nodes": read("MATCH (n) WHERE n.enrichment_source_id = $src RETURN count(n) AS d", src=SOURCE_ID)[0]["d"],
    }
    problems = {k: x for k, x in v.items() if isinstance(x, int) and x and k not in ("orphan_nodes", "relationships_without_rel_id")}
    v["problems"] = problems
    return v


# ── commands ──────────────────────────────────────────────────────────────────────────────────────
def _write_report(name: str, data: dict[str, Any], md: str) -> None:
    AUDITS.mkdir(parents=True, exist_ok=True)
    (AUDITS / f"{name}.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    (AUDITS / f"{name}.md").write_text(md, encoding="utf-8")


def _audit_md(a: dict[str, Any]) -> str:
    rows = "\n".join(f"| {l} | {v['count']} | {', '.join(v['data_status'])} |" for l, v in a["labels"].items())
    rels = "\n".join(f"| {r['from']} | {r['type']} | {r['to']} | {r['count']} | {', '.join(r['data_status'])} |" for r in a["relationships"])
    gaps = "\n".join(f"| {k} | {json.dumps(v)} |" for k, v in a["gaps"].items())
    return f"""# Demo enrichment: graph audit

Taken {a['taken_at']} (read-only). Nodes **{a['totals']['nodes']}**, relationships **{a['totals']['relationships']}**, constraints {a['constraints']}.

Provenance (nodes): {json.dumps(a['provenance']['nodes'])}
Provenance (relationships): {json.dumps(a['provenance']['relationships'])}

Source fingerprint (every SOURCE_DERIVED / DERIVED / USER_PROVIDED node and relationship with all properties): `{a['source_checksum']}`

Schema-only labels (documented, no data): {', '.join(a['schema_only_labels']) or 'none'}

## Gaps
| Check | Value |
|---|---|
{gaps}

## Labels
| Label | Count | data_status |
|---|---|---|
{rows}

## Relationships
| From | Type | To | Count | data_status |
|---|---|---|---|---|
{rels}
"""


def cmd_audit() -> dict[str, Any]:
    a = audit()
    _write_report("demo_enrichment_audit", a, _audit_md(a))
    print(json.dumps({"totals": a["totals"], "gaps": a["gaps"], "provenance": a["provenance"], "schema_only_labels": a["schema_only_labels"],
                      "batch_already_present": a["enrichment_batch_present"]}, indent=2, default=str))
    return a


def cmd_plan() -> None:
    p = plan()
    print(json.dumps({k: len(v) for k, v in p.items()}, indent=2))
    print("order lines:", sum(len(o["lines"]) for o in p["orders"]), "| shipments:", sum(1 for o in p["orders"] if o.get("shipment")),
          "| tracking events:", sum(len(o["shipment"]["events"]) for o in p["orders"] if o.get("shipment")), "| status events:", sum(len(o["events"]) for o in p["orders"]))
    for r in p["requests"]:
        print("request", r["id"], r["props"]["request_text"], r["props"]["request_status"])
    for a in p["assemblies"]:
        print("assembly", a["id"], a["props"]["name"], sum(1 for x in p["part_of"] if x["assembly_id"] == a["id"]), "parts")
    for o in p["orders"]:
        print("order", o["id"], o["status"], [ln["part_id"] for ln in o["lines"]])


def cmd_apply() -> None:
    before = audit()
    if before["enrichment_batch_present"]:
        print(f"batch {BATCH} already present ({before['enrichment_batch_present']} records): re-running is safe; MERGE creates nothing that exists")
    p = plan()
    run: list[dict[str, Any]] = []
    for name, statements in stages(p):
        created = {"nodes": 0, "rels": 0, "props": 0, "deleted": 0}
        try:
            for query, params in statements:
                c = write(query, **params)
                for k in created:
                    created[k] += c[k]
        except Exception as exc:  # stop safely; earlier stages are complete and idempotent
            print(f"STAGE FAILED: {name}: {type(exc).__name__}: {str(exc)[:300]}")
            run.append({"stage": name, "error": type(exc).__name__})
            break
        if created["deleted"]:
            raise SystemExit(f"stage {name} deleted something; stopping")
        run.append({"stage": name, **created})
        print(f"{name}: +{created['nodes']} nodes, +{created['rels']} relationships, {created['props']} properties set")
    after = audit()
    v = validate()
    data = {"before": before["totals"], "after": after["totals"], "delta": {k: after["totals"][k] - before["totals"][k] for k in before["totals"]},
            "stages": run, "validation": v, "source_checksum_before": before["source_checksum"], "source_checksum_after": after["source_checksum"],
            "source_data_unchanged": before["source_checksum"] == after["source_checksum"], "provenance_after": after["provenance"], "gaps_after": after["gaps"]}
    runs = []
    log = AUDITS / "demo_enrichment_runs.json"
    if log.exists():
        runs = json.loads(log.read_text(encoding="utf-8"))
    runs.append({"at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "delta": data["delta"], "source_data_unchanged": data["source_data_unchanged"],
                 "problems": v["problems"]})
    log.write_text(json.dumps(runs, indent=2), encoding="utf-8")
    (AUDITS / "demo_enrichment_report.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"delta": data["delta"], "source_data_unchanged": data["source_data_unchanged"], "problems": v["problems"], "batch": v["batch_records"]}, indent=2))


def cmd_validate() -> None:
    v = validate()
    print(json.dumps(v, indent=2, default=str))


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "audit"
    {"audit": cmd_audit, "plan": cmd_plan, "apply": cmd_apply, "validate": cmd_validate}[command]()
    _client.close()
