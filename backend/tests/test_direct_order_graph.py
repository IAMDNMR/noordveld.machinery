"""The direct-order flow against the REAL graph (AuraDB): the Cypher that places an order, reserves and releases depot stock, creates shipments, tracking and
dealer service. Unlike the other order tests this one WRITES to the database, so it only runs on request:

    RUN_GRAPH_WRITE_TESTS=1 python -m pytest tests/test_direct_order_graph.py

Everything it creates is removed afterwards (orders, lines, events, shipments, tracking, services, the order-number counter) and every inventory row it
touches is restored to exactly the properties it had before. It never edits a catalogue, price, supplier, dealer, transport or customer record."""
from __future__ import annotations

import os
import threading
import uuid

import pytest

from app.api.dependencies import get_graph
from app.core.config import get_settings
from app.graph.repositories.fulfilment import GraphConflictError
from app.services.checkout import CheckoutService
from app.services.orders import SYSTEM, GraphOrdersRepository, OrdersService, TransitionError

pytestmark = pytest.mark.skipif(not (get_settings().graph_configured and os.environ.get("RUN_GRAPH_WRITE_TESTS") == "1"),
                                reason="writes to the database: set RUN_GRAPH_WRITE_TESTS=1 to run")


class World:
    """A repository + services over the live graph, with exact cleanup of everything a test creates."""

    def __init__(self) -> None:
        self.g = get_graph()
        self.repo = GraphOrdersRepository(self.g)
        self.orders = OrdersService(self.repo)
        self.checkout = CheckoutService(self.repo, self.orders)
        self.anna = self.orders.user("USR-EU-001")
        self.jane = self.orders.user("USR-OP-001")
        self.tag = uuid.uuid4().hex[:8]
        self.snap: dict[tuple[str, str], dict] = {}
        self.created: list[str] = []
        self.cart_before = self.repo.cart(f"CRT-{self.anna.id}")  # the user's own cart is theirs: it is put back exactly as it was
        seq = self.g.read("MATCH (c:OrderSequence {name:'direct'}) RETURN c.value AS v")
        self.seq_before = seq[0]["v"] if seq else None

    def key(self, n: int = 0) -> str:
        return f"gt-{self.tag}-{n}"

    def keep_stock(self, part_id: str, depot: str) -> dict:
        """Remember an inventory row before the test touches it; cleanup puts back exactly these properties."""
        row = self.g.read("MATCH (:Part {part_id:$p})-[a:AVAILABLE_AT]->(:Warehouse {warehouse_id:$w}) RETURN properties(a) AS a", p=part_id, w=depot)[0]["a"]
        self.snap.setdefault((part_id, depot), row)
        return row

    def stock(self, part_id: str, depot: str) -> dict:
        return self.g.read("MATCH (:Part {part_id:$p})-[a:AVAILABLE_AT]->(:Warehouse {warehouse_id:$w}) RETURN properties(a) AS a", p=part_id, w=depot)[0]["a"]

    def order(self, order_id: str) -> dict:
        self.created.append(order_id) if order_id not in self.created else None
        return self.g.read("MATCH (o:Order {order_id:$o}) RETURN properties(o) AS o", o=order_id)[0]["o"]

    def body(self, sc: dict, **over) -> dict:
        b = {"items": [{"part_id": sc["part"], "quantity": 2, "machine": sc["machine"]}],
             "requester": {"name": "Test Buyer", "email": "buyer@test-company.example", "phone": "+49 40 5550100", "company": "Test Company GmbH"},
             "delivery": {"ship_to_id": sc["shipto"], "receiver_name": "Test Receiver", "receiver_phone": "+49 40 5550199"},
             "dealer_id": sc["dealer"], "dealer_service_required": False, "depot_id": sc["depot"], "route_id": sc["route"], "confirmed": True, "idempotency_key": self.key(0)}
        b.update(over)
        return b

    def cleanup(self) -> None:
        for (p, w), props in self.snap.items():  # exactly the properties the row had
            self.g.write("MATCH (:Part {part_id:$p})-[a:AVAILABLE_AT]->(:Warehouse {warehouse_id:$w}) SET a = $props", p=p, w=w, props=props)
        ids = [r["id"] for r in self.g.read("MATCH (o:Order) WHERE o.idempotency_key STARTS WITH $k RETURN o.order_id AS id", k=f"{self.anna.id}:gt-{self.tag}")] + self.created
        self.g.write("""MATCH (o:Order) WHERE o.order_id IN $ids
                        OPTIONAL MATCH (o)-[:CONTAINS_LINE]->(l:OrderLine) OPTIONAL MATCH (o)-[:HAS_STATUS_EVENT]->(e:OrderStatusEvent)
                        OPTIONAL MATCH (o)-[:HAS_SHIPMENT]->(s:Shipment) OPTIONAL MATCH (s)-[:HAS_TRACKING_EVENT]->(t:TrackingEvent) OPTIONAL MATCH (o)-[:HAS_SERVICE]->(sv:DealerService)
                        DETACH DELETE t, s, sv, e, l, o""", ids=list(set(ids)))
        self.g.write("MATCH (c:Cart {cart_id:$c})-[:CONTAINS_LINE]->(l:CartLine) DETACH DELETE l", c=f"CRT-{self.anna.id}")
        if self.cart_before:
            self.repo.put_cart(cart_id=f"CRT-{self.anna.id}", user_id=self.anna.id, customer_id=self.anna.customer_id, today="2026-10-05",
                               lines=[{"part_id": l["part_id"], "machine": l.get("machine"), "quantity": l["quantity"], "key": f"{l['part_id']}-{l['machine']}" if l.get("machine") else l["part_id"]}
                                      for l in self.cart_before])
        if self.seq_before is None:
            self.g.write("MATCH (c:OrderSequence {name:'direct'}) DELETE c")
        else:
            self.g.write("MATCH (c:OrderSequence {name:'direct'}) SET c.value = $v", v=self.seq_before)


@pytest.fixture()
def world():
    w = World()
    yield w
    w.cleanup()


@pytest.fixture()
def sc(world):
    """A real scenario: a verified part with a CONFIRMED fit, stocked (>= 40) at a depot that has a standard road route to a destination, and a dealer that installs it."""
    rows = world.g.read("""
        MATCH (c:PartCatalogProfile {part_status:'VERIFIED', orderable:true})-[:PROFILES_PART]->(p:Part)-[:FITS {fitment_status:'CONFIRMED'}]->(m:Machine)
        MATCH (p)-[a:AVAILABLE_AT]->(w:Warehouse) WHERE a.stock_status = 'IN_STOCK' AND a.available >= 40
        MATCH (w)<-[:FROM_DEPOT]-(r:TransportRoute {option_code:'STANDARD_ROAD_EU'})-[:TO_SHIP_TO]->(s:ShipTo) MATCH (d:Dealer)-[:INSTALLS_PART]->(p)
        RETURN p.part_id AS part, p.part_number AS no, m.model_code AS machine, w.warehouse_id AS depot, r.route_id AS route, s.shipto_id AS shipto, d.dealer_id AS dealer
        ORDER BY p.part_id, w.warehouse_id, s.shipto_id LIMIT 1""")
    assert rows, "the graph holds no complete ordering scenario"
    world.keep_stock(rows[0]["part"], rows[0]["depot"])
    return rows[0]


def ctx_of(world: World, order_id: str) -> dict:
    return world.orders._ctx(world.repo.owner(order_id))


# ── checkout reads come from the graph ────────────────────────────────────────────────────────────
def test_destinations_dealers_and_transport_options_come_from_the_graph(world, sc):
    countries = world.checkout.countries(world.anna)
    assert countries and all(c["destinations"] > 0 for c in countries)
    sites = world.checkout.destinations(world.anna, "DE")
    assert sites and all(s["country_code"] == "DE" and s["street"] and s["postal_code"] for s in sites)
    dealers = world.checkout.dealers(world.anna, None)
    assert len(dealers) == world.g.read("MATCH (d:Dealer) WHERE d.dealer_status STARTS WITH 'ACTIVE' RETURN count(d) AS n")[0]["n"]  # whatever the network holds today
    rv = world.checkout.review(world.anna, [{"part_id": sc["part"], "quantity": 2, "machine": sc["machine"]}], sc["shipto"])
    depot = next(d for d in rv["depots"] if d["depot_id"] == sc["depot"])
    in_graph = world.g.read("""MATCH (:Warehouse {warehouse_id:$w})<-[:FROM_DEPOT]-(r:TransportRoute)-[:TO_SHIP_TO]->(:ShipTo {shipto_id:$s}) WHERE (r)-[:PRICED_BY]->(:FreightRate)
                               RETURN r.route_id AS id, r.transport_mode AS mode, r.total_distance_km AS km, r.total_estimated_days AS days""", w=sc["depot"], s=sc["shipto"])
    assert {o["route_id"] for o in depot["options"]} == {r["id"] for r in in_graph} and len(in_graph) >= 2  # exactly the routes that exist, no more, no fewer
    for o in depot["options"]:
        g = next(r for r in in_graph if r["id"] == o["route_id"])
        assert (o["mode"], o["distance_km"], o["estimated_days"]) == (g["mode"], g["km"], g["days"]) and o["data_status"] == "SYNTHETIC_DEMO" and o["freight"]["data_status"] == "SYNTHETIC_DEMO"
    assert rv["cost"]["total"] is None and rv["can_order"]
    # every depot the review calls selectable really holds known stock and has a route: it was not picked for the largest quantity
    for d in rv["depots"]:
        assert d["selectable"] == (all(l["can_supply"] for l in d["lines"]) and bool(d["options"]))


def test_unknown_inventory_is_unknown_in_the_review_and_that_depot_is_not_selectable(world):
    row = world.g.read("""MATCH (p:Part)-[a:AVAILABLE_AT {stock_status:'UNKNOWN'}]->(w:Warehouse)
                          MATCH (c:PartCatalogProfile {part_status:'VERIFIED', orderable:true})-[:PROFILES_PART]->(p)
                          MATCH (w)<-[:FROM_DEPOT]-(:TransportRoute)-[:TO_SHIP_TO]->(s:ShipTo) RETURN p.part_id AS part, w.warehouse_id AS depot, s.shipto_id AS shipto LIMIT 1""")
    assert row, "no UNKNOWN inventory row with a route and a verified part"
    r = row[0]
    rv = world.checkout.review(world.anna, [{"part_id": r["part"], "quantity": 1}], r["shipto"])
    d = next(x for x in rv["depots"] if x["depot_id"] == r["depot"])
    assert d["lines"][0]["state"] == "UNKNOWN" and d["lines"][0]["available"] is None and not d["selectable"]  # null did not become 0
    assert world.stock(r["part"], r["depot"]).get("available") is None  # the property does not exist: unknown, not zero


# ── place order: the order, its relationships, the reservation ────────────────────────────────────
def test_place_order_persists_the_order_and_reserves_the_stock_in_the_graph(world, sc):
    before = world.stock(sc["part"], sc["depot"])
    d = world.checkout.place(world.anna, world.body(sc))
    oid = d["order_id"]
    assert oid.startswith("HCME-ORD-") and d["status"] == "ALLOCATED" and d["channel"] == "DIRECT_ORDER"
    o = world.order(oid)
    country = world.g.read("MATCH (s:ShipTo {shipto_id:$s}) RETURN s.country_code AS c", s=sc["shipto"])[0]["c"]
    assert (o["requester_name"], o["requester_company"], o["receiver_name"], o["delivery_country_code"]) == ("Test Buyer", "Test Company GmbH", "Test Receiver", country)
    assert o.get("part_cost") is None and o.get("transport_cost") is None and o.get("order_total") is None and o["cost_status"] == "NOT_AVAILABLE" and o["transport_data_status"] == "SYNTHETIC_DEMO"
    rels = {r["t"]: r["id"] for r in world.g.read("""MATCH (o:Order {order_id:$o})-[r]->(x) WHERE type(r) IN ['PLACED_BY','SHIPS_TO','FOR_DEALER','FULFILLED_FROM','USES_TRANSPORT']
                                                     RETURN type(r) AS t, coalesce(x.user_id, x.shipto_id, x.dealer_id, x.warehouse_id, x.route_id) AS id""", o=oid)}
    assert rels == {"PLACED_BY": "USR-EU-001", "SHIPS_TO": sc["shipto"], "FOR_DEALER": sc["dealer"], "FULFILLED_FROM": sc["depot"], "USES_TRANSPORT": sc["route"]}  # five distinct things
    assert world.g.read("MATCH (o:Order {order_id:$o})-[:ORDERED_BY]->(:Customer) RETURN count(*) AS n", o=oid)[0]["n"] == 0  # no customer master involved
    line = world.g.read("MATCH (:Order {order_id:$o})-[:CONTAINS_LINE]->(l:OrderLine) RETURN properties(l) AS l", o=oid)[0]["l"]
    assert (line["quantity"], line["machine_model"], line["part_number"], line["allocation_status"], line["reserved_quantity"]) == (2, sc["machine"], sc["no"], "RESERVED", 2)
    after = world.stock(sc["part"], sc["depot"])
    assert after["available"] == before["available"] - 2 and after["reserved"] == (before.get("reserved") or 0) + 2 and after["on_hand"] == before["on_hand"]
    events = world.g.read("MATCH (:Order {order_id:$o})-[:HAS_STATUS_EVENT]->(e) RETURN e.order_status AS s, e.actor_name AS who ORDER BY e.sequence", o=oid)
    assert [(e["s"], e["who"]) for e in events] == [("NEW", world.anna.name), ("ALLOCATED", "System")]


def test_place_order_is_idempotent_in_the_graph(world, sc):
    before = world.stock(sc["part"], sc["depot"])["available"]
    a = world.checkout.place(world.anna, world.body(sc))
    b = world.checkout.place(world.anna, world.body(sc))
    assert a["order_id"] == b["order_id"]
    assert world.g.read("MATCH (o:Order) WHERE o.idempotency_key = $k RETURN count(o) AS n", k=f"{world.anna.id}:{world.key(0)}")[0]["n"] == 1
    assert world.stock(sc["part"], sc["depot"])["available"] == before - 2  # reserved once
    with pytest.raises(GraphConflictError):  # the constraint itself refuses a second order with the same key (a concurrent double submit)
        world.repo.create_order(key=f"{world.anna.id}:{world.key(0)}", user_id=world.anna.id, actor={"id": "x", "name": "x", "role": "END_USER"}, at="2026-10-05T00:00:00+00:00", today="2026-10-05",
                                requester={"name": "a", "email": "a", "phone": "1", "company": "c"}, receiver={"name": "r", "phone": "1"}, shipto_id=sc["shipto"], dealer_id=sc["dealer"],
                                depot_id=sc["depot"], route_id=sc["route"], service_required=False, freight={"amount": None, "currency": "EUR"},
                                lines=[{"line_no": 1, "part_id": sc["part"], "quantity": 1, "machine": None}])


def test_orders_get_distinct_consecutive_numbers_from_the_counter(world, sc):
    a = world.checkout.place(world.anna, world.body(sc, idempotency_key=world.key(1)))["order_id"]
    b = world.checkout.place(world.anna, world.body(sc, idempotency_key=world.key(2)))["order_id"]
    assert int(b.rsplit("-", 1)[1]) == int(a.rsplit("-", 1)[1]) + 1


def test_the_cart_line_is_removed_on_order_and_keeps_the_machine_in_the_graph(world, sc):
    world.orders.put_cart(world.anna, [(sc["part"], 3, sc["machine"]), (sc["part"], 1, None)])
    got = world.orders.cart(world.anna)
    assert {(l["partId"], l["machine"], l["qty"]) for l in got} == {(sc["part"], sc["machine"], 3), (sc["part"], None, 1)} and all(l["partNumber"] and l["partName"] for l in got)
    with pytest.raises(TransitionError) as e:
        world.orders.put_cart(world.anna, [(sc["part"], 1, "NV-NO-SUCH")])
    assert e.value.code == "machine_mismatch"
    world.checkout.place(world.anna, world.body(sc))
    left = world.orders.cart(world.anna)
    assert [(l["partId"], l["machine"]) for l in left] == [(sc["part"], None)]  # only the ordered part+machine line left the cart


# ── allocation: atomic, never over-reserves, never uses UNKNOWN ───────────────────────────────────
def make_pending_order(world, sc, qty, n):
    """An order that exists but is not allocated yet (the state between creation and allocation)."""
    return world.repo.create_order(key=f"{world.anna.id}:{world.key(n)}", user_id=world.anna.id, actor={"id": world.anna.id, "name": world.anna.name, "role": "END_USER"},
                                   at="2026-10-05T00:00:00+00:00", today="2026-10-05", requester={"name": "A", "email": "a@b.example", "phone": "+49 1234567", "company": "C"},
                                   receiver={"name": "R", "phone": "+49 1234567"}, shipto_id=sc["shipto"], dealer_id=sc["dealer"], depot_id=sc["depot"], route_id=sc["route"],
                                   service_required=False, freight={"amount": 1.0, "currency": "EUR"}, lines=[{"line_no": 1, "part_id": sc["part"], "quantity": qty, "machine": sc["machine"]}])


@pytest.mark.parametrize("workers,per_order,fit", [(2, "over_half", 1), (2, "over_half", 1), (4, "half", 2), (4, "half", 2)])
def test_concurrent_allocations_never_reserve_the_same_units(world, sc, workers, per_order, fit):
    """N orders allocate at the same instant against one inventory row. Exactly as many win as the stock allows, the rest fail, and the row is
    decremented once per winner: no unit is ever reserved twice."""
    avail = world.stock(sc["part"], sc["depot"])["available"]
    qty = avail // 2 + 1 if per_order == "over_half" else avail // 2
    ids = [make_pending_order(world, sc, qty, n) for n in range(1, workers + 1)]
    world.created += ids
    results: dict[str, str] = {}
    barrier = threading.Barrier(workers)

    def go(oid: str) -> None:
        barrier.wait()
        results[oid] = world.orders.perform(oid, "allocate", SYSTEM, {"status": "NEW", "channel": "DIRECT_ORDER", "allocation_status": "PENDING", "service_required": False})

    threads = [threading.Thread(target=go, args=(i,)) for i in ids]
    [t.start() for t in threads]
    [t.join() for t in threads]
    won = [i for i, s_ in results.items() if s_ == "ALLOCATED"]
    assert len(won) == fit and sorted(set(results.values())) == ["ALLOCATED", "ALLOCATION_FAILED"], results
    row = world.stock(sc["part"], sc["depot"])
    assert row["available"] == avail - fit * qty and (row.get("reserved") or 0) >= fit * qty  # taken once per winner, never twice
    for i in ids:
        assert world.order(i)["allocation_status"] == ("RESERVED" if i in won else "FAILED")
        assert world.g.read("MATCH (:Order {order_id:$o})-[:CONTAINS_LINE]->(l) RETURN l.allocation_status AS s", o=i)[0]["s"] == ("RESERVED" if i in won else "NOT_YET_ALLOCATED")


def test_the_same_allocation_applied_twice_reserves_once(world, sc):
    oid = make_pending_order(world, sc, 3, 1)
    world.created.append(oid)
    before = world.stock(sc["part"], sc["depot"])["available"]
    ctx = {"status": "NEW", "channel": "DIRECT_ORDER", "allocation_status": "PENDING", "service_required": False}
    assert world.orders.perform(oid, "allocate", SYSTEM, ctx) == "ALLOCATED"
    with pytest.raises(TransitionError) as e:  # the second caller still believes the order is NEW
        world.orders.perform(oid, "allocate", SYSTEM, ctx)
    assert e.value.code == "stale_status"
    assert world.stock(sc["part"], sc["depot"])["available"] == before - 3


def test_unknown_stock_is_never_allocated_and_stays_unknown(world):
    row = world.g.read("""MATCH (p:Part)-[a:AVAILABLE_AT {stock_status:'UNKNOWN'}]->(w:Warehouse) MATCH (w)<-[:FROM_DEPOT]-(r:TransportRoute)-[:TO_SHIP_TO]->(s:ShipTo)
                          MATCH (d:Dealer) RETURN p.part_id AS part, w.warehouse_id AS depot, r.route_id AS route, s.shipto_id AS shipto, d.dealer_id AS dealer LIMIT 1""")[0]
    world.keep_stock(row["part"], row["depot"])
    sc2 = {**row, "machine": None}
    oid = make_pending_order(world, sc2, 1, 1)
    world.created.append(oid)
    state = world.orders.perform(oid, "allocate", SYSTEM, {"status": "NEW", "channel": "DIRECT_ORDER", "allocation_status": "PENDING", "service_required": False})
    assert state == "ALLOCATION_FAILED" and world.order(oid)["allocation_status"] == "FAILED"
    after = world.stock(row["part"], row["depot"])
    assert after["stock_status"] == "UNKNOWN" and after.get("available") is None  # still UNKNOWN: not 0, not decremented


def test_insufficient_stock_fails_the_allocation_and_reserves_nothing(world, sc):
    before = world.stock(sc["part"], sc["depot"])
    oid = make_pending_order(world, sc, before["available"] + 1, 1)
    world.created.append(oid)
    assert world.orders.perform(oid, "allocate", SYSTEM, {"status": "NEW", "channel": "DIRECT_ORDER", "allocation_status": "PENDING", "service_required": False}) == "ALLOCATION_FAILED"
    after = world.stock(sc["part"], sc["depot"])
    assert (after["available"], after["stock_status"], after.get("reserved") or 0, after["on_hand"]) == (before["available"], before["stock_status"], before.get("reserved") or 0, before["on_hand"])


def test_cancel_returns_the_reserved_units_to_the_depot(world, sc):
    before = world.stock(sc["part"], sc["depot"])
    oid = world.checkout.place(world.anna, world.body(sc, items=[{"part_id": sc["part"], "quantity": 5, "machine": sc["machine"]}]))["order_id"]
    assert world.stock(sc["part"], sc["depot"])["available"] == before["available"] - 5
    d = world.orders.act(world.anna, oid, "cancel")
    after = world.stock(sc["part"], sc["depot"])
    assert d["status"] == "CANCELLED" and after["available"] == before["available"] and after["stock_status"] == before["stock_status"] and (after.get("reserved") or 0) == (before.get("reserved") or 0)


# ── the whole lifecycle, in the graph ─────────────────────────────────────────────────────────────
def test_full_lifecycle_with_shipment_tracking_and_dealer_service_in_the_graph(world, sc):
    before = world.stock(sc["part"], sc["depot"])
    oid = world.checkout.place(world.anna, world.body(sc, dealer_service_required=True))["order_id"]
    jane = world.jane
    for a in ("start_fulfilment", "begin_fulfilling", "mark_ready"):
        assert world.orders.act(jane, oid, a)["status"] in ("FULFILMENT_PENDING", "FULFILLING", "READY_TO_SHIP")
    d = world.orders.act(jane, oid, "create_shipment")
    shipment_id = d["shipments"][0]["shipment_id"]
    rel = world.g.read("""MATCH (o:Order {order_id:$o})-[:HAS_SHIPMENT]->(s:Shipment {shipment_id:$s})
                          RETURN [(s)-[:DISPATCHED_FROM]->(w) | w.warehouse_id] AS depot, [(s)-[:SHIPS_TO]->(t) | t.shipto_id] AS dest, [(s)-[:USES_OPTION]->(p) | p.transport_option_id] AS opt,
                                 [(s)-[:USES_ROUTE]->(r) | r.route_id] AS route, s.shipment_status AS st, size([(s)-[:SHIPS_LINE]->() | 1]) AS lines""", o=oid, s=shipment_id)[0]
    assert rel["depot"] == [sc["depot"]] and rel["dest"] == [sc["shipto"]] and rel["route"] == [sc["route"]] and len(rel["opt"]) == 1 and rel["st"] == "CREATED" and rel["lines"] == 1
    for a, order_status in (("dispatch", "SHIPPED"), ("in_transit", "SHIPPED"), ("deliver", "DELIVERED")):
        assert world.orders.act(jane, oid, a)["status"] == order_status
    mid = world.stock(sc["part"], sc["depot"])
    assert mid["on_hand"] == before["on_hand"] - 2 and (mid.get("reserved") or 0) == (before.get("reserved") or 0)  # shipped: no longer on hand, nothing left reserved
    tracking = world.g.read("MATCH (:Shipment {shipment_id:$s})-[:HAS_TRACKING_EVENT]->(e) RETURN e.event_status AS s, e.data_status AS ds ORDER BY e.event_seq", s=shipment_id)
    assert [t["s"] for t in tracking] == ["CREATED", "DISPATCHED", "IN_TRANSIT", "DELIVERED"] and {t["ds"] for t in tracking} == {"SYNTHETIC_DEMO"}
    d = world.orders.detail(jane, oid)
    assert d["status"] == "DELIVERED" and d["service"]["service_status"] == "CREATED"
    for a in ("service_receive_part", "service_start", "service_install"):
        assert world.orders.act(jane, oid, a)["status"] == "DELIVERED"
    d = world.orders.act(jane, oid, "service_complete")
    assert d["status"] == "COMPLETED" and d["service"]["service_status"] == "COMPLETED"
    # the lifecycle comes back from the database on a fresh read, not from this process
    fresh = world.orders.detail(world.anna, oid)
    assert fresh["status"] == "COMPLETED" and fresh["shipments"][0]["status"] == "DELIVERED" and [h["status"] for h in fresh["history"]][-1] == "COMPLETED"
    assert world.g.read("MATCH (o:Order {order_id:$o}) RETURN o.order_status AS s", o=oid)[0]["s"] == "COMPLETED"


def test_the_cleanup_puts_the_users_own_cart_back_exactly(sc):
    """These tests must never leave the demo user's cart changed (an earlier version of the cleanup deleted a real cart line)."""
    w0 = World()
    original = w0.repo.cart(f"CRT-{w0.anna.id}")
    try:
        w0.orders.put_cart(w0.anna, [(sc["part"], 2, sc["machine"])])
        w = World()  # takes its snapshot now
        w.orders.put_cart(w.anna, [(sc["part"], 9, None)])  # a test disturbs the cart
        w.cleanup()
        back = w0.orders.cart(w0.anna)
        assert [(l["partId"], l["qty"], l["machine"]) for l in back] == [(sc["part"], 2, sc["machine"])]
    finally:  # leave the cart as this test found it
        w0.g.write("MATCH (c:Cart {cart_id:$c})-[:CONTAINS_LINE]->(l:CartLine) DETACH DELETE l", c=f"CRT-{w0.anna.id}")
        if original:
            w0.repo.put_cart(cart_id=f"CRT-{w0.anna.id}", user_id=w0.anna.id, customer_id=w0.anna.customer_id, today="2026-10-05",
                             lines=[{"part_id": l["part_id"], "machine": l.get("machine"), "quantity": l["quantity"], "key": f"{l['part_id']}-{l['machine']}" if l.get("machine") else l["part_id"]} for l in original])
