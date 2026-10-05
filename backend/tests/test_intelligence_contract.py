"""Parts Intelligence answer contract: what each intent may return, what the wording may say, and warehouse-anchored questions.

Deterministic: no real language model is called. The model is scripted (what it understood and, where a test needs it, the wording it wrote),
so these prove what the BACKEND does with it. The graph-backed tests read the live graph (read-only) and skip when it is not configured.
"""
from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_graph, get_llm
from app.core.config import get_settings
from app.intelligence.contract import enforce_result_kinds
from app.intelligence.grounding import contradicts, grounding_records
from app.intelligence.models import Intent, Outcome
from app.intelligence.registry import HINTS, REGISTRY, RESULT_KINDS, answerable_intents
from app.llm import LLMParse, LLMUnavailable
from app.main import app
from app.schemas.intelligence import Fact, QueryRequest, ResultItem
from tests.test_intelligence_unit import FakeLLM, FakeRepo, ask, row, service

needs_graph = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")
V1 = "/api/v1/intelligence"
KINDS = set(ResultItem.model_fields["kind"].annotation.__args__)


# ── helpers ──────────────────────────────────────────────────────────────────────────────────────
class Capturing(FakeLLM):
    """A model that understood the question as scripted and wrote `reply`; remembers the evidence it was given."""

    def __init__(self, parse: LLMParse, reply: str) -> None:
        super().__init__(parse=parse, reply=reply)
        self.seen: list[dict] = []

    def generate_grounded_response(self, question, intent, evidence, draft):
        self.seen = evidence
        return self.reply


class Spy:
    """Wraps a repository and records every call, to prove a question never reached the graph."""

    def __init__(self, inner: Any) -> None:
        self.inner, self.calls = inner, []

    def __getattr__(self, name: str):
        attr = getattr(self.inner, name)

        def call(*a, **k):
            self.calls.append(name)
            return attr(*a, **k)
        return call


class Scripted:
    name = "scripted"

    def __init__(self, parse: LLMParse, reply: str | None = None) -> None:
        self.parse, self.reply, self.seen = parse, reply, []

    def parse_question(self, question, intents):
        return self.parse

    def resolve_entities(self, question, intents):
        return ()

    def generate_grounded_response(self, question, intent, evidence, draft):
        self.seen = evidence
        if self.reply is None:
            raise LLMUnavailable("not used")
        return self.reply


def graph_ask(parse: LLMParse, question: str = "any question", reply: str | None = None, **extra) -> dict:
    model = Scripted(parse, reply)
    app.dependency_overrides[get_llm] = lambda: model
    try:
        with TestClient(app) as c:
            r = c.post(f"{V1}/query", json={"question": question, **extra})
    finally:
        app.dependency_overrides.pop(get_llm, None)
    assert r.status_code == 200, r.text
    body = r.json()
    body["_model_saw"] = model.seen
    return body


def parse(intent: str, **entities: str) -> LLMParse:
    return LLMParse(intent, tuple(entities.values()), entities=entities)


SUPPLIERS = [
    {"supplier_id": "S-1", "name": "Alpha Supply (demo)", "city": "A-town", "country_code": "NL", "is_primary": True, "lead_time_days": 28, "supplier_part_number": None, "categories": [], "data_status": "SYNTHETIC_DEMO"},
    {"supplier_id": "S-2", "name": "Beta Supply (demo)", "city": "B-town", "country_code": "DE", "is_primary": False, "lead_time_days": 3, "supplier_part_number": None, "categories": [], "data_status": "SYNTHETIC_DEMO"},
]
WAREHOUSES = [
    {"warehouse_id": "W-1", "name": "North Depot", "city": "N", "country_code": "NL", "available": 48, "stock_status": "IN_STOCK", "data_status": "SYNTHETIC_DEMO"},
    {"warehouse_id": "W-2", "name": "South Depot", "city": "S", "country_code": "NL", "available": 20, "stock_status": "IN_STOCK", "data_status": "SYNTHETIC_DEMO"},
    {"warehouse_id": "W-3", "name": "East Depot", "city": "E", "country_code": "DE", "available": 0, "stock_status": "OUT_OF_STOCK", "data_status": "SYNTHETIC_DEMO"},
]
DEALERS = [{"dealer_id": "D-1", "name": "Dealer One (demo)", "city": "D", "country_code": "NL", "available": 3, "stocking_status": "STOCKED", "pickup_allowed": True, "dealer_type": None, "data_status": "SYNTHETIC_DEMO"}]
PART = row("PART", "PRT-1", "AB-1000-XY")
PART_SUBJECT = {"label": "AB-1000-XY", "name": "Air filter", "data_status": "SOURCE_DERIVED", "source": "Catalogue", "category": "Filtration", "subcategory": "Air filter", "part_status": "VERIFIED"}


def part_repo(**data):
    return FakeRepo({"ab-1000-xy": [PART]}, subject=lambda kind, id: PART_SUBJECT, **data)


# ── 2. the wording must never contradict the deterministic evidence (Q14, Q27) ──────────────────────────────────
PRIMARY_DENIALS = [
    "The evidence does not identify a primary supplier for AB-1000-XY.",
    "No primary supplier is recorded for AB-1000-XY.",
    "There is no primary supplier for AB-1000-XY, only Alpha Supply (demo) and Beta Supply (demo).",
]
QUANTITY_DENIALS = [
    "The evidence does not contain specific unit counts for AB-1000-XY.",
    "No quantity information is available for AB-1000-XY.",
    "AB-1000-XY is recorded at 3 warehouses, but the number of units is not stated.",
    "The stock level is unknown for AB-1000-XY.",
]


@pytest.mark.parametrize("wording", PRIMARY_DENIALS)
def test_q14_wording_that_denies_the_primary_supplier_is_replaced_by_the_evidence_backed_answer(wording):
    model = Capturing(parse("PART_TO_SUPPLIER", part="AB-1000-XY"), wording)
    r = ask(service(part_repo(suppliers=SUPPLIERS), model), "Who is the primary supplier for AB-1000-XY?")
    assert r.answer.source == "template"  # the contradictory wording was discarded
    assert "Primary supplier: Alpha Supply (demo)." in r.answer.summary
    records = {x["name"]: x for x in model.seen if "name" in x}
    assert records["Alpha Supply (demo)"]["facts"]["Primary supplier"] == "Yes"  # the model was given the flag, not a stripped list
    assert records["Alpha Supply (demo)"]["facts"]["Lead time"] == "28 days" and records["Beta Supply (demo)"]["facts"]["Primary supplier"] == "No"


def test_q14_wording_that_states_the_primary_supplier_is_kept():
    model = Capturing(parse("PART_TO_SUPPLIER", part="AB-1000-XY"), "Alpha Supply (demo) is the primary supplier for AB-1000-XY.")
    r = ask(service(part_repo(suppliers=SUPPLIERS), model), "Who is the primary supplier for AB-1000-XY?")
    assert r.answer.source == "llm" and "Alpha Supply (demo) is the primary supplier" in r.answer.summary


def test_when_no_supplier_is_primary_saying_so_is_correct_and_the_template_says_it_too():
    none_primary = [{**s, "is_primary": False} for s in SUPPLIERS]
    model = Capturing(parse("PART_TO_SUPPLIER", part="AB-1000-XY"), "No supplier is marked as the primary supplier for AB-1000-XY.")
    r = ask(service(part_repo(suppliers=none_primary), model), "Who is the primary supplier for AB-1000-XY?")
    assert r.answer.source == "llm"  # a true negative is allowed
    assert "None of them is marked as the primary supplier" in ask(service(part_repo(suppliers=none_primary), FakeLLM()), "Who is the primary supplier for AB-1000-XY?").answer.summary


@pytest.mark.parametrize("wording", QUANTITY_DENIALS)
def test_q27_wording_that_denies_quantities_is_replaced_by_the_evidence_backed_answer(wording):
    model = Capturing(parse("PART_TO_INVENTORY", part="AB-1000-XY"), wording)
    r = ask(service(part_repo(warehouses=WAREHOUSES, dealers=DEALERS), model), "How many units of AB-1000-XY are in stock?")
    assert r.answer.source == "template" and "68 units recorded across 3 warehouses" in r.answer.summary
    units = {x["name"]: x["facts"]["Units recorded"] for x in model.seen if x.get("kind") == "warehouse"}
    assert units == {"North Depot": "48", "South Depot": "20", "East Depot": "0"}  # every quantity reached the wording step


def test_q27_wording_that_reports_the_quantity_is_kept():
    model = Capturing(parse("PART_TO_INVENTORY", part="AB-1000-XY"), "AB-1000-XY has 68 units recorded across 3 warehouses.")
    r = ask(service(part_repo(warehouses=WAREHOUSES, dealers=DEALERS), model), "How many units of AB-1000-XY are in stock?")
    assert r.answer.source == "llm" and "68 units" in r.answer.summary


def test_wording_that_says_there_are_no_listed_entities_is_rejected():
    model = Capturing(parse("PART_TO_SUPPLIER", part="AB-1000-XY"), "No suppliers are connected to AB-1000-XY.")
    r = ask(service(part_repo(suppliers=SUPPLIERS), model), "Which suppliers does AB-1000-XY have?")
    assert r.answer.source == "template" and "2 suppliers are connected" in r.answer.summary


def test_the_structured_evidence_object_keeps_every_fact_and_the_totals():
    out = Outcome("s", [ResultItem(kind="supplier", key="S", title="Alpha", subtitle="A-town", relationship="SUPPLIED_BY", data_class="SYNTHETIC_DEMO",
                                   facts=[Fact(label="Primary supplier", value="Yes"), Fact(label="Lead time", value=None)])], total=7)
    head, rec = grounding_records(out)
    assert head["total"] == 7 and head["shown"] == 1
    assert rec["facts"] == {"Primary supplier": "Yes"} and rec["data_class"] == "SYNTHETIC_DEMO" and rec["relationship"] == "SUPPLIED_BY"  # a missing value is left out, never zero
    assert len(grounding_records(Outcome("s", [ResultItem(kind="part", key=str(i), title=f"P{i}") for i in range(40)], total=40))) == 12  # summary + 11, within the wording cap


def test_contradiction_check_only_fires_when_the_result_holds_the_value():
    none_result = Outcome("s", [])
    assert contradicts("The evidence does not contain specific unit counts.", none_result) is None  # nothing to contradict
    with_units = Outcome("s", [ResultItem(kind="warehouse", key="W", title="W", facts=[Fact(label="Units recorded", value="5")])])
    assert contradicts("No quantity information is available.", with_units) == "denies units recorded"
    assert contradicts("5 units are recorded.", with_units) is None


# ── 6. provenance wording: demo compliance never reads as real certification ───────────────────────────────────
DEMO_COMPLIANCE = [{"compliance_id": "C-1", "requirement": "Hydraulic components (demo)", "standard": "ISO 4413 (demo)", "certification": "CERT-1", "certificate_status": "VALID_DEMO",
                    "valid_until": None, "covers": [], "data_status": "SYNTHETIC_DEMO"}]


def test_synthetic_compliance_is_stated_as_not_establishing_certification():
    r = ask(service(part_repo(compliance=DEMO_COMPLIANCE), FakeLLM()), "Is AB-1000-XY certified?")
    assert "SYNTHETIC_DEMO" in r.answer.summary and "does not establish real-world certification" in r.answer.summary
    assert not r.answer.summary.lower().startswith("yes") and r.results[0].data_class == "SYNTHETIC_DEMO"


@pytest.mark.parametrize("wording", ["Yes, AB-1000-XY is certified under ISO 4413.", "AB-1000-XY holds a valid certificate."])
def test_wording_that_presents_synthetic_compliance_as_certification_is_rejected(wording):
    r = ask(service(part_repo(compliance=DEMO_COMPLIANCE), Capturing(parse("PART_TO_COMPLIANCE", part="AB-1000-XY"), wording)), "Is AB-1000-XY certified?")
    assert r.answer.source == "template" and "does not establish real-world certification" in r.answer.summary


def test_wording_that_keeps_the_demo_qualifier_on_certification_is_allowed():
    wording = "AB-1000-XY has a compliance record, but it is synthetic demo data and does not establish certification."
    r = ask(service(part_repo(compliance=DEMO_COMPLIANCE), Capturing(parse("PART_TO_COMPLIANCE", part="AB-1000-XY"), wording)), "Is AB-1000-XY certified?")
    assert r.answer.source == "llm"


def test_no_compliance_record_is_not_established_never_a_flat_no():
    r = ask(service(part_repo(compliance=[]), FakeLLM()), "Is AB-1000-XY certified?")
    assert "not established in the current graph" in r.answer.summary and r.results == []


# ── 3/4. one result type per intent; intermediate nodes never leak ───────────────────────────────────────────
def test_every_intent_declares_its_result_kinds_and_a_short_hint():
    for intent in answerable_intents():
        assert RESULT_KINDS[intent] and set(RESULT_KINDS[intent]) <= KINDS, intent
        assert HINTS[intent] and len(HINTS[intent].split()) <= 14, intent
    assert RESULT_KINDS[Intent.UNSUPPORTED] == () and set(RESULT_KINDS) == set(REGISTRY)
    assert RESULT_KINDS[Intent.PART_TO_MACHINE] == ("machine",) and RESULT_KINDS[Intent.PART_TO_WAREHOUSE] == ("warehouse",)
    assert RESULT_KINDS[Intent.PART_TO_SUPPLIER] == ("supplier",) and RESULT_KINDS[Intent.PART_TO_DEALER] == ("dealer",)
    assert RESULT_KINDS[Intent.PART_TO_PART] == ("part",) and RESULT_KINDS[Intent.PART_TO_ORDERS] == ("order",)
    assert RESULT_KINDS[Intent.PART_TO_SERVICE_PLAN] == ("service_plan",) and RESULT_KINDS[Intent.PART_TO_COMPLIANCE] == ("compliance",)
    assert RESULT_KINDS[Intent.PART_TO_ASSEMBLY] == ("assembly",) and RESULT_KINDS[Intent.WAREHOUSE_STOCK] == ("part",)


def test_the_contract_removes_intermediate_nodes_and_says_so(caplog):
    out = Outcome("s", [ResultItem(kind="warehouse", key="W", title="W"), ResultItem(kind="dealer", key="D", title="D"), ResultItem(kind="supplier", key="S", title="S")], total=3)
    with caplog.at_level(logging.WARNING):
        assert enforce_result_kinds(Intent.PART_TO_WAREHOUSE, out) == 2
    assert [r.kind for r in out.results] == ["warehouse"] and out.total == 1 and "PART_TO_WAREHOUSE" in caplog.text
    clean = Outcome("s", [ResultItem(kind="machine", key="M", title="M")], total=1)
    assert enforce_result_kinds(Intent.PART_TO_MACHINE, clean) == 0 and len(clean.results) == 1


def test_a_handler_that_over_reaches_cannot_leak_into_the_answer():
    """Even if a query returned dealers and suppliers for a warehouses-only intent, the service returns only warehouses."""
    from app.intelligence import handlers

    leaky = handlers.HANDLERS[Intent.PART_TO_WAREHOUSE]

    def over_reach(c):
        out = leaky(c)
        out.results += [ResultItem(kind="dealer", key="D", title="Dealer One (demo)"), ResultItem(kind="supplier", key="S", title="Alpha Supply (demo)")]
        return out

    handlers.HANDLERS[Intent.PART_TO_WAREHOUSE] = over_reach
    try:
        r = ask(service(part_repo(warehouses=WAREHOUSES), FakeLLM(parse=parse("PART_TO_WAREHOUSE", part="AB-1000-XY"))), "Which warehouses have AB-1000-XY?")
    finally:
        handlers.HANDLERS[Intent.PART_TO_WAREHOUSE] = leaky
    assert {i.kind for i in r.results} == {"warehouse"} and [i.title for i in r.results] == ["North Depot", "South Depot"]


def test_which_warehouses_have_a_part_returns_warehouses_only_and_treats_zero_as_zero_not_unknown():
    repo = part_repo(warehouses=WAREHOUSES + [{**WAREHOUSES[0], "warehouse_id": "W-4", "name": "West Depot", "available": None, "stock_status": None}], dealers=DEALERS, suppliers=SUPPLIERS)
    r = ask(service(repo, FakeLLM(parse=parse("PART_TO_WAREHOUSE", part="AB-1000-XY"))), "Which warehouses have AB-1000-XY?")
    assert [i.title for i in r.results] == ["North Depot", "South Depot", "West Depot"]  # East is recorded at zero: not a holder. West has no quantity: unknown, kept
    assert {i.kind for i in r.results} == {"warehouse"} and {e.target_kind for e in r.evidence} == {"WAREHOUSE"}
    assert "1 other warehouse is recorded with no units available" in r.answer.summary
    west = next(i for i in r.results if i.title == "West Depot")
    assert [f.value for f in west.facts if f.label == "Units recorded"] == [None]  # shown as not available, not 0


def test_where_is_a_part_available_returns_warehouses_and_dealers_but_not_suppliers():
    r = ask(service(part_repo(warehouses=WAREHOUSES, dealers=DEALERS, suppliers=SUPPLIERS), FakeLLM(parse=parse("PART_TO_LOCATION", part="AB-1000-XY"))), "Where is AB-1000-XY available?")
    assert {i.kind for i in r.results} == {"warehouse", "dealer"} and "Alpha Supply (demo)" not in [i.title for i in r.results]


# ── 1. warehouse-anchored questions (unit level) ─────────────────────────────────────────────────────────────
WH_ROW = row("WAREHOUSE", "W-4", "Regional Centre Zwolle (demo)", tier=2, detail="Zwolle")
STOCK = {"recorded": 5, "in_stock": 3, "out_of_stock": 2, "not_stated": 0,
         "rows": [{"part_id": f"P-{n}", "part_number": f"PN-{n}", "name": f"Part {n}", "category": "Filtration", "available": 10 - n, "stock_status": "IN_STOCK", "data_status": "SYNTHETIC_DEMO"} for n in range(3)]}


def test_a_named_warehouse_returns_its_own_parts_only():
    repo = FakeRepo({"zwolle": [WH_ROW]}, warehouse_stock=STOCK, subject=lambda kind, id: {"label": WH_ROW["label"], "name": WH_ROW["label"], "data_status": "SYNTHETIC_DEMO", "city": "Zwolle", "country": "NL", "warehouse_type": "REGIONAL_DEPOT", "operating_status": "OPERATIONAL"})
    r = ask(service(repo, FakeLLM(parse=parse("WAREHOUSE_STOCK", warehouse="Zwolle"))), "What is in stock at the Zwolle warehouse?")
    assert r.intent == "WAREHOUSE_STOCK" and [e.kind for e in r.entities] == ["WAREHOUSE"]
    assert {i.kind for i in r.results} == {"part"} and [i.title for i in r.results] == ["PN-0", "PN-1", "PN-2"] and r.total == 3
    assert "3 parts in stock out of 5 with a stock record; 2 recorded as out of stock" in r.answer.summary
    assert r.subject is not None and r.subject.kind == "WAREHOUSE" and ("Location (stated)", "Zwolle, NL") in [(f.label, f.value) for f in r.subject.facts]
    assert all(e.target == WH_ROW["label"] and e.relationship == "AVAILABLE_AT" for e in r.evidence)


def test_a_warehouse_question_never_uses_the_catalogue_wide_low_stock_list():
    spy = Spy(FakeRepo({"zwolle": [WH_ROW]}, warehouse_stock=STOCK))
    r = ask(service(spy, FakeLLM(parse=parse("WAREHOUSE_STOCK", warehouse="Zwolle"))), "Which parts are available at Zwolle?")
    assert "low_stock_parts" not in spy.calls and "warehouse_stock" in spy.calls and r.intent == "WAREHOUSE_STOCK"


def test_an_unnamed_or_unknown_warehouse_asks_instead_of_guessing():
    repo = FakeRepo({"zwolle": [WH_ROW]}, warehouse_stock=STOCK)
    none = ask(service(repo, FakeLLM(parse=LLMParse("WAREHOUSE_STOCK"))), "Show the inventory at this warehouse")
    assert none.clarification is not None and none.results == [] and "Which warehouse" in none.clarification.question
    unknown = ask(service(repo, FakeLLM(parse=parse("WAREHOUSE_STOCK", warehouse="Atlantis"))), "What is in stock at Atlantis?")
    assert unknown.results == [] and unknown.clarification is not None and unknown.clarification.code == "WAREHOUSE_NOT_FOUND"


def test_two_warehouses_match_so_the_user_chooses():
    two = [row("WAREHOUSE", "W-1", "North Depot Lingen (demo)", tier=2), row("WAREHOUSE", "W-2", "South Depot Lingen (demo)", tier=2)]
    r = ask(service(FakeRepo({"lingen": two}, warehouse_stock=STOCK), FakeLLM(parse=parse("WAREHOUSE_STOCK", warehouse="Lingen"))), "What is in stock at Lingen?")
    assert r.results == [] and r.clarification is not None and r.clarification.code == "AMBIGUOUS" and len(r.clarification.candidates) == 2


def test_a_selected_warehouse_is_accepted_from_a_clarification():
    two = [row("WAREHOUSE", "W-1", "North Depot Lingen (demo)", tier=0), row("WAREHOUSE", "W-2", "South Depot Lingen (demo)", tier=2)]
    repo = FakeRepo({"lingen": two, "north depot lingen (demo)": [two[0]]}, warehouse_stock=STOCK)
    r = ask(service(repo, FakeLLM(parse=parse("WAREHOUSE_STOCK", warehouse="Lingen"))), "What is in stock at Lingen?", selected=[{"kind": "WAREHOUSE", "key": "North Depot Lingen (demo)"}])
    assert r.clarification is None and r.intent == "WAREHOUSE_STOCK" and r.total == 3


# ── 5. unsupported entity types and scope: no graph access, no invented answer ───────────────────────────────
@pytest.mark.parametrize("llm_parse", [
    LLMParse("UNSUPPORTED", in_scope=False),                       # out of scope
    LLMParse("UNSUPPORTED", in_scope=True),                        # in the domain, but no intent can answer it (e.g. which parts must meet a standard)
    LLMParse("TABLE_DROP", in_scope=True),                         # an intent the registry does not know
])
def test_out_of_scope_and_unsupported_questions_never_touch_the_graph(llm_parse):
    spy = Spy(FakeRepo({}))
    r = ask(service(spy, FakeLLM(parse=llm_parse)), "Which parts must meet ISO 4413?")
    assert spy.calls == [] and r.results == [] and r.evidence == [] and r.intent == "UNSUPPORTED"


def test_a_shipment_id_does_not_resolve_so_nothing_is_invented():
    r = ask(service(FakeRepo({}), FakeLLM(parse=parse("ORDER_STATUS", order="SHP-0010"))), "Where is shipment SHP-0010?")
    assert r.results == [] and r.clarification is not None and r.clarification.code == "ORDER_NOT_FOUND"


# ── the same contracts against the live graph (read-only) ──────────────────────────────────────────────────
@needs_graph
def test_graph_warehouse_question_returns_that_warehouses_parts_only():
    r = graph_ask(parse("WAREHOUSE_STOCK", warehouse="Zwolle"), "What is in stock at the Zwolle warehouse?")
    assert r["intent"] == "WAREHOUSE_STOCK" and r["clarification"] is None
    assert [(e["kind"], e["key"]) for e in r["entities"]] == [("WAREHOUSE", "Regional Distribution Centre Zwolle (demo)")]
    assert r["results"] and {i["kind"] for i in r["results"]} == {"part"}
    assert {e["target"] for e in r["evidence"]} == {"Regional Distribution Centre Zwolle (demo)"} and {e["relationship"] for e in r["evidence"]} == {"AVAILABLE_AT"}
    names = " ".join(i["title"] + (i["subtitle"] or "") for i in r["results"])
    assert not any(w in names for w in ("Depot", "Warehouse", "Dealer", "(demo)"))  # no other warehouse, dealer or supplier appears as a result
    for i in r["results"]:
        units = next(f["value"] for f in i["facts"] if f["label"] == "Units recorded")
        assert units is not None and int(units) > 0  # "in stock" means a recorded quantity above zero
    assert r["subject"]["kind"] == "WAREHOUSE" and any(f["value"] == "Zwolle, NL" for f in r["subject"]["facts"])


@needs_graph
def test_graph_warehouse_totals_match_a_direct_count_and_other_warehouses_differ():
    from app.graph.client import GraphClient

    graph = GraphClient(get_settings())
    try:
        direct = {r["id"]: (r["recorded"], r["in_stock"]) for r in graph.read(
            "MATCH (p:Part)-[r:AVAILABLE_AT]->(w:Warehouse) RETURN w.warehouse_id AS id, count(r) AS recorded, sum(CASE WHEN r.available > 0 THEN 1 ELSE 0 END) AS in_stock")}
    finally:
        graph.close()
    zwolle = graph_ask(parse("WAREHOUSE_STOCK", warehouse="WH-004"), limit=40)
    assen = graph_ask(parse("WAREHOUSE_STOCK", warehouse="WH-001"), limit=40)
    assert zwolle["total"] == direct["WH-004"][1] and assen["total"] == direct["WH-001"][1] and zwolle["total"] != assen["total"]  # each warehouse reports its own stock
    assert len(zwolle["results"]) == 40 and zwolle["total"] > 40  # a page of the warehouse's own parts, with the true total
    assert f"{zwolle['total']} parts in stock out of {direct['WH-004'][0]} with a stock record" in zwolle["answer"]["summary"] and "recorded as out of stock" in zwolle["answer"]["summary"]


@needs_graph
def test_graph_warehouse_is_found_by_id_and_never_by_geography():
    by_id = graph_ask(parse("WAREHOUSE_STOCK", warehouse="WH-004"))
    assert by_id["entities"][0]["key"] == "Regional Distribution Centre Zwolle (demo)"
    geography = graph_ask(parse("WAREHOUSE_STOCK", warehouse="Enschede"))  # a dealer city: no warehouse is named that, so none is chosen
    assert geography["results"] == [] and geography["clarification"]["code"] == "WAREHOUSE_NOT_FOUND"


@needs_graph
def test_graph_which_warehouses_have_a_part_returns_only_warehouses():
    r = graph_ask(parse("PART_TO_WAREHOUSE", part="NVM-1030-HY"), "Which warehouses have NVM-1030-HY?")
    assert r["results"] and {i["kind"] for i in r["results"]} == {"warehouse"} and {e["target_kind"] for e in r["evidence"]} == {"WAREHOUSE"}
    assert r["subject"]["label"] == "NVM-1030-HY"
    assert not any("(demo)" in i["title"] and ("Machinery" in i["title"] or "Heavy" in i["title"]) for i in r["results"])  # no dealer names


@needs_graph
def test_graph_q14_primary_supplier_wording_that_denies_it_is_never_returned():
    r = graph_ask(parse("PART_TO_SUPPLIER", part="NVM-1020-FL"), "Who is the primary supplier for NVM-1020-FL?", reply="The evidence does not identify a primary supplier for NVM-1020-FL.")
    assert r["answer"]["source"] == "template" and "Primary supplier: Hanselmann Kuehlsysteme (demo)" in r["answer"]["summary"]
    flagged = [x for x in r["_model_saw"] if x.get("facts", {}).get("Primary supplier") == "Yes"]
    assert [x["name"] for x in flagged] == ["Hanselmann Kuehlsysteme (demo)"]  # the real flag reached the wording step


@needs_graph
def test_graph_q27_quantity_wording_that_denies_it_is_never_returned():
    r = graph_ask(parse("PART_TO_INVENTORY", part="NVM-1020-FL"), "How many units of NVM-1020-FL are in stock?", reply="The evidence does not contain specific unit counts for NVM-1020-FL.")
    assert r["answer"]["source"] == "template" and "172 units recorded across 8 warehouses" in r["answer"]["summary"]
    seen = {x["name"]: x["facts"].get("Units recorded") for x in r["_model_saw"] if x.get("kind") == "warehouse"}
    assert len(seen) == 8 and sum(int(v) for v in seen.values()) == 172  # every warehouse quantity (the original 4 depots plus the European foundation depots) reached the wording step
    assert {"20", "48", "5", "8"} <= set(seen.values())


@needs_graph
def test_graph_demo_compliance_is_worded_as_not_establishing_certification():
    r = graph_ask(parse("PART_TO_COMPLIANCE", part="NVM-1010-HY"), "Is NVM-1010-HY certified?", reply="Yes, NVM-1010-HY is certified.")
    assert r["answer"]["source"] == "template" and "SYNTHETIC_DEMO" in r["answer"]["summary"] and "does not establish real-world certification" in r["answer"]["summary"]


@needs_graph
def test_graph_alternatives_and_replacements_show_only_stored_links():
    r = graph_ask(parse("PART_TO_PART", part="NVM-1010-FL"), "What can replace NVM-1010-FL?")
    assert {i["kind"] for i in r["results"]} == {"part"} and any("does not establish alternatives" in w for w in r["warnings"])
    assert "interchangeable" not in r["answer"]["summary"].replace("not interchangeable", "").replace("interchangeable.", "") or "None of these links states" in r["answer"]["summary"]


@needs_graph
@pytest.mark.parametrize("intent, kind, entities, expected_subject", [
    ("PART_TO_SUPPLIER", "PART", {"part": "NVM-1010-HY"}, "NVM-1010-HY"),
    ("MACHINE_TO_PART", "MACHINE", {"machine": "NV-4500"}, "NV-4500"),
    ("SUPPLIER_GRAPH", "SUPPLIER", {"supplier": "Veldstra Hydraulics"}, "Veldstra Hydraulics (demo)"),
    ("DEALER_GRAPH", "DEALER", {"dealer": "Brabant Heavy Parts"}, "Brabant Heavy Parts (demo)"),
    ("ASSEMBLY_TO_PART", "ASSEMBLY", {"assembly": "Brake caliper assembly"}, "Brake caliper assembly"),
    ("ORDER_STATUS", "ORDER", {"order": "ORD-0013"}, "ORD-0013"),
    ("WAREHOUSE_STOCK", "WAREHOUSE", {"warehouse": "Zwolle"}, "Regional Distribution Centre Zwolle (demo)"),
])
def test_graph_every_anchored_entity_type_carries_its_identity(intent, kind, entities, expected_subject):
    s = graph_ask(parse(intent, **entities))["subject"]
    assert (s["kind"], s["label"]) == (kind, expected_subject) and s["data_class"] != "UNKNOWN"
    if kind in ("PART", "MACHINE", "ASSEMBLY", "WAREHOUSE"):
        assert s["facts"]  # type / category / status where the graph states one


# every intent, one real question each: the result kinds must stay inside the contract, and the contract must never have to remove anything
SWEEP = {
    "PART_SEARCH": {"part": "hydraulic hose"}, "PART_TO_MACHINE": {"part": "NVM-1010-AT"}, "MACHINE_TO_PART": {"machine": "NV-4500"}, "PART_TO_CATEGORY": {"part": "NVM-1030-BR"},
    "PART_TO_ASSEMBLY": {"part": "NVM-1010-HY"}, "ASSEMBLY_TO_PART": {"assembly": "Brake caliper assembly"}, "PART_TO_PART": {"part": "NVM-1010-FL"},
    "PART_TO_SUPPLIER": {"part": "NVM-1010-HY"}, "PART_TO_DEALER": {"part": "NVM-1010-FL"}, "PART_TO_LOCATION": {"part": "NVM-1010-HY"}, "PART_TO_WAREHOUSE": {"part": "NVM-1030-HY"},
    "PART_TO_INVENTORY": {"part": "NVM-1020-FL"}, "WAREHOUSE_STOCK": {"warehouse": "Zwolle"}, "PART_TO_COMPLIANCE": {"part": "NVM-1010-BR"}, "PART_PROVENANCE": {"part": "NVM-1010-HY"},
    "PART_GRAPH": {"part": "NVM-1010-AT"}, "MACHINE_GRAPH": {"machine": "NV-6000"}, "MACHINE_LIST": {}, "SHARED_PARTS": {}, "PART_TO_SERVICE_PLAN": {"part": "NVM-1010-FL"},
    "PART_TO_ORDERS": {"part": "NVM-1010-HY"}, "LOW_STOCK_PARTS": {}, "SUPPLIER_GRAPH": {"supplier": "Veldstra Hydraulics"}, "DEALER_GRAPH": {"dealer": "Brabant Heavy Parts"},
    "DATA_QUALITY": {}, "ENTITY_PATH": {"part": "NVM-1010-AT", "machine": "NV-6000"}, "ORDER_STATUS": {"order": "ORD-0013"},
}


@needs_graph
def test_graph_sweep_covers_every_answerable_intent():
    assert set(SWEEP) | {"GEO_LOCATION"} == {i.value for i in answerable_intents()}


@needs_graph
@pytest.mark.parametrize("intent", sorted(SWEEP))
def test_graph_every_intent_returns_only_its_declared_result_kinds(intent, caplog):
    with caplog.at_level(logging.WARNING, logger="app.intelligence.contract"):
        r = graph_ask(parse(intent, **SWEEP[intent]), f"sweep {intent}")
    assert r["clarification"] is None, r["answer"]["summary"]
    allowed = set(RESULT_KINDS[Intent(intent)])
    assert r["results"] and {i["kind"] for i in r["results"]} <= allowed, (intent, {i["kind"] for i in r["results"]})
    assert "returned" not in caplog.text, "a handler over-reached and the contract had to remove results"


@needs_graph
def test_graph_geo_question_returns_only_the_requested_kind():
    r = graph_ask(LLMParse("GEO_LOCATION", filters={"place": "Zwolle", "place_kind": "DEALER", "proximity": "in"}), "What dealers are in Zwolle?")
    assert r["results"] and {i["kind"] for i in r["results"]} == {"dealer"}


@needs_graph
def test_graph_out_of_scope_question_never_reaches_neo4j():
    class NoGraph:
        def __getattr__(self, name):
            raise AssertionError(f"the graph was used: {name}")

    app.dependency_overrides[get_graph] = lambda: NoGraph()
    app.dependency_overrides[get_llm] = lambda: Scripted(LLMParse("UNSUPPORTED", in_scope=False))
    try:
        with TestClient(app) as c:
            r = c.post(f"{V1}/query", json={"question": "What is the capital of France?"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200 and r.json()["scope"] == "OUT_OF_SCOPE" and r.json()["results"] == []
    assert QueryRequest(question="ok").limit == 12
