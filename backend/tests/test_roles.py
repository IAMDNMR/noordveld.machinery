"""End User and Order Processor: authentication, permissions, ownership, the status state machine and its audit trail.

The order workflow runs against an in-memory repository (no demo order in AuraDB is changed by the suite); catalogue, Parts
Intelligence and Agentic Shopping run against the live graph when it is configured, as in the other API tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_llm, get_orders_repository
from app.core.config import get_settings
from app.core.roles import PERMISSIONS, Role
from app.core.session import sign, verify
from app.llm import LLMParse, ShoppingParse
from app.main import app
from app.services.orders import FLOW, TRANSITIONS


from tests.support.fake_orders import FakeRepo, line  # noqa: E402


@pytest.fixture()
def repo():
    r = FakeRepo()
    app.dependency_overrides[get_orders_repository] = lambda: r
    yield r
    app.dependency_overrides.pop(get_orders_repository, None)


def client(user_id=None):
    c = TestClient(app)
    if user_id:
        assert c.post("/api/v1/auth/login", json={"user_id": user_id}).status_code == 200
    return c


# ── session and role resolution ──────────────────────────────────────────────────────────────────




def test_a_role_sent_by_the_browser_is_ignored(repo):
    c = client("U-ANNA")
    c.headers["X-Role"] = "ORDER_PROCESSOR"
    assert c.post("/api/v1/orders/O-1/status", json={"status": "CONFIRMED"}).status_code == 403




# ── END_USER ─────────────────────────────────────────────────────────────────────────────────────


def test_end_user_cannot_view_another_customers_order(repo):
    assert client("U-ANNA").get("/api/v1/orders/O-2").status_code == 403
    assert client("U-ANNA").get("/api/v1/orders/NOPE").status_code == 404

















# ── ORDER_PROCESSOR ──────────────────────────────────────────────────────────────────────────────




def test_processor_can_move_an_order_one_valid_step_and_it_is_audited(repo):
    r = client("U-JANE").post("/api/v1/orders/O-1/status", json={"status": "CONFIRMED", "expected_status": "NEW"})
    assert r.status_code == 200 and r.json()["status"] == "CONFIRMED"
    event = repo.orders_["O-1"]["history"][-1]
    assert event["previous_status"] == "NEW" and event["order_status"] == "CONFIRMED" and event["actor_name"] == "Jane" and event["actor_role"] == "ORDER_PROCESSOR"
    assert event["occurred_at"] and event["action"] == "status_change:NEW->CONFIRMED"












# ── both roles keep the existing products ────────────────────────────────────────────────────────
graph = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")


class Scripted:
    name = "scripted"

    def parse_question(self, question, intents):
        return LLMParse("MACHINE_LIST")

    def generate_grounded_response(self, *a, **k):
        from app.llm import LLMUnavailable

        raise LLMUnavailable("not needed")

    def parse_shopping_request(self, request):
        return ShoppingParse(True, machine="NV-3200", part_type="air filter")


