"""LogisticsContext: the stable contract over the Phase 2 ShipmentContext.

All logistics facts (status, location, route progress, ETA, alternatives, comparison) come from `app.logistics.context.ShipmentContextBuilder`. This module adds the common
metadata, the decision, the evidence path and the order lines, and nothing else: it never recomputes a route, a duration or a cost.

A shipment whose route could not be determined (route_resolution_status = ROUTE_NOT_DETERMINABLE) is INSUFFICIENT_DATA with requires_review = True: what is known (status, events,
order, part) is still returned, and no route, leg, ETA or alternative is invented.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.commerce import contract as c
from app.logistics.context import ShipmentContext, ShipmentContextBuilder
from app.logistics.readers import LogisticsReader

TRACKED, DELIVERED, ROUTE_NOT_DETERMINABLE, NO_SHIPMENT = "TRACKED", "DELIVERED", "ROUTE_NOT_DETERMINABLE", "NO_SHIPMENT_RECORDED"


@dataclass(kw_only=True)
class LogisticsContext(c.CommerceContext):
    order: dict[str, Any] | None = None
    order_lines: list[dict[str, Any]] = field(default_factory=list)
    shipment: dict[str, Any] | None = None
    part: dict[str, Any] | None = None
    origin: dict[str, Any] | None = None
    destination: dict[str, Any] | None = None
    current_status: str | None = None
    current_location: dict[str, Any] | None = None
    route: dict[str, Any] | None = None
    route_legs: list[dict[str, Any]] = field(default_factory=list)
    route_progress: dict[str, Any] | None = None
    completed_legs: list[dict[str, Any]] = field(default_factory=list)
    remaining_legs: list[dict[str, Any]] = field(default_factory=list)
    planned_eta: dict[str, Any] | None = None
    alternative_routes: list[dict[str, Any]] = field(default_factory=list)
    transport_comparison: dict[str, Any] | None = None
    tracking_events: list[dict[str, Any]] = field(default_factory=list)
    route_resolution_status: str | None = None
    requires_review: bool = False
    provenance: list[dict[str, Any]] = field(default_factory=list)
    clarification: dict[str, Any] | None = None


class LogisticsContextBuilder:
    def __init__(self, reader: LogisticsReader, as_of: date, generated_at: str) -> None:
        self.r = reader
        self.as_of = as_of
        self.generated_at = generated_at
        self._ship = ShipmentContextBuilder(reader, as_of)

    # ── whole contexts ───────────────────────────────────────────────────────────────────────────
    def build(self, shipment_id: str) -> LogisticsContext:
        sc = self._ship.build(shipment_id, self.as_of)
        inputs = {"shipment_id": shipment_id}
        if sc is None:
            d = c.CommerceDecision(status=c.NOT_FOUND, decision="NOT_FOUND", summary=f"No shipment {shipment_id} is recorded.", missing=["shipment"],
                                   recommended_next_action="Ask the user to check the shipment number.")
            return LogisticsContext(**c.meta("LOGISTICS", inputs, self.as_of.isoformat(), self.generated_at, d, [], [], []))
        return self._from_shipment(sc, inputs)

    def for_order_without_shipment(self, order_id: str) -> LogisticsContext:
        order = self.r.order(order_id)
        lines = self.r.order_lines(order_id)
        recs = [c.record("Order", order_id, order)] + [c.record("OrderLine", x["order_line_id"], x) for x in lines]
        d = c.CommerceDecision(status=c.NOT_FOUND, decision=NO_SHIPMENT, summary=f"Order {order_id} exists but no shipment is recorded for it yet.", facts={"order_status": (order or {}).get("status")},
                               missing=["shipment"], recommended_next_action="Tell the user the order has not shipped yet; do not estimate a delivery date.")
        return LogisticsContext(**c.meta("LOGISTICS", {"order_id": order_id}, self.as_of.isoformat(), self.generated_at, d, recs,
                                         [c.evidence_item(f"order {order_id} has status {(order or {}).get('status')} and no shipment record", "Order", order_id, order)], [c.path_step(1, "Order", order_id, "HAS_SHIPMENT", order)]),
                                order=order, order_lines=lines, provenance=c.dedupe_records(recs))

    def clarify(self, options: list[dict[str, Any]], question: str, inputs: dict[str, Any]) -> LogisticsContext:
        d = c.CommerceDecision(status=c.REQUIRES_CLARIFICATION, decision=c.REQUIRES_CLARIFICATION, summary=question, facts={"options": options}, missing=["shipment"],
                               recommended_next_action="Ask the user: " + question)
        return LogisticsContext(**c.meta("LOGISTICS", inputs, self.as_of.isoformat(), self.generated_at, d, [], [], []), clarification={"question": question, "options": options})

    # ── from the Phase 2 context ─────────────────────────────────────────────────────────────────
    def _from_shipment(self, sc: ShipmentContext, inputs: dict[str, Any]) -> LogisticsContext:
        s, order, route = sc.shipment, sc.order, sc.route
        lines = self.r.order_lines(s["order_id"]) if s.get("order_id") else []
        progress = sc.route_progress
        done = [leg for leg in sc.route_legs if progress and leg["sequence"] in progress["completed_legs"]]
        todo = [leg for leg in sc.route_legs if progress and leg["sequence"] in progress["remaining_legs"]]
        delivered = bool(sc.planned_eta["delivered"])
        missing: list[str] = []
        if route is None:
            missing += ["route", "route_progress", "alternative_routes"]
        if sc.destination is None:
            missing.append("destination")
        if not delivered and not sc.planned_eta["planned_eta"]:
            missing.append("planned_eta")
        if not sc.events:
            missing.append("tracking_events")
        warnings = list(sc.notes)
        requires_review = route is None
        records = [c.record("Shipment", s["shipment_id"], s)] + [c.record("Order", order["order_id"], order)] * bool(order) + [c.record("OrderLine", x["order_line_id"], x) for x in lines]
        if route:
            records.append(c.record("Route", route["route_id"], route))
            records += [c.record("Route", a["route_id"], a) for a in sc.alternative_routes]
        records += [c.record("Location", loc["location_id"], loc) for loc in (sc.origin, sc.destination) if loc]
        if sc.current_location and sc.current_location.get("location"):
            records.append(c.record("Location", sc.current_location["location"]["location_id"], sc.current_location["location"]))
        records += [c.record("TrackingEvent", e["tracking_event_id"], e) for e in sc.events]
        evidence = [c.evidence_item(f"shipment {s['shipment_id']} status {sc.current_status} as of its last tracking event", "TrackingEvent", sc.events[-1]["tracking_event_id"], sc.events[-1])] if sc.events else []
        if route:
            evidence.append(c.evidence_item(f"route {route['route_id']}: {route['transport_mode']}, {route['planned_transit_days']} days, {route['estimated_cost']} {route['currency']}", "Route", route["route_id"], route))
        evidence += [c.evidence_item(f"alternative route {a['route_id']}: {a['transport_mode']}, {a['planned_transit_days']} days, {a['estimated_cost']} {a['currency']}", "Route", a["route_id"], a)
                     for a in sc.alternative_routes]
        path: list[dict[str, Any]] = []
        if order:
            path.append(c.path_step(len(path) + 1, "Order", order["order_id"], "HAS_SHIPMENT", order))
        path.append(c.path_step(len(path) + 1, "Shipment", s["shipment_id"], "USES_ROUTE" if route else "HAS_TRACKING_EVENT", s))
        if route:
            path.append(c.path_step(len(path) + 1, "Route", route["route_id"], "HAS_TRACKING_EVENT", route))
        if sc.events:
            path.append(c.path_step(len(path) + 1, "TrackingEvent", sc.events[-1]["tracking_event_id"], None, sc.events[-1]))

        facts: dict[str, Any] = {"shipment_status": s.get("status"), "current_status": sc.current_status, "route_resolution_status": sc.route_resolution_status, "delivered": delivered,
                                 "completed_leg_count": len(done) if progress else None, "remaining_leg_count": len(todo) if progress else None, "position": progress["position"] if progress else None,
                                 "planned_eta": sc.planned_eta["planned_eta"], "eta_source": sc.planned_eta["source"], "days_to_eta": sc.planned_eta["days_to_eta"],
                                 "current_location_known": bool(sc.current_location and sc.current_location["known"]) if sc.current_location else None,
                                 "alternatives": [{"route_id": o["route_id"], "transport_mode": o["transport_mode"], "planned_transit_days": o["planned_transit_days"], "estimated_cost": o["estimated_cost"],
                                                   "currency": o["currency"], "days_vs_current": o["days_vs_current"], "cost_vs_current": o["cost_vs_current"]}
                                                  for o in (sc.transport_comparison or {}).get("options", []) if not o["is_current"]],
                                 "fastest_route_id": (sc.transport_comparison or {}).get("fastest_route_id"), "lowest_cost_route_id": (sc.transport_comparison or {}).get("lowest_cost_route_id")}
        if route is None:
            decision = c.CommerceDecision(
                status=c.INSUFFICIENT_DATA, decision=ROUTE_NOT_DETERMINABLE, summary=f"Shipment {s['shipment_id']} is recorded as {sc.current_status}, but its route could not be determined from the records, "
                "so route progress, ETA and alternatives are not available.", facts=facts, reasons=[f"route_resolution_status = {sc.route_resolution_status}"] + [f"remediation flag: {f}" for f in s.get("remediation_flags", [])],
                evidence=evidence, missing=missing, warnings=warnings, recommended_next_action="Say what is known (status, events, order, part); route the question to a person who can resolve the route. Do not estimate a route or a date.")
        else:
            decision = c.CommerceDecision(
                status=c.SUCCESS, decision=DELIVERED if delivered else TRACKED,
                summary=(f"Shipment {s['shipment_id']} was delivered." if delivered else f"Shipment {s['shipment_id']} is {sc.current_status} on route {route['route_id']}: "
                         f"{len(done)} of {len(sc.route_legs)} legs completed, planned ETA {sc.planned_eta['planned_eta']}."), facts=facts,
                reasons=[f"route progress is read from tracking events against the legs of {route['route_id']}"], evidence=evidence, missing=missing, warnings=warnings,
                recommended_next_action="Explain status, remaining legs and ETA from the facts; mention alternatives only as recorded options with their recorded time and cost.")
        return LogisticsContext(
            **c.meta("LOGISTICS", inputs, self.as_of.isoformat(), self.generated_at, decision, records, evidence, path), order=order, order_lines=lines, shipment=s, part=sc.part, origin=sc.origin,
            destination=sc.destination, current_status=sc.current_status, current_location=sc.current_location, route=route, route_legs=sc.route_legs, route_progress=progress, completed_legs=done,
            remaining_legs=todo, planned_eta=sc.planned_eta, alternative_routes=sc.alternative_routes, transport_comparison=sc.transport_comparison, tracking_events=sc.events,
            route_resolution_status=sc.route_resolution_status, requires_review=requires_review, provenance=c.dedupe_records(records))
