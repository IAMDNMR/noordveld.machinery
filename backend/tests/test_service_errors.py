"""Dependency failures describe the affected feature without exposing connection details."""

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import GraphUnavailableError
from app.main import create_app


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/api/v1/auth/error-probe", "account service"),
        ("/api/v1/checkout/error-probe", "Refresh the order status"),
        ("/api/v1/parts/error-probe/dependency", "parts catalogue"),
        ("/api/v1/site/error-probe", "Required data"),
    ],
)
def test_graph_error_matches_feature(path, expected):
    app = create_app()

    def unavailable():
        raise GraphUnavailableError("private-host-and-password")

    app.add_api_route(path, unavailable, methods=["POST"])
    with TestClient(app) as client:
        response = client.post(path)
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "graph_unavailable"
    assert expected in error["message"]
    assert "private-host-and-password" not in response.text
    if "parts" not in path:
        assert "parts catalogue" not in error["message"]


def test_every_refusal_has_the_same_error_shape_and_a_named_field():
    from pydantic import BaseModel, Field

    class Body(BaseModel):
        email: str = Field(min_length=3)
        quantity: int = Field(ge=1)

    def probe(body: Body) -> dict:
        return {"ok": True}

    app = create_app()
    app.add_api_route("/api/v1/site/shape-probe", probe, methods=["POST"])
    with TestClient(app) as client:
        bad = client.post("/api/v1/site/shape-probe", json={"email": "secret@example.com-but-too", "quantity": 0})
        missing = client.post("/api/v1/site/shape-probe", json={"quantity": 2})
        unknown = client.get("/api/v1/no-such-route")
        wrong = client.delete("/api/v1/site/shape-probe")
        broken = client.post("/api/v1/site/shape-probe", content=b"{bad", headers={"content-type": "application/json"})
    assert broken.status_code == 422 and broken.json()["error"]["details"]["field"] == "request"  # not a character offset such as "1"
    assert bad.status_code == 422
    err = bad.json()["error"]
    assert err["code"] == "validation_error" and err["details"]["field"] == "quantity"
    assert err["message"].startswith("quantity:")
    assert "secret@example.com" not in bad.text  # input values are never echoed back
    assert missing.json()["error"]["details"]["fields"] == [{"field": "email", "message": "This field is required."}]
    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "not_found"
    assert wrong.status_code == 405 and wrong.json()["error"]["code"] == "method_not_allowed" and "POST" in wrong.headers["allow"]
