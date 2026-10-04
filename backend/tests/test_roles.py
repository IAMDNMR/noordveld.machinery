"""End User and Order Processor: authentication, permissions, ownership, the status state machine and its audit trail.

The order workflow runs against an in-memory repository (no demo order in AuraDB is changed by the suite); catalogue, Parts
Intelligence and Agentic Shopping run against the live graph when it is configured, as in the other API tests."""
from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_llm, get_orders_repository
from app.core.config import get_settings
from app.core.roles import PERMISSIONS, Role
from app.core.session import sign, verify
from app.llm import LLMParse, ShoppingParse
from app.main import app
from app.services.orders import FLOW, TRANSITIONS


def line(part, qty=1, stock=10, allocated=False, verified=True, price=50.0, fits=("M-1",)):
    return {"line_no": 1, "order_line_id": f"L-{part}", "quantity": qty, "unit_price_eur": price, "line_total_eur": price * qty, "allocation_status": "NOT_YET_ALLOCATED",
            "part_id": f"P-{part}", "part_number": part, "name": f"Part {part}", "data_status": "SYNTHETIC_DEMO",
            "part_status": "VERIFIED" if verified else "IDENTIFICATION_REQUIRED", "orderable": verified, "availability_state": "IN_STOCK",
            "inventory_data_status": "SYNTHETIC_DEMO", "price": {"list_price_ex_vat": price, "currency": "EUR", "data_status": "SYNTHETIC_DEMO"},
            "fitment": [{"model_code": m, "name": "Loader", "status": "CONFIRMED", "data_status": "SOURCE_DERIVED"} for m in fits],
            "warehouses": [{"warehouse_id": "WH-1", "name": "Assen", "city": "Assen", "available": stock, "data_status": "SYNTHETIC_DEMO"}],
            "suppliers": [{"name": "Supplier (demo)", "lead_time_days": 10, "primary": True, "data_status": "SYNTHETIC_DEMO"}],
            "allocated_from": ["Assen"] if allocated else [], "planned_from": []}


class FakeRepo:
    """In-memory stand-in for GraphOrdersRepository, holding the same shapes the Cypher returns."""

    def __init__(self):
        self.users_ = {
            "U-ANNA": {"id": "U-ANNA", "name": "Anna", "email": "anna@x.example", "role": "END_USER", "customer_id": "C-1", "customer_name": "Customer One"},
            "U-LARS": {"id": "U-LARS", "name": "Lars", "email": "lars@x.example", "role": "END_USER", "customer_id": "C-2", "customer_name": "Customer Two"},
            "U-JANE": {"id": "U-JANE", "name": "Jane", "email": "jane@x.example", "role": "ORDER_PROCESSOR", "customer_id": None, "customer_name": None},
        }
        self.orders_ = {
            "O-1": {"customer": "C-1", "status": "NEW", "lines": [line("AB-1")], "shipments": [], "history": [{"sequence": 1, "order_status": "NEW"}]},
            "O-2": {"customer": "C-2", "status": "NEW", "lines": [line("AB-2")], "shipments": [], "history": []},
            "O-3": {"customer": "C-1", "status": "PROCESSING", "lines": [line("AB-3", qty=50, stock=10)], "shipments": [], "history": []},
            "O-4": {"customer": "C-1", "status": "ALLOCATED", "lines": [line("AB-4", allocated=True)], "shipments": [], "history": []},
            "O-5": {"customer": "C-1", "status": "NEW", "lines": [line("AB-5", verified=False)], "shipments": [], "history": []},
        }
        self.parts_ = {}
        self.carts = {}
        self.allocations = []
        self.writes = 0

    def user(self, user_id):
        return self.users_.get(user_id)

    def users(self):
        return list(self.users_.values())

    def orders(self, customer_id):
        return [{"order_id": k, "order_date": "2026-10-01", "status": o["status"], "currency": "EUR", "subtotal_ex_vat": 50.0, "total_incl_vat": None, "channel": "X",
                 "data_status": "SYNTHETIC_DEMO", "customer_id": o["customer"], "customer_name": o["customer"],
                 "lines": [{"part_number": l["part_number"], "name": l["name"], "quantity": l["quantity"], "stock": 10, "allocated": bool(l["allocated_from"]), "fits": ["M-1"]} for l in o["lines"]],
                 "shipments": [s["status"] for s in o["shipments"]]}
                for k, o in self.orders_.items() if customer_id is None or o["customer"] == customer_id]

    def owner(self, order_id):
        o = self.orders_.get(order_id)
        return {"status": o["status"], "customer_id": o["customer"]} if o else None

    def detail(self, order_id):
        o = self.orders_.get(order_id)
        if not o:
            return None
        return {"o": {"order_id": order_id, "order_date": "2026-10-01", "order_status": o["status"], "currency": "EUR", "subtotal_ex_vat": 50.0, "data_status": "SYNTHETIC_DEMO"},
                "customer": {"customer_id": o["customer"], "name": o["customer"]}, "address": None, "lines": copy.deepcopy(o["lines"]),
                "shipments": copy.deepcopy(o["shipments"]), "history": copy.deepcopy(o["history"])}

    def create_request(self, order_id, customer_id, lines, **_):
        self.writes += 1
        self.orders_[order_id] = {"customer": customer_id, "status": "NEW", "lines": [line(self._pn(l["part_id"]), qty=l["quantity"]) for l in lines], "shipments": [], "history": []}

    def _pn(self, part_id):
        return part_id.removeprefix("P-")

    def status_event(self, order_id, previous, status, action, user_id, user_name, role, at, today):
        o = self.orders_[order_id]
        if o["status"] != previous:
            return False
        self.writes += 1
        o["history"].append({"sequence": len(o["history"]) + 1, "order_status": status, "previous_status": previous, "action": action,
                             "actor_name": user_name, "actor_role": role, "occurred_at": at, "data_status": "USER_PROVIDED"})
        o["status"] = status
        return True

    def allocate(self, order_line_id, warehouse_id, today):
        self.allocations.append((order_line_id, warehouse_id))

    def cart(self, cart_id):
        return [{"part_id": k, "quantity": v} for k, v in self.carts.get(cart_id, {}).items()]

    def put_cart(self, cart_id, lines, **_):
        self.carts[cart_id] = {l["part_id"]: l["quantity"] for l in lines}

    def clear_cart(self, cart_id):
        self.carts[cart_id] = {}

    def parts(self, part_ids):
        from app.schemas.catalogue import Availability, Money, PartSummary

        return [PartSummary(part_id=p, part_number=p.removeprefix("P-"), name=p, fitment=[],
                            price=Money(amount=25.0, currency="EUR"), availability=Availability(state="IN_STOCK", orderable=not p.endswith("BAD"), part_status="VERIFIED" if not p.endswith("BAD") else "UNVERIFIED"))
                for p in part_ids]


@pytest.fixture()
def repo():
    r = FakeRepo()
    app.dependency_overrides[get_orders_repository] = lambda: r
    yield r
    app.dependency_overrides.pop(get_orders_repository, None)


def client(user_id=None):
    c = TestClient(app)
    if user_id:
        assert c.post("/api/v1/auth/login", json={"user_id": user_id}).status_code == 200
    return c


# ── session and role resolution ──────────────────────────────────────────────────────────────────
def test_session_tokens_are_signed_and_expire():
    token = sign("U-ANNA", "secret", now=1000)
    assert verify(token, "secret", now=1001) == "U-ANNA"
    assert verify(token, "other", now=1001) is None  # wrong key
    assert verify(token.replace(".", "x."), "secret", now=1001) is None  # tampered
    assert verify(token, "secret", now=1000 + 13 * 3600) is None  # expired


def test_me_resolves_the_role_on_the_backend(repo):
    assert client().get("/api/v1/me").status_code == 401
    me = client("U-ANNA").get("/api/v1/me").json()
    assert me["role"] == "END_USER" and me["customer"] == "Customer One" and "orders.process" not in me["permissions"]
    assert client("U-JANE").get("/api/v1/me").json()["role"] == "ORDER_PROCESSOR"
    assert client().post("/api/v1/auth/login", json={"user_id": "NOBODY"}).status_code == 401


def test_a_role_sent_by_the_browser_is_ignored(repo):
    c = client("U-ANNA")
    c.headers["X-Role"] = "ORDER_PROCESSOR"
    assert c.post("/api/v1/orders/O-1/status", json={"status": "CONFIRMED"}).status_code == 403


def test_the_permission_matrix_has_no_engineering_or_admin_rights():
    every = PERMISSIONS[Role.END_USER] | PERMISSIONS[Role.ORDER_PROCESSOR]
    assert not any(p.startswith(("catalogue.write", "fitment.", "price.write", "inventory.write", "supplier.write", "provenance.", "admin")) for p in every)
    assert "orders.update_status" not in PERMISSIONS[Role.END_USER] and "requests.create" not in PERMISSIONS[Role.ORDER_PROCESSOR]


# ── END_USER ─────────────────────────────────────────────────────────────────────────────────────
def test_end_user_sees_only_their_own_orders(repo):
    c = client("U-ANNA")
    ids = {o["order_id"] for o in c.get("/api/v1/orders").json()}
    assert ids == {"O-1", "O-3", "O-4", "O-5"} and "O-2" not in ids
    assert all("customer" not in o for o in c.get("/api/v1/orders").json())  # no other customers, no queue fields


def test_end_user_cannot_view_another_customers_order(repo):
    assert client("U-ANNA").get("/api/v1/orders/O-2").status_code == 403
    assert client("U-ANNA").get("/api/v1/orders/NOPE").status_code == 404


def test_end_user_order_detail_has_no_processor_controls_or_internal_data(repo):
    d = client("U-ANNA").get("/api/v1/orders/O-1").json()
    assert "next" not in d and "customer" not in d and "delivery_address" not in d
    assert "warehouses" not in d["lines"][0] and "suppliers" not in d["lines"][0]
    assert d["lines"][0]["fitment"][0]["status"] == "CONFIRMED" and "No payment has been taken" in d["payment"]


def test_end_user_cannot_process_or_update_status(repo):
    c = client("U-ANNA")
    assert c.post("/api/v1/orders/O-1/status", json={"status": "CONFIRMED"}).status_code == 403
    assert repo.orders_["O-1"]["status"] == "NEW" and repo.writes == 0


def test_end_user_cart_is_server_side_and_their_own(repo):
    anna, lars = client("U-ANNA"), client("U-LARS")
    assert anna.put("/api/v1/me/cart", json={"lines": [{"part_id": "P-AB-1", "quantity": 2}, {"part_id": "P-AB-1", "quantity": 1}]}).json() == [{"partId": "P-AB-1", "qty": 3}]
    assert lars.get("/api/v1/me/cart").json() == []
    assert anna.get("/api/v1/me/cart").json() == [{"partId": "P-AB-1", "qty": 3}]
    assert client().get("/api/v1/me/cart").status_code == 401


def test_end_user_can_submit_and_review_a_purchase_request_idempotently(repo):
    c = client("U-ANNA")
    body = {"items": [{"part_id": "P-AB-9", "quantity": 2}], "idempotency_key": "cart-0001-key"}
    first = c.post("/api/v1/requests", json=body)
    assert first.status_code == 201
    d = first.json()
    assert d["status"] == "NEW" and d["status_label"] == "Pending review" and d["lines"][0]["quantity"] == 2
    assert "No payment has been taken" in d["payment"]
    again = c.post("/api/v1/requests", json=body).json()
    assert again["order_id"] == d["order_id"] and sum(1 for k in repo.orders_ if k.startswith("ORD-R")) == 1  # no duplicate
    assert d["order_id"] in {o["order_id"] for o in c.get("/api/v1/orders").json()}
    assert client("U-LARS").get(f"/api/v1/orders/{d['order_id']}").status_code == 403


def test_submitting_a_request_consumes_the_server_cart_and_leaves_history_alone(repo):
    anna, lars = client("U-ANNA"), client("U-LARS")
    anna.put("/api/v1/me/cart", json={"lines": [{"part_id": "P-AB-9", "quantity": 2}]})
    lars.put("/api/v1/me/cart", json={"lines": [{"part_id": "P-AB-7", "quantity": 1}]})
    before = {k: dict(v) for k, v in repo.orders_.items() if not k.startswith("ORD-R")}
    first = anna.post("/api/v1/requests", json={"items": [{"part_id": "P-AB-9", "quantity": 2}], "idempotency_key": "cart-0004-key"})
    assert first.status_code == 201
    assert anna.get("/api/v1/me/cart").json() == []  # the submitted cart is not an active cart any more
    assert lars.get("/api/v1/me/cart").json() == [{"partId": "P-AB-7", "qty": 1}]  # nobody else's cart is touched
    order = first.json()["order_id"]
    assert anna.get(f"/api/v1/orders/{order}").json()["lines"][0]["quantity"] == 2  # the request and its lines remain
    assert {k: dict(v) for k, v in repo.orders_.items() if not k.startswith("ORD-R")} == before  # earlier orders and history unchanged
    anna.put("/api/v1/me/cart", json={"lines": [{"part_id": "P-AB-3", "quantity": 1}]})  # a new cart starts clean and is kept
    assert anna.get("/api/v1/me/cart").json() == [{"partId": "P-AB-3", "qty": 1}]


def test_a_rejected_request_leaves_the_cart_in_place(repo):
    anna = client("U-ANNA")
    anna.put("/api/v1/me/cart", json={"lines": [{"part_id": "P-XBAD", "quantity": 1}]})
    assert anna.post("/api/v1/requests", json={"items": [{"part_id": "P-XBAD", "quantity": 1}], "idempotency_key": "cart-0005-key"}).status_code == 409
    assert anna.get("/api/v1/me/cart").json() == [{"partId": "P-XBAD", "qty": 1}]  # nothing was consumed


def test_a_request_accepts_only_verified_orderable_priced_parts(repo):
    r = client("U-ANNA").post("/api/v1/requests", json={"items": [{"part_id": "P-XBAD", "quantity": 1}], "idempotency_key": "cart-0002-key"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_orderable"


def test_end_user_cannot_call_processor_endpoints_and_processor_cannot_shop_as_a_customer(repo):
    assert client("U-JANE").post("/api/v1/requests", json={"items": [{"part_id": "P-AB-1", "quantity": 1}], "idempotency_key": "cart-0003-key"}).status_code == 403
    assert client("U-JANE").get("/api/v1/me/cart").status_code == 403


# ── ORDER_PROCESSOR ──────────────────────────────────────────────────────────────────────────────
def test_processor_sees_the_whole_queue_in_sections(repo):
    q = client("U-JANE").get("/api/v1/orders").json()
    assert len(q) == 5 and {o["queue"] for o in q} == {"pending_review", "needs_fulfilment", "ready_to_ship"} and all("customer" in o for o in q)


def test_processor_detail_shows_fitment_inventory_supplier_fulfilment_and_the_next_step(repo):
    d = client("U-JANE").get("/api/v1/orders/O-1").json()
    l = d["lines"][0]
    assert l["fitment"][0]["status"] == "CONFIRMED" and l["warehouses"][0]["available"] == 10 and l["suppliers"][0]["lead_time_days"] == 10
    assert l["fulfilment"] == "Available from stock" and l["evidence"]["inventory"] == "SYNTHETIC_DEMO"
    assert d["next"] == {"status": "CONFIRMED", "label": "Confirmed", "allowed": True, "reason": None} and d["customer"]["customer_id"] == "C-1"


def test_processor_can_move_an_order_one_valid_step_and_it_is_audited(repo):
    r = client("U-JANE").post("/api/v1/orders/O-1/status", json={"status": "CONFIRMED", "expected_status": "NEW"})
    assert r.status_code == 200 and r.json()["status"] == "CONFIRMED"
    event = repo.orders_["O-1"]["history"][-1]
    assert event["previous_status"] == "NEW" and event["order_status"] == "CONFIRMED" and event["actor_name"] == "Jane" and event["actor_role"] == "ORDER_PROCESSOR"
    assert event["occurred_at"] and event["action"] == "status_change:NEW->CONFIRMED"


@pytest.mark.parametrize("order,target,code", [
    ("O-1", "DELIVERED", "invalid_transition"),     # skipping steps
    ("O-4", "NEW", "invalid_transition"),           # going back
    ("O-1", "PAID", "invalid_status"),              # not a status in the vocabulary
    ("O-5", "CONFIRMED", "transition_blocked"),     # part not verified: confirmation needs the catalogue's order gate
    ("O-3", "ALLOCATED", "transition_blocked"),     # 50 needed, 10 recorded: stock cannot be invented
    ("O-4", "SHIPPED", "transition_blocked"),       # no shipment recorded: none is fabricated
])
def test_invalid_or_unsupported_transitions_are_rejected(repo, order, target, code):
    before = repo.orders_[order]["status"]
    r = client("U-JANE").post(f"/api/v1/orders/{order}/status", json={"status": target})
    assert r.status_code == 409 and r.json()["error"]["code"] == code
    assert repo.orders_[order]["status"] == before and repo.writes == 0


def test_a_stale_status_is_rejected(repo):
    r = client("U-JANE").post("/api/v1/orders/O-1/status", json={"status": "CONFIRMED", "expected_status": "PROCESSING"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale_status"


def test_allocation_links_a_warehouse_with_enough_stock_and_never_changes_stock(repo):
    repo.orders_["O-6"] = {"customer": "C-1", "status": "PROCESSING", "lines": [line("AB-6", qty=4, stock=10)], "shipments": [], "history": []}
    r = client("U-JANE").post("/api/v1/orders/O-6/status", json={"status": "ALLOCATED"})
    assert r.status_code == 200 and repo.allocations == [("L-AB-6", "WH-1")]
    assert repo.orders_["O-6"]["lines"][0]["warehouses"][0]["available"] == 10


def test_the_flow_matches_the_graph_vocabulary():
    assert FLOW == ["NEW", "CONFIRMED", "PROCESSING", "ALLOCATED", "SHIPPED", "DELIVERED"] and "DELIVERED" not in TRANSITIONS


def test_no_endpoint_edits_engineering_facts_inventory_or_prices(repo):
    c = client("U-JANE")
    for method, path in [("put", "/api/v1/parts/AB-1"), ("post", "/api/v1/parts/AB-1/fitment"), ("post", "/api/v1/parts/AB-1/inventory"),
                         ("put", "/api/v1/intelligence/parts/AB-1"), ("post", "/api/v1/prices")]:
        assert getattr(c, method)(path, json={}).status_code in (404, 405), path


# ── both roles keep the existing products ────────────────────────────────────────────────────────
graph = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")


class Scripted:
    name = "scripted"

    def parse_question(self, question, intents):
        return LLMParse("MACHINE_LIST")

    def generate_grounded_response(self, *a, **k):
        from app.llm import LLMUnavailable

        raise LLMUnavailable("not needed")

    def parse_shopping_request(self, request):
        return ShoppingParse(True, machine="NV-3200", part_type="air filter")


@graph
@pytest.mark.parametrize("user", ["U-ANNA", "U-JANE"])
def test_both_roles_can_use_catalogue_parts_intelligence_and_shopping(repo, user):
    app.dependency_overrides[get_llm] = lambda: Scripted()
    try:
        c = client(user)
        assert c.get("/api/v1/parts", params={"limit": 1}).status_code == 200
        assert c.post("/api/v1/intelligence/query", json={"question": "What machines are available?"}).json()["intent"] == "MACHINE_LIST"
        assert c.post("/api/v1/agent/recommend", json={"request": "air filter for NV-3200"}).json()["state"] == "recommendation"
    finally:
        app.dependency_overrides.pop(get_llm, None)
