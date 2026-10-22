"""Specification metadata, generation safety, completeness, approvals, audit and export artefacts.

Synthetic data, isolated temp-file storage, no Neo4j, no model provider, no network.
"""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies import current_user, get_orders_repository
from app.api.routes.design_studio import get_design_store, get_project_store
from app.core.roles import Role
from app.design_studio.codegen import generate_archive
from app.design_studio.completeness import EXPLANATIONS, analyze
from app.design_studio.diff import compare, invalidating_changes
from app.design_studio.knowledge.provider import LocalKnowledgeProvider, apply_pack
from app.design_studio.record_validation import entity_rules, sample_record, validate_record
from app.design_studio.service import template
from app.design_studio.sqlite_store import SqliteProjectStore, SqliteStudioStore
from app.main import app
from app.schemas.application_definition import ApplicationDefinition, convert_v1
from app.services.fulfilment import STATES
from app.services.orders import User
from app.services.part_status import STATUS_LABELS
from tests.support.fake_orders import FakeRepo

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
PROVIDER = LocalKnowledgeProvider()
PACK = "noordveld_spare_parts"
API = "/api/v1/design-studio"


def pack_definition(revision: int = 0) -> ApplicationDefinition:
    definition, _ = apply_pack(convert_v1(template("spare-parts"), "app_eng"), PACK, PROVIDER)
    return definition.model_copy(update={"revision": revision})


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.children or [])


# ── attribute metadata ──







# ── generated forms respect the metadata ──





def walk_raw(nodes):
    for node in nodes:
        yield node
        yield from walk_raw(node.get("children") or [])


# ── completeness ──



# ── record validation (authoritative server side) ──



# ── API: approvals, audit, comparison, validation, access ──

@pytest.fixture()
def studio(tmp_path):
    path = tmp_path / "studio.sqlite"
    drafts, projects = SqliteStudioStore(path), SqliteProjectStore(path)
    actor = {"id": "alice"}
    app.dependency_overrides[current_user] = lambda: User(actor["id"], "Tester", "test@example.invalid", Role.END_USER)
    app.dependency_overrides[get_design_store] = lambda: drafts
    app.dependency_overrides[get_project_store] = lambda: projects
    yield TestClient(app), actor
    for dependency in (current_user, get_design_store, get_project_store):
        app.dependency_overrides.pop(dependency, None)


def ready(raw: dict) -> dict:
    raw["business"]["brief"]["goal"] = "Order spare parts"
    for decision in raw["business"]["decisions"]:
        decision.update(status="deferred", deferral_reason="Synthetic demo: not decided by the business owner.")
    return raw


def approve(client, project, revision, scope, comment=""):
    first = client.post(f"{API}/projects/{project}/approve", json={"expected_revision": revision, "scope": scope}).json()
    warnings = first["error"]["details"]["finding_ids"] if first.get("error", {}).get("code") == "warnings_unacknowledged" else []
    return client.post(f"{API}/projects/{project}/approve", json={"expected_revision": revision, "scope": scope, "acknowledged_warnings": warnings, "comment": comment}).json()








# ── export artefacts ──

def test_export_is_reproducible_classified_and_safe():
    definition = pack_definition(3)
    data = generate_archive(definition, PROVIDER)
    assert data == generate_archive(definition, PROVIDER)
    with ZipFile(BytesIO(data)) as archive:
        names = archive.namelist()
        assert all(not name.startswith("/") and ".." not in name and "\\" not in name and ".env" not in name for name in names)
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["generator_version"] == "2" and manifest["specification_revision"] == 3 and manifest["specification_id"] == "app_eng"
        assert all(sha256(archive.read(name)).hexdigest() == digest for name, digest in manifest["file_sha256"].items())
        catalogue = json.loads(archive.read("design/artifacts.json"))
        assert {entry["path"] for entry in catalogue["files"]} == set(names)
        kinds = {entry["path"]: entry["kind"] for entry in catalogue["files"]}
        assert kinds["src/generated/validation.ts"] == "executable" and kinds["api/openapi.json"] == "contract" and kinds["src/App.tsx"] == "preview"
        assert {item["artifact"] for item in catalogue["unsupported"]} >= {"Backend API implementation", "Database schema and migrations"}
        schema = json.loads(archive.read("schemas/ent_order.schema.json"))
        assert schema["properties"]["order_id"]["readOnly"] is True and schema["properties"]["requester_email"]["format"] == "email"
        assert schema["additionalProperties"] is False and "order_id" in schema["required"]
        contract = json.loads(archive.read("api/openapi.json"))
        assert contract["paths"]["/steps/order_enter_details"]["post"]["x-required-permission"] == "orders.place"
        assert "order_id" not in contract["components"]["schemas"]["OrderInput"]["properties"]
        assert "Contract only" in contract["info"]["description"]
        models = archive.read("src/generated/models.ts").decode()
        assert 'readonly "order_id": string' in models and '"stock_status": "IN_STOCK" | "LOW_STOCK" | "ON_ORDER" | "OUT_OF_STOCK" | "UNKNOWN"' in models
        assert "eval(" not in archive.read("src/generated/validation.ts").decode()
        _run_generated_checks(archive)


def _run_generated_checks(archive: ZipFile) -> None:
    node = shutil.which("node")
    tsc = REPO / "frontend/node_modules/typescript/bin/tsc"
    vitest = REPO / "frontend/node_modules/vitest/vitest.mjs"
    if node is None or not tsc.exists() or not vitest.exists():
        pytest.skip("node, TypeScript or Vitest is not installed; generated-project checks not run")
    # Isolated workspace inside frontend/ so imports resolve against the installed packages; no network is used.
    target = Path(tempfile.mkdtemp(prefix=".export-check-", dir=REPO / "frontend"))
    try:
        archive.extractall(target)
        compiled = subprocess.run([node, str(tsc), "-p", str(target / "tsconfig.json")], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
        assert compiled.returncode == 0, compiled.stdout + compiled.stderr
        tested = subprocess.run([node, str(vitest), "run", "--root", str(target), "--dir", str(target / "src/generated")], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
        assert tested.returncode == 0, (tested.stdout + tested.stderr)[-3000:]
    finally:
        shutil.rmtree(target, ignore_errors=True)
