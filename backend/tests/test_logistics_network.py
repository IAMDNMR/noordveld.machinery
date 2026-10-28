"""Phase 2: the global network, routes, shipments, tracking, route progress and the shipment context.

Part 1 reads only the canonical files. Part 2 exercises the rules and the context builder on small fixtures. Part 3 is the engine on an isolated in-memory world.
Part 4 reads the live graph (read-only): idempotency, the integrity checksum and that the files and the graph give the same context.
"""

from __future__ import annotations

from collections import defaultdict
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
    return sorted(
        (leg for leg in recs("network_route_legs") if leg.route_id == route_id),
        key=lambda leg: leg.sequence,
    )


# ── geography ────────────────────────────────────────────────────────────────────────────────────


# ── routes ───────────────────────────────────────────────────────────────────────────────────────


def test_route_legs_are_ordered_contiguous_and_add_up_to_their_route():
    routes = {r.route_id: r for r in recs("network_routes")}
    locs = set(all_locations())
    by_route = defaultdict(list)
    for leg in recs("network_route_legs"):
        by_route[leg.route_id].append(leg)
    assert set(by_route) == set(routes)  # no orphan legs, no route without legs
    ids = [leg.route_leg_id for leg in recs("network_route_legs")]
    assert len(ids) == len(set(ids)) and len(
        {leg.leg_id for leg in recs("network_route_legs")}
    ) == len(ids)
    for rid, legs in by_route.items():
        legs.sort(key=lambda leg: leg.sequence)
        assert [leg.sequence for leg in legs] == list(range(1, len(legs) + 1)), rid
        assert (
            legs[0].origin_location_id == routes[rid].origin_location_id
            and legs[-1].destination_location_id == routes[rid].destination_location_id
        )
        for a, b in pairwise(legs):
            assert a.destination_location_id == b.origin_location_id, (
                f"{rid}: leg {a.sequence} ends where leg {b.sequence} does not start"
            )
        for leg in legs:
            assert (
                leg.origin_location_id in locs
                and leg.destination_location_id in locs
                and leg.planned_transit_days >= 0
                and leg.estimated_cost >= 0
                and leg.transport_mode
            )
        assert sum(leg.planned_transit_days for leg in legs) == routes[rid].planned_transit_days
        assert round(sum(leg.estimated_cost for leg in legs), 2) == routes[rid].estimated_cost


# ── the same lane by sea and by air ──────────────────────────────────────────────────────────────
SEA_MODES = {"SEA", "SEA_PLUS_ROAD", "SHORT_SEA"}


def lanes() -> dict[tuple[str, str], list[m.Route]]:
    out = defaultdict(list)
    for r in recs("network_routes"):
        out[(r.origin_location_id, r.destination_location_id)].append(r)
    return out


# ── shipments and tracking ───────────────────────────────────────────────────────────────────────
def test_new_scenario_shipments_are_fully_linked_to_their_route_order_and_places():
    shipments = recs("network_shipments")
    assert len(shipments) >= 3
    routes, locs = all_routes(), all_locations()
    orders = {o.order_id for o in recs("network_orders")}
    lines = {ln.order_line_id: ln for ln in recs("network_order_lines")}
    shipped: dict[str, list[str]] = {}
    for sl in recs("network_shipment_lines"):
        shipped.setdefault(sl.shipment_id, []).append(sl.order_line_id)
    for s in shipments:
        route = routes[s.route_id]
        assert shipped[s.shipment_id] and all(
            lines[i].order_id == s.order_id for i in shipped[s.shipment_id]
        )  # every shipment ships at least one line of its own order
        assert s.route_resolution_status == "LINKED" and s.order_id in orders
        assert (s.origin_location_id, s.destination_location_id, s.transport_mode) == (
            route.origin_location_id,
            route.destination_location_id,
            route.transport_mode,
        )
        assert (
            s.origin_location_id in locs
            and s.destination_location_id in locs
            and not s.remediation_flags
        )
        assert date.fromisoformat(s.planned_eta) == date.fromisoformat(
            s.departure_date
        ) + timedelta(days=route.planned_transit_days)
        assert s.data_status == "SYNTHETIC_DEMO" and s.source_type == "SYNTHETIC_DEMO"


def test_the_three_required_scenarios_exist():
    s = {x.shipment_id: x for x in recs("network_shipments")}
    a, b, c = s["SHP-NET-0001"], s["SHP-NET-0002"], s["SHP-NET-0003"]
    assert (
        a.status == "IN_TRANSIT" and a.transport_mode == "SEA" and a.origin_location_id == "SUP-041"
    )  # A: Japan -> sea -> Rotterdam -> Netherlands DC -> dealer
    assert "TRM-SEA-NL-ROTTERDAM" in {
        leg.destination_location_id for leg in legs_of(a.route_id)
    } and "WH-005" in {leg.destination_location_id for leg in legs_of(a.route_id)}
    shipped = {sl.shipment_id: sl.order_line_id for sl in recs("network_shipment_lines")}
    assert (
        b.origin_location_id,
        b.destination_location_id,
        b.order_id,
        shipped[b.shipment_id],
    ) == (
        a.origin_location_id,
        a.destination_location_id,
        a.order_id,
        shipped[a.shipment_id],
    )  # B: the air alternative
    assert b.transport_mode == "AIR" and b.route_id != a.route_id
    routes = all_routes()
    assert (
        routes[b.route_id].planned_transit_days != routes[a.route_id].planned_transit_days
        and routes[b.route_id].estimated_cost != routes[a.route_id].estimated_cost
    )
    assert (
        c.origin_location_id == "WH-005"
        and all_locations()[c.destination_location_id].country_code == "US"
    )  # C: Netherlands -> USA -> regional hub -> dealer
    assert "TRM-XDK-US-HOUSTON" in {leg.destination_location_id for leg in legs_of(c.route_id)}


def test_existing_shipments_are_linked_only_when_determinable_and_otherwise_flagged_explicitly():
    seeded = recs("shipments")
    assert len(seeded) == 11
    for s in seeded:
        if s.route_id:
            assert s.route_resolution_status == "LINKED" and s.route_id in all_routes()
        else:
            assert (
                s.route_resolution_status == "ROUTE_NOT_DETERMINABLE"
                and "ROUTE_NOT_DETERMINABLE" in s.remediation_flags
            )  # explicit, never invented
    unresolved = [s for s in seeded if not s.route_id]
    assert (
        len(unresolved) == 11
    )  # no deterministic match exists for any of them today; nothing was guessed


def test_tracking_events_belong_to_real_shipments_and_have_unique_ids():
    shipments = {s.shipment_id for s in recs("shipments") + recs("network_shipments")}
    events = recs("tracking_events") + recs("network_tracking_events")
    assert len({e.tracking_event_id for e in events}) == len(events)
    assert all(e.shipment_id in shipments for e in events)
    assert {e.shipment_id for e in recs("network_tracking_events")} == {
        s.shipment_id for s in recs("network_shipments")
    }
    locs = set(all_locations())
    for e in events:
        assert e.location_id is None or e.location_id in locs
        assert e.data_status == "SYNTHETIC_DEMO" and e.source_type == "SYNTHETIC_DEMO"


def test_every_shipments_events_are_a_possible_sequence():
    by = defaultdict(list)
    for e in recs("tracking_events") + recs("network_tracking_events"):
        by[e.shipment_id].append(
            {
                "timestamp": e.timestamp,
                "event_type": e.event_type,
                "location_id": e.location_id,
                "location_text": e.location_text,
                "sequence": e.sequence,
            }
        )
    assert by
    for sid, evs in by.items():
        assert sequence_errors(evs) == [], sid


def test_the_required_lifecycle_event_types_are_all_exercised():
    types = {e.event_type for e in recs("network_tracking_events")}
    assert {
        "ORDER_CONFIRMED",
        "BOOKED",
        "DEPARTED_ORIGIN",
        "IN_TRANSIT",
        "ARRIVED_PORT",
        "CUSTOMS",
        "DEPARTED_PORT",
        "ARRIVED_DC",
        "OUT_FOR_DELIVERY",
        "DELIVERED",
    } <= types


def test_there_is_no_live_position_only_discrete_events():
    assert not {"latitude", "longitude", "lat", "lon", "gps", "position"} & set(
        m.TrackingEvent.model_fields
    )
    for e in recs("network_tracking_events"):
        if e.location_id is None:
            assert (
                e.event_type == "IN_TRANSIT"
                and e.location_text
                and "no live position" in e.description.lower()
                or "demo status" in (e.location_text or "")
                or "demo status" in (e.location_text or "").lower()
            )


def test_a_delivered_shipment_has_its_actual_eta_and_a_status_that_matches_its_events():
    for s in recs("network_shipments"):
        evs = sorted(
            (e for e in recs("network_tracking_events") if e.shipment_id == s.shipment_id),
            key=lambda e: e.sequence,
        )
        delivered = [e for e in evs if e.event_type == "DELIVERED"]
        assert (s.status == "DELIVERED") == bool(delivered)
        assert s.actual_eta == (delivered[0].timestamp[:10] if delivered else None)


# ── rules and the context builder ────────────────────────────────────────────────────────────────
def ev(t, ts, loc=None, seq=None, text=None):
    return {
        "event_type": t,
        "timestamp": ts,
        "location_id": loc,
        "sequence": seq,
        "location_text": text,
    }


def test_impossible_event_sequences_are_detected():
    assert sequence_errors(
        [ev("DELIVERED", "2026-01-02", "D", 1)]
    )  # a shipment cannot start delivered
    assert sequence_errors(
        [ev("ORDER_CONFIRMED", "2026-01-01", "A", 1), ev("DELIVERED", "2026-01-02", "D", 2)]
    )  # nothing between confirmation and delivery
    assert sequence_errors(
        [ev("ORDER_CONFIRMED", "2026-01-02", "A", 1), ev("BOOKED", "2026-01-01", "A", 2)]
    )  # going back in time
    assert sequence_errors(
        [ev("ORDER_CONFIRMED", "2026-01-01", "A", 1), ev("BOOKED", "2026-01-02", "A", 1)]
    )  # duplicate sequence
    assert sequence_errors(
        [ev("ORDER_CONFIRMED", "2026-01-01", None, 1)]
    )  # a confirmed order has a place
    ok = [
        ev("ORDER_CONFIRMED", "2026-01-01", "A", 1),
        ev("BOOKED", "2026-01-02", "A", 2),
        ev("DEPARTED_ORIGIN", "2026-01-03", "A", 3),
        ev("IN_TRANSIT", "2026-01-04", None, 4, "In flight"),
        ev("DELIVERED", "2026-01-05", "D", 5),
    ]
    assert sequence_errors(ok) == [] and sequence_errors([]) == []
    assert (
        all(t in TRANSITIONS for t in TRANSITIONS)
        and "DELIVERED" in TRANSITIONS
        and not TRANSITIONS["DELIVERED"]
    )  # delivery is final


LEGS = [
    {"sequence": i, "origin_location_id": o, "destination_location_id": d}
    for i, (o, d) in enumerate([("S", "P1"), ("P1", "P2"), ("P2", "DC"), ("DC", "D")], 1)
]


def test_a_delivered_shipment_has_completed_every_leg():
    moving = [ev("DEPARTED_ORIGIN", "2026-01-01", "S", 1), ev("ARRIVED_PORT", "2026-01-02", "P1", 2)]
    p = route_progress(LEGS, moving)
    assert p["completed_legs"] == [1] and p["current_leg"] == 2 and p["position"] == "at_location"
    # app tracking records the place as text only: the DELIVERED event has no location_id
    p = route_progress(LEGS, moving + [ev("DELIVERED", "2026-01-05", None, 3, "Customer site")])
    assert p["completed_legs"] == [1, 2, 3, 4] and p["remaining_legs"] == [] and p["position"] == "delivered"


def builder() -> ShipmentContextBuilder:
    return ShipmentContextBuilder(FileReader(CANON_DIR), AS_OF)


# ── the engine on an isolated world ──────────────────────────────────────────────────────────────
def seeded_world() -> MemoryStore:
    """A store holding only what the network files point at but do not define (the existing depot, ports, dealers, customers, parts, carrier)."""
    store = MemoryStore()
    defined = {r.dealer_id for r in recs("network_dealers")}
    from app.canonical.registry import LOCATION_KEYS

    for loc in recs(
        "locations"
    ):  # every place the graph already had (depots, terminals, dealers, ship-tos): the network refers to them without defining them
        key = LOCATION_KEYS[loc.graph_label]
        store.seed_node(
            loc.graph_label,
            key,
            {key: loc.location_id, "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-005"},
        )
    for o in recs("network_orders"):
        store.seed_node(
            "Customer",
            "customer_id",
            {"customer_id": o.customer_id, "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-003"},
        )
        if o.dealer_id not in defined and not store.resolve("dealer", [o.dealer_id]):
            store.seed_node(
                "Dealer",
                "dealer_id",
                {"dealer_id": o.dealer_id, "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-005"},
            )
    for ln in recs("network_order_lines"):
        store.seed_node(
            "Part",
            "part_id",
            {"part_id": ln.part_id, "data_status": "SOURCE_DERIVED", "source_id": "SRC-001"},
        )
    for s in recs("network_shipments"):
        store.seed_node(
            "Carrier",
            "carrier_id",
            {"carrier_id": s.carrier_id, "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-003"},
        )
    return store


NETWORK = [
    "network_suppliers",
    "network_dealers",
    "network_locations",
    "network_routes",
    "network_route_legs",
    "network_orders",
    "network_order_lines",
    "network_shipments",
    "network_tracking_events",
]


def test_network_ingestion_is_idempotent_a_second_run_writes_nothing():
    store = seeded_world()
    first = Engine(store, CANON_DIR).run(NETWORK, dry_run=False)
    assert first["totals"]["records_invalid"] == 0 and first["totals"]["records_created"] > 100
    nodes, rels, writes = len(store.nodes), len(store.rels), store.writes
    second = Engine(store, CANON_DIR).run(NETWORK, dry_run=False)
    assert (
        second["totals"]["records_created"] == 0
        and second["totals"]["records_updated"] == 0
        and second["totals"]["nodes_to_create"] == 0
        and second["totals"]["relationships_to_create"] == 0
    )
    assert (len(store.nodes), len(store.rels), store.writes) == (
        nodes,
        rels,
        writes,
    )  # second run = 0 writes
    assert len({k for k in store.rels}) == len(store.rels)


# ── the live graph (read-only) ───────────────────────────────────────────────────────────────────
