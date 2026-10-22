"""ROUTE_OPTIONS: "How could a part get to <place>?" answered from the recorded transport lanes, for a place no shipment goes to yet.

A shipment follows ONE route, assigned to it (logistics context). A lane is different: the routes the network records between two places, any of which COULD be assigned. This module
reads those lanes (sea, air, road ... with their own recorded days and cost) and says so: they are potential routes, not a promise, not a booking and not a delivery date for any order.
Nothing is estimated here and no mode has a built-in duration: every number is a route record's own. A place with no recorded lane is reported as not covered, never as unreachable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.commerce import contract as c
from app.commerce.engine import CommerceContextEngine

ROUTE_OPTIONS = "ROUTE_OPTIONS"
# plain-language names for the same place that are not the record's own spelling (language, not business data)
PLACE_ALIASES = {"usa": "united states", "u.s.a": "united states", "u.s": "united states", "america": "united states", "uk": "united kingdom", "britain": "united kingdom", "england": "united kingdom"}


@dataclass(kw_only=True)
class RouteOptionsContext(c.CommerceContext):
    lookup: str = ROUTE_OPTIONS
    destinations: list[dict[str, Any]] = field(default_factory=list)  # each: the place and its recorded lanes' routes
    matched: list[str] = field(default_factory=list)


def _words(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9. ]+", " ", (text or "").lower()) + " "


def _places(engine: CommerceContextEngine) -> dict[str, dict[str, Any]]:
    """The places recorded lanes lead to, with the terms that name them (city, country, region, name words)."""
    reader, out = engine.logistics, {}
    for route in reader.network_routes():
        dest = route["destination_location_id"]
        if dest in out:
            out[dest]["routes"].append(route)
            continue
        loc = reader.location(dest) or {}
        terms = {str(loc.get(k) or "").lower() for k in ("city", "country", "region")} - {""}
        out[dest] = {"location": loc, "terms": terms, "routes": [route]}
    return out


def find_destinations(engine: CommerceContextEngine, message: str) -> list[str]:
    """The ids of the places with a recorded lane that the message names (by city, country or region)."""
    text = _words(message)
    for short, full in PLACE_ALIASES.items():
        text = text.replace(f" {short} ", f" {full} ")
    return [dest for dest, p in _places(engine).items() if any(f" {t} " in text for t in p["terms"])]


def route_options(engine: CommerceContextEngine, destination_ids: list[str]) -> RouteOptionsContext:
    places = _places(engine)
    rows, records, evidence, path = [], [], [], []
    for dest in destination_ids:
        p = places.get(dest)
        if not p:
            continue
        loc = p["location"]
        routes = sorted(p["routes"], key=lambda r: (r.get("planned_transit_days") is None, r.get("planned_transit_days") or 0, r["route_id"]))
        options = []
        for r in routes:
            origin = engine.logistics.location(r["origin_location_id"]) or {}
            legs = engine.logistics.legs(r["route_id"])
            options.append({"route_id": r["route_id"], "transport_mode": r.get("transport_mode"), "service_level": r.get("service_level"), "planned_transit_days": r.get("planned_transit_days"),
                            "estimated_cost": r.get("estimated_cost"), "currency": r.get("currency"), "origin": {"location_id": r["origin_location_id"], "name": origin.get("name"), "country": origin.get("country")},
                            "legs": [{"sequence": g["sequence"], "transport_mode": g.get("transport_mode"), "planned_transit_days": g.get("planned_transit_days"), "origin_location_id": g["origin_location_id"],
                                      "destination_location_id": g["destination_location_id"]} for g in legs],
                            "data_status": r.get("data_status")})
            records.append(c.record("TransportRoute", r["route_id"], r))
            evidence.append(c.evidence_item(f"{r['route_id']} ({r.get('transport_mode')}) is a recorded route to {loc.get('city') or dest}: {r.get('planned_transit_days')} days", "TransportRoute", r["route_id"], r))
        rows.append({"location_id": dest, "name": loc.get("name"), "city": loc.get("city"), "country": loc.get("country"), "region": loc.get("region"), "routes": options})
        records.append(c.record("Location", dest, loc))
        path += [c.path_step(len(path) + 1, "Location", dest, "REACHED_BY_ROUTE", loc)]
    if not rows:
        d = c.CommerceDecision(status=c.NOT_FOUND, decision="NO_RECORDED_LANE", summary="No transport lane to that place is recorded, so no route can be named. That does not mean it cannot be reached.", missing=["route"])
    else:
        places_txt = "; ".join(f"{r['city'] or r['name']} ({r['country']}): " + ", ".join(f"{o['transport_mode'].replace('_', ' ').lower()} {o['planned_transit_days']} days" for o in r["routes"]) for r in rows)
        d = c.CommerceDecision(status=c.SUCCESS, decision=ROUTE_OPTIONS, summary=f"Recorded routes (potential, not assigned to any shipment): {places_txt}.",
                               facts={"destinations": [{"location_id": r["location_id"], "routes": [{k: o[k] for k in ("route_id", "transport_mode", "planned_transit_days", "estimated_cost", "currency")} for o in r["routes"]]} for r in rows]},
                               reasons=["read from the transport routes recorded for each place; no shipment is assigned to them"],
                               warnings=["potential routes only: days and cost are the route record's own (demonstration data), not a booking or a delivery date for an order"])
    meta = c.meta("LOGISTICS", {"destinations": destination_ids, "lookup": ROUTE_OPTIONS}, engine._today().isoformat(), engine._generated_at(), d, records, evidence, path)
    ctx = RouteOptionsContext(**meta, destinations=rows, matched=[r["location_id"] for r in rows])
    ctx.visibility = {"role": "ALL", "hidden_fields": []}
    return ctx
