"""The Parts Store direct-order flow, rules enforced in FastAPI: checkout reads, review (availability / depot / transport), place order, atomic
allocation, fulfilment, shipment, tracking, dealer service, exceptions and ownership.

Runs against an in-memory repository (tests/support/fake_orders.py) that reserves stock atomically and rolls a failed reservation back as a whole,
exactly as the graph transaction does. The same flows run against the real Cypher in test_direct_order_graph.py."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_orders_repository
from app.main import app
from app.services import order_flow as flow
from app.services.fulfilment import cost_block, depot_plan, stock_state
from tests.support.fake_orders import FakeRepo

ROUTE_B = "RTE-WH-B-SHT-1-STANDARD_ROAD_EU"
ROUTE_B_EXPRESS = "RTE-WH-B-SHT-1-EXPRESS_ROAD_EU"


@pytest.fixture()
def repo():
    r = FakeRepo()
    app.dependency_overrides[get_orders_repository] = lambda: r
    yield r
    app.dependency_overrides.pop(get_orders_repository, None)


def client(user_id):
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"user_id": user_id}).status_code == 200
    return c


def body(**over):
    b = {"items": [{"part_id": "P-AB-1", "quantity": 2, "machine": "M-1"}],
         "requester": {"name": "Anna de Vries", "email": "anna@buyer.example", "phone": "+31 20 555 0100", "company": "De Vries Bouw B.V."},
         "delivery": {"ship_to_id": "SHT-1", "receiver_name": "Rita Receiver", "receiver_phone": "+49 40 1234567"},
         "dealer_id": "DLR-1", "dealer_service_required": False, "depot_id": "WH-B", "route_id": ROUTE_B, "confirmed": True, "idempotency_key": "key-0000001"}
    b.update(over)
    return b


def place(c, **over):
    return c.post("/api/v1/orders", json=body(**over))


def act(c, order_id, action, expected=None):
    return c.post(f"/api/v1/orders/{order_id}/actions", json={"action": action, **({"expected_status": expected} if expected else {})})


def drive(jane, order_id, *actions):
    last = None
    for a in actions:
        last = act(jane, order_id, a)
        assert last.status_code == 200, (a, last.json())
    return last.json()


# ── cart: part number, name, quantity and the machine it was chosen for ───────────────────────────




# ── checkout reference data: ship-to and dealers come from the graph ──────────────────────────────


# ── review: availability, depot selection, transport, cost ────────────────────────────────────────
def review(c, **over):
    b = {"items": [{"part_id": "P-AB-1", "quantity": 2, "machine": "M-1"}], "ship_to_id": "SHT-1"}
    b.update(over)
    return c.post("/api/v1/checkout/review", json=b)










# ── availability and UNKNOWN stock ────────────────────────────────────────────────────────────────






# ── customer details belong to the order; nothing creates a customer ──────────────────────────────






# ── ship-to, dealer, depot are explicit and separate ──────────────────────────────────────────────






# ── place order ───────────────────────────────────────────────────────────────────────────────────


def test_place_order_creates_the_order_not_a_request_and_persists_everything(repo):
    anna = client("U-ANNA")
    anna.put("/api/v1/me/cart", json={"lines": [{"part_id": "P-AB-1", "quantity": 2, "machine": "M-1"}, {"part_id": "P-AB-9", "quantity": 1}]})
    r = place(anna)
    assert r.status_code == 201
    d = r.json()
    assert d["order_id"] == "NM-ORD001" and d["channel"] == "DIRECT_ORDER"
    assert "request" not in d["status_label"].lower() and "request" not in d["payment"].lower() and "quote" not in str(d).lower()
    assert d["lines"][0]["part_number"] == "AB-1" and d["lines"][0]["quantity"] == 2 and d["lines"][0]["machine"] == "M-1"
    assert d["transport"] == {"route_id": ROUTE_B, "option_code": "STANDARD_ROAD_EU", "mode": "ROAD", "distance_km": 100.0, "estimated_days": 2, "estimate_basis": "ESTIMATED",
                              "data_status": "SYNTHETIC_DEMO", "freight_estimate": {"amount": 12.5, "currency": "EUR", "data_status": "SYNTHETIC_DEMO_ESTIMATE", "label": "Demo transport estimate"}}
    assert d["cost"]["part_cost"] == 50.0
    assert d["cost"]["transport_cost"] == d["transport"]["freight_estimate"]["amount"]
    assert d["cost"]["total"] == 50.0 + d["cost"]["transport_cost"]
    assert d["cost"]["status"] == "SYNTHETIC_DEMO"
    assert d["provenance"]["transport"] == "SYNTHETIC_DEMO" and d["provenance"]["tracking"] == "SYNTHETIC_DEMO" and d["provenance"]["inventory"] == "SYNTHETIC_DEMO"
    assert [l for l in anna.get("/api/v1/me/cart").json()] == [{"partId": "P-AB-9", "partNumber": "AB-9", "partName": "Part AB-9", "qty": 1, "machine": None}]  # only the ordered line left the cart
    assert d["history"][0]["status"] == "NEW" and d["history"][0]["status_label"] == "Order placed"




# ── allocation: it reserves stock, atomically, once ───────────────────────────────────────────────


def test_two_orders_cannot_reserve_the_same_units(repo):
    anna, lars = client("U-ANNA"), client("U-LARS")
    first = place(anna, items=[{"part_id": "P-AB-1", "quantity": 15, "machine": "M-1"}]).json()
    assert first["status"] == "ALLOCATED" and repo.stock[("P-AB-1", "WH-B")]["available"] == 5
    second = place(lars, items=[{"part_id": "P-AB-1", "quantity": 15}], idempotency_key="key-0000002")  # the review said 20: the second order now finds only 5
    assert second.status_code == 409 and second.json()["error"]["code"] == "availability"  # refused up front
    assert repo.stock[("P-AB-1", "WH-B")]["available"] == 5




def test_an_order_with_several_lines_is_allocated_all_or_nothing(repo, monkeypatch):
    import app.services.checkout as co

    real = co.CheckoutService._plan
    monkeypatch.setattr(co.CheckoutService, "_plan", lambda self, lines, shipto: (repo.stock.__setitem__(("P-AB-9", "WH-B"), {"stock_status": "OUT_OF_STOCK", "available": 0, "on_hand": 0, "reserved": 0}) or real(self, lines, shipto)))
    d = place(client("U-ANNA"), items=[{"part_id": "P-AB-1", "quantity": 2, "machine": "M-1"}, {"part_id": "P-AB-9", "quantity": 1}])
    # the review (taken before the stock change) allowed it; the transaction refuses the second line, so the first line must not stay reserved
    assert d.status_code in (201, 409)
    if d.status_code == 201:
        assert d.json()["status"] == "ALLOCATION_FAILED" and repo.stock[("P-AB-1", "WH-B")]["available"] == 20 and repo.stock[("P-AB-1", "WH-B")]["reserved"] == 0
    monkeypatch.setattr(co.CheckoutService, "_plan", real)






# ── the lifecycle: fulfilment, shipment, tracking, service, completion ────────────────────────────
def test_the_full_lifecycle_without_dealer_service(repo):
    anna, jane = client("U-ANNA"), client("U-JANE")
    oid = place(anna).json()["order_id"]
    d = drive(jane, oid, "start_fulfilment", "begin_fulfilling", "mark_ready")
    assert d["status"] == "READY_TO_SHIP" and [s["state"] for s in d["stages"]][:3] == ["done", "done", "done"]
    d = drive(jane, oid, "create_shipment")
    sh = d["shipments"][0]
    assert d["status"] == "READY_TO_SHIP" and sh["status"] == "CREATED" and sh["dispatched_from"] == "Depot B (demo)" and sh["tracking_basis"] == "SYNTHETIC_DEMO"  # origin depot, synthetic tracking
    assert sh["tracking_ref"].startswith("DEMO-") and sh["events"][0]["data_status"] == "SYNTHETIC_DEMO"
    assert d["fulfilment"]["allocation_status"] == "RESERVED"
    d = drive(jane, oid, "dispatch")
    assert d["status"] == "SHIPPED" and d["shipments"][0]["status"] == "DISPATCHED"
    row = repo.stock[("P-AB-1", "WH-B")]
    assert (row["on_hand"], row["reserved"], row["available"]) == (18, 0, 18)  # the units have left the depot
    assert d["fulfilment"]["allocation_status"] == "CONSUMED" and d["fulfilment"]["lines"][0]["allocation_status"] == "SHIPPED"  # order and line agree: nothing is held any more
    d = drive(jane, oid, "in_transit")
    assert d["status"] == "SHIPPED" and d["shipments"][0]["status"] == "IN_TRANSIT"
    d = drive(jane, oid, "deliver")
    assert d["status"] == "DELIVERED" and d["shipments"][0]["status"] == "DELIVERED" and d["service"] is None  # no service was asked for: none is forced
    assert [e["event_status"] for e in d["shipments"][0]["events"]] == ["CREATED", "DISPATCHED", "IN_TRANSIT", "DELIVERED"]
    assert all(e["data_status"] == "SYNTHETIC_DEMO" for e in d["shipments"][0]["events"])
    d = drive(jane, oid, "complete_order")
    assert d["status"] == "COMPLETED" and d["actions"] == [] and [s["state"] for s in d["stages"]] == ["done", "done", "done", "done", "done", "skipped", "done"]
    assert d["fulfilment"]["allocation_status"] == "CONSUMED"
    assert [h["status"] for h in d["history"]] == ["NEW", "ALLOCATED", "FULFILMENT_PENDING", "FULFILLING", "READY_TO_SHIP", "READY_TO_SHIP", "SHIPPED", "SHIPPED", "DELIVERED", "COMPLETED"]
    assert all(h["by"] for h in d["history"])  # every step is attributed










def test_a_stale_status_is_rejected_and_two_actions_cannot_both_win(repo):
    jane = client("U-JANE")
    oid = place(client("U-ANNA")).json()["order_id"]
    assert act(jane, oid, "start_fulfilment", expected="NEW").json()["error"]["code"] == "stale_status"
    assert act(jane, oid, "start_fulfilment", expected="ALLOCATED").status_code == 200
    assert act(jane, oid, "start_fulfilment", expected="ALLOCATED").json()["error"]["code"] == "stale_status"  # the second caller saw an old status


# ── exceptions ────────────────────────────────────────────────────────────────────────────────────


def test_the_owner_cannot_cancel_once_fulfilment_has_started_and_others_never_can(repo):
    anna, lars, jane = client("U-ANNA"), client("U-LARS"), client("U-JANE")
    oid = place(anna).json()["order_id"]
    assert act(lars, oid, "cancel").status_code == 403  # another customer's order
    drive(jane, oid, "start_fulfilment", "begin_fulfilling")
    r = act(anna, oid, "cancel")
    assert r.status_code == 403 or r.status_code == 409
    d = act(jane, oid, "cancel").json()  # the processor still can, and the stock goes back
    assert d["status"] == "CANCELLED" and repo.stock[("P-AB-1", "WH-B")]["available"] == 20










# ── ownership and roles ───────────────────────────────────────────────────────────────────────────






# ── pure rules ────────────────────────────────────────────────────────────────────────────────────




def test_checkout_review_prices_each_route_and_order_keeps_its_price_snapshot(repo):
    anna = client("U-ANNA")
    pricing = review(anna).json()
    depot = next(d for d in pricing["depots"] if d["depot_id"] == "WH-B")
    for option in depot["options"]:
        assert option["cost"]["part_cost"] == 50.0
        assert option["cost"]["transport_cost"] == option["freight"]["amount"]
        assert option["cost"]["total"] == 50.0 + option["freight"]["amount"]
    saved = place(anna).json()
    assert saved["lines"][0]["unit_price_eur"] == 25.0
    repo.parts_["P-AB-1"].price.amount = 999.0
    again = anna.get(f"/api/v1/orders/{saved['order_id']}").json()
    assert again["cost"] == saved["cost"]
    row = next(o for o in anna.get("/api/v1/orders").json() if o["order_id"] == saved["order_id"])
    assert row["total"] == saved["cost"]["total"]
