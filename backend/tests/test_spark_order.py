"""Spark's guided order journey: follow-ups, data accuracy, fulfilment recommendation, persistence and failure handling, over the in-memory graph stand-in."""
from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_orders_repository, get_part_service
from app.api.routes.spark import get_spark_llm
from app.api.routes import spark_voice
from app.api.routes.profile import get_profile_store
from app.services.profile import ProfileStore
from app.core.exceptions import NotFoundError
from app.main import app
from app.schemas.catalogue import PartDetail
from app.schemas.spark_order import OrderMessage
from tests.support.fake_orders import FakeRepo

CONTACT = {"name": "Anna de Vries", "company": "De Vries Bouw B.V.", "email": "anna@buyer.example", "phone": "+31 20 555 0100",
           "receiver_name": "Rita Receiver", "receiver_phone": "+49 40 1234567"}
STANDARD = "RTE-WH-B-SHT-1-STANDARD_ROAD_EU"


class Parts:
    def detail(self, key):
        if key not in ("P-AB-1", "P-XBAD"):
            raise NotFoundError("Part", key)
        ok = key == "P-AB-1"
        return PartDetail(
            part={"part_id": key, "part_number": key.removeprefix("P-"), "name": f"Part {key}"},
            fitment=[{"machine_id": "M-1", "model_code": "M-1", "name": "Loader", "fitment_status": "CONFIRMED"}],
            specifications=[], legacy_references=[], price={"amount": 25.0, "currency": "EUR"},
            profile={"part_status": "VERIFIED" if ok else "UNVERIFIED", "orderable": ok, "availability_state": "IN_STOCK"},
            warehouses=[], dealers=[{"dealer_id": "DLR-1", "name": "Dealer One (demo)", "available": 3}],
            suppliers=[{"supplier_id": "S-1", "name": "Supplier (demo)", "is_primary": True, "lead_time_days": 10}],
            compliance=[], assemblies=[], identification=[],
            related=[{"part_id": "P-AB-9", "part_number": "AB-9", "name": "Part AB-9", "relation": "SAME_NAME_GROUP_AS"}])


class Llm:
    reading = OrderMessage(relevant=True)

    def parse_order_message(self, rules, prompt):
        if isinstance(self.reading, Exception):
            raise self.reading
        return self.reading


@pytest.fixture()
def world():
    spark_voice._requests.clear()
    repo, llm, store = FakeRepo(), Llm(), ProfileStore(":memory:")
    app.dependency_overrides[get_orders_repository] = lambda: repo
    app.dependency_overrides[get_part_service] = lambda: Parts()
    app.dependency_overrides[get_spark_llm] = lambda: llm
    app.dependency_overrides[get_profile_store] = lambda: store
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"user_id": "U-ANNA"}).status_code == 200
    yield c, repo, llm
    for dep in (get_orders_repository, get_part_service, get_spark_llm, get_profile_store):
        app.dependency_overrides.pop(dep, None)


def turn(c, slots=None, **kw):
    r = c.post("/api/v1/spark/order", json={"slots": slots or {"part_id": "P-AB-1"}, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def full(**over):
    return {"part_id": "P-AB-1", "quantity": 2, "machine": "M-1", "ship_to_id": "SHT-1", "country": "DE", "dealer_id": "DLR-1", "timing_skipped": True, **CONTACT, **over}


def test_asks_only_for_what_is_missing_one_step_at_a_time(world):
    c, _, _ = world
    a = turn(c)
    assert a["stage"] == "quantity" and a["ask"]["kind"] == "number" and a["part"]["part_number"] == "AB-1"
    b = turn(c, {**a["slots"], "quantity": 2})
    assert b["ask"]["question"].startswith("Which machine") and b["ask"]["choices"][0]["patch"] == {"machine": "M-1"}
    d = turn(c, b["slots"], patch={"machine": "M-1"})
    assert d["stage"] == "delivery" and d["slots"]["quantity"] == 2 and d["slots"]["machine"] == "M-1"  # nothing asked twice
    assert d["stages"][1]["state"] == "done" and d["stages"][2]["state"] == "current"


def test_unorderable_and_unknown_parts_are_refused_with_related_parts_not_invented_substitutes(world):
    c, _, _ = world
    bad = turn(c, {"part_id": "P-XBAD"})
    assert bad["blocked"] and bad["stage"] == "part" and "can't be ordered" in bad["message"]
    assert bad["alternatives"][0]["part_number"] == "AB-9" and "Interchangeability is not recorded" in bad["alternatives"][0]["note"]
    assert turn(c, {"part_id": "P-NOPE"})["blocked"]


def test_recommendation_is_deterministic_explained_and_honours_date_and_budget(world):
    c, _, _ = world
    r = turn(c, full())
    assert r["stage"] == "fulfilment" and r["ask"]["field"] == "route_id"
    rec = [o for o in r["options"] if o["recommended"]]
    assert len(rec) == 1 and rec[0]["depot_id"] == "WH-B" and rec[0]["estimated_days"] == 1  # express: fastest recorded option
    assert "holds 20 in stock" in r["explanation"] and "(demo estimate)" in r["explanation"]
    assert all(o["depot_id"] != "WH-A" for o in r["options"])  # most stock but no route to the site: never offered
    cheap = turn(c, full(budget_eur=70))  # express totals 90.00, over budget
    assert [o["route_id"] for o in cheap["options"] if o["recommended"]] == [STANDARD]
    tomorrow = turn(c, full(needed_by=(dt.date.today() + dt.timedelta(days=1)).isoformat()))
    assert [o["estimated_days"] for o in tomorrow["options"] if o["meets_date"]] == [1]
    nothing = turn(c, full(budget_eur=1))
    assert not any(o["recommended"] for o in nothing["options"]) and "No recorded option satisfies" in nothing["explanation"]


def test_insufficient_stock_is_reported_never_invented_and_offers_what_is_real(world):
    c, repo, _ = world
    r = turn(c, full(quantity=30))  # WH-B holds 20; WH-C (40) is routed, so 30 can only come from WH-C
    assert r["stage"] == "review" and r["summary"]["depot"]["city"] == "Brno"  # the single feasible option is chosen, and said so
    assert any("only delivery option" in w for w in r["warnings"])
    r = turn(c, full(quantity=45))  # 500 at WH-A has no route to the site; no routed depot can supply 45
    assert r["stage"] == "fulfilment" and r["blocked"] and r["options"] is None
    assert "Not available as asked" in r["message"] and any(x["patch"] == {"quantity": 40} for x in r["ask"]["choices"])
    assert "restocking, not a stock-backed delivery" in r["message"]
    # another recorded site in the same city that a stocked depot reaches is offered, after the same check
    from tests.support.fake_orders import route
    repo.shiptos["SHT-3"] = {**repo.shiptos["SHT-1"], "shipto_id": "SHT-3", "street": "Kai 3"}
    repo.routes_.append(route("WH-A", "SHT-3", days=2))
    r = turn(c, full(quantity=45))
    assert any(x["patch"] == {"ship_to_id": "SHT-3", "route_id": None} for x in r["ask"]["choices"])


def test_review_requires_explicit_confirmation_and_creates_nothing_until_then(world):
    c, repo, _ = world
    r = turn(c, full(route_id=STANDARD))
    assert r["stage"] == "review" and r["ask"]["kind"] == "confirm" and r["order"] is None
    assert r["summary"]["total"] == 62.5 and "No payment" in r["ask"]["choices"][0]["detail"]
    assert r["summary"]["compared"] == 3 and "holds 20 in stock" in r["summary"]["why"]  # the review says why this option, and against how many
    assert repo.keys == {} and repo.writes == 0


def test_confirm_persists_the_order_once_and_a_retry_cannot_duplicate_it(world):
    c, repo, _ = world
    slots = full(route_id=STANDARD)
    placed = turn(c, slots, confirm=True, idempotency_key="spark-key-0001", reviewed_total=62.5)
    assert placed["stage"] == "placed" and placed["order"]["order_id"] == "NM-ORD001"
    again = turn(c, slots, confirm=True, idempotency_key="spark-key-0001", reviewed_total=62.5)
    assert again["order"]["order_id"] == "NM-ORD001" and len(repo.keys) == 1
    stored = c.get("/api/v1/orders/NM-ORD001").json()  # it really exists in the backend, in the user's own orders
    assert stored["lines"][0]["quantity"] == 2 and stored["channel"] == "DIRECT_ORDER"


def test_confirm_without_key_changed_price_or_missing_details_places_nothing(world):
    c, repo, _ = world
    slots = full(route_id=STANDARD)
    assert turn(c, slots, confirm=True)["order"] is None
    changed = turn(c, slots, confirm=True, idempotency_key="spark-key-0002", reviewed_total=50.0)
    assert changed["stage"] == "review" and "changed from €50.00 to €62.50" in " ".join(changed["warnings"])
    incomplete = turn(c, {**slots, "phone": None}, confirm=True, idempotency_key="spark-key-0003")
    assert incomplete["stage"] == "details" and incomplete["order"] is None and not repo.keys


def test_stock_taken_between_review_and_confirm_refreshes_options_instead_of_ordering(world):
    c, repo, _ = world
    repo.stock[("P-AB-1", "WH-C")]["available"] = 5
    r = turn(c, full(route_id="RTE-WH-C-SHT-1-STANDARD_ROAD_EU", quantity=30), confirm=True, idempotency_key="spark-key-0004")
    assert r["order"] is None and r["stage"] == "fulfilment" and r["blocked"] and not repo.keys


def test_free_text_fills_slots_the_graph_can_verify_and_ignores_the_rest(world):
    c, _, llm = world
    llm.reading = OrderMessage(relevant=True, quantity=3, machine="m 1", destination="hamburg", budget_eur=500)
    r = turn(c, {"part_id": "P-AB-1"}, message="3 for my M-1 to Hamburg, budget 500")
    assert (r["slots"]["quantity"], r["slots"]["machine"], r["slots"]["ship_to_id"], r["slots"]["budget_eur"]) == (3, "M-1", "SHT-1", 500)
    llm.reading = OrderMessage(relevant=True, machine="NV-9999", destination="atlantis")
    r = turn(c, {"part_id": "P-AB-1", "quantity": 1}, message="NV-9999 to Atlantis")
    assert r["slots"]["machine"] is None and r["slots"]["ship_to_id"] is None
    assert any("not recorded as a machine" in w for w in r["warnings"]) and any("No recorded delivery site" in w for w in r["warnings"])
    llm.reading = OrderMessage(relevant=False)
    assert turn(c, {"part_id": "P-AB-1"}, message="where is my last order?")["handled"] is False


def test_model_failure_keeps_the_journey_intact_and_stale_values_are_dropped(world):
    c, _, llm = world
    llm.reading = RuntimeError("quota")
    r = turn(c, {"part_id": "P-AB-1", "quantity": 2}, message="Hamburg")
    assert r["slots"]["quantity"] == 2 and any("couldn't read that reply" in w for w in r["warnings"])
    stale = turn(c, {"part_id": "P-AB-1", "quantity": 2, "machine_skipped": True, "ship_to_id": "SHT-GONE", "dealer_id": "DLR-X"})
    assert stale["stage"] == "delivery" and stale["slots"]["ship_to_id"] is None


def test_sign_in_and_role_are_required(world):
    spark_voice._requests.clear()
    anon = TestClient(app)
    assert anon.post("/api/v1/spark/order", json={"slots": {}}).status_code == 401
    jane = TestClient(app)
    jane.post("/api/v1/auth/login", json={"user_id": "U-JANE"})
    assert jane.post("/api/v1/spark/order", json={"slots": {"part_id": "P-AB-1"}}).status_code == 403


PROFILE = {"consent": True, "preferred_machine": "M-1", "ship_to_id": "SHT-1", "dealer_id": "DLR-1", **CONTACT, "delivery_preference": "cheapest"}


def test_profile_is_stored_only_with_consent_and_can_be_erased(world):
    c, _, _ = world
    assert c.get("/api/v1/me/profile").json()["stored"] is False
    c.put("/api/v1/me/profile", json={**PROFILE, "consent": False})
    assert c.get("/api/v1/me/profile").json()["stored"] is False  # no consent: nothing kept
    saved = c.put("/api/v1/me/profile", json=PROFILE).json()
    assert saved["stored"] and saved["profile"]["ship_to_id"] == "SHT-1" and saved["consent_at"]
    assert c.put("/api/v1/me/profile", json={**PROFILE, "unknown_field": 1}).status_code == 422
    assert c.delete("/api/v1/me/profile").json()["profile"] is None
    assert TestClient(app).get("/api/v1/me/profile").status_code == 401


def test_profile_prefills_what_spark_would_ask_and_the_user_still_confirms_everything(world):
    c, repo, _ = world
    first = turn(c, {"part_id": "P-AB-1", "quantity": 2})
    assert first["stage"] == "quantity" and first["prefilled"] == []  # no profile: asked as usual
    c.put("/api/v1/me/profile", json=PROFILE)
    r = turn(c, {"part_id": "P-AB-1", "quantity": 2})
    assert r["slots"]["machine"] == "M-1" and r["slots"]["ship_to_id"] == "SHT-1" and r["slots"]["dealer_id"] == "DLR-1" and r["slots"]["phone"] == CONTACT["phone"]
    assert "machine M-1" in r["prefilled"] and r["ask"]["kind"] == "date"  # timing is still asked; quantity was never guessed
    review = turn(c, {**r["slots"], "timing_skipped": True, "route_id": STANDARD})
    assert review["stage"] == "review" and review["summary"]["checks"]["timing"] == "As soon as possible" and not repo.keys
    # an explicit "change delivery site" is not silently refilled from the profile
    again = turn(c, review["slots"], patch={"ship_to_id": None, "route_id": None})
    assert again["slots"]["ship_to_id"] is None and again["ask"]["choices"]
    # stale profile values are validated, never trusted
    c.put("/api/v1/me/profile", json={**PROFILE, "ship_to_id": "SHT-GONE", "preferred_machine": "NV-0"})
    stale = turn(c, {"part_id": "P-AB-1", "quantity": 2})
    assert stale["slots"]["ship_to_id"] is None and stale["slots"]["machine"] is None


def test_after_an_order_a_new_profile_is_offered_not_saved(world):
    c, repo, _ = world
    placed = turn(c, full(route_id=STANDARD), confirm=True, idempotency_key="spark-key-0009", reviewed_total=62.5)
    assert placed["profile_offer"]["ship_to_id"] == "SHT-1" and placed["profile_offer"]["preferred_machine"] == "M-1"
    assert c.get("/api/v1/me/profile").json()["stored"] is False  # offered only; saving needs the user's own yes
    c.put("/api/v1/me/profile", json={**PROFILE, "name": CONTACT["name"]})
    again = turn(c, full(route_id=STANDARD), confirm=True, idempotency_key="spark-key-0010", reviewed_total=62.5)
    assert again["profile_offer"] is None  # nothing new to remember


def test_spark_routing_sees_only_consented_machine_facts_and_says_when_it_used_them():
    import json as _json
    from app.api.routes.spark import used_profile
    from app.schemas.spark import SparkPlan
    from app.services.spark import interpret

    seen = {}

    class Model:
        def parse_spark_request(self, rules, prompt):
            seen["prompt"] = _json.loads(prompt)
            return SparkPlan(intelligence=None, shopping="Find a hydraulic hose for machine M-1", account=None, clarification=None)

    profile = {**PROFILE, "machines": ["M-2"]}
    plan = interpret(Model(), "I need a hydraulic hose", {}, profile)
    assert seen["prompt"]["saved_profile"] == {"machines": ["M-1", "M-2"], "delivery_preference": "cheapest"}
    assert "phone" not in _json.dumps(seen["prompt"]) and CONTACT["email"] not in _json.dumps(seen["prompt"])  # contact details never reach the model
    assert used_profile(plan, "I need a hydraulic hose", profile) == ["machine M-1"]
    assert used_profile(plan, "a hose for M-1", profile) == []  # the user said it themselves
    interpret(Model(), "hello", {}, None)
    assert "saved_profile" not in seen["prompt"]


def test_a_saved_city_with_its_country_code_resolves_to_that_city():
    from app.agent.supply import resolve_destination

    sites = [{"city": "Almelo", "country_code": "NL", "shipto_id": "S-1"}, {"city": "Almere", "country_code": "NL", "shipto_id": "S-2"}]
    for place in ("Almelo NL", "Almelo, NL", "almelo"):
        assert resolve_destination(place, sites).shipto_ids == ["S-1"], place
    assert resolve_destination("NL", sites).kind == "country"


def test_a_search_alias_never_turns_another_kind_of_part_into_the_requested_one():
    """A water pump carrying the alias 'hydraulic pump' is not offered for 'hydraulic pump'; a real hydraulic pump is."""
    from types import SimpleNamespace as N
    from app.agent.service import AgentService

    svc = AgentService.__new__(AgentService)
    svc._g = N(read=lambda query, **_: [{"names": ["Cooling", "Water pump", "Hydraulics", "Gear pump"]}])
    water = N(name="Water pump", category="Cooling", subcategory="Water pump")
    gear = N(name="Gear pump, 28cc/rev", category="Hydraulics", subcategory="Gear pump")
    assert svc._same_class("hydraulic pump", [water, gear]) == [gear]
    assert svc._same_class("pump", [water, gear]) == [water, gear]  # no class word beyond the one both share
    assert svc._same_class("bucket", [water]) == [water]  # words that name no product class never filter


def test_auto_order_fills_what_it_can_asks_only_the_gaps_and_a_yes_only_signals_confirmation(world):
    c, repo, llm = world
    start = {"part_id": "P-AB-1", "ship_to_id": "SHT-1", "country": "DE"}
    a = turn(c, start, patch={"auto": True})
    # quantity, machine, timing, route and dealer are chosen; only contact details the account lacks are asked
    assert a["stage"] == "details" and a["slots"]["quantity"] == 1 and a["slots"]["machine"] == "M-1"
    asked = [f["name"] for f in a["ask"]["fields"]]
    assert asked and set(asked) <= {"phone", "receiver_name", "receiver_phone"} and a["message"].startswith("To place it I only need")
    llm.reading = OrderMessage(relevant=True, phone="+31 20 555 0100", receiver_name="Ricky Receiver", receiver_phone="+31 20 555 0100")
    b = turn(c, a["slots"], message="+31 20 555 0100, Ricky receives it, same number for both")
    assert b["stage"] == "review" and b["message"].startswith("Ready to order 1 × AB-1") and "I chose 1 unit" in b["message"]
    llm.reading = OrderMessage(relevant=True, proceed=True)
    before = len(repo.orders_)
    yes = turn(c, b["slots"], message="yes, place it")
    assert yes["confirm_ready"] and yes["order"] is None and len(repo.orders_) == before  # the client places it with the total it showed
    # a value the user sets is no longer an assumption
    assert "quantity" not in turn(c, b["slots"], patch={"quantity": 3})["slots"]["assumed"]
    # 'ok, continue' in the stepwise journey takes the quantity shown instead of asking again
    assert turn(c, message="ok, continue")["slots"]["quantity"] == 1
