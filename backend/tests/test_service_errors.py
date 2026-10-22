"""Dependency failures describe the affected feature without exposing connection details."""

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import GraphUnavailableError
from app.main import create_app


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/api/v1/studio-session/error-probe", "account service"),
        ("/api/v1/design-studio/error-probe", "Design Studio"),
        ("/api/v1/domain-knowledge/error-probe", "knowledge service"),
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
