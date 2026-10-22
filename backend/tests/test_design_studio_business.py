"""Business-aware Design Studio: schema, reference pack, completeness, approval, generation, export.

Synthetic data and isolated temp-file storage only; never Neo4j, a model provider or production storage.
"""
from copy import deepcopy
from io import BytesIO
import json
import ast
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies import current_user
from app.api.routes.design_studio import get_design_store, get_project_store
from app.core.roles import PERMISSIONS, Role
from app.design_studio import approval
from app.design_studio.codegen import generate_archive
from app.design_studio.completeness import analyze
from app.design_studio.discovery import blank_definition, discover
from app.design_studio.knowledge.provider import GraphKnowledgeProvider, LocalKnowledgeProvider, PackConflict, PackUnavailable, apply_pack, identify_domains, stale_items
from app.design_studio.service import template
from app.design_studio.sqlite_store import SqliteProjectStore, SqliteStudioStore
from app.design_studio.traceability import impact, report
from app.lifecycle.rules import OUTCOMES
from app.logistics.rules import FIRST_EVENTS
from app.main import app
from app.schemas.application_definition import ApplicationDefinition, convert_v1
from app.services.order_flow import ACTIONS, EXCEPTIONS
from app.services.orders import User

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
PROVIDER = LocalKnowledgeProvider()
PACK = "noordveld_spare_parts"


def pack_design() -> dict:
    definition, _ = apply_pack(convert_v1(template("spare-parts"), "app_parts"), PACK, PROVIDER)
    return definition.model_dump(mode="json")


def ready_for_approval(raw: dict) -> dict:
    """What a user does on the brief, requirements and decisions tabs before approving. Synthetic, explicit choices."""
    business = raw["business"]
    business["brief"]["goal"] = "Let customers order the right spare part and follow it to delivery."
    for requirement in business["requirements"]:
        requirement["status"] = "agreed"
    for decision in business["decisions"]:
        decision["status"] = "deferred"
        decision["deferral_reason"] = "Synthetic demo: not decided by the business owner; the implemented behaviour stands."
    business["questions"] = []
    return raw


# ── schema ──



def _mutations():
    def first_state(raw):
        return raw["workflow_definitions"][0]["states"][1]

    def entity(raw, entity_id="ent_order"):
        return next(item for item in raw["business"]["entities"] if item["id"] == entity_id)

    def rule(raw, rule_id):
        return next(item for item in raw["business"]["rules"] if item["id"] == rule_id)

    return {
        "duplicate business ID": lambda raw: raw["business"]["roles"].append({**raw["business"]["roles"][0], "id": raw["business"]["requirements"][0]["id"]}),
        "duplicate criterion ID": lambda raw: raw["business"]["requirements"][0]["acceptance_criteria"].append(dict(raw["business"]["requirements"][0]["acceptance_criteria"][0])),
        "dangling role": lambda raw: first_state(raw).update(role_id="role_missing"),
        "dangling requirement": lambda raw: first_state(raw).update(requirement_ids=["req_missing"]),
        "dangling read entity": lambda raw: first_state(raw).update(reads_entity_ids=["ent_missing"]),
        "dangling write entity": lambda raw: first_state(raw).update(writes_entity_ids=["ent_missing"]),
        "dangling rule": lambda raw: first_state(raw).update(rule_ids=["rule_missing"]),
        "dangling exception": lambda raw: first_state(raw).update(exception_ids=["exc_missing"]),
        "duplicate step reference": lambda raw: first_state(raw).update(requirement_ids=["req_find_part", "req_find_part"]),
        "permission not held": lambda raw: first_state(raw).update(permission="orders.process"),
        "relationship target": lambda raw: entity(raw)["relationships"].append({"id": "rel_x", "name": "x", "target": "ent_missing", "cardinality": "one_to_many"}),
        "relationship cardinality": lambda raw: entity(raw)["relationships"].append({"id": "rel_x", "name": "x", "target": "ent_part", "cardinality": "some"}),
        "attribute type": lambda raw: entity(raw)["attributes"].append({"id": "x_attr", "name": "X", "type": "money"}),
        "key not required": lambda raw: entity(raw)["attributes"].append({"id": "x_key", "name": "X", "type": "string", "key": True}),
        "rule status": lambda raw: rule(raw, "rule_fitment").update(status="probable"),
        "confirmed synthetic rule": lambda raw: rule(raw, "rule_warranty_review").update(status="confirmed"),
        "decision rule with one outcome": lambda raw: rule(raw, "rule_fitment").update(outcomes=["COMPATIBLE"]),
        "undeclared rule outcome in condition": lambda raw: raw["workflow_definitions"][0]["transitions"][1]["condition"].update(value="MAYBE"),
        "exception resolution state": lambda raw: raw["business"]["exceptions"][0].update(resolution_state_id="state_missing"),
        "decision affects unknown": lambda raw: raw["business"]["decisions"][0].update(affects=["thing_missing"]),
        "entity owner role": lambda raw: entity(raw).update(owner_role_id="role_missing"),
        "integration entity": lambda raw: raw["business"]["integrations"][0]["entity_ids"].append("ent_missing"),
        "trace step": lambda raw: raw["screens"][0].update(trace={"workflow_id": "wf_spare_parts_order", "step_id": "state_missing"}),
        "trace requirement": lambda raw: raw["screens"][0].update(trace={"requirement_ids": ["req_missing"]}),
        "unknown business field": lambda raw: raw["business"]["requirements"][0].update(owner="someone"),
        "unknown top-level field": lambda raw: raw.update(extra_section={}),
        "nfr without category": lambda raw: raw["business"]["requirements"].append({"id": "nfr_x", "statement": "x", "kind": "non_functional", "priority": "must", "status": "draft"}),
        "outcome on non-end step": lambda raw: raw["workflow_definitions"][0]["states"][1].update(outcome="success"),
    }


def test_invalid_business_designs_are_rejected():
    for name, mutate in sorted(_mutations().items()):
        raw = pack_design()
        mutate(raw)
        with pytest.raises(ValidationError):
            ApplicationDefinition.model_validate(raw)



# ── reference knowledge reflects the implemented behaviour ──



















# ── the journey over HTTP with isolated SQLite ──

@pytest.fixture()
def studio(tmp_path):
    path = tmp_path / "studio.sqlite"
    drafts, projects = SqliteStudioStore(path), SqliteProjectStore(path)
    actor = {"id": "alice"}
    app.dependency_overrides[current_user] = lambda: User(actor["id"], "Tester", "test@example.invalid", Role.END_USER)
    app.dependency_overrides[get_design_store] = lambda: drafts
    app.dependency_overrides[get_project_store] = lambda: projects
    yield TestClient(app), actor, path
    for dependency in (current_user, get_design_store, get_project_store):
        app.dependency_overrides.pop(dependency, None)


API = "/api/v1/design-studio"






def _typecheck_export(content: bytes) -> None:
    node = shutil.which("node")
    tsc = REPO / "frontend/node_modules/typescript/bin/tsc"
    if node is None or not tsc.exists():
        pytest.skip("node or the frontend's TypeScript is not installed; exported-project type check not run")
    # Inside frontend/ so the generated imports resolve against the installed React types; no network is used.
    target = Path(tempfile.mkdtemp(prefix=".export-check-", dir=REPO / "frontend"))
    try:
        with ZipFile(BytesIO(content)) as archive:
            archive.extractall(target)
        result = subprocess.run([node, str(tsc), "-p", str(target / "tsconfig.json")], capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        shutil.rmtree(target, ignore_errors=True)
