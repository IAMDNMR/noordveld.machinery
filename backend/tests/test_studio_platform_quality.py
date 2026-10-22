"""Platform-level guarantees of what Design Studio builds from approved knowledge. No network, no model."""
from __future__ import annotations

from app.design_studio.auto_resolve import resolve
from app.design_studio.compiler import references
from app.design_studio.evaluation import SCENARIOS, build, run
from app.design_studio.templates import automatic, navigation_for


def test_every_domain_scenario_builds_a_complete_connected_maintainable_application():
    failures = {result.name: result.failures for result in run() if not result.passed}
    assert not failures, failures


def test_overlapping_packs_share_one_record_and_everything_that_named_the_other_follows_it():
    definition = build(SCENARIOS["warehouse (WMS)"])
    names = [entity.name for entity in definition.business.entities]
    assert names.count("Item") == 1 and names.count("Warehouse") == 1
    ids = {entity.id for entity in definition.business.entities}
    assert all(
        entity_id in ids
        for workflow in definition.workflow_definitions
        for state in workflow.states
        for entity_id in [*state.reads_entity_ids, *state.writes_entity_ids]
    )


def test_resolving_findings_never_removes_a_rule_a_role_or_a_requirement():
    definition = build(SCENARIOS["warehouse (WMS)"])
    raw = definition.model_dump(mode="json")
    raw["business"]["roles"].append({**raw["business"]["roles"][0], "id": "role_idle", "name": "Idle clerk", "permissions": []})
    rule = {**raw["business"]["rules"][0], "id": "rule_unused", "execution": None, "origin": None, "status": "assumption"}
    raw["business"]["rules"].append(rule)
    from app.schemas.application_definition import ApplicationDefinition

    seeded = ApplicationDefinition.model_validate(raw)
    resolved, _ = resolve(seeded)
    def counts(d):
        return len(d.business.rules), len(d.business.roles), len(d.business.requirements)

    assert counts(resolved) == counts(seeded)
    assert "rule_unused" in {r.id for r in resolved.business.rules} and "role_idle" in {r.id for r in resolved.business.roles}


def test_a_drafted_role_that_is_a_shorter_name_for_a_verified_one_is_merged_but_a_different_job_stays():
    from app.schemas.application_definition import ApplicationDefinition

    raw = build(SCENARIOS["warehouse (WMS)"]).model_dump(mode="json")
    verified = next(role for role in raw["business"]["roles"] if role["origin"])
    verified["name"] = "Service technician"
    drafted = {**verified, "id": "role_drafted_tech", "name": "Technician", "origin": None, "permissions": [], "responsibilities": ["Carry out visits"]}
    other = {**verified, "id": "role_drafted_lead", "name": "Workshop technician lead", "origin": None, "permissions": []}
    raw["business"]["roles"] += [drafted, other]
    raw["workflow_definitions"][0]["states"][1]["role_id"] = "role_drafted_tech"
    raw["workflow_definitions"][0]["states"][1]["permission"] = None
    resolved, changes = resolve(ApplicationDefinition.model_validate(raw))
    names = {role.name for role in resolved.business.roles}
    assert "Technician" not in names and "Workshop technician lead" in names
    assert resolved.workflow_definitions[0].states[1].role_id == verified["id"]
    assert "Carry out visits" in next(r for r in resolved.business.roles if r.id == verified["id"]).responsibilities
    assert any("Merged the role Technician into Service technician" in line for line in changes)


def test_a_workflow_of_only_look_up_and_check_steps_is_a_dashboard_not_a_process_to_start():
    from types import SimpleNamespace as Step

    from app.design_studio.runtime_generation import is_view, work_areas

    flow = lambda *kinds: Step(states=[Step(kind=kind) for kind in ("start", *kinds, "end")])  # noqa: E731
    assert is_view(flow("search", "search", "review"))
    assert not is_view(flow("search", "form")) and not is_view(flow())
    definition = build(SCENARIOS["warehouse (WMS)"])
    assert all(area["id"] != "views" for area in work_areas(definition))


def test_the_preview_opens_with_consistent_sample_records_and_running_cases_for_every_scenario():
    from app.design_studio.runtime_generation import preview_document
    from app.design_studio.runtime_samples import sample_data

    for name, scenario in SCENARIOS.items():
        definition = build(scenario)
        samples = sample_data(definition)
        rows = {entity_id: {row["id"]: row for row in entity_rows} for entity_id, entity_rows in samples["records"].items()}
        for entity in definition.business.entities:
            assert rows[entity.id], f"{name}: {entity.name} has no sample records"
            attribute_ids = {a.id for a in entity.attributes}
            for row in rows[entity.id].values():
                assert set(row["data"]) - attribute_ids <= {r.field for r in references(definition)[0] if r.source == entity.id}, name
        workflows = {w.id: w for w in definition.workflow_definitions}
        assert samples["instances"], name
        for case in samples["instances"]:
            workflow = workflows[case["workflow"]]
            assert case["state"] in {s.id for s in workflow.states}
            assert all(record_id in rows[entity_id] for entity_id, record_id in case["links"].items()), name
            assert case["events"][0]["action"] == "process.start"
    import base64
    import re

    outer = preview_document(build(SCENARIOS["after-sales"]))
    inner = base64.b64decode(re.search(r"base64,([^\"]+)\"", outer).group(1)).decode()
    assert '"samples"' in inner and "sample-" in inner


def test_an_application_gets_a_visual_layer_without_a_template_choice_and_a_side_menu_when_large():
    definition = build(SCENARIOS["multi-domain (warehouse + procurement + transport)"])
    assert definition.template is None and automatic(definition) is not None
    assert navigation_for(definition, "bottom_tabs") == "sidebar"


def _step(name, role, kind="action"):
    return {"name": name, "kind": kind, "role": role}


def test_a_process_a_verified_pack_already_covers_is_refused_but_a_separate_activity_is_allowed():
    from app.assistant.studio_actions import apply_actions, parse_actions
    from app.design_studio.knowledge.provider import LocalKnowledgeProvider

    definition = build(SCENARIOS["warehouse (WMS)"])
    role = definition.business.roles[0].name
    drafts = [
        {"type": "create_workflow", "name": "Run cycle count", "steps": [_step("Record counted quantities", role), _step("Review differences", role)]},
        {"type": "create_workflow", "name": "Pack picked items", "steps": [_step("Pack items into containers", role)]},
    ]
    actions, invalid = parse_actions(drafts)
    saved, applied, refused = apply_actions(definition, actions, LocalKnowledgeProvider())
    names = [w.name for w in saved.workflow_definitions]
    assert "Run cycle count" not in names and "Pack picked items" in names
    assert len(refused) == 1 and "Stock count" in refused[0]["reason"]


def test_merging_a_drafted_duplicate_keeps_its_requirements_and_leaves_unrelated_processes_alone():
    import copy

    from app.design_studio.knowledge.provider import LocalKnowledgeProvider
    from app.design_studio.process_overlap import find_overlaps, merge_processes
    from app.schemas.application_definition import ApplicationDefinition

    provider = LocalKnowledgeProvider()
    definition = build(SCENARIOS["warehouse (WMS)"])
    raw = definition.model_dump(mode="json")
    original = next(w for w in raw["workflow_definitions"] if w["name"] == "Stock count")
    copy_ = copy.deepcopy(original)
    copy_["id"], copy_["name"] = "wf_run_cycle_count", "Run cycle count"
    ids = {}
    for state in copy_["states"]:
        ids[state["id"]] = state["id"] = f"{state['id']}_cc"
        state["requirement_ids"] = ["req_cycle_count"] if state["kind"] not in ("start", "end") else []
        state["rule_ids"], state["exception_ids"] = [], []
    for edge in copy_["transitions"]:
        edge["id"], edge["source"], edge["target"] = f"{edge['id']}_cc", ids[edge["source"]], ids[edge["target"]]
    raw["workflow_definitions"].append(copy_)
    raw["workflows"].append(copy_["id"])
    raw["business"]["requirements"].append({**raw["business"]["requirements"][0], "id": "req_cycle_count", "statement": "Inventory controllers run cycle counts of stock", "origin": None})
    seeded = ApplicationDefinition.model_validate(raw)
    assert [(f["duplicate"], f["keep"]) for f in find_overlaps(seeded, provider)] == [("wf_run_cycle_count", original["id"])]
    merge_processes(raw, original["id"], "wf_run_cycle_count")
    merged = ApplicationDefinition.model_validate(raw)
    assert "wf_run_cycle_count" not in {w.id for w in merged.workflow_definitions}
    assert "req_cycle_count" in {r for w in merged.workflow_definitions for s in w.states for r in s.requirement_ids}
    assert len(merged.workflow_definitions) == len(definition.workflow_definitions)


def test_the_process_name_catalogue_is_valid_and_only_names_processes_of_the_packs_it_cites():
    from app.design_studio.knowledge.process_synonyms import load_synonyms
    from app.design_studio.knowledge.provider import LocalKnowledgeProvider

    provider = LocalKnowledgeProvider()
    for entry in load_synonyms():
        assert entry.workflow_id in {w.id for w in provider.pack(entry.pack_id).workflows}, entry.workflow_id


def test_a_proposed_process_name_flags_a_duplicate_for_review_but_only_an_approved_one_blocks_drafting(monkeypatch):
    import copy
    from datetime import date

    import app.design_studio.knowledge.process_synonyms as catalogue
    from app.design_studio.knowledge.provider import LocalKnowledgeProvider
    from app.design_studio.process_overlap import covered_by, find_overlaps
    from app.schemas.application_definition import ApplicationDefinition

    provider = LocalKnowledgeProvider()
    definition = build(SCENARIOS["warehouse (WMS)"])
    raw = definition.model_dump(mode="json")
    reorder = next(w for w in raw["workflow_definitions"] if w["name"] == "Automatic reorder")
    draft = copy.deepcopy(reorder)
    ids = {}
    draft["id"], draft["name"] = "wf_automatic_restocking", "Automatic restocking"
    for state in draft["states"]:
        ids[state["id"]] = state["id"] = f"{state['id']}_rp"
        state["requirement_ids"], state["rule_ids"], state["exception_ids"] = [], [], []
    for edge in draft["transitions"]:
        edge["id"], edge["source"], edge["target"] = f"{edge['id']}_rp", ids[edge["source"]], ids[edge["target"]]
    raw["workflow_definitions"].append(draft)
    raw["workflows"].append(draft["id"])
    seeded = ApplicationDefinition.model_validate(raw)

    found = find_overlaps(seeded, provider)
    assert [(f["duplicate"], f["keep"], f["approved"]) for f in found] == [("wf_automatic_restocking", reorder["id"], False)]
    assert covered_by(raw, "Automatic restocking", ["Check stock levels"], provider) is None  # proposed: a person judges afterwards

    approved = [e.model_copy(update={"review_state": "reviewed", "reviewed_by": "Test reviewer", "reviewed_on": date(2026, 10, 22)}) for e in catalogue.load_synonyms()]
    monkeypatch.setattr(catalogue, "load_synonyms", lambda: tuple(approved))
    assert covered_by(raw, "Automatic restocking", ["Check stock levels"], provider) == "Automatic reorder"
    assert covered_by(raw, "Pack picked items", ["Pack items into containers"], provider) is None


def test_the_generated_wms_application_passes_its_own_tests_and_says_why_any_path_cannot_run():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import evaluate_runtime

    result = evaluate_runtime.run_one("warehouse (WMS)", SCENARIOS["warehouse (WMS)"])
    assert result["status"] == "generated", result["reasons"]
    assert result["tests"]["ran"] > 50 and result["tests"]["failed"] == 0, result["failures"]
    # A path that needs a value nothing calculates is reported as skipped with its reason, never as a silent pass.
    assert all("calculat" in reason for reason in result["skips"])
