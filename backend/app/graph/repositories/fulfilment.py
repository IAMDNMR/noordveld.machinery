"""The graph side of the direct-order flow: checkout reads and the atomic order-lifecycle writes. Every method is one fixed, parameterised query
(app/graph/queries/checkout.py and orders.py); the rules that decide when to call them live in app/services (checkout.py, orders.py, order_flow.py)."""
from __future__ import annotations

from typing import Any

from app.core.exceptions import GraphConflictError
from app.graph.client import GraphClient
from app.graph.queries import checkout as q
from app.services.fulfilment import LOW_STOCK_AT


class Stale(Exception):
    """The order is no longer in the status the caller saw (someone else changed it first)."""


class ReservationFailed(Exception):
    """Not every line could be reserved from the depot: nothing was reserved (the transaction is rolled back)."""


class GraphFulfilmentRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._g = graph

    # ── checkout reads ─────────────────────────────────────────────────────────────────────────
    def countries(self) -> list[dict[str, Any]]:
        return self._g.read(q.COUNTRIES)

    def destinations(self, country_code: str) -> list[dict[str, Any]]:
        return self._g.read(q.DESTINATIONS, country_code=country_code)

    def shipto(self, shipto_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.SHIPTO, shipto_id=shipto_id)
        return rows[0] if rows else None

    def dealers(self, country_code: str | None) -> list[dict[str, Any]]:
        return self._g.read(q.DEALERS, country_code=country_code)

    def dealer(self, dealer_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.DEALER, dealer_id=dealer_id)
        return rows[0] if rows else None

    def dealer_installs(self, dealer_id: str, part_ids: list[str]) -> dict[str, bool]:
        return {r["part_id"]: bool(r["installs"]) for r in self._g.read(q.DEALER_INSTALLS, dealer_id=dealer_id, part_ids=part_ids)}

    def machine_fits(self, pairs: list[dict[str, str]]) -> list[dict[str, Any]]:
        return self._g.read(q.MACHINE_FITS, pairs=pairs) if pairs else []

    def depot_stock(self, part_ids: list[str]) -> list[dict[str, Any]]:
        return self._g.read(q.DEPOT_STOCK, part_ids=part_ids)

    def routes(self, depots: list[str], shipto_id: str) -> list[dict[str, Any]]:
        return self._g.read(q.ROUTES, depots=depots, shipto_id=shipto_id) if depots else []

    def route(self, route_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.ROUTE_ONE, route_id=route_id)
        return rows[0] if rows else None

    def order_by_key(self, key: str) -> str | None:
        rows = self._g.read(q.ORDER_BY_KEY, key=key)
        return rows[0]["order_id"] if rows else None

    # ── place order ────────────────────────────────────────────────────────────────────────────
    def create_order(self, *, key: str, user_id: str, actor: dict[str, str], at: str, today: str, requester: dict, receiver: dict, shipto_id: str, dealer_id: str, depot_id: str, route_id: str,
                     service_required: bool, freight: dict, lines: list[dict]) -> str:
        """Order number, order, lines, relationships: one transaction. A second call with the same key hits the unique constraint and raises GraphConflictError."""

        def work(tx):
            n = tx.run(q.NEXT_ORDER_NUMBER).single()["n"]
            order_id = f"HCME-ORD-{n:06d}"
            made = tx.run(q.CREATE_ORDER, order_id=order_id, key=key, user_id=user_id, today=today, requester=requester, receiver=receiver, shipto_id=shipto_id,
                          dealer_id=dealer_id, depot_id=depot_id, route_id=route_id, service_required=service_required, freight=freight,
                          lines=[{**ln, "order_line_id": f"{order_id}-L{ln['line_no']}"} for ln in lines]).single()
            if not made or made["lines"] != len(lines):
                raise ValueError("the order could not be created: a referenced record is missing")
            from app.graph.queries import orders as oq

            tx.run(oq.STATUS_EVENT, order_id=order_id, previous="NEW", status="NEW", action="order_placed", user_id=actor["id"], user_name=actor["name"], role=actor["role"], at=at, today=today).single()
            return order_id

        return self._g.transaction(work)

    # ── one lifecycle step: guard + effects + audit event, all or nothing ──────────────────────
    def transition(self, order_id: str, previous: str, status: str, action: str, *, actor: dict[str, str], at: str, today: str, effects: list[tuple[str, dict]]) -> dict[str, Any]:
        """Run `effects` and move the order previous -> status as ONE transaction. Raises Stale if the order is not in `previous` any more, and
        ReservationFailed (everything rolled back) if a 'reserve' effect cannot reserve every line."""
        from app.graph.queries import orders as oq

        def work(tx):
            guard = tx.run(q.GUARD, order_id=order_id, previous=previous, today=today).single()
            if guard is None:
                raise Stale(order_id)
            out: dict[str, Any] = {"allocation_status": guard["allocation_status"]}
            for name, p in effects:
                if name in ("reserve", "release") or (name == "shipment_status" and p["status"] == "DISPATCHED"):
                    tx.run(q.LOCK_STOCK, order_id=order_id, at=at).consume()  # lock the inventory rows first; the statements below then read the latest committed quantity
                if name == "reserve":
                    lines = tx.run("MATCH (:Order {order_id: $o})-[:CONTAINS_LINE]->(l:OrderLine) RETURN count(l) AS n", o=order_id).single()["n"]
                    got = tx.run(q.RESERVE, order_id=order_id, at=at, today=today, low=LOW_STOCK_AT).single()
                    if not got or got["reserved"] != lines or lines == 0:
                        raise ReservationFailed(order_id)
                    tx.run(q.MARK_ALLOCATION, order_id=order_id, status="RESERVED", at=at)
                elif name == "release":
                    tx.run(q.RELEASE, order_id=order_id, at=at, today=today, low=LOW_STOCK_AT)
                    tx.run(q.MARK_ALLOCATION, order_id=order_id, status="RELEASED", at=at)
                elif name == "mark_allocation":
                    tx.run(q.MARK_ALLOCATION, order_id=order_id, status=p["status"], at=at)
                elif name == "create_shipment":
                    tx.run(q.CREATE_SHIPMENT, order_id=order_id, shipment_id=p["shipment_id"], tracking_ref=p["tracking_ref"], today=today).single()
                    tx.run(q.SHIPMENT_LINES, order_id=order_id, shipment_id=p["shipment_id"], today=today)
                    tx.run(q.SHIPMENT_STATUS, order_id=order_id, shipment_id=p["shipment_id"], previous="CREATED", status="CREATED", location=p["location"], today=today).single()
                elif name == "shipment_status":
                    done = tx.run(q.SHIPMENT_STATUS, order_id=order_id, shipment_id=p["shipment_id"], previous=p["previous"], status=p["status"], location=p["location"], today=today).single()
                    if done is None:
                        raise Stale(order_id)
                    if p["status"] == "DISPATCHED":
                        tx.run(q.CONSUME, order_id=order_id, at=at, today=today)
                elif name == "cancel_open_shipment":
                    tx.run(q.CANCEL_OPEN_SHIPMENT, order_id=order_id, today=today)
                elif name == "create_service":
                    tx.run(q.CREATE_SERVICE, order_id=order_id, service_id=p["service_id"], at=at, today=today).single()
                elif name == "service_status":
                    done = tx.run(q.SERVICE_STATUS, order_id=order_id, previous=p["previous"], status=p["status"], at=at, today=today).single()
                    if done is None:
                        raise Stale(order_id)
                else:  # a programming error, never user input
                    raise ValueError(f"unknown effect {name}")
            event = tx.run(oq.STATUS_EVENT, order_id=order_id, previous=previous, status=status, action=action, user_id=actor["id"], user_name=actor["name"], role=actor["role"],
                           at=at, today=today).single()
            if event is None:
                raise Stale(order_id)
            return out

        return self._g.transaction(work)

    def remove_cart_lines(self, cart_id: str, keys: list[dict[str, Any]]) -> None:
        self._g.write(q.CART_REMOVE_LINES, cart_id=cart_id, keys=keys)


__all__ = ["GraphFulfilmentRepository", "Stale", "ReservationFailed", "GraphConflictError"]
