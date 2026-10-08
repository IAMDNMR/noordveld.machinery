"""CommerceContextEngine: the one abstraction behind the three journeys.

    engine.build_discovery_context(...)   DiscoveryReader  + discovery rules (app/commerce/discovery.py)
    engine.build_logistics_context(...)   LogisticsReader  + Phase 2 ShipmentContextBuilder
    engine.build_warranty_context(...)    LifecycleReader  + Phase 3 evaluator (rules.evaluate)

Order of work for every call: (1) who is asking -> (2) may they read this record (AccessPolicy, on the records) -> (3) build the context from the graph facts and the
deterministic rules -> (4) apply the role's visibility. A refused request never reaches step 3. No language model is involved at any step.

Readers are injected: `from_files` runs on the canonical dataset files (tests, offline), `from_graph` on the Neo4j graph (read-only). Both give the same answers (the
Phase 1-3 suites check files == graph for the readers).
"""
from __future__ import annotations

import copy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.canonical.io import CANON_DIR
from app.commerce import contract as c
from app.commerce.access import AccessPolicy, CommerceRole, Principal, apply_visibility
from app.commerce.discovery import DiscoveryContext, DiscoveryContextBuilder
from app.commerce.discovery_reader import DiscoveryReader, FileDiscoveryReader, GraphDiscoveryReader
from app.commerce.logistics import LogisticsContext, LogisticsContextBuilder
from app.commerce.warranty import WarrantyContext, WarrantyContextAssembler
from app.graph.client import GraphClient
from app.lifecycle.readers import FileReader as FileLifecycleReader
from app.lifecycle.readers import GraphReader as GraphLifecycleReader
from app.lifecycle.readers import LifecycleReader
from app.logistics.readers import FileReader as FileLogisticsReader
from app.logistics.readers import GraphReader as GraphLogisticsReader
from app.logistics.readers import LogisticsReader


class CommerceContextEngine:
    def __init__(self, discovery: DiscoveryReader, logistics: LogisticsReader, lifecycle: LifecycleReader, *, as_of: date | None = None,
                 clock: Callable[[], datetime] | None = None) -> None:
        self.discovery, self.logistics, self.lifecycle = discovery, logistics, lifecycle
        self._as_of, self._clock = as_of, clock
        self.access = AccessPolicy(logistics, lifecycle)

    @classmethod
    def from_files(cls, root: Path = CANON_DIR, **kw: Any) -> CommerceContextEngine:
        return cls(FileDiscoveryReader(root), FileLogisticsReader(root), FileLifecycleReader(root), **kw)

    @classmethod
    def from_graph(cls, graph: GraphClient, **kw: Any) -> CommerceContextEngine:
        return cls(GraphDiscoveryReader(graph), GraphLogisticsReader(graph), GraphLifecycleReader(graph), **kw)

    # ── time: the reference day is explicit, and generated_at follows it when the engine is pinned ──
    def _today(self) -> date:
        return self._as_of or datetime.now(timezone.utc).date()

    def _generated_at(self) -> str:
        if self._clock:
            return c.now_iso(self._clock)
        if self._as_of:
            return f"{self._as_of.isoformat()}T00:00:00Z"
        return c.now_iso()

    def _scoped(self, ctx: Any, principal: Principal) -> Any:
        """Role visibility on a copy (the readers hand out shared rows, so nothing is changed in place)."""
        if principal.role == CommerceRole.OEM:
            ctx.visibility = {"role": principal.role.value, "hidden_fields": []}
            return ctx
        scoped = copy.deepcopy(ctx)
        apply_visibility(principal, ctx.context_type, vars(scoped))
        return scoped

    # ── discovery ────────────────────────────────────────────────────────────────────────────────
    def build_discovery_context(self, request: str, *, principal: Principal | None = None, machine_id: str | None = None, machine_instance_id: str | None = None,
                                destination_country: str | None = None) -> DiscoveryContext:
        p = principal or Principal.system()
        instance_machine = None
        if machine_instance_id:
            instance = self.lifecycle.instance(machine_instance_id)
            self.access.instance(p, instance)  # authorization before any context is built
            instance_machine = instance["machine_id"] if instance else None
            if instance is None:  # only an OEM principal gets here for a missing instance
                return self._scoped(self._discovery_not_found(request, machine_instance_id), p)
        customer_country = None
        if p.role == CommerceRole.END_CUSTOMER and p.customer_id:
            cust = self.discovery.customer(p.customer_id)
            customer_country = cust["country_code"] if cust else None
        builder = DiscoveryContextBuilder(self.discovery, self._today(), self._generated_at())
        ctx = builder.build(request, machine_id=machine_id, instance_machine_id=instance_machine, destination_country=destination_country, customer_country=customer_country)
        return self._scoped(ctx, p)

    def _discovery_not_found(self, request: str, machine_instance_id: str) -> DiscoveryContext:
        d = c.CommerceDecision(status=c.NOT_FOUND, decision="NO_VALID_RECOMMENDATION", summary=f"No machine instance {machine_instance_id} is recorded.", missing=["machine"])
        return DiscoveryContext(**c.meta("DISCOVERY", {"request": request, "machine_instance_id": machine_instance_id}, self._today().isoformat(), self._generated_at(), d, [], [], []),
                                user_request=request, machine={"resolution": "NOT_FOUND", "via": "machine_instance"})

    # ── logistics ────────────────────────────────────────────────────────────────────────────────
    def build_logistics_context(self, *, principal: Principal | None = None, shipment_id: str | None = None, order_id: str | None = None) -> LogisticsContext:
        p = principal or Principal.system()
        b = LogisticsContextBuilder(self.logistics, self._today(), self._generated_at())
        if shipment_id:
            shipment = self.logistics.shipment(shipment_id)
            self.access.shipment(p, shipment)
            return self._scoped(b.build(shipment_id), p)
        if order_id:
            order = self.logistics.order(order_id)
            self.access.order(p, order, None)
            if order is None:
                return self._order_not_found(order_id)
            ships = [s for s in self.logistics.shipments_of_order(order_id) if p.role != CommerceRole.DEALER or p.dealer_id in (order.get("dealer_id"), s.get("destination_location_id"))]
            if not ships:
                return self._scoped(b.for_order_without_shipment(order_id), p)
            if len(ships) == 1:
                return self._scoped(b.build(ships[0]["shipment_id"]), p)
            return self._scoped(b.clarify(self._options(ships), f"Order {order_id} has {len(ships)} shipments. Which one do you mean?", {"order_id": order_id}), p)
        if p.role == CommerceRole.END_CUSTOMER and p.customer_id:  # "where is my shipment?": the customer's own shipments only
            ships = [s for o in self.logistics.orders_of_customer(p.customer_id) for s in self.logistics.shipments_of_order(o)]
            open_ = [s for s in ships if s.get("status") != "DELIVERED"]
            if len(open_) == 1:
                return self._scoped(b.build(open_[0]["shipment_id"]), p)
            if not open_:
                d = c.CommerceDecision(status=c.NOT_FOUND, decision="NO_OPEN_SHIPMENT", summary="There is no shipment in progress on this account.", missing=["shipment"])
                return self._scoped(LogisticsContext(**c.meta("LOGISTICS", {"customer_id": p.customer_id}, self._today().isoformat(), self._generated_at(), d, [], [], [])), p)
            return self._scoped(b.clarify(self._options(open_), f"{len(open_)} shipments are in progress. Which one do you mean?", {"customer_id": p.customer_id}), p)
        return self._scoped(b.clarify([], "Which shipment or order do you mean? Give a shipment or order number.", {}), p)

    def _order_not_found(self, order_id: str) -> LogisticsContext:
        d = c.CommerceDecision(status=c.NOT_FOUND, decision="NOT_FOUND", summary=f"No order {order_id} is recorded.", missing=["order"])
        return LogisticsContext(**c.meta("LOGISTICS", {"order_id": order_id}, self._today().isoformat(), self._generated_at(), d, [], [], []))

    def _options(self, shipments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for s in sorted(shipments, key=lambda x: x["shipment_id"]):
            part = self.logistics.order_part(s["order_line_id"]) if s.get("order_line_id") else None
            out.append({"shipment_id": s["shipment_id"], "order_id": s.get("order_id"), "status": s.get("status"), "transport_mode": s.get("transport_mode"),
                        "part_number": (part or {}).get("part_number"), "part_name": (part or {}).get("name")})
        return out

    # ── warranty ─────────────────────────────────────────────────────────────────────────────────
    def build_warranty_context(self, *, principal: Principal | None = None, claim_id: str | None = None, machine_instance_id: str | None = None,
                               part_id: str | None = None) -> WarrantyContext:
        p = principal or Principal.system()
        a = WarrantyContextAssembler(self.lifecycle, self._today(), self._generated_at())
        if claim_id:
            self.access.claim(p, self.lifecycle.claim(claim_id))
            return self._scoped(a.for_claim(claim_id), p)
        if machine_instance_id and part_id:
            self.access.instance(p, self.lifecycle.instance(machine_instance_id))
            return self._scoped(a.for_part(machine_instance_id, part_id), p)
        options = self._warranty_options(p)
        return self._scoped(a.clarify("Which claim, or which machine and part, do you mean?", options, {}), p)

    def _warranty_options(self, p: Principal) -> list[dict[str, Any]]:
        """What the asker may choose from: an end customer sees only their own machines; a dealer only the ones they serviced; OEM none (it must name one)."""
        if p.role != CommerceRole.END_CUSTOMER or not p.customer_id:
            return []
        out = []
        for mid in self.lifecycle.instance_ids():
            inst = self.lifecycle.instance(mid)
            if inst and inst.get("owner_id") == p.customer_id:
                out.append({"machine_instance_id": mid, "machine_id": inst["machine_id"], "installed_part_ids": sorted({i["part_id"] for i in self.lifecycle.installations(mid)})})
        return out
