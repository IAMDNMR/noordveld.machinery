"""Conversation continuity through the real authenticated route and CAS project store."""
# ruff: noqa: F811 -- pytest fixtures intentionally share their parameter names

import json

import pytest

from app.design_studio.approval import digest
from app.design_studio.codegen import archive_files
from app.design_studio.discovery import blank_definition
from app.schemas.application_definition import ApplicationDefinition
from app.schemas.studio_task import StudioTask, TaskMessage
from tests.test_studio_voice_first import API, new_project, studio  # noqa: F401
from tests.test_studio_guided import journey  # noqa: F401
from tests.test_studio_roles import world, login, org, assign, S  # noqa: F401


def send(client, project, message, request_id, **extra):
    return client.post(
        f"{API}/projects/{project['id']}/studio/turn",
        json={
            "message": message,
            "request_id": request_id,
            "expected_revision": project["revision"],
            **extra,
        },
    )


@pytest.mark.parametrize(
    "name,entity",
    [
        ("Transport planning", "Shipment"),
        ("Warehouse receiving", "Receipt"),
        ("After-sales", "Service case"),
    ],
)
def test_instruction_executes_once_and_server_history_survives_reload(studio, name, entity):
    client, model, holder = studio
    holder["llm"] = model
    project = new_project(client)
    model.replies.append(
        {
            "reply": "Recorded the requested record type.",
            "actions": [
                {"type": "set_brief", "name": name, "goal": f"Manage {entity.lower()} records"},
                {
                    "type": "add_entity",
                    "name": entity,
                    "attributes": [{"name": "Reference", "type": "string"}],
                },
            ],
        }
    )
    response = send(client, project, f"Manage {entity.lower()} records", "request-create-1")
    assert response.status_code == 200, response.text
    result = response.json()
    assert [e["name"] for e in result["state"]["definition"]["business"]["entities"]] == [entity]
    revision = result["state"]["revision"]
    replay = send(client, project, f"Manage {entity.lower()} records", "request-create-1")
    assert replay.status_code == 200 and replay.json()["state"]["revision"] == revision
    assert len(model.seen) == 1 and replay.json()["turn"]["client_action"] is None
    state = client.get(f"{API}/projects/{project['id']}/studio/state").json()
    assert [m["role"] for m in state["task"]["history"]] == ["user", "assistant"]
    reused = send(client, state["definition"], "Delete everything", "request-create-1")
    assert reused.status_code == 409


def test_focused_question_answer_and_correction_use_saved_context(studio):
    client, model, holder = studio
    holder["llm"] = model
    project = new_project(client)
    model.replies.append(
        {
            "reply": "Who approves purchases?",
            "actions": [{"type": "set_brief", "goal": "Manage purchase requests"}],
            "questions": [{"topic": "approvals", "text": "Who approves purchases?"}],
        }
    )
    first = send(client, project, "Manage purchase requests", "request-question").json()
    question = first["turn"]["asked_question_id"]
    assert question and first["state"]["task"]["status"] == "awaiting_answer"
    model.replies.append(
        {
            "reply": "Recorded the approver.",
            "actions": [
                {"type": "answer_question", "question_id": question, "answer": "Warehouse manager"}
            ],
        }
    )
    answered = send(
        client, first["state"]["definition"], "Use the warehouse manager", "request-answer-1"
    ).json()
    assert (
        next(
            q
            for q in answered["state"]["definition"]["business"]["questions"]
            if q["id"] == question
        )["answer"]
        == "Warehouse manager"
    )
    prompt = json.loads(model.seen[-1][1])
    assert prompt["conversation"][0]["text"] == "Manage purchase requests"
    model.replies.append(
        {
            "reply": "Prepared the corrected role.",
            "actions": [
                {
                    "type": "answer_question",
                    "question_id": question,
                    "answer": "Procurement manager",
                },
                {"type": "add_role", "name": "Procurement manager"},
            ],
        }
    )
    corrected = send(
        client,
        answered["state"]["definition"],
        "That was wrong. Use the procurement manager role instead.",
        "request-correct-1",
    ).json()
    assert corrected["turn"]["proposal"]["actions"][0]["name"] == "Procurement manager"
    assert (
        next(
            q
            for q in corrected["state"]["definition"]["business"]["questions"]
            if q["id"] == question
        )["answer"]
        == "Procurement manager"
    )
    applied = send(client, corrected["state"]["definition"], "go ahead", "request-accept-1")
    assert applied.status_code == 200, applied.text
    assert [r["name"] for r in applied.json()["state"]["definition"]["business"]["roles"]] == [
        "Procurement manager"
    ]


def test_policy_answer_is_reviewed_and_go_ahead_does_not_invent_a_policy(studio):
    client, model, holder = studio
    holder["llm"] = model
    raw = blank_definition().model_dump(mode="json")
    raw["business"]["brief"]["goal"] = "Manage deliveries"
    raw["business"]["decisions"] = [
        {"id": "dec_short_stock", "question": "Should shortages allow partial delivery?"}
    ]
    project = client.post(f"{API}/projects", json=raw).json()
    model.replies.append({"reply": "Should shortages allow partial delivery?", "actions": []})
    first = send(client, project, "What is missing?", "request-policy-1", guided=True).json()
    blocked = send(
        client, first["state"]["definition"], "go ahead", "request-policy-2", guided=True
    ).json()
    assert blocked["turn"]["client_action"] is None
    assert blocked["state"]["definition"]["business"]["decisions"][0]["status"] == "open"
    answer = send(
        client,
        blocked["state"]["definition"],
        "Partial deliveries are allowed",
        "request-policy-3",
        guided=True,
    ).json()
    assert answer["turn"]["proposal"]["actions"][0]["type"] == "answer_decision"
    applied = send(client, answer["state"]["definition"], "apply", "request-policy-4", guided=True)
    assert applied.status_code == 200, applied.text
    assert applied.json()["state"]["definition"]["business"]["decisions"][0]["status"] == "decided"


def test_continuation_executes_existing_phase_service_and_replay_cannot_skip(journey, monkeypatch):
    client, url, state = journey
    response = send(client, state["definition"], "go ahesd", "request-next-001", guided=True)
    assert response.status_code == 200, response.text
    assert response.json()["state"]["flow"]["active"] == "knowledge"
    assert response.json()["turn"]["client_action"] is None
    replay = send(client, state["definition"], "go ahesd", "request-next-001", guided=True)
    assert replay.status_code == 200
    assert replay.json()["state"]["revision"] == response.json()["state"]["revision"]
    from tests.test_studio_voice_first import FakeModel

    model = FakeModel()
    model.replies.append({"reply": "Your reviewed requirements remain available.", "actions": []})
    monkeypatch.setattr("app.api.routes.studio_conversation.get_studio_llm", lambda: model)
    viewed = send(
        client,
        response.json()["state"]["definition"],
        "Show my reviewed requirements",
        "request-view-old",
        guided=True,
        stage="brief",
    )
    assert viewed.status_code == 200, viewed.text
    assert viewed.json()["state"]["flow"]["active"] == "knowledge"
    assert viewed.json()["state"]["flow"]["reviewed"] == ["brief"]


def test_failure_is_saved_and_a_new_request_can_recover_without_duplicate_changes(studio):
    client, model, holder = studio
    holder["llm"] = model
    project = new_project(client)
    model.replies.append(RuntimeError("interrupted test provider"))
    with pytest.raises(RuntimeError):
        send(client, project, "Add a Shipment record", "request-failure-1")
    state = client.get(f"{API}/projects/{project['id']}/studio/state").json()
    assert state["task"]["status"] == "blocked"
    assert (
        send(client, state["definition"], "Add a Shipment record", "request-failure-1").status_code
        == 409
    )
    model.replies.append(
        {
            "reply": "Recorded the request.",
            "actions": [
                {"type": "set_brief", "goal": "Manage shipments"},
                {"type": "add_entity", "name": "Shipment"},
            ],
        }
    )
    recovered = send(client, state["definition"], "Add a Shipment record", "request-recover-1")
    assert recovered.status_code == 200, recovered.text
    assert len(recovered.json()["state"]["definition"]["business"]["entities"]) == 1
    client.post("/api/v1/auth/login", json={"user_id": "studio-bob"})
    forbidden = send(
        client, recovered.json()["state"]["definition"], "Add a driver role", "request-forbidden"
    )
    assert forbidden.status_code in (403, 404)


def test_private_context_is_not_exported_and_cannot_change_approval_digest():
    original = blank_definition()
    private = original.model_copy(
        update={
            "assistant_context": StudioTask(
                history=[
                    TaskMessage(
                        role="user", text="private discussion", request_id="request-private"
                    )
                ]
            )
        }
    )
    assert digest(original, "design") == digest(private, "design")
    assert digest(original, "process") == digest(private, "process")
    exported = archive_files(private)
    assert "assistant_context" not in json.loads(exported["src/definition.json"])
    assert (
        ApplicationDefinition.model_validate(private.model_dump()).assistant_context.history[0].text
        == "private discussion"
    )


def test_deferral_asks_for_reason_then_records_warning_after_review(studio):
    client, model, holder = studio
    holder["llm"] = model
    raw = blank_definition().model_dump(mode="json")
    raw["business"]["brief"]["goal"] = "Manage deliveries"
    raw["business"]["decisions"] = [
        {"id": "dec_retention", "question": "How long should shipment tracking be retained?"}
    ]
    project = client.post(f"{API}/projects", json=raw).json()
    model.replies.append({"reply": "How long should shipment tracking be retained?", "actions": []})
    first = send(client, project, "What is missing?", "request-defer-1", guided=True).json()
    reason = send(
        client, first["state"]["definition"], "I'll decide later", "request-defer-2", guided=True
    ).json()
    assert reason["turn"]["proposal"] is None and "reason" in reason["turn"]["reply"]
    assert reason["state"]["definition"]["business"]["decisions"][0]["status"] == "open"
    proposed = send(
        client,
        reason["state"]["definition"],
        "The operations owner must review it",
        "request-defer-3",
        guided=True,
    ).json()
    assert proposed["turn"]["proposal"]["actions"][0]["type"] == "defer_decision"
    applied = send(
        client, proposed["state"]["definition"], "go ahead", "request-defer-4", guided=True
    )
    assert applied.status_code == 200, applied.text
    state = applied.json()["state"]
    decision = state["definition"]["business"]["decisions"][0]
    assert (
        decision["status"] == "deferred"
        and decision["deferral_reason"] == "The operations owner must review it"
    )
    findings = state["analysis"]["process"]["findings"]
    assert not any(f["code"] == "DECISION_OPEN" for f in findings)
    assert any(f["code"] == "DECISION_DEFERRED" and f["severity"] == "warning" for f in findings)


def test_dismissed_proposal_cannot_be_applied_after_session_recovery(studio):
    client, model, holder = studio
    holder["llm"] = model
    project = new_project(client)
    model.replies.append(
        {
            "reply": "Prepared a driver role.",
            "actions": [
                {"type": "set_brief", "goal": "Manage transport"},
                {"type": "add_role", "name": "Driver"},
            ],
        }
    )
    result = send(
        client, project, "Manage transport and add a driver role", "request-dismiss-1"
    ).json()
    response = client.post(
        f"{API}/projects/{project['id']}/studio/dismiss",
        json={
            "expected_revision": result["state"]["revision"],
            "proposal_id": result["turn"]["proposal"]["id"],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["task"]["pending_proposal"] is None
    assert response.json()["task"]["last_turn"]["proposal"] is None
    assert not response.json()["definition"]["business"]["roles"]


def test_deferral_cannot_bypass_business_owner_authority(world):
    client, _ = world
    login(client, "studio-alice")
    raw = blank_definition().model_dump(mode="json")
    raw["id"] = "app_policy_auth"
    raw["business"]["brief"]["goal"] = "Manage transport"
    raw["business"]["decisions"] = [
        {"id": "dec_attempts", "question": "How many delivery attempts are allowed?"}
    ]
    raw["assistant_context"] = {"status": "completed"}
    project = client.post(f"{S}/projects", json=raw, headers=org()).json()
    assert "assistant_context" not in project
    assign(client, project["id"], "user", "studio-dave", "editor")
    login(client, "studio-dave")
    root = f"{S}/projects/{project['id']}/studio"
    proposed = client.post(
        root + "/act",
        json={
            "expected_revision": project["revision"],
            "actions": [
                {
                    "type": "defer_decision",
                    "decision_id": "dec_attempts",
                    "reason": "Operations must review the policy",
                }
            ],
        },
        headers=org(),
    )
    assert proposed.status_code == 200, proposed.text
    result = proposed.json()
    assert result["state"]["definition"]["business"]["decisions"][0]["status"] == "open"
    proposal = result["turn"]["proposal"]
    body = {
        "expected_revision": result["state"]["revision"],
        **{key: proposal[key] for key in ("base_sha256", "candidate_sha256", "actions")},
    }
    denied = client.post(root + "/apply", json=body, headers=org())
    assert denied.status_code == 403 and "owner" in denied.text
    login(client, "studio-alice")
    allowed = client.post(root + "/apply", json=body, headers=org())
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["state"]["definition"]["business"]["decisions"][0]["status"] == "deferred"


def test_unavailable_action_is_reported_and_does_not_silently_advance(studio):
    client, model, holder = studio
    holder["llm"] = model
    project = new_project(client)
    model.replies.append(
        {
            "reply": "I added the shipment entity.",
            "actions": [{"type": "add_entity", "name": "Shipment"}],
        }
    )
    result = send(
        client, project, "Build shipment management", "request-locked-1", guided=True
    ).json()
    assert any(r["type"] == "add_entity" for r in result["turn"]["rejected"])
    assert not result["state"]["definition"]["business"]["entities"]
    next_result = send(
        client, result["state"]["definition"], "next phase", "request-locked-2", guided=True
    )
    assert next_result.status_code == 200, next_result.text
    assert next_result.json()["state"]["flow"]["active"] == "brief"


def test_test_command_executes_real_prerequisite_checks_without_creating_a_goal(studio):
    client, _, _ = studio
    project = new_project(client)
    response = send(client, project, "run generated tests", "request-test-001")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["turn"]["client_action"] == "test"
    assert result["state"]["revision"] == project["revision"]
    assert not result["state"]["definition"]["business"]["brief"]["goal"]
    failed = client.post(f"{API}/projects/{project['id']}/runtime/test", json={})
    assert failed.status_code == 409, failed.text
    state = client.get(f"{API}/projects/{project['id']}/studio/state").json()
    assert state["task"]["status"] == "blocked"
    assert state["revision"] == project["revision"]
    assert "could not start" in state["task"]["last_turn"]["reply"]
