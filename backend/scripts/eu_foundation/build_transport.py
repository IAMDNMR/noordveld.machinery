"""European transport network: carriers, options, terminals, distances, routes (with their legs) and freight rates.

Every non-road service is modelled as legs: road first mile -> terminal -> trunk -> terminal -> road final mile -> ship-to. Distances
are straight-line (haversine, derived) times a fixed circuity factor per mode (synthetic route distance, never a live routing result).
Rates, transit times and costs are synthetic. A route exists only where the terminals and corridor links to carry it exist.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from build_entities import Actor
from common import stable_int
from geo import (AIR_TERMINALS, CIRCUITY, CITY, COUNTRIES, CROSS_DOCKS, INLAND_PORTS, ISLANDS, RAIL_LINKS, RAIL_TERMINALS, SEA_LINKS, SEAPORTS, WATER_LINKS, haversine_km)
from model import Existing, Model, node_props
from names import slug

# (code, name, mode, service level, min km, max km, handling days, km per day on the main haul, rate multiplier, fuel surcharge, service model, main mode)
OPTIONS = [
    ("STANDARD_ROAD_EU", "Standard Road (EU)", "ROAD", "STANDARD", 0, 4500, 1, 700, 1.00, 0.08, "ROAD_ONLY", "ROAD"),
    ("PREMIUM_ROAD", "Premium Road", "ROAD", "PREMIUM", 0, 3000, 0, 850, 1.35, 0.08, "ROAD_ONLY", "ROAD"),
    ("EXPRESS_ROAD_EU", "Express Road (EU)", "ROAD", "EXPRESS", 0, 2000, 0, 1000, 1.80, 0.08, "ROAD_ONLY", "ROAD"),
    ("PALLET_FREIGHT_EU", "Pallet Freight (EU)", "ROAD", "PALLET", 0, 4500, 1, 600, 1.15, 0.08, "ROAD_ONLY", "ROAD"),
    ("RAIL_STANDARD", "Rail Standard", "RAIL", "STANDARD", 400, 4500, 2, 600, 0.90, 0.04, "RAIL_WITH_ROAD_FIRST_AND_FINAL_MILE", "RAIL"),
    ("RAIL_PRIORITY", "Rail Priority", "RAIL", "PRIORITY", 400, 4500, 1, 800, 1.25, 0.04, "RAIL_WITH_ROAD_FIRST_AND_FINAL_MILE", "RAIL"),
    ("INLAND_WATERWAY", "Inland Waterway", "INLAND_WATERWAY", "STANDARD", 250, 3000, 2, 280, 0.80, 0.05, "WATERWAY_WITH_ROAD_FIRST_AND_FINAL_MILE", "INLAND_WATERWAY"),
    ("SHORT_SEA", "Short Sea", "SHORT_SEA", "STANDARD", 300, 4500, 2, 650, 0.85, 0.07, "SEA_WITH_ROAD_FIRST_AND_FINAL_MILE", "SHORT_SEA"),
    ("AIR_STANDARD", "Air Standard", "AIR", "STANDARD", 500, 4500, 2, 6000, 4.50, 0.12, "AIR_WITH_ROAD_FIRST_AND_FINAL_MILE", "AIR"),
    ("AIR_EXPRESS", "Air Express", "AIR", "EXPRESS", 500, 4500, 1, 6000, 6.50, 0.12, "AIR_WITH_ROAD_FIRST_AND_FINAL_MILE", "AIR"),
    ("AIR_CRITICAL", "Air Critical", "AIR", "CRITICAL", 300, 4500, 0, 6000, 11.00, 0.12, "AIR_WITH_ROAD_FIRST_AND_FINAL_MILE", "AIR"),
    ("ROAD_RAIL_ROAD", "Road-Rail-Road", "MULTIMODAL", "STANDARD", 500, 4500, 2, 600, 0.95, 0.05, "MULTIMODAL_INTERMODAL_UNIT", "RAIL"),
    ("ROAD_WATER_ROAD", "Road-Water-Road", "MULTIMODAL", "STANDARD", 300, 3000, 2, 280, 0.85, 0.06, "MULTIMODAL_INTERMODAL_UNIT", "INLAND_WATERWAY"),
    ("ROAD_SEA_ROAD", "Road-Sea-Road", "MULTIMODAL", "STANDARD", 400, 4500, 2, 650, 0.90, 0.07, "MULTIMODAL_INTERMODAL_UNIT", "SHORT_SEA"),
]
HANDLING_FEE = {"RAIL": 14.0, "INLAND_WATERWAY": 14.0, "SHORT_SEA": 16.0, "AIR": 25.0}
FIRST_FINAL_KM_PER_DAY = 550
MAX_ACCESS_KM = {"RAIL": 350, "INLAND_WATERWAY": 250, "SHORT_SEA": 350, "AIR": 350}
BANDS = [("LOCAL", 0, 100, "SHR-01", 1.0), ("REGIONAL", 100, 250, "SHR-03", 1.0), ("NATIONAL", 250, 500, "SHR-05", 1.0),
         ("LONG_DISTANCE", 500, 1000, "SHR-07", 1.0), ("CONTINENTAL", 1000, 2000, "SHR-07", 1.6), ("TRANS_EUROPEAN", 2000, 5000, "SHR-07", 2.4)]
CARD_PRICE = {"SHR-01": 12.0, "SHR-03": 19.0, "SHR-05": 29.0, "SHR-07": 45.0}
DIST_TYPE = {"ROAD": "SYNTHETIC_ROAD_ESTIMATE", "RAIL": "SYNTHETIC_RAIL_ESTIMATE", "INLAND_WATERWAY": "SYNTHETIC_WATERWAY_ESTIMATE", "SHORT_SEA": "SYNTHETIC_SEA_ESTIMATE", "AIR": "SYNTHETIC_AIR_ESTIMATE"}
# (country, name, modes, serving region). Fictional operators; no real carrier, contract or price.
CARRIERS = [
    ("NL", "Maasland Freight", ["ROAD", "PALLET"], "NL|BE|DE|FR"), ("DE", "Nordtrans Spedition", ["ROAD", "PALLET"], "DE|NL|AT|CZ|PL|DK"), ("DE", "Rheinbogen Logistik", ["ROAD", "PREMIUM"], "DE|FR|BE|LU|AT"),
    ("BE", "Kempen Cargo", ["ROAD", "EXPRESS"], "BE|NL|FR|LU|DE"), ("FR", "Transports Valmont", ["ROAD", "PALLET"], "FR|BE|ES|IT|DE"), ("IT", "Autotrasporti Ligure", ["ROAD", "PALLET"], "IT|FR|AT|SI|HR"),
    ("PL", "Silesia Trans", ["ROAD", "PALLET"], "PL|DE|CZ|SK|LT|LV|EE"), ("ES", "Transportes Iberia Centro", ["ROAD", "PALLET"], "ES|PT|FR"), ("AT", "Alpenfracht Express", ["ROAD", "EXPRESS"], "AT|DE|IT|SI|HU|CZ|SK"),
    ("SE", "Svea Linjegods", ["ROAD", "PALLET"], "SE|DK|FI|DE"), ("RO", "Carpati Trans", ["ROAD", "PALLET"], "RO|BG|HU|GR"),
    ("DE", "Eurorail Intermodal Services", ["RAIL"], "DE|NL|FR|AT|PL|CZ|IT"), ("AT", "Rhine-Alpine Rail Cargo", ["RAIL"], "DE|AT|IT|NL|HU"), ("ES", "Iberia Rail Freight", ["RAIL"], "ES|FR|IT"),
    ("DE", "Rhein-Main Binnenschiff", ["INLAND_WATERWAY"], "DE|NL|BE|FR|AT"), ("AT", "Danube Barge Lines", ["INLAND_WATERWAY"], "DE|AT|HU|SK"), ("BE", "Scheldt Inland Shipping", ["INLAND_WATERWAY"], "BE|NL|FR"),
    ("NL", "North Sea Short Sea Lines", ["SHORT_SEA"], "NL|BE|DE|SE|DK|IE|FR"), ("PL", "Baltic Feeder Services", ["SHORT_SEA"], "PL|SE|DK|DE|FI|LT|LV|EE"), ("IT", "Mediterranean Ro-Ro Link", ["SHORT_SEA"], "IT|ES|GR|MT|CY|FR"),
    ("NL", "Continental Air Cargo Services", ["AIR"], "NL|BE|DE|FR|IT|ES|PL|AT|GR"), ("BE", "Euro Express Air Freight", ["AIR"], "EU27"), ("DE", "Critical Parts Air Courier", ["AIR"], "EU27"),
    ("NL", "TransEuropa Intermodal", ["MULTIMODAL"], "NL|DE|BE|FR|PL|CZ|AT|IT"), ("DE", "Corridor Combined Logistics", ["MULTIMODAL"], "DE|NL|AT|PL|CZ|HU|IT|FR"),
]
BRAND = {"ROAD": "ROAD", "PALLET": "ROAD", "PREMIUM": "ROAD", "EXPRESS": "ROAD"}


@dataclass
class Terminal:
    id: str
    kind: str
    cc: str
    city: str
    lat: float
    lon: float
    modes: list[str]


def build_options_and_carriers(m: Model, ex: Existing) -> dict[str, str]:
    option_ids: dict[str, str] = {}
    for n, (code, name, mode, level, mn, mx, hd, kpd, mult, fuel, model, main) in enumerate(OPTIONS, start=9):
        oid = f"TOP-{n:03d}"
        option_ids[code] = oid
        m.node("TransportOption", oid, node_props("eu_transport_options", oid, {
            "name": name, "option_code": code, "transport_mode": mode, "service_level": level, "service_model": model, "main_haul_mode": main, "option_status": "ACTIVE_DEMO",
            "countries_served": "EU27", "min_distance_km": mn, "max_distance_km": mx, "handling_days": hd, "applicability": f"Route-specific: offered only where a route exists ({mn}-{mx} km)",
            "shipment_class_supported": "DEMO_SHIPMENT_CLASS", "estimated_delivery": "Estimated, not a guaranteed delivery date"}))
    cseq = 5
    for cc, name, modes, region in CARRIERS:
        cseq += 1
        cid = f"CAR-DEMO-{cseq:03d}"
        m.node("Carrier", cid, node_props("eu_carriers", cid, {
            "name": f"{name} (demo)", "provider_code": slug(name)[:3].upper() + str(cseq), "transport_modes": "|".join(modes), "region": region, "country_code": cc, "service_status": "ACTIVE_DEMO",
            "provider_note": "Fictional demo provider. Not a real carrier and not connected to any carrier system."}))
        wanted = {"ROAD": ["ROAD", "PREMIUM", "EXPRESS", "PALLET"], "RAIL": ["RAIL"], "INLAND_WATERWAY": ["INLAND_WATERWAY"], "SHORT_SEA": ["SHORT_SEA"], "AIR": ["AIR"], "MULTIMODAL": ["MULTIMODAL"]}
        for code, _n, mode, level, *_ in OPTIONS:
            fits = (mode == "ROAD" and "ROAD" in modes and (level in modes or level == "STANDARD")) or (mode != "ROAD" and mode in modes)
            if fits:
                m.rel("OFFERS", ("Carrier", cid), ("TransportOption", option_ids[code]), "eu_carriers")
    return option_ids


def build_terminals(m: Model, geo) -> tuple[list[Terminal], dict[str, dict[tuple[str, str], str]], dict[str, dict[str, list[tuple[str, float, str]]]]]:
    terminals: list[Terminal] = []
    by_key: dict[str, dict[tuple[str, str], str]] = {"SHORT_SEA": {}, "INLAND_WATERWAY": {}, "RAIL": {}, "AIR": {}, "XDOCK": {}}
    water_cities = {("NL", "Rotterdam"), ("BE", "Antwerpen")}
    specs = [("SEA", "Seaport", "SeaPort", SEAPORTS), ("INL", "Inland Port", "InlandPort", INLAND_PORTS), ("RAL", "Rail Terminal", "RailTerminal", RAIL_TERMINALS),
             ("AIR", "Air Cargo Terminal", "AirportCargoTerminal", AIR_TERMINALS), ("XDK", "Cross-Dock", "CrossDock", CROSS_DOCKS)]
    for code, label, extra, rows in specs:
        for cc, city in rows:
            region, lat, lon = CITY[(cc, city)]
            tid = f"TRM-{code}-{cc}-{slug(city).upper()}"
            modes = {"SEA": ["SHORT_SEA"] + (["INLAND_WATERWAY"] if (cc, city) in water_cities else []), "INL": ["INLAND_WATERWAY"], "RAL": ["RAIL"], "AIR": ["AIR"], "XDK": ["ROAD"]}[code]
            m.node("TransportTerminal", tid, node_props("eu_terminals", tid, {
                "name": f"{city} {label} (demo)", "terminal_code": tid[4:], "terminal_type": extra.upper(), "country_code": cc, "city": city, "latitude": lat, "longitude": lon,
                "geo_basis": "APPROX_CITY_CENTRE", "modes": modes, "terminal_status": "ACTIVE_DEMO"}), extra=(extra,))
            geo.place(("TransportTerminal", tid), cc, city)
            terminals.append(Terminal(tid, code, cc, city, lat, lon, modes))
            for md in modes:
                if code != "XDK":
                    by_key[md][(cc, city)] = tid
            if code == "XDK":
                by_key["XDOCK"][(cc, city)] = tid
    term = {t.id: t for t in terminals}
    graph: dict[str, dict[str, list[tuple[str, float, str]]]] = {"RAIL": defaultdict(list), "INLAND_WATERWAY": defaultdict(list), "SHORT_SEA": defaultdict(list), "AIR": defaultdict(list)}

    def link(mode: str, a: str, b: str, corridor: str | None) -> None:
        ta, tb = term[a], term[b]
        straight = haversine_km(ta.lat, ta.lon, tb.lat, tb.lon)
        km = round(straight * CIRCUITY[mode], 1)
        graph[mode][a].append((b, km, corridor or ""))
        graph[mode][b].append((a, km, corridor or ""))
        m.rel("DISTANCE_TO", ("TransportTerminal", a), ("TransportTerminal", b), "eu_terminal_links", {
            "distance_km": km, "straight_line_km": round(straight, 1), "distance_type": DIST_TYPE[mode], "mode": mode, "route_context": "TERMINAL_TRUNK_LINK", "corridor": corridor,
            "distance_basis": f"straight line between approximate city centres x {CIRCUITY[mode]}"}, f":{mode}")

    def at(mode: str, key: str) -> str:
        cc, city = key.split(":")
        return by_key[mode][(cc, city)]

    for mode, links in (("RAIL", RAIL_LINKS), ("INLAND_WATERWAY", WATER_LINKS), ("SHORT_SEA", SEA_LINKS)):
        for a, b, corridor in links:
            link(mode, at(mode, a), at(mode, b), corridor)
    air = [t.id for t in terminals if t.kind == "AIR"]
    for i, a in enumerate(air):
        for b in air[i + 1:]:
            link("AIR", a, b, None)
    return terminals, by_key, graph


def all_pairs(graph: dict[str, list[tuple[str, float, str]]]) -> tuple[dict, dict]:
    nodes = list(graph)
    dist = {a: {b: math.inf for b in nodes} for a in nodes}
    nxt: dict[str, dict[str, str | None]] = {a: {b: None for b in nodes} for a in nodes}
    for a in nodes:
        dist[a][a] = 0.0
        for b, km, _ in graph[a]:
            if km < dist[a][b]:
                dist[a][b], nxt[a][b] = km, b
    for k in nodes:
        for i in nodes:
            for j in nodes:
                if dist[i][k] + dist[k][j] < dist[i][j]:
                    dist[i][j], nxt[i][j] = dist[i][k] + dist[k][j], nxt[i][k]
    return dist, nxt


def path(nxt: dict, a: str, b: str) -> list[str]:
    out = [a]
    while a != b:
        a = nxt[a][b]
        out.append(a)
    return out


def band_of(km: float) -> tuple[str, int, int, str, float]:
    for b in BANDS:
        if km < b[2]:
            return b
    return BANDS[-1]


@dataclass
class Place:
    id: str
    label: str
    cc: str
    lat: float
    lon: float


MAX_DETOUR = 1.5


def build_routes(m: Model, ex: Existing, depots: list[Actor], shiptos: list[Place], terminals: list[Terminal], by_key, graph, option_ids: dict[str, str],
                 existing_dist: dict[tuple[str, str], float]) -> dict[str, Any]:
    term = {t.id: t for t in terminals}
    apsp = {mode: all_pairs(g) for mode, g in graph.items()}
    options = {code: (oid, mode, level, mn, mx, hd, kpd, mult, fuel, model, main) for (code, _n, mode, level, mn, mx, hd, kpd, mult, fuel, model, main), oid in zip(OPTIONS, option_ids.values())}
    depot_by = {d.id: d for d in depots}
    legs: dict[str, dict[str, Any]] = {}
    dist_rels: dict[str, dict[str, Any]] = {}
    routes: dict[str, dict[str, Any]] = {}

    def road_km(straight: float) -> float:
        return round(straight * CIRCUITY["ROAD"], 1)

    def leg(mode: str, a: tuple[str, str], b: tuple[str, str], km: float, straight: float) -> str:
        lid = f"LEG-{mode}-{a[1]}-{b[1]}"
        if lid not in legs:
            legs[lid] = {"mode": mode, "a": a, "b": b, "km": km, "straight": straight}
        return lid

    def distance_rel(a: tuple[str, str], b: tuple[str, str], km: float, straight: float, context: str, suffix: str = "") -> None:
        rid = f"DISTANCE_TO:{a[1]}>{b[1]}{suffix}"
        if rid in dist_rels or (a[0] == "Warehouse" and b[0] == "ShipTo" and (a[1], b[1]) in existing_dist):
            return
        dist_rels[rid] = {"a": a, "b": b, "km": km, "straight": straight, "context": context, "suffix": suffix}

    # depot -> terminal (road first mile) for every terminal of every mode within reach
    depot_terms: dict[tuple[str, str], list[tuple[float, str]]] = {}
    for mode in ("RAIL", "INLAND_WATERWAY", "SHORT_SEA", "AIR"):
        for d in depots:
            found = []
            for key, tid in by_key[mode].items():
                t = term[tid]
                s = haversine_km(d.lat, d.lon, t.lat, t.lon)
                if road_km(s) <= MAX_ACCESS_KM[mode]:
                    found.append((road_km(s), tid))
                    distance_rel(("Warehouse", d.id), ("TransportTerminal", tid), road_km(s), round(s, 1), "DEPOT_TO_TERMINAL_FIRST_MILE")
            depot_terms[(mode, d.id)] = sorted(found)

    for s in shiptos:
        cands = sorted(depots, key=lambda d: haversine_km(d.lat, d.lon, s.lat, s.lon))
        # Noordveld's two principal depots (Assen NL, Lingen DE) hold the full catalogue and ship Europe-wide, so they are candidates for every ship-to within 1,800 km
        principal = [depot_by[i] for i in ("WH-001", "WH-002") if i in depot_by and haversine_km(depot_by[i].lat, depot_by[i].lon, s.lat, s.lon) <= 1800]
        chosen = cands[:2] + [d for d in cands if d.cc == s.cc][:1] + principal
        chosen = list(dict.fromkeys(d.id for d in chosen))
        # the nearest two depots (plus the nearest in the same country); further depots are tried only if none of those can reach this ship-to
        order = chosen + [d.id for d in cands if d.id not in chosen]
        before = len(routes)
        for did in order:
            if did not in chosen and len(routes) > before:
                break
            d = depot_by[did]
            straight = haversine_km(d.lat, d.lon, s.lat, s.lon)
            direct = existing_dist.get((did, s.id)) or road_km(straight)
            scope = "DOMESTIC" if d.cc == s.cc else ("ISLAND_CROSS_BORDER" if s.cc in ISLANDS else "CROSS_BORDER")
            candidates: list[tuple[str, list[str], float]] = []  # (option code, ordered leg ids, total km)
            if s.cc not in ISLANDS:
                road_legs = [leg("ROAD", ("Warehouse", did), ("ShipTo", s.id), direct, round(straight, 1))]
                distance_rel(("Warehouse", did), ("ShipTo", s.id), direct, round(straight, 1), "DEPOT_TO_SHIP_TO")
                for code in ("STANDARD_ROAD_EU", "PREMIUM_ROAD", "EXPRESS_ROAD_EU", "PALLET_FREIGHT_EU"):
                    legs_for = road_legs
                    total = direct
                    if direct > 1200 and code in ("PREMIUM_ROAD", "EXPRESS_ROAD_EU"):  # long road haul relays through a cross-dock when the detour is small
                        best = None
                        for (cc, city), xid in by_key["XDOCK"].items():
                            t = term[xid]
                            s1, s2 = haversine_km(d.lat, d.lon, t.lat, t.lon), haversine_km(t.lat, t.lon, s.lat, s.lon)
                            if road_km(s1) + road_km(s2) <= direct * 1.10 and (best is None or road_km(s1) + road_km(s2) < best[0]):
                                best = (road_km(s1) + road_km(s2), xid, s1, s2)
                        if best:
                            xid = best[1]
                            t = term[xid]
                            legs_for = [leg("ROAD", ("Warehouse", did), ("TransportTerminal", xid), road_km(best[2]), round(best[2], 1)),
                                        leg("ROAD", ("TransportTerminal", xid), ("ShipTo", s.id), road_km(best[3]), round(best[3], 1))]
                            total = best[0]
                            distance_rel(("Warehouse", did), ("TransportTerminal", xid), road_km(best[2]), round(best[2], 1), "DEPOT_TO_CROSS_DOCK")
                            distance_rel(("TransportTerminal", xid), ("ShipTo", s.id), road_km(best[3]), round(best[3], 1), "CROSS_DOCK_TO_SHIP_TO")
                    candidates.append((code, legs_for, total))
            for mode, option_codes in (("RAIL", ["RAIL_STANDARD", "RAIL_PRIORITY", "ROAD_RAIL_ROAD"]), ("INLAND_WATERWAY", ["INLAND_WATERWAY", "ROAD_WATER_ROAD"]),
                                       ("SHORT_SEA", ["SHORT_SEA", "ROAD_SEA_ROAD"]), ("AIR", ["AIR_STANDARD", "AIR_EXPRESS", "AIR_CRITICAL"])):
                dist, nxt = apsp[mode]
                best = None
                finals = []
                for key, tid in by_key[mode].items():
                    t = term[tid]
                    fs = haversine_km(t.lat, t.lon, s.lat, s.lon)
                    if road_km(fs) <= MAX_ACCESS_KM[mode]:
                        finals.append((road_km(fs), round(fs, 1), tid))
                for first_km, o in depot_terms[(mode, did)]:
                    for final_km, fs, f in finals:
                        if o == f or dist[o][f] == math.inf:
                            continue
                        total = first_km + dist[o][f] + final_km
                        if best is None or total < best[0]:
                            best = (total, o, f, first_km, final_km, fs)
                if not best:
                    continue
                total, o, f, first_km, final_km, fs = best
                if mode == "AIR" and straight < 300:
                    continue
                ids = path(nxt, o, f)
                chain = [leg("ROAD", ("Warehouse", did), ("TransportTerminal", o), first_km, round(first_km / CIRCUITY["ROAD"], 1))]
                for a_, b_ in zip(ids, ids[1:]):
                    km = next(k for n_, k, _c in graph[mode][a_] if n_ == b_)
                    chain.append(leg(mode, ("TransportTerminal", a_), ("TransportTerminal", b_), km, round(km / CIRCUITY[mode], 1)))
                chain.append(leg("ROAD", ("TransportTerminal", f), ("ShipTo", s.id), final_km, fs))
                distance_rel(("TransportTerminal", f), ("ShipTo", s.id), final_km, fs, "TERMINAL_TO_SHIP_TO_FINAL_MILE")
                trunk = sum(km for _, km, *_ in [(0, legs[x]["km"]) for x in chain[1:-1]])
                for code in option_codes:
                    _oid, _mode, _lvl, mn, mx, *_rest = options[code]
                    if mode == "INLAND_WATERWAY" and (first_km > 250 or final_km > 250 or trunk < 100):
                        continue
                    if mode == "SHORT_SEA" and not (s.cc in ISLANDS or trunk >= 300):
                        continue
                    if mode == "RAIL" and trunk < 200:
                        continue
                    candidates.append((code, chain, total))
            for code, chain, total in candidates:
                oid, omode, level, mn, mx, hd, kpd, mult, fuel, model, main = options[code]
                if total < mn or total > mx:
                    continue
                if s.cc in ISLANDS and omode == "ROAD":
                    continue
                if omode != "ROAD" and s.cc not in ISLANDS and total > direct * MAX_DETOUR:  # a rail/water/sea/air option must not be an absurd detour versus the direct road route
                    continue
                nonroad = [x for x in chain if legs[x]["mode"] != "ROAD"]
                road_first_final = sum(legs[x]["km"] for x in chain if legs[x]["mode"] == "ROAD")
                trunk_km = sum(legs[x]["km"] for x in nonroad)
                transfers = 0 if not nonroad else 2
                days = (road_first_final / (kpd if not nonroad else FIRST_FINAL_KM_PER_DAY)) + (trunk_km / kpd if nonroad else 0) + transfers * (0.25 if main == "AIR" else 0.5)
                transit_days = max(1, math.ceil(days))
                band = band_of(total)
                rid = f"RTE-{did}-{s.id}-{oid}"
                routes[rid] = {"depot": did, "shipto": s.id, "option": code, "option_id": oid, "mode": omode, "level": level, "model": model, "legs": chain, "km": round(total, 1),
                               "transit": transit_days, "handling": hd, "total_days": transit_days + hd, "band": band[0], "scope": scope, "transfers": transfers, "main": main,
                               "dest_cc": s.cc}
    return {"legs": legs, "distances": dist_rels, "routes": routes}


def emit_routes(m: Model, result: dict[str, Any], option_ids: dict[str, str], existing_dist: dict[tuple[str, str], float]) -> dict[str, Any]:
    routes = result["routes"]
    used = {lid for r in routes.values() for lid in r["legs"]}
    legs = {lid: l for lid, l in result["legs"].items() if lid in used}  # candidate legs no route ended up using are not emitted
    for lid, l in legs.items():
        m.node("TransportLeg", lid, node_props("eu_route_legs", lid, {
            "mode": l["mode"], "distance_km": l["km"], "straight_line_km": l["straight"], "distance_type": DIST_TYPE[l["mode"]], "from_id": l["a"][1], "to_id": l["b"][1],
            "from_kind": l["a"][0], "to_kind": l["b"][0], "leg_status": "ACTIVE_DEMO"}))
        m.rel("LEG_FROM", ("TransportLeg", lid), l["a"], "eu_route_legs")
        m.rel("LEG_TO", ("TransportLeg", lid), l["b"], "eu_route_legs")
    for rid, d in result["distances"].items():
        if (d["a"][0], d["b"][0]) == ("Warehouse", "ShipTo"):
            kind = "SYNTHETIC_ROAD_ESTIMATE"
        else:
            kind = DIST_TYPE["ROAD"]
        m.rel("DISTANCE_TO", d["a"], d["b"], "eu_distances", {
            "distance_km": d["km"], "straight_line_km": d["straight"], "distance_type": kind, "mode": "ROAD", "route_context": d["context"],
            "distance_basis": f"straight line between approximate city centres x {CIRCUITY['ROAD']}"}, d["suffix"])
    # rates: one per (depot, option, band, scope); transit_days is the slowest route in the group so every route is within its rate
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in routes.values():
        groups[(r["depot"], r["option_id"], r["band"], r["scope"])].append(r)
    opt = {oid: next(o for o in OPTIONS if option_ids[o[0]] == oid) for oid in option_ids.values()}
    rate_ids: dict[tuple[str, str, str, str], str] = {}
    for (depot, oid, band, scope), rs in sorted(groups.items()):
        code, _n, mode, level, mn, mx, hd, kpd, mult, fuel, model, main = opt[oid]
        bname, lo, hi, card, bmult = next(b for b in BANDS if b[0] == band)
        base = round(CARD_PRICE[card] * bmult * mult, 2)
        fuel_cost = round(base * fuel, 2)
        cross = 12.0 if scope != "DOMESTIC" else 0.0
        island = 18.0 if scope == "ISLAND_CROSS_BORDER" else 0.0
        additional = round(fuel_cost + cross + island, 2)
        transfers = max(r["transfers"] for r in rs)
        handling = round(HANDLING_FEE.get(main, 0.0) * transfers, 2) if transfers else 0.0
        suffix = {"DOMESTIC": "DOM", "CROSS_BORDER": "CRO", "ISLAND_CROSS_BORDER": "ISL"}[scope]
        frid = f"FRT-{depot}-{oid}-{band}-{suffix}"
        rate_ids[(depot, oid, band, scope)] = frid
        parts = [f"fuel surcharge {int(fuel * 100)}% = {fuel_cost:.2f}"] + ([f"cross-border fee = {cross:.2f}"] if cross else []) + ([f"island surcharge = {island:.2f}"] if island else [])
        m.node("FreightRate", frid, node_props("eu_freight_rates", frid, {
            "currency": "EUR", "distance_band": band, "from_km": lo, "to_km": hi, "destination_scope": scope, "base_cost": base, "additional_cost": additional,
            "additional_cost_breakdown": "; ".join(parts), "total_transport_cost": round(base + additional, 2), "handling_cost": handling, "total_cost_incl_handling": round(base + additional + handling, 2),
            "transit_days": max(r["total_days"] for r in rs), "valid_from": "2026-01-01", "valid_to": "2026-12-31", "rate_status": "ACTIVE_DEMO", "shipment_class": "DEMO_SHIPMENT_CLASS",
            "rate_basis": f"standard rate card {card} x band factor {bmult} x option factor {mult}", "cost_note": "Synthetic demo rate. Not a real freight rate."}))
        m.rel("HAS_RATE", ("TransportOption", oid), ("FreightRate", frid), "eu_freight_rates")
        m.rel("APPLIES_FROM", ("FreightRate", frid), ("Warehouse", depot), "eu_freight_rates")
        m.rel("BASED_ON_RATE_CARD", ("FreightRate", frid), ("ShippingRate", card), "eu_freight_rates")
    served: set[tuple[str, str]] = set()
    for rid, r in sorted(routes.items()):
        m.node("TransportRoute", rid, node_props("eu_transport_routes", rid, {
            "origin_depot_id": r["depot"], "destination_shipto_id": r["shipto"], "option_code": r["option"], "transport_mode": r["mode"], "service_level": r["level"],
            "service_model": r["model"], "total_distance_km": r["km"], "distance_type": DIST_TYPE["ROAD"] if r["mode"] == "ROAD" else "SYNTHETIC_ROUTE_DISTANCE", "legs_count": len(r["legs"]),
            "estimated_transit_days": r["transit"], "handling_days": r["handling"], "total_estimated_days": r["total_days"], "estimate_basis": "ESTIMATED",
            "estimate_note": "Estimated and synthetic; not a guaranteed delivery date", "distance_band": r["band"], "destination_scope": r["scope"], "route_status": "ACTIVE_DEMO"}))
        m.rel("FROM_DEPOT", ("TransportRoute", rid), ("Warehouse", r["depot"]), "eu_transport_routes")
        m.rel("TO_SHIP_TO", ("TransportRoute", rid), ("ShipTo", r["shipto"]), "eu_transport_routes")
        m.rel("USES_OPTION", ("TransportRoute", rid), ("TransportOption", r["option_id"]), "eu_transport_routes")
        m.rel("PRICED_BY", ("TransportRoute", rid), ("FreightRate", rate_ids[(r["depot"], r["option_id"], r["band"], r["scope"])]), "eu_transport_routes")
        for seq, lid in enumerate(r["legs"], start=1):
            m.rel("HAS_LEG", ("TransportRoute", rid), ("TransportLeg", lid), "eu_transport_routes", {"sequence": seq})
        served.add((r["depot"], r["option_id"]))
    for depot, oid in sorted(served):
        m.rel("HAS_TRANSPORT_OPTION", ("Warehouse", depot), ("TransportOption", oid), "eu_depot_options")
    return {"routes": len(routes), "legs": len(legs), "rates": len(rate_ids)}
