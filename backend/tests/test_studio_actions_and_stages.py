"""The closed action vocabulary, the stage statuses, the first-request grounding, and running what was generated. No network, no model."""
from __future__ import annotations

import urllib.request
import json

import pytest

from app.assistant import studio_agent
from app.assistant.studio_actions import REVIEW_ACTIONS, apply_actions, high_impact, parse_actions
from app.design_studio import stages
from app.design_studio.compiler import compile_project
from app.design_studio.completeness import analyze
from app.design_studio.discovery import blank_definition, discover
from app.design_studio.knowledge.provider import LocalKnowledgeProvider, identify_domains, apply_pack
from app.design_studio.process import ordered_states
from app.design_studio.runtime_demo import synthetic_transport
from tests.support.frontend import with_frontend
from app.domain_knowledge.store import ReadOnlyDomainStore

PROVIDER = LocalKnowledgeProvider()
FIRST = "I want to build a transport management system for our company to manage transport requests, vehicle assignments, shipment tracking, deliveries, and exceptions."


def run(definition, *raw):
    actions, invalid = parse_actions(list(raw))
    assert not invalid, invalid
    return apply_actions(definition, actions, PROVIDER)


def test_only_the_closed_vocabulary_is_accepted_and_anything_else_is_dropped_with_a_reason():
    actions, rejected = parse_actions([{"type": "add_role", "name": "Dispatcher"}, {"type": "drop_table"}, {"add_role": {"name": "Planner"}}, {"type": "add_role", "name": "x", "sudo": True}, "add_role", 7])
    assert [a.type for a in actions] == ["add_role", "add_role"] and [a.name for a in actions] == ["Dispatcher", "Planner"]
    assert len(rejected) == 4, "an unknown type, an extra field and two non-objects are refused, never repaired"
    assert not high_impact([a for a in actions if a.type == "add_requirement"]) and high_impact(actions) and "add_role" in REVIEW_ACTIONS










def test_first_request_is_the_goal_and_the_models_own_foundation_is_kept():
    plan = studio_agent.Plan(reply="Understood.", actions=parse_actions([{"type": "add_entity", "name": "Vehicle"}, {"type": "add_role", "name": "Driver"}, {"type": "set_brief", "name": "TMS"}])[0])
    grounded = studio_agent.ground_first_request(plan, discover(blank_definition(), PROVIDER)[0], FIRST)
    assert [a.type for a in grounded.actions] == ["add_entity", "add_role", "set_brief"], "the foundation designed for this request is never replaced by a pack"
    assert grounded.actions[2].goal.startswith("I want to build a transport management system")
    # Later turns are the model's own: nothing is rewritten once the project has a goal.
    later = studio_agent.Plan(actions=parse_actions([{"type": "add_entity", "name": "Driver"}])[0])
    populated, _, _ = run(blank_definition(), {"type": "set_brief", "goal": "x goal"})
    assert [a.type for a in studio_agent.ground_first_request(later, populated, "add a driver").actions] == ["add_entity"]


def test_only_verified_knowledge_can_be_adopted_into_a_project():
    base = blank_definition()
    unverified, _, refused = run(base, {"type": "adopt_pack", "pack_id": "cat_procurement"})
    assert unverified == base and "verified" in refused[0]["reason"], "a pack not checked against official documentation is refused"
    adopted, changes, refused = run(base, {"type": "adopt_pack", "pack_id": "cat_procure_to_pay"})
    assert not refused and changes and adopted.business.knowledge, "a verified pack brings its cited processes, rules and exception handling"
    findings = [f["code"] for f in analyze(discover(adopted, PROVIDER)[0], PROVIDER, "process")["findings"] if f["severity"] == "error"]
    assert findings == [], "adopted verified knowledge arrives complete: nothing is blocked"


def show(definition, compile_summary=None):
    analysis = analyze(definition, PROVIDER, "design")
    return stages.compute(definition, analysis, identify_domains(definition.business.brief.goal, PROVIDER), compile_summary)




def test_an_approved_design_completes_its_stages_and_generation_completes_only_when_it_ran():
    approved = with_frontend(synthetic_transport())  # the fixture the runtime tests use: approved process and design, generated interface
    before = show(approved)
    assert [before[k]["status"] for k in ("brief", "workflow", "data", "rules", "roles", "screen", "checks")] == ["completed"] * 7
    assert before["export"]["status"] == "ready_for_review", "approved, but nothing has been generated yet"
    ran = show(approved, {"status": "generated", "files": 55, "checks_passed": 9, "checks_failed": 0, "reason": None})
    assert ran["export"]["status"] == "completed" and "55 files" in ran["export"]["reason"]
    blocked = show(approved, {"status": "blocked", "files": 55, "checks_passed": 8, "checks_failed": 1, "reason": "a check failed"})
    assert blocked["export"]["status"] == "blocked" and blocked["export"]["reason"] == "a check failed"
    # Editing after approval makes the approval stale, so the stages stop claiming to be complete.
    edited, _, _ = run(approved, {"type": "add_requirement", "statement": "A new capability nobody approved", "priority": "should"})
    assert show(edited)["brief"]["status"] != "completed" and show(edited)["export"]["status"] == "not_started"


@pytest.fixture(scope="module")
def generated_files():
    result = compile_project(with_frontend(synthetic_transport()), ReadOnlyDomainStore(), PROVIDER)
    assert result["status"] == "generated", result["plan"]
    return result["files"]


def test_the_generated_application_can_be_tested_launched_called_and_stopped(generated_files):
    from app.design_studio.runtime_launcher import manager
    revision = 777
    outcome = manager.test("pytest-run", revision, generated_files)
    assert outcome["passed"] is True and outcome["passed_count"] == 31, outcome["output_tail"]
    assert outcome["failed_count"] == outcome["skipped_count"] == 0
    status = manager.launch("pytest-run", revision, generated_files)
    try:
        assert status["running"] and status["url"].startswith("http://127.0.0.1:") and manager.status("pytest-run", revision)["stale"] is False
        assert manager.status("pytest-run", revision + 1)["stale"] is True
        with urllib.request.urlopen(status["url"] + "/api/demo-users", timeout=5) as response:
            assert response.status == 200 and json.loads(response.read())
    finally:
        assert manager.stop("pytest-run") is True
    assert manager.status("pytest-run", revision) == {"running": False} and manager.stop("pytest-run") is False
    import shutil, tempfile
    from pathlib import Path
    assert not (Path(tempfile.gettempdir()) / f"noordveld-generated-pytest-run-r{revision}").exists(), "stopping removes the generated files"
    shutil.rmtree(Path(tempfile.gettempdir()) / f"studio-runtime-pytest-run-r{revision}", ignore_errors=True)










def test_unresolved_semantic_gaps_are_not_hidden_by_keyword_wiring():
    from app.design_studio.settle import settle
    from app.schemas.application_definition import ApplicationDefinition
    base, _ = apply_pack(blank_definition(), "cat_procurement", PROVIDER)
    raw = base.model_dump(mode="json")
    raw["business"]["exceptions"].append({"id": "exc_late", "name": "Delivery late", "trigger": "Arrives after the promised date", "recovery": "Record the receipt again", "resolution": None, "resolution_state_id": None, "origin": None})
    raw["business"]["requirements"].append({"id": "req_board", "statement": "Buyers see open purchase orders in one place", "kind": "functional", "priority": "must", "status": "draft", "acceptance_criteria": [{"id": "ac_board", "statement": "Listed"}]})
    gaps = lambda d: [f["code"] for f in analyze(d, PROVIDER, "design")["findings"] if f["code"] in ("EXCEPTION_NO_RESOLUTION", "REQ_UNCOVERED")]  # noqa: E731
    open_ = ApplicationDefinition.model_validate(raw)
    assert sorted(gaps(open_)) == ["EXCEPTION_NO_RESOLUTION", "REQ_UNCOVERED"]
    settled, notes = settle(open_, [f for f in analyze(open_, PROVIDER, "design")["findings"] if f["code"] in ("EXCEPTION_NO_RESOLUTION", "REQ_UNCOVERED")])
    assert sorted(gaps(settled)) == ["EXCEPTION_NO_RESOLUTION", "REQ_UNCOVERED"]
    assert settled.model_dump(mode='json') == open_.model_dump(mode='json')
    assert len(notes) == 2, 'remaining gaps are reported without fabricating process coverage'
