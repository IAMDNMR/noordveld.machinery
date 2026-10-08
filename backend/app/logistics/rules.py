"""Tracking and route-progress rules. Workflow rules in the same spirit as order_flow.py: they say which event can follow which, never what a lane costs or
how long it takes (that is route data).

Tracking is a list of DISCRETE events. There is no live position: an event at sea or in the air has no location_id, only a status.

Route progress
  A leg is COMPLETED when the shipment has an arrival event (ARRIVED_PORT, ARRIVED_DC or DELIVERED) at the leg's destination location.
  Position: all legs completed -> delivered. Otherwise the first incomplete leg is the CURRENT leg; the shipment is `on_leg` while the last event is a
  departure, transit or out-for-delivery event, and `at_location` while the last event is an arrival or customs event.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import pairwise
from typing import Any

TRANSITIONS: dict[str, frozenset[str]] = {
    "ORDER_CONFIRMED": frozenset({"BOOKED"}),
    "BOOKED": frozenset({"DEPARTED_ORIGIN"}),
    "DEPARTED_ORIGIN": frozenset({"IN_TRANSIT", "ARRIVED_PORT", "ARRIVED_DC", "OUT_FOR_DELIVERY", "DELIVERED"}),
    "ARRIVED_PORT": frozenset({"CUSTOMS", "DEPARTED_PORT", "ARRIVED_DC"}),
    "CUSTOMS": frozenset({"DEPARTED_PORT", "ARRIVED_DC", "OUT_FOR_DELIVERY"}),
    "DEPARTED_PORT": frozenset({"IN_TRANSIT", "ARRIVED_PORT", "ARRIVED_DC", "OUT_FOR_DELIVERY"}),
    "IN_TRANSIT": frozenset({"IN_TRANSIT", "ARRIVED_PORT", "ARRIVED_DC", "OUT_FOR_DELIVERY", "DELIVERED"}),
    "ARRIVED_DC": frozenset({"DEPARTED_ORIGIN", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED"}),
    "OUT_FOR_DELIVERY": frozenset({"DELIVERED"}),
    "DELIVERED": frozenset(),
    # the seeded shipments' own, shorter lifecycle
    "PICKED": frozenset({"IN_TRANSIT", "DELIVERED"}),
}
FIRST_EVENTS = frozenset({"ORDER_CONFIRMED", "PICKED"})
ARRIVAL_TYPES = frozenset({"ARRIVED_PORT", "ARRIVED_DC", "DELIVERED"})
MOVING_TYPES = frozenset({"DEPARTED_ORIGIN", "DEPARTED_PORT", "IN_TRANSIT", "OUT_FOR_DELIVERY"})
AT_SEA_OR_IN_FLIGHT = frozenset({"IN_TRANSIT"})  # the only status that may have no location: there is no live position


def sequence_errors(events: list[dict[str, Any]]) -> list[str]:
    """Why a shipment's events are impossible, or [] when they are coherent. `events`: dicts with timestamp, event_type, location_id, sequence (any order given)."""
    if not events:
        return []
    ordered = sorted(events, key=lambda e: (e.get("sequence") if e.get("sequence") is not None else 0, e["timestamp"]))
    errors: list[str] = []
    if ordered[0]["event_type"] not in FIRST_EVENTS:
        errors.append(f"starts with {ordered[0]['event_type']}")
    seqs = [e.get("sequence") for e in ordered if e.get("sequence") is not None]
    if len(seqs) != len(set(seqs)):
        errors.append("duplicate sequence numbers")
    for prev, nxt in pairwise(ordered):
        if nxt["timestamp"] < prev["timestamp"]:
            errors.append(f"{nxt['event_type']} is dated before {prev['event_type']}")
        if nxt["event_type"] not in TRANSITIONS.get(prev["event_type"], frozenset()):
            errors.append(f"{nxt['event_type']} cannot follow {prev['event_type']}")
    for e in ordered:
        if not e.get("location_id") and e["event_type"] not in AT_SEA_OR_IN_FLIGHT and not e.get("location_text"):
            errors.append(f"{e['event_type']} has no location")
    return errors


def tracking_group_check(records: list[Any]) -> dict[str, str]:
    """Engine hook: records of one tracking dataset -> {tracking_event_id: reason} for every event of a shipment whose sequence is impossible."""
    by_shipment: dict[str, list[Any]] = defaultdict(list)
    for r in records:
        by_shipment[r.shipment_id].append(r)
    bad: dict[str, str] = {}
    for shipment, evs in by_shipment.items():
        errs = sequence_errors([{"timestamp": e.timestamp, "event_type": e.event_type, "location_id": e.location_id, "location_text": e.location_text, "sequence": e.sequence} for e in evs])
        if errs:
            for e in evs:
                bad[e.tracking_event_id] = f"impossible event sequence for {shipment}: {'; '.join(errs[:3])}"
    return bad


def route_progress(legs: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Where a shipment is on its route, from discrete events only. `legs`: sequence, origin_location_id, destination_location_id (any order);
    `events`: timestamp, event_type, location_id, sequence."""
    legs = sorted(legs, key=lambda leg: leg["sequence"])
    evs = sorted(events, key=lambda e: (e.get("sequence") if e.get("sequence") is not None else 0, e["timestamp"]))
    arrived = {e["location_id"] for e in evs if e["event_type"] in ARRIVAL_TYPES and e.get("location_id")}
    completed: list[dict[str, Any]] = []
    for leg in legs:
        if leg["destination_location_id"] in arrived:
            completed.append(leg)
        else:
            break  # legs complete in order: a later arrival does not complete an earlier unfinished leg
    remaining = legs[len(completed):]
    last = evs[-1] if evs else None
    out: dict[str, Any] = {"legs_total": len(legs), "completed_legs": [leg["sequence"] for leg in completed], "remaining_legs": [leg["sequence"] for leg in remaining],
                           "current_leg": remaining[0]["sequence"] if remaining else None, "last_event_type": last["event_type"] if last else None,
                           "last_event_location_id": last.get("location_id") if last else None}
    if not legs:
        out["position"] = "no_route"
    elif not evs:
        out["position"] = "not_started"
    elif not remaining:
        out["position"] = "delivered"
    elif last["event_type"] in MOVING_TYPES:
        out["position"] = "on_leg"
    elif last["event_type"] in ARRIVAL_TYPES or last["event_type"] == "CUSTOMS":
        out["position"] = "at_location"
    else:
        out["position"] = "not_started"  # confirmed or booked, not yet departed
    return out
