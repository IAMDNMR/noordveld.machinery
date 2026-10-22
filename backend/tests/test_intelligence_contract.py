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














def test_the_structured_evidence_object_keeps_every_fact_and_the_totals():
    out = Outcome("s", [ResultItem(kind="supplier", key="S", title="Alpha", subtitle="A-town", relationship="SUPPLIED_BY", data_class="SYNTHETIC_DEMO",
                                   facts=[Fact(label="Primary supplier", value="Yes"), Fact(label="Lead time", value=None)])], total=7)
    head, rec = grounding_records(out)
    assert head["total"] == 7 and head["shown"] == 1
    assert rec["facts"] == {"Primary supplier": "Yes"} and rec["data_class"] == "SYNTHETIC_DEMO" and rec["relationship"] == "SUPPLIED_BY"  # a missing value is left out, never zero
    assert len(grounding_records(Outcome("s", [ResultItem(kind="part", key=str(i), title=f"P{i}") for i in range(40)], total=40))) == 12  # summary + 11, within the wording cap




# ── 6. provenance wording: demo compliance never reads as real certification ───────────────────────────────────
DEMO_COMPLIANCE = [{"compliance_id": "C-1", "requirement": "Hydraulic components (demo)", "standard": "ISO 4413 (demo)", "certification": "CERT-1", "certificate_status": "VALID_DEMO",
                    "valid_until": None, "covers": [], "data_status": "SYNTHETIC_DEMO"}]








def test_no_compliance_record_is_not_established_never_a_flat_no():
    r = ask(service(part_repo(compliance=[]), FakeLLM()), "Is AB-1000-XY certified?")
    assert "not established in the current graph" in r.answer.summary and r.results == []


# ── 3/4. one result type per intent; intermediate nodes never leak ───────────────────────────────────────────




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










# ── 5. unsupported entity types and scope: no graph access, no invented answer ───────────────────────────────




# ── the same contracts against the live graph (read-only) ──────────────────────────────────────────────────


















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








