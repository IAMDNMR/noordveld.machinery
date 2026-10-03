"""Parts Intelligence without Neo4j or a live model: rules, registry, Cypher safety, grounding, routing and data-truth behaviour."""
from __future__ import annotations

import re
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.graph.queries import intelligence as queries
from app.intelligence import rules
from app.intelligence.grounding import is_grounded
from app.intelligence.models import Intent
from app.intelligence.registry import REGISTRY, answerable_intents
from app.intelligence.service import IntelligenceService
from app.llm import LLMParse, LLMUnavailable, create_llm
from app.llm.base import LLMInvalidResponse
from app.llm.gemini import GeminiClient, RateLimiter
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
    return {n: v for n, v in vars(queries).items() if n.isupper() and isinstance(v, str)}


def test_cypher_is_read_only():
    forbidden = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH)\b|apoc\.(create|merge|refactor)|dbms\.", re.I)
    for name, text in _all_cypher().items():
        assert not forbidden.search(text), f"{name} contains a write or admin operation"


def test_cypher_is_parameterised_and_bounded():
    for name, text in _all_cypher().items():
        assert not re.search(r"['\"]\s*\+\s*\$", text), f"{name} concatenates a parameter into a string"
        bounded = re.search(r"LIMIT|\[\.\.\d+\]|\[0\.\.\$limit\]|count\(|size\(", text)
        assert bounded, f"{name} is unbounded"


# ── rules ─────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "question,intent",
    [
        ("Which machines use ABC-1234-XY?", Intent.PART_TO_MACHINE),
        ("What parts fit the AB-4500?", Intent.PART_TO_MACHINE),
        ("What category is ABC-1234-XY?", Intent.PART_TO_CATEGORY),
        ("What assemblies contain ABC-1234-XY?", Intent.PART_TO_ASSEMBLY),
        ("Which suppliers are connected to ABC-1234-XY?", Intent.PART_TO_SUPPLIER),
        ("Which parts does Acme supply?", Intent.PART_TO_SUPPLIER),
        ("Which dealers stock ABC-1234-XY?", Intent.PART_TO_DEALER),
        ("Where is ABC-1234-XY available?", Intent.PART_TO_LOCATION),
        ("What is the stock of ABC-1234-XY?", Intent.PART_TO_INVENTORY),
        ("compliance requirements for ABC-1234-XY", Intent.PART_TO_COMPLIANCE),
        ("What is the provenance of ABC-1234-XY?", Intent.PART_PROVENANCE),
        ("Show the relationships for ABC-1234-XY", Intent.PART_GRAPH),
        ("Is there a replacement for ABC-1234-XY?", Intent.PART_TO_PART),
        ("Where is the catalogue data incomplete?", Intent.DATA_QUALITY),
        ("find hydraulic hose", Intent.PART_SEARCH),
    ],
)
def test_rules_choose_the_intent(question, intent):
    assert rules.parse(question).intent is intent


def test_rules_extract_identifier_mentions_and_not_trailing_words():
    assert "NVM-1010-HY" in rules.parse("Which machines use NVM-1010-HY fit").mentions
    assert any(m.replace(" ", "-").lower() == "nvm-1010-hy" for m in rules.parse("show NVM 1010 HY").mentions)


def test_rules_leave_unrelated_questions_undecided():
    assert rules.parse("what is the weather in Paris").intent is None


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


# ── Gemini client ─────────────────────────────────────────────────────────────────────────────────
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
        return _reply('{"intent": "PART_TO_MACHINE", "mentions": ["P-1"], "requires_clarification": false}')

    parse = _gemini(handler).parse_question("which machines use P-1", INTENTS)
    assert "test-key-123" not in seen["url"] and seen["key"] == "test-key-123" and "m-test" in seen["url"]
    assert parse == LLMParse("PART_TO_MACHINE", ("P-1",), False, None)


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
        if isinstance(self.parse, Exception):
            raise self.parse
        return self.parse

    def resolve_entities(self, question, intents): return ()

    def generate_grounded_response(self, question, intent, evidence, draft):
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def service(repo: FakeRepo, llm: Any = None) -> IntelligenceService:
    return IntelligenceService(repo, NoParts(), llm)  # type: ignore[arg-type]


PART = row("PART", "PRT-1", "AB-1000-XY")
MACHINE = row("MACHINE", "MCH-1", "ZZ-1")


def ask(svc: IntelligenceService, question: str, **kw):
    return svc.query(QueryRequest(question=question, **kw))


def test_deterministic_question_never_calls_the_model():
    llm = FakeLLM(parse=LLMUnavailable("must not be used"), reply=LLMUnavailable("down"))
    repo = FakeRepo({"ab-1000-xy": [PART]}, fitment=[{"machine_id": "MCH-1", "model_code": "ZZ-1", "name": "Zed", "machine_type": "Loader", "family": "Z", "fitment_status": "CONFIRMED",
                                                      "condition_note": None, "data_status": "SOURCE_DERIVED"}])
    r = ask(service(repo, llm), "Which machines use AB-1000-XY?")
    assert (r.intent, r.understood_by, r.total, r.answer.source) == ("PART_TO_MACHINE", "rules", 1, "template") and llm.calls == 0
    assert r.evidence[0].relationship == "FITS" and r.provenance[0].data_class == "SOURCE_DERIVED"


def test_unsupported_question_does_not_hallucinate():
    r = ask(service(FakeRepo()), "what is the weather in Paris")
    assert r.intent == "UNSUPPORTED" and r.results == [] and "investigate parts" in r.answer.summary


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


def test_llm_unavailable_falls_back_to_a_clarification():
    r = ask(service(FakeRepo(), FakeLLM(LLMUnavailable("down"))), "tell me something vague about stuff")
    assert r.intent == "UNSUPPORTED" and r.answer.source == "template"


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
    assert good.answer.source == "gemini"


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
    forbidden = re.compile(r"NVM-\d{4}|PRT-\d{3}|\b(NV|KFT|BTS)-\d{3,4}\b|\(demo\)|Hanselmann|Drenthe|Nordwest|Radiator|\bSUP-\d|\bDLR-\d|\bWH-\d|\bMCH-\d")
    for f in files:
        assert not forbidden.search(f.read_text(encoding="utf-8")), f"{f.name} contains a catalogue entry"
    assert len(files) >= 12
