"""Domain intelligence and domain-to-application compilation.

Synthetic packs and isolated temporary SQLite stores only. No test connects to Neo4j or any external service. Generated
TypeScript is compiled and its tests run in an isolated workspace when node and the frontend toolchain are installed.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.design_studio.compiler import compile_project, project_graph, references, resolve, update_plan, validate_references
from app.design_studio.discovery import blank_definition
from app.design_studio.knowledge.provider import LocalKnowledgeProvider, apply_pack
from app.design_studio.local_app import create_local_app
from app.domain_knowledge import importer
from app.domain_knowledge.adoption import adopt, required_closure
from app.domain_knowledge.models import DomainPack
from app.domain_knowledge.packs import shipped_packs
from app.domain_knowledge.store import ReadOnlyDomainStore, SqliteDomainStore, active
from app.domain_knowledge.traversal import MAX_DEPTH, KnowledgeGraph, pack_graph
from app.domain_knowledge.validation import analyze
from app.schemas.application_definition import ApplicationDefinition
from tests.test_design_studio_business import pack_design, ready_for_approval
from tests.test_design_studio_engineering import _run_generated_checks

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = LocalKnowledgeProvider()


def _latest(pack_id: str = "noordveld_machinery") -> DomainPack:
    return max((item for item in shipped_packs() if item.id == pack_id), key=lambda item: tuple(int(part) for part in item.version.split(".")))


def frozen_1_0_0() -> DomainPack:
    return next(item for item in shipped_packs() if item.id == "noordveld_machinery" and item.version == "1.0.0")

def pack() -> DomainPack:
    return _latest()


# ── reliable domain data ──







# ── multi-hop traversal ──





# ── compilation ──

def adopted(entity_ids: list[str], include_required: bool = True, base: ApplicationDefinition | None = None) -> ApplicationDefinition:
    return adopt(base or blank_definition(), pack(), entity_ids, include_required)[0]














# ── full journey through the API, generated code executed in isolation ──

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DESIGN_STUDIO_LOCAL_DEV", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    with TemporaryDirectory(prefix="noordveld-studio-") as root:
        with TestClient(create_local_app(Path(root) / "studio.sqlite")) as test_client:
            yield test_client


def login(client, user):
    assert client.post("/api/v1/auth/login", json={"user_id": user}).status_code == 200


API = "/api/v1/design-studio"
DK = "/api/v1/domain-knowledge"


def test_domain_to_application_journey(client, monkeypatch):
    from tests.support.frontend import enable_frontend_fixture

    enable_frontend_fixture(monkeypatch)
    login(client, "studio-alice")
    assert client.get(f"{DK}/me").json()["permissions"] == ["domain.propose", "domain.review"]
    trace = client.get(f"{DK}/traverse", params={"start": "order", "direction": "in", "kinds": "process", "depth": 1}).json()
    assert trace["results"][0]["node"]["id"] == "proc_spare_parts_order"
    assert client.get(f"{DK}/traverse", params={"start": "nope"}).status_code == 404
    assert client.get(f"{DK}/traverse", params={"start": "order", "depth": 9}).status_code == 422

    blueprint, _ = apply_pack(blank_definition(), "cat_ecommerce", PROVIDER)
    base = ApplicationDefinition.model_validate(ready_for_approval(blueprint.model_dump(mode="json")))
    adoption = client.post(f"{DK}/adopt", json={"definition": base.model_dump(mode="json"), "entity_ids": ["order", "order_line", "part"], "include_required": True}).json()
    assert adoption["report"]["added_as_required_dependency"] == ["dk_category", "dk_customer", "dk_plant"]
    raw = adoption["definition"]
    raw["id"] = "app_compiled"
    assert client.post(f"{API}/projects", json=raw).status_code == 200
    preview = client.get(f"{API}/projects/app_compiled/compile").json()
    assert preview["status"] == "blocked" and not [i for i in preview["resolution"]["issues"] if i["code"] == "UNRESOLVED_DEPENDENCY"]
    assert client.get(f"{API}/projects/app_compiled/compile/archive").json()["error"]["code"] == "generation_blocked"

    # approve process → generate screens → approve design, as the user does in the studio
    def approve(revision: int, scope: str) -> dict:
        # The creator cannot approve her own project: a business approver in the organization does.
        assert client.post(f"{API}/projects/app_compiled/approve", json={"expected_revision": revision, "scope": scope}).status_code == 403
        login(client, "studio-bob")
        first = client.post(f"{API}/projects/app_compiled/approve", json={"expected_revision": revision, "scope": scope})
        warnings = first.json()["error"]["details"]["finding_ids"] if first.status_code == 422 else []
        done = client.post(f"{API}/projects/app_compiled/approve", json={"expected_revision": revision, "scope": scope, "acknowledged_warnings": warnings})
        assert done.status_code == 200, done.text
        assert done.json()["approvals"][-1]["approved_by"] == "studio-bob", "the record names the real approver, not the project's owner"
        login(client, "studio-alice")
        return done.json()
    approved = approve(1, "process")
    generated = client.post(f"{API}/projects/app_compiled/frontend/generate", json={"expected_revision": approved["revision"]}).json()["definition"]
    final = approve(generated["revision"], "design")

    compiled = client.get(f"{API}/projects/app_compiled/compile").json()
    assert compiled["status"] == "generated", compiled["plan"]["reasons"]
    assert compiled["manifest"]["project_revision"] == final["revision"]
    assert all(check["status"] != "fail" for check in compiled["checks"])
    shown = client.get(f"{API}/projects/app_compiled/compile/file", params={"path": "design/relationships.json"})
    assert shown.status_code == 200 and "rel_order_ordered_by_customer" in shown.text
    assert client.get(f"{API}/projects/app_compiled/compile/file", params={"path": "../../etc/passwd"}).status_code == 404
    archive = client.get(f"{API}/projects/app_compiled/compile/archive")
    assert archive.status_code == 200
    with ZipFile(BytesIO(archive.content)) as zipped:
        names = set(zipped.namelist())
        assert all(not name.startswith(("/", "..")) and ".." not in name.split("/") for name in names)
        assert {"generation-manifest.json", "src/generated/relationships.ts", "design/forms.json", "design/specification.json"} <= names
        manifest = json.loads(zipped.read("generation-manifest.json"))
        assert all(sha256(zipped.read(path)).hexdigest() == entry["sha256"] for path, entry in manifest["files"].items())
        _run_generated_checks(zipped)  # compiles the TypeScript and runs both generated test files

    # requirement → step → operation → generated file, explained hop by hop
    deps = client.get(f"{API}/projects/app_compiled/dependencies", params={"start": "requirement:req_eco_order", "kinds": "file", "depth": 4}).json()
    files = {item["node"]["id"]: item for item in deps["results"]}
    assert "file:api/openapi.json" in files and files["file:api/openapi.json"]["hops"][0]["type"] == "SATISFIED_BY"
    from_domain = client.get(f"{API}/projects/app_compiled/dependencies", params={"start": "domain:noordveld_machinery@1.1.0/order", "kinds": "file", "depth": 3}).json()
    assert "file:schemas/dk_order.schema.json" in {item["node"]["id"] for item in from_domain["results"]}

    # safe regeneration plan against the exported workspace
    current = {path: entry["sha256"] for path, entry in manifest["files"].items()}
    current["design/forms.json"] = "0" * 64  # a person edited a generated file
    plan = client.post(f"{API}/projects/app_compiled/compile/update-plan", json={"previous_manifest": manifest, "current_sha256": current}).json()
    assert plan["conflict_user_modified"] == ["design/forms.json"] and not plan["update"] and not plan["safe"]

    # a domain change: proposal, permission checks, impact, nothing applied to the project
    exported = json.loads(client.get(f"{DK}/packs/noordveld_machinery/versions/1.1.0/export").content)
    exported["version"] = "1.2.0"
    next(e for e in exported["entities"] if e["id"] == "order")["description"] = "Changed"
    body = {"format": "json", "content": json.dumps(exported)}
    dry = client.post(f"{DK}/import/dry-run", json=body).json()
    assert client.post(f"{DK}/import/apply", json={**body, "expected_sha256": dry["content_sha256"], "reason": "clarify"}).status_code == 200
    impact = client.get(f"{DK}/packs/noordveld_machinery/versions/1.2.0/impact").json()
    assert impact["projects"][0]["entities"] == ["dk_order"] and impact["projects"][0]["applied"] is False
    transition = f"{DK}/packs/noordveld_machinery/versions/1.2.0/transition"
    assert client.post(transition, json={"to": "approved", "reason": "x"}).json()["error"]["code"] == "domain_permission_required"
    login(client, "studio-erin")
    assert client.post(transition, json={"to": "approved", "reason": "reviewed"}).status_code == 200
    # Another organization's administrator cannot compile, inspect or download this project.
    login(client, "studio-gina")
    for path in ("/compile", "/compile/archive", "/dependencies?start=requirement:req_eco_order"):
        assert client.get(f"{API}/projects/app_compiled{path}", headers={"X-Org-Id": "org_harbor"}).status_code == 404
    login(client, "studio-alice")
    after = client.get(f"{API}/projects/app_compiled/compile").json()
    assert after["manifest"]["domain_packs"][0]["version"] == "1.1.0", "the project still compiles from what it adopted"
    assert after["status"] == "generated" and any(i["code"] == "PACK_NEWER_VERSION" for i in after["resolution"]["issues"])
    # Re-adopting is an explicit edit: it is a new revision, so the design approval becomes stale.
    stale = deepcopy(after["specification"])
    assert stale["approval"]["design"] == "valid"


# ── TMS / WMS on the shared model ──







