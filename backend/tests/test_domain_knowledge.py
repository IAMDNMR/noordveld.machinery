"""Domain knowledge foundation: schema integrity, provenance, import/export, governance, graph contract and Design Studio adoption.

Synthetic fixtures and temporary SQLite only. No test connects to Neo4j or any external service.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.design_studio.completeness import analyze as analyze_design
from app.design_studio.discovery import blank_definition
from app.design_studio.knowledge.provider import get_knowledge_provider, stale_items
from app.design_studio.local_app import create_local_app
from app.domain_knowledge import graph, importer
from app.domain_knowledge.adoption import AdoptionConflict, adopt, overrides, suggest
from app.domain_knowledge.models import DomainPack
from app.domain_knowledge.packs import canonical_bytes, content_sha256, shipped_packs
from app.domain_knowledge.repository import KnowledgeIndex
from app.domain_knowledge.store import GovernanceError, ReadOnlyDomainStore, SqliteDomainStore, StoreUnavailable, VersionConflict, active
from app.domain_knowledge.validation import analyze

ROOT = Path(__file__).resolve().parents[1]
PROV = {"kind": "synthetic", "reference": "test fixture", "verification": "unverified"}



def _latest(pack_id: str = "noordveld_machinery") -> DomainPack:
    return max((item for item in shipped_packs() if item.id == pack_id), key=lambda item: tuple(int(part) for part in item.version.split(".")))


def frozen_1_0_0() -> DomainPack:
    return next(item for item in shipped_packs() if item.id == "noordveld_machinery" and item.version == "1.0.0")

def noordveld() -> DomainPack:
    return _latest()


def tiny(**changes) -> dict:
    """A minimal synthetic pack used to exercise validation edges."""
    raw = {"id": "test_pack", "version": "1.1.0", "title": "Test", "synthetic": True,
           "domains": [{"id": "dom_a", "name": "A", "description": "a", "provenance": PROV}],
           "concepts": [{"id": "concept_part", "canonical_name": "Part", "kind": "business_concept", "domain_id": "dom_a", "definition": "A part.", "provenance": PROV}],
           "entities": [{"id": "part", "canonical_name": "Part", "domain_id": "dom_a", "concept_id": "concept_part", "description": "A part.", "natural_keys": ["part_id"],
                         "attributes": [{"id": "part_id", "name": "Part id", "type": "string", "required": True, "key": True}], "provenance": PROV},
                        {"id": "machine", "canonical_name": "Machine", "domain_id": "dom_a", "description": "A machine.", "natural_keys": ["machine_id"],
                         "attributes": [{"id": "machine_id", "name": "Machine id", "type": "string", "required": True, "key": True}], "provenance": PROV}],
           "relationships": [{"id": "rel_fits", "source_id": "part", "type": "FITS", "target_id": "machine", "cardinality": "many_to_many", "meaning": "Fits.", "provenance": PROV}]}
    raw.update(changes)
    return raw


@pytest.fixture
def store(tmp_path: Path) -> SqliteDomainStore:
    return SqliteDomainStore(tmp_path / "domain.sqlite")


# ── schema and integrity ──













# ── repository queries ──



# ── import / export / versioning / governance ──









# ── graph contract (no connection) ──





# ── Design Studio integration ──



# ── API (isolated local app, temporary SQLite) ──

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


def test_api_journey_explore_import_govern_adopt_and_impact(client):
    api = "/api/v1/domain-knowledge"
    assert client.get(f"{api}/domains").status_code == 401
    login(client, "studio-alice")
    domains = client.get(f"{api}/domains").json()
    assert domains["pack"]["id"] == "noordveld_machinery" and len(domains["domains"]) == 12
    assert client.get(f"{api}/entities/part").json()["entity"]["operational_label"] == "Part"
    assert client.get(f"{api}/entities/nope").status_code == 404
    assert client.get(f"{api}/search", params={"q": "depot"}).json()[0]["entity_id"] == "warehouse"
    assert client.get(f"{api}/path", params={"source": "order", "target": "part"}).json()["connected"]
    status = client.get(f"{api}/graph-provider").json()
    assert status["mode"] == "disabled" and status["collisions_with_operational_graph"] == []

    exported = client.get(f"{api}/packs/noordveld_machinery/versions/1.1.0/export")
    assert exported.status_code == 200 and exported.content == canonical_bytes(noordveld())
    raw = json.loads(exported.content)
    raw["version"] = "1.2.0"
    raw["concepts"].append({"id": "concept_backorder_note", "canonical_name": "Backorder note", "kind": "business_concept", "domain_id": "dom_procurement",
                            "definition": "Free-text note on a supplier backorder.", "provenance": {"kind": "assumption", "reference": "test", "verification": "unverified"}})
    body = {"format": "json", "content": json.dumps(raw)}
    dry = client.post(f"{api}/import/dry-run", json=body).json()
    assert dry["valid"] and dry["summary"]["added"] == 1
    assert client.post(f"{api}/import/apply", json={**body, "expected_sha256": dry["content_sha256"], "reason": ""}).status_code == 422
    applied = client.post(f"{api}/import/apply", json={**body, "expected_sha256": dry["content_sha256"], "reason": "Add a concept"})
    assert applied.status_code == 200 and applied.json()["proposal"]["status"] == "under_review"
    transition = f"{api}/packs/noordveld_machinery/versions/1.2.0/transition"
    assert client.post(transition, json={"to": "approved", "reason": "mine"}).status_code == 403
    login(client, "studio-bob")  # a business approver in a customer organization holds no domain permission
    assert client.post(transition, json={"to": "approved", "reason": "reviewed"}).json()["error"]["code"] == "domain_permission_required"
    login(client, "studio-erin")
    assert client.post(transition, json={"to": "approved", "reason": "reviewed"}).json()["status"] == "approved"
    assert client.get(f"{api}/packs").json()["active"] == [{"id": "noordveld_machinery", "version": "1.2.0"}]
    compared = client.get(f"{api}/packs/noordveld_machinery/compare", params={"base": "1.1.0", "target": "1.2.0"}).json()
    assert compared["compatibility"]["level"] == "additive"

    login(client, "studio-alice")
    adopted = client.post(f"{api}/adopt", json={"definition": blank_definition().model_dump(mode="json"), "entity_ids": ["order", "order_line"]}).json()
    project = client.post("/api/v1/design-studio/projects", json=adopted["definition"])
    assert project.status_code == 200, project.text
    analysis = client.get(f"/api/v1/design-studio/projects/{project.json()['id']}/analysis").json()
    assert not any(item["code"] == "KNOWLEDGE_STALE" for item in analysis["process"]["findings"]), "adopted from the active 1.1.0, judged against the same store"
    hits = client.get(f"{api}/impact/order").json()
    assert hits["project_storage"] == "available" and hits["projects"][0]["entities"] == ["dk_order"]
    assert client.post(f"{api}/adopt", json={"definition": blank_definition().model_dump(mode="json"), "entity_ids": ["ghost"]}).status_code == 404






