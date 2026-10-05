"""An in-memory stand-in for GraphOrdersRepository that behaves like the graph where it matters: stock is reserved atomically per order and rolled back
as a whole on failure, a status change is guarded by the status the caller saw, and every lifecycle step writes an audit event.

It holds the same row shapes the Cypher returns, so the services run unchanged. Used by the unit tests; the live-graph tests (test_direct_order_graph.py)
run the same flows against the real Cypher."""
from __future__ import annotations

import copy
from typing import Any

from app.graph.repositories.fulfilment import ReservationFailed, Stale
from app.core.exceptions import GraphConflictError
from app.services.fulfilment import status_after


def part(pid: str, number: str | None = None, *, verified: bool = True, price: float | None = 25.0):
    from app.schemas.catalogue import Availability, Money, PartSummary

    n = number or pid.removeprefix("P-")
    return PartSummary(part_id=pid, part_number=n, name=f"Part {n}", fitment=[], price=Money(amount=price, currency="EUR") if price is not None else None,
                       availability=Availability(state="IN_STOCK", orderable=verified, part_status="VERIFIED" if verified else "UNVERIFIED"))


def line(part_no, qty=1, stock=10, allocated=False, verified=True, price=50.0, fits=("M-1",)):
    """A legacy (earlier-channel) order line in the shape ORDER_DETAIL returns."""
    return {"line_no": 1, "order_line_id": f"L-{part_no}", "quantity": qty, "unit_price_eur": price, "line_total_eur": price * qty, "allocation_status": "NOT_YET_ALLOCATED",
            "part_id": f"P-{part_no}", "part_number": part_no, "name": f"Part {part_no}", "data_status": "SYNTHETIC_DEMO",
            "part_status": "VERIFIED" if verified else "IDENTIFICATION_REQUIRED", "orderable": verified, "availability_state": "IN_STOCK",
            "inventory_data_status": "SYNTHETIC_DEMO", "price": {"list_price_ex_vat": price, "currency": "EUR", "data_status": "SYNTHETIC_DEMO"},
            "fitment": [{"model_code": m, "name": "Loader", "status": "CONFIRMED", "data_status": "SOURCE_DERIVED"} for m in fits],
            "warehouses": [{"warehouse_id": "WH-1", "name": "Assen", "city": "Assen", "available": stock, "stock_status": "IN_STOCK", "data_status": "SYNTHETIC_DEMO"}],
            "suppliers": [{"name": "Supplier (demo)", "lead_time_days": 10, "primary": True, "data_status": "SYNTHETIC_DEMO"}],
            "allocated_from": ["Assen"] if allocated else [], "planned_from": []}


def route(depot: str, shipto: str, option="STANDARD_ROAD_EU", mode="ROAD", level="STANDARD", km=100.0, days=2, freight=12.5, rid=None):
    return {"depot_id": depot, "shipto_id": shipto, "route_id": rid or f"RTE-{depot}-{shipto}-{option}", "option_id": "TOP-009", "option_name": option.replace("_", " ").title(),
            "option_code": option, "mode": mode, "service_level": level, "distance_km": km, "days": days, "estimate_basis": "ESTIMATED", "legs": 1, "data_status": "SYNTHETIC_DEMO",
            "rate_id": "FRT-1", "freight_total": freight, "freight_currency": "EUR", "rate_data_status": "SYNTHETIC_DEMO", "route_status": "ACTIVE_DEMO"}


class FakeRepo:
    def __init__(self) -> None:
        self.users_ = {
            "U-ANNA": {"id": "U-ANNA", "name": "Anna", "email": "anna@x.example", "role": "END_USER", "customer_id": "C-1", "customer_name": "Customer One"},
            "U-LARS": {"id": "U-LARS", "name": "Lars", "email": "lars@x.example", "role": "END_USER", "customer_id": "C-2", "customer_name": "Customer Two"},
            "U-NOCUS": {"id": "U-NOCUS", "name": "Nora", "email": "nora@x.example", "role": "END_USER", "customer_id": None, "customer_name": None},
            "U-JANE": {"id": "U-JANE", "name": "Jane", "email": "jane@x.example", "role": "ORDER_PROCESSOR", "customer_id": None, "customer_name": None},
        }
        # earlier-channel orders (customer-owned, forward-only flow)
        self.orders_: dict[str, dict[str, Any]] = {
            "O-1": {"channel": "DEMO_WEB_STORE", "customer": "C-1", "user": None, "status": "NEW", "lines": [line("AB-1")], "shipments": [], "history": [{"sequence": 1, "order_status": "NEW"}]},
            "O-2": {"channel": "DEMO_WEB_STORE", "customer": "C-2", "user": None, "status": "NEW", "lines": [line("AB-2")], "shipments": [], "history": []},
            "O-3": {"channel": "DEMO_WEB_STORE", "customer": "C-1", "user": None, "status": "PROCESSING", "lines": [line("AB-3", qty=50, stock=10)], "shipments": [], "history": []},
            "O-4": {"channel": "DEMO_WEB_STORE", "customer": "C-1", "user": None, "status": "ALLOCATED", "lines": [line("AB-4", allocated=True)], "shipments": [], "history": []},
            "O-5": {"channel": "DEMO_WEB_STORE", "customer": "C-1", "user": None, "status": "NEW", "lines": [line("AB-5", verified=False)], "shipments": [], "history": []},
        }
        self.carts: dict[str, list[dict[str, Any]]] = {}
        self.allocations: list[tuple[str, str]] = []
        self.writes = 0
        self.seq = 0
        self.keys: dict[str, str] = {}
        # reference data for checkout
        self.parts_ = {p.part_id: p for p in (part("P-AB-1"), part("P-AB-2"), part("P-AB-3"), part("P-AB-9"), part("P-AB-7"), part("P-XBAD", verified=False))}
        self.fits = {("P-AB-1", "M-1"), ("P-AB-9", "M-1"), ("P-AB-2", "M-2")}
        self.shiptos = {"SHT-1": {"shipto_id": "SHT-1", "street": "Hafenstrasse 1", "city": "Hamburg", "postal_code": "20457", "country_code": "DE", "receiving_hours": "Mon-Fri 07:00-16:00", "data_status": "SYNTHETIC_DEMO"},
                        "SHT-2": {"shipto_id": "SHT-2", "street": "Kade 9", "city": "Rotterdam", "postal_code": "3011", "country_code": "NL", "receiving_hours": None, "data_status": "SYNTHETIC_DEMO"}}
        self.dealers_ = {"DLR-1": {"dealer_id": "DLR-1", "name": "Dealer One (demo)", "city": "Hamburg", "country_code": "DE", "dealer_type": "AUTHORISED_DEALER", "data_status": "SYNTHETIC_DEMO"},
                         "DLR-2": {"dealer_id": "DLR-2", "name": "Dealer Two (demo)", "city": "Utrecht", "country_code": "NL", "dealer_type": "SERVICE_PARTNER", "data_status": "SYNTHETIC_DEMO"}}
        self.installs = {("DLR-1", "P-AB-1"), ("DLR-1", "P-AB-9"), ("DLR-1", "P-AB-2")}
        self.depots = {"WH-A": {"name": "Depot A (demo)", "city": "Assen", "country_code": "NL"}, "WH-B": {"name": "Depot B (demo)", "city": "Lingen", "country_code": "DE"},
                       "WH-C": {"name": "Depot C (demo)", "city": "Brno", "country_code": "CZ"}}
        # (part, depot) -> inventory row. WH-A has the MOST stock but no route to SHT-1; WH-B is the nearest with a route.
        self.stock: dict[tuple[str, str], dict[str, Any]] = {}
        for p in ("P-AB-1", "P-AB-2", "P-AB-9"):
            self.stock[(p, "WH-A")] = {"stock_status": "IN_STOCK", "available": 500, "on_hand": 500, "reserved": 0}
            self.stock[(p, "WH-B")] = {"stock_status": "IN_STOCK", "available": 20, "on_hand": 20, "reserved": 0}
            self.stock[(p, "WH-C")] = {"stock_status": "IN_STOCK", "available": 40, "on_hand": 40, "reserved": 0}
        self.routes_ = [route("WH-B", "SHT-1", km=100, days=2), route("WH-B", "SHT-1", "EXPRESS_ROAD_EU", level="EXPRESS", km=100, days=1, freight=40.0),
                        route("WH-C", "SHT-1", km=700, days=4), route("WH-A", "SHT-2", km=60, days=1), route("WH-B", "SHT-2", km=400, days=3)]

    # ── accounts ───────────────────────────────────────────────────────────────────────────────
    def user(self, user_id):
        return self.users_.get(user_id)

    def users(self):
        return list(self.users_.values())

    # ── reading orders ─────────────────────────────────────────────────────────────────────────
    def orders(self, user_id, customer_id, everything):
        out = []
        for k, o in self.orders_.items():
            if not (everything or (o.get("customer") and o["customer"] == customer_id) or (o.get("user") and o["user"] == user_id)):
                continue
            p = o.get("props", {})
            out.append({"order_id": k, "order_date": "2026-10-01", "status": o["status"], "currency": "EUR", "subtotal_ex_vat": None if o["channel"] == "DIRECT_ORDER" else 50.0,
                        "total_incl_vat": None, "channel": o["channel"], "data_status": "USER_PROVIDED" if o["channel"] == "DIRECT_ORDER" else "SYNTHETIC_DEMO",
                        "customer_id": o.get("customer"), "customer_name": o.get("customer") or p.get("requester_company"), "requester_name": p.get("requester_name"),
                        "lines": [{"part_number": l["part_number"], "name": l["name"], "quantity": l["quantity"], "machine": l.get("machine_model"), "stock": 10, "stock_unknown": 0,
                                   "allocated": bool(l.get("allocated_from")) or l.get("allocation_status") in ("RESERVED", "SHIPPED"), "fits": ["M-1"]} for l in o["lines"]],
                        "allocation_status": p.get("allocation_status"), "service_required": p.get("dealer_service_required"),
                        "dealer": (self.dealers_.get(p.get("dealer_id")) or {}).get("name"), "depot": (self.depots.get(p.get("fulfilment_depot_id")) or {}).get("name"),
                        "shipments": [s["status"] for s in o["shipments"]]})
        return out

    def owner(self, order_id):
        o = self.orders_.get(order_id)
        if not o:
            return None
        return {"status": o["status"], "channel": o["channel"], "customer_id": o.get("customer"), "user_id": o.get("user"),
                "allocation_status": o.get("props", {}).get("allocation_status", "PENDING"), "service_required": bool(o.get("props", {}).get("dealer_service_required")),
                "shipment_statuses": [s["status"] for s in o["shipments"]], "service_status": (o.get("service") or {}).get("service_status")}

    def detail(self, order_id):
        o = self.orders_.get(order_id)
        if not o:
            return None
        p = o.get("props", {})
        base = {"order_id": order_id, "order_date": "2026-10-01", "order_status": o["status"], "currency": "EUR", "subtotal_ex_vat": None if o["channel"] == "DIRECT_ORDER" else 50.0,
                "channel": o["channel"], "data_status": "USER_PROVIDED" if o["channel"] == "DIRECT_ORDER" else "SYNTHETIC_DEMO", **p}
        depot = self.depots.get(p.get("fulfilment_depot_id"))
        return {"o": base, "customer": {"customer_id": o["customer"], "name": o["customer"]} if o.get("customer") else None, "address": None,
                "dealer": self.dealers_.get(p.get("dealer_id")), "depot": ({"warehouse_id": p["fulfilment_depot_id"], **depot} if depot else None),
                "ship_to": {"shipto_id": p.get("shipto_id")} if p.get("shipto_id") else None, "service": copy.deepcopy(o.get("service")),
                "lines": copy.deepcopy(o["lines"]), "shipments": copy.deepcopy(o["shipments"]), "history": copy.deepcopy(o["history"])}

    # ── earlier-channel writes ─────────────────────────────────────────────────────────────────
    def status_event(self, order_id, previous, status, action, user_id, user_name, role, at, today):
        o = self.orders_[order_id]
        if o["status"] != previous:
            return False
        self.writes += 1
        o["history"].append({"sequence": len(o["history"]) + 1, "order_status": status, "previous_status": previous, "action": action, "actor_name": user_name,
                             "actor_role": role, "occurred_at": at, "data_status": "USER_PROVIDED"})
        o["status"] = status
        return True

    def allocate(self, order_line_id, warehouse_id, today):
        self.allocations.append((order_line_id, warehouse_id))

    # ── cart ───────────────────────────────────────────────────────────────────────────────────
    def cart(self, cart_id):
        return [dict(l) for l in self.carts.get(cart_id, [])]

    def put_cart(self, cart_id, lines, **_):
        self.carts[cart_id] = [{"part_id": l["part_id"], "part_number": self.parts_[l["part_id"]].part_number if l["part_id"] in self.parts_ else None,
                                "part_name": self.parts_[l["part_id"]].name if l["part_id"] in self.parts_ else None, "quantity": l["quantity"], "machine": l.get("machine")} for l in lines]

    def clear_cart(self, cart_id):
        self.carts[cart_id] = []

    def remove_cart_lines(self, cart_id, keys):
        self.carts[cart_id] = [l for l in self.carts.get(cart_id, []) if not any(k["part_id"] == l["part_id"] and (k.get("machine") or "") == (l.get("machine") or "") for k in keys)]

    def parts(self, part_ids):
        return [self.parts_[p] for p in part_ids if p in self.parts_]

    def machine_fits(self, pairs):
        return [{"part_id": p["part_id"], "machine": p["machine"], "fits": (p["part_id"], p["machine"]) in self.fits, "fitment_status": "CONFIRMED"} for p in pairs]

    # ── checkout reads ─────────────────────────────────────────────────────────────────────────
    def countries(self):
        out: dict[str, int] = {}
        for s in self.shiptos.values():
            out[s["country_code"]] = out.get(s["country_code"], 0) + 1
        return [{"country_code": c, "destinations": n} for c, n in sorted(out.items())]

    def destinations(self, country_code):
        return [s for s in self.shiptos.values() if s["country_code"] == country_code]

    def shipto(self, shipto_id):
        return self.shiptos.get(shipto_id)

    def dealers(self, country_code):
        return [d for d in self.dealers_.values() if country_code is None or d["country_code"] == country_code]

    def dealer(self, dealer_id):
        return self.dealers_.get(dealer_id)

    def dealer_installs(self, dealer_id, part_ids):
        return {p: (dealer_id, p) in self.installs for p in part_ids}

    def depot_stock(self, part_ids):
        return [{"part_id": p, "warehouse_id": d, "name": self.depots[d]["name"], "city": self.depots[d]["city"], "country_code": self.depots[d]["country_code"],
                 "stock_status": row["stock_status"], "available": row["available"], "data_status": "SYNTHETIC_DEMO"}
                for (p, d), row in sorted(self.stock.items(), key=lambda x: x[0][1]) if p in part_ids]

    def routes(self, depots, shipto_id):
        return [r for r in self.routes_ if r["depot_id"] in depots and r["shipto_id"] == shipto_id]

    def route(self, route_id):
        return next((r for r in self.routes_ if r["route_id"] == route_id), None)

    def order_by_key(self, key):
        return self.keys.get(key)

    # ── place order ────────────────────────────────────────────────────────────────────────────
    def create_order(self, *, key, user_id, actor, at, today, requester, receiver, shipto_id, dealer_id, depot_id, route_id, service_required, freight, lines):
        if key in self.keys:
            raise GraphConflictError(key)
        self.seq += 1
        order_id = f"HCME-ORD-{self.seq:06d}"
        r = self.route(route_id)
        self.orders_[order_id] = {
            "channel": "DIRECT_ORDER", "customer": None, "user": user_id, "status": "NEW", "shipments": [], "service": None, "history": [],
            "props": {"requester_name": requester["name"], "requester_email": requester["email"], "requester_phone": requester["phone"], "requester_company": requester["company"],
                      "delivery_street": self.shiptos[shipto_id]["street"], "delivery_city": self.shiptos[shipto_id]["city"], "delivery_postal_code": self.shiptos[shipto_id]["postal_code"],
                      "delivery_country_code": self.shiptos[shipto_id]["country_code"], "receiver_name": receiver["name"], "receiver_phone": receiver["phone"],
                      "dealer_service_required": service_required, "fulfilment_depot_id": depot_id, "allocation_status": "PENDING", "dealer_id": dealer_id, "shipto_id": shipto_id,
                      "transport_route_id": route_id, "transport_option_code": r["option_code"], "transport_mode": r["mode"], "transport_distance_km": r["distance_km"],
                      "transport_estimated_days": r["days"], "transport_estimate_basis": "ESTIMATED", "transport_data_status": "SYNTHETIC_DEMO",
                      "freight_estimate_amount": freight["amount"], "freight_estimate_currency": freight["currency"], "freight_estimate_status": "SYNTHETIC_DEMO_ESTIMATE",
                      "part_cost": None, "transport_cost": None, "order_total": None, "cost_status": "NOT_AVAILABLE"},
            "lines": [{"line_no": ln["line_no"], "order_line_id": f"{order_id}-L{ln['line_no']}", "quantity": ln["quantity"], "machine_model": ln["machine"], "part_id": ln["part_id"],
                       "part_number": self.parts_[ln["part_id"]].part_number, "name": self.parts_[ln["part_id"]].name, "unit_price_eur": None, "line_total_eur": None,
                       "allocation_status": "NOT_YET_ALLOCATED", "data_status": "USER_PROVIDED", "fitment": [], "warehouses": [], "suppliers": [], "allocated_from": [], "planned_from": []}
                      for ln in lines]}
        self.keys[key] = order_id
        self.status_event(order_id, "NEW", "NEW", "order_placed", actor["id"], actor["name"], actor["role"], at, today)
        return order_id

    # ── one lifecycle step: guard + effects + audit event, atomically ──────────────────────────
    def transition(self, order_id, previous, status, action, *, actor, at, today, effects):
        o = self.orders_[order_id]
        if o["status"] != previous:
            raise Stale(order_id)
        snapshot = (copy.deepcopy(o), copy.deepcopy(self.stock))
        try:
            for name, p in effects:
                self._effect(order_id, o, name, p, at)
            if not self.status_event(order_id, previous, status, action, actor["id"], actor["name"], actor["role"], at, today):
                raise Stale(order_id)
        except (ReservationFailed, Stale):
            self.orders_[order_id], self.stock = snapshot  # all or nothing
            raise
        return {}

    def _effect(self, order_id, o, name, p, at):
        props = o["props"]
        depot = props.get("fulfilment_depot_id")
        if name == "reserve":
            if props["allocation_status"] == "RESERVED":
                raise ReservationFailed(order_id)
            for l in o["lines"]:
                row = self.stock.get((l["part_id"], depot))
                if not row or row["stock_status"] not in ("IN_STOCK", "LOW_STOCK") or row["available"] is None or row["available"] < l["quantity"]:
                    raise ReservationFailed(order_id)
                rest = row["available"] - l["quantity"]
                row.update(available=rest, reserved=row.get("reserved", 0) + l["quantity"], stock_status=status_after(rest))
                l.update(allocation_status="RESERVED", reserved_quantity=l["quantity"], allocated_from=[self.depots[depot]["name"]])
            props["allocation_status"] = "RESERVED"
        elif name == "release":
            if props["allocation_status"] == "RESERVED":
                for l in o["lines"]:
                    if l["allocation_status"] == "RESERVED":
                        row = self.stock[(l["part_id"], depot)]
                        back = (row["available"] or 0) + l["reserved_quantity"]
                        row.update(available=back, reserved=max(row.get("reserved", 0) - l["reserved_quantity"], 0), stock_status=status_after(back))
                        l.update(allocation_status="RELEASED", allocated_from=[])
            props["allocation_status"] = "RELEASED"
        elif name == "mark_allocation":
            props["allocation_status"] = p["status"]
        elif name == "create_shipment":
            o["shipments"].append({"shipment_id": p["shipment_id"], "status": "CREATED", "tracking_ref": p["tracking_ref"], "tracking_basis": "SYNTHETIC_DEMO", "data_status": "USER_PROVIDED",
                                   "mode": props["transport_mode"], "dispatched_from": self.depots[depot]["name"], "events": [{"event_seq": 1, "event_status": "CREATED", "event_location": p["location"], "data_status": "SYNTHETIC_DEMO"}]})
        elif name == "shipment_status":
            sh = next(s for s in o["shipments"] if s["shipment_id"] == p["shipment_id"])
            if sh["status"] != p["previous"]:
                raise Stale(order_id)
            sh["status"] = p["status"]
            sh["events"].append({"event_seq": len(sh["events"]) + 1, "event_status": p["status"], "event_location": p["location"], "data_status": "SYNTHETIC_DEMO"})
            if p["status"] == "DISPATCHED":
                for l in o["lines"]:
                    if l["allocation_status"] == "RESERVED":
                        row = self.stock[(l["part_id"], depot)]
                        row.update(on_hand=max(row["on_hand"] - l["reserved_quantity"], 0), reserved=max(row.get("reserved", 0) - l["reserved_quantity"], 0))
                        l["allocation_status"] = "SHIPPED"
        elif name == "cancel_open_shipment":
            for s in o["shipments"]:
                if s["status"] == "CREATED":
                    s["status"] = "CANCELLED"
        elif name == "create_service":
            o["service"] = {"service_id": p["service_id"], "service_status": "CREATED", "created_at": at, "data_status": "USER_PROVIDED", "dealer": self.dealers_[props["dealer_id"]]["name"]}
        elif name == "service_status":
            if (o.get("service") or {}).get("service_status") != p["previous"]:
                raise Stale(order_id)
            o["service"]["service_status"] = p["status"]
        else:
            raise ValueError(name)
