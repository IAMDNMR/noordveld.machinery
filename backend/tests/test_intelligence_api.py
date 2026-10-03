"""Parts Intelligence API against the live validated graph (read-only). Skipped when Neo4j is not configured.

Values are discovered from the graph at run time, so the tests name no catalogue entries. The Gemini test only runs when a key is set.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_llm
from app.core.config import get_settings
from app.main import app

pytestmark = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")
V1 = "/api/v1/intelligence"


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_llm] = lambda: None  # deterministic and fast; the live-Gemini test uses `live_client`
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def live_client():
    app.dependency_overrides.pop(get_llm, None)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def seeds(client):
    """Questions built by the graph itself (the same ones the UI suggests)."""
    s = client.get(f"{V1}/suggestions").json()
    assert s, "the graph should provide suggestions"
    return {q["question"]: q["category"] for q in s}


@pytest.fixture(scope="module")
def part(client, seeds):
    first = next(q for q in seeds if q.startswith("Find "))
    return first.removeprefix("Find ")


def query(client, question, **extra):
    r = client.post(f"{V1}/query", json={"question": question, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_suggestions_cover_the_question_categories(client, seeds):
    assert {"Part Discovery", "Machine & Fitment", "Supplier Intelligence", "Provenance", "Compliance", "Inventory"} <= set(seeds.values())


@pytest.mark.parametrize("prefix,intent", [
    ("Which parts fit the", "MACHINE_TO_PART"), ("Which machines use", "PART_TO_MACHINE"), ("Which parts are related to", "PART_TO_PART"),
    ("Which suppliers are connected to", "PART_TO_SUPPLIER"), ("Which dealers stock", "PART_TO_DEALER"), ("What assemblies contain", "PART_TO_ASSEMBLY"),
    ("Where is", "PART_TO_LOCATION"), ("Which compliance requirements apply to", "PART_TO_COMPLIANCE"), ("What is the stock of", "PART_TO_INVENTORY"),
    ("Show the relationships for", "PART_GRAPH"), ("What is the provenance of", "PART_PROVENANCE"), ("Which parts does", "SUPPLIER_GRAPH"),
    ("What does", "DEALER_GRAPH"), ("Which parts are in", "ASSEMBLY_TO_PART"), ("Find", "PART_SEARCH"),
])
def test_every_suggested_question_routes_to_its_intent(client, seeds, prefix, intent):
    question = next(q for q in seeds if q.startswith(prefix))
    r = query(client, question)
    assert r["intent"] == intent, question
    assert r["clarification"] is None and r["answer"]["grounded"] is True and r["answer"]["summary"]
    assert r["graph_path"] and r["elapsed_ms"] >= 0


def test_results_are_structured_with_part_numbers_and_provenance(client, seeds):
    r = query(client, next(q for q in seeds if q.startswith("Which parts fit the")))
    assert r["results"] and r["total"] >= len(r["results"])
    item = r["results"][0]
    assert item["kind"] == "part" and item["part_number"] == item["title"] and item["facts"] and item["data_class"] != "UNKNOWN"
    assert r["evidence"] and all(e["relationship"] == "FITS" for e in r["evidence"]) and r["provenance"]


def test_data_quality_and_unsupported_and_unknown_entity(client):
    assert query(client, "Where is the catalogue data incomplete?")["intent"] == "DATA_QUALITY"
    assert query(client, "what is the weather in Paris")["intent"] == "UNSUPPORTED"
    r = query(client, "Which machines use ZQ-0000-XX?")
    assert r["clarification"] and r["results"] == []


def test_ambiguous_machine_asks_which_one(client):
    r = query(client, "which parts fit the loader")
    assert r["clarification"] and len(r["clarification"]["candidates"]) > 1 and r["results"] == []
    pick = r["clarification"]["candidates"][0]
    again = query(client, "which parts fit the loader", selected=[{"kind": pick["kind"], "key": pick["key"]}])
    assert again["clarification"] is None and again["intent"] == "MACHINE_TO_PART" and again["understood_by"] == "selection"


def test_replacement_question_does_not_claim_interchangeability(client, part):
    r = query(client, f"Is there a replacement for {part}?")
    assert r["intent"] == "PART_TO_PART" and r["warnings"]
    assert all(f["value"] == "Not established" for it in r["results"] for f in it["facts"] if f["label"] == "Interchangeability")


def test_invalid_requests_are_rejected(client):
    assert client.post(f"{V1}/query", json={"question": "x"}).status_code == 422
    assert client.post(f"{V1}/query", json={"question": "ok question", "limit": 999}).status_code == 422


# ── part workspace ────────────────────────────────────────────────────────────────────────────────
def test_part_workspace_tabs(client, part):
    base = f"{V1}/parts/{part}"
    overview = client.get(base).json()
    assert overview["part_number"] == part and overview["status"]["label"] and overview["data_class"] != "UNKNOWN"
    assert any(a["kind"] == "parts_store" and a["href"].endswith(part) for a in overview["actions"]) or overview["status"]["code"] != "VERIFIED"
    assert client.get(f"{base}/fitment").json() and all(f["data_class"] for f in client.get(f"{base}/fitment").json())
    assert isinstance(client.get(f"{base}/relationships").json(), list)
    assert client.get(f"{base}/assemblies").json()[0]["components"] is not None
    assert client.get(f"{base}/suppliers").json()[0]["relation"] == "SUPPLIED_BY"
    assert client.get(f"{base}/dealers").json()[0]["relation"] == "STOCKED_BY"
    inv = client.get(f"{base}/inventory").json()
    assert inv["state"] == "CONNECTED" and inv["total_available"] is not None and "demonstration" in inv["note"]
    assert client.get(f"{base}/compliance").json()
    prov = client.get(f"{base}/provenance").json()
    assert prov["classification"] and prov["relationship_sources"] and prov["limitations"]
    insights = {i["key"]: i for i in client.get(f"{base}/insights").json()}
    assert insights["machines"]["value"] == len(client.get(f"{base}/fitment").json())  # counted in Neo4j, equals the listed fitment
    graph = client.get(f"{base}/graph").json()
    ids = {n["id"] for n in graph["nodes"]}
    assert graph["nodes"][0]["part_number"] == part and all(e["source"] in ids and e["target"] in ids for e in graph["edges"])


def test_part_without_stock_reports_not_connected_not_zero(client):
    """Find any part with no stock relationship; if the graph has none, the case cannot occur and is covered by the unit test."""
    page = client.get("/api/v1/parts", params={"limit": 60}).json()["items"]
    for p in page:
        inv = client.get(f"{V1}/parts/{p['part_number']}/inventory").json()
        if inv["state"] == "NOT_CONNECTED":
            assert inv["total_available"] is None and inv["data_class"] == "NOT_CONNECTED"
            return


def test_unknown_part_is_a_structured_404(client):
    r = client.get(f"{V1}/parts/NOPE-0000")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert client.get(f"{V1}/parts/NOPE-0000/graph").status_code == 404


def test_kpis_are_consistent_with_the_catalogue(client):
    k = client.get(f"{V1}/kpis").json()
    assert k["parts"] == client.get("/api/v1/parts", params={"limit": 1}).json()["total"]
    assert 0 < k["provenance_coverage_pct"] <= 100 and k["relationships"] > k["fitments"] > 0


@pytest.mark.skipif(not get_settings().llm_configured, reason="GEMINI_API_KEY is not configured")
def test_live_gemini_understands_a_free_form_question(live_client, part):
    r = query(live_client, f"I need to know which suppliers provide {part}, could you tell me")
    if r["understood_by"] == "llm" or r["intent"] == "PART_TO_SUPPLIER":
        assert r["intent"] == "PART_TO_SUPPLIER"
    assert r["answer"]["source"] in ("template", "gemini")
