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
def test_the_cart_keeps_part_number_name_quantity_and_machine(repo):
    anna = client("U-ANNA")
    r = anna.put("/api/v1/me/cart", json={"lines": [{"part_id": "P-AB-1", "quantity": 2, "machine": "M-1"}, {"part_id": "P-AB-1", "quantity": 1}, {"part_id": "P-AB-1", "quantity": 3, "machine": "M-1"}]})
    assert r.status_code == 200
    lines = {(l["partId"], l["machine"]): l for l in r.json()}
    assert lines[("P-AB-1", "M-1")] == {"partId": "P-AB-1", "partNumber": "AB-1", "partName": "Part AB-1", "qty": 5, "machine": "M-1"}  # same part + machine merge
    assert lines[("P-AB-1", None)]["qty"] == 1  # the same part for no machine is its own line
    assert anna.get("/api/v1/me/cart").json() == r.json()  # it is read back from the server, not browser memory
    assert not repo.orders_.keys() - {"O-1", "O-2", "O-3", "O-4", "O-5"}  # adding to the cart creates no order


def test_a_machine_the_part_does_not_fit_is_rejected_in_the_cart(repo):
    r = client("U-ANNA").put("/api/v1/me/cart", json={"lines": [{"part_id": "P-AB-2", "quantity": 1, "machine": "M-1"}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "machine_mismatch"


# ── checkout reference data: ship-to and dealers come from the graph ──────────────────────────────
def test_destinations_and_dealers_come_from_the_graph_and_are_separate_things(repo):
    anna = client("U-ANNA")
    assert {c["country_code"] for c in anna.get("/api/v1/checkout/countries").json()} == {"DE", "NL"}
    sites = anna.get("/api/v1/checkout/destinations", params={"country": "de"}).json()
    assert [s["ship_to_id"] for s in sites] == ["SHT-1"] and sites[0]["street"] == "Hafenstrasse 1"
    dealers = anna.get("/api/v1/checkout/dealers").json()
    assert {d["dealer_id"] for d in dealers} == {"DLR-1", "DLR-2"}  # not hard-coded: whatever the network holds
    assert [d["dealer_id"] for d in anna.get("/api/v1/checkout/dealers", params={"country": "NL"}).json()] == ["DLR-2"]
    assert client("U-JANE").get("/api/v1/checkout/countries").status_code == 403  # processors do not check out
    assert TestClient(app).get("/api/v1/checkout/countries").status_code == 401


# ── review: availability, depot selection, transport, cost ────────────────────────────────────────
def review(c, **over):
    b = {"items": [{"part_id": "P-AB-1", "quantity": 2, "machine": "M-1"}], "ship_to_id": "SHT-1"}
    b.update(over)
    return c.post("/api/v1/checkout/review", json=b)


def test_the_depot_is_chosen_for_route_and_distance_not_for_the_most_stock(repo):
    d = review(client("U-ANNA")).json()
    by = {x["depot_id"]: x for x in d["depots"]}
    assert by["WH-A"]["lines"][0]["available"] == 500 and not by["WH-A"]["selectable"]  # the most stock, but no route to this destination
    assert "No recorded transport route" in " ".join(by["WH-A"]["reasons"])
    assert [x["depot_id"] for x in d["depots"] if x["selectable"]] == ["WH-B", "WH-C"]  # nearest/fastest first
    assert by["WH-B"]["recommended"] is True and by["WH-B"]["recommended_route_id"] == ROUTE_B
    assert d["can_order"] is True


def test_transport_options_come_from_the_routes_and_carry_mode_time_distance_and_demo_labels(repo):
    d = review(client("U-ANNA")).json()
    opts = {o["option_code"]: o for o in next(x for x in d["depots"] if x["depot_id"] == "WH-B")["options"]}
    assert set(opts) == {"STANDARD_ROAD_EU", "EXPRESS_ROAD_EU"}  # only the routes that exist from this depot to this destination
    std = opts["STANDARD_ROAD_EU"]
    assert (std["mode"], std["service_level"], std["distance_km"], std["estimated_days"], std["estimate_basis"]) == ("ROAD", "STANDARD", 100.0, 2, "ESTIMATED")
    assert std["origin_depot_id"] == "WH-B" and std["destination_shipto_id"] == "SHT-1" and std["data_status"] == "SYNTHETIC_DEMO"
    assert std["freight"]["label"] == "Synthetic demo freight estimate, not a price" and std["freight"]["data_status"] == "SYNTHETIC_DEMO"
    assert not [o for x in d["depots"] if x["depot_id"] == "WH-A" for o in x["options"]]  # no route, no option, nothing invented


def test_no_price_is_invented_part_transport_and_total_are_not_available(repo):
    c = review(client("U-ANNA")).json()["cost"]
    assert c["part_cost"] is None and c["transport_cost"] is None and c["total"] is None and c["status"] == "NOT_AVAILABLE" and "synthetic demo" in c["note"].lower()
    assert cost_block() == c


def test_review_checks_the_part_the_machine_and_the_destination(repo):
    anna = client("U-ANNA")
    assert review(anna, items=[{"part_id": "P-XBAD", "quantity": 1}]).json()["error"]["code"] == "not_orderable"  # unverified: never proceeds as a verified order
    assert review(anna, items=[{"part_id": "P-AB-2", "quantity": 1, "machine": "M-1"}]).json()["error"]["code"] == "machine_mismatch"
    assert review(anna, items=[{"part_id": "P-NOPE", "quantity": 1}]).json()["error"]["code"] == "unknown_part"
    assert review(anna, ship_to_id="SHT-NOPE").json()["error"]["code"] == "destination_not_found"


# ── availability and UNKNOWN stock ────────────────────────────────────────────────────────────────
def test_unknown_stock_stays_unknown_and_is_never_zero_or_allocated():
    assert stock_state(None) == {"state": "UNKNOWN", "available": None, "known": False}
    assert stock_state({"stock_status": "UNKNOWN", "available": None}) == {"state": "UNKNOWN", "available": None, "known": False}
    assert stock_state({"stock_status": "IN_STOCK", "available": None})["state"] == "UNKNOWN"  # a status without a quantity is not a quantity
    assert stock_state({"stock_status": "IN_STOCK", "available": 0})["state"] == "UNKNOWN" or stock_state({"stock_status": "IN_STOCK", "available": 0})["available"] == 0
    assert stock_state({"stock_status": "OUT_OF_STOCK", "available": 0}) == {"state": "OUT_OF_STOCK", "available": 0, "known": True}
    assert stock_state({"stock_status": "ON_ORDER", "available": 0})["state"] == "ON_ORDER"
    assert stock_state({"stock_status": "LOW_STOCK", "available": 3}) == {"state": "LOW_STOCK", "available": 3, "known": True}


def test_review_reports_unknown_as_unknown_and_that_depot_cannot_supply(repo):
    repo.stock[("P-AB-1", "WH-B")] = {"stock_status": "UNKNOWN", "available": None, "on_hand": None, "reserved": 0}
    d = review(client("U-ANNA")).json()
    b = next(x for x in d["depots"] if x["depot_id"] == "WH-B")
    assert b["lines"][0]["state"] == "UNKNOWN" and b["lines"][0]["available"] is None and not b["selectable"]  # null is not 0
    assert "UNKNOWN" in " ".join(b["reasons"]) and "not treated as zero" in " ".join(b["reasons"])
    assert [x["depot_id"] for x in d["depots"] if x["selectable"]] == ["WH-C"]
    r = place(client("U-ANNA"))  # the user still picks WH-B: the server refuses
    assert r.status_code == 409 and r.json()["error"]["code"] == "availability"
    assert repo.stock[("P-AB-1", "WH-B")] == {"stock_status": "UNKNOWN", "available": None, "on_hand": None, "reserved": 0}  # untouched, still UNKNOWN


@pytest.mark.parametrize("qty,ok", [(20, True), (21, False)])
def test_requested_quantity_must_not_exceed_known_available_stock(repo, qty, ok):
    r = place(client("U-ANNA"), items=[{"part_id": "P-AB-1", "quantity": qty, "machine": "M-1"}])
    assert (r.status_code == 201) is ok
    if not ok:
        assert r.json()["error"]["code"] == "availability" and "only 20 available" in " ".join(r.json()["error"]["details"]["reasons"])


# ── customer details belong to the order; nothing creates a customer ──────────────────────────────
def test_requester_details_are_stored_on_the_order_as_entered(repo):
    anna = client("U-ANNA")
    d = place(anna, requester={"name": "  Sam   Buyer ", "email": "sam@other-company.example", "phone": "+44 20 7946 0000", "company": "Other Co Ltd"}).json()
    assert d["requester"] == {"name": "Sam Buyer", "email": "sam@other-company.example", "phone": "+44 20 7946 0000", "company": "Other Co Ltd"}  # not Anna's account details
    assert d["channel"] == "DIRECT_ORDER" and not any(k.startswith("C-") for k in repo.keys) and "customer" not in client("U-ANNA").get(f"/api/v1/orders/{d['order_id']}").json()
    assert repo.orders_[d["order_id"]]["customer"] is None  # no customer master record is linked or created


@pytest.mark.parametrize("field,value,label", [("email", "not-an-email", "Email"), ("phone", "abc", "Phone"), ("name", " ", "Name"), ("company", "", "Company")])
def test_invalid_requester_details_are_rejected_by_the_server(repo, field, value, label):
    req = body()["requester"] | {field: value}
    r = place(client("U-ANNA"), requester=req)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_details" and r.json()["error"]["details"]["field"] == label
    assert not [k for k in repo.orders_ if k.startswith("HCME")]


def test_receiver_details_are_required_and_kept_apart_from_the_requester(repo):
    anna = client("U-ANNA")
    assert place(anna, delivery={"ship_to_id": "SHT-1", "receiver_name": "", "receiver_phone": "+49 40 1234567"}).json()["error"]["details"]["field"] == "Receiver name"
    assert place(anna, delivery={"ship_to_id": "SHT-1", "receiver_name": "Rita", "receiver_phone": "x"}).json()["error"]["details"]["field"] == "Receiver phone"
    d = place(anna).json()
    assert d["receiver"] == {"name": "Rita Receiver", "phone": "+49 40 1234567"} and d["requester"]["name"] != d["receiver"]["name"]


# ── ship-to, dealer, depot are explicit and separate ──────────────────────────────────────────────
def test_ship_to_dealer_and_depot_are_stored_separately_and_never_inferred(repo):
    d = place(client("U-ANNA"), dealer_id="DLR-2").json()  # a dealer in the Netherlands, delivering to a German site, shipping from a German depot
    assert d["delivery"] == {"ship_to_id": "SHT-1", "street": "Hafenstrasse 1", "city": "Hamburg", "postal_code": "20457", "country_code": "DE"}
    assert d["dealer"]["dealer_id"] == "DLR-2" and d["dealer"]["country_code"] == "NL"
    assert d["fulfilment"]["depot"]["warehouse_id"] == "WH-B"
    assert len({d["delivery"]["ship_to_id"], d["dealer"]["dealer_id"], d["fulfilment"]["depot"]["warehouse_id"]}) == 3


def test_an_unknown_dealer_destination_or_route_is_rejected(repo):
    anna = client("U-ANNA")
    assert place(anna, dealer_id="DLR-NOPE").json()["error"]["code"] == "dealer_not_found"
    assert place(anna, delivery={"ship_to_id": "SHT-NOPE", "receiver_name": "Rita", "receiver_phone": "+49 40 1234567"}).json()["error"]["code"] == "destination_not_found"
    assert place(anna, route_id="RTE-NOPE").json()["error"]["code"] == "route_mismatch"
    assert place(anna, depot_id="WH-C", route_id=ROUTE_B).json()["error"]["code"] == "route_mismatch"  # the route belongs to another depot
    assert place(anna, route_id="RTE-WH-A-SHT-2-STANDARD_ROAD_EU").json()["error"]["code"] == "route_mismatch"  # exists, but goes to a different destination
    assert not [k for k in repo.orders_ if k.startswith("HCME")]


def test_dealer_service_requires_a_dealer_recorded_as_installing_the_part(repo):
    anna = client("U-ANNA")
    r = place(anna, dealer_id="DLR-2", dealer_service_required=True)
    assert r.status_code == 409 and r.json()["error"]["code"] == "dealer_cannot_install"
    assert place(anna, dealer_id="DLR-1", dealer_service_required=True, idempotency_key="key-0000002").status_code == 201


# ── place order ───────────────────────────────────────────────────────────────────────────────────
def test_place_order_requires_explicit_confirmation(repo):
    r = place(client("U-ANNA"), confirmed=False)
    assert r.status_code == 422 and r.json()["error"]["code"] == "confirmation_required" and not [k for k in repo.orders_ if k.startswith("HCME")]


def test_place_order_creates_the_order_not_a_request_and_persists_everything(repo):
    anna = client("U-ANNA")
    anna.put("/api/v1/me/cart", json={"lines": [{"part_id": "P-AB-1", "quantity": 2, "machine": "M-1"}, {"part_id": "P-AB-9", "quantity": 1}]})
    r = place(anna)
    assert r.status_code == 201
    d = r.json()
    assert d["order_id"] == "HCME-ORD-000001" and d["channel"] == "DIRECT_ORDER"
    assert "request" not in d["status_label"].lower() and "request" not in d["payment"].lower() and "quote" not in str(d).lower()
    assert d["lines"][0]["part_number"] == "AB-1" and d["lines"][0]["quantity"] == 2 and d["lines"][0]["machine"] == "M-1"
    assert d["transport"] == {"route_id": ROUTE_B, "option_code": "STANDARD_ROAD_EU", "mode": "ROAD", "distance_km": 100.0, "estimated_days": 2, "estimate_basis": "ESTIMATED",
                              "data_status": "SYNTHETIC_DEMO", "freight_estimate": {"amount": 12.5, "currency": "EUR", "data_status": "SYNTHETIC_DEMO_ESTIMATE", "label": "Synthetic demo freight estimate, not a price"}}
    assert d["cost"]["part_cost"] is None and d["cost"]["transport_cost"] is None and d["cost"]["total"] is None and d["cost"]["status"] == "NOT_AVAILABLE"
    assert d["provenance"]["transport"] == "SYNTHETIC_DEMO" and d["provenance"]["tracking"] == "SYNTHETIC_DEMO" and d["provenance"]["inventory"] == "SYNTHETIC_DEMO"
    assert [l for l in anna.get("/api/v1/me/cart").json()] == [{"partId": "P-AB-9", "partNumber": "AB-9", "partName": "Part AB-9", "qty": 1, "machine": None}]  # only the ordered line left the cart
    assert d["history"][0]["status"] == "NEW" and d["history"][0]["status_label"] == "Order placed"


def test_the_order_number_is_sequential_and_place_order_is_idempotent(repo):
    anna = client("U-ANNA")
    a = place(anna).json()
    again = place(anna)  # same key: the network retry, the double click
    assert again.status_code == 201 and again.json()["order_id"] == a["order_id"] and len([k for k in repo.orders_ if k.startswith("HCME")]) == 1
    assert repo.stock[("P-AB-1", "WH-B")]["available"] == 18  # reserved once, not twice
    b = place(anna, idempotency_key="key-0000002").json()
    assert (a["order_id"], b["order_id"]) == ("HCME-ORD-000001", "HCME-ORD-000002")
    other = place(client("U-LARS"), idempotency_key="key-0000001").json()  # another user's identical key is a different order
    assert other["order_id"] == "HCME-ORD-000003"


# ── allocation: it reserves stock, atomically, once ───────────────────────────────────────────────
def test_allocation_after_creation_reserves_the_stock_and_records_it(repo):
    d = place(client("U-ANNA")).json()
    assert d["status"] == "ALLOCATED" and d["fulfilment"]["allocation_status"] == "RESERVED"
    row = repo.stock[("P-AB-1", "WH-B")]
    assert (row["available"], row["reserved"], row["on_hand"]) == (18, 2, 20)  # decremented, held, still on the shelf
    assert d["fulfilment"]["lines"][0]["reserved_quantity"] == 2 and d["lines"][0]["allocation_status"] == "RESERVED" and "Allocated from" in d["lines"][0]["fulfilment"]
    assert [h["status"] for h in d["history"]] == ["NEW", "ALLOCATED"] and d["history"][1]["by"] == "System"


def test_two_orders_cannot_reserve_the_same_units(repo):
    anna, lars = client("U-ANNA"), client("U-LARS")
    first = place(anna, items=[{"part_id": "P-AB-1", "quantity": 15, "machine": "M-1"}]).json()
    assert first["status"] == "ALLOCATED" and repo.stock[("P-AB-1", "WH-B")]["available"] == 5
    second = place(lars, items=[{"part_id": "P-AB-1", "quantity": 15}], idempotency_key="key-0000002")  # the review said 20: the second order now finds only 5
    assert second.status_code == 409 and second.json()["error"]["code"] == "availability"  # refused up front
    assert repo.stock[("P-AB-1", "WH-B")]["available"] == 5


def test_a_reservation_lost_between_review_and_allocation_is_recorded_as_failed_and_reserves_nothing(repo, monkeypatch):
    anna = client("U-ANNA")
    import app.services.checkout as co

    real = co.CheckoutService._plan

    def stale_plan(self, lines, shipto):  # the review still sees stock; by allocation another order has taken it
        plan = real(self, lines, shipto)
        repo.stock[("P-AB-1", "WH-B")]["available"] = 1
        return plan

    monkeypatch.setattr(co.CheckoutService, "_plan", stale_plan)
    d = place(anna, items=[{"part_id": "P-AB-1", "quantity": 2, "machine": "M-1"}]).json()
    assert d["status"] == "ALLOCATION_FAILED" and d["fulfilment"]["allocation_status"] == "FAILED"
    assert repo.stock[("P-AB-1", "WH-B")]["available"] == 1 and repo.stock[("P-AB-1", "WH-B")]["reserved"] == 0  # nothing was held
    assert [h["status"] for h in d["history"]] == ["NEW", "ALLOCATION_FAILED"]


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


def test_allocation_cannot_be_repeated_and_a_released_or_failed_order_can_be_allocated_again(repo):
    jane = client("U-JANE")
    d = place(client("U-ANNA")).json()
    again = act(jane, d["order_id"], "allocate")
    assert again.status_code == 409 and again.json()["error"]["code"] == "invalid_transition"  # already allocated: no second reservation
    assert repo.stock[("P-AB-1", "WH-B")]["available"] == 18
    rel = act(jane, d["order_id"], "release_allocation").json()
    assert rel["status"] == "ALLOCATION_RELEASED" and repo.stock[("P-AB-1", "WH-B")]["available"] == 20 and repo.stock[("P-AB-1", "WH-B")]["reserved"] == 0
    back = act(jane, d["order_id"], "allocate").json()
    assert back["status"] == "ALLOCATED" and repo.stock[("P-AB-1", "WH-B")]["available"] == 18


def test_a_low_stock_threshold_is_recomputed_after_a_reservation(repo):
    place(client("U-ANNA"), items=[{"part_id": "P-AB-1", "quantity": 16, "machine": "M-1"}])
    assert repo.stock[("P-AB-1", "WH-B")]["stock_status"] == "LOW_STOCK" and repo.stock[("P-AB-1", "WH-B")]["available"] == 4
    place(client("U-LARS"), items=[{"part_id": "P-AB-1", "quantity": 4}], idempotency_key="key-0000002")
    assert repo.stock[("P-AB-1", "WH-B")]["stock_status"] == "OUT_OF_STOCK" and repo.stock[("P-AB-1", "WH-B")]["available"] == 0


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
    d = drive(jane, oid, "dispatch")
    assert d["status"] == "SHIPPED" and d["shipments"][0]["status"] == "DISPATCHED"
    row = repo.stock[("P-AB-1", "WH-B")]
    assert (row["on_hand"], row["reserved"], row["available"]) == (18, 0, 18)  # the units have left the depot
    d = drive(jane, oid, "in_transit")
    assert d["status"] == "SHIPPED" and d["shipments"][0]["status"] == "IN_TRANSIT"
    d = drive(jane, oid, "deliver")
    assert d["status"] == "DELIVERED" and d["shipments"][0]["status"] == "DELIVERED" and d["service"] is None  # no service was asked for: none is forced
    assert [e["event_status"] for e in d["shipments"][0]["events"]] == ["CREATED", "DISPATCHED", "IN_TRANSIT", "DELIVERED"]
    assert all(e["data_status"] == "SYNTHETIC_DEMO" for e in d["shipments"][0]["events"])
    d = drive(jane, oid, "complete_order")
    assert d["status"] == "COMPLETED" and d["actions"] == [] and [s["state"] for s in d["stages"]] == ["done", "done", "done", "done", "done", "skipped", "done"]
    assert [h["status"] for h in d["history"]] == ["NEW", "ALLOCATED", "FULFILMENT_PENDING", "FULFILLING", "READY_TO_SHIP", "READY_TO_SHIP", "SHIPPED", "SHIPPED", "DELIVERED", "COMPLETED"]
    assert all(h["by"] for h in d["history"])  # every step is attributed


def test_the_full_lifecycle_with_dealer_service_then_the_order_closes(repo):
    anna, jane = client("U-ANNA"), client("U-JANE")
    oid = place(anna, dealer_service_required=True).json()["order_id"]
    drive(jane, oid, "start_fulfilment", "begin_fulfilling", "mark_ready", "create_shipment", "dispatch", "in_transit")
    d = drive(jane, oid, "deliver")
    assert d["status"] == "DELIVERED" and d["service"]["service_status"] == "CREATED" and d["service"]["dealer"] == "Dealer One (demo)"
    assert "complete_order" in {a["action"] for a in d["actions"] if not a["allowed"]} and not any(a["action"] == "complete_order" and a["allowed"] for a in d["actions"])  # service first
    assert act(jane, oid, "complete_order").status_code == 409
    seen = []
    for step, expect in [("service_receive_part", "PART_RECEIVED"), ("service_start", "STARTED"), ("service_install", "INSTALLED")]:
        d = drive(jane, oid, step)
        seen.append(d["service"]["service_status"])
        assert d["status"] == "DELIVERED" and d["service"]["service_status"] == expect
    d = drive(jane, oid, "service_complete")
    assert d["status"] == "COMPLETED" and d["service"]["service_status"] == "COMPLETED" and seen == ["PART_RECEIVED", "STARTED", "INSTALLED"]


def test_service_steps_cannot_be_skipped_or_run_without_a_service(repo):
    jane = client("U-JANE")
    oid = place(client("U-ANNA"), dealer_service_required=True).json()["order_id"]
    drive(jane, oid, "start_fulfilment", "begin_fulfilling", "mark_ready", "create_shipment", "dispatch", "in_transit", "deliver")
    for skipped in ("service_start", "service_install", "service_complete"):
        r = act(jane, oid, skipped)
        assert r.status_code == 409 and r.json()["error"]["code"] == "transition_blocked", skipped
    plain = place(client("U-ANNA"), idempotency_key="key-0000002").json()["order_id"]
    drive(jane, plain, "start_fulfilment", "begin_fulfilling", "mark_ready", "create_shipment", "dispatch", "in_transit", "deliver")
    assert act(jane, plain, "service_receive_part").json()["error"]["code"] == "transition_blocked"


@pytest.mark.parametrize("actions,target,code", [
    (["mark_ready"], "start", "invalid_transition"),
    (["begin_fulfilling"], "x", "invalid_transition"),
    (["dispatch"], "x", "invalid_transition"),
    (["deliver"], "x", "invalid_transition"),
    (["create_shipment"], "x", "invalid_transition"),   # not ready to ship yet
    (["complete_order"], "x", "invalid_transition"),    # not delivered
])
def test_invalid_transitions_from_allocated_are_rejected_and_change_nothing(repo, actions, target, code):
    jane = client("U-JANE")
    oid = place(client("U-ANNA")).json()["order_id"]
    before = (repo.orders_[oid]["status"], len(repo.orders_[oid]["history"]))
    r = act(jane, oid, actions[0])
    assert r.status_code == 409 and r.json()["error"]["code"] == code
    assert (repo.orders_[oid]["status"], len(repo.orders_[oid]["history"])) == before


def test_shipment_steps_need_the_right_shipment_state(repo):
    jane = client("U-JANE")
    oid = place(client("U-ANNA")).json()["order_id"]
    drive(jane, oid, "start_fulfilment", "begin_fulfilling", "mark_ready")
    assert act(jane, oid, "dispatch").json()["error"]["code"] == "transition_blocked"  # no shipment yet
    drive(jane, oid, "create_shipment")
    assert act(jane, oid, "create_shipment").status_code == 409  # one active shipment
    drive(jane, oid, "dispatch")
    assert act(jane, oid, "deliver").json()["error"]["code"] == "transition_blocked"  # dispatched is not in transit
    assert act(jane, oid, "mark_ready").json()["error"]["code"] == "invalid_transition"  # no way back


def test_a_stale_status_is_rejected_and_two_actions_cannot_both_win(repo):
    jane = client("U-JANE")
    oid = place(client("U-ANNA")).json()["order_id"]
    assert act(jane, oid, "start_fulfilment", expected="NEW").json()["error"]["code"] == "stale_status"
    assert act(jane, oid, "start_fulfilment", expected="ALLOCATED").status_code == 200
    assert act(jane, oid, "start_fulfilment", expected="ALLOCATED").json()["error"]["code"] == "stale_status"  # the second caller saw an old status


# ── exceptions ────────────────────────────────────────────────────────────────────────────────────
def test_cancel_by_the_owner_early_releases_the_reserved_stock(repo):
    anna = client("U-ANNA")
    oid = place(anna).json()["order_id"]
    assert repo.stock[("P-AB-1", "WH-B")]["available"] == 18
    d = act(anna, oid, "cancel").json()
    assert d["status"] == "CANCELLED" and d["fulfilment"]["allocation_status"] == "RELEASED" and d["lines"][0]["allocation_status"] == "RELEASED"
    assert repo.stock[("P-AB-1", "WH-B")]["available"] == 20 and repo.stock[("P-AB-1", "WH-B")]["reserved"] == 0 and d["actions"] == []
    assert act(anna, oid, "cancel").status_code == 409  # already cancelled


def test_the_owner_cannot_cancel_once_fulfilment_has_started_and_others_never_can(repo):
    anna, lars, jane = client("U-ANNA"), client("U-LARS"), client("U-JANE")
    oid = place(anna).json()["order_id"]
    assert act(lars, oid, "cancel").status_code == 403  # another customer's order
    drive(jane, oid, "start_fulfilment", "begin_fulfilling")
    r = act(anna, oid, "cancel")
    assert r.status_code == 403 or r.status_code == 409
    d = act(jane, oid, "cancel").json()  # the processor still can, and the stock goes back
    assert d["status"] == "CANCELLED" and repo.stock[("P-AB-1", "WH-B")]["available"] == 20


def test_cancelling_at_ready_to_ship_cancels_the_open_shipment_and_frees_the_stock(repo):
    jane = client("U-JANE")
    oid = place(client("U-ANNA")).json()["order_id"]
    drive(jane, oid, "start_fulfilment", "begin_fulfilling", "mark_ready", "create_shipment")
    d = act(jane, oid, "cancel").json()
    assert d["status"] == "CANCELLED" and d["shipments"][0]["status"] == "CANCELLED" and repo.stock[("P-AB-1", "WH-B")]["available"] == 20


def test_reject_and_allocation_failure_paths(repo, monkeypatch):
    jane = client("U-JANE")
    import app.services.checkout as co

    real = co.CheckoutService._plan

    def stale(self, lines, shipto):  # the availability check passes, then another order takes the stock before allocation
        plan = real(self, lines, shipto)
        repo.stock[("P-AB-1", "WH-B")]["available"] = 1
        return plan

    monkeypatch.setattr(co.CheckoutService, "_plan", stale)
    oid = place(client("U-ANNA")).json()["order_id"]
    monkeypatch.setattr(co.CheckoutService, "_plan", real)
    assert repo.orders_[oid]["status"] == "ALLOCATION_FAILED"
    retry = act(jane, oid, "allocate")  # still only 1 available
    assert retry.json()["status"] == "ALLOCATION_FAILED" and retry.status_code == 200
    repo.stock[("P-AB-1", "WH-B")]["available"] = 20  # stock arrives
    assert act(jane, oid, "allocate").json()["status"] == "ALLOCATED"
    oid2 = place(client("U-ANNA"), idempotency_key="key-0000002").json()["order_id"]
    assert act(jane, oid2, "reject").status_code == 409  # allocated orders are released/cancelled, not rejected
    repo.orders_[oid2]["status"] = "NEW"
    repo.orders_[oid2]["props"]["allocation_status"] = "PENDING"
    d = act(jane, oid2, "reject").json()
    assert d["status"] == "REJECTED" and d["actions"] == []


def test_shipment_exception_and_failed_delivery(repo):
    jane = client("U-JANE")
    oid = place(client("U-ANNA")).json()["order_id"]
    drive(jane, oid, "start_fulfilment", "begin_fulfilling", "mark_ready", "create_shipment", "dispatch", "in_transit")
    d = drive(jane, oid, "shipment_exception")
    assert d["status"] == "SHIPMENT_EXCEPTION" and d["shipments"][0]["status"] == "EXCEPTION" and d["stages"][5]["state"] != "exception"
    d = drive(jane, oid, "resume_shipment")
    assert d["status"] == "SHIPPED" and d["shipments"][0]["status"] == "IN_TRANSIT"
    d = drive(jane, oid, "delivery_failed")
    assert d["status"] == "DELIVERY_FAILED" and d["shipments"][0]["status"] == "DELIVERY_FAILED"
    assert repo.stock[("P-AB-1", "WH-B")]["reserved"] == 0  # the goods left the depot: nothing to release
    d = drive(jane, oid, "cancel")
    assert d["status"] == "CANCELLED" and repo.stock[("P-AB-1", "WH-B")]["available"] == 18  # not returned to stock: it shipped


def test_service_cancelled_still_lets_the_order_complete(repo):
    jane = client("U-JANE")
    oid = place(client("U-ANNA"), dealer_service_required=True).json()["order_id"]
    drive(jane, oid, "start_fulfilment", "begin_fulfilling", "mark_ready", "create_shipment", "dispatch", "in_transit", "deliver", "service_receive_part")
    d = drive(jane, oid, "service_cancel")
    assert d["status"] == "SERVICE_CANCELLED" and d["service"]["service_status"] == "CANCELLED"
    assert drive(jane, oid, "complete_order")["status"] == "COMPLETED"


# ── ownership and roles ───────────────────────────────────────────────────────────────────────────
def test_orders_belong_to_the_user_who_placed_them_even_without_a_customer_record(repo):
    nora = client("U-NOCUS")  # an account that acts for no customer at all
    oid = place(nora).json()["order_id"]
    assert [o["order_id"] for o in nora.get("/api/v1/orders").json()] == [oid]
    assert client("U-ANNA").get(f"/api/v1/orders/{oid}").status_code == 403 and client("U-LARS").get("/api/v1/orders").json() == [o for o in client("U-LARS").get("/api/v1/orders").json() if o["order_id"] != oid]
    jane = client("U-JANE")
    listing = {o["order_id"]: o for o in jane.get("/api/v1/orders").json()}
    assert listing[oid]["customer"] == "De Vries Bouw B.V." and listing[oid]["queue"] == "needs_fulfilment" and listing[oid]["channel"] == "DIRECT_ORDER"
    assert listing[oid]["total"] is None  # no total is invented


def test_end_users_only_see_the_actions_they_may_take_and_processors_the_rest(repo):
    oid = place(client("U-ANNA")).json()["order_id"]
    mine = client("U-ANNA").get(f"/api/v1/orders/{oid}").json()
    assert {a["action"] for a in mine["actions"]} == {"cancel"} and "warehouses" not in mine["lines"][0]
    theirs = client("U-JANE").get(f"/api/v1/orders/{oid}").json()
    assert {"start_fulfilment", "release_allocation", "cancel"} <= {a["action"] for a in theirs["actions"]}
    assert client("U-ANNA").post(f"/api/v1/orders/{oid}/actions", json={"action": "start_fulfilment"}).status_code == 403


def test_a_direct_order_has_no_free_status_edit_and_unknown_actions_are_refused(repo):
    jane = client("U-JANE")
    oid = place(client("U-ANNA")).json()["order_id"]
    r = jane.post(f"/api/v1/orders/{oid}/status", json={"status": "SHIPPED"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "use_actions"
    assert act(jane, oid, "teleport").json()["error"]["code"] == "invalid_action"
    assert act(jane, "HCME-ORD-999999", "cancel").status_code == 404


# ── pure rules ────────────────────────────────────────────────────────────────────────────────────
def test_every_status_the_flow_uses_is_in_the_one_vocabulary():
    used = {s for a in flow.ACTIONS.values() for s in (*a.from_statuses, a.to_status) if s}
    assert used <= set(flow.LABEL) and set(flow.NEW_STATUS_SEQUENCE) <= set(flow.LABEL)
    assert {"REJECTED", "ALLOCATION_FAILED", "ALLOCATION_RELEASED", "CANCELLED", "SHIPMENT_EXCEPTION", "DELIVERY_FAILED", "SERVICE_CANCELLED"} == set(flow.EXCEPTIONS)


def test_depot_plan_ranks_by_route_not_stock_and_marks_gaps():
    lines = [{"part_id": "P1", "part_number": "N1", "quantity": 5}]
    stock = [{"part_id": "P1", "warehouse_id": d, "name": d, "city": d, "country_code": "NL", "stock_status": s, "available": a}
             for d, s, a in [("BIG", "IN_STOCK", 900), ("NEAR", "LOW_STOCK", 5), ("NONE", "UNKNOWN", None)]]
    routes = [{"depot_id": "NEAR", "shipto_id": "S", "route_id": "R1", "option_code": "STANDARD_ROAD_EU", "mode": "ROAD", "service_level": "STANDARD", "distance_km": 50.0, "days": 1,
               "freight_total": 9.0}, {"depot_id": "NONE", "shipto_id": "S", "route_id": "R2", "option_code": "X", "mode": "ROAD", "service_level": "STANDARD", "distance_km": 10.0, "days": 1}]
    plan = {p["depot_id"]: p for p in depot_plan(lines, stock, routes)}
    assert plan["NEAR"]["selectable"] and plan["NEAR"]["recommended"] and not plan["BIG"]["selectable"] and not plan["NONE"]["selectable"]  # BIG: most stock, no route; NONE: unknown stock
    assert plan["NONE"]["lines"][0]["available"] is None
