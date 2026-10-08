"""Graph -> canonical files (read-only migration of what already exists).

Every exported value is read from the graph; nothing is invented. Where the graph does not state a value the canonical field is left empty, and where a
mapping would reinterpret an unsupported value the export stops with an error instead of guessing. Records written by the running app (source_id
APP-SESSION: live orders, carts, app shipments) are NOT exported: they change in normal use and the graph stays their owner.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from app.canonical.engine import APP_SESSION, normalise
from app.canonical.io import CANON_DIR, dump_rows
from app.canonical.registry import BY_NAME, DatasetSpec
from app.core.config import get_settings
from app.graph.client import GraphClient


class ExportError(Exception):
    pass


FITMENT_MAP = {"CONFIRMED": "APPROVED", "CONDITIONAL": "CONDITIONAL"}  # an unsupported graph value stops the export
NOT_APP = f"coalesce({{v}}.source_id, '') <> '{APP_SESSION}'"
# records the Phase 2 network datasets own are not exported again: their files are the source
NOT_NET = "NOT coalesce({v}.canonical_dataset, '') STARTS WITH 'network_'"
TERMINAL_TYPE = {"SEAPORT": "PORT", "AIRPORTCARGOTERMINAL": "AIRPORT"}  # any other terminal is a TERMINAL
AUTHORISED = {"AUTHORISED_DEALER": "AUTHORISED", "SERVICE_PARTNER": "SERVICE_PARTNER", "INDUSTRIAL_SPECIALIST": "INDEPENDENT"}
SERVICE_CAPABILITIES = {"INSTALLATION", "MAINTENANCE", "REPAIR"}
SOURCE_TYPE = {"SOURCE_DERIVED": "OEM_MASTER", "DERIVED": "OEM_MASTER", "USER_PROVIDED": "OEM_MASTER", "REAL": "OEM_MASTER", "SYNTHETIC_DEMO": "SYNTHETIC_DEMO",
               "REFERENCE": "REFERENCE", "TEST": "SYNTHETIC_DEMO"}


class Exporter:
    def __init__(self, vocab: dict[str, Any] | None = None) -> None:
        s = get_settings()
        self.g = GraphClient(dataclasses.replace(s, neo4j_query_timeout=180.0))
        self.vocab = vocab or json.loads((CANON_DIR / "reference" / "discovery_vocabulary.json").read_text(encoding="utf-8"))
        self.geo = json.loads((CANON_DIR / "reference" / "geography.json").read_text(encoding="utf-8"))

    def where(self, cc: str | None) -> dict[str, Any]:
        """country, region and timezone of a country code, from the geography reference (never guessed: an unknown code gives nothing)."""
        c = self.geo["countries"].get(cc or "")
        return {"country": c["name"], "region": c["region"], "timezone": c["timezone"]} if c else {"country": None, "region": None, "timezone": None}

    def close(self) -> None:
        self.g.close()

    # ── helpers ──────────────────────────────────────────────────────────────────────────────────
    def rd(self, q: str, **p: Any) -> list[dict[str, Any]]:
        return self.g.read(q, **p)

    @staticmethod
    def prov(p: dict[str, Any], status: str | None = None) -> dict[str, Any]:
        ds = status or p.get("data_status") or "SYNTHETIC_DEMO"
        return {"data_status": ds, "source_type": SOURCE_TYPE.get(ds, "SYNTHETIC_DEMO"), "source_record_id": p.get("source_record_id")}

    @staticmethod
    def strip(rel_id: str, prefix: str) -> str:
        if not rel_id.startswith(prefix + ":"):
            raise ExportError(f"relationship id {rel_id!r} does not start with {prefix}:")
        return rel_id[len(prefix) + 1:]

    # ── master ───────────────────────────────────────────────────────────────────────────────────
    def plants(self):
        return [{"plant_id": r["p"]["plant_id"], "name": r["p"].get("name"), "city": r["p"].get("city"), "country_code": r["p"].get("country_code"), **self.prov(r["p"])}
                for r in self.rd("MATCH (p:Plant) RETURN properties(p) AS p")]

    def locations(self):
        out = []
        for r in self.rd("MATCH (p:Plant) RETURN properties(p) AS p"):
            p = r["p"]
            out.append({"location_id": p["plant_id"], "name": p.get("name"), "location_kind": "PLANT", "graph_label": "Plant", "country_code": p.get("country_code"),
                        "city": p.get("city"), "location_type": "PLANT", **self.where(p.get("country_code")), **self.prov(p)})
        for r in self.rd("MATCH (w:Warehouse) RETURN properties(w) AS p"):
            p = r["p"]
            kind = "DISTRIBUTION_CENTER" if p.get("warehouse_type") == "CENTRAL_DC" else "WAREHOUSE"
            out.append({"location_id": p["warehouse_id"], "name": p.get("name"), "location_kind": "DEPOT", "graph_label": "Warehouse", "country_code": p.get("country_code"),
                        "city": p.get("city"), "latitude": p.get("latitude"), "longitude": p.get("longitude"), "geo_basis": p.get("geo_basis"), "location_type": kind,
                        **self.where(p.get("country_code")), **self.prov(p)})
        for r in self.rd("MATCH (s:ShipTo) WHERE " + NOT_NET.format(v="s") + " RETURN properties(s) AS p"):
            p = r["p"]
            out.append({"location_id": p["shipto_id"], "name": p.get("name"), "location_kind": "SHIP_TO", "graph_label": "ShipTo", "country_code": p.get("country_code"),
                        "city": p.get("city"), "latitude": p.get("latitude"), "longitude": p.get("longitude"), "geo_basis": p.get("geo_basis"), **self.prov(p)})
        coords = self.geo["city_coordinates"]
        for r in self.rd("MATCH (l:Location) WHERE " + NOT_NET.format(v="l") + " RETURN properties(l) AS p"):
            p = r["p"]
            lat, lon = (coords.get(p.get("name") or "") or (None, None)) if p.get("location_type") == "CITY" else (None, None)
            out.append({"location_id": p["location_id"], "name": p.get("name"), "location_kind": p["location_type"], "graph_label": "Location", "country_code": p.get("country_code"),
                        "city": None, "latitude": lat, "longitude": lon, "geo_basis": "REFERENCE_CITY_CENTRE" if lat is not None else None, **self.prov(p)})
        for r in self.rd("MATCH (t:TransportTerminal) WHERE " + NOT_NET.format(v="t") + " RETURN properties(t) AS p"):
            p = r["p"]
            tt = p.get("terminal_type")
            out.append({"location_id": p["terminal_id"], "name": p.get("name"), "location_kind": "TERMINAL", "graph_label": "TransportTerminal", "country_code": p.get("country_code"),
                        "city": p.get("city"), "latitude": p.get("latitude"), "longitude": p.get("longitude"), "geo_basis": p.get("geo_basis"),
                        "location_type": TERMINAL_TYPE.get(tt, "TERMINAL"), "terminal_type": tt, "modes": p.get("modes") or [], **self.where(p.get("country_code")), **self.prov(p)})
        for r in self.rd("MATCH (d:Dealer) WHERE " + NOT_NET.format(v="d") + " RETURN properties(d) AS p"):
            p = r["p"]
            out.append({"location_id": p["dealer_id"], "name": p.get("name"), "location_kind": "DEALER", "graph_label": "Dealer", "country_code": p.get("country_code"),
                        "city": p.get("city"), "latitude": p.get("latitude"), "longitude": p.get("longitude"), "geo_basis": p.get("geo_basis"), "location_type": "DEALER",
                        **self.where(p.get("country_code")), **self.prov(p)})
        return out

    def categories(self):
        return [{"category_id": r["p"]["category_id"], "name": r["p"].get("name"), "parent_category_id": r["parent"], "status": None, **self.prov(r["p"])}
                for r in self.rd("MATCH (c:Category) OPTIONAL MATCH (c)-[:SUBCATEGORY_OF]->(p:Category) RETURN properties(c) AS p, p.category_id AS parent")]

    def machines(self):
        return [{"machine_id": r["p"]["machine_id"], "manufacturer": r["brand"], "model": r["p"]["model_code"], "machine_type": r["p"].get("machine_type"), "model_year": None,
                 "variant_id": None, "plant_id": r["plant"], "status": None, "name": r["p"].get("name"), **self.prov(r["p"])}
                for r in self.rd("MATCH (m:Machine) OPTIONAL MATCH (m)-[:BRANDED_AS]->(b:BusinessUnit) OPTIONAL MATCH (m)-[:MANUFACTURED_AT]->(pl:Plant) "
                                 "RETURN properties(m) AS p, b.name AS brand, pl.plant_id AS plant")]

    def suppliers(self):
        return [{"supplier_id": r["p"]["supplier_id"], "name": r["p"].get("name"), "city": r["p"].get("city"), "country_code": r["p"].get("country_code"),
                 "supplier_type": r["p"].get("supplier_type"), "status": r["p"].get("supplier_status"), **self.prov(r["p"])}
                for r in self.rd("MATCH (s:Supplier) WHERE " + NOT_NET.format(v="s") + " RETURN properties(s) AS p")]

    def dealers(self):
        out = []
        for r in self.rd("MATCH (d:Dealer) WHERE " + NOT_NET.format(v="d") + " RETURN properties(d) AS p, exists { (d)-[:HAS_CAPABILITY]->(:Capability {name: 'Warranty Service'}) } AS warranty"):
            p = r["p"]
            caps = set(p.get("service_capability") or [])
            out.append({"dealer_id": p["dealer_id"], "name": p.get("name"), "city": p.get("city"), "country_code": p.get("country_code"), "dealer_type": p.get("dealer_type"),
                        "status": p.get("dealer_status"), "latitude": p.get("latitude"), "longitude": p.get("longitude"), "location_id": p["dealer_id"],
                        "authorized_status": AUTHORISED.get(p.get("dealer_type")), "service_capable": bool(caps & SERVICE_CAPABILITIES), "warranty_capable": bool(r["warranty"]),
                        **{k: v for k, v in self.where(p.get("country_code")).items() if k != "timezone"}, **self.prov(p)})
        return out

    def parts(self):
        rows = self.rd("""MATCH (p:Part)
            OPTIONAL MATCH (p)-[:IN_CATEGORY]->(c:Category) OPTIONAL MATCH (p)-[:IN_SUBCATEGORY]->(s:Category)
            OPTIONAL MATCH (c2:PartCatalogProfile)-[:PROFILES_PART]->(p)
            RETURN properties(p) AS p, c.category_id AS cat, c.name AS cat_name, s.category_id AS sub, s.name AS sub_name, c2.part_status AS status,
              [(p)-[:HAS_ALIAS]->(a:SearchAlias) | [a.alias, a.alias_type]] AS aliases,
              [(p)-[:FITS]->(m:Machine) | m.model_code] AS fits,
              [(p)-[:HAS_SPECIFICATION]->(sp:PartSpecification) WHERE NOT sp.name IN ['Note segment', 'Spec Note'] | [sp.name, sp.value]] AS specs""")
        sym = self.vocab["symptoms_by_category"]
        out = []
        for r in rows:
            p = r["p"]
            aliases = sorted({a for a, _ in r["aliases"] if a})
            common = sorted({a for a, t in r["aliases"] if a and t == "SYNONYM_DEMO"})
            fits = sorted(set(r["fits"]))
            desc = f"{p.get('name')}. {r['sub_name'] or r['cat_name'] or 'Part'} ({r['cat_name']})." + (f" Recorded as fitting {', '.join(fits)}." if fits else "")
            terms = sorted({f"{n} {v}" for n, v in r["specs"] if n and v is not None and not n.startswith("Dimension")})
            out.append({"part_id": p["part_id"], "part_number": p["part_number"], "name": p.get("name"), "description": desc, "category_id": r["cat"], "subcategory_id": r["sub"],
                        "manufacturer": p.get("brand"), "oem_status": "OEM" if p.get("origin_plant") else "UNKNOWN", "status": r["status"], "aliases": aliases,
                        "common_names": common, "technical_terms": terms, "symptoms": sym.get(r["cat_name"] or "", []), **self.prov(p)})
        return out

    def specifications(self):
        return [{"specification_id": r["p"]["specification_id"], "part_id": r["part"], "name": r["p"].get("name"), "value": r["p"].get("value"), "unit": None,
                 "source_text": r["p"].get("source_text"), "group": r["p"].get("group"), **self.prov(r["p"])}
                for r in self.rd("MATCH (p:Part)-[:HAS_SPECIFICATION]->(s:PartSpecification) RETURN properties(s) AS p, p.part_id AS part")]

    # ── relationships ────────────────────────────────────────────────────────────────────────────
    def fitment(self):
        out = []
        for r in self.rd("MATCH (p:Part)-[f:FITS]->(m:Machine) RETURN properties(f) AS f, p.part_id AS part, m.machine_id AS machine"):
            f = r["f"]
            status = FITMENT_MAP.get(f.get("fitment_status"))
            if status is None:
                raise ExportError(f"fitment {f.get('rel_id')}: unsupported fitment_status {f.get('fitment_status')!r} (not reinterpreted)")
            out.append({"fitment_id": f["rel_id"], "machine_id": r["machine"], "variant_id": None, "part_id": r["part"], "fitment_status": status, "approval_status": status,
                        "fitment_rule": f.get("fitment_type"), "valid_from": None, "valid_to": None, "data_status": "SYNTHETIC_DEMO", "source_type": "SYNTHETIC_DEMO",
                        "source_record_id": f.get("source_record_id")})
        return out

    def approved_sources(self):
        out = []
        for r in self.rd("MATCH (p:Part)-[x:SUPPLIED_BY]->(s:Supplier) RETURN properties(x) AS x, p.part_id AS part, s.supplier_id AS sup"):
            x = r["x"]
            if not str(x.get("relationship_status", "")).startswith("ACTIVE"):
                raise ExportError(f"{x.get('rel_id')}: relationship_status {x.get('relationship_status')!r} cannot be read as an approval")
            out.append({"approved_source_id": f"AS-{r['part']}-{r['sup']}", "part_id": r["part"], "source_id": r["sup"], "source_kind": "SUPPLIER", "approval_status": "APPROVED",
                        "approved_regions": [], "valid_from": None, "valid_to": None, "data_status": "SYNTHETIC_DEMO", "source_type": "SYNTHETIC_DEMO",
                        "source_record_id": x.get("source_record_id")})
        return out

    def assemblies(self):
        return [{"link_id": self.strip(r["x"]["rel_id"], "PART_OF"), "part_id": r["part"], "assembly_id": r["asm"], "quantity": r["x"].get("quantity"), "basis": r["x"].get("basis"),
                 **self.prov(r["x"])} for r in self.rd("MATCH (p:Part)-[x:PART_OF]->(a:Assembly) RETURN properties(x) AS x, p.part_id AS part, a.assembly_id AS asm")]

    def legacy_part_mappings(self):
        return [{"legacy_mapping_id": self.strip(r["x"]["rel_id"], "HAS_LEGACY_REFERENCE"), "part_id": r["part"], "legacy_part_number": r["l"].get("legacy_part_number"),
                 "legacy_system": r["l"].get("legacy_system"), **self.prov(r["x"])}
                for r in self.rd("MATCH (p:Part)-[x:HAS_LEGACY_REFERENCE]->(l:LegacyReference) RETURN properties(x) AS x, properties(l) AS l, p.part_id AS part")]

    # ── commerce ─────────────────────────────────────────────────────────────────────────────────
    def customers(self):
        return [{"customer_id": r["p"]["customer_id"], "name": r["p"].get("name"), "city": r["p"].get("city"), "country_code": r["p"].get("country_code"),
                 "customer_type": r["p"].get("customer_type"), "status": r["p"].get("customer_status"), **self.prov(r["p"])} for r in self.rd("MATCH (c:Customer) RETURN properties(c) AS p")]

    def orders(self):
        return [{"order_id": r["p"]["order_id"], "customer_id": r["cust"], "dealer_id": None, "order_date": r["p"].get("order_date"), "status": r["p"].get("order_status"),
                 "priority": None, "currency": r["p"].get("currency"), "total_value": r["p"].get("order_total_incl_vat"), "channel": r["p"].get("channel"), **self.prov(r["p"])}
                for r in self.rd(f"MATCH (o:Order) WHERE {NOT_APP.format(v='o')} AND {NOT_NET.format(v='o')} OPTIONAL MATCH (o)-[:ORDERED_BY]->(c:Customer) RETURN properties(o) AS p, c.customer_id AS cust")]

    def order_lines(self):
        return [{"order_line_id": r["p"]["order_line_id"], "order_id": r["order"], "part_id": r["part"], "quantity": r["p"].get("quantity"), "unit_price": r["p"].get("unit_price_eur"),
                 "requested_date": None, **self.prov(r["p"])}
                for r in self.rd(f"MATCH (o:Order)-[:CONTAINS_LINE]->(l:OrderLine)-[:REFERENCES_PART]->(p:Part) WHERE {NOT_APP.format(v='o')} AND {NOT_APP.format(v='l')} AND {NOT_NET.format(v='o')} "
                                 "RETURN properties(l) AS p, o.order_id AS order, p.part_id AS part")]

    def inventory(self):
        return [{"inventory_id": self.strip(r["x"]["rel_id"], "AVAILABLE_AT"), "part_id": r["part"], "location_id": r["loc"], "quantity": r["x"].get("on_hand"),
                 "available_quantity": r["x"].get("available"), "reserved_quantity": r["x"].get("reserved"), "status": r["x"].get("stock_status"),
                 "last_updated": r["x"].get("last_updated"), **self.prov(r["x"])}
                for r in self.rd("MATCH (p:Part)-[x:AVAILABLE_AT]->(w:Warehouse) RETURN properties(x) AS x, p.part_id AS part, w.warehouse_id AS loc")]

    def pricing(self):
        return [{"price_id": r["p"]["price_id"], "part_id": r["part"], "dealer_id": None, "region": None, "currency": r["p"].get("currency"), "unit_price": r["p"].get("list_price_ex_vat"),
                 "valid_from": r["p"].get("valid_from"), "valid_to": r["p"].get("valid_to"), "status": r["p"].get("price_status"), **self.prov(r["p"])}
                for r in self.rd("MATCH (x:Price)-[:PRICES_PART]->(p:Part) RETURN properties(x) AS p, p.part_id AS part")]

    # ── logistics ────────────────────────────────────────────────────────────────────────────────
    def routes(self):
        return [{"route_id": r["p"]["route_id"], "origin_location_id": r["p"].get("origin_depot_id"), "destination_location_id": r["p"].get("destination_shipto_id"),
                 "transport_mode": r["p"].get("transport_mode"), "planned_transit_days": r["p"].get("total_estimated_days"), "estimated_cost": r["cost"], "currency": r["cur"],
                 "service_level": r["p"].get("service_level"), "status": r["p"].get("route_status"), **self.prov(r["p"])}
                for r in self.rd("MATCH (r:TransportRoute) WHERE " + NOT_NET.format(v="r") + " OPTIONAL MATCH (r)-[:PRICED_BY]->(f:FreightRate) RETURN properties(r) AS p, f.total_transport_cost AS cost, f.currency AS cur")]

    def route_legs(self):
        return [{"route_leg_id": self.strip(r["x"]["rel_id"], "HAS_LEG"), "route_id": r["route"], "leg_id": r["leg"]["leg_id"], "sequence": r["x"].get("sequence"),
                 "origin_location_id": r["leg"].get("from_id"), "destination_location_id": r["leg"].get("to_id"), "transport_mode": r["leg"].get("mode"), "planned_transit_days": None,
                 "estimated_cost": None, "status": r["leg"].get("leg_status"), "distance_km": r["leg"].get("distance_km"), **self.prov(r["x"])}
                for r in self.rd("MATCH (r:TransportRoute)-[x:HAS_LEG]->(l:TransportLeg) WHERE " + NOT_NET.format(v="r") + " RETURN properties(x) AS x, properties(l) AS leg, r.route_id AS route")]

    def shipments(self):
        out = []
        rows = self.rd(f"""MATCH (s:Shipment) WHERE {NOT_APP.format(v='s')} AND {NOT_NET.format(v='s')}
            OPTIONAL MATCH (s)-[:CARRIED_BY]->(c:Carrier) OPTIONAL MATCH (s)-[:DISPATCHED_FROM]->(w:Warehouse)
            OPTIONAL MATCH (s)-[:SHIPS_LINE]->(:OrderLine)<-[:CONTAINS_LINE]-(o:Order)
            OPTIONAL MATCH (s)-[:SHIPS_LINE]->(ol:OrderLine)
            OPTIONAL MATCH (s)-[:DELIVERS_TO_CUSTOMER]->(cu:Customer)-[:HAS_SHIP_TO]->(st:ShipTo)
            OPTIONAL MATCH (rt:TransportRoute)-[:FROM_DEPOT]->(w) WHERE (rt)-[:TO_SHIP_TO]->(st)
            RETURN properties(s) AS p, c.name AS carrier, c.carrier_id AS carrier_id, w.warehouse_id AS depot, collect(DISTINCT o.order_id) AS orders, collect(DISTINCT ol.order_line_id) AS lines,
              collect(DISTINCT rt.route_id) AS routes, collect(DISTINCT st.shipto_id) AS shiptos,
              [(s)-[:HAS_TRACKING_EVENT]->(e:TrackingEvent) | [e.event_seq, e.event_date, e.event_status]] AS events ORDER BY p.shipment_id""")
        for r in rows:
            p, ev = r["p"], sorted(r["events"])
            flags = []
            route = r["routes"][0] if len(r["routes"]) == 1 else None  # a route is linked only when exactly one exists between the dispatch depot and the customer's ship-tos
            if route is None:
                flags.append("ROUTE_NOT_DETERMINABLE")
            dest = r["shiptos"][0] if route and len(r["shiptos"]) == 1 else None
            if dest is None:
                flags.append("DESTINATION_LOCATION_NOT_DETERMINABLE")
            first = next((d for _, d, st in ev if st == "PICKED"), ev[0][1] if ev else None)
            delivered = next((d for _, d, st in ev if st == "DELIVERED"), None)
            out.append({"shipment_id": p["shipment_id"], "order_id": r["orders"][0] if len(r["orders"]) == 1 else None, "carrier": r["carrier"], "route_id": route,
                        "origin_location_id": r["depot"], "destination_location_id": dest, "transport_mode": None, "status": p.get("shipment_status"), "departure_date": first,
                        "planned_eta": None, "actual_eta": delivered, "tracking_ref": p.get("tracking_ref"), "remediation_flags": flags,
                        "route_resolution_status": "LINKED" if route else "ROUTE_NOT_DETERMINABLE", "carrier_id": r["carrier_id"],
                        "order_line_id": r["lines"][0] if len(r["lines"]) == 1 else None, **self.prov(p)})
        return out

    def tracking_events(self):
        return [{"tracking_event_id": r["p"]["tracking_event_id"], "shipment_id": r["ship"], "timestamp": r["p"].get("event_date"), "location_id": None,
                 "location_text": r["p"].get("event_location"), "status": r["p"].get("event_status"), "event_type": r["p"].get("event_status"), "description": None,
                 "sequence": r["p"].get("event_seq"), **self.prov(r["p"])}
                for r in self.rd(f"MATCH (s:Shipment)-[:HAS_TRACKING_EVENT]->(e:TrackingEvent) WHERE {NOT_APP.format(v='s')} AND {NOT_APP.format(v='e')} AND {NOT_NET.format(v='s')} "
                                 "RETURN properties(e) AS p, s.shipment_id AS ship")]

    # ── lifecycle (the part of it that already exists in the graph) ──────────────────────────────
    def warranty_policies(self):
        w = self.vocab["warranty"]
        out = []
        for r in self.rd("MATCH (c:PartCatalogProfile)-[:PROFILES_PART]->(p:Part) RETURN c.warranty_months AS months, p.part_id AS part ORDER BY part"):
            if r["months"] is None:
                continue
            out.append({"warranty_policy_id": f"WP-{r['part']}", "part_id": r["part"], "coverage_type": w["coverage_type"], "coverage_period_days": round(r["months"] * 365 / 12),
                        "coverage_conditions": w["coverage_conditions"], "start_rule": w["start_rule"], "region": None, "status": "ACTIVE", "data_status": "SYNTHETIC_DEMO",
                        "source_type": "SYNTHETIC_DEMO", "source_record_id": f"warranty_months={r['months']}"})
        return out


EXPORTS = ["plants", "locations", "categories", "machines", "suppliers", "dealers", "parts", "specifications", "fitment", "approved_sources", "assemblies",
           "legacy_part_mappings", "customers", "orders", "order_lines", "inventory", "pricing", "routes", "route_legs", "shipments", "tracking_events", "warranty_policies"]


def export_dataset(ex: Exporter, spec: DatasetSpec, root: Path, generated_at: str) -> tuple[int, list[Any]]:
    """Read, validate against the canonical model, normalise and write one dataset file. Returns (records, validated records)."""
    rows = getattr(ex, spec.name)()
    recs = []
    for row in rows:
        recs.append(normalise(spec, spec.model.model_validate(row)))  # an invalid export is a bug in the mapping: fail loudly
    dump_rows(spec, [r.model_dump(exclude={"ingestion_timestamp"}) for r in recs], root, generated_at)
    return len(recs), recs


def export_all(root: Path = CANON_DIR, generated_at: str = "", names: list[str] | None = None) -> dict[str, int]:
    ex = Exporter()
    counts: dict[str, int] = {}
    try:
        for name in (names or EXPORTS):
            counts[name], _ = export_dataset(ex, BY_NAME[name], root, generated_at)
    finally:
        ex.close()
    return counts
