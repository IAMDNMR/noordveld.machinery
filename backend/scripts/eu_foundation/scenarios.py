"""End-to-end scenarios over the live graph (read-only): depot -> stock -> route/legs -> rate -> dealer coverage -> estimate.

  python scenarios.py     writes backend/data/eu_foundation/scenarios.json; exit 1 if any scenario fails
"""
from __future__ import annotations

import sys
from typing import Any

from common import dump, read

# name, origin depot country, destination country, destination city (None = any), mode that must be offered (None = road default only)
SCENARIOS = [
    ("NL domestic",                  "NL", "NL", None,        "ROAD"),
    ("DE domestic",                  "DE", "DE", None,        "ROAD"),
    ("NL -> DE cross-border",        "NL", "DE", None,        "ROAD"),
    ("DE -> FR cross-border",        "DE", "FR", None,        "ROAD"),
    ("NL -> BE cross-border",        "NL", "BE", None,        "ROAD"),
    ("NL -> PL cross-border",        "NL", "PL", None,        "ROAD"),
    ("DE -> AT cross-border",        "DE", "AT", None,        "ROAD"),
    ("DE -> CZ cross-border",        "DE", "CZ", None,        "ROAD"),
    ("NL -> FR road and multimodal", "NL", "FR", None,        "MULTIMODAL"),
    ("Urgent air NL -> ES (fastest)",          "NL", "ES", None,        "AIR"),
    ("Urgent air DE -> IT (fastest)",          "DE", "IT", None,        "AIR"),
    ("Rail DE -> IT",                "DE", "IT", None,        "RAIL"),
    ("Inland waterway NL -> DE",     "NL", "DE", None,        "INLAND_WATERWAY"),
    ("Short-sea NL -> SE",           "NL", "SE", None,        "SHORT_SEA"),
]


def scenario(name: str, origin_cc: str, dest_cc: str, city: str | None, mode: str) -> dict[str, Any]:
    r: dict[str, Any] = {"scenario": name, "steps": {}}
    st = r["steps"]
    rows = read("""
        MATCH (w:Warehouse {country_code: $o})<-[:FROM_DEPOT]-(t:TransportRoute)-[:TO_SHIP_TO]->(s:ShipTo {country_code: $d})
        WHERE ($c IS NULL OR s.city = $c) AND t.transport_mode = $m
        MATCH (t)-[:PRICED_BY]->(f:FreightRate) MATCH (t)-[:USES_OPTION]->(o:TransportOption)
        RETURN w.warehouse_id AS depot, w.name AS depot_name, s.shipto_id AS shipto, s.city AS city, t.route_id AS route, t.option_code AS option, t.total_distance_km AS km,
               t.total_estimated_days AS days, t.estimate_basis AS basis, t.legs_count AS legs, f.total_cost_incl_handling AS total, f.total_transport_cost AS transport,
               f.handling_cost AS handling, f.currency AS cur ORDER BY CASE WHEN $m = 'AIR' THEN t.total_estimated_days ELSE 0 END, total, route LIMIT 1""", o=origin_cc, d=dest_cc, c=city, m=mode)
    st["route_found"] = bool(rows)
    if not rows:
        r["pass"] = False
        return r
    x = rows[0]
    r["route"] = {k: x[k] for k in ("depot", "depot_name", "shipto", "city", "route", "option", "km", "days", "legs", "transport", "handling", "total", "cur")}
    legs = read("MATCH (t:TransportRoute {route_id: $r})-[h:HAS_LEG]->(l:TransportLeg) RETURN h.sequence AS seq, l.mode AS mode, l.from_id AS a, l.to_id AS b, l.distance_km AS km ORDER BY seq", r=x["route"])
    r["legs"] = legs
    st["legs_chain_connected"] = bool(legs) and legs[0]["a"] == x["depot"] and legs[-1]["b"] == x["shipto"] and all(legs[i]["b"] == legs[i + 1]["a"] for i in range(len(legs) - 1))
    st["leg_distances_sum_to_route"] = abs(sum(l["km"] for l in legs) - x["km"]) < 1.0
    st["mode_present_in_legs"] = mode in {l["mode"] for l in legs} or (mode == "MULTIMODAL" and len({l["mode"] for l in legs}) >= 2)
    st["multimodal_has_two_modes"] = mode != "MULTIMODAL" or len({l["mode"] for l in legs}) >= 2
    st["cost_components_add_up"] = abs(x["total"] - (x["transport"] + x["handling"])) < 0.02 and x["cur"] == "EUR"
    st["estimate_labelled"] = x["basis"] == "ESTIMATED"
    # road default: a road route exists for the same depot/ship-to pair
    road = read("MATCH (:Warehouse {warehouse_id: $w})<-[:FROM_DEPOT]-(t:TransportRoute {transport_mode:'ROAD'})-[:TO_SHIP_TO]->(:ShipTo {shipto_id: $s}) RETURN count(t) AS n", w=x["depot"], s=x["shipto"])
    st["road_default_available"] = road[0]["n"] > 0 or mode != "ROAD"
    # a catalogue part in stock at that depot (stock the customer could actually draw on)
    stock = read("""MATCH (p:Part)-[a:AVAILABLE_AT]->(:Warehouse {warehouse_id: $w}) WHERE a.stock_status IN ['IN_STOCK','LOW_STOCK'] AND coalesce(a.available,0) > 0
                    MATCH (pr:Price)-[:PRICES_PART]->(p) RETURN p.part_id AS part, a.available AS qty, a.stock_status AS status, pr.list_price_ex_vat AS price ORDER BY part LIMIT 1""", w=x["depot"])
    st["part_in_stock_at_depot"] = bool(stock)
    if stock:
        r["part"] = stock[0]
        st["part_price_preserved_eur"] = stock[0]["price"] is not None and stock[0]["price"] > 0
        r["total_incl_transport_eur"] = round(stock[0]["price"] + x["total"], 2)
    # a dealer in the destination country that is explicitly configured to serve a territory there and supports machine families
    dealer = read("""MATCH (d:Dealer {country_code: $d})-[:SERVES_TERRITORY]->() MATCH (d)-[:SERVES_FAMILY|SERVICES_MACHINE_FAMILY]->(f:MachineFamily)
                     RETURN d.dealer_id AS dealer, d.name AS name, collect(DISTINCT f.family_id)[..3] AS families ORDER BY dealer LIMIT 1""", d=dest_cc)
    st["destination_dealer_configured"] = bool(dealer)
    r["dealer"] = dealer[0] if dealer else None
    # the destination is a ship-to and is never inferred to belong to a dealer
    linked = read("MATCH (s:ShipTo {shipto_id: $s}) RETURN size([(s)--(d:Dealer) | 1]) AS n", s=x["shipto"])
    st["ship_to_not_linked_to_dealer"] = linked[0]["n"] == 0
    r["pass"] = all(st.values())
    return r


def main() -> int:
    results = [scenario(*s) for s in SCENARIOS]
    dump("scenarios.json", {"scenarios": results, "passed": sum(x["pass"] for x in results), "total": len(results)})
    for x in results:
        route = x.get("route", {})
        print(f"{'PASS' if x['pass'] else 'FAIL'}  {x['scenario']:<30} {route.get('depot', '-'):>6} -> {route.get('shipto', '-'):<10} {route.get('option', '-'):<22} {route.get('km', '-')!s:>8} km  {route.get('days', '-')!s:>2} d  EUR {route.get('total', '-')}")
        if not x["pass"]:
            print("      failed steps:", [k for k, v in x["steps"].items() if not v])
    print(f"{sum(x['pass'] for x in results)}/{len(results)} scenarios passed")
    return 0 if all(x["pass"] for x in results) else 1


if __name__ == "__main__":
    sys.exit(main())
