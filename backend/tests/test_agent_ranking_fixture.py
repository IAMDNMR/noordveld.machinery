"""Deterministic ranking, proven on an isolated in-memory world: no Neo4j, no model, nothing shared with production data.

The real AgentService (its flow, its evaluation, its ranking, its evidence) runs on a small fixture "graph" held in plain dictionaries. Each
test changes ONE ranking input in the fixture, runs the same request again, and sees the recommendation move; restoring the fixture brings the
original recommendation back. Because the world is the only thing that changes, the ranking is backend-driven and deterministic.
"""
from __future__ import annotations

import copy

import pytest

from app.agent.service import AgentService
from app.graph.queries import agent as q
from app.intelligence.models import Kind, Resolved
from app.intelligence.resolver import Resolution
from app.llm import ShoppingParse

DESTINATION = {"shipto_id": "S1", "city": "Testburg", "country_code": "NL"}


def world() -> dict:
    """Two verified parts that fit machine M-1, each stocked at its own depot with its own route to the destination."""
    return {
        "parts": {
            "P-A": {"part_id": "P-A", "part_number": "TST-A", "name": "Test filter A", "category": "Filtration", "subcategory": "Test filter", "price": 100.0},
            "P-B": {"part_id": "P-B", "part_number": "TST-B", "name": "Test filter B", "category": "Filtration", "subcategory": "Test filter", "price": 150.0},
        },
        "stock": {"P-A": ("D1", "IN_STOCK", 10), "P-B": ("D2", "IN_STOCK", 10)},
        "routes": {"D1": 3, "D2": 1},  # estimated days from each depot to the destination
    }


class Scripted:
    name = "scripted"

    def parse_shopping_request(self, request):
        return ShoppingParse(True, machine="M-1", part_type="test filter", **self.kw)

    def __init__(self, **kw):
        self.kw = kw


class FakeResolver:
    def resolve(self, mentions):
        m = Resolved(Kind.MACHINE, "MCH-1", "M-1", "Test machine", "SYNTHETIC_DEMO", 0)
        return Resolution(by_kind={Kind.MACHINE: [m]})


class FakeParts:
    def __init__(self, w):
        self._w = w

    def search(self, *, text, machine, **_):
        ids = sorted(self._w["parts"])
        return len(ids), ids

    def summaries(self, ids):
        out = []
        for pid in ids:
            p = self._w["parts"][pid]
            out.append({**{k: p[k] for k in ("part_id", "part_number", "name", "category", "subcategory")},
                        "fitment": [{"model_code": "M-1", "fitment_status": "CONFIRMED"}],
                        "price": {"amount": p["price"], "currency": "EUR", "data_status": "SYNTHETIC_DEMO"},
                        "profile": {"availability_state": "IN_STOCK", "orderable": True, "part_status": "VERIFIED", "data_status": "SYNTHETIC_DEMO"},
                        "total_available": 10})
        return out


class FakeIntel:
    def suppliers(self, part_id):
        return [{"supplier_id": "SUP-1", "name": "Test Supplier (demo)", "lead_time_days": 5, "is_primary": True, "data_status": "SYNTHETIC_DEMO"}]

    def machines(self):
        return []


class FakeFulfilment:
    def __init__(self, w):
        self._w = w

    def depot_stock(self, part_ids):
        rows = []
        for pid in part_ids:
            depot, state, qty = self._w["stock"][pid]
            rows.append({"part_id": pid, "warehouse_id": depot, "name": f"Depot {depot}", "city": "Teststad", "country_code": "NL", "stock_status": state, "available": qty,
                         "data_status": "SYNTHETIC_DEMO"})
        return rows


class FakeGraph:
    def __init__(self, w):
        self._w = w

    def read(self, query, **params):
        if query == q.DESTINATIONS:
            return [DESTINATION]
        if query == q.ROUTES_TO:
            return [{"depot_id": d, "shipto_id": "S1", "route_id": f"R-{d}", "option_id": "O1", "option_name": "Test Road", "option_code": "TR", "mode": "ROAD",
                     "service_level": "STANDARD", "distance_km": 100.0, "days": days, "estimate_basis": "ESTIMATED", "legs": 1, "data_status": "SYNTHETIC_DEMO",
                     "freight_total": 10.0, "freight_currency": "EUR", "rate_data_status": "SYNTHETIC_DEMO"}
                    for d, days in sorted(self._w["routes"].items()) if d in params["depots"]]
        if query == q.DEALERS_INSTALLING:
            return []
        raise AssertionError("the fixture world was asked something it does not hold")


class FixtureService(AgentService):
    def __init__(self, w, **parse):
        self._g, self._intel, self._parts = FakeGraph(w), FakeIntel(), FakeParts(w)
        self._resolver, self._fulfilment, self._llm = FakeResolver(), FakeFulfilment(w), Scripted(**parse)


def recommended(w, **parse) -> str | None:
    return FixtureService(w, **parse).recommend("a request").recommended


def test_the_fixture_world_gives_the_expected_starting_recommendations():
    w = world()
    assert recommended(w, preference="cheapest") == "TST-A"  # A is cheaper (100 vs 150)
    assert recommended(w, preference="fastest", delivery_place="Testburg") == "TST-B"  # B is faster (1 day vs 3)


def test_price_is_a_ranking_input_changing_it_moves_the_recommendation_and_restoring_it_brings_it_back():
    w = world()
    original = copy.deepcopy(w)
    assert recommended(w, preference="cheapest") == "TST-A"  # A: candidate A recommended initially
    w["parts"]["P-A"]["price"] = 200.0  # B: change only the price of A
    assert recommended(w, preference="cheapest") == "TST-B"  # C: candidate B becomes recommended
    w["parts"]["P-A"]["price"] = original["parts"]["P-A"]["price"]  # D: restore the fixture
    assert w == original
    assert recommended(w, preference="cheapest") == "TST-A"  # E: the original recommendation returns


def test_route_days_are_a_ranking_input_for_fastest():
    w = world()
    original = copy.deepcopy(w)
    assert recommended(w, preference="fastest", delivery_place="Testburg") == "TST-B"
    w["routes"]["D2"] = 9  # only the recorded route estimate from B's depot changes
    assert recommended(w, preference="fastest", delivery_place="Testburg") == "TST-A"
    w["routes"]["D2"] = original["routes"]["D2"]
    assert recommended(w, preference="fastest", delivery_place="Testburg") == "TST-B"


def test_availability_is_a_ranking_input_a_part_that_runs_out_is_no_longer_recommended():
    w = world()
    original = copy.deepcopy(w)
    assert recommended(w, preference="cheapest") == "TST-A"
    w["stock"]["P-A"] = ("D1", "OUT_OF_STOCK", 0)
    assert recommended(w, preference="cheapest") == "TST-B"
    w["stock"]["P-A"] = original["stock"]["P-A"]
    assert recommended(w, preference="cheapest") == "TST-A"


def test_a_missing_route_removes_a_part_from_a_destination_request_and_a_budget_does_the_same():
    w = world()
    del w["routes"]["D1"]  # no recorded route from A's depot
    r = FixtureService(w, preference="cheapest", delivery_place="Testburg").recommend("x")
    assert r.recommended == "TST-B" and [c.part.part_number for c in r.candidates] == ["TST-B"]
    r = FixtureService(world(), preference="cheapest", budget_max=120).recommend("x")
    assert r.recommended == "TST-A" and [c.part.part_number for c in r.candidates] == ["TST-A"]


def test_values_that_are_not_ranking_inputs_do_not_move_the_recommendation():
    w = world()
    before = recommended(w, preference="cheapest")
    w["parts"]["P-B"]["name"] = "A completely different name"
    w["parts"]["P-A"]["name"] = "Another name"
    assert recommended(w, preference="cheapest") == before


def test_equal_ranking_inputs_are_broken_by_part_number_in_either_insertion_order():
    w = world()
    w["parts"]["P-A"]["price"] = w["parts"]["P-B"]["price"] = 100.0
    assert recommended(w, preference="cheapest") == "TST-A"
    w["parts"] = dict(reversed(list(w["parts"].items())))  # the same world listed in the opposite order
    assert recommended(w, preference="cheapest") == "TST-A"


def test_the_whole_response_is_repeatable_for_the_same_world():
    w = world()
    a = FixtureService(w, preference="fastest", delivery_place="Testburg").recommend("x").model_dump()
    b = FixtureService(w, preference="fastest", delivery_place="Testburg").recommend("x").model_dump()
    assert a == b


@pytest.mark.parametrize("pref", ["cheapest", "fastest", "none"])
def test_the_fixture_run_never_touches_a_real_graph(pref):
    # FakeGraph raises for any query it does not hold, so this passing proves the service asked only the fixture
    r = FixtureService(world(), preference=pref, delivery_place="Testburg").recommend("x")
    assert r.state == "recommendation"
