"""Expands reference/network_definition.json into the Phase 2 canonical datasets, checking the network is coherent before anything is written.

The definition is the single authored source. This module adds nothing of its own: no durations, costs or mode rules. It derives only what is arithmetic
(a route's days and cost are the sums of its legs, a shipment's planned ETA is its departure plus its route's days) and refuses to write an incoherent network.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

from app.canonical.io import CANON_DIR, dump_rows, load_rows
from app.canonical.registry import BY_NAME
from app.logistics.rules import sequence_errors

SOURCE = {"data_status": "SYNTHETIC_DEMO", "source_type": "SYNTHETIC_DEMO"}


class NetworkError(Exception):
    pass


def _prov(defn: dict[str, Any], rid: str) -> dict[str, Any]:
    return {**SOURCE, "source_record_id": f"network_definition:{rid}", "effective_from": defn["effective_from"]}


def _where(geo: dict[str, Any], cc: str, city: str | None = None) -> dict[str, Any]:
    c = geo["countries"].get(cc)
    if not c:
        raise NetworkError(f"country {cc!r} is not in the geography reference")
    tz = geo.get("timezone_overrides", {}).get(f"{cc}:{city}", c["timezone"])
    return {"country": c["name"], "region": c["region"], "timezone": tz}


def build(root: Path = CANON_DIR) -> dict[str, list[dict[str, Any]]]:
    defn = json.loads((root / "reference" / "network_definition.json").read_text(encoding="utf-8"))
    geo = json.loads((root / "reference" / "geography.json").read_text(encoding="utf-8"))
    out: dict[str, list[dict[str, Any]]] = {}

    out["network_suppliers"] = [{**s, **_prov(defn, s["supplier_id"])} for s in defn["suppliers"]]
    dealers = []
    for d in defn["dealers"]:
        dealers.append({**{k: d[k] for k in ("dealer_id", "name", "city", "country_code", "dealer_type", "status", "latitude", "longitude", "authorized_status", "service_capable", "warranty_capable")},
                        "location_id": d["dealer_id"], **{k: v for k, v in _where(geo, d["country_code"], d["city"]).items() if k != "timezone"}, **_prov(defn, d["dealer_id"])})
    out["network_dealers"] = dealers

    locations: list[dict[str, Any]] = []
    for loc in defn["locations"]:
        kind = {"SUPPLIER": "SUPPLIER"}.get(loc["location_type"], "TERMINAL")
        locations.append({"location_id": loc["location_id"], "name": loc["name"], "location_kind": kind, "graph_label": loc["graph_label"], "country_code": loc["country_code"],
                          "city": loc["city"], "latitude": loc["latitude"], "longitude": loc["longitude"], "geo_basis": "SYNTHETIC_DEMO_PLACEMENT", "location_type": loc["location_type"],
                          "terminal_type": loc.get("terminal_type"), "modes": loc.get("modes", []), **_where(geo, loc["country_code"], loc["city"]), **_prov(defn, loc["location_id"])})
    for d in dealers:
        locations.append({"location_id": d["dealer_id"], "name": d["name"], "location_kind": "DEALER", "graph_label": "Dealer", "country_code": d["country_code"], "city": d["city"],
                          "latitude": d["latitude"], "longitude": d["longitude"], "geo_basis": "SYNTHETIC_DEMO_PLACEMENT", "location_type": "DEALER", "country": d["country"],
                          "region": d["region"], "timezone": _where(geo, d["country_code"], d["city"])["timezone"], **_prov(defn, d["dealer_id"])})
    out["network_locations"] = locations

    routes: list[dict[str, Any]] = []
    legs: list[dict[str, Any]] = []
    by_route: dict[str, dict[str, Any]] = {}
    for lane in defn["lanes"]:
        for r in lane["routes"]:
            rid = f"RTE-NET-{lane['lane_id']}-{r['suffix']}"
            if rid in by_route:
                raise NetworkError(f"duplicate route id {rid}")
            chain = r["legs"]
            if chain[0]["from"] != lane["origin_location_id"] or chain[-1]["to"] != lane["destination_location_id"]:
                raise NetworkError(f"{rid}: legs do not run from the lane origin to the lane destination")
            for a, b in pairwise(chain):
                if a["to"] != b["from"]:
                    raise NetworkError(f"{rid}: leg ends at {a['to']} but the next starts at {b['from']}")
            days, cost = sum(c["days"] for c in chain), round(sum(c["cost"] for c in chain), 2)
            if days < 1 or cost <= 0 or any(c["days"] < 0 or c["cost"] < 0 for c in chain):
                raise NetworkError(f"{rid}: transit days and costs must be positive")
            route = {"route_id": rid, "origin_location_id": lane["origin_location_id"], "destination_location_id": lane["destination_location_id"], "transport_mode": r["transport_mode"],
                     "planned_transit_days": days, "estimated_cost": cost, "currency": defn["cost_currency"], "service_level": r["service_level"], "status": "ACTIVE_DEMO", **_prov(defn, rid)}
            routes.append(route)
            by_route[rid] = route
            for seq, c in enumerate(chain, 1):
                leg_id = f"LEG-{rid}-{seq}"
                legs.append({"route_leg_id": f"{rid}>{leg_id}", "route_id": rid, "leg_id": leg_id, "sequence": seq, "origin_location_id": c["from"], "destination_location_id": c["to"],
                             "transport_mode": c["mode"], "planned_transit_days": c["days"], "estimated_cost": float(c["cost"]), "status": "ACTIVE_DEMO", "distance_km": None, **_prov(defn, leg_id)})
    out["network_routes"], out["network_route_legs"] = routes, legs

    prices = {r["part_id"]: float(r["unit_price"]) for r in load_rows(BY_NAME["pricing"], root)[0] if r["unit_price"] not in ("", None)}
    orders, lines = [], []
    for o in defn["orders"]:
        orders.append({"order_id": o["order_id"], "customer_id": o["customer_id"], "dealer_id": o["dealer_id"], "order_date": o["order_date"], "status": o["status"], "priority": None,
                       "currency": o["currency"], "total_value": None, "channel": o["channel"], **_prov(defn, o["order_id"])})
        for ln in o["lines"]:
            lines.append({"order_line_id": ln["order_line_id"], "order_id": o["order_id"], "part_id": ln["part_id"], "quantity": ln["quantity"], "unit_price": prices.get(ln["part_id"]),
                          "requested_date": None, **_prov(defn, ln["order_line_id"])})
    out["network_orders"], out["network_order_lines"] = orders, lines

    shipments, events = [], []
    for s in defn["shipments"]:
        route = by_route.get(s["route_id"])
        if route is None:
            raise NetworkError(f"{s['shipment_id']}: unknown route {s['route_id']}")
        eta = (date.fromisoformat(s["departure_date"]) + timedelta(days=route["planned_transit_days"])).isoformat()
        delivered = next((e["timestamp"] for e in s["events"] if e["event_type"] == "DELIVERED"), None)
        shipments.append({"shipment_id": s["shipment_id"], "order_id": s["order_id"], "carrier": None, "route_id": s["route_id"], "origin_location_id": route["origin_location_id"],
                          "destination_location_id": route["destination_location_id"], "transport_mode": route["transport_mode"], "status": "DELIVERED" if delivered else "IN_TRANSIT",
                          "departure_date": s["departure_date"], "planned_eta": eta, "actual_eta": delivered[:10] if delivered else None, "tracking_ref": s["tracking_ref"], "remediation_flags": [], "route_resolution_status": "LINKED",
                          "order_line_id": s["order_line_id"], "carrier_id": s["carrier_id"], **_prov(defn, s["shipment_id"])})
        batch = []
        for e in s["events"]:
            batch.append({"tracking_event_id": f"TRK-{s['shipment_id'][4:]}-{e['n']:02d}", "shipment_id": s["shipment_id"], "timestamp": e["timestamp"], "location_id": e["location_id"],
                          "location_text": e["location_text"], "status": e["event_type"], "event_type": e["event_type"], "description": e["description"], "sequence": e["n"],
                          **_prov(defn, f"{s['shipment_id']}:{e['n']}")})
        problems = sequence_errors(batch)
        if problems:
            raise NetworkError(f"{s['shipment_id']}: {'; '.join(problems)}")
        events.extend(batch)
    out["network_shipments"], out["network_tracking_events"] = shipments, events
    return out


def generate(root: Path = CANON_DIR, generated_at: str = "") -> dict[str, int]:
    data = build(root)
    for name, rows in data.items():
        spec = BY_NAME[name]
        checked = [spec.model.model_validate(r).model_dump(exclude={"ingestion_timestamp"}) for r in rows]  # an invalid generated record is a bug: fail loudly
        dump_rows(spec, checked, root, generated_at)
    return {k: len(v) for k, v in data.items()}
