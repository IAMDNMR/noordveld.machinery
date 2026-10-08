"""ShipmentContext: everything a logistics answer needs about one shipment, assembled from data. No language model, no wording, no ranking by mode.

The builder answers two questions from records only:
  "Where is my shipment?"        -> current status, current location, route progress (completed and remaining legs), planned ETA
  "What are the options?"        -> every other recorded route between the same origin and destination, compared on the recorded days and cost

Nothing is invented. A shipment whose route could not be determined says so (route_resolution_status) and has no route progress or alternatives. There is no live
position: an event at sea or in the air has no place, and the context says so. Comparisons use the numbers on each route; no mode has a built-in duration or price.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

from app.logistics.readers import LogisticsReader
from app.logistics.rules import route_progress, sequence_errors

PROVENANCE_FIELDS = ("data_status", "source_type", "source_record_id")


def _prov(kind: str, row: dict[str, Any] | None, id_field: str) -> dict[str, Any] | None:
    if not row:
        return None
    return {"record": kind, "id": row.get(id_field), **{k: row.get(k) for k in PROVENANCE_FIELDS}}


@dataclass
class ShipmentContext:
    shipment: dict[str, Any]
    order: dict[str, Any] | None
    part: dict[str, Any] | None
    origin: dict[str, Any] | None
    destination: dict[str, Any] | None
    current_location: dict[str, Any] | None
    current_status: str | None
    events: list[dict[str, Any]]
    route: dict[str, Any] | None
    route_legs: list[dict[str, Any]]
    route_progress: dict[str, Any] | None
    planned_eta: dict[str, Any]
    alternative_routes: list[dict[str, Any]]
    transport_comparison: dict[str, Any] | None
    route_resolution_status: str
    provenance: list[dict[str, Any]] = field(default_factory=list)
    synthetic: bool = True
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ShipmentContextBuilder:
    def __init__(self, reader: LogisticsReader, today: date | None = None) -> None:
        self._r = reader
        self._today = today

    def build(self, shipment_id: str, as_of: date | None = None) -> ShipmentContext | None:
        r = self._r
        shipment = r.shipment(shipment_id)
        if shipment is None:
            return None
        today = as_of or self._today or date.today()  # noqa: DTZ011 - a calendar date; callers that need a fixed day pass as_of
        events = r.events(shipment_id)
        order = r.order(shipment["order_id"]) if shipment.get("order_id") else None
        part = r.order_part(shipment["order_line_id"]) if shipment.get("order_line_id") else None
        route = r.route(shipment["route_id"]) if shipment.get("route_id") else None
        legs = r.legs(route["route_id"]) if route else []
        origin_id = shipment.get("origin_location_id") or (route or {}).get("origin_location_id")
        destination_id = shipment.get("destination_location_id") or (route or {}).get("destination_location_id")
        origin = r.location(origin_id) if origin_id else None
        destination = r.location(destination_id) if destination_id else None
        notes: list[str] = []

        last = events[-1] if events else None
        current_status = last["event_type"] if last else shipment.get("status")
        current_location = self._current_location(last, notes)
        progress = route_progress(legs, events) if route else None
        if not route:
            notes.append(f"No route is linked to this shipment ({shipment['route_resolution_status']}); route progress and alternatives are not available.")
        if events:
            problems = sequence_errors(events)
            if problems:
                notes.append("The recorded tracking events are not a coherent sequence: " + "; ".join(problems[:3]))

        alternatives, comparison = [], None
        if route:
            alternatives = [x for x in r.routes_between(route["origin_location_id"], route["destination_location_id"]) if x["route_id"] != route["route_id"]]
            comparison = self._compare(route, alternatives)

        return ShipmentContext(
            shipment=shipment, order=order, part=part, origin=origin, destination=destination, current_location=current_location, current_status=current_status, events=events,
            route=route, route_legs=legs, route_progress=progress, planned_eta=self._eta(shipment, route, today), alternative_routes=alternatives, transport_comparison=comparison,
            route_resolution_status=shipment["route_resolution_status"], provenance=self._provenance(shipment, order, route, events, origin, destination),
            synthetic=all(p["data_status"] == "SYNTHETIC_DEMO" for p in self._provenance(shipment, order, route, events, origin, destination)), notes=notes)

    def _current_location(self, last: dict[str, Any] | None, notes: list[str]) -> dict[str, Any] | None:
        if last is None:
            return None
        if last.get("location_id"):
            loc = self._r.location(last["location_id"])
            return {"known": True, "location": loc, "as_of": last["timestamp"], "event_type": last["event_type"]}
        notes.append("There is no live position: the last event has no place (for example at sea or in flight), only a status.")
        return {"known": False, "location": None, "description": last.get("location_text"), "as_of": last["timestamp"], "event_type": last["event_type"]}

    @staticmethod
    def _eta(shipment: dict[str, Any], route: dict[str, Any] | None, today: date) -> dict[str, Any]:
        planned = shipment.get("planned_eta")
        delivered = shipment.get("actual_eta") or (shipment.get("status") == "DELIVERED")
        out: dict[str, Any] = {"planned_eta": planned, "actual_eta": shipment.get("actual_eta"), "source": "RECORDED" if planned else None, "as_of": today.isoformat(), "delivered": bool(delivered),
                               "days_to_eta": None}
        if not planned and route and shipment.get("departure_date") and route.get("planned_transit_days") is not None:
            planned = (date.fromisoformat(shipment["departure_date"]) + timedelta(days=route["planned_transit_days"])).isoformat()
            out.update(planned_eta=planned, source="DERIVED_FROM_ROUTE")
        if planned and not delivered:
            out["days_to_eta"] = (date.fromisoformat(planned[:10]) - today).days  # negative: the planned date has passed
        return out

    @staticmethod
    def _compare(current: dict[str, Any], others: list[dict[str, Any]]) -> dict[str, Any]:
        """The recorded options for this lane side by side. Differences are arithmetic on each route's own numbers: nothing depends on the mode."""
        rows = []
        for r in [current, *others]:
            d, c = r.get("planned_transit_days"), r.get("estimated_cost")
            rows.append({"route_id": r["route_id"], "transport_mode": r["transport_mode"], "service_level": r.get("service_level"), "planned_transit_days": d, "estimated_cost": c,
                         "currency": r.get("currency"), "is_current": r["route_id"] == current["route_id"],
                         "days_vs_current": (d - current["planned_transit_days"]) if d is not None and current.get("planned_transit_days") is not None else None,
                         "cost_vs_current": round(c - current["estimated_cost"], 2) if c is not None and current.get("estimated_cost") is not None else None,
                         "data_status": r.get("data_status")})
        comparable = [x for x in rows if x["planned_transit_days"] is not None and x["estimated_cost"] is not None]
        same_currency = len({x["currency"] for x in comparable}) <= 1
        return {"basis": "recorded route values for the same origin and destination (synthetic demo data unless a route says otherwise)", "options": sorted(rows, key=lambda x: (x["planned_transit_days"] is None, x["planned_transit_days"] or 0, x["route_id"])),
                "fastest_route_id": min(comparable, key=lambda x: (x["planned_transit_days"], x["estimated_cost"], x["route_id"]))["route_id"] if comparable else None,
                "lowest_cost_route_id": min(comparable, key=lambda x: (x["estimated_cost"], x["planned_transit_days"], x["route_id"]))["route_id"] if comparable and same_currency else None}

    @staticmethod
    def _provenance(shipment, order, route, events, origin, destination) -> list[dict[str, Any]]:
        out = [_prov("shipment", shipment, "shipment_id"), _prov("order", order, "order_id"), _prov("route", route, "route_id"), _prov("origin", origin, "location_id"),
               _prov("destination", destination, "location_id")]
        if events:
            out.append({"record": "tracking_events", "id": shipment["shipment_id"], "data_status": "SYNTHETIC_DEMO" if all(e.get("data_status") == "SYNTHETIC_DEMO" for e in events) else events[0].get("data_status"),
                        "source_type": events[0].get("source_type"), "source_record_id": f"{len(events)} events"})
        return [p for p in out if p]
