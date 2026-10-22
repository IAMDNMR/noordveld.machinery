"""The voice-first Studio: conversation turns, proposals, stage status, revert, and speech. No network: the model and Deepgram are test doubles."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.assistant.speech_deepgram import DeepgramSpeech, SpeechUnavailable
from app.design_studio.discovery import blank_definition
from app.design_studio.local_app import create_local_app
from app.llm.base import LLMUnavailable

API = "/api/v1/design-studio"
FIRST = "I want to build a transport management system for our company to manage transport requests, vehicle assignments, shipment tracking, deliveries, and exceptions."


class FakeModel:
    """Stands in for the language model: returns whatever JSON the test queues, and records what it was shown."""
    name = "fake"
    _model = "fake-1"

    def __init__(self):
        self.replies: list = []
        self.seen: list[tuple[str, str]] = []

    def studio_json(self, system: str, prompt: str) -> dict:
        self.seen.append((system, prompt))
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def studio(monkeypatch):
    monkeypatch.setenv("DESIGN_STUDIO_LOCAL_DEV", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("STUDIO_VOICE", "off")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    model = FakeModel()
    holder = {"llm": None}
    monkeypatch.setattr("app.api.routes.studio_conversation.get_studio_llm", lambda: holder["llm"])
    monkeypatch.setattr("app.assistant.providers.get_studio_llm", lambda: holder["llm"])
    with TemporaryDirectory(prefix="noordveld-studio-") as root:
        with TestClient(create_local_app(Path(root) / "studio.sqlite")) as client:
            client.post("/api/v1/auth/login", json={"user_id": "studio-alice"})
            yield client, model, holder


def new_project(client) -> dict:
    definition = blank_definition().model_copy(update={"id": "app_voice_test"})
    response = client.post(f"{API}/projects", json=definition.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    return response.json()


def turn(client, project, message, **extra):
    body = {"message": message, "expected_revision": project["revision"], **extra}
    response = client.post(f"{API}/projects/{project['id']}/studio/turn", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_without_a_model_the_first_request_is_recorded_and_nothing_is_copied_from_a_pack(studio):
    client, _, _ = studio
    project = new_project(client)
    result = turn(client, project, FIRST)
    t, state = result["turn"], result["state"]
    assert t["mode"] == "local_rules" and t["degraded"] == "No language model is configured."
    assert t["proposal"] is None, "no reference pack is proposed as a template"
    business = state["definition"]["business"]
    assert business["brief"]["goal"].startswith("I want to build a transport management system") and business["brief"]["domain_id"]
    assert business["knowledge"] == [] and not business["roles"] and not state["definition"]["workflow_definitions"]
    assert state["stages"]["knowledge"]["status"] == "in_progress"
    assert all(item["status"] != "completed" for item in state["stages"].values())




def test_the_model_plan_is_validated_and_split_into_applied_and_reviewed_changes(studio):
    client, model, holder = studio
    holder["llm"] = model
    project = new_project(client)
    model.replies.append({"reply": "A recipe costing tool. Who signs off a costing?", "ask": None,
                          "questions": [{"topic": "approvals", "text": "Who signs off a recipe costing?"}], "focus": "requirements",
                          "actions": [{"type": "set_brief", "name": "Recipe costing", "goal": "Bakers cost recipes and the owner signs them off", "user_types": ["Baker", "Owner"]},
                                      {"type": "add_requirement", "statement": "A baker can submit a recipe for costing", "priority": "must", "acceptance_criteria": ["The costing names the ingredients"]},
                                      {"type": "add_entity", "name": "Recipe", "attributes": [{"name": "Batch date", "type": "date", "required": True}]},
                                      {"type": "add_role", "name": "Owner"},
                                      {"type": "create_workflow", "name": "Costing sign-off", "steps": [{"name": "Submit recipe", "kind": "form", "role": "Baker"}, {"name": "Sign off costing", "kind": "approval", "role": "Owner"}]},
                                      {"type": "wipe_database"},
                                      {"type": "add_requirement", "statement": ""}]})
    result = turn(client, project, "I need a tool to cost our bakery recipes", history=[{"role": "user", "text": "hello"}])
    t, definition = result["turn"], result["state"]["definition"]
    assert t["mode"] == "language_model" and t["degraded"] is None
    assert t["focus"] == "brief" and "Who signs off" in t["reply"]
    business = definition["business"]
    assert business["brief"]["goal"].startswith("Bakers cost recipes") and definition["metadata"]["name"] == "Recipe costing"
    assert [r["statement"] for r in business["requirements"]] == ["A baker can submit a recipe for costing"]
    assert [e["name"] for e in business["entities"]] == ["Recipe"]
    assert business["roles"] == [] and definition["workflow_definitions"] == [], "roles and processes wait for review"
    assert {r["type"] for r in t["rejected"]} == {"wipe_database", "add_requirement"}
    assert any(q["text"] == "Who signs off a recipe costing?" for q in business["questions"]), "the model's follow-up question joins the specification"
    assert t["asked_question_id"] and t["asked_question_id"].startswith("q_ai_")
    proposal = t["proposal"]
    assert {a["type"] for a in proposal["actions"]} == {"add_role", "create_workflow"} and "who may do what" in " ".join(proposal["reasons"]).lower()
    assert proposal["base_sha256"] != client.get(f"{API}/projects/{project['id']}/history").json()[0]["id"]
    sent = json.loads(model.seen[0][1])
    assert sent["person_says"] == "I need a tool to cost our bakery recipes" and sent["conversation"] == [{"role": "user", "text": "hello"}]
    assert "api_key" not in model.seen[0][1].lower()

    applied = client.post(f"{API}/projects/{project['id']}/studio/apply", json={"expected_revision": t["revision"], "base_sha256": proposal["base_sha256"],
                                                                                   "candidate_sha256": proposal["candidate_sha256"], "actions": proposal["actions"]}).json()
    process = applied["state"]["definition"]["workflow_definitions"][0]
    assert [s["label"] for s in process["states"]] == ["Start", "Submit recipe", "Sign off costing", "Completed"]
    assert all(s["role_id"] and s["permission"] for s in process["states"] if s["kind"] not in ("start", "end"))
    roles = {r["id"]: r for r in applied["state"]["definition"]["business"]["roles"]}
    assert all(s["permission"] in roles[s["role_id"]]["permissions"] for s in process["states"] if s["permission"]), "a step's permission is held by its role"
    from app.design_studio.knowledge.provider import get_knowledge_provider, identify_domains
    assert not identify_domains("I need a tool to cost our bakery recipes", get_knowledge_provider()), "this test's domain has no reference knowledge, by design"


def test_verified_knowledge_informs_the_model_and_unverified_packs_are_refused(studio):
    client, model, holder = studio
    holder["llm"] = model
    project = new_project(client)
    model.replies.append({"reply": "A purchase request system.", "focus": "requirements",
                          "actions": [{"type": "set_brief", "name": "Purchase requests", "goal": "Employees request items and managers approve them"},
                                      {"type": "add_role", "name": "Buyer"},
                                      {"type": "adopt_pack", "pack_id": "cat_workforce"}]})
    result = turn(client, project, "I need a purchase requisition and supplier approval system")
    t, business = result["turn"], result["state"]["definition"]["business"]
    assert business["knowledge"] == [] and any("verified" in r["reason"] for r in t["rejected"]), "a pack not checked against official documentation is refused"
    sent = json.loads(model.seen[0][1])["specification"]
    ids = {pack["id"] for pack in sent["reference_knowledge"]}
    assert {"cat_procure_to_pay", "cat_supplier_lifecycle"} <= ids, "the verified packs for the domain are shown, with their ids"
    assert all(pack["status"] == "approved" for pack in sent["reference_knowledge"]) and "adopt_pack{pack_id}" in model.seen[0][0]


def test_the_model_failing_degrades_to_rules_and_says_so(studio):
    client, model, holder = studio
    holder["llm"] = model
    project = new_project(client)
    model.replies.append(LLMUnavailable("rate_limited"))
    result = turn(client, project, FIRST)
    t = result["turn"]
    assert t["mode"] == "local_rules" and "unavailable" in t["degraded"] and t["proposal"] is None
    assert result["state"]["definition"]["business"]["brief"]["goal"].startswith("I want to build")




def test_generate_now_says_what_is_missing_instead_of_pretending(studio):
    client, _, _ = studio
    project, _ = adopted_project(client)
    result = turn(client, project, "Generate the application now")
    generation = result["turn"]["generation"]
    assert generation["state"] == "needs_process_approval" and "separate approver" in generation["message"]
    assert result["turn"]["client_action"] is None and result["turn"]["focus"] == "checks"
    assert result["state"]["stages"]["export"]["status"] == "not_started"


def test_stale_revision_and_permissions_are_enforced(studio):
    client, _, _ = studio
    project = new_project(client)
    url = f"{API}/projects/{project['id']}/studio/turn"
    assert client.post(url, json={"message": "hello", "expected_revision": 9}).status_code == 409
    assert client.post(url, json={"message": "hello", "expected_revision": 1, "extra": "x"}).status_code == 422
    client.post("/api/v1/auth/login", json={"user_id": "studio-bob"})  # business approver: may approve, may not edit
    assert client.post(url, json={"message": FIRST, "expected_revision": 1}).status_code == 403
    assert client.get(f"{API}/projects/{project['id']}/studio/state").status_code == 200
    client.post("/api/v1/auth/login", json={"user_id": "studio-frank"})  # a dealer is closed out of Design Studio entirely
    assert client.get(f"{API}/projects/{project['id']}/studio/state").status_code in (403, 404)


# ── speech ─────────────────────────────────────────────────────────────

def deepgram(handler) -> DeepgramSpeech:
    return DeepgramSpeech("test-key-value", httpx.Client(transport=httpx.MockTransport(handler)))










# ── what the person hears must match what happened ──

def pack_proposal(client, project):
    """Test setup only: the explicit action API still builds a transport project from a pack, so later behaviour can be exercised."""
    response = client.post(f"{API}/projects/{project['id']}/studio/act", json={"expected_revision": project["revision"], "actions": [{"type": "adopt_pack", "pack_id": "cat_procure_to_pay"}]})
    assert response.status_code == 200, response.text
    return response.json()["turn"]


def adopted_project(client):
    project = new_project(client)
    t = pack_proposal(client, project)
    p = t["proposal"]
    state = client.post(f"{API}/projects/{project['id']}/studio/apply", json={"expected_revision": t["revision"], "base_sha256": p["base_sha256"], "candidate_sha256": p["candidate_sha256"], "actions": p["actions"]}).json()["state"]
    return {"id": project["id"], "revision": state["revision"]}, state








