"""The order workflow for the two roles. An End User places and follows their own direct orders and can cancel one early; the Order Processor
runs the queue and advances each order through its lifecycle. Ownership and permissions are checked here as well as at the route.

Two channels share one status vocabulary (OrderStatus nodes):
  * DIRECT_ORDER   - orders placed through the Parts Store checkout. Lifecycle rules: app/services/order_flow.py (actions, not free status edits).
                     Placing the order and reserving its stock are in app/services/checkout.py.
  * earlier demo orders (DEMO_WEB_STORE, DEMO_APP_REQUEST) keep their forward-only flow, NEW -> CONFIRMED -> PROCESSING -> ALLOCATED -> SHIPPED -> DELIVERED,
    each step allowed only when the graph supports it (see _gate). Their stock is never changed.
Every change writes an OrderStatusEvent with the user, role, previous status and time. Historical events are never touched.
No payment exists in this demo; part cost and transportation cost are 'Not available' (no real pricing source is connected).
"""
from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.roles import Role, allowed
from app.graph.client import GraphClient
from app.graph.queries import orders as q
from app.graph.repositories.fulfilment import GraphFulfilmentRepository, ReservationFailed, Stale
from app.graph.repositories.parts import PartRepository
from app.services import order_flow as flow
from app.services.fulfilment import cost_block
from app.services.parts import to_summary

FLOW = ["NEW", "CONFIRMED", "PROCESSING", "ALLOCATED", "SHIPPED", "DELIVERED"]  # the earlier channels
TRANSITIONS: dict[str, str] = {a: b for a, b in zip(FLOW, FLOW[1:])}
LABEL = {**{"NEW": "Pending review", "CONFIRMED": "Confirmed", "PROCESSING": "Processing", "ALLOCATED": "Allocated", "SHIPPED": "Shipped", "DELIVERED": "Delivered"}}
DIRECT_LABEL = flow.LABEL
QUEUE = {  # the processor's work queue sections, in workflow order: earlier-channel orders ...
    "pending_review": ["NEW"],
    "needs_fulfilment": ["CONFIRMED", "PROCESSING"],
    "ready_to_ship": ["ALLOCATED"],
    "shipped": ["SHIPPED"],
    "completed": ["DELIVERED"],
}
DIRECT_QUEUE = {  # ... and direct orders (an order placed through checkout is allocated on placement, so NEW means allocation is still to happen)
    "pending_review": ["NEW", "ALLOCATION_FAILED", "ALLOCATION_RELEASED"],
    "needs_fulfilment": ["ALLOCATED", "FULFILMENT_PENDING", "FULFILLING"],
    "ready_to_ship": ["READY_TO_SHIP"],
    "shipped": ["SHIPPED", "DELIVERED"],
    "completed": ["COMPLETED"],
    "exceptions": ["REJECTED", "CANCELLED", "SHIPMENT_EXCEPTION", "DELIVERY_FAILED", "SERVICE_CANCELLED"],
}


def queue_for(status: str, channel: str | None) -> str:
    table = DIRECT_QUEUE if channel == flow.DIRECT else QUEUE
    return next((k for k, v in table.items() if status in v), "other")


SYSTEM = {"id": "system", "name": "System", "role": "SYSTEM"}


def label_for(status: str, channel: str | None) -> str:
    """Direct orders use the direct vocabulary; earlier orders keep their own labels (NEW is 'Pending review' there, 'Order placed' here)."""
    if channel == flow.DIRECT:
        return DIRECT_LABEL.get(status, status)
    return LABEL.get(status) or DIRECT_LABEL.get(status, status)


@dataclass(frozen=True)
class User:
    id: str
    name: str
    email: str
    role: Role
    customer_id: str | None = None
    customer_name: str | None = None

    def can(self, permission: str) -> bool:
        return allowed(self.role, permission)


class Forbidden(Exception):
    """The user's role or ownership does not allow this (HTTP 403)."""


class Missing(Exception):
    """No such order (HTTP 404)."""


class TransitionError(Exception):
    """The status change is not a valid next step, or the graph does not support it yet (HTTP 409)."""

    def __init__(self, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class OrdersRepository(Protocol):
    def user(self, user_id: str) -> dict[str, Any] | None: ...
    def users(self) -> list[dict[str, Any]]: ...
    def orders(self, user_id: str, customer_id: str | None, everything: bool) -> list[dict[str, Any]]: ...
    def owner(self, order_id: str) -> dict[str, Any] | None: ...
    def detail(self, order_id: str) -> dict[str, Any] | None: ...
    def status_event(self, **params: Any) -> bool: ...
    def allocate(self, order_line_id: str, warehouse_id: str, today: str) -> None: ...
    def cart(self, cart_id: str) -> list[dict[str, Any]]: ...
    def put_cart(self, **params: Any) -> None: ...
    def clear_cart(self, cart_id: str) -> None: ...
    def parts(self, part_ids: list[str]) -> list[Any]: ...
    def machine_fits(self, pairs: list[dict[str, str]]) -> list[dict[str, Any]]: ...
    def transition(self, order_id: str, previous: str, status: str, action: str, *, actor: dict[str, str], at: str, today: str, effects: list[tuple[str, dict]]) -> dict[str, Any]: ...
    # checkout reads and order creation (see GraphFulfilmentRepository)
    def countries(self) -> list[dict[str, Any]]: ...
    def destinations(self, country_code: str) -> list[dict[str, Any]]: ...
    def shipto(self, shipto_id: str) -> dict[str, Any] | None: ...
    def dealers(self, country_code: str | None) -> list[dict[str, Any]]: ...
    def dealer(self, dealer_id: str) -> dict[str, Any] | None: ...
    def dealer_installs(self, dealer_id: str, part_ids: list[str]) -> dict[str, bool]: ...
    def depot_stock(self, part_ids: list[str]) -> list[dict[str, Any]]: ...
    def routes(self, depots: list[str], shipto_id: str) -> list[dict[str, Any]]: ...
    def route(self, route_id: str) -> dict[str, Any] | None: ...
    def order_by_key(self, key: str) -> str | None: ...
    def create_order(self, **params: Any) -> str: ...
    def remove_cart_lines(self, cart_id: str, keys: list[dict[str, Any]]) -> None: ...


class GraphOrdersRepository(GraphFulfilmentRepository):
    def __init__(self, graph: GraphClient) -> None:
        super().__init__(graph)
        self._parts = PartRepository(graph)

    def user(self, user_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.USER, user_id=user_id)
        return rows[0] if rows else None

    def users(self) -> list[dict[str, Any]]:
        return self._g.read(q.USERS)

    def orders(self, user_id: str, customer_id: str | None, everything: bool) -> list[dict[str, Any]]:
        return self._g.read(q.ORDER_LIST, user_id=user_id, customer_id=customer_id, all=everything)

    def owner(self, order_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.ORDER_OWNER, order_id=order_id)
        return rows[0] if rows and rows[0]["status"] is not None else None

    def detail(self, order_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.ORDER_DETAIL, order_id=order_id)
        return rows[0] if rows and rows[0]["o"] is not None else None

    def status_event(self, **params: Any) -> bool:
        return bool(self._g.write(q.STATUS_EVENT, **params))

    def allocate(self, order_line_id: str, warehouse_id: str, today: str) -> None:
        self._g.write(q.ALLOCATE_LINE, order_line_id=order_line_id, warehouse_id=warehouse_id, today=today)

    def cart(self, cart_id: str) -> list[dict[str, Any]]:
        return self._g.read(q.CART_GET, cart_id=cart_id)

    def put_cart(self, **params: Any) -> None:
        self._g.write(q.CART_PUT, **params)

    def clear_cart(self, cart_id: str) -> None:
        self._g.write(q.CART_CLEAR, cart_id=cart_id)

    def parts(self, part_ids: list[str]) -> list[Any]:
        return [to_summary(r) for r in self._parts.summaries(part_ids)]


def _today() -> str:
    return dt.date.today().isoformat()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _active_shipment(statuses: list[str | None]) -> str | None:
    live = [s for s in statuses if s and s not in ("CANCELLED", "DELIVERY_FAILED")]
    return live[-1] if live else None


class OrdersService:
    def __init__(self, repo: OrdersRepository) -> None:
        self._repo = repo

    # ── who is asking ──────────────────────────────────────────────────────────────────────────
    def user(self, user_id: str | None) -> User | None:
        row = self._repo.user(user_id) if user_id else None
        if not row or row.get("role") not in Role.__members__:
            return None
        return User(id=row["id"], name=row["name"], email=row["email"], role=Role(row["role"]), customer_id=row.get("customer_id"), customer_name=row.get("customer_name"))

    def demo_users(self) -> list[dict[str, Any]]:
        return self._repo.users()

    # ── reading ────────────────────────────────────────────────────────────────────────────────
    def list(self, user: User) -> list[dict[str, Any]]:
        if user.can("orders.read"):
            rows = self._repo.orders(user.id, None, True)
        elif user.can("orders.read_own"):
            rows = self._repo.orders(user.id, user.customer_id, False)
        else:
            raise Forbidden("This account has no orders to show.")
        out = []
        for r in rows:
            lines = [l for l in r["lines"] if l]
            direct = r.get("channel") == flow.DIRECT
            item = {"order_id": r["order_id"], "order_date": r["order_date"], "status": r["status"], "status_label": label_for(r["status"], r.get("channel")),
                    "parts": [f"{l['part_number']} × {l['quantity']}" for l in lines], "fits": sorted({m for l in lines for m in l["fits"]} | {l["machine"] for l in lines if l.get("machine")}),
                    "total": None if direct else _total(r), "currency": r.get("currency") or "EUR", "channel": r.get("channel"),
                    "fulfilment": _direct_fulfilment_text(r) if direct else _fulfilment_summary(lines, r.get("shipments") or []), "data_status": r.get("data_status")}
            if direct:
                item |= {"dealer": r.get("dealer"), "depot": r.get("depot")}
            if user.can("orders.read"):
                item |= {"customer": r["customer_name"], "queue": queue_for(r["status"], r.get("channel"))}
            out.append(item)
        return out

    def _authorise(self, user: User, order_id: str) -> dict[str, Any]:
        owner = self._repo.owner(order_id)
        if owner is None:
            raise Missing(order_id)
        if user.can("orders.read"):
            return owner
        mine = user.can("orders.read_own") and ((owner.get("user_id") and owner["user_id"] == user.id) or (owner.get("customer_id") and owner["customer_id"] == user.customer_id))
        if not mine:
            raise Forbidden("This order belongs to another customer.")
        return owner

    @staticmethod
    def _is_owner(user: User, owner: dict[str, Any]) -> bool:
        return bool((owner.get("user_id") and owner["user_id"] == user.id) or (owner.get("customer_id") and owner["customer_id"] == user.customer_id))

    @staticmethod
    def _ctx(owner: dict[str, Any]) -> dict[str, Any]:
        return {"status": owner["status"], "channel": owner.get("channel"), "allocation_status": owner.get("allocation_status"),
                "service_required": bool(owner.get("service_required")), "service_status": owner.get("service_status"),
                "shipment_status": _active_shipment(owner.get("shipment_statuses") or [])}

    def detail(self, user: User, order_id: str) -> dict[str, Any]:
        owner = self._authorise(user, order_id)
        d = self._repo.detail(order_id)
        if d is None:
            raise Missing(order_id)
        o, lines, shipments = d["o"], d["lines"] or [], d["shipments"] or []
        processor = user.can("orders.process")
        direct = o.get("channel") == flow.DIRECT
        history = sorted(d["history"] or [], key=lambda e: e.get("sequence") or 0)
        status = o["order_status"]
        result = {
            "order_id": o["order_id"], "order_date": o.get("order_date"), "status": status, "status_label": label_for(status, o.get("channel")),
            "channel": o.get("channel"), "currency": o.get("currency") or "EUR", "data_status": o.get("data_status"),
            "totals": {"subtotal_ex_vat": o.get("subtotal_ex_vat"), "shipping_ex_vat": o.get("shipping_ex_vat"), "vat_amount": o.get("vat_amount"),
                       "total_incl_vat": o.get("order_total_incl_vat"), "note": o.get("pricing_note")},
            "lines": [_line(l, processor) for l in sorted(lines, key=lambda l: l.get("line_no") or 0)],
            "shipments": [{**s, "events": sorted(s.get("events") or [], key=lambda e: e.get("event_seq") or 0)} for s in sorted(shipments, key=lambda s: s.get("shipment_id") or "")],
            "history": [{"sequence": e.get("sequence"), "status": e.get("order_status"), "status_label": label_for(e.get("order_status") or "", o.get("channel")),
                         "previous_status": e.get("previous_status"), "action": e.get("action"), "occurred_at": e.get("occurred_at"),
                         "by": e.get("actor_name") if processor else (None if e.get("actor_role") == Role.ORDER_PROCESSOR.value else e.get("actor_name")),
                         "role": e.get("actor_role"), "recorded": e.get("data_status")} for e in history],
            "payment": ("No payment is taken in this demo store and none has been taken. Part and transportation cost are not available (no pricing source is connected)."
                        if direct else "Order placement and payment are not connected in this demo. No payment has been taken."),
        }
        if direct:
            ctx = self._ctx({**owner, "status": status})
            result |= self._direct_sections(o, d, lines, shipments, ctx)
            result["stages"] = flow.stages(ctx)
            result["actions"] = flow.available_actions(ctx, is_processor=processor, is_owner=self._is_owner(user, owner))
        if processor:
            result["customer"] = d["customer"] or ({"customer_id": None, "name": o.get("requester_company") or o.get("requester_name"), "city": None, "country_code": None} if direct else None)
            result["delivery_address"] = d.get("address")
            if not direct:
                result["next"] = self._next(status, lines, shipments)
        return result

    @staticmethod
    def _direct_sections(o: dict[str, Any], d: dict[str, Any], lines: list[dict[str, Any]], shipments: list[dict[str, Any]], ctx: dict[str, Any]) -> dict[str, Any]:
        service = d.get("service")
        return {
            "requester": {"name": o.get("requester_name"), "email": o.get("requester_email"), "phone": o.get("requester_phone"), "company": o.get("requester_company")},
            "delivery": {"ship_to_id": (d.get("ship_to") or {}).get("shipto_id"), "street": o.get("delivery_street"), "city": o.get("delivery_city"),
                         "postal_code": o.get("delivery_postal_code"), "country_code": o.get("delivery_country_code")},
            "receiver": {"name": o.get("receiver_name"), "phone": o.get("receiver_phone")},
            "dealer": d.get("dealer"), "dealer_service_required": bool(o.get("dealer_service_required")),
            "fulfilment": {"depot": d.get("depot"), "allocation_status": o.get("allocation_status"), "allocation_updated_at": o.get("allocation_updated_at"),
                           "lines": [{"part_number": l["part_number"], "quantity": l["quantity"], "reserved_quantity": l.get("reserved_quantity"), "allocation_status": l.get("allocation_status"),
                                      "machine": l.get("machine_model")} for l in lines]},
            "transport": {"route_id": o.get("transport_route_id"), "option_code": o.get("transport_option_code"), "mode": o.get("transport_mode"),
                          "distance_km": o.get("transport_distance_km"), "estimated_days": o.get("transport_estimated_days"), "estimate_basis": o.get("transport_estimate_basis"),
                          "data_status": o.get("transport_data_status"),
                          "freight_estimate": None if o.get("freight_estimate_amount") is None else {"amount": o["freight_estimate_amount"], "currency": o.get("freight_estimate_currency") or "EUR",
                                                                                                    "data_status": o.get("freight_estimate_status"), "label": "Synthetic demo freight estimate, not a price"}},
            "cost": {**cost_block(), "part_cost": o.get("part_cost"), "transport_cost": o.get("transport_cost"), "total": o.get("order_total"), "status": o.get("cost_status") or "NOT_AVAILABLE"},
            "service": service,
            "provenance": {"order": o.get("data_status"), "transport": o.get("transport_data_status"), "tracking": "SYNTHETIC_DEMO", "inventory": "SYNTHETIC_DEMO"},
        }

    def _next(self, status: str, lines: list[dict[str, Any]], shipments: list[dict[str, Any]]) -> dict[str, Any] | None:
        """The one valid next status of an earlier-channel order and whether the graph supports it now."""
        target = TRANSITIONS.get(status)
        if not target:
            return None
        blocked = _gate(target, lines, shipments)
        return {"status": target, "label": LABEL[target], "allowed": blocked is None, "reason": blocked}

    # ── changing: earlier-channel orders ───────────────────────────────────────────────────────
    def update_status(self, user: User, order_id: str, target: str, expected: str | None = None) -> dict[str, Any]:
        if not user.can("orders.update_status"):
            raise Forbidden("Only an Order Processor can change an order's status.")
        owner = self._authorise(user, order_id)
        if owner.get("channel") == flow.DIRECT:
            raise TransitionError("use_actions", "A direct order moves through its lifecycle actions, not free status changes.")
        current = owner["status"]
        if expected and expected != current:
            raise TransitionError("stale_status", f"The order is now {LABEL.get(current, current)}; reload before changing it.")
        if target not in LABEL:
            raise TransitionError("invalid_status", f"{target} is not an order status.")
        if TRANSITIONS.get(current) != target:
            nxt = TRANSITIONS.get(current)
            raise TransitionError("invalid_transition", f"{LABEL.get(current, current)} cannot move to {LABEL[target]}." + (f" The next step is {LABEL[nxt]}." if nxt else " This order is complete."))
        d = self._repo.detail(order_id) or {}
        lines, shipments = d.get("lines") or [], d.get("shipments") or []
        blocked = _gate(target, lines, shipments)
        if blocked:
            raise TransitionError("transition_blocked", blocked)
        today = _today()
        if target == "ALLOCATED":
            for l in lines:
                if not l.get("allocated_from"):
                    self._repo.allocate(l["order_line_id"], _warehouse_for(l)["warehouse_id"], today)  # type: ignore[index]
        ok = self._repo.status_event(order_id=order_id, previous=current, status=target, action=f"status_change:{current}->{target}",
                                     user_id=user.id, user_name=user.name, role=user.role.value, at=_now(), today=today)
        if not ok:
            raise TransitionError("stale_status", "The order changed while you were working on it; reload and try again.")
        return self.detail(user, order_id)

    # ── changing: direct orders ────────────────────────────────────────────────────────────────
    def act(self, user: User, order_id: str, action: str, expected: str | None = None) -> dict[str, Any]:
        """One lifecycle action on a direct order. The server decides whether it is valid now; the status, the stock and the audit event change together."""
        owner = self._authorise(user, order_id)
        if action not in flow.ACTIONS:
            raise TransitionError("invalid_action", f"{action} is not an order action.")
        ctx = self._ctx(owner)
        if expected and expected != ctx["status"]:
            raise TransitionError("stale_status", f"The order is now {label_for(ctx['status'], ctx['channel'])}; reload before changing it.")
        a = flow.ACTIONS[action]
        is_processor, is_owner = user.can("orders.update_status"), self._is_owner(user, owner)
        if a.actor == flow.PROCESSOR and not is_processor:
            raise Forbidden("Only an Order Processor can do this.")
        if a.actor == flow.OWNER_OR_PROCESSOR and not is_processor and not (user.can("orders.cancel_own") and is_owner):
            raise Forbidden("Only the person who placed the order or an Order Processor can do this.")
        reason = flow.blocked(action, ctx, is_processor=is_processor, is_owner=is_owner)
        if reason:
            code = "invalid_transition" if ctx["status"] not in a.from_statuses else "transition_blocked"
            raise TransitionError(code, reason)
        self.perform(order_id, action, {"id": user.id, "name": user.name, "role": user.role.value}, ctx)
        return self.detail(user, order_id)

    def perform(self, order_id: str, action: str, actor: dict[str, str], ctx: dict[str, Any]) -> str:
        """Apply an already-validated action as one transaction and return the order's new status. Used by `act` and by checkout (system allocation)."""
        a = flow.ACTIONS[action]
        status, target = ctx["status"], a.to_status
        at, today = _now(), _today()
        d = self._repo.detail(order_id) or {"o": {}, "depot": None, "shipments": []}
        shipments = d.get("shipments") or []
        live = [s for s in shipments if s.get("status") not in ("CANCELLED", "DELIVERY_FAILED")]
        current = live[-1] if live else None
        depot_city = (d.get("depot") or {}).get("city") or "Depot"
        dest_city = (d.get("o") or {}).get("delivery_city") or "Destination"
        effects: list[tuple[str, dict]] = []
        if action == "allocate":
            effects = [("reserve", {})]
        elif action == "release_allocation":
            effects = [("release", {})]
        elif action == "cancel":
            if ctx.get("allocation_status") == "RESERVED" and status != "DELIVERY_FAILED":
                effects.append(("release", {}))
            if ctx.get("shipment_status") == "CREATED":
                effects.append(("cancel_open_shipment", {}))
        elif action == "create_shipment":
            sid = f"SHP-{order_id}-{len(shipments) + 1}"
            effects = [("create_shipment", {"shipment_id": sid, "tracking_ref": "DEMO-" + hashlib.sha1(sid.encode()).hexdigest()[:10].upper(), "location": depot_city})]
        elif action in flow.SHIPMENT_EFFECT and current is not None:
            new = flow.SHIPMENT_EFFECT[action]
            where = {"DISPATCHED": depot_city, "IN_TRANSIT": "In transit", "DELIVERED": dest_city, "EXCEPTION": "Exception reported", "DELIVERY_FAILED": dest_city}[new]
            effects = [("shipment_status", {"shipment_id": current["shipment_id"], "previous": current["status"], "status": new, "location": where})]
            if action == "deliver" and ctx.get("service_required"):
                effects.append(("create_service", {"service_id": f"SVC-{order_id}"}))
        elif action in flow.SERVICE_EFFECT:
            effects = [("service_status", {"previous": ctx["service_status"], "status": flow.SERVICE_EFFECT[action]})]
        try:
            self._repo.transition(order_id, status, target or status, action, actor=actor, at=at, today=today, effects=effects)
        except Stale as exc:
            raise TransitionError("stale_status", "The order changed while you were working on it; reload and try again.") from exc
        except ReservationFailed:
            # nothing was reserved (the transaction rolled back). Record the failure as its own audited step; stock is untouched.
            try:
                self._repo.transition(order_id, status, "ALLOCATION_FAILED", "allocation_failed", actor=actor, at=_now(), today=today, effects=[("mark_allocation", {"status": "FAILED"})])
            except Stale as exc:
                raise TransitionError("stale_status", "The order changed while you were working on it; reload and try again.") from exc
            return "ALLOCATION_FAILED"
        return target or status

    # ── the user's own cart ────────────────────────────────────────────────────────────────────
    def cart(self, user: User) -> list[dict[str, Any]]:
        if not user.can("cart.read"):
            raise Forbidden("This account has no cart.")
        return [{"partId": r["part_id"], "partNumber": r.get("part_number"), "partName": r.get("part_name"), "qty": r["quantity"], "machine": r.get("machine")}
                for r in self._repo.cart(f"CRT-{user.id}")]

    def put_cart(self, user: User, lines: list[tuple[str, int, str | None]]) -> list[dict[str, Any]]:
        if not user.can("cart.write"):
            raise Forbidden("This account has no cart.")
        merged: dict[tuple[str, str | None], int] = {}
        for part_id, qty, machine in lines:
            k = (part_id, machine or None)
            merged[k] = min(99, merged.get(k, 0) + qty)
        pairs = [{"part_id": p, "machine": m} for (p, m) in merged if m]
        bad = [f"{r['part_id']} / {r['machine']}" for r in self._repo.machine_fits(pairs) if not r["fits"]]
        if bad:
            raise TransitionError("machine_mismatch", "The part is not recorded as fitting the selected machine: " + ", ".join(bad) + ".")
        self._repo.put_cart(cart_id=f"CRT-{user.id}", user_id=user.id, customer_id=user.customer_id, today=_today(),
                            lines=[{"part_id": p, "machine": m, "quantity": v, "key": f"{p}-{m}" if m else p} for (p, m), v in merged.items() if v > 0])
        return self.cart(user)


# ── pure helpers (graph facts in, decisions out) ─────────────────────────────────────────────────────
def _total(r: dict[str, Any]) -> float | None:
    return r.get("total_incl_vat") if r.get("total_incl_vat") is not None else r.get("subtotal_ex_vat")


def _warehouse_for(line: dict[str, Any]) -> dict[str, Any] | None:
    """The warehouse with the most KNOWN recorded stock that covers the line, or None. A warehouse whose stock is unknown (no quantity) is never chosen."""
    fits = [w for w in line.get("warehouses") or [] if w.get("available") is not None and w["available"] >= (line.get("quantity") or 0)]
    return max(fits, key=lambda w: w["available"]) if fits else None


def _gate(target: str, lines: list[dict[str, Any]], shipments: list[dict[str, Any]]) -> str | None:
    """Why the graph does not support moving an earlier-channel order to `target` yet; None when it does."""
    if target == "CONFIRMED":
        bad = [l["part_number"] for l in lines if not (l.get("part_status") == "VERIFIED" and l.get("orderable") is True and l.get("price"))]
        return f"Not every part is verified, orderable and priced: {', '.join(bad)}." if bad else (None if lines else "The order has no lines.")
    if target == "ALLOCATED":
        short = [l["part_number"] for l in lines if not l.get("allocated_from") and _warehouse_for(l) is None]
        if not short:
            return None
        unknown = [l["part_number"] for l in lines if l["part_number"] in short and any(w.get("available") is None for w in l.get("warehouses") or [])]
        extra = f" Stock is UNKNOWN (not zero) at some depots for: {', '.join(unknown)}." if unknown else ""
        return f"No warehouse holds enough known stock for: {', '.join(short)}. Stock cannot be added here.{extra}"
    if target == "SHIPPED":
        return None if shipments else "No shipment is recorded for this order. Shipment creation is not connected for this earlier order."
    if target == "DELIVERED":
        open_ = [s["shipment_id"] for s in shipments if s.get("status") != "DELIVERED"]
        return f"Not every shipment is recorded as delivered: {', '.join(open_)}." if open_ or not shipments else None
    return None


def _fulfilment_summary(lines: list[dict[str, Any]], shipments: list[str]) -> str:
    if shipments:
        return "Delivered" if all(s == "DELIVERED" for s in shipments) else "Shipped"
    if lines and all(l.get("allocated") for l in lines):
        return "Allocated from stock"
    if lines and all((l.get("stock") or 0) >= (l.get("quantity") or 0) for l in lines):
        return "In stock"
    if lines and any(l.get("stock_unknown") for l in lines) and not all((l.get("stock") or 0) >= (l.get("quantity") or 0) for l in lines):
        return "Stock unknown"  # an unknown quantity is not "no stock"
    return "Needs supplier" if lines else "No lines"


def _direct_fulfilment_text(r: dict[str, Any]) -> str:
    alloc = r.get("allocation_status")
    base = {"RESERVED": "Stock reserved", "FAILED": "Allocation failed", "RELEASED": "Allocation released", "PENDING": "Allocation pending"}.get(alloc or "", "Allocation pending")
    ships = r.get("shipments") or []
    if ships:
        return {"CREATED": "Shipment created", "DISPATCHED": "Dispatched", "IN_TRANSIT": "In transit", "DELIVERED": "Delivered"}.get(ships[-1], base)
    return base


def _line(l: dict[str, Any], processor: bool) -> dict[str, Any]:
    known = [w for w in l.get("warehouses") or [] if w.get("available") is not None]
    stock = sum(w["available"] for w in known)
    unknown = len(l.get("warehouses") or []) - len(known)
    out = {
        "line_no": l.get("line_no"), "part_id": l["part_id"], "part_number": l["part_number"], "name": l["name"], "quantity": l["quantity"], "machine": l.get("machine_model"),
        "unit_price_eur": l.get("unit_price_eur"), "line_total_eur": l.get("line_total_eur"),
        "fitment": [{"model_code": f["model_code"], "name": f.get("name"), "status": (f.get("status") or "").upper() or None} for f in l.get("fitment") or []],
        "availability_state": l.get("availability_state"), "in_stock_units": stock, "stock_unknown_depots": unknown,
        "fulfilment": ("Allocated from " + ", ".join(l["allocated_from"])) if l.get("allocated_from") else
                      ("Planned from " + ", ".join(l["planned_from"])) if l.get("planned_from") else
                      "Available from stock" if stock >= (l.get("quantity") or 0) and stock > 0 else
                      "Stock unknown at some depots" if unknown else "Awaiting supplier",
        "allocation_status": l.get("allocation_status"), "reserved_quantity": l.get("reserved_quantity"),
    }
    if processor:  # operational detail only for the processor
        out |= {"part_status": l.get("part_status"), "orderable": l.get("orderable"), "price": l.get("price"),
                "warehouses": l.get("warehouses") or [], "suppliers": l.get("suppliers") or [],
                "evidence": {"fitment": "Noordveld catalogue (FITS relationship)", "inventory": l.get("inventory_data_status"),
                             "price": (l.get("price") or {}).get("data_status"), "line": l.get("data_status")}}
    return out
