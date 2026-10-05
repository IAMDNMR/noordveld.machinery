"""End User and Order Processor: authentication, permissions, ownership, the status state machine and its audit trail.

The order workflow runs against an in-memory repository (no demo order in AuraDB is changed by the suite); catalogue, Parts
Intelligence and Agentic Shopping run against the live graph when it is configured, as in the other API tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_llm, get_orders_repository
from app.core.config import get_settings
from app.core.roles import PERMISSIONS, Role
from app.core.session import sign, verify
from app.llm import LLMParse, ShoppingParse
from app.main import app
from app.services.orders import FLOW, TRANSITIONS


from tests.support.fake_orders import FakeRepo, line  # noqa: E402


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
    assert "orders.update_status" not in PERMISSIONS[Role.END_USER] and "orders.place" not in PERMISSIONS[Role.ORDER_PROCESSOR]


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
    assert anna.put("/api/v1/me/cart", json={"lines": [{"part_id": "P-AB-1", "quantity": 2}, {"part_id": "P-AB-1", "quantity": 1}]}).json() == [{"partId": "P-AB-1", "partNumber": "AB-1", "partName": "Part AB-1", "qty": 3, "machine": None}]
    assert lars.get("/api/v1/me/cart").json() == []
    assert anna.get("/api/v1/me/cart").json()[0]["qty"] == 3
    assert client().get("/api/v1/me/cart").status_code == 401











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
    repo.orders_["O-6"] = {"channel": "DEMO_WEB_STORE", "user": None, "customer": "C-1", "status": "PROCESSING", "lines": [line("AB-6", qty=4, stock=10)], "shipments": [], "history": []}
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
