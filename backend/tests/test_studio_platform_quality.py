"""Platform-level guarantees of what Design Studio builds from approved knowledge. No network, no model."""
from __future__ import annotations

from app.design_studio.auto_resolve import resolve
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
    counts = lambda d: (len(d.business.rules), len(d.business.roles), len(d.business.requirements))
    assert counts(resolved) == counts(seeded)
    assert "rule_unused" in {r.id for r in resolved.business.rules} and "role_idle" in {r.id for r in resolved.business.roles}


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
