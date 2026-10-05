"""Agentic Shopping against the specification: the 20 required cases, the regression requests, the deterministic-ranking proof and the product boundaries.

The language model's reading is scripted (ShoppingParse); every machine, part, price, stock level, route and supplier comes from the live graph.
Nothing here writes to the graph: the ranking proof rewrites rows in flight, in a proxy, and the stored data is never touched.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.graph.client import GraphClient
from app.graph.queries import agent as q
from app.llm import ShoppingParse
from tests.test_agent import GraphClientProxy, NoGraph, agent

pytestmark = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")

HOSE = dict(machine="NV-4500", part_type="hydraulic hose")
BRAKE = dict(machine="NV-4500", part_type="brake pad")


def parse(**kw):
    return ShoppingParse(True, **kw)


# ── the 20 required cases ────────────────────────────────────────────────────────────────────────
def test_01_machine_and_need_apply_both_constraints():
    r = agent(parse(machine="NV-3200", part_type="air filter"))
    assert r["state"] == "recommendation" and r["interpretation"]["machine"] == "NV-3200"
    for c in r["candidates"]:
        assert any(f["model_code"] == "NV-3200" for f in c["part"]["fitment"]) and "filter" in c["part"]["name"].lower()


def test_02_machine_only_asks_what_part_instead_of_returning_everything_that_fits():
    r = agent(parse(machine="NV-4500"))
    assert r["state"] == "need_part" and r["candidates"] == [] and r["options"]


def test_03_need_only_asks_which_machine_offering_only_machines_the_part_fits():
    r = agent(parse(part_type="hydraulic hose"))
    assert r["state"] == "need_machine" and r["candidates"] == [] and {o["label"] for o in r["options"]} <= {"NV-2100", "NV-3200", "NV-4500", "NV-6000", "NV-7500"}


def test_04_budget_is_a_hard_limit():
    r = agent(parse(**BRAKE, budget_max=600))
    assert r["state"] == "recommendation" and all(c["part"]["price"]["amount"] <= 600 for c in r["candidates"])
    r = agent(parse(**BRAKE, budget_max=100))
    assert r["state"] == "no_match" and r["candidates"] == [] and "budget" in r["question"]


def test_05_cheapest_is_the_lowest_validated_price():
    r = agent(parse(**BRAKE, preference="cheapest"))
    prices = [c["part"]["price"]["amount"] for c in r["candidates"]]
    assert len(prices) >= 2 and prices == sorted(prices) and r["decision"]["priorities"][0] == "Lowest price"


def test_06_fastest_needs_a_destination_and_then_follows_the_recorded_route():
    ask = agent(parse(**BRAKE, preference="fastest"))
    assert ask["state"] == "need_detail" and ask["candidates"] == [] and "delivered" in ask["question"].lower() and ask["options"]
    r = agent(parse(**BRAKE, preference="fastest", delivery_place="Hamburg"))
    days = [c["fulfilment_days"] for c in r["candidates"]]
    assert r["state"] == "recommendation" and None not in days and days == sorted(days) and r["decision"]["priorities"][1] == "Fastest recorded route"


def test_07_destination_is_resolved_through_recorded_destinations_and_never_inferred():
    r = agent(parse(**HOSE, delivery_place="Hamburg"))
    assert r["state"] == "recommendation" and r["delivery"]["city"] == "Hamburg" and r["delivery"]["route_id"] and r["interpretation"]["delivery_place"] == "Hamburg"
    for place in ("Atlantis", "Germany"):  # not recorded / only a country: asked, not guessed
        a = agent(parse(**HOSE, delivery_place=place))
        assert a["state"] == "need_detail" and a["candidates"] == [] and a["options"] and a["delivery"] is None


def test_08_only_stock_available_now_is_eligible():
    r = agent(parse(**BRAKE))
    assert all(c["availability_label"] in ("In stock", "Low stock") for c in r["candidates"])
    big = agent(parse(machine="NV-3200", part_type="air filter", quantity=500))  # more than any single depot holds
    assert big["state"] == "no_match" and big["candidates"] == [] and "500" in big["question"]


def test_09_unknown_stock_is_never_treated_as_available():
    g = GraphClient(get_settings())
    unknown = g.read("MATCH (p:Part)-[a:AVAILABLE_AT]->(:Warehouse) WHERE a.stock_status = 'UNKNOWN' RETURN DISTINCT p.part_number AS n LIMIT 8")
    g.close()
    assert unknown  # the graph really holds UNKNOWN depot rows
    from app.agent.supply import part_supply
    s = part_supply("P", 1, [{"part_id": "P", "warehouse_id": "W", "stock_status": "UNKNOWN", "available": None}], None)
    assert s.availability == "UNKNOWN" and s.units is None and not s.available_now


def test_10_an_ambiguous_machine_asks_which_one():
    r = agent(parse(machine="BTS", part_type="hydraulic"))
    assert r["state"] == "choose_machine" and r["candidates"] == [] and len(r["options"]) >= 2 and all(o["refine"].startswith("for my BTS-") for o in r["options"])


def test_11_an_unknown_machine_is_not_invented():
    r = agent(parse(machine="NV200", part_type="hydraulic"))
    assert r["state"] == "need_machine" and r["interpretation"]["machine"] is None and r["candidates"] == []
    assert "NV-2100" not in json.dumps(r["interpretation"]) and "NV200" in r["question"]


def test_12_no_valid_candidate_says_so_and_relaxes_nothing():
    r = agent(parse(machine="BTS-500", part_type="hydraulic"))
    assert r["state"] == "no_match" and r["candidates"] == [] and r["recommended"] is None
    r = agent(parse(**BRAKE, budget_max=10))
    assert r["state"] == "no_match" and r["candidates"] == []


def test_13_several_valid_candidates_are_all_deterministically_ordered():
    a = agent(parse(**BRAKE))
    b = agent(parse(**BRAKE))
    nums = [c["part"]["part_number"] for c in a["candidates"]]
    assert len(nums) >= 2 and nums == [c["part"]["part_number"] for c in b["candidates"]] and a["recommended"] == nums[0]


def test_14_only_verified_confirmed_parts_can_be_recommended_or_bought():
    r = agent(parse(machine="NV-7500", part_type="track roller assembly", budget_max=1_000_000))
    assert all(c["part"]["availability"]["part_status"] == "VERIFIED" and c["fitment_status"] == "CONFIRMED" and c["can_add_to_cart"] for c in r["candidates"])
    assert all(c["part"]["part_number"] != "NVM-1140-DT" for c in r["candidates"])  # a family-level part is shown as excluded, never as purchasable
    assert any(e["part_number"] == "NVM-1140-DT" for e in r["excluded"])


def test_15_alternatives_are_independently_valid_and_never_implied_interchangeable():
    r = agent(parse(**BRAKE))
    best, *alts = r["candidates"]
    assert alts
    for a in alts:  # each alternative passed every gate on its own and carries its own graph facts
        assert a["can_add_to_cart"] and a["fitment_status"] == "CONFIRMED" and a["inventory"] != "Not recorded" and a["suppliers"]
        assert a["tradeoffs"] is not None
    blob = json.dumps(r).lower()
    assert "interchangeable" not in blob and "equivalent" not in blob


def test_16_supplier_evidence_comes_from_the_graph():
    r = agent(parse(**HOSE))
    ev = {e["key"]: e for e in r["evidence"]}
    assert ev["supplier"]["ok"] and "(demo)" in ev["supplier"]["label"] and ev["supplier"]["data_class"] == "SYNTHETIC_DEMO"


def test_17_dealer_evidence_is_service_evidence_and_never_the_destination():
    r = agent(parse(**HOSE, delivery_place="Hamburg"))
    dealer = next(e for e in r["evidence"] if e["key"] == "dealer")
    assert "DE" in dealer["label"] and ("never taken to be the delivery destination" in dealer["detail"] or not dealer["ok"])
    assert r["delivery"]["warehouse"] and r["delivery"]["city"] == "Hamburg"  # the destination is the ship-to city, not a dealer or a depot


def test_18_transport_evidence_names_the_recorded_route_and_labels_it_synthetic():
    r = agent(parse(**HOSE, delivery_place="Hamburg"))
    t = next(e for e in r["evidence"] if e["key"] == "transport")
    assert t["ok"] and t["data_class"] == "SYNTHETIC_DEMO" and "not a price" in t["detail"] and r["delivery"]["route_id"] in t["detail"]


class NoRouteGraph(GraphClientProxy):
    """The live graph, with every transport route removed in flight (the stored graph is not touched)."""

    def __init__(self):
        self._g = GraphClient(get_settings())

    def read(self, query, **params):
        return [] if query == q.ROUTES_TO else self._g.read(query, **params)


def test_19_a_destination_with_no_route_is_reported_not_claimed():
    r = agent(parse(**HOSE, delivery_place="Hamburg"), graph=NoRouteGraph())
    assert r["state"] == "no_match" and r["candidates"] == [] and "no transport route is configured" in r["question"] and r["delivery"] is None


def test_20_out_of_scope_questions_never_reach_the_graph():
    for text in ("What machines are available?", "What is the supplier network?", "Tell me about the history of Noordveld."):
        r = agent(ShoppingParse(False), text, graph=NoGraph())
        assert r["state"] == "out_of_scope" and r["candidates"] == [] and r["recommended"] is None


# ── regression requests ──────────────────────────────────────────────────────────────────────────
def test_regression_filter_for_my_nv_3200():
    r = agent(parse(machine="NV-3200", part_type="filter"), "filter for my NV-3200")
    assert r["state"] == "choose_type" and r["interpretation"]["machine"] == "NV-3200" and all("filter" in o["label"].lower() for o in r["options"])


def test_regression_hydraulic_for_bts_500_applies_both_constraints():
    r = agent(parse(machine="BTS-500", part_type="hydraulic"), "hydraulic for BTS-500")
    assert r["interpretation"]["machine"] == "BTS-500" and r["state"] == "no_match" and "BTS-500" in r["question"]  # never every part that fits the machine


def test_regression_hydraulic_for_my_bts_machine_asks_which():
    r = agent(parse(machine="BTS", part_type="hydraulic"), "hydraulic for my BTS machine")
    assert r["state"] == "choose_machine" and len(r["options"]) >= 2


def test_regression_hydraulic_for_nv200_is_not_mapped_to_another_machine():
    r = agent(parse(machine="NV200", part_type="hydraulic"), "hydraulic for NV200")
    assert r["state"] == "need_machine" and r["interpretation"]["machine"] is None


# Deterministic ranking is proven on an isolated in-memory world: tests/test_agent_ranking_fixture.py (no proxy over the real graph).


# ── boundaries ───────────────────────────────────────────────────────────────────────────────────
APP = Path(__file__).resolve().parents[1] / "app"


def imports(folder: str) -> set[str]:
    found: set[str] = set()
    for path in (APP / folder).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module)
            elif isinstance(node, ast.Import):
                found.update(a.name for a in node.names)
    return found


def test_parts_intelligence_does_not_depend_on_agentic_shopping():
    assert not {m for m in imports("intelligence") if m == "app.agent" or m.startswith("app.agent.")}


def test_agentic_shopping_does_not_reuse_the_parts_intelligence_intent_registry():
    shared_ok = {"app.intelligence.models", "app.intelligence.resolver"}  # entity resolution is a shared lower-level service
    used = {m for m in imports("agent") if m.startswith("app.intelligence")}
    assert used <= shared_ok, used - shared_ok


def test_a_recommendation_is_read_only_and_creates_no_order_or_cart():
    g = GraphClient(get_settings())
    count = lambda: g.read("MATCH (o:Order) WITH count(o) AS orders MATCH (l:CartLine) RETURN orders, count(l) AS lines")[0]  # noqa: E731
    before = count()
    agent(parse(**HOSE, delivery_place="Hamburg", preference="fastest"))
    agent(parse(**BRAKE, preference="cheapest", budget_max=700))
    after = count()
    g.close()
    assert before == after


def test_agentic_shopping_only_reads_the_graph_and_is_not_a_generic_graph_explorer():
    import re

    queries = (APP / "graph" / "queries" / "agent.py").read_text(encoding="utf-8")
    assert not re.search(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD CSV|CALL dbms|apoc)\b", queries)  # read-only Cypher only
    assert len(re.findall(r'^[A-Z_]+ = """', queries, flags=re.M)) <= 8  # a small fixed set of approved queries, no query text built from the request
    code = "\n".join(p.read_text(encoding="utf-8") for p in (APP / "agent").glob("*.py"))
    assert not re.search(r"\.(write|transaction|execute_write)\(", code) and "f\"MATCH" not in code and "f'MATCH" not in code
