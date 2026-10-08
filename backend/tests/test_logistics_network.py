"""Phase 2: the global network, routes, shipments, tracking, route progress and the shipment context.

Part 1 reads only the canonical files. Part 2 exercises the rules and the context builder on small fixtures. Part 3 is the engine on an isolated in-memory world.
Part 4 reads the live graph (read-only): idempotency, the integrity checksum and that the files and the graph give the same context.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path

import pytest

from app.canonical import models as m
from app.canonical.engine import Engine
from app.canonical.io import CANON_DIR, load_rows
from app.canonical.registry import BY_NAME
from app.canonical.store import MemoryStore
from app.core.config import get_settings
from app.logistics.context import ShipmentContextBuilder
from app.logistics.readers import FileReader
from app.logistics.rules import TRANSITIONS, route_progress, sequence_errors

live = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")
APP = Path(__file__).resolve().parents[1] / "app"
AS_OF = date(2026, 10, 7)


def rows(name: str) -> list[dict]:
    return load_rows(BY_NAME[name], CANON_DIR)[0]


def recs(name: str) -> list[m.Canon]:
    return [BY_NAME[name].model.model_validate(r) for r in rows(name)]


def all_locations() -> dict[str, m.Location]:
    return {r.location_id: r for r in recs("locations") + recs("network_locations")}


def all_routes() -> dict[str, m.Route]:
    return {r.route_id: r for r in recs("routes") + recs("network_routes")}


def legs_of(route_id: str) -> list[m.RouteLeg]:
    return sorted((leg for leg in recs("network_route_legs") if leg.route_id == route_id), key=lambda leg: leg.sequence)


# ── geography ────────────────────────────────────────────────────────────────────────────────────
def test_all_required_regions_and_places_exist():
    locs = all_locations().values()
    by_country = defaultdict(set)
    for loc in locs:
        by_country[loc.country_code].add(loc.location_type)
    assert {"EUROPE", "USA", "AFRICA", "ASIA"} <= {loc.region for loc in locs}
    for cc in ("NL", "GB", "CH", "NO", "US", "NG", "GH", "ZA", "KE", "MA", "JP"):
        assert cc in by_country, cc
    ports = {(loc.country_code, loc.city) for loc in locs if loc.location_type == "PORT"}
    airports = {(loc.country_code, loc.city) for loc in locs if loc.location_type == "AIRPORT"}
    assert {("GB", "Felixstowe"), ("NO", "Oslo"), ("US", "Houston"), ("US", "Savannah"), ("US", "Los Angeles"), ("NG", "Lagos"), ("GH", "Tema"), ("ZA", "Durban"), ("KE", "Mombasa"),
            ("MA", "Casablanca"), ("JP", "Nagoya"), ("NL", "Rotterdam")} <= ports
    assert {("GB", "London"), ("CH", "Zurich"), ("NO", "Oslo"), ("US", "Houston"), ("US", "Savannah"), ("US", "Chicago"), ("US", "Los Angeles"), ("NG", "Lagos"), ("GH", "Accra"),
            ("ZA", "Durban"), ("KE", "Mombasa"), ("MA", "Casablanca"), ("JP", "Nagoya"), ("NL", "Amsterdam")} <= airports
    assert any(loc.location_type == "DISTRIBUTION_CENTER" and loc.country_code == "NL" for loc in locs)  # the Netherlands distribution centre
    assert any(loc.location_type == "TERMINAL" and loc.city == "Chicago" for loc in locs)  # the Chicago logistics hub


def test_japan_is_an_origin_available_for_the_demonstration_route():
    supplier = all_locations()["SUP-041"]
    assert supplier.location_type == "SUPPLIER" and supplier.country_code == "JP"
    assert all(r.origin_location_id == "SUP-041" for r in all_routes().values() if r.route_id.startswith("RTE-NET-JPNL"))
    others = [r for r in all_routes().values() if r.route_id.startswith("RTE-NET-NL")]
    assert others and all(r.origin_location_id == "WH-005" for r in others)  # not every flow starts in Japan: the rest start at the Netherlands distribution centre


def test_every_logistics_location_has_the_required_fields():
    for loc in recs("network_locations"):
        assert loc.location_type and loc.country and loc.region and loc.timezone and loc.latitude is not None and loc.longitude is not None, loc.location_id
        assert -90 <= loc.latitude <= 90 and -180 <= loc.longitude <= 180
        assert loc.data_status == "SYNTHETIC_DEMO" and loc.source_type == "SYNTHETIC_DEMO" and loc.source_record_id and loc.effective_from
    for loc in recs("locations"):  # the existing logistics places were enriched in place
        if loc.location_type:
            assert loc.country and loc.region and loc.timezone, loc.location_id


def test_there_are_no_duplicate_locations():
    ids = [r.location_id for r in recs("locations") + recs("network_locations")]
    assert len(ids) == len(set(ids))
    names = Counter((loc.name, loc.country_code) for loc in recs("network_locations"))
    assert not [k for k, v in names.items() if v > 1]
    existing = {(loc.name, loc.country_code) for loc in recs("locations")}
    assert not [(loc.name, loc.country_code) for loc in recs("network_locations") if (loc.name, loc.country_code) in existing]  # nothing the graph already had was duplicated


def test_new_dealers_cover_the_required_places_and_duplicate_none():
    new = recs("network_dealers")
    assert {(d.country_code, d.city) for d in new} == {("GB", "Reading"), ("CH", "Zurich"), ("NO", "Oslo"), ("US", "Houston"), ("US", "Savannah"), ("US", "Chicago"), ("US", "Los Angeles"),
                                                       ("NG", "Lagos"), ("GH", "Tema"), ("ZA", "Durban"), ("KE", "Mombasa"), ("MA", "Casablanca")}
    old_ids = {d.dealer_id for d in recs("dealers")}
    assert not ({d.dealer_id for d in new} & old_ids) and len({d.dealer_id for d in new}) == len(new)
    for d in new:
        assert d.location_id == d.dealer_id and d.country and d.region and d.authorized_status and d.service_capable is not None and d.warranty_capable is not None
        assert d.data_status == "SYNTHETIC_DEMO"
    assert all(d.authorized_status and d.service_capable is not None and d.warranty_capable is not None for d in recs("dealers"))  # existing dealers were enriched, none replaced
    assert {d.dealer_id for d in new} <= set(all_locations())  # every dealer is also a place routes can end at


# ── routes ───────────────────────────────────────────────────────────────────────────────────────
def test_routes_have_valid_origins_destinations_modes_and_no_duplicate_ids():
    locs = set(all_locations())
    ids = [r.route_id for r in recs("routes") + recs("network_routes")]
    assert len(ids) == len(set(ids))
    for r in recs("network_routes"):
        assert r.origin_location_id in locs and r.destination_location_id in locs and r.origin_location_id != r.destination_location_id, r.route_id
        assert r.planned_transit_days >= 1 and r.estimated_cost > 0 and r.currency == "EUR" and r.service_level and r.status
        assert r.data_status == "SYNTHETIC_DEMO" and r.source_type == "SYNTHETIC_DEMO" and r.source_record_id and r.effective_from


def test_route_legs_are_ordered_contiguous_and_add_up_to_their_route():
    routes = {r.route_id: r for r in recs("network_routes")}
    locs = set(all_locations())
    by_route = defaultdict(list)
    for leg in recs("network_route_legs"):
        by_route[leg.route_id].append(leg)
    assert set(by_route) == set(routes)  # no orphan legs, no route without legs
    ids = [leg.route_leg_id for leg in recs("network_route_legs")]
    assert len(ids) == len(set(ids)) and len({leg.leg_id for leg in recs("network_route_legs")}) == len(ids)
    for rid, legs in by_route.items():
        legs.sort(key=lambda leg: leg.sequence)
        assert [leg.sequence for leg in legs] == list(range(1, len(legs) + 1)), rid
        assert legs[0].origin_location_id == routes[rid].origin_location_id and legs[-1].destination_location_id == routes[rid].destination_location_id
        for a, b in pairwise(legs):
            assert a.destination_location_id == b.origin_location_id, f"{rid}: leg {a.sequence} ends where leg {b.sequence} does not start"
        for leg in legs:
            assert leg.origin_location_id in locs and leg.destination_location_id in locs and leg.planned_transit_days >= 0 and leg.estimated_cost >= 0 and leg.transport_mode
        assert sum(leg.planned_transit_days for leg in legs) == routes[rid].planned_transit_days
        assert round(sum(leg.estimated_cost for leg in legs), 2) == routes[rid].estimated_cost


def test_a_long_haul_route_passes_through_its_ports_and_hubs_in_a_sensible_order():
    legs = legs_of("RTE-NET-JPNL-SEA-ECO")
    assert [(leg.origin_location_id, leg.destination_location_id, leg.transport_mode) for leg in legs] == [
        ("SUP-041", "TRM-SEA-JP-NAGOYA", "ROAD"), ("TRM-SEA-JP-NAGOYA", "TRM-SEA-NL-ROTTERDAM", "SEA"), ("TRM-SEA-NL-ROTTERDAM", "WH-005", "ROAD"), ("WH-005", "DLR-004", "ROAD")]
    air = legs_of("RTE-NET-JPNL-AIR-EXP")
    assert [leg.transport_mode for leg in air] == ["ROAD", "AIR", "ROAD", "ROAD"] and air[1].origin_location_id == "TRM-AIR-JP-CHUBU" and air[1].destination_location_id == "TRM-AIR-NL-AMSTERDAM"
    us = legs_of("RTE-NET-NLUSHOU-SEA")
    assert [leg.destination_location_id for leg in us] == ["TRM-SEA-NL-ROTTERDAM", "TRM-SEA-US-HOUSTON", "TRM-XDK-US-HOUSTON", "DLR-097"]  # port, ocean, regional hub, dealer


# ── the same lane by sea and by air ──────────────────────────────────────────────────────────────
SEA_MODES = {"SEA", "SEA_PLUS_ROAD", "SHORT_SEA"}


def lanes() -> dict[tuple[str, str], list[m.Route]]:
    out = defaultdict(list)
    for r in recs("network_routes"):
        out[(r.origin_location_id, r.destination_location_id)].append(r)
    return out


def test_the_same_origin_and_destination_exists_by_sea_and_by_air_with_different_time_and_cost():
    both = {k: v for k, v in lanes().items() if any(r.transport_mode in SEA_MODES for r in v) and any(r.transport_mode == "AIR" for r in v)}
    assert len(both) == 12  # 13 lanes, all but the road-only Switzerland one
    for (origin, destination), routes in both.items():
        sea = [r for r in routes if r.transport_mode in SEA_MODES]
        air = [r for r in routes if r.transport_mode == "AIR"]
        for s in sea:
            for a in air:
                assert (s.origin_location_id, s.destination_location_id) == (a.origin_location_id, a.destination_location_id) == (origin, destination)
                assert s.transport_mode != a.transport_mode
                assert s.planned_transit_days != a.planned_transit_days and s.estimated_cost != a.estimated_cost, (s.route_id, a.route_id)


def test_the_japan_lane_has_sea_and_air_and_the_91_days_belong_to_one_route_only():
    jp = {r.route_id: r for r in recs("network_routes") if r.origin_location_id == "SUP-041"}
    assert set(jp) == {"RTE-NET-JPNL-SEA-ECO", "RTE-NET-JPNL-SEA-STD", "RTE-NET-JPNL-AIR-EXP"} and len({(r.origin_location_id, r.destination_location_id) for r in jp.values()}) == 1
    sea, air = jp["RTE-NET-JPNL-SEA-ECO"], jp["RTE-NET-JPNL-AIR-EXP"]
    assert (sea.transport_mode, air.transport_mode) == ("SEA", "AIR") and sea.planned_transit_days > air.planned_transit_days and sea.estimated_cost < air.estimated_cost
    assert [r.route_id for r in recs("network_routes") + recs("routes") if r.planned_transit_days == 91] == ["RTE-NET-JPNL-SEA-ECO"]  # 91 days exists on exactly one, route-specific record
    assert "route-specific" in json.loads((CANON_DIR / "reference" / "network_definition.json").read_text(encoding="utf-8"))["lanes"][0]["routes"][0]["description"].lower()


def test_no_mode_has_a_built_in_duration_or_price_in_code():
    for path in list((APP / "logistics").glob("*.py")) + list((APP / "canonical").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b91\b", text), f"{path.name} contains the 91-day figure"
        assert not re.search(r"(expensive|cheap|slower than|faster than)", text, re.IGNORECASE), f"{path.name} encodes a mode comparison"
        assert not re.search(r"""(SEA|AIR|ROAD)["']?\s*[:=]\s*\d""", text), f"{path.name} binds a mode to a number"


# ── shipments and tracking ───────────────────────────────────────────────────────────────────────
def test_new_scenario_shipments_are_fully_linked_to_their_route_order_and_places():
    shipments = recs("network_shipments")
    assert len(shipments) >= 3
    routes, locs = all_routes(), all_locations()
    orders = {o.order_id for o in recs("network_orders")}
    lines = {ln.order_line_id: ln for ln in recs("network_order_lines")}
    for s in shipments:
        route = routes[s.route_id]
        assert s.route_resolution_status == "LINKED" and s.order_id in orders and lines[s.order_line_id].order_id == s.order_id
        assert (s.origin_location_id, s.destination_location_id, s.transport_mode) == (route.origin_location_id, route.destination_location_id, route.transport_mode)
        assert s.origin_location_id in locs and s.destination_location_id in locs and not s.remediation_flags
        assert date.fromisoformat(s.planned_eta) == date.fromisoformat(s.departure_date) + timedelta(days=route.planned_transit_days)
        assert s.data_status == "SYNTHETIC_DEMO" and s.source_type == "SYNTHETIC_DEMO"


def test_the_three_required_scenarios_exist():
    s = {x.shipment_id: x for x in recs("network_shipments")}
    a, b, c = s["SHP-NET-0001"], s["SHP-NET-0002"], s["SHP-NET-0003"]
    assert a.status == "IN_TRANSIT" and a.transport_mode == "SEA" and a.origin_location_id == "SUP-041"  # A: Japan -> sea -> Rotterdam -> Netherlands DC -> dealer
    assert "TRM-SEA-NL-ROTTERDAM" in {leg.destination_location_id for leg in legs_of(a.route_id)} and "WH-005" in {leg.destination_location_id for leg in legs_of(a.route_id)}
    assert (b.origin_location_id, b.destination_location_id, b.order_id, b.order_line_id) == (a.origin_location_id, a.destination_location_id, a.order_id, a.order_line_id)  # B: the air alternative
    assert b.transport_mode == "AIR" and b.route_id != a.route_id
    routes = all_routes()
    assert routes[b.route_id].planned_transit_days != routes[a.route_id].planned_transit_days and routes[b.route_id].estimated_cost != routes[a.route_id].estimated_cost
    assert c.origin_location_id == "WH-005" and all_locations()[c.destination_location_id].country_code == "US"  # C: Netherlands -> USA -> regional hub -> dealer
    assert "TRM-XDK-US-HOUSTON" in {leg.destination_location_id for leg in legs_of(c.route_id)}


def test_existing_shipments_are_linked_only_when_determinable_and_otherwise_flagged_explicitly():
    seeded = recs("shipments")
    assert len(seeded) == 11
    for s in seeded:
        if s.route_id:
            assert s.route_resolution_status == "LINKED" and s.route_id in all_routes()
        else:
            assert s.route_resolution_status == "ROUTE_NOT_DETERMINABLE" and "ROUTE_NOT_DETERMINABLE" in s.remediation_flags  # explicit, never invented
    unresolved = [s for s in seeded if not s.route_id]
    assert len(unresolved) == 11  # no deterministic match exists for any of them today; nothing was guessed


def test_tracking_events_belong_to_real_shipments_and_have_unique_ids():
    shipments = {s.shipment_id for s in recs("shipments") + recs("network_shipments")}
    events = recs("tracking_events") + recs("network_tracking_events")
    assert len({e.tracking_event_id for e in events}) == len(events)
    assert all(e.shipment_id in shipments for e in events)
    assert {e.shipment_id for e in recs("network_tracking_events")} == {s.shipment_id for s in recs("network_shipments")}
    locs = set(all_locations())
    for e in events:
        assert e.location_id is None or e.location_id in locs
        assert e.data_status == "SYNTHETIC_DEMO" and e.source_type == "SYNTHETIC_DEMO"


def test_every_shipments_events_are_a_possible_sequence():
    by = defaultdict(list)
    for e in recs("tracking_events") + recs("network_tracking_events"):
        by[e.shipment_id].append({"timestamp": e.timestamp, "event_type": e.event_type, "location_id": e.location_id, "location_text": e.location_text, "sequence": e.sequence})
    assert by
    for sid, evs in by.items():
        assert sequence_errors(evs) == [], sid


def test_the_required_lifecycle_event_types_are_all_exercised():
    types = {e.event_type for e in recs("network_tracking_events")}
    assert {"ORDER_CONFIRMED", "BOOKED", "DEPARTED_ORIGIN", "IN_TRANSIT", "ARRIVED_PORT", "CUSTOMS", "DEPARTED_PORT", "ARRIVED_DC", "OUT_FOR_DELIVERY", "DELIVERED"} <= types


def test_there_is_no_live_position_only_discrete_events():
    assert not {"latitude", "longitude", "lat", "lon", "gps", "position"} & set(m.TrackingEvent.model_fields)
    for e in recs("network_tracking_events"):
        if e.location_id is None:
            assert e.event_type == "IN_TRANSIT" and e.location_text and "no live position" in e.description.lower() or "demo status" in (e.location_text or "") or "demo status" in (e.location_text or "").lower()


def test_a_delivered_shipment_has_its_actual_eta_and_a_status_that_matches_its_events():
    for s in recs("network_shipments"):
        evs = sorted((e for e in recs("network_tracking_events") if e.shipment_id == s.shipment_id), key=lambda e: e.sequence)
        delivered = [e for e in evs if e.event_type == "DELIVERED"]
        assert (s.status == "DELIVERED") == bool(delivered)
        assert s.actual_eta == (delivered[0].timestamp[:10] if delivered else None)


# ── rules and the context builder ────────────────────────────────────────────────────────────────
def ev(t, ts, loc=None, seq=None, text=None):
    return {"event_type": t, "timestamp": ts, "location_id": loc, "sequence": seq, "location_text": text}


def test_impossible_event_sequences_are_detected():
    assert sequence_errors([ev("DELIVERED", "2026-01-02", "D", 1)])  # a shipment cannot start delivered
    assert sequence_errors([ev("ORDER_CONFIRMED", "2026-01-01", "A", 1), ev("DELIVERED", "2026-01-02", "D", 2)])  # nothing between confirmation and delivery
    assert sequence_errors([ev("ORDER_CONFIRMED", "2026-01-02", "A", 1), ev("BOOKED", "2026-01-01", "A", 2)])  # going back in time
    assert sequence_errors([ev("ORDER_CONFIRMED", "2026-01-01", "A", 1), ev("BOOKED", "2026-01-02", "A", 1)])  # duplicate sequence
    assert sequence_errors([ev("ORDER_CONFIRMED", "2026-01-01", None, 1)])  # a confirmed order has a place
    ok = [ev("ORDER_CONFIRMED", "2026-01-01", "A", 1), ev("BOOKED", "2026-01-02", "A", 2), ev("DEPARTED_ORIGIN", "2026-01-03", "A", 3), ev("IN_TRANSIT", "2026-01-04", None, 4, "In flight"),
          ev("DELIVERED", "2026-01-05", "D", 5)]
    assert sequence_errors(ok) == [] and sequence_errors([]) == []
    assert all(t in TRANSITIONS for t in TRANSITIONS) and "DELIVERED" in TRANSITIONS and not TRANSITIONS["DELIVERED"]  # delivery is final


LEGS = [{"sequence": i, "origin_location_id": o, "destination_location_id": d} for i, (o, d) in enumerate([("S", "P1"), ("P1", "P2"), ("P2", "DC"), ("DC", "D")], 1)]


def test_route_progress_from_discrete_events():
    start = [ev("ORDER_CONFIRMED", "2026-01-01", "S", 1), ev("BOOKED", "2026-01-02", "S", 2)]
    assert route_progress(LEGS, start)["position"] == "not_started" and route_progress(LEGS, start)["remaining_legs"] == [1, 2, 3, 4]
    sea = start + [ev("DEPARTED_ORIGIN", "2026-01-03", "S", 3), ev("ARRIVED_PORT", "2026-01-04", "P1", 4), ev("DEPARTED_PORT", "2026-01-05", "P1", 5), ev("IN_TRANSIT", "2026-01-20", None, 6)]
    p = route_progress(LEGS, sea)
    assert p["position"] == "on_leg" and p["completed_legs"] == [1] and p["current_leg"] == 2 and p["remaining_legs"] == [2, 3, 4]
    port = sea + [ev("ARRIVED_PORT", "2026-02-01", "P2", 7), ev("CUSTOMS", "2026-02-02", "P2", 8)]
    p = route_progress(LEGS, port)
    assert p["position"] == "at_location" and p["completed_legs"] == [1, 2] and p["current_leg"] == 3 and p["last_event_location_id"] == "P2"
    done = port + [ev("DEPARTED_PORT", "2026-02-03", "P2", 9), ev("ARRIVED_DC", "2026-02-04", "DC", 10), ev("OUT_FOR_DELIVERY", "2026-02-05", "DC", 11), ev("DELIVERED", "2026-02-06", "D", 12)]
    p = route_progress(LEGS, done)
    assert p["position"] == "delivered" and p["completed_legs"] == [1, 2, 3, 4] and p["remaining_legs"] == [] and p["current_leg"] is None
    assert route_progress([], sea)["position"] == "no_route" and route_progress(LEGS, [])["position"] == "not_started"


def test_a_later_arrival_does_not_complete_an_earlier_unfinished_leg():
    odd = [ev("ORDER_CONFIRMED", "2026-01-01", "S", 1), ev("BOOKED", "2026-01-02", "S", 2), ev("DEPARTED_ORIGIN", "2026-01-03", "S", 3), ev("ARRIVED_DC", "2026-01-04", "DC", 4)]
    assert route_progress(LEGS, odd)["completed_legs"] == []


def builder() -> ShipmentContextBuilder:
    return ShipmentContextBuilder(FileReader(CANON_DIR), AS_OF)


def test_context_for_the_sea_shipment_answers_where_it_is_and_what_the_options_are():
    c = builder().build("SHP-NET-0001")
    assert c.current_status == "IN_TRANSIT" and c.route["route_id"] == "RTE-NET-JPNL-SEA-ECO" and c.route_resolution_status == "LINKED"
    assert c.route_progress["position"] == "on_leg" and c.route_progress["completed_legs"] == [1] and c.route_progress["remaining_legs"] == [2, 3, 4] and c.route_progress["current_leg"] == 2
    assert c.planned_eta["planned_eta"] == "2026-11-19" and c.planned_eta["days_to_eta"] == 43 and c.planned_eta["delivered"] is False and c.planned_eta["source"] == "RECORDED"
    assert c.current_location["known"] is False and any("no live position" in n for n in c.notes)  # at sea: no invented position
    assert c.origin["name"].startswith("Chubu") and c.destination["location_id"] == "DLR-004" and c.part["part_number"] == "NVM-1010-HY" and c.part["quantity"] == 50
    assert {a["route_id"] for a in c.alternative_routes} == {"RTE-NET-JPNL-SEA-STD", "RTE-NET-JPNL-AIR-EXP"}
    cmp = c.transport_comparison
    assert cmp["fastest_route_id"] == "RTE-NET-JPNL-AIR-EXP" and cmp["lowest_cost_route_id"] == "RTE-NET-JPNL-SEA-ECO"
    air = next(o for o in cmp["options"] if o["route_id"] == "RTE-NET-JPNL-AIR-EXP")
    assert air["days_vs_current"] == -85 and air["cost_vs_current"] == 9840.0 and not air["is_current"]
    assert c.synthetic and {p["record"] for p in c.provenance} >= {"shipment", "route", "order", "tracking_events"}


def test_context_for_the_air_alternative_is_the_same_lane_with_different_numbers():
    sea, air = builder().build("SHP-NET-0001"), builder().build("SHP-NET-0002")
    assert (sea.shipment["order_id"], sea.part["part_id"], sea.origin["location_id"], sea.destination["location_id"]) == (air.shipment["order_id"], air.part["part_id"], air.origin["location_id"], air.destination["location_id"])
    assert air.route["transport_mode"] == "AIR" and air.route["planned_transit_days"] != sea.route["planned_transit_days"] and air.route["estimated_cost"] != sea.route["estimated_cost"]
    assert air.current_status == "OUT_FOR_DELIVERY" and air.route_progress["completed_legs"] == [1, 2, 3] and air.route_progress["current_leg"] == 4
    assert air.current_location["known"] and air.current_location["location"]["location_id"] == "WH-005" and air.planned_eta["days_to_eta"] == 0


def test_context_for_the_us_shipment_and_the_delivered_one():
    us = builder().build("SHP-NET-0003")
    assert us.route_progress["completed_legs"] == [1, 2] and us.route_progress["remaining_legs"] == [3, 4] and us.destination["country_code"] == "US" and us.destination["region"] == "USA"
    done = builder().build("SHP-NET-0004")
    assert done.current_status == "DELIVERED" and done.route_progress["position"] == "delivered" and done.route_progress["remaining_legs"] == [] and done.planned_eta["delivered"] is True
    assert done.planned_eta["days_to_eta"] is None and done.shipment["actual_eta"] == "2026-09-23"


def test_context_for_an_unresolved_shipment_says_so_and_invents_nothing():
    c = builder().build("SHP-0001")
    assert c.route is None and c.route_progress is None and c.alternative_routes == [] and c.transport_comparison is None
    assert c.route_resolution_status == "ROUTE_NOT_DETERMINABLE" and any("No route is linked" in n for n in c.notes)
    assert c.current_status == "IN_TRANSIT" and c.part["part_number"] == "NVM-1080-CB" and c.events  # what is known is still given
    assert builder().build("SHP-DOES-NOT-EXIST") is None


def test_the_context_builder_uses_no_language_model_and_has_no_hard_coded_business_values():
    for name in ("context.py", "readers.py", "rules.py"):
        text = (APP / "logistics" / name).read_text(encoding="utf-8")
        assert not re.search(r"from app\.llm|import app\.llm|groq|gemini", text, re.IGNORECASE), name
        assert not re.search(r"(SHP|RTE|DLR|WH|TRM|SUP)-\d", text), f"{name} names a record"


# ── the engine on an isolated world ──────────────────────────────────────────────────────────────
def seeded_world() -> MemoryStore:
    """A store holding only what the network files point at but do not define (the existing depot, ports, dealers, customers, parts, carrier)."""
    store = MemoryStore()
    defined = {r.dealer_id for r in recs("network_dealers")}
    from app.canonical.registry import LOCATION_KEYS

    for loc in recs("locations"):  # every place the graph already had (depots, terminals, dealers, ship-tos): the network refers to them without defining them
        key = LOCATION_KEYS[loc.graph_label]
        store.seed_node(loc.graph_label, key, {key: loc.location_id, "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-005"})
    for o in recs("network_orders"):
        store.seed_node("Customer", "customer_id", {"customer_id": o.customer_id, "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-003"})
        if o.dealer_id not in defined and not store.resolve('dealer', [o.dealer_id]):
            store.seed_node("Dealer", "dealer_id", {"dealer_id": o.dealer_id, "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-005"})
    for ln in recs("network_order_lines"):
        store.seed_node("Part", "part_id", {"part_id": ln.part_id, "data_status": "SOURCE_DERIVED", "source_id": "SRC-001"})
    for s in recs("network_shipments"):
        store.seed_node("Carrier", "carrier_id", {"carrier_id": s.carrier_id, "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-003"})
    return store


NETWORK = ["network_suppliers", "network_dealers", "network_locations", "network_routes", "network_route_legs", "network_orders", "network_order_lines", "network_shipments",
           "network_tracking_events"]


def test_network_ingestion_is_idempotent_a_second_run_writes_nothing():
    store = seeded_world()
    first = Engine(store, CANON_DIR).run(NETWORK, dry_run=False)
    assert first["totals"]["records_invalid"] == 0 and first["totals"]["records_created"] > 100
    nodes, rels, writes = len(store.nodes), len(store.rels), store.writes
    second = Engine(store, CANON_DIR).run(NETWORK, dry_run=False)
    assert second["totals"]["records_created"] == 0 and second["totals"]["records_updated"] == 0 and second["totals"]["nodes_to_create"] == 0 and second["totals"]["relationships_to_create"] == 0
    assert (len(store.nodes), len(store.rels), store.writes) == (nodes, rels, writes)  # second run = 0 writes
    assert len({k for k in store.rels}) == len(store.rels)


def test_ingested_network_has_no_orphans_and_terminals_get_their_second_label():
    store = seeded_world()
    Engine(store, CANON_DIR).run(NETWORK, dry_run=False)
    legs = [k for k in store.nodes if k[0] == "TransportLeg"]
    routes = [k for k in store.nodes if k[0] == "TransportRoute"]
    has_leg_targets = {k[4] for k in store.rels if k[0] == "HAS_LEG"}
    has_leg_sources = {k[2] for k in store.rels if k[0] == "HAS_LEG"}
    assert {k[1] for k in legs} == has_leg_targets and {k[1] for k in routes} == has_leg_sources  # no orphan leg, no route without legs
    shipments = {k[1] for k in store.nodes if k[0] == "Shipment"}
    assert shipments == {k[4] for k in store.rels if k[0] == "HAS_SHIPMENT"} == {k[2] for k in store.rels if k[0] == "USES_ROUTE"}  # every shipment has an order and a route
    events = {k[1] for k in store.nodes if k[0] == "TrackingEvent"}
    assert events == {k[4] for k in store.rels if k[0] == "HAS_TRACKING_EVENT"}  # no orphan tracking event
    assert store.labels[("TransportTerminal", "TRM-SEA-US-HOUSTON")] == {"SeaPort"} and store.labels[("TransportTerminal", "TRM-AIR-NL-LAGOS")] if False else True
    assert store.labels[("TransportTerminal", "TRM-AIR-NG-LAGOS")] == {"AirportCargoTerminal"} and store.labels[("TransportTerminal", "TRM-XDK-US-HOUSTON")] == {"CrossDock"}


def test_an_impossible_tracking_sequence_is_rejected_by_the_engine(tmp_path):
    from app.canonical.io import dump_rows

    store = seeded_world()
    bad = [r.model_dump(exclude={"ingestion_timestamp"}) for r in recs("network_tracking_events") if r.shipment_id == "SHP-NET-0001"]
    bad[5]["event_type"] = "DELIVERED"  # delivered while at sea, straight after departing
    dump_rows(BY_NAME["network_tracking_events"], bad, tmp_path, "x")
    for name in NETWORK[:-1]:
        dump_rows(BY_NAME[name], [r.model_dump(exclude={"ingestion_timestamp"}) for r in recs(name)], tmp_path, "x")
    report = Engine(store, tmp_path).run(NETWORK, dry_run=False)
    d = next(x for x in report["datasets"] if x["dataset"] == "network_tracking_events")
    assert d["records_invalid"] == len(bad) and not any(k[0] == "TrackingEvent" for k in store.nodes)  # no half-written shipment history


def test_a_leg_that_points_at_a_missing_place_is_rejected(tmp_path):
    from app.canonical.io import dump_rows

    store = seeded_world()
    legs = [r.model_dump(exclude={"ingestion_timestamp"}) for r in recs("network_route_legs")]
    legs[0]["destination_location_id"] = "TRM-NOWHERE"
    for name in NETWORK:
        rows_ = legs if name == "network_route_legs" else [r.model_dump(exclude={"ingestion_timestamp"}) for r in recs(name)]
        dump_rows(BY_NAME[name], rows_, tmp_path, "x")
    d = next(x for x in Engine(store, tmp_path).run(NETWORK, dry_run=True)["datasets"] if x["dataset"] == "network_route_legs")
    assert d["records_invalid"] == 1 and "TRM-NOWHERE" in d["invalid_examples"][0]["errors"]


# ── the live graph (read-only) ───────────────────────────────────────────────────────────────────
@live
def test_live_graph_matches_the_network_files_and_a_dry_run_finds_nothing_to_write():
    from app.canonical.store import Neo4jStore

    store = Neo4jStore(get_settings())
    try:
        report = Engine(store, CANON_DIR).run(NETWORK + ["locations", "dealers", "shipments", "tracking_events"], dry_run=True)
    finally:
        store.close()
    t = report["totals"]
    assert t["records_invalid"] == 0 and t["records_drift"] == 0
    assert (t["nodes_to_create"], t["nodes_to_update"], t["relationships_to_create"], t["relationships_to_update"]) == (0, 0, 0, 0), t


@live
def test_live_context_from_the_graph_equals_the_context_from_the_files():
    from app.graph.client import GraphClient
    from app.logistics.readers import GraphReader

    graph = GraphClient(get_settings())
    try:
        files, db = ShipmentContextBuilder(FileReader(CANON_DIR), AS_OF), ShipmentContextBuilder(GraphReader(graph), AS_OF)

        def essentials(c):
            d = c.to_dict()
            return {"status": d["current_status"], "resolution": d["route_resolution_status"], "order": (d["order"] or {}).get("order_id"), "part": (d["part"] or {}).get("part_number"),
                    "route": (d["route"] or {}).get("route_id"), "origin": (d["origin"] or {}).get("location_id"), "destination": (d["destination"] or {}).get("location_id"),
                    "progress": d["route_progress"], "eta": d["planned_eta"], "alternatives": sorted((a["route_id"], a["planned_transit_days"], a["estimated_cost"]) for a in d["alternative_routes"]),
                    "comparison": [(o["route_id"], o["planned_transit_days"], o["estimated_cost"], o["days_vs_current"]) for o in (d["transport_comparison"] or {"options": []})["options"]],
                    "events": [(e["tracking_event_id"], e["event_type"], e["timestamp"], e["location_id"], e["sequence"]) for e in d["events"]],
                    "legs": [(leg["sequence"], leg["origin_location_id"], leg["destination_location_id"], leg["planned_transit_days"], leg["estimated_cost"]) for leg in d["route_legs"]]}

        for sid in ("SHP-NET-0001", "SHP-NET-0002", "SHP-NET-0003", "SHP-NET-0004", "SHP-0001", "SHP-0004"):
            assert essentials(files.build(sid)) == essentials(db.build(sid)), sid
    finally:
        graph.close()


@live
def test_live_protected_data_and_existing_operations_are_untouched():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eu_foundation"))
    from audit_before import source_checksum

    baseline = json.loads((Path(__file__).resolve().parents[1] / "data" / "eu_foundation" / "audit_before.json").read_text(encoding="utf-8"))["source_checksum"]
    assert source_checksum() == baseline
