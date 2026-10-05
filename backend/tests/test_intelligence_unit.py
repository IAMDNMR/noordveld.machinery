"""Parts Intelligence without Neo4j or a live model: registry, Cypher safety, grounding, Gemini-first routing and data-truth behaviour.

`FakeLLM` stands in for Gemini. Unless a test hands it an explicit parse, it answers like a model would (tests/support/keyword_model.py is a
test double; the application itself contains no keyword routing).
"""
from __future__ import annotations

import re
from typing import Any

import httpx
import json

import pytest

from app.core.config import Settings
from app.graph.queries import intelligence as queries
from app.intelligence.identifiers import identifiers
from tests.support.keyword_model import model_parse
from app.intelligence.grounding import is_grounded
from app.intelligence.models import Intent
from app.intelligence.registry import REGISTRY, answerable_intents
from app.intelligence.service import IntelligenceService
from app.llm import LLMError, LLMParse, LLMUnavailable, create_llm
from app.llm.base import LLMInvalidResponse
from app.llm.gemini import GeminiClient
from app.llm.structured import RateLimiter
from app.schemas.intelligence import QueryRequest, SelectedEntity


# ── registry and Cypher safety ────────────────────────────────────────────────────────────────────
def test_every_intent_is_registered_with_a_spec():
    assert set(REGISTRY) == set(Intent)
    for spec in REGISTRY.values():
        assert spec.description and spec.result_type
        if spec.intent is not Intent.UNSUPPORTED:
            assert spec.queries and spec.path and spec.provenance


def test_intent_catalogue_matches_the_brief():
    assert {i.value for i in answerable_intents()} >= {
        "PART_SEARCH", "PART_TO_MACHINE", "MACHINE_TO_PART", "PART_TO_CATEGORY", "PART_TO_ASSEMBLY", "ASSEMBLY_TO_PART", "PART_TO_PART", "PART_TO_SUPPLIER", "PART_TO_DEALER",
        "PART_TO_LOCATION", "PART_TO_INVENTORY", "PART_TO_COMPLIANCE", "PART_PROVENANCE", "PART_GRAPH", "MACHINE_GRAPH", "SUPPLIER_GRAPH", "DEALER_GRAPH", "DATA_QUALITY",
    }


def _all_cypher() -> dict[str, str]:
    found = {n: v for n, v in vars(queries).items() if n.isupper() and isinstance(v, str)}
    found.update({f"{n}.{k}": t for n, v in vars(queries).items() if n.isupper() and isinstance(v, dict) for k, t in v.items()})  # e.g. SUBJECT per kind
    return found


def test_cypher_is_read_only():
    forbidden = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH)\b|apoc\.(create|merge|refactor)|dbms\.", re.I)
    for name, text in _all_cypher().items():
        assert not forbidden.search(text), f"{name} contains a write or admin operation"


def test_cypher_is_parameterised_and_bounded():
    for name, text in _all_cypher().items():
        assert not re.search(r"['\"]\s*\+\s*\$", text), f"{name} concatenates a parameter into a string"
        bounded = re.search(r"LIMIT|\[\.\.\d+\]|\[0\.\.\$limit\]|count\(|size\(", text)
        assert bounded, f"{name} is unbounded"


# ── exact identifiers (entity assistance only: they never choose an intent) ──────────────────────
def test_identifiers_are_read_exactly_not_trailing_words():
    # a trailing word may be captured with the identifier; the resolver trims trailing words until it matches
    assert any(m.startswith("NVM-1010-HY") for m in identifiers("Which machines use NVM-1010-HY fit"))
    assert any(m.lower() == "nvm 1050 cl" for m in identifiers("suppliers of nvm 1050 cl"))
    assert "NVM1050CL" in identifiers("Which machines use NVM1050CL?")
    assert any(m.replace(" ", "-").lower() == "nvm-1010-hy" for m in identifiers("show NVM 1010 HY"))
    assert identifiers("what is the weather in Paris") == ()


# ── grounding (hallucination prevention) ──────────────────────────────────────────────────────────
EVIDENCE: list[dict[str, Any]] = [{"entity": "P-1", "relationship": "FITS", "target": "M-2", "data_class": "SOURCE_DERIVED"}]


def test_grounding_rejects_reciting_every_item():
    many = [{"entity": f"P-{i}", "relationship": "FITS", "target": "M-1", "data_class": "SOURCE_DERIVED"} for i in range(8)]
    recital = "P-0, P-1, P-2, P-3, P-4, P-5 and P-6 fit M-1."
    assert not is_grounded(recital, many, "M-1 is associated with 8 parts.", "q")


def test_grounding_accepts_a_faithful_summary():
    assert is_grounded("P-1 is associated with M-2.", EVIDENCE, "P-1 is associated with 1 machine: M-2.", "which machines use P-1")


@pytest.mark.parametrize("claim", [
    "P-1 is interchangeable with P-9.",          # invented identifier and interchangeability
    "P-1 fits M-2 and has 14 in stock.",          # invented number and stock claim
    "P-1 is a certified replacement for M-2.",    # replacement/certified not in evidence
    "P-1 has zero stock.",                       # unknown turned into zero
])
def test_grounding_rejects_invented_facts(claim):
    assert not is_grounded(claim, EVIDENCE, "P-1 is associated with 1 machine: M-2.", "q")


# ── optional Gemini provider (Groq is covered in test_llm_providers.py) ─────────────────────────────────────────────────────────────────────────────────
def _gemini(handler) -> GeminiClient:
    settings = Settings(gemini_api_key="test-key-123", gemini_model="m-test")
    return GeminiClient(settings, httpx.Client(transport=httpx.MockTransport(handler)))


def _reply(text: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


INTENTS = {"PART_TO_MACHINE": "machines a part fits"}


def test_gemini_requires_a_key_and_hides_it():
    assert create_llm(Settings()) is None
    with pytest.raises(LLMUnavailable):
        GeminiClient(Settings())
    assert "test-key-123" not in repr(Settings(gemini_api_key="test-key-123"))


def test_gemini_sends_key_in_header_not_url_and_uses_configured_model():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), key=request.headers.get("x-goog-api-key"))
        return _reply('{"in_scope": true, "domain": "parts_intelligence", "intent": "PART_TO_MACHINE", "entities": {"part": "P-1", "machine": null}, "filters": {}, "requires_clarification": false}')

    parse = _gemini(handler).parse_question("which machines use P-1", INTENTS)
    assert "test-key-123" not in seen["url"] and seen["key"] == "test-key-123" and "m-test" in seen["url"]
    assert parse == LLMParse("PART_TO_MACHINE", ("P-1",), False, None, {}, {"part": "P-1"})


def test_gemini_returns_typed_entities_and_filters_and_nothing_executable():
    body = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body.update(json.loads(request.content))
        return _reply(json.dumps({"in_scope": True, "domain": "parts_intelligence", "intent": "MACHINE_LIST", "entities": {"machine": None, "cypher": "MATCH (n) DETACH DELETE n"}, "filters": {"location": "Assen", "query": "MATCH (n) RETURN n"},
                                  "requires_clarification": False, "cypher": "MATCH (n) DETACH DELETE n"}))

    parse = _gemini(handler).parse_question("show me the machines at Assen", {"MACHINE_LIST": "list machines", **INTENTS})
    assert parse.intent == "MACHINE_LIST" and parse.entities == {} and parse.filters["location"] == "Assen"
    assert "MATCH" not in repr(parse.entities) and not hasattr(parse, "cypher")  # only the declared fields survive; no query text is ever carried
    schema = body["generationConfig"]["responseSchema"]
    assert set(schema["properties"]) == {"in_scope", "intent", "entities", "need", "filters", "requires_clarification", "clarification_question"}  # no query (domain and confidence were dropped to save tokens; a reply that still carries them is read)
    assert "cypher" not in json.dumps(schema).lower() and "Do not generate" not in json.dumps(schema)
    assert "do not answer the question" in body["systemInstruction"]["parts"][0]["text"].lower() and "cypher" in body["systemInstruction"]["parts"][0]["text"].lower()


def test_gemini_scope_verdict_is_parsed_and_a_missing_verdict_is_invalid():
    out = _gemini(lambda r: _reply('{"in_scope": false, "domain": "out_of_scope", "intent": "UNSUPPORTED", "entities": {}, "filters": {}, "requires_clarification": false, "confidence": 0.99}'))
    parse = out.parse_question("What is the capital of France?", INTENTS)
    assert parse.in_scope is False and parse.intent == "UNSUPPORTED" and parse.confidence == 0.99
    contradictory = _gemini(lambda r: _reply('{"in_scope": true, "domain": "out_of_scope", "intent": "PART_TO_MACHINE", "entities": {}, "filters": {}, "requires_clarification": false}'))
    assert contradictory.parse_question("q", INTENTS).in_scope is False  # either signal saying "out of scope" wins
    with pytest.raises(LLMInvalidResponse):
        _gemini(lambda r: _reply('{"intent": "PART_TO_MACHINE", "entities": {}, "filters": {}, "requires_clarification": false}')).parse_question("q", INTENTS)


def test_gemini_invalid_and_unavailable_responses():
    with pytest.raises(LLMInvalidResponse):
        _gemini(lambda r: _reply("not json")).parse_question("q", INTENTS)
    with pytest.raises(LLMInvalidResponse):
        _gemini(lambda r: httpx.Response(200, json={"nothing": 1})).parse_question("q", INTENTS)
    with pytest.raises(LLMUnavailable):
        _gemini(lambda r: httpx.Response(429, json={})).parse_question("q", INTENTS)
    with pytest.raises(LLMUnavailable):
        _gemini(lambda r: (_ for _ in ()).throw(httpx.ConnectError("down"))).parse_question("q", INTENTS)


def test_rate_limiter_blocks_over_the_window():
    limiter = RateLimiter(2)
    assert [limiter.allow() for _ in range(3)] == [True, True, False]


# ── service behaviour with a fake graph ───────────────────────────────────────────────────────────
class FakeRepo:
    """Just enough graph for routing tests. `data` can omit a relationship to prove it is never invented."""

    def __init__(self, resolve: dict[str, list[dict]] | None = None, **data: Any) -> None:
        self._resolve, self.data = resolve or {}, data

    def resolve(self, mention: str) -> list[dict]:
        return self._resolve.get(mention.lower(), [])

    def __getattr__(self, name: str):
        if name in self.data:
            value = self.data[name]
            return value if callable(value) else (lambda *a, **k: value)
        return lambda *a, **k: []

    def category(self, part_id): return {}


def row(kind: str, id: str, label: str, tier: int = 0, detail: str | None = None) -> dict:
    return {"kind": kind, "id": id, "label": label, "detail": detail, "data_status": "SOURCE_DERIVED", "tier": tier}


class NoParts:
    def search(self, **kw): return 0, []
    def summaries(self, ids): return []


class FakeLLM:
    name = "fake"

    def __init__(self, parse: LLMParse | Exception | None = None, reply: str | Exception = "") -> None:
        self.parse, self.reply, self.calls = parse, reply, 0

    def parse_question(self, question, intents):
        self.calls += 1
        if self.parse is None:
            return model_parse(question)  # a model that understands the question
        if isinstance(self.parse, Exception):
            raise self.parse
        return self.parse

    def resolve_entities(self, question, intents): return ()

    def generate_grounded_response(self, question, intent, evidence, draft):
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def service(repo: FakeRepo, llm: Any = None) -> IntelligenceService:
    return IntelligenceService(repo, NoParts(), llm if llm is not None else FakeLLM())  # type: ignore[arg-type]


PART = row("PART", "PRT-1", "AB-1000-XY")
MACHINE = row("MACHINE", "MCH-1", "ZZ-1")


def ask(svc: IntelligenceService, question: str, **kw):
    return svc.query(QueryRequest(question=question, **kw))


FIT = [{"machine_id": "MCH-1", "model_code": "ZZ-1", "name": "Zed", "machine_type": "Loader", "family": "Z", "fitment_status": "CONFIRMED", "condition_note": None, "data_status": "SOURCE_DERIVED"}]


def test_every_question_goes_to_the_model_first_and_its_intent_is_what_runs():
    llm = FakeLLM(parse=LLMParse("PART_TO_MACHINE", ("AB-1000-XY",)))
    repo = FakeRepo({"ab-1000-xy": [PART]}, fitment=FIT)
    r = ask(service(repo, llm), "Which machines use AB-1000-XY?")
    assert (r.intent, r.understood_by, r.total) == ("PART_TO_MACHINE", "llm", 1) and llm.calls == 1
    assert r.evidence[0].relationship == "FITS" and r.provenance[0].data_class == "SOURCE_DERIVED"  # the answer is the graph's, not the model's


def test_the_model_decides_even_when_keywords_would_say_otherwise():
    # the keyword rules read "Which machines use ..." as fitment; the model says suppliers, and the model is what runs
    repo = FakeRepo({"ab-1000-xy": [PART]}, suppliers=[])
    r = ask(service(repo, FakeLLM(parse=LLMParse("PART_TO_SUPPLIER", ("AB-1000-XY",)))), "Which machines use AB-1000-XY?")
    assert r.intent == "PART_TO_SUPPLIER" and r.understood_by == "llm"


def test_model_entities_are_resolved_against_the_graph_not_trusted():
    repo = FakeRepo({"ab-1000-xy": [PART]}, suppliers=[])
    r = ask(service(repo, FakeLLM(parse=LLMParse("PART_TO_SUPPLIER", ("ZQ-0000-XX",)))), "who supplies that?")
    assert r.results == [] and r.clarification is not None  # an entity the graph does not hold is asked about, never invented


def test_no_model_means_a_clear_error_never_a_silent_keyword_router():
    repo = FakeRepo({"ab-1000-xy": [PART]}, fitment=FIT)
    for llm in (FakeLLM(parse=LLMUnavailable("rate limit")), FakeLLM(parse=LLMInvalidResponse("bad json"))):
        with pytest.raises(LLMError):
            ask(service(repo, llm), "Which machines use AB-1000-XY?")
    with pytest.raises(LLMUnavailable):
        ask(IntelligenceService(repo, NoParts(), None), "Which machines use AB-1000-XY?")  # type: ignore[arg-type]


def test_a_model_that_finds_nothing_is_not_second_guessed_by_keywords():
    repo = FakeRepo({"ab-1000-xy": [PART]}, fitment=FIT)
    r = ask(service(repo, FakeLLM(parse=LLMParse("UNSUPPORTED"))), "Which machines use AB-1000-XY?")
    assert r.intent == "UNSUPPORTED" and r.results == [] and r.understood_by == "llm"


def test_the_same_question_is_understood_once():
    llm = FakeLLM(parse=LLMParse("PART_TO_MACHINE", ("AB-1000-XY",)))
    svc = service(FakeRepo({"ab-1000-xy": [PART]}, fitment=FIT), llm)
    ask(svc, "Which machines use AB-1000-XY?")
    ask(svc, "which machines use  ab-1000-xy?")
    assert llm.calls == 1


def test_unsupported_question_does_not_hallucinate():
    r = ask(service(FakeRepo()), "what is the weather in Paris")
    assert r.intent == "UNSUPPORTED" and r.scope == "OUT_OF_SCOPE" and r.results == [] and "Parts Intelligence questions" in r.answer.summary


def test_missing_entity_asks_instead_of_guessing():
    r = ask(service(FakeRepo()), "Which machines use ZQ-0000-XX?")
    assert r.clarification and r.results == [] and "Which part" in r.answer.summary


def test_ambiguous_entity_returns_candidates_not_a_choice():
    repo = FakeRepo({"loader": [row("MACHINE", "A", "ZZ-1", 2), row("MACHINE", "B", "ZZ-2", 2)]})
    r = ask(service(repo), "which parts fit the loader")
    assert r.clarification and {c.label for c in r.clarification.candidates} == {"ZZ-1", "ZZ-2"} and r.results == []


def test_user_selection_resolves_the_ambiguity():
    repo = FakeRepo({"loader": [row("MACHINE", "A", "ZZ-1", 2), row("MACHINE", "B", "ZZ-2", 2)], "zz-2": [row("MACHINE", "B", "ZZ-2", 0)]},
                    machine_parts=(0, []))
    r = ask(service(repo), "which parts fit the loader", selected=[SelectedEntity(kind="MACHINE", key="ZZ-2")])
    assert r.clarification is None and r.entities[0].label == "ZZ-2" and r.understood_by == "selection"


def test_llm_unsupported_or_unknown_intent_is_rejected_without_a_query():
    for parse in (LLMParse("DROP_EVERYTHING", ("x",)), LLMParse("UNSUPPORTED")):
        r = ask(service(FakeRepo(), FakeLLM(parse)), "tell me something vague about stuff")
        assert r.intent == "UNSUPPORTED" and r.results == []


def test_llm_intent_is_validated_then_executed_by_a_fixed_handler():
    repo = FakeRepo({"ab-1000-xy": [PART]}, suppliers=[])
    r = ask(service(repo, FakeLLM(LLMParse("PART_TO_SUPPLIER", ("AB-1000-XY",)))), "who provides that gizmo AB-1000-XY nowadays")
    assert r.intent == "PART_TO_SUPPLIER"


def test_model_summary_is_discarded_when_it_invents_facts():
    repo = FakeRepo({"ab-1000-xy": [PART]}, fitment=[{"machine_id": "MCH-1", "model_code": "ZZ-1", "name": "Zed", "machine_type": None, "family": None, "fitment_status": "CONFIRMED",
                                                      "condition_note": None, "data_status": "SOURCE_DERIVED"}])
    bad = ask(service(repo, FakeLLM(reply="AB-1000-XY is interchangeable with AB-2000-XY and has 40 in stock.")), "Which machines use AB-1000-XY?")
    good = ask(service(repo, FakeLLM(reply="AB-1000-XY is associated with ZZ-1 in the graph.")), "Which machines use AB-1000-XY?")
    assert bad.answer.source == "template" and "interchangeable" not in bad.answer.summary
    assert good.answer.source == "llm"


def test_model_failure_on_wording_keeps_the_deterministic_answer():
    repo = FakeRepo({"ab-1000-xy": [PART]}, fitment=[])
    r = ask(service(repo, FakeLLM(reply=LLMUnavailable("rate limit"))), "Which machines use AB-1000-XY?")
    assert r.answer.source == "template"


# ── data truth ────────────────────────────────────────────────────────────────────────────────────
def test_supplier_not_connected_is_not_reported_as_supplying():
    repo = FakeRepo({"ab-1000-xy": [PART], "acme": [row("SUPPLIER", "S1", "Acme", 0)]}, suppliers=[])
    r = ask(service(repo), "Which suppliers are connected to AB-1000-XY?")
    assert r.results == [] and "No supplier relationship is recorded" in r.answer.summary and "Acme" not in r.answer.summary


def test_same_city_does_not_create_a_business_relationship():
    wh = [{"warehouse_id": "W", "name": "Depot", "city": "Assen", "country_code": "NL", "available": 3, "stock_status": "IN_STOCK", "data_status": "SYNTHETIC_DEMO"}]
    dealers = [{"dealer_id": "D", "name": "Dealer", "city": "Assen", "country_code": "NL", "dealer_type": None, "pickup_allowed": True, "available": 1, "stocking_status": "STOCKED", "data_status": "SYNTHETIC_DEMO"}]
    suppliers = [{"supplier_id": "S", "name": "Supplier", "city": "Assen", "country_code": "NL", "status": None, "is_primary": True, "lead_time_days": 2, "supplier_part_number": None, "categories": [], "data_status": "SYNTHETIC_DEMO"}]
    repo = FakeRepo({"ab-1000-xy": [PART]}, warehouses=wh, dealers=dealers, suppliers=suppliers)
    r = ask(service(repo), "Where is AB-1000-XY available?")
    assert any("does not imply a business relationship" in w for w in r.warnings)
    assert {e.relationship for e in r.evidence} <= {"AVAILABLE_AT", "STOCKED_BY", "SUPPLIED_BY"}  # never a relationship between dealer and supplier


def test_similar_names_are_never_called_interchangeable():
    related = [{"part_id": "PRT-2", "part_number": "AB-1001-XY", "name": "Similar", "category": "C", "relation": "SAME_NAME_GROUP_AS", "interchangeability_status": "UNKNOWN", "data_status": "SYNTHETIC_DEMO"}]
    r = ask(service(FakeRepo({"ab-1000-xy": [PART]}, related=related)), "Is there a replacement for AB-1000-XY?")
    assert r.warnings and "does not establish" in r.warnings[0]
    assert all(f.value == "Not established" for it in r.results for f in it.facts if f.label == "Interchangeability")
    assert not re.search(r"\b(alternative|replacement|equivalent)\b", r.answer.summary, re.I)


def test_unknown_stock_is_not_zero():
    r = ask(service(FakeRepo({"ab-1000-xy": [PART]}, warehouses=[], dealers=[])), "stock of AB-1000-XY")
    assert r.results == [] and "unknown" in r.answer.summary and "0 " not in r.answer.summary.replace("not the same as zero", "")
    assert any("not connected" in w.lower() for w in r.warnings)


def test_synthetic_inventory_and_compliance_are_labelled():
    wh = [{"warehouse_id": "W", "name": "Depot", "city": None, "country_code": None, "available": 3, "stock_status": "IN_STOCK", "data_status": "SYNTHETIC_DEMO"}]
    inv = ask(service(FakeRepo({"ab-1000-xy": [PART]}, warehouses=wh, dealers=[])), "stock of AB-1000-XY")
    assert any("demonstration data" in w for w in inv.warnings) and inv.results[0].data_class == "SYNTHETIC_DEMO"
    comp = [{"compliance_id": "C", "requirement": "R", "standard": "S", "certification": None, "certificate_status": "VALID_DEMO", "valid_until": None, "covers": [], "data_status": "SYNTHETIC_DEMO"}]
    c = ask(service(FakeRepo({"ab-1000-xy": [PART]}, compliance=comp)), "compliance for AB-1000-XY")
    assert any("not real certifications" in w for w in c.warnings)


# ── hard-code audit ───────────────────────────────────────────────────────────────────────────────
def test_intelligence_source_names_no_catalogue_entries():
    """Part numbers, machine models, suppliers, dealers and prices live in the graph, never in intelligence code."""
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "app"
    files = [*(app / "intelligence").glob("*.py"), *(app / "llm").glob("*.py"), app / "api/routes/intelligence.py", app / "schemas/intelligence.py",
             app / "graph/queries/intelligence.py", app / "graph/repositories/intelligence.py"]
    # a catalogue name looks like "<Name> (demo)"; the bare qualifier "(demo)" is vocabulary the answer checks need
    forbidden = re.compile(r"NVM-\d{4}|PRT-\d{3}|\b(NV|KFT|BTS)-\d{3,4}\b|[A-Za-z]{3,} \(demo\)|Hanselmann|Drenthe|Nordwest|Radiator|\bSUP-\d|\bDLR-\d|\bWH-\d|\bMCH-\d")
    for f in files:
        assert not forbidden.search(f.read_text(encoding="utf-8")), f"{f.name} contains a catalogue entry"
    assert len(files) >= 12


# ── demo qualifier in worded answers (QA fix 5) ───────────────────────────────────────────────────
def test_keep_demo_qualifier_repairs_dropped_names():
    from app.intelligence.grounding import keep_demo_qualifier
    names = {"Acme Seals (demo)", "Beta Parts (demo)"}
    assert keep_demo_qualifier("Acme Seals and Beta Parts (demo) supply it.", names) == "Acme Seals (demo) and Beta Parts (demo) supply it."


SUPPLIER_ROW = {"supplier_id": "S1", "name": "Acme Seals (demo)", "city": "X", "country_code": "NL", "status": None, "is_primary": True, "lead_time_days": 3,
                "supplier_part_number": None, "categories": [], "data_status": "SYNTHETIC_DEMO"}


def test_model_wording_that_drops_the_qualifier_is_repaired_and_flagged_demo():
    repo = FakeRepo({"ab-1000-xy": [PART]}, suppliers=[SUPPLIER_ROW])
    r = ask(service(repo, FakeLLM(reply="Acme Seals is connected to AB-1000-XY.")), "Which suppliers are connected to AB-1000-XY?")
    assert r.answer.source == "llm" and "Acme Seals (demo)" in r.answer.summary and r.answer.demo is True


def test_model_wording_that_drops_every_demo_qualifier_falls_back_to_the_template():
    repo = FakeRepo({"ab-1000-xy": [PART]}, suppliers=[SUPPLIER_ROW])
    svc = service(repo, FakeLLM(reply="A supplier in the Netherlands is connected to AB-1000-XY."))
    from app.intelligence.models import Outcome
    from app.intelligence.models import Intent as I
    outcome = Outcome("Acme Seals (demo) is connected to AB-1000-XY.", [], [ev_row()])
    answer = svc._answer("q", I.PART_TO_SUPPLIER, outcome)
    assert answer.source == "template" and "(demo)" in answer.summary and answer.demo is True


def ev_row():
    from app.schemas.intelligence import Evidence
    return Evidence(entity="AB-1000-XY", entity_kind="PART", relationship="SUPPLIED_BY", target="Acme Seals (demo)", target_kind="SUPPLIER", data_class="SYNTHETIC_DEMO")


def test_a_source_derived_name_is_never_labelled_demo_by_the_wording():
    from app.intelligence.grounding import drop_false_demo_qualifier
    demo = {"Hydraulic components (demo)", "ISO 4413 (demo)"}
    text = "AB-1000-XY (demo) has the Hydraulic components (demo) compliance under ISO 4413 (demo)."
    assert drop_false_demo_qualifier(text, demo, {"AB-1000-XY"}) == "AB-1000-XY has the Hydraulic components (demo) compliance under ISO 4413 (demo)."


def test_gemini_retries_a_transient_overload_but_never_a_quota_error():
    calls = {"n": 0}

    def overloaded_then_ok(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={})
        return _reply('{"in_scope": true, "domain": "parts_intelligence", "intent": "PART_TO_MACHINE", "entities": {}, "filters": {}, "requires_clarification": false}')

    assert _gemini(overloaded_then_ok).parse_question("q", INTENTS).intent == "PART_TO_MACHINE" and calls["n"] == 2
    quota = {"n": 0}

    def limited(request: httpx.Request) -> httpx.Response:
        quota["n"] += 1
        return httpx.Response(429, json={})

    with pytest.raises(LLMUnavailable):
        _gemini(limited).parse_question("q", INTENTS)
    assert quota["n"] == 1


# ── entity context: an answer always says what it is about ───────────────────────────────────────
PART_SUBJECT = {"label": "AB-1000-XY", "name": "Bucket, general purpose", "data_status": "SOURCE_DERIVED", "source": "Catalogue", "category": "Attachments", "subcategory": "Bucket", "part_status": "VERIFIED"}
FIT2 = FIT + [{**FIT[0], "machine_id": "MCH-2", "model_code": "ZZ-2", "name": "Zed Two"}]


def test_part_answers_carry_the_part_identity_and_name_it():
    repo = FakeRepo({"ab-1000-xy": [PART]}, fitment=FIT2, subject=lambda kind, id: PART_SUBJECT if (kind, id) == ("PART", "PRT-1") else None)
    r = ask(service(repo, FakeLLM(parse=LLMParse("PART_TO_MACHINE", ("AB-1000-XY",)))), "Which machines use AB-1000-XY?")
    assert r.subject is not None and (r.subject.kind, r.subject.label, r.subject.name) == ("PART", "AB-1000-XY", "Bucket, general purpose")
    facts = {f.label: f.value for f in r.subject.facts}
    assert facts == {"Category": "Attachments · Bucket", "Catalogue status": "Verified", "Source": "Catalogue"}
    assert r.subject.data_class == "SOURCE_DERIVED"
    assert r.answer.summary.startswith("AB-1000-XY (Bucket, general purpose) is associated with 2 machines")
    assert [i.title for i in r.results] == ["ZZ-1", "ZZ-2"]  # the machines, and nothing else
    assert all(i.kind == "machine" for i in r.results)


def test_subject_is_the_required_entity_for_every_part_intent():
    repo = FakeRepo({"ab-1000-xy": [PART]}, subject=lambda kind, id: PART_SUBJECT)
    for intent in ("PART_TO_SUPPLIER", "PART_TO_DEALER", "PART_TO_ASSEMBLY", "PART_TO_COMPLIANCE", "PART_TO_INVENTORY", "PART_TO_ORDERS", "PART_TO_SERVICE_PLAN", "PART_TO_PART"):
        r = ask(service(repo, FakeLLM(parse=LLMParse(intent, ("AB-1000-XY",)))), f"{intent} AB-1000-XY")
        assert r.subject is not None and r.subject.label == "AB-1000-XY", intent
        assert "Bucket, general purpose" in r.answer.summary, intent  # the empty answer names the part too


def test_machine_subject_uses_the_machine_name():
    sub = {"label": "ZZ-1", "name": "ZZ-1 Wheel Loader", "data_status": "SOURCE_DERIVED", "machine_type": "Wheel loader", "family": "Z"}
    repo = FakeRepo({"zz-1": [MACHINE]}, machine_parts=(0, []), subject=lambda kind, id: sub)
    r = ask(service(repo, FakeLLM(parse=LLMParse("MACHINE_TO_PART", ("ZZ-1",)))), "Which parts fit ZZ-1?")
    assert r.subject is not None and r.subject.kind == "MACHINE" and r.answer.summary.startswith("No parts are recorded as fitting ZZ-1 Wheel Loader")


def test_no_subject_when_the_results_are_the_entities():
    repo = FakeRepo({}, low_stock_parts=(0, []), subject=lambda kind, id: PART_SUBJECT)
    r = ask(service(repo, FakeLLM(parse=LLMParse("LOW_STOCK_PARTS", ()))), "Which parts are low on stock?")
    assert r.subject is None


# ── audit regressions: search plurals, naming one of several candidates, alternatives routing ──────────
def test_plural_search_words_still_find_singular_names():
    from app.graph.repositories.parts import search_tokens
    assert search_tokens("hydraulic hoses") == ["hydraulic", "hos"]
    assert search_tokens("air filters") == ["air", "filter"]
    assert search_tokens("brake pads glass 1.2m3") == ["brake", "pad", "glass", "1.2m3"]  # no change to short words, 'ss' or identifiers


def test_the_full_name_in_the_question_picks_one_of_several_candidates():
    cands = [row("ASSEMBLY", f"ASM-{s}", f"Hydraulics module, {s} series (demo)", tier=2) for s in ("NV", "KFT", "BTS")]
    repo = FakeRepo({"hydraulics module": cands}, assembly_core=None, assembly_parts=(0, []))
    r = ask(service(repo, FakeLLM(parse=LLMParse("ASSEMBLY_TO_PART", ("Hydraulics module",)))), "Which parts are in the Hydraulics module, NV series?")
    assert r.clarification is None and [e.label for e in r.entities] == ["Hydraulics module, NV series (demo)"]
    r = ask(service(repo, FakeLLM(parse=LLMParse("ASSEMBLY_TO_PART", ("Hydraulics module",)))), "Which parts are in the hydraulics module?")
    assert r.clarification is not None and len(r.clarification.candidates) == 3  # not named: still asked, never guessed


def test_alternatives_and_replacements_are_routed_to_explicit_links():
    desc = REGISTRY[Intent.PART_TO_PART].description.lower()
    assert all(w in desc for w in ("alternative", "replacement", "interchangeab")) and "never states interchangeability" in desc


def test_does_a_part_fit_one_machine_answers_for_that_pair_only():
    repo = FakeRepo({"ab-1000-xy": [PART], "zz-2": [row("MACHINE", "MCH-2", "ZZ-2")], "zz-9": [row("MACHINE", "MCH-9", "ZZ-9")]}, fitment=FIT2)
    r = ask(service(repo, FakeLLM(parse=LLMParse("PART_TO_MACHINE", ("AB-1000-XY", "ZZ-2")))), "Does AB-1000-XY fit the ZZ-2?")
    assert [i.title for i in r.results] == ["ZZ-2"] and r.answer.summary.startswith("Yes: AB-1000-XY is recorded as fitting ZZ-2 (fitment: confirmed)")
    r = ask(service(repo, FakeLLM(parse=LLMParse("PART_TO_MACHINE", ("AB-1000-XY", "ZZ-9")))), "Does AB-1000-XY fit the ZZ-9?")
    assert r.results == [] and "not established that it fits" in r.answer.summary and "ZZ-1, ZZ-2" in r.answer.summary  # unknown, never "does not fit"


# ── a misspelled category is still understood; an empty machine+category result says so and points to the same-family models ──
CATS = [{"id": "CAT-HY", "label": "Hydraulics", "data_status": "SOURCE_DERIVED"}, {"id": "CAT-BR", "label": "Brakes", "data_status": "SOURCE_DERIVED"}]


def test_misspelled_category_resolves_to_the_one_clear_category():
    from app.intelligence.models import Kind
    from app.intelligence.resolver import EntityResolver
    found = EntityResolver(FakeRepo(category_names=CATS)).resolve(("hydralic",))
    assert [r.label for r in found.by_kind[Kind.CATEGORY]] == ["Hydraulics"]
    assert EntityResolver(FakeRepo(category_names=CATS)).resolve(("zzzzzz",)).by_kind == {}  # no clear match: nothing is guessed


def test_machine_with_no_part_in_the_category_says_so_and_names_same_family_models():
    repo = FakeRepo({"bts-500": [row("MACHINE", "MCH-13", "BTS-500")], "hydralic": []}, category_names=CATS, machine_parts=(0, []),
                    machines_with_category=[{"model_code": "BTS-250", "parts": 2}])
    r = ask(service(repo, FakeLLM(parse=LLMParse("MACHINE_TO_PART", ("BTS-500", "hydralic")))), "hydralic for BTS-500")
    s = r.answer.summary
    assert r.results == [] and "no Hydraulics part is available in this store for BTS-500" in s and "BTS-250 (2 parts)" in s and "contact" in s


# ── casual requests ───────────────────────────────────────────────────────────────────────────────────────────
def test_casual_phrasing_is_reduced_to_the_part_named():
    from app.intelligence.casual import content_text
    assert content_text("show me that belt") == "belt"
    assert content_text("do you have a hose") == "hose"
    assert content_text("show me the hydraulics you have available") == "hydraulic"
    assert content_text("brake pads") == "brake pad"
    assert content_text("parts for my machine") == ""  # nothing named: still asks which machine


def test_the_plain_reading_is_only_a_fallback_for_an_unusable_model_reply():
    svc = IntelligenceService(FakeRepo(), None, FakeLLM(parse=LLMParse("UNSUPPORTED")))
    plain = svc._plain_request("show me that belt")  # used only when the model returned no usable structure
    assert plain is not None and plain.intent == "PART_SEARCH" and plain.need == "belt"
    assert svc._plain_request("show me NVM-1010-AT") is None  # a named identifier is left to the model
    assert svc._plain_request("parts for my machine") is None  # nothing named


def test_a_model_that_only_asks_for_detail_is_not_overridden():
    """The model's own reading decides: a clarification it asks for is asked, not answered by a word-stripping guess."""
    r = ask(service(FakeRepo(), FakeLLM(parse=LLMParse("UNSUPPORTED", requires_clarification=True, clarification_question="Which belt do you mean?"))), "show me that belt")
    assert r.scope == "NEEDS_CLARIFICATION" and r.clarification.question == "Which belt do you mean?" and r.results == []
