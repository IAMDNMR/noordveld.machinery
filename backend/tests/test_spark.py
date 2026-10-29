"""Conversation continuity, shared tool execution and authority without external services."""

import json
from types import SimpleNamespace

import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_commerce_agent, get_orders, get_part_service
from app.core.exceptions import NotFoundError
from app.api.routes import spark, spark_voice
from app.speech.providers import get_speech
from app.api.routes.spark import get_spark_llm
from app.speech.contracts import Transcript
from app.core.session import sign
from app.llm import LLMInvalidResponse, LLMUnavailable
from app.llm.structured import StructuredLLM
from app.llm.nvidia import NvidiaClient
from app.core.config import Settings
from app.orgs.directory import get_org_directory
from app.schemas.agent import AgentResponse, Interpretation
from app.schemas.intelligence import Answer, Clarification, EntityRef, QueryResponse
from app.schemas.spark import SparkPlan
from app.services.spark import save_memory, remember_answer, previous_answer
from app.services import spark as spark_memory

SECRET = "spark-test-secret"


def plan(**kwargs):
    return SparkPlan(intelligence=None, shopping=None, account=None, clarification=None, **kwargs)


def answer(question, clarify=False):
    return QueryResponse(question=question, intent="PART_TO_SUPPLIER", intent_label="Suppliers",
                         understood_by="llm", entities=[EntityRef(kind="PART", key="p1", label="TEST-PART", match="exact")],
                         answer=Answer(summary="The recorded supplier is Example Supply.", grounded=True, source="template"),
                         results=[], total=0, evidence=[], provenance=[], graph_path=[], warnings=[], actions=[],
                         clarification=Clarification(question="Which machine?") if clarify else None, elapsed_ms=4)


@pytest.fixture
def world(monkeypatch):
    spark_voice._requests.clear()
    app = FastAPI()
    app.include_router(spark.router, prefix="/api/v1")
    app.include_router(spark_voice.router, prefix="/api/v1")
    seen = {"plans": [], "questions": [], "shopping": [], "commerce": []}
    class Model:
        next = plan()
        def parse_spark_request(self, rules, prompt):
            seen["plans"].append(json.loads(prompt))
            return self.next
    model = Model()
    class Questions:
        fail = False
        clarify = False
        def query(self, body):
            seen["questions"].append(body)
            if self.fail:
                raise LLMUnavailable("provider unavailable")
            return answer(body.question, self.clarify)
    questions = Questions()
    def shop(text):
        seen["shopping"].append(text)
        return AgentResponse(request=text, state="need_machine", interpretation=Interpretation(), steps=[], question="Which machine do you have?")
    class Commerce:
        def handle(self, body):
            seen["commerce"].append(body)
            return {"state": {"order_id": "test-order"}}
    app.dependency_overrides[get_org_directory] = lambda: SimpleNamespace(configured=False)
    app.dependency_overrides[get_orders] = lambda: SimpleNamespace(user=lambda _: None)
    app.dependency_overrides[get_spark_llm] = lambda: model
    app.dependency_overrides[spark.spark_questions] = lambda: questions
    app.dependency_overrides[spark.spark_shopping] = lambda: SimpleNamespace(recommend=shop)
    app.dependency_overrides[get_commerce_agent] = Commerce

    class Catalogue:  # one recorded part; any other number is not in the catalogue
        def detail(self, key):
            if key.upper().replace(" ", "-") != "NVM-1020-FL":
                raise NotFoundError("Part", key)
            return SimpleNamespace(part=SimpleNamespace(part_id="PRT-059", part_number="NVM-1020-FL"))  # the PartDetail shape
    app.dependency_overrides[get_part_service] = Catalogue
    monkeypatch.setattr(spark, "get_settings", lambda: SimpleNamespace(session_secret=SECRET))
    client = TestClient(app)
    return client, model, questions, seen, app


def test_natural_message_runs_real_shared_tool_and_followup_graph_uses_signed_context(world):
    client, model, _, seen, _ = world
    model.next = SparkPlan(intelligence="Who supplies TEST-PART?", shopping=None, account=None, clarification=None)
    first = client.post("/api/v1/spark/conversation", json={"message": "nvm 1010 at supllier pls"}).json()
    assert first["intelligence"]["answer"]["grounded"]
    assert seen["plans"][0]["message"] == "nvm 1010 at supllier pls"
    assert "NVM-1010-AT" in seen["plans"][0]["explicit_reference_hints"]
    assert seen["questions"][0].question == "Who supplies TEST-PART?"
    model.next = SparkPlan(intelligence="Show suppliers linked to TEST-PART", shopping=None, account=None, clarification=None, view="graph", reuse_previous=True)
    second = client.post("/api/v1/spark/conversation", json={"message": "show that as a graph", "context": first["context"]}).json()
    assert second["view"] == "graph"
    assert len(seen["questions"]) == 1
    assert second["intelligence"] == first["intelligence"]
    assert seen["questions"][-1].question == "Who supplies TEST-PART?"
    assert second["steps"][-1]["label"] == "Opened the graph of your previous answer"
    assert seen["plans"][-1]["offered_records"][0]["label"] == "TEST-PART"
    assert seen["plans"][-1]["recent_conversation"][0]["message"] == "nvm 1010 at supllier pls"


def test_graph_evidence_cache_is_bounded_private_and_expires(monkeypatch):
    monkeypatch.setattr(spark_memory, "_answers", spark_memory.OrderedDict())
    now = [10.0]
    monkeypatch.setattr(spark_memory.time, "monotonic", lambda: now[0])
    record = answer("Who supplies TEST-PART?")
    key = remember_answer(record, "user:organisation-one")
    assert previous_answer(key, "user:organisation-two") is None
    assert previous_answer(key, "other-user:organisation-one") is None
    retrieved = previous_answer(key, "user:organisation-one")
    retrieved.answer.summary = "Changed by caller"
    assert previous_answer(key, "user:organisation-one").answer.summary == record.answer.summary
    now[0] = 311.0
    assert previous_answer(key, "user:organisation-one") is None
    for _ in range(130):
        remember_answer(record, "user:organisation-one")
    assert len(spark_memory._answers) == 128


def test_graph_cache_miss_rechecks_records_and_changed_question_does_not_reuse_answer(world, monkeypatch):
    client, model, _, seen, _ = world
    monkeypatch.setattr(spark_memory, "_answers", spark_memory.OrderedDict())
    model.next = SparkPlan(intelligence="Who supplies TEST-PART?", shopping=None, account=None, clarification=None)
    first = client.post("/api/v1/spark/conversation", json={"message": "supplier?"}).json()
    spark_memory._answers.clear()
    model.next = model.next.model_copy(update={"view": "graph"})
    second = client.post("/api/v1/spark/conversation", json={"message": "graph", "context": first["context"]}).json()
    assert second["intelligence"] and len(seen["questions"]) == 2
    model.next = model.next.model_copy(update={"intelligence": "What machines fit TEST-PART?"})
    third = client.post("/api/v1/spark/conversation", json={"message": "fitment graph instead", "context": second["context"]}).json()
    assert third["intelligence"] and len(seen["questions"]) == 3
    assert seen["questions"][-1].question == "What machines fit TEST-PART?"


def test_clarification_answer_resumes_original_request_and_mixed_tools_both_execute(world):
    client, model, questions, seen, _ = world
    model.next = SparkPlan(intelligence=None, shopping="Find a replacement", account=None, clarification=None)
    first = client.post("/api/v1/spark/conversation", json={"message": "need replacement"}).json()
    model.next = SparkPlan(intelligence="Which parts fit Machine One?", shopping="Find a replacement for Machine One", account=None, clarification=None)
    second = client.post("/api/v1/spark/conversation", json={"message": "Machine One", "context": first["context"]}).json()
    assert seen["plans"][-1]["pending_request"] == "Find a replacement"
    assert second["intelligence"] and second["shopping"]
    assert len(seen["shopping"]) == 2


def test_clarification_does_not_guess_or_run_tools(world):
    client, model, _, seen, _ = world
    model.next = SparkPlan(intelligence=None, shopping=None, account=None, clarification="Which of the two parts do you mean?")
    result = client.post("/api/v1/spark/conversation", json={"message": "buy that one"}).json()
    assert result["message"].startswith("Which")
    assert not seen["questions"] and not seen["shopping"]


def test_private_data_requires_signin_and_never_calls_commerce_for_guests(world):
    client, model, _, seen, _ = world
    model.next = SparkPlan(intelligence=None, shopping=None, account="Where is my order?", clarification=None)
    response = client.post("/api/v1/spark/conversation", json={"message": "my order where"}).json()
    assert response["sign_in_required"] is True
    assert not seen["commerce"]


def test_failed_subtool_keeps_successful_result_and_reports_failure(world):
    client, model, questions, _, _ = world
    questions.fail = True
    model.next = SparkPlan(intelligence="Who supplies this part?", shopping="Find a replacement", account=None, clarification=None)
    result = client.post("/api/v1/spark/conversation", json={"message": "supplier and replacement"}).json()
    assert result["intelligence"] is None and result["shopping"]
    assert result["warnings"] and any(s["status"] == "failed" for s in result["steps"])


def test_selection_resumes_verified_question_without_reinterpreting(world):
    client, model, questions, seen, _ = world
    questions.clarify = True
    model.next = SparkPlan(intelligence="Which parts fit the machine?", shopping=None, account=None, clarification=None)
    first = client.post("/api/v1/spark/conversation", json={"message": "parts for machine"}).json()
    result = client.post("/api/v1/spark/conversation", json={"message": "selected", "context": first["context"], "selected": [{"kind": "MACHINE", "key": "m1"}]}).json()
    assert result["intelligence"]
    assert len(seen["plans"]) == 1
    assert seen["questions"][-1].selected[0].key == "m1"


def test_tampered_context_and_owner_change_are_refused(world):
    client, _, _, _, _ = world
    token = save_memory({"history": []}, SECRET, "another-user")
    for context in (token, token + "tampered"):
        assert client.post("/api/v1/spark/conversation", json={"message": "continue", "context": context}).status_code == 409


def test_expired_context_and_forged_authority_are_rejected(world):
    client, _, _, _, _ = world
    token = sign(json.dumps({"owner": "anonymous"}), "spark:" + SECRET, now=1, max_age=1)
    assert client.post("/api/v1/spark/conversation", json={"message": "continue", "context": token}).status_code == 409
    assert client.post("/api/v1/spark/conversation", json={"message": "my orders", "user_role": "OEM"}).status_code == 422


def test_router_model_output_is_schema_validated():
    class Model(StructuredLLM):
        def _complete(self, kind, system, prompt, schema):
            assert kind == "spark" and "view" in schema["properties"]
            return json.dumps({"intelligence": None, "shopping": None, "account": None, "clarification": "Which part?", "view": "answer", "run_sql": "DROP TABLE"})
    with pytest.raises(LLMInvalidResponse):
        Model(10).parse_spark_request("rules", "user text")


def test_speech_reuses_provider_without_storing_recording(world, monkeypatch):
    client, _, _, _, app = world
    class Speech:
        def status(self):
            return SimpleNamespace(enabled=True)
        def transcribe(self, scope, audio, mime):
            assert scope is None and audio == b"test-audio" and mime == "audio/webm"
            return Transcript(text="show that as a graph", confidence=.95)
        def synthesize(self, scope, text):
            assert text == "Which machine?"
            return b"audio-result"
    app.dependency_overrides[get_speech] = Speech
    assert client.get("/api/v1/spark/voice/status").json()["enabled"]
    # the voice mode is a server switch: hands-free by default, SPARK_VOICE_MODE=dictate rolls back to dictation only
    from app.core.config import get_settings
    for env, mode in (("", "hands_free"), ("dictate", "dictate")):
        monkeypatch.setenv("SPARK_VOICE_MODE", env)
        get_settings.cache_clear()
        assert client.get("/api/v1/spark/voice/status").json()["mode"] == mode
    get_settings.cache_clear()
    assert client.post("/api/v1/spark/voice/transcribe", content=b"test-audio", headers={"Content-Type": "audio/webm"}).json()["text"] == "show that as a graph"
    spoken = client.post("/api/v1/spark/voice/speak", json={"text": "Which machine?"})
    assert spoken.content == b"audio-result" and spoken.headers["cache-control"] == "no-store"


def test_account_permission_refusal_is_not_turned_into_an_answer(world, monkeypatch):
    client, model, _, seen, _ = world
    model.next = SparkPlan(intelligence=None, shopping=None, account="Read another person's order", clarification=None)
    monkeypatch.setattr(spark, "current_user", lambda *args, **kwargs: SimpleNamespace(can=lambda _: False))
    refused = client.post("/api/v1/spark/conversation", json={"message": "read other order"})
    assert refused.status_code == 403 and not seen["commerce"]


def test_oversized_speech_and_conversation_are_refused_before_provider_use(world):
    client, _, _, seen, _ = world
    assert client.post("/api/v1/spark/conversation", json={"message": "x" * 501}).status_code == 422
    assert client.post("/api/v1/spark/voice/speak", json={"text": "x" * 1501}).status_code == 422
    assert not seen["plans"]


def test_nvidia_hosted_schema_contract_is_supported_and_still_validated():
    def complete(request):
        body = json.loads(request.content)
        assert "nvext" not in body
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["strict"] is True
        content = {"intelligence": None, "shopping": None, "account": None,
                   "clarification": "Which part do you mean?", "view": "answer"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})
    model = NvidiaClient(Settings(nvidia_api_key="test-only", nvidia_planner_model="test-model"),
                         http=httpx.Client(transport=httpx.MockTransport(complete)))
    assert model.parse_spark_request("rules", "supplies for that?").clarification == "Which part do you mean?"


@pytest.mark.parametrize("grants,creator,expected", [
    ({"parts_intelligence": "app_user"}, False, (True, False)),
    ({"agentic_shopping": "app_user"}, False, (False, True)),
    ({"parts_intelligence": "app_user", "agentic_shopping": "app_user"}, False, (True, True)),
    ({"parts_intelligence": "app_viewer", "agentic_shopping": "app_user"}, False, (False, True)),
    ({}, True, (True, True)),
    ({}, False, None),
    ({"parts_intelligence": "app_viewer"}, False, None),
])
def test_organization_feature_grants_are_checked_independently(world, tmp_path, monkeypatch, grants, creator, expected):
    from app.api import app_access
    from app.core.session import COOKIE
    from app.orgs.directory import SqliteOrgDirectory

    client, model, _, seen, app = world
    directory = SqliteOrgDirectory(tmp_path / "orgs.sqlite")
    directory.seed_organization("org-test", "Test organization")
    # An unrelated app establishes membership without granting creator privileges.
    directory.seed_app_grant("member", "org-test", "parts_store", "app_user")
    for feature, role in grants.items():
        directory.seed_app_grant("member", "org-test", feature, role)
    if creator:
        directory.seed_membership("member", "org-test", "project_owner")
    app.dependency_overrides[get_org_directory] = lambda: directory
    app.dependency_overrides[get_orders] = lambda: SimpleNamespace(user=lambda uid: SimpleNamespace(id="member") if uid == "member" else None)
    monkeypatch.setattr(app_access, "get_settings", lambda: SimpleNamespace(session_secret=SECRET))
    client.cookies.set(COOKIE, sign("member", SECRET))
    model.next = SparkPlan(intelligence="Who supplies TEST-PART?", shopping="Find TEST-PART", account=None, clarification=None)
    result = client.post("/api/v1/spark/conversation", json={"message": "Who supplies it and can I buy it?"})
    if expected is None:
        assert result.status_code == 403
        assert not seen["plans"] and not seen["questions"] and not seen["shopping"]
    else:
        assert result.status_code == 200, result.text
        body = result.json()
        assert (body["intelligence"] is not None, body["shopping"] is not None) == expected
        assert (bool(seen["questions"]), bool(seen["shopping"])) == expected
        assert sum(step["status"] == "access_denied" for step in body["steps"]) == expected.count(False)
        # Voice uses the same combined entry policy, without requiring both grants.
        app.dependency_overrides[get_speech] = lambda: SimpleNamespace(synthesize=lambda scope, text: b"audio")
        voice = client.post("/api/v1/spark/voice/speak", json={"text": "Hello"})
        assert voice.status_code == 200, voice.text
    before = len(seen["plans"])
    rejected = client.post("/api/v1/spark/conversation", headers={"X-Org-Id": "other-org"}, json={"message": "Find a part"})
    assert rejected.status_code == 404
    assert len(seen["plans"]) == before
    client.cookies.clear()
    assert client.post("/api/v1/spark/conversation", json={"message": "Find a part"}).status_code == 401


@pytest.mark.parametrize("message,reference", [
    ("nvm 1010 at ki dealers evaru?", "NVM-1010-AT"),
    ("nvm1010at suppliers", "NVM-1010-AT"),
    ("nv 3200 ki filter", "NV-3200"),
    ("NVM-1010-AT-KI", "NVM-1010-AT-KI"),
])
def test_reference_hints_preserve_codes_without_transliteration_words(message, reference):
    assert reference in spark_memory.reference_hints(message)


def test_order_intent_starts_the_guided_order_only_for_a_part_spark_offered(world):
    client, model, _, seen, _ = world
    context = save_memory({"history": [], "offered": [{"kind": "PART", "label": "AB-1", "part_id": "P-AB-1"}], "pending": None}, SECRET, "anonymous")
    model.next = plan(order="ab-1")
    r = client.post("/api/v1/spark/conversation", json={"message": "order this part", "context": context}).json()
    assert r["order_part"] == {"part_id": "P-AB-1", "label": "AB-1", "patch": {}} and not seen["shopping"] and not seen["questions"]
    model.next = plan(order="ZZ-9")  # never offered and not in the catalogue: nothing to order, and the model cannot make an id up
    r = client.post("/api/v1/spark/conversation", json={"message": "order ZZ-9", "context": context}).json()
    assert r["order_part"] is None and "Which part" in r["message"]
    model.next = plan(order="nvm 1020 fl")  # an exact catalogue part number, however it is typed, is not a guess: the order starts with the catalogue's own id
    r = client.post("/api/v1/spark/conversation", json={"message": "order 1 NVM-1020-FL for my NV-3200", "context": context}).json()
    assert r["order_part"] == {"part_id": "PRT-059", "label": "NVM-1020-FL", "patch": {}}
    model.next = plan(order="the filter")  # a description is not a part number: still asked, never guessed
    r = client.post("/api/v1/spark/conversation", json={"message": "order the filter", "context": context}).json()
    assert r["order_part"] is None or r["order_part"]["part_id"] == "P-AB-1"
