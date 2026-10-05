"""Parts Store checkout, enforced entirely here (the browser only displays what this returns):

  cart lines  ->  review (availability per depot, transport options, cost)  ->  place order (confirmed)  ->  order created  ->  stock allocated.

Keep these apart; none of them is derived from another: the requester (who orders), the ship-to (where it is delivered), the receiver (who takes it
in), the dealer (who services / receives for the customer) and the fulfilment depot (where it ships from). No customer record is created: the
requester's details belong to the order. Part cost and transportation cost are never invented ('Not available').
"""
from __future__ import annotations

import re
from typing import Any

from app.core.exceptions import GraphConflictError
from app.services import order_flow as flow
from app.services.fulfilment import cost_block, depot_plan, option_view
from app.services.orders import SYSTEM, Forbidden, OrdersService, TransitionError, User, _now, _today
from app.services.part_status import is_orderable, rejection_reason

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
PHONE = re.compile(r"^\+?[0-9][0-9 ()\-./]{5,29}$")


def _clean(value: Any, label: str, *, min_len: int = 2, max_len: int = 120) -> str:
    text = " ".join(str(value or "").split())
    if not (min_len <= len(text) <= max_len):
        raise TransitionError("invalid_details", f"{label} is required.", {"field": label})
    return text


class CheckoutService:
    def __init__(self, repo, orders: OrdersService) -> None:
        self._repo = repo
        self._orders = orders

    # ── reference data for the checkout screens ────────────────────────────────────────────────
    @staticmethod
    def _need(user: User) -> None:
        if not user.can("orders.place"):
            raise Forbidden("Only an End User can check out.")

    def countries(self, user: User) -> list[dict[str, Any]]:
        self._need(user)
        return [{"country_code": r["country_code"], "destinations": r["destinations"]} for r in self._repo.countries()]

    def destinations(self, user: User, country_code: str) -> list[dict[str, Any]]:
        self._need(user)
        return [{"ship_to_id": r["shipto_id"], "street": r["street"], "city": r["city"], "postal_code": r["postal_code"], "country_code": r["country_code"],
                 "receiving_hours": r.get("receiving_hours"), "vehicle_restrictions": r.get("vehicle_restrictions"), "data_status": r.get("data_status")}
                for r in self._repo.destinations(country_code.upper())]

    def dealers(self, user: User, country_code: str | None) -> list[dict[str, Any]]:
        self._need(user)
        return [{"dealer_id": r["dealer_id"], "name": r["name"], "city": r["city"], "country_code": r["country_code"], "dealer_type": r.get("dealer_type"),
                 "data_status": r.get("data_status")} for r in self._repo.dealers(country_code.upper() if country_code else None)]

    # ── validation shared by review and place ──────────────────────────────────────────────────
    def _lines(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merge repeated part+machine, check each part exists and is orderable, and that a named machine is one the part fits."""
        merged: dict[tuple[str, str | None], int] = {}
        for it in items:
            k = (it["part_id"], (it.get("machine") or None))
            merged[k] = min(99, merged.get(k, 0) + int(it["quantity"]))
        if not merged:
            raise TransitionError("empty_order", "The order has no parts.")
        parts = {p.part_id: p for p in self._repo.parts(list({p for p, _ in merged}))}
        missing = [p for p, _ in merged if p not in parts]
        if missing:
            raise TransitionError("unknown_part", "Not in the catalogue: " + ", ".join(sorted(set(missing))) + ".")
        lines, rejected = [], []
        for n, ((part_id, machine), qty) in enumerate(merged.items(), start=1):
            p = parts[part_id]
            status = p.availability.part_status if p.availability else None
            orderable = p.availability.orderable if p.availability else None
            if not is_orderable(status, orderable):
                rejected.append(f"{p.part_number} ({rejection_reason(status, orderable)})")
                continue
            lines.append({"line_no": n, "part_id": part_id, "part_number": p.part_number, "part_name": p.name, "quantity": qty, "machine": machine})
        if rejected:
            raise TransitionError("not_orderable", "Only verified, orderable parts can be ordered: " + "; ".join(rejected))
        pairs = [{"part_id": ln["part_id"], "machine": ln["machine"]} for ln in lines if ln["machine"]]
        bad = [f"{ln['part_number']} for {r['machine']}" for r in self._repo.machine_fits(pairs) for ln in lines if ln["part_id"] == r["part_id"] and ln["machine"] == r["machine"] and not r["fits"]]
        if bad:
            raise TransitionError("machine_mismatch", "The part is not recorded as fitting the selected machine: " + ", ".join(bad) + ".")
        return lines

    def _destination(self, shipto_id: str) -> dict[str, Any]:
        s = self._repo.shipto(shipto_id)
        if s is None:
            raise TransitionError("destination_not_found", "That delivery destination is not recorded.")
        return s

    def _plan(self, lines: list[dict[str, Any]], shipto_id: str) -> list[dict[str, Any]]:
        stock = self._repo.depot_stock([ln["part_id"] for ln in lines])
        depots = sorted({r["warehouse_id"] for r in stock})
        return depot_plan(lines, stock, self._repo.routes(depots, shipto_id))

    # ── review: what the order would look like, before anything is placed ──────────────────────
    def review(self, user: User, items: list[dict[str, Any]], shipto_id: str) -> dict[str, Any]:
        self._need(user)
        lines = self._lines(items)
        dest = self._destination(shipto_id)
        plan = self._plan(lines, shipto_id)
        return {
            "lines": [{**ln, "availability": [{"depot_id": d["depot_id"], "depot": d["name"], "city": d["city"],
                                               **next(x for x in d["lines"] if x["part_id"] == ln["part_id"])} for d in plan]} for ln in lines],
            "destination": {"ship_to_id": dest["shipto_id"], "street": dest["street"], "city": dest["city"], "postal_code": dest["postal_code"], "country_code": dest["country_code"]},
            "depots": plan,
            "can_order": any(d["selectable"] for d in plan),
            "cost": cost_block(),
        }

    # ── place order ────────────────────────────────────────────────────────────────────────────
    def place(self, user: User, body: dict[str, Any]) -> dict[str, Any]:
        self._need(user)
        if body.get("confirmed") is not True:
            raise TransitionError("confirmation_required", "Confirm the order review before placing the order.")
        key = f"{user.id}:{body['idempotency_key']}"
        existing = self._repo.order_by_key(key)
        if existing:  # the same place-order key again: the order already exists, nothing is created
            return self._orders.detail(user, existing)

        req = body["requester"]
        requester = {"name": _clean(req.get("name"), "Name"), "company": _clean(req.get("company"), "Company"), "email": str(req.get("email") or "").strip(),
                     "phone": str(req.get("phone") or "").strip()}
        if not EMAIL.match(requester["email"]):
            raise TransitionError("invalid_details", "A valid email address is required.", {"field": "Email"})
        if not PHONE.match(requester["phone"]):
            raise TransitionError("invalid_details", "A valid phone number is required.", {"field": "Phone"})
        recv = body["delivery"]
        receiver = {"name": _clean(recv.get("receiver_name"), "Receiver name"), "phone": str(recv.get("receiver_phone") or "").strip()}
        if not PHONE.match(receiver["phone"]):
            raise TransitionError("invalid_details", "A valid receiver phone number is required.", {"field": "Receiver phone"})

        lines = self._lines(body["items"])
        dest = self._destination(recv["ship_to_id"])
        dealer = self._repo.dealer(body["dealer_id"])
        if dealer is None:
            raise TransitionError("dealer_not_found", "Choose a dealer from the dealer network.")
        service_required = bool(body.get("dealer_service_required"))
        if service_required:
            installs = self._repo.dealer_installs(dealer["dealer_id"], [ln["part_id"] for ln in lines])
            cannot = [ln["part_number"] for ln in lines if not installs.get(ln["part_id"])]
            if cannot:
                raise TransitionError("dealer_cannot_install", "This dealer is not recorded as installing: " + ", ".join(cannot) + ".")

        # the fulfilment source and transport are explicit choices that must still be valid
        depot_id, route_id = body["depot_id"], body["route_id"]
        route = self._repo.route(route_id)
        if route is None or route["depot_id"] != depot_id or route["shipto_id"] != dest["shipto_id"]:
            raise TransitionError("route_mismatch", "That transport option is not a recorded route from the chosen depot to the chosen destination.")
        entry = next((d for d in self._plan(lines, dest["shipto_id"]) if d["depot_id"] == depot_id), None)
        if entry is None or not entry["selectable"]:
            raise TransitionError("availability", "The chosen depot cannot supply this order.", {"reasons": entry["reasons"] if entry else ["The depot holds none of these parts."]})
        opt = option_view(route)

        try:
            order_id = self._repo.create_order(
                key=key, user_id=user.id, actor={"id": user.id, "name": user.name, "role": user.role.value}, at=_now(), today=_today(), requester=requester, receiver=receiver, shipto_id=dest["shipto_id"], dealer_id=dealer["dealer_id"],
                depot_id=depot_id, route_id=route_id, service_required=service_required,
                freight={"amount": (opt["freight"] or {}).get("amount"), "currency": (opt["freight"] or {}).get("currency", "EUR")},
                lines=[{"line_no": ln["line_no"], "part_id": ln["part_id"], "quantity": ln["quantity"], "machine": ln["machine"]} for ln in lines])
        except GraphConflictError:  # the same key arrived twice at once: the other request created the order
            existing = self._repo.order_by_key(key)
            if existing is None:
                raise
            return self._orders.detail(user, existing)

        # allocation happens after the order exists: reserve the stock now, or record that it could not be reserved
        self._orders.perform(order_id, "allocate", SYSTEM, {"status": "NEW", "channel": flow.DIRECT, "allocation_status": "PENDING", "service_required": service_required})
        # the lines that were ordered leave the cart
        self._repo.remove_cart_lines(f"CRT-{user.id}", [{"part_id": ln["part_id"], "machine": ln["machine"]} for ln in lines])
        return self._orders.detail(user, order_id)
