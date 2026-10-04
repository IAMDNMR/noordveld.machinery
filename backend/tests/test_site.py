"""Website and launch-film endpoints against the live graph: every value they return must equal the graph."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_graph
from app.core.config import get_settings
from app.main import app

pytestmark = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def graph():
    return get_graph()


def test_site_overview_is_the_graph(client, graph):
    o = client.get("/api/v1/site/overview").json()
    truth = {r["m"]: r for r in graph.read("""MATCH (m:Machine) OPTIONAL MATCH (m)-[:BRANDED_AS]->(b) OPTIONAL MATCH (m)-[:MEMBER_OF_FAMILY]->(f)
        RETURN m.model_code AS m, m.machine_type AS t, b.name AS brand, f.name AS family, size([(p:Part)-[:FITS]->(m) | 1]) AS parts""")}
    assert {m["model"] for m in o["machines"]} == set(truth)
    for m in o["machines"]:
        t = truth[m["model"]]
        assert (m["name"], m["brand"], m["family"], len(m["parts"])) == (t["t"], t["brand"], t["family"], t["parts"])
    assert o["part_count"] == graph.read("MATCH (p:Part) RETURN count(p) AS n")[0]["n"]
    assert sum(c["count"] for c in o["part_categories"]) == o["part_count"]
    assert o["families"] == sorted({r["family"] for r in truth.values() if r["family"]})


def test_plants_come_with_brand_acquisition_and_map_position(client, graph):
    plants = client.get("/api/v1/site/overview").json()["plants"]
    truth = {r["city"]: r for r in graph.read("MATCH (p:Plant) OPTIONAL MATCH (p)-[:OWNED_BY]->(b) RETURN p.city AS city, b.name AS brand, b.acquired_year AS year")}
    assert {p["city"] for p in plants} == set(truth)
    for p in plants:
        assert (p["brand"], p["acquired_year"]) == (truth[p["city"]]["brand"], truth[p["city"]]["year"])
        assert p["lat"] is not None and p["lon"] is not None  # every plant city has a map position


def test_launch_film_values_are_read_from_the_graph_with_provenance_names(client, graph):
    f = client.get("/api/v1/showcase/launch-film").json()
    price = graph.read("MATCH (:Part {part_id: $id})<-[:PRICES_PART]-(p:Price) RETURN p.list_price_ex_vat AS v", id=f["part"]["id"])[0]["v"]
    assert f["part"]["priceExVat"] == price
    stock = {r["id"]: r["a"] for r in graph.read("MATCH (:Part {part_id: $id})-[a:AVAILABLE_AT|STOCKED_BY]->(n) RETURN coalesce(n.warehouse_id, n.dealer_id) AS id, a.available AS a", id=f["part"]["id"])}
    assert {s["id"]: s["available"] for s in f["stock"]} == stock
    assert f["supplier"]["name"].endswith("(demo)") and f["customer"]["name"].endswith("(demo)")  # synthetic records keep their label
    assert f["delivery"]["from"] in stock and f["counts"]["parts"] == 100


def test_agent_pipeline_is_defined_by_the_backend(client):
    steps = client.get("/api/v1/agent/pipeline").json()
    assert [s["key"] for s in steps] == ["request", "understand", "machine", "part", "fitment", "availability", "fulfilment", "compare", "recommend"]


def test_site_endpoints_fail_clearly_when_the_graph_is_down():
    from app.core.exceptions import GraphUnavailableError

    class Down:
        def read(self, *a, **k):
            raise GraphUnavailableError("down")

        def close(self):
            pass

    app.dependency_overrides[get_graph] = lambda: Down()
    try:
        with TestClient(app) as c:
            assert c.get("/api/v1/site/overview").status_code == 503
            assert c.get("/api/v1/showcase/launch-film").status_code == 503
    finally:
        app.dependency_overrides.clear()
