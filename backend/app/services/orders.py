"""The order workflow for the two roles: an End User's own purchase requests and orders, the Order Processor's queue and status
changes. Ownership and permissions are checked here as well as at the route, so no caller can skip them.

Status model: the graph's own vocabulary (OrderStatus nodes) and its recorded order, NEW -> CONFIRMED -> PROCESSING -> ALLOCATED ->
SHIPPED -> DELIVERED. Each step is allowed only when the graph supports it:
  CONFIRMED  every line's part is verified, orderable and priced (the catalogue's order gate)
  ALLOCATED  every line has a warehouse with enough recorded stock; the line is linked to it (stock figures are never changed)
  SHIPPED    a shipment is recorded for the order (shipment creation is not connected in this demo, so none is invented)
  DELIVERED  every recorded shipment is delivered
Every change writes an OrderStatusEvent with the user, role, previous status and time. Historical events are never touched.
No payment exists: a request is a purchase request for review, not a paid order.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.roles import Role, allowed
from app.graph.client import GraphClient
from app.graph.queries import orders as q
from app.graph.repositories.parts import PartRepository
from app.services.part_status import is_orderable
from app.services.parts import to_summary

FLOW = ["NEW", "CONFIRMED", "PROCESSING", "ALLOCATED", "SHIPPED", "DELIVERED"]
TRANSITIONS: dict[str, str] = {a: b for a, b in zip(FLOW, FLOW[1:])}
LABEL = {"NEW": "Pending review", "CONFIRMED": "Confirmed", "PROCESSING": "Processing", "ALLOCATED": "Allocated", "SHIPPED": "Shipped", "DELIVERED": "Delivered"}
QUEUE = {  # the processor's work queue sections, in workflow order
    "pending_review": ["NEW"],
    "needs_fulfilment": ["CONFIRMED", "PROCESSING"],
    "ready_to_ship": ["ALLOCATED"],
    "shipped": ["SHIPPED"],
    "completed": ["DELIVERED"],
}


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

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class OrdersRepository(Protocol):
    def user(self, user_id: str) -> dict[str, Any] | None: ...
    def users(self) -> list[dict[str, Any]]: ...
    def orders(self, customer_id: str | None) -> list[dict[str, Any]]: ...
    def owner(self, order_id: str) -> dict[str, Any] | None: ...
    def detail(self, order_id: str) -> dict[str, Any] | None: ...
    def create_request(self, **params: Any) -> None: ...
    def status_event(self, **params: Any) -> bool: ...
    def allocate(self, order_line_id: str, warehouse_id: str, today: str) -> None: ...
    def cart(self, cart_id: str) -> list[dict[str, Any]]: ...
    def put_cart(self, **params: Any) -> None: ...
    def clear_cart(self, cart_id: str) -> None: ...
    def parts(self, part_ids: list[str]) -> list[Any]: ...


class GraphOrdersRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._g = graph
        self._parts = PartRepository(graph)

    def user(self, user_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.USER, user_id=user_id)
        return rows[0] if rows else None

    def users(self) -> list[dict[str, Any]]:
        return self._g.read(q.USERS)

    def orders(self, customer_id: str | None) -> list[dict[str, Any]]:
        return self._g.read(q.ORDER_LIST, customer_id=customer_id)

    def owner(self, order_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.ORDER_OWNER, order_id=order_id)
        return rows[0] if rows else None

    def detail(self, order_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.ORDER_DETAIL, order_id=order_id)
        return rows[0] if rows else None

    def create_request(self, **params: Any) -> None:
        self._g.write(q.CREATE_REQUEST, **params)

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
    def _scope(self, user: User) -> str | None:
        """The customer whose orders this user may see: their own for an End User, all for the Order Processor."""
        if user.can("orders.read"):
            return None
        if user.can("orders.read_own") and user.customer_id:
            return user.customer_id
        raise Forbidden("This account has no orders to show.")

    def list(self, user: User) -> list[dict[str, Any]]:
        rows = self._repo.orders(self._scope(user))
        out = []
        for r in rows:
            lines = [l for l in r["lines"] if l]
            fulfilment = _fulfilment_summary(lines, r.get("shipments") or [])
            item = {"order_id": r["order_id"], "order_date": r["order_date"], "status": r["status"], "status_label": LABEL.get(r["status"], r["status"]),
                    "parts": [f"{l['part_number']} × {l['quantity']}" for l in lines], "fits": sorted({m for l in lines for m in l["fits"]}),
                    "total": _total(r), "currency": r.get("currency") or "EUR", "fulfilment": fulfilment, "data_status": r.get("data_status")}
            if user.can("orders.read"):
                item |= {"customer": r["customer_name"], "queue": next((k for k, v in QUEUE.items() if r["status"] in v), "other")}
            out.append(item)
        return out

    def _authorise(self, user: User, order_id: str) -> dict[str, Any]:
        owner = self._repo.owner(order_id)
        if owner is None:
            raise Missing(order_id)
        if not user.can("orders.read") and not (user.can("orders.read_own") and user.customer_id and owner["customer_id"] == user.customer_id):
            raise Forbidden("This order belongs to another customer.")
        return owner

    def detail(self, user: User, order_id: str) -> dict[str, Any]:
        self._authorise(user, order_id)
        d = self._repo.detail(order_id)
        if d is None:
            raise Missing(order_id)
        o, lines, shipments = d["o"], d["lines"] or [], d["shipments"] or []
        processor = user.can("orders.process")
        history = sorted(d["history"] or [], key=lambda e: e.get("sequence") or 0)
        result = {
            "order_id": o["order_id"], "order_date": o.get("order_date"), "status": o["order_status"], "status_label": LABEL.get(o["order_status"], o["order_status"]),
            "channel": o.get("channel"), "currency": o.get("currency") or "EUR", "data_status": o.get("data_status"),
            "totals": {"subtotal_ex_vat": o.get("subtotal_ex_vat"), "shipping_ex_vat": o.get("shipping_ex_vat"), "vat_amount": o.get("vat_amount"),
                       "total_incl_vat": o.get("order_total_incl_vat"), "note": o.get("pricing_note")},
            "lines": [_line(l, processor) for l in sorted(lines, key=lambda l: l.get("line_no") or 0)],
            "shipments": [{**s, "events": sorted(s.get("events") or [], key=lambda e: e.get("event_seq") or 0)} for s in shipments],
            "history": [{"sequence": e.get("sequence"), "status": e.get("order_status"), "status_label": LABEL.get(e.get("order_status") or "", e.get("order_status")),
                         "previous_status": e.get("previous_status"), "action": e.get("action"), "occurred_at": e.get("occurred_at"),
                         "by": e.get("actor_name") if processor else (None if e.get("actor_role") == Role.ORDER_PROCESSOR.value else e.get("actor_name")),
                         "role": e.get("actor_role"), "recorded": e.get("data_status")} for e in history],
            "payment": "Order placement and payment are not connected in this demo. No payment has been taken.",
        }
        if processor:
            result["customer"] = d["customer"]
            result["delivery_address"] = d.get("address")
            result["next"] = self._next(o["order_status"], lines, shipments)
        return result

    def _next(self, status: str, lines: list[dict[str, Any]], shipments: list[dict[str, Any]]) -> dict[str, Any] | None:
        """The one valid next status and whether the graph supports it now."""
        target = TRANSITIONS.get(status)
        if not target:
            return None
        blocked = _gate(target, lines, shipments)
        return {"status": target, "label": LABEL[target], "allowed": blocked is None, "reason": blocked}

    # ── changing ───────────────────────────────────────────────────────────────────────────────
    def update_status(self, user: User, order_id: str, target: str, expected: str | None = None) -> dict[str, Any]:
        if not user.can("orders.update_status"):
            raise Forbidden("Only an Order Processor can change an order's status.")
        owner = self._authorise(user, order_id)
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
                                     user_id=user.id, user_name=user.name, role=user.role.value, at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), today=today)
        if not ok:
            raise TransitionError("stale_status", "The order changed while you were working on it; reload and try again.")
        return self.detail(user, order_id)

    def create_request(self, user: User, items: list[tuple[str, int]], key: str) -> dict[str, Any]:
        if not user.can("requests.create") or not user.customer_id:
            raise Forbidden("Only an End User acting for a customer can submit a purchase request.")
        quantities: dict[str, int] = {}
        for part_id, qty in items:
            quantities[part_id] = quantities.get(part_id, 0) + qty
        parts = {p.part_id: p for p in self._repo.parts(list(quantities))}
        lines, rejected = [], []
        order_id = "ORD-R" + hashlib.sha256(f"{user.id}:{key}".encode()).hexdigest()[:8].upper()
        for n, (part_id, qty) in enumerate(quantities.items(), start=1):
            p = parts.get(part_id)
            status = p.availability.part_status if p and p.availability else None
            orderable = p.availability.orderable if p and p.availability else None
            if p is None or not is_orderable(status, orderable) or p.price is None:
                rejected.append(p.part_number if p else part_id)
                continue
            lines.append({"part_id": part_id, "order_line_id": f"{order_id}-L{n}", "line_no": n, "quantity": qty,
                          "unit_price": p.price.amount, "line_total": round(p.price.amount * qty, 2)})
        if rejected:
            raise TransitionError("not_orderable", "Only verified, orderable, priced parts can be requested: " + ", ".join(rejected) + ".")
        if not lines:
            raise TransitionError("empty_request", "The request has no parts.")
        existing = self._repo.owner(order_id)
        if existing is None:
            self._repo.create_request(order_id=order_id, customer_id=user.customer_id, user_id=user.id, today=_today(),
                                      subtotal=round(sum(l["line_total"] for l in lines), 2), lines=lines)
            self._repo.status_event(order_id=order_id, previous="NEW", status="NEW", action="request_submitted", user_id=user.id, user_name=user.name,
                                    role=user.role.value, at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), today=_today())
        # a submitted cart is consumed: it must not stay behind as the user's active cart (the browser cannot be relied on to clear it:
        # it leaves the page that owns the cart before its debounced save runs). Also on a repeated submit with the same key, which converges.
        self._repo.clear_cart(f"CRT-{user.id}")
        return self.detail(user, order_id)

    # ── the user's own cart ────────────────────────────────────────────────────────────────────
    def cart(self, user: User) -> list[dict[str, Any]]:
        if not user.can("cart.read"):
            raise Forbidden("This account has no cart.")
        return [{"partId": r["part_id"], "qty": r["quantity"]} for r in self._repo.cart(f"CRT-{user.id}")]

    def put_cart(self, user: User, lines: list[tuple[str, int]]) -> list[dict[str, Any]]:
        if not user.can("cart.write"):
            raise Forbidden("This account has no cart.")
        merged: dict[str, int] = {}
        for part_id, qty in lines:
            merged[part_id] = min(99, merged.get(part_id, 0) + qty)
        self._repo.put_cart(cart_id=f"CRT-{user.id}", user_id=user.id, customer_id=user.customer_id, today=_today(),
                            lines=[{"part_id": k, "quantity": v} for k, v in merged.items() if v > 0])
        return self.cart(user)


# ── pure helpers (graph facts in, decisions out) ─────────────────────────────────────────────────────
def _total(r: dict[str, Any]) -> float | None:
    return r.get("total_incl_vat") if r.get("total_incl_vat") is not None else r.get("subtotal_ex_vat")


def _warehouse_for(line: dict[str, Any]) -> dict[str, Any] | None:
    """The warehouse with the most recorded stock that covers the line, or None."""
    fits = [w for w in line.get("warehouses") or [] if (w.get("available") or 0) >= (line.get("quantity") or 0)]
    return max(fits, key=lambda w: w.get("available") or 0) if fits else None


def _gate(target: str, lines: list[dict[str, Any]], shipments: list[dict[str, Any]]) -> str | None:
    """Why the graph does not support moving to `target` yet; None when it does."""
    if target == "CONFIRMED":
        bad = [l["part_number"] for l in lines if not (l.get("part_status") == "VERIFIED" and l.get("orderable") is True and l.get("price"))]
        return f"Not every part is verified, orderable and priced: {', '.join(bad)}." if bad else (None if lines else "The order has no lines.")
    if target == "ALLOCATED":
        short = [l["part_number"] for l in lines if not l.get("allocated_from") and _warehouse_for(l) is None]
        return f"No warehouse holds enough recorded stock for: {', '.join(short)}. Stock cannot be added here." if short else None
    if target == "SHIPPED":
        return None if shipments else "No shipment is recorded for this order. Shipment creation is not connected in this demo."
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
    return "Needs supplier" if lines else "No lines"


def _line(l: dict[str, Any], processor: bool) -> dict[str, Any]:
    stock = sum((w.get("available") or 0) for w in l.get("warehouses") or [])
    out = {
        "line_no": l.get("line_no"), "part_id": l["part_id"], "part_number": l["part_number"], "name": l["name"], "quantity": l["quantity"],
        "unit_price_eur": l.get("unit_price_eur"), "line_total_eur": l.get("line_total_eur"),
        "fitment": [{"model_code": f["model_code"], "name": f.get("name"), "status": (f.get("status") or "").upper() or None} for f in l.get("fitment") or []],
        "availability_state": l.get("availability_state"), "in_stock_units": stock,
        "fulfilment": ("Allocated from " + ", ".join(l["allocated_from"])) if l.get("allocated_from") else
                      ("Planned from " + ", ".join(l["planned_from"])) if l.get("planned_from") else
                      "Available from stock" if stock >= (l.get("quantity") or 0) and stock > 0 else "Awaiting supplier",
        "allocation_status": l.get("allocation_status"),
    }
    if processor:  # operational detail only for the processor
        out |= {"part_status": l.get("part_status"), "orderable": l.get("orderable"), "price": l.get("price"),
                "warehouses": l.get("warehouses") or [], "suppliers": l.get("suppliers") or [],
                "evidence": {"fitment": "Noordveld catalogue (FITS relationship)", "inventory": l.get("inventory_data_status"),
                             "price": (l.get("price") or {}).get("data_status"), "line": l.get("data_status")}}
    return out
