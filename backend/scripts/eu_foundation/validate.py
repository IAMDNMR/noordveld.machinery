"""Read-only validation of the live graph after seeding. Exits non-zero if any hard check fails.

  python validate.py     writes backend/data/eu_foundation/validation.json
"""
from __future__ import annotations

import json
import sys
from typing import Any

from audit_before import source_checksum
from common import BATCH, dump, read
from geo import EU27

# verified, orderable parts that stay single-source on purpose: machine-specific assemblies (see supplier_top_up.py)
SINGLE_SOURCE_BY_DESIGN = ["PRT-018", "PRT-027", "PRT-097"]

CHECKS: list[dict[str, Any]] = []


def check(name: str, ok: bool, detail: Any = None) -> None:
    CHECKS.append({"check": name, "pass": bool(ok), "detail": detail})


def one(q: str, **p: Any) -> Any:
    rows = read(q, **p)
    return list(rows[0].values())[0] if rows else None


def main() -> int:
    B = {"b": BATCH}
    out: dict[str, Any] = {}

    # --- totals -------------------------------------------------------------------------------------------------------
    out["nodes_total"] = one("MATCH (n) RETURN count(n)")
    out["relationships_total"] = one("MATCH ()-[r]->() RETURN count(r)")
    out["nodes_added"] = one("MATCH (n) WHERE n.enrichment_batch = $b RETURN count(n)", **B)
    out["relationships_added"] = one("MATCH ()-[r]->() WHERE r.enrichment_batch = $b RETURN count(r)", **B)
    out["nodes_by_label_added"] = {r["l"]: r["n"] for r in read("MATCH (n) WHERE n.enrichment_batch = $b UNWIND labels(n) AS l RETURN l, count(*) AS n ORDER BY l", **B)}
    out["rels_by_type_added"] = {r["t"]: r["n"] for r in read("MATCH ()-[r]->() WHERE r.enrichment_batch = $b RETURN type(r) AS t, count(*) AS n ORDER BY t", **B)}

    # --- catalogue untouched ------------------------------------------------------------------------------------------
    cat = {"parts": one("MATCH (p:Part) RETURN count(p)"), "machines": one("MATCH (m:Machine) RETURN count(m)"), "fitments": one("MATCH (:Part)-[r:FITS]->(:Machine) RETURN count(r)"),
           "specs": one("MATCH (s:PartSpecification) RETURN count(s)"), "machine_specs": one("MATCH (s:MachineSpecification) RETURN count(s)"), "plants": one("MATCH (p:Plant) RETURN count(p)"), "business_units": one("MATCH (b:BusinessUnit) RETURN count(b)")}
    out["catalogue"] = cat
    check("catalogue: 100 parts", cat["parts"] == 100, cat["parts"])
    check("catalogue: 15 machines", cat["machines"] == 15, cat["machines"])
    check("catalogue: 219 fitments", cat["fitments"] == 219, cat["fitments"])
    check("catalogue: 279 part specs (83 machine specs untouched)", cat["specs"] == 279 and cat["machine_specs"] == 83, cat["specs"])
    check("plants and business units unchanged", cat["plants"] == 3 and cat["business_units"] == 3, cat)
    check("SOURCE/DERIVED DATA INTEGRITY CHECKSUM identical to the pre-seed baseline", source_checksum() == json.load(open(__import__("common").DATA_DIR / "audit_before.json", encoding="utf-8")).get("source_checksum"),
          "compared with audit_before.json")

    # --- provenance ---------------------------------------------------------------------------------------------------
    missing_n = one("MATCH (n) WHERE n.enrichment_batch = $b AND (n.data_status IS NULL OR n.provenance_type IS NULL OR n.source_id IS NULL OR n.demo_marker IS NULL) RETURN count(n)", **B)
    missing_r = one("MATCH ()-[r]->() WHERE r.enrichment_batch = $b AND (r.data_status IS NULL OR r.provenance_type IS NULL OR r.source_id IS NULL OR r.rel_id IS NULL) RETURN count(r)", **B)
    check("every added node has provenance", missing_n == 0, missing_n)
    check("every added relationship has provenance + rel_id", missing_r == 0, missing_r)
    bad_status = one("MATCH (n) WHERE n.enrichment_batch = $b AND n.data_status <> 'SYNTHETIC_DEMO' RETURN count(n)", **B)
    check("added nodes never labelled as source/real", bad_status == 0, bad_status)
    out["provenance_nodes"] = {str(r["s"]): r["n"] for r in read("MATCH (n) RETURN n.data_status AS s, count(*) AS n ORDER BY n DESC")}
    out["provenance_rels"] = {str(r["s"]): r["n"] for r in read("MATCH ()-[r]->() RETURN r.data_status AS s, count(*) AS n ORDER BY n DESC")}
    out["provenance_nodes_added"] = {str(r["s"]): r["n"] for r in read("MATCH (n) WHERE n.enrichment_batch = $b RETURN n.data_status AS s, count(*) AS n", **B)}
    out["provenance_rels_added"] = {str(r["s"]): r["n"] for r in read("MATCH ()-[r]->() WHERE r.enrichment_batch = $b RETURN r.data_status AS s, count(*) AS n", **B)}

    # --- geography ----------------------------------------------------------------------------------------------------
    cc = {}
    for label in ("Dealer", "Supplier", "Customer", "ShipTo", "Warehouse", "TransportTerminal"):
        cc[label] = {r["c"]: r["n"] for r in read(f"MATCH (n:`{label}`) WHERE NOT coalesce(n.canonical_dataset, '') STARTS WITH 'network_' RETURN n.country_code AS c, count(*) AS n ORDER BY c")}
    out["country_counts"] = cc
    for label, rows in cc.items():
        non = [c for c in rows if c not in EU27]
        check(f"{label}: all countries EU27 (no GB/US)", not non, non)
    check("dealers cover all 27 member states", set(cc["Dealer"]) == set(EU27), sorted(set(EU27) - set(cc["Dealer"])))
    check("ship-tos cover all 27 member states", set(cc["ShipTo"]) == set(EU27), sorted(set(EU27) - set(cc["ShipTo"])))
    check("NL and DE are the densest dealer countries", sorted(cc["Dealer"], key=cc["Dealer"].get, reverse=True)[:2] in (["NL", "DE"], ["DE", "NL"]), {k: cc["Dealer"][k] for k in ("NL", "DE")})

    # --- counts vs. brief ---------------------------------------------------------------------------------------------
    n = {l: one(f"MATCH (n:`{l}`) WHERE NOT coalesce(n.canonical_dataset, '') STARTS WITH 'network_' RETURN count(n)") for l in ("Supplier", "Dealer", "Customer", "ShipTo", "Warehouse", "TransportTerminal", "Carrier", "TransportOption")}
    out["entity_totals"] = n
    check("suppliers 30-60", 30 <= n["Supplier"] <= 60, n["Supplier"])
    check("dealers 60-100", 60 <= n["Dealer"] <= 100, n["Dealer"])
    check("no synthetic EU customer master remains (customers are the original 10)", one("MATCH (c:Customer) WHERE c.enrichment_batch = $b RETURN count(c)", **B) == 0 and n["Customer"] == 10, n["Customer"])
    check("ship-tos 200-300", 200 <= n["ShipTo"] <= 300, n["ShipTo"])
    check("depots 8-15", 8 <= n["Warehouse"] <= 15, n["Warehouse"])
    check("terminals 20-50", 20 <= n["TransportTerminal"] <= 50, n["TransportTerminal"])
    check("providers 20-40", 20 <= n["Carrier"] <= 40, n["Carrier"])
    nopt = one("MATCH (o:TransportOption) WHERE o.enrichment_batch = $b RETURN count(o)", **B)
    check("new transport options 10-20", 10 <= nopt <= 20, nopt)

    # --- orphans / integrity ------------------------------------------------------------------------------------------
    def zero(name: str, q: str, **p: Any) -> None:
        v = one(q, **p)
        check(name, v == 0, v)
        out.setdefault("integrity", {})[name] = v

    zero("dealers without a location", "MATCH (d:Dealer) WHERE NOT coalesce(d.canonical_dataset, '') STARTS WITH 'network_' AND NOT (d)-[:LOCATED_IN]->(:Location) RETURN count(d)")
    zero("dealers without any machine-family support", "MATCH (d:Dealer) WHERE NOT coalesce(d.canonical_dataset, '') STARTS WITH 'network_' AND NOT (d)-[:SERVES_FAMILY|SERVICES_MACHINE_FAMILY|SELLS_MACHINE_FAMILY]->(:MachineFamily) RETURN count(d)")
    zero("dealers without a territory", "MATCH (d:Dealer) WHERE NOT coalesce(d.canonical_dataset, '') STARTS WITH 'network_' AND NOT (d)-[:SERVES_TERRITORY]->() RETURN count(d)")
    zero("suppliers without supplied parts", "MATCH (s:Supplier) WHERE s.enrichment_batch = $b AND NOT (:Part)-[:SUPPLIED_BY]->(s) RETURN count(s)", **B)
    zero("batch ship-tos owned by a customer (destinations are not customer-owned)", "MATCH (:Customer)-[r:HAS_SHIP_TO]->(s:ShipTo) WHERE s.enrichment_batch = $b RETURN count(r)", **B)
    zero("batch customer contacts / customer addresses remaining", "MATCH (n) WHERE n.enrichment_batch = $b AND (n:CustomerContact OR (n:Address AND n.owner_type = 'CUSTOMER')) RETURN count(n)", **B)
    zero("orphan nodes in the batch (no relationship at all; DataSource registry entries are standalone by design)", "MATCH (n) WHERE n.enrichment_batch = $b AND NOT n:DataSource AND NOT (n)--() RETURN count(n)", **B)
    zero("parts with no supplier", "MATCH (p:Part) WHERE NOT (p)-[:SUPPLIED_BY]->(:Supplier) RETURN count(p)")
    zero("supplier links pointing at a non-Part or non-Supplier", "MATCH (a)-[r:SUPPLIED_BY]->(b) WHERE NOT (a:Part AND b:Supplier) RETURN count(r)")
    zero("duplicate part-supplier pairs", "MATCH (p:Part)-[r:SUPPLIED_BY]->(s:Supplier) WITH p, s, count(r) AS c WHERE c > 1 RETURN count(*)")
    zero("verified orderable parts with fewer than 1 supplier or a single supplier outside the single-source list",
         "MATCH (c:PartCatalogProfile {part_status:'VERIFIED', orderable:true})-[:PROFILES_PART]->(p:Part) WHERE NOT p.part_id IN $single AND COUNT { (p)-[:SUPPLIED_BY]->(:Supplier) } < 2 RETURN count(p)", single=SINGLE_SOURCE_BY_DESIGN)
    zero("supplier linked directly to a dealer (no blanket supplier-dealer links)", "MATCH (:Supplier)-[r]-(:Dealer) RETURN count(r)")
    zero("suppliers without a replenished depot", "MATCH (s:Supplier) WHERE NOT coalesce(s.canonical_dataset, '') STARTS WITH 'network_' AND NOT (s)-[:REPLENISHES_DEPOT]->(:Warehouse) RETURN count(s)")
    zero("ship-tos without any route", "MATCH (s:ShipTo) WHERE s.enrichment_batch = $b AND NOT (:TransportRoute)-[:TO_SHIP_TO]->(s) RETURN count(s)", **B)
    zero("depots without a location", "MATCH (w:Warehouse) WHERE NOT (w)-[:LOCATED_IN]->(:Location) RETURN count(w)")
    zero("routes without origin depot", "MATCH (r:TransportRoute) WHERE NOT coalesce(r.canonical_dataset, '') STARTS WITH 'network_' AND NOT (r)-[:FROM_DEPOT]->(:Warehouse) RETURN count(r)")
    zero("routes without destination ship-to", "MATCH (r:TransportRoute) WHERE NOT coalesce(r.canonical_dataset, '') STARTS WITH 'network_' AND NOT (r)-[:TO_SHIP_TO]->(:ShipTo) RETURN count(r)")
    zero("routes without option or rate", "MATCH (r:TransportRoute) WHERE NOT coalesce(r.canonical_dataset, '') STARTS WITH 'network_' AND (NOT (r)-[:USES_OPTION]->(:TransportOption) OR NOT (r)-[:PRICED_BY]->(:FreightRate)) RETURN count(r)")
    zero("routes without legs", "MATCH (r:TransportRoute) WHERE NOT (r)-[:HAS_LEG]->(:TransportLeg) RETURN count(r)")
    zero("multimodal routes with fewer than 2 distinct modes",
         "MATCH (r:TransportRoute {transport_mode:'MULTIMODAL'})-[:HAS_LEG]->(l:TransportLeg) WITH r, count(DISTINCT l.mode) AS m WHERE m < 2 RETURN count(r)")
    zero("legs not attached to a route", "MATCH (l:TransportLeg) WHERE NOT (:TransportRoute)-[:HAS_LEG]->(l) RETURN count(l)")
    zero("route without positive distance", "MATCH (r:TransportRoute) WHERE NOT coalesce(r.canonical_dataset, '') STARTS WITH 'network_' AND (r.total_distance_km IS NULL OR r.total_distance_km <= 0) RETURN count(r)")
    zero("route whose estimate is not labelled ESTIMATED", "MATCH (r:TransportRoute) WHERE NOT coalesce(r.canonical_dataset, '') STARTS WITH 'network_' AND r.estimate_basis <> 'ESTIMATED' RETURN count(r)")
    zero("distance without a distance_type", "MATCH ()-[d:DISTANCE_TO]->() WHERE d.enrichment_batch = $b AND d.distance_type IS NULL RETURN count(d)", **B)
    zero("freight rate without currency EUR or components",
         "MATCH (f:FreightRate) WHERE f.enrichment_batch = $b AND (f.currency <> 'EUR' OR f.base_cost IS NULL OR f.total_transport_cost IS NULL OR f.handling_cost IS NULL) RETURN count(f)", **B)
    zero("freight rate total != base + additional + handling",
         "MATCH (f:FreightRate) WHERE f.enrichment_batch = $b AND abs(f.total_cost_incl_handling - (f.base_cost + f.additional_cost + f.handling_cost)) > 0.02 RETURN count(f)", **B)
    zero("UNKNOWN stock carrying a quantity", "MATCH ()-[a:AVAILABLE_AT]->() WHERE a.stock_status = 'UNKNOWN' AND a.available IS NOT NULL RETURN count(a)")
    zero("OUT_OF_STOCK rows with stock", "MATCH ()-[a:AVAILABLE_AT]->() WHERE a.stock_status = 'OUT_OF_STOCK' AND coalesce(a.available, 0) > 0 RETURN count(a)")
    zero("IN_STOCK rows without positive stock", "MATCH ()-[a:AVAILABLE_AT]->() WHERE a.stock_status = 'IN_STOCK' AND coalesce(a.available, 0) <= 0 RETURN count(a)")
    zero("negative stock fields", "MATCH ()-[a:AVAILABLE_AT]->() WHERE a.available < 0 OR a.reserved < 0 OR a.on_hand < 0 RETURN count(a)")
    zero("depot inventory on parts not in catalogue", "MATCH (p)-[a:AVAILABLE_AT]->(:Warehouse) WHERE a.enrichment_batch = $b AND NOT p:Part RETURN count(a)", **B)
    zero("dealer-part links to non-catalogue parts", "MATCH (p)-[r:STOCKED_BY|CAN_ORDER_PART|INSTALLS_PART|SERVICES_PART]-(d:Dealer) WHERE r.enrichment_batch = $b AND NOT (p:Part OR d:Part) RETURN count(r)", **B)
    zero("non-orderable parts newly stocked at depots",
         "MATCH (p:Part)-[a:AVAILABLE_AT]->(:Warehouse) WHERE a.enrichment_batch = $b AND a.stock_status IN ['IN_STOCK','LOW_STOCK'] AND coalesce(p.part_status,'') IN ['DISCONTINUED','OBSOLETE'] RETURN count(a)", **B)
    zero("batch nodes duplicated by id",
         "MATCH (n) WHERE n.enrichment_batch = $b AND n.source_record_id IS NOT NULL WITH n.source_record_id AS i, labels(n)[0] AS l, count(*) AS c WHERE c > 1 RETURN count(*)", **B)
    zero("duplicate rel_id within a type", "MATCH ()-[r]->() WHERE r.rel_id IS NOT NULL WITH type(r) AS t, r.rel_id AS i, count(*) AS c WHERE c > 1 RETURN count(*)")
    zero("supplier linked directly to a machine (no inference allowed)", "MATCH (:Supplier)-[r]-(:Machine) RETURN count(r)")
    zero("dealer linked directly to a ship-to (no inference allowed)", "MATCH (:Dealer)-[r]-(:ShipTo) RETURN count(r)")
    zero("customer linked to a depot or dealer by distance", "MATCH (:Customer)-[r:DISTANCE_TO]-() RETURN count(r)")
    zero("new fitments / supersessions / interchange created",
         "MATCH ()-[r:FITS|SUPERSEDES|INTERCHANGEABLE_WITH|REPLACES]->() WHERE r.enrichment_batch = $b RETURN count(r)", **B)
    zero("new Part / Machine / Specification / Plant nodes", "MATCH (n) WHERE n.enrichment_batch = $b AND (n:Part OR n:Machine OR n:MachineSpecification OR n:PartSpecification OR n:Plant OR n:BusinessUnit) RETURN count(n)", **B)

    # --- transport ----------------------------------------------------------------------------------------------------
    out["routes_by_mode"] = {r["m"]: r["n"] for r in read("MATCH (r:TransportRoute) WHERE NOT coalesce(r.canonical_dataset, '') STARTS WITH 'network_' RETURN r.transport_mode AS m, count(*) AS n ORDER BY m")}
    out["routes_by_option"] = {r["o"]: r["n"] for r in read("MATCH (r:TransportRoute) WHERE NOT coalesce(r.canonical_dataset, '') STARTS WITH 'network_' RETURN r.option_code AS o, count(*) AS n ORDER BY o")}
    out["legs_by_mode"] = {r["m"]: r["n"] for r in read("MATCH (l:TransportLeg) RETURN l.mode AS m, count(*) AS n ORDER BY m")}
    out["terminals_by_type"] = {r["t"]: r["n"] for r in read("MATCH (t:TransportTerminal) RETURN t.terminal_type AS t, count(*) AS n ORDER BY t")}
    out["distance_types"] = {str(r["t"]): r["n"] for r in read("MATCH ()-[d:DISTANCE_TO]->() RETURN d.distance_type AS t, count(*) AS n ORDER BY n DESC")}
    out["rate_bands"] = {r["b"]: r["n"] for r in read("MATCH (f:FreightRate) WHERE f.enrichment_batch = $b RETURN f.distance_band AS b, count(*) AS n ORDER BY b", **B)}
    out["stock_status"] = {str(r["s"]): r["n"] for r in read("MATCH ()-[a:AVAILABLE_AT]->(:Warehouse) RETURN a.stock_status AS s, count(*) AS n ORDER BY n DESC")}
    out["stock_status_new"] = {str(r["s"]): r["n"] for r in read("MATCH ()-[a:AVAILABLE_AT]->(:Warehouse) WHERE a.enrichment_batch = $b RETURN a.stock_status AS s, count(*) AS n ORDER BY n DESC", **B)}
    for mode in ("ROAD", "RAIL", "INLAND_WATERWAY", "SHORT_SEA", "AIR", "MULTIMODAL"):
        check(f"routes exist for mode {mode}", out["routes_by_mode"].get(mode, 0) > 0, out["routes_by_mode"].get(mode, 0))
    out["dealer_relationships"] = {r["t"]: r["n"] for r in read("MATCH (:Dealer)-[r]->() RETURN type(r) AS t, count(*) AS n ORDER BY t")}
    out["dealer_capability_counts"] = {r["c"]: r["n"] for r in read("MATCH (:Dealer)-[:HAS_CAPABILITY]->(c:Capability) RETURN c.name AS c, count(*) AS n ORDER BY c")}
    out["customers_by_industry"] = {r["i"]: r["n"] for r in read("MATCH (:Customer)-[:IN_INDUSTRY]->(i:Industry) RETURN i.name AS i, count(*) AS n ORDER BY n DESC")}
    out["order_status_vocabulary"] = [r["s"] for r in read("MATCH (s:OrderStatus) RETURN s.status_code AS s ORDER BY s")] if one("MATCH (s:OrderStatus) RETURN count(s)") else []

    out["checks"] = CHECKS
    out["passed"] = sum(c["pass"] for c in CHECKS)
    out["failed"] = [c for c in CHECKS if not c["pass"]]
    dump("validation.json", out)
    print(f"{out['passed']}/{len(CHECKS)} checks passed")
    for c in out["failed"]:
        print("FAIL:", c["check"], c["detail"])
    return 0 if not out["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
