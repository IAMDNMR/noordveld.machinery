"""Spark multi-turn regression: the bucket transcript replayed through /spark/conversation and /spark/order exactly as the browser drives them.

The language model is scripted (what it would read from each message); everything checked here is what the server does with that reading:
which part is ordered, which constraints survive each turn, what is asked next, and what is recalculated. Each step asserts the reply AND the
structured state (slots) the browser keeps and sends back."""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_commerce_agent, get_orders_repository, get_part_service
from app.api.routes import spark, spark_voice
from app.api.routes.profile import get_profile_store
from app.api.routes.spark import get_spark_llm
from app.core.exceptions import NotFoundError
from app.main import app
from app.schemas.agent import AgentResponse, Candidate, Interpretation
from app.schemas.catalogue import PartDetail
from app.schemas.spark import SparkPlan
from app.schemas.spark_order import OrderMessage
from app.services.profile import ProfileStore
from app.services.spark import resolve_order_part
from tests.support.fake_orders import FakeRepo, part

TODAY = dt.date.today()
CONTACT = {"name": "Anna de Vries", "company": "De Vries Bouw B.V.", "email": "anna@buyer.example", "phone": "+31 20 555 0100",
           "receiver_name": "Rita Receiver", "receiver_phone": "+49 40 1234567"}
FITS = {"P-AB-1": ["M-1"], "P-AB-9": ["M-1"], "P-AB-2": ["M-2"]}


class Parts:
    """Catalogue detail by part id or number, like the graph query."""

    def detail(self, key):
        pid = key if key.startswith("P-") else f"P-{key}"
        if pid not in FITS:
            raise NotFoundError("Part", key)
        return PartDetail(
            part={"part_id": pid, "part_number": pid.removeprefix("P-"), "name": f"Bucket {pid}"},
            fitment=[{"machine_id": m, "model_code": m, "name": "Loader", "fitment_status": "CONFIRMED"} for m in FITS[pid]],
            specifications=[], legacy_references=[], price={"amount": 25.0, "currency": "EUR"},
            profile={"part_status": "VERIFIED", "orderable": True, "availability_state": "IN_STOCK"},
            warehouses=[], dealers=[], suppliers=[], compliance=[], assemblies=[], identification=[], related=[])


class Model:
    """Scripted language model: `plan` for Spark routing, `reading` for a reply inside the order."""

    def __init__(self):
        self.plan = SparkPlan(intelligence=None, shopping=None, account=None, clarification=None)
        self.reading = OrderMessage(relevant=True)
        self.order_prompts: list[str] = []

    def parse_spark_request(self, rules, prompt):
        return self.plan

    def parse_order_message(self, rules, prompt):
        self.order_prompts.append(prompt)
        return self.reading


def recommendation(text):
    cands = [Candidate(part=part("P-AB-1"), recommended=True, availability_label="In stock"),
             Candidate(part=part("P-AB-9"), recommended=False, availability_label="In stock")]
    return AgentResponse(request=text, state="recommendation", steps=[], candidates=cands, recommended="AB-1",
                         interpretation=Interpretation(machine="M-1", part_type="bucket", budget_max=2200, budget_currency="EUR"))


@pytest.fixture()
def world():
    repo, model, store = FakeRepo(), Model(), ProfileStore(":memory:")
    overrides = {get_orders_repository: lambda: repo, get_part_service: Parts, get_spark_llm: lambda: model, get_profile_store: lambda: store,
                 spark.spark_shopping: lambda: SimpleNamespace(recommend=recommendation), spark.spark_questions: lambda: None,
                 get_commerce_agent: lambda: None}
    app.dependency_overrides.update(overrides)
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"user_id": "U-ANNA"}).status_code == 200
    yield c, repo, model
    for dep in overrides:
        app.dependency_overrides.pop(dep, None)


def say(c, model, message, context=None, order_part=None, **plan):
    spark_voice._requests.clear()
    model.plan = SparkPlan(**{"intelligence": None, "shopping": None, "account": None, "clarification": None, **plan})
    r = c.post("/api/v1/spark/conversation", json={"message": message, "context": context, "order_part": order_part})
    assert r.status_code == 200, r.text
    return r.json()


def order(c, model, slots, message=None, reading=None, **kw):
    spark_voice._requests.clear()
    if reading is not None:
        model.reading = reading
    r = c.post("/api/v1/spark/order", json={"slots": slots, **({"message": message} if message else {}), **kw})
    assert r.status_code == 200, r.text
    out = r.json()
    assert not any("not valid" in w for w in out["warnings"]), out["warnings"]  # the transcript's error never comes back
    return out


def day(n):
    return (TODAY + dt.timedelta(days=n)).isoformat()


def test_bucket_transcript_keeps_every_choice_while_the_user_changes_their_mind(world):
    c, repo, model = world
    # 1. find a bucket under €2,200: the recommendation is remembered with its constraints
    found = say(c, model, "Find a bucket under €2,200 for my M-1", shopping="Find a bucket for M-1 under 2200 EUR")
    assert found["shopping"]["recommended"] == "AB-1"

    # 2. "I want it in one day, so order it": 'it' is the recommended bucket, and machine + budget travel with it
    start = say(c, model, "I want it in one day, so order it", found["context"], order="it")
    assert start["order_part"] == {"part_id": "P-AB-1", "label": "AB-1", "patch": {"machine": "M-1"}}  # the unit-price budget is already met, not an order total
    a = order(c, model, {"part_id": "P-AB-1"}, "I want it in one day, so order it", OrderMessage(relevant=True, needed_by=day(1)),
              patch=start["order_part"]["patch"])
    assert a["stage"] == "delivery" and "should it go" in a["ask"]["question"]  # the site the answer depends on
    assert (a["slots"]["machine"], a["slots"]["budget_eur"], a["slots"]["needed_by"]) == ("M-1", None, day(1))
    assert a["message"].startswith("Noted: you need it by")  # the delivery wish is acknowledged, not dropped
    assert '"part": "AB-1"' in model.order_prompts[-1]  # the reader sees what is already chosen

    # 3. "Can I get it in one day?" mid-quantity: answered, nothing reset, no validation error
    b = order(c, model, a["slots"], "Can I get it in one day?", OrderMessage(relevant=True, needed_by=day(1), preference="fastest"))
    assert b["slots"]["preference"] == "fastest" and b["slots"]["needed_by"] == day(1) and b["slots"]["machine"] == "M-1"
    assert b["stage"] == "delivery" and "depends on where it goes" in b["message"]

    # 4. "What if I want this in one or two days?": the constraint is replaced, everything else kept
    d = order(c, model, b["slots"], "What if I want this in one or two days?", OrderMessage(relevant=True, needed_by=day(2)))
    assert d["slots"]["needed_by"] == day(2) and d["slots"]["preference"] == "fastest"

    # 5. the site (a button): the delivery question is answered at once from recorded routes, for 1 unit until the quantity is known
    site = order(c, model, d["slots"], patch={"ship_to_id": "SHT-1", "country": "DE"})
    assert site["stage"] == "quantity" and site["message"].startswith("For 1 unit: Yes. Express road from Depot B (demo) (Lingen)")
    e = order(c, model, site["slots"], "2 please", OrderMessage(relevant=True, quantity=2))
    assert e["slots"]["quantity"] == 2 and e["slots"]["ship_to_id"] == "SHT-1" and e["slots"]["needed_by"] == day(2)

    # 6. compare delivery options: shown again, none picked for the user, standard vs express explained with real totals
    f = order(c, model, e["slots"], "Compare the delivery options", OrderMessage(relevant=True, compare_options=True))
    assert f["stage"] == "fulfilment" and f["slots"]["route_id"] is None and len(f["options"]) == 3
    assert "Yes. Express road from Depot B (demo) (Lingen) is estimated to arrive" in f["message"] and "costs €27.50 less, €62.50 in total" in f["message"]
    assert "not a guaranteed delivery date" in f["message"]

    # 7. keep the part, pay for the fastest: express is chosen, the part and quantity are untouched
    g = order(c, model, f["slots"], "Keep the same part but I'll pay more for the fastest", OrderMessage(relevant=True, preference="fastest"))
    assert g["slots"]["route_id"].endswith("EXPRESS_ROAD_EU") and (g["slots"]["part_id"], g["slots"]["quantity"]) == ("P-AB-1", 2)
    assert g["stage"] == "details"  # the only DE dealer was taken; only the contact details are still missing

    # 8. change quantity: stock re-checked, the same delivery priority re-applied, still at the step the user was on
    h = order(c, model, g["slots"], "Make it 3", OrderMessage(relevant=True, quantity=3))
    assert h["slots"]["quantity"] == 3 and h["slots"]["route_id"].endswith("EXPRESS_ROAD_EU") and h["stage"] == "details"

    # 9. change the part: fitment re-validated (M-1 still fits AB-9), price and route recalculated, quantity kept
    i = order(c, model, h["slots"], "Actually switch to AB-9", OrderMessage(relevant=True, part="ab 9"))
    assert (i["slots"]["part_id"], i["slots"]["machine"], i["slots"]["quantity"]) == ("P-AB-9", "M-1", 3)
    assert i["part"]["part_number"] == "AB-9" and i["slots"]["route_id"].endswith("EXPRESS_ROAD_EU")

    # 10. details -> review: everything is shown before anything is ordered
    review = order(c, model, i["slots"], patch=CONTACT)
    s = review["summary"]
    assert review["stage"] == "review" and review["order"] is None and not repo.keys
    assert (s["part"]["part_number"], s["quantity"], s["machine"], s["destination"]["city"], s["depot"]["name"]) == ("AB-9", 3, "M-1", "Hamburg", "Depot B (demo)")
    assert s["cost"]["part_cost"] == 75.0 and s["total"] == 115.0 and "excluding VAT" in s["cost_note"] and s["checks"]["meets_date"] is True

    # 11. refresh: the same slots give the same step and values (the server derives nothing from memory of its own)
    again = order(c, model, review["slots"])
    assert (again["stage"], again["slots"], again["summary"]["total"]) == ("review", review["slots"], 115.0)
    # reopening a finished step keeps every other choice: delivery options come back, details come back pre-filled
    back = order(c, model, review["slots"], revisit="fulfilment")
    assert back["stage"] == "fulfilment" and back["decision"]["status"] == "met" and back["slots"]["quantity"] == 3 and back["slots"]["name"] == CONTACT["name"]
    edit = order(c, model, review["slots"], revisit="details")
    assert edit["stage"] == "details" and {f["name"]: f["value"] for f in edit["ask"]["fields"]}["phone"] == CONTACT["phone"]

    # 12. confirm once; a retried confirm cannot create a second order; the status comes from the backend
    placed = order(c, model, review["slots"], confirm=True, idempotency_key="flow-key-0001", reviewed_total=115.0, confirmation=review["confirmation"])
    retry = order(c, model, review["slots"], confirm=True, idempotency_key="flow-key-0001", reviewed_total=115.0, confirmation=review["confirmation"])
    assert placed["stage"] == "placed" and retry["order"]["order_id"] == placed["order"]["order_id"] and len(repo.keys) == 1
    status = c.get(f"/api/v1/orders/{placed['order']['order_id']}").json()
    assert status["status"] == placed["order"]["status"] and status["lines"][0]["quantity"] == 3


def test_unavailable_dates_wrong_machines_unknown_parts_and_ambiguous_references_are_explained(world):
    c, _, model = world
    base = {"part_id": "P-AB-1", "quantity": 2, "machine": "M-1", "ship_to_id": "SHT-1", "country": "DE"}
    # nothing arrives today: said plainly, with the closest real alternative, and no option is presented as meeting it
    r = order(c, model, base, "I need it today", OrderMessage(relevant=True, needed_by=day(0)))
    assert "No recorded delivery option arrives by" in r["message"] and "The fastest is express road from Depot B" in r["message"]
    assert not any(o["meets_date"] for o in r["options"]) and not any(o["recommended"] for o in r["options"])
    # a date that only the dearer option meets: the answer says it breaks the budget, and what the cheaper one costs
    pricey = order(c, model, {**base, "budget_eur": 70}, "tomorrow?", OrderMessage(relevant=True, needed_by=day(1)))
    assert "That is over your budget of €70.00" in pricey["message"] and "costs €27.50 less" in pricey["message"]
    # ...and the comparison says no option meets both, nothing is called recommended, and the two closest trade-offs carry exact gaps
    d = pricey["decision"]
    assert d["status"] == "none" and d["feasible"] == 0 and not any(o["recommended"] for o in pricey["options"])
    assert [(a["title"], a["gap"]) for a in d["alternatives"]] == [("Meets your date", "€20.00 over budget"), ("Stays within budget", "1 day(s) after your date")]
    assert {a["label"] for a in d["actions"]} >= {"Drop the delivery date", "Drop the budget", "Prioritise fastest delivery"}
    # options that meet every limit are listed first
    both = order(c, model, {**base, "budget_eur": 100, "needed_by": day(2)})
    assert both["decision"]["status"] == "met" and all(o["days_late"] == 0 and o["over_budget"] == 0 for o in both["options"][:2])
    assert both["options"][-1]["days_late"] == 2  # the 4-day route comes last, with its delay
    # a question before the site is known is acknowledged, then only the missing detail is asked
    early = order(c, model, {"part_id": "P-AB-1", "quantity": 2, "machine": "M-1"}, "tomorrow?", OrderMessage(relevant=True, needed_by=day(1)))
    assert early["message"].startswith("Noted: you need it by") and early["stage"] == "delivery" and early["slots"]["quantity"] == 2
    # switching to a part that does not fit the machine: the machine is re-asked, with the reason
    swap = order(c, model, base, "switch to AB-2", OrderMessage(relevant=True, part="AB-2"))
    assert swap["slots"]["part_id"] == "P-AB-2" and swap["slots"]["machine"] is None and swap["slots"]["quantity"] == 2
    assert any("not recorded as fitting M-1" in w for w in swap["warnings"])
    # an order opened by part number continues with the catalogue id, so checkout can price and route it
    assert order(c, model, {"part_id": "AB-1", "quantity": 2, "machine": "M-1", "ship_to_id": "SHT-1", "country": "DE", "timing_skipped": True})["stage"] == "fulfilment"
    # an unknown part number is refused and the current part kept
    keep = order(c, model, base, "switch to ZZ-404", OrderMessage(relevant=True, part="ZZ-404"))
    assert keep["slots"]["part_id"] == "P-AB-1" and any("not a part number in the catalogue" in w for w in keep["warnings"])
    # 'order it' with two offered parts and no recommendation is asked about, never guessed
    two = [{"kind": "PART", "label": "AB-1", "part_id": "P-AB-1"}, {"kind": "PART", "label": "AB-9", "part_id": "P-AB-9"}]
    assert resolve_order_part("it", two) is None and resolve_order_part("the AB-9", two) is None
    assert resolve_order_part("ab 9", two)["part_id"] == "P-AB-9" and resolve_order_part("it", [{**two[0], "recommended": True}, two[1]])["part_id"] == "P-AB-1"
    # mid-order, Spark resolves 'order it' to the part being ordered (the browser then continues that order)
    mid = say(c, model, "ok order it", order_part={"part_id": "P-AB-1", "label": "AB-1"}, order="it")
    assert mid["order_part"] == {"part_id": "P-AB-1", "label": "AB-1", "patch": {}}
