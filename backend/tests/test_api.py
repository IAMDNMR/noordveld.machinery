"""API tests against the live validated graph (read-only). Skipped when Neo4j is not configured."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

pytestmark = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_ready(client):
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_listing_and_pagination(client):
    page = client.get("/api/v1/parts", params={"limit": 10}).json()
    assert page["total"] == 100 and len(page["items"]) == 10
    nxt = client.get("/api/v1/parts", params={"limit": 10, "offset": 10}).json()
    assert {p["part_id"] for p in page["items"]}.isdisjoint(p["part_id"] for p in nxt["items"])


def test_search_by_name_number_and_legacy(client):
    by_name = client.get("/api/v1/parts", params={"q": "water pump"}).json()
    assert by_name["total"] >= 1
    number = by_name["items"][0]["part_number"]
    assert client.get("/api/v1/parts", params={"q": number.lower().replace("-", "")}).json()["items"][0]["part_number"] == number
    detail = client.get(f"/api/v1/parts/{number}").json()
    legacy = detail["legacy_references"][0]["legacy_part_number"]
    assert any(p["part_number"] == number for p in client.get("/api/v1/parts", params={"q": legacy}).json()["items"])


def test_empty_results(client):
    assert client.get("/api/v1/parts", params={"q": "zzzzzz-nothing"}).json() == {"items": [], "total": 0, "offset": 0, "limit": 24}


def test_filters_drive_listing(client):
    filters = client.get("/api/v1/catalogue/filters").json()
    assert filters["machines"] and filters["categories"] and filters["availability"]
    machine = filters["machines"][0]
    page = client.get("/api/v1/parts", params={"machine": machine["model_code"], "limit": 60}).json()
    assert page["total"] == machine["part_count"]
    assert all(machine["model_code"] in [f["model_code"] for f in p["fitment"]] for p in page["items"])
    cat = filters["categories"][0]
    assert client.get("/api/v1/parts", params={"category": cat["name"]}).json()["total"] == cat["part_count"]


def test_part_detail_keeps_unknown_unknown(client):
    detail = client.get("/api/v1/parts/PRT-078").json()
    assert detail["part"]["part_number"] == "NVM-1050-CL"
    assert detail["fitment"] and all(f["fitment_status"] for f in detail["fitment"])
    assert all(r["relation"] in {"SAME_NAME_GROUP_AS", "RELATED_COMPONENT", "CO_ORDERED_WITH"} for r in detail["related"])
    assert all(s.get("unit_cost") is None for s in detail["suppliers"])


def test_unknown_part_is_structured_404(client):
    r = client.get("/api/v1/parts/NOPE-0000")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_invalid_params_rejected(client):
    assert client.get("/api/v1/parts", params={"sort": "bogus"}).status_code == 422
    assert client.get("/api/v1/parts", params={"limit": 1000}).status_code == 422


def test_cart_quote(client):
    items = client.get("/api/v1/parts", params={"limit": 2}).json()["items"]
    body = {"items": [{"part_id": items[0]["part_id"], "quantity": 2}, {"part_id": "PRT-DOES-NOT-EXIST", "quantity": 1}]}
    quote = client.post("/api/v1/cart/quote", json=body).json()
    assert quote["unknown_part_ids"] == ["PRT-DOES-NOT-EXIST"]
    assert quote["order_placement_available"] is False
    price = items[0]["price"]
    if price:
        assert quote["subtotal"]["amount"] == round(price["amount"] * 2, 2)
    else:
        assert quote["subtotal"] is None
    assert client.post("/api/v1/cart/quote", json={"items": [{"part_id": "x", "quantity": 0}]}).status_code == 422
