"""The question catalogs: served by the API as listed, about 30 questions each, and every record they name exists in the graph."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_graph
from app.core.config import get_settings
from app.main import app
from app.question_catalog import INTELLIGENCE_CATALOG, SHOPPING_CATALOG

CATALOGS = {"/api/v1/intelligence/catalog": INTELLIGENCE_CATALOG, "/api/v1/agent/catalog": SHOPPING_CATALOG}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("path", CATALOGS)
def test_the_api_serves_the_catalog_by_category(client, path):
    groups = client.get(path).json()
    assert groups == CATALOGS[path]
    questions = [q for g in groups for q in g["questions"]]
    assert 28 <= len(questions) <= 34
    assert len(set(questions)) == len(questions)
    assert len({g["category"] for g in groups}) == len(groups) >= 6
    assert all(q.strip() == q and len(q) >= 5 for q in questions)


ALL = " ".join(q for c in CATALOGS.values() for g in c for q in g["questions"])


@pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")
@pytest.mark.parametrize(("label", "key", "pattern"), [
    ("Part", "part_number", r"NVM-\d{4}-[A-Z]{2}"),
    ("Machine", "model_code", r"\b(?:NV|KFT|BTS)-\d{3,4}\b"),
    ("Order", "order_id", r"\b(?:HCME-ORD-\d{6}|ORD-\d{4})\b"),
])
def test_every_record_a_question_names_exists(label, key, pattern):
    names = sorted(set(re.findall(pattern, ALL)))
    assert names
    found = {r["k"] for r in get_graph().read(f"MATCH (n:{label}) WHERE n.{key} IN $names RETURN n.{key} AS k", names=names)}
    assert set(names) == found


@pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")
def test_every_named_supplier_dealer_warehouse_and_assembly_exists():
    graph = get_graph()
    for label, name in [("Supplier", "Veldstra Hydraulics (demo)"), ("Dealer", "Noordland Machines (demo)"), ("Warehouse", "Regional Distribution Centre Zwolle (demo)")]:
        assert name in ALL and graph.read(f"MATCH (n:{label} {{name: $name}}) RETURN count(n) AS c", name=name)[0]["c"] == 1
    assert "Final drive gearbox assembly" in ALL
    assert graph.read("MATCH (a:Assembly) WHERE a.name STARTS WITH 'Final drive gearbox assembly' RETURN count(a) AS c")[0]["c"] == 1
    assert graph.read("MATCH (d:Dealer {city: 'Rotterdam'}) RETURN count(d) AS c")[0]["c"] >= 1
    assert graph.read("MATCH (c) WHERE c.claim_id = 'CLM-G001' OR c.warranty_claim_id = 'CLM-G001' RETURN count(c) AS c")[0]["c"] == 1
