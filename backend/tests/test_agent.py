"""Agentic Shopping against the live graph. The model's reading of the request is scripted (Part 1) or the real configured provider (Part 2, opt-in)."""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_graph, get_llm
from app.core.config import get_settings
from app.llm import LLMUnavailable, ShoppingParse
from tests.support.live import live, live_model
from app.main import app

pytestmark = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")
URL = "/api/v1/agent/recommend"


class ScriptedShopper:
    name = "scripted"

    def __init__(self, parse: ShoppingParse | Exception) -> None:
        self.parse = parse

    def parse_shopping_request(self, request):
        if isinstance(self.parse, Exception):
            raise self.parse
        return self.parse


def agent(parse, request="a request", status=200, graph=None):
    app.dependency_overrides[get_llm] = lambda: ScriptedShopper(parse)
    if graph is not None:
        app.dependency_overrides[get_graph] = lambda: graph
    try:
        with TestClient(app) as c:
            r = c.post(URL, json={"request": request})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == status, r.text
    return r.json()


def test_recommends_a_verified_part_that_fits_with_graph_evidence_and_delivery():
    r = agent(ShoppingParse(True, machine="NV-4500", part_type="hydraulic hose", delivery_place="Zwolle"), "I need a hydraulic hose for my NV-4500, delivered to Zwolle")
    assert r["state"] == "recommendation" and r["recommended"] == "NVM-1010-HY"
    best = next(c for c in r["candidates"] if c["recommended"])
    assert best["part"]["availability"]["part_status"] == "VERIFIED" and best["part"]["price"]["amount"] > 0
    assert any(f["model_code"] == "NV-4500" for f in best["part"]["fitment"])
    keys = {e["key"]: e for e in r["evidence"]}
    assert keys["fit"]["ok"] and keys["verified"]["ok"] and keys["delivery"]["ok"] and r["delivery"]["city"] == "Zwolle"
    assert [s["status"] for s in r["steps"]] == ["done"] * 9 and r["reason"].startswith("Recommended because it fits the NV-4500")


def test_fastest_ranks_by_availability_and_cheapest_by_price():
    fast = agent(ShoppingParse(True, machine="NV-4500", part_type="brake pad", preference="fastest"))
    cheap = agent(ShoppingParse(True, machine="NV-4500", part_type="brake pad", preference="cheapest"))
    rank = {"In stock": 0, "Limited": 1, "Backorder": 2}
    f = [rank[c["availability_label"]] for c in fast["candidates"]]
    assert f == sorted(f)
    prices = [c["part"]["price"]["amount"] for c in cheap["candidates"]]
    assert prices == sorted(prices)


def test_the_order_gate_excludes_parts_that_are_not_verified():
    r = agent(ShoppingParse(True, machine="NV-7500", part_type="track roller assembly"), "I need a track roller for my NV-7500")
    assert r["recommended"] != "NVM-1140-DT" and all(c["part"]["part_number"] != "NVM-1140-DT" for c in r["candidates"])
    assert any(e["part_number"] == "NVM-1140-DT" and e["status_label"] == "Identification required" for e in r["excluded"])


def test_ambiguous_machine_offers_the_matching_machines():
    r = agent(ShoppingParse(True, machine="loader", part_type="bucket"), "I need a bucket for the loader")
    assert r["state"] == "choose_machine" and len(r["options"]) > 1 and r["candidates"] == []
    assert all(o["refine"].startswith("for my ") for o in r["options"])


def test_missing_machine_offers_only_machines_the_part_fits():
    r = agent(ShoppingParse(True, part_type="water pump"), "I need a water pump")
    assert r["state"] == "need_machine" and {o["label"] for o in r["options"]} == {"NV-4500", "NV-6000"}


def test_missing_part_asks_instead_of_guessing():
    r = agent(ShoppingParse(True, machine="NV-4500"), "something for my NV-4500")
    assert r["state"] == "need_part" and r["options"] and r["candidates"] == [] and "won't guess" in r["question"]


def test_unknown_machine_is_not_invented():
    r = agent(ShoppingParse(True, machine="ZX-9999", part_type="filter"))
    assert r["state"] == "need_machine" and "ZX-9999" in r["question"]


def test_no_fitment_means_no_recommendation_and_says_where_it_does_fit():
    r = agent(ShoppingParse(True, machine="KFT-200", part_type="water pump"), "water pump for my KFT-200")
    assert r["state"] == "no_match" and r["candidates"] == [] and any("NV-4500" in n for n in r["notes"])


def test_several_kinds_of_part_ask_which_kind():
    r = agent(ShoppingParse(True, machine="NV-4500", part_type="hydraulic"), "something hydraulic for my NV-4500")
    assert r["state"] == "choose_type" and len(r["options"]) > 1 and r["recommended"] is None


class NoGraph:
    def read(self, *a, **k):
        raise AssertionError("an out-of-scope request reached Neo4j")

    def close(self):
        pass


def test_out_of_scope_requests_never_reach_the_graph():
    r = agent(ShoppingParse(False), "What is the capital of France?", graph=NoGraph())
    assert r["state"] == "out_of_scope" and r["candidates"] == [] and "Parts Intelligence" in r["question"]


def test_model_unavailable_is_a_clear_503():
    r = agent(LLMUnavailable("rate limit"), status=503)
    assert r["error"]["code"] == "llm_unavailable"


def test_suggestions_come_from_the_graph():
    with TestClient(app) as c:
        s = c.get("/api/v1/agent/suggestions").json()
    assert len(s) == 4 and all(any(code in x["request"] for code in ("NV-", "KFT-", "BTS-")) for x in s)
    assert all(x["need"] and x["context"] and x["action"] for x in s)  # need -> context -> action


def test_no_order_is_placed_and_no_customer_data_is_returned():
    r = agent(ShoppingParse(True, machine="NV-4500", part_type="hydraulic hose"))
    blob = json.dumps(r)
    assert "CUS-" not in blob and "ORD-" not in blob and "No order is placed" in r["disclaimer"]


# ── Budget and constraints (scripted reading; every price, stock level and fitment comes from the graph) ──────────
def fan(budget=None, **kw):
    return agent(ShoppingParse(True, machine="NV-4500", part_type="cooling fan", budget_max=budget, **kw), "I need a cooling fan for NV-4500")


def graph_price(r):
    return next(c for c in r["candidates"] if c["recommended"])["part"]["price"]["amount"]


def test_budget_1_a_part_within_budget_is_recommended_with_budget_evidence():
    r = fan(800)
    assert r["state"] == "recommendation" and r["recommended"] == "NVM-1020-CL"
    best = r["candidates"][0]
    assert best["within_budget"] is True and best["part"]["price"]["amount"] <= 800 and best["can_add_to_cart"]
    budget = next(e for e in r["evidence"] if e["key"] == "budget")
    assert "within your €800 budget" in budget["label"] and "€800 budget" in r["reason"]
    assert r["interpretation"]["budget_max"] == 800 and r["interpretation"]["budget_currency"] == "EUR"


def test_budget_2_nothing_within_budget_says_so_and_does_not_relax():
    r = fan(500)
    assert r["state"] == "no_match" and r["candidates"] == [] and r["recommended"] is None
    assert "none currently meets your €500 budget" in r["question"] and "€645.38" in r["question"]


def test_budget_3_no_matter_what_under_10_without_a_part_asks_instead_of_returning_anything():
    r = agent(ShoppingParse(True, budget_max=10), "No matter what, find me a part under €10")
    assert r["state"] in ("need_part", "need_machine") and r["candidates"] == [] and r["recommended"] is None


def test_budget_4_no_matter_what_under_10_for_a_real_part_returns_nothing_incompatible_or_unverified():
    r = agent(ShoppingParse(True, machine="NV-4500", part_type="brake pad", budget_max=10), "No matter what, find me a brake pad under €10 for my NV-4500")
    assert r["state"] == "no_match" and r["candidates"] == [] and "€10 budget" in r["question"]


def test_budget_5_a_price_equal_to_the_budget_is_within_it():
    price = graph_price(fan())
    r = fan(price)
    assert r["state"] == "recommendation" and r["candidates"][0]["within_budget"] is True


def test_budget_6_a_budget_in_another_currency_is_not_converted():
    r = fan(800, budget_currency="USD")
    assert r["state"] == "need_detail" and "euros" in r["question"] and r["candidates"] == []


def test_budget_7_a_budget_between_prices_keeps_only_the_options_within_it():
    full = agent(ShoppingParse(True, machine="NV-4500", part_type="brake pad", preference="cheapest"))
    prices = sorted(c["part"]["price"]["amount"] for c in full["candidates"])
    assert len(prices) > 1 and prices[0] < prices[-1]
    cap = (prices[0] + prices[-1]) / 2
    r = agent(ShoppingParse(True, machine="NV-4500", part_type="brake pad", budget_max=cap))
    assert r["state"] == "recommendation" and all(c["part"]["price"]["amount"] <= cap and c["within_budget"] for c in r["candidates"])


def test_budget_8_cheapest_within_budget_ranks_by_price():
    r = agent(ShoppingParse(True, machine="NV-4500", part_type="brake pad", preference="cheapest", budget_max=100000))
    prices = [c["part"]["price"]["amount"] for c in r["candidates"]]
    assert prices == sorted(prices) and next(e for e in r["evidence"] if e["key"] == "ranking")["label"].startswith("Lowest recorded price")


def test_budget_9_must_be_available_now_keeps_only_parts_with_stock():
    r = agent(ShoppingParse(True, machine="NV-4500", part_type="brake pad", availability="require"))
    assert r["state"] == "recommendation" and all(c["availability_label"] in ("In stock", "Limited") for c in r["candidates"])


def test_budget_10_fastest_puts_stocked_parts_first():
    r = agent(ShoppingParse(True, machine="NV-4500", part_type="brake pad", preference="fastest"))
    stocked = [c["availability_label"] in ("In stock", "Limited") for c in r["candidates"]]
    assert stocked == sorted(stocked, reverse=True)


def test_budget_11_a_huge_budget_never_admits_an_unverified_part():
    r = agent(ShoppingParse(True, machine="NV-7500", part_type="track roller assembly", budget_max=1_000_000))
    assert all(c["part"]["part_number"] != "NVM-1140-DT" for c in r["candidates"])


def test_budget_12_alternatives_show_real_tradeoffs_against_the_recommendation():
    r = agent(ShoppingParse(True, machine="NV-4500", part_type="brake pad", preference="cheapest"))
    best, *alts = r["candidates"]
    assert best["tradeoffs"] == [] and alts
    for a in alts:
        if a["part"]["price"]["amount"] != best["part"]["price"]["amount"]:
            assert "Higher price" in a["tradeoffs"]


def test_budget_13_without_a_budget_nothing_claims_a_budget():
    r = fan()
    assert r["interpretation"]["budget_max"] is None and r["candidates"][0]["within_budget"] is None and "budget" not in r["reason"]


def test_budget_14_out_of_scope_with_a_budget_still_never_reaches_the_graph():
    r = agent(ShoppingParse(False, budget_max=500), "Book me a flight to Paris under €500", graph=NoGraph())
    assert r["state"] == "out_of_scope" and r["candidates"] == []


def test_budget_15_changing_a_price_in_the_graph_changes_the_decision():
    real = GraphClientProxy(price_override=("NVM-1020-CL", 900.0))
    r = agent(ShoppingParse(True, machine="NV-4500", part_type="cooling fan", budget_max=800), graph=real)
    assert r["state"] == "no_match" and "€900" in r["question"]


class GraphClientProxy:
    """The live graph, with one part's price row rewritten in flight (the stored graph is not touched)."""

    def __init__(self, price_override):
        from app.graph.client import GraphClient

        self._g = GraphClient(get_settings())
        self._part, self._price = price_override

    def read(self, *a, **k):
        rows = self._g.read(*a, **k)
        for r in rows:
            if r.get("part_number") == self._part and isinstance(r.get("price"), dict):
                r["price"] = {**r["price"], "amount": self._price}
        return rows

    def close(self):
        self._g.close()


# ── Part 2: the real provider (opt-in) ───────────────────────────────────────────────────────────────────────────


@live
@pytest.mark.parametrize("request_text,state", [
    ("I need a hydraulic hose for my NV-4500, delivered to Zwolle.", "recommendation"),
    ("My NV-4500 is down. I need brake pads as soon as possible.", "recommendation"),
    ("I need a water pump.", "need_machine"),
    ("Which machines use NVM-1050-CL?", "out_of_scope"),  # an investigation belongs to Parts Intelligence
    ("Tell me a joke.", "out_of_scope"),
])
def test_live_model_reads_shopping_requests(request_text, state):
    model = live_model()
    app.dependency_overrides[get_llm] = lambda: model
    try:
        with TestClient(app) as c:
            time.sleep(1.0)
            for _ in range(3):  # the free tier's per-minute quota is shared with the other live tests
                r = c.post(URL, json={"request": request_text})
                if r.status_code != 503:
                    break
                time.sleep(25)
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert r.json()["state"] == state, (request_text, r.json()["state"], r.json()["interpretation"])


# ── a complete commercial decision: no empty decision fields (cases 1-7 of the recommendation brief) ─────────────
DECISION_FIELDS = ("availability_label", "fitment_label", "inventory", "fulfilment", "delivery", "supplier_label")


def air_filter(**kw):
    return agent(ShoppingParse(True, machine="NV-3200", part_type="air filter", **kw), "I need an air filter for my NV-3200")


def assert_complete(candidate):
    for field in DECISION_FIELDS:
        value = candidate[field]
        assert isinstance(value, str) and value.strip() and value.strip() not in ("-", "—", "N/A", "null"), (field, value)


def test_case1_prefer_in_stock_is_complete_and_explained():
    r = air_filter(availability="prefer")
    assert r["state"] == "recommendation" and r["recommended"] == "NVM-1020-FL"
    best, alt = r["candidates"]
    for c in r["candidates"]:
        assert_complete(c)
    assert best["fitment_label"] == "Confirmed fit" and best["availability_label"] == "In stock"
    assert best["inventory"].startswith("81 units") and best["fulfilment"].startswith("Available from") and best["delivery"] == "Estimate not recorded"
    assert best["price_basis"] == "ex VAT" and best["order_action"] == "add_to_cart" and best["stock_locations"]
    assert "lead time" not in best["supplier_label"]  # a supplier lead time does not apply to stock already on the shelf
    assert alt["part"]["part_number"] == "NVM-1010-FL" and alt["availability_label"] == "Backorder" and alt["fulfilment"] == "Supplier lead time · 10 days"
    assert r["decision"]["priorities"][0] == "In-stock availability" and "NVM-1020-FL ranked first" in r["decision"]["summary"]
    titles = [w["title"] for w in r["why"]]
    assert titles[:2] == ["Confirmed compatibility", "In stock"] and "Better availability" in titles and "Lower price" in titles
    assert "availability was prioritised before price" in r["why"][-1]["detail"]
    assert {h["label"] for h in r["how_we_know"]} >= {"Fitment", "Price", "Inventory", "Supplier", "Ranking"}


def test_case2_no_option_within_a_50_budget():
    r = air_filter(budget_max=50)
    assert r["state"] == "no_match" and r["candidates"] == [] and "€50 budget" in r["question"]


def test_case3_cheapest_is_the_lowest_verified_price_and_says_so():
    r = air_filter(preference="cheapest")
    prices = [c["part"]["price"]["amount"] for c in r["candidates"]]
    assert prices == sorted(prices) and r["decision"]["priorities"][0] == "Lowest price"
    assert "cheapest" in r["why"][-1]["detail"]


def test_case4_fastest_puts_stock_and_fulfilment_before_price():
    r = air_filter(preference="fastest")
    assert r["decision"]["priorities"][:2] == ["In-stock availability", "Fastest recorded fulfilment"]
    assert r["candidates"][0]["availability_label"] == "In stock"


def test_case5_no_priority_uses_the_default_ranking_without_asking():
    r = air_filter()
    assert r["state"] == "recommendation" and r["decision"]["priorities"] == ["Availability", "Price"]
    assert "default" in r["why"][-1]["detail"]


def test_case6_and_7_delivery_has_an_explicit_state():
    unknown = air_filter(delivery_place="Atlantis")
    assert unknown["candidates"][0]["delivery"] == "No delivery estimate recorded to Atlantis"
    recorded = air_filter(delivery_place="Zwolle")
    best = recorded["candidates"][0]
    assert "to Zwolle" in best["delivery"] and best["fulfilment"].startswith("Ships from") and recorded["delivery"]["city"] == "Zwolle"


def test_a_single_option_has_no_alternatives_and_is_still_complete():
    r = agent(ShoppingParse(True, machine="NV-4500", part_type="cooling fan"))
    assert len(r["candidates"]) == 1 and r["candidates"][0]["recommended"]
    assert_complete(r["candidates"][0])
