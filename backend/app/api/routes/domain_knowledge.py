"""Domain knowledge routes: explore, search, trace, import (dry run, then proposal) and govern domain-pack versions.

Viewing and proposing are open to any signed-in Design Studio user; approval must come from a different person than
the proposer. Deployed environments have no approved store, so writes there return 503. Nothing here writes to Neo4j.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.dependencies import CurrentUser
from app.api.routes.design_studio import Projects, require_studio_identity
from app.design_studio.store import StorageNotConfigured
from app.domain_knowledge import importer
from app.domain_knowledge.adoption import AdoptionConflict, adopt, overrides, suggest
from app.domain_knowledge.graph import GraphDomainProvider, get_graph_provider
from app.domain_knowledge.packs import canonical_bytes
from app.domain_knowledge.repository import KnowledgeIndex
from app.domain_knowledge.traversal import pack_graph
from app.domain_knowledge.store import (
    TRANSITION_PERMISSION,
    PROPOSE,
    DomainAccess,
    DomainStore,
    GovernanceError,
    ReadOnlyDomainStore,
    StoreUnavailable,
    VersionConflict,
    VersionMissing,
    active,
    get_domain_access,
    get_domain_store,
)
from app.domain_knowledge.validation import analyze
from app.schemas.application_definition import ApplicationDefinition

router = APIRouter(
    prefix="/domain-knowledge",
    tags=["domain-knowledge"],
    dependencies=[Depends(require_studio_identity)],
)


Store = Annotated[DomainStore, Depends(get_domain_store)]
Access = Annotated[DomainAccess, Depends(get_domain_access)]
Graph = Annotated[GraphDomainProvider, Depends(get_graph_provider)]


def _error(status: int, code: str, message: str, details: object = None) -> HTTPException:
    detail: dict = {"code": code, "message": message}
    if details is not None:
        detail["details"] = details
    return HTTPException(status, detail=detail)


def _index(store: DomainStore, pack_id: str | None) -> KnowledgeIndex:
    packs = active(store)
    pack = next((item for item in packs if pack_id in (None, item.id)), None)
    if pack is None:
        raise _error(404, "pack_not_found", "No approved domain pack has that ID.")
    return KnowledgeIndex(pack)


def _get(store: DomainStore, pack_id: str, version: str):
    try:
        return store.get(pack_id, version)
    except VersionMissing:
        raise _error(404, "version_not_found", f"{pack_id} {version} does not exist.") from None


class ImportBody(BaseModel):
    format: Literal["json", "csv"]
    content: str = Field(min_length=2, max_length=2_000_000)
    csv_kind: Literal["concepts", "relationships"] | None = None
    pack_id: str | None = Field(default=None, max_length=80)
    base_version: str | None = Field(default=None, max_length=40)
    new_version: str | None = Field(default=None, max_length=40)


class ApplyBody(ImportBody):
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=1000)


class TransitionBody(BaseModel):
    to: Literal["under_review", "approved", "draft", "deprecated"]
    reason: str = Field(min_length=1, max_length=1000)


class SuggestBody(BaseModel):
    text: str = Field(min_length=2, max_length=4000)
    pack_id: str | None = Field(default=None, max_length=80)


class AdoptBody(BaseModel):
    definition: ApplicationDefinition
    entity_ids: list[str] = Field(min_length=1, max_length=60)
    pack_id: str | None = Field(default=None, max_length=80)
    include_required: bool = False


class OverridesBody(BaseModel):
    definition: ApplicationDefinition
    pack_id: str | None = Field(default=None, max_length=80)


@router.get("/packs")
def packs(_: CurrentUser, store: Store):
    return {
        "versions": store.versions(),
        "active": [{"id": pack.id, "version": pack.version} for pack in active(store)],
        "writable": not isinstance(store, ReadOnlyDomainStore),
    }


@router.get("/packs/{pack_id}/versions/{version}")
def pack_version(pack_id: str, version: str, _: CurrentUser, store: Store):
    pack = _get(store, pack_id, version)
    return {"pack": pack.model_dump(mode="json"), "analysis": analyze(pack)}


@router.get("/packs/{pack_id}/versions/{version}/export")
def export_pack(pack_id: str, version: str, _: CurrentUser, store: Store):
    pack = _get(store, pack_id, version)
    return Response(
        canonical_bytes(pack),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{pack.id}-{pack.version}.json"'},
    )


@router.get("/packs/{pack_id}/compare")
def compare_versions(
    pack_id: str,
    _: CurrentUser,
    store: Store,
    base: str = Query(max_length=40),
    target: str = Query(max_length=40),
):
    old, new = _get(store, pack_id, base), _get(store, pack_id, target)
    changes = importer.compare(old, new)
    return {
        "base": base,
        "target": target,
        "changes": changes,
        "compatibility": importer.compatibility(old, new, changes),
    }


@router.get("/packs/{pack_id}/audit")
def pack_audit(pack_id: str, _: CurrentUser, store: Store):
    return store.audit(pack_id)


def _require(access: DomainAccess, user_id: str, permission: str) -> None:
    if permission not in access(user_id):
        raise _error(
            403,
            "domain_permission_required",
            f"This needs the {permission} permission, which your account does not hold.",
        )


@router.get("/me")
def my_permissions(user: CurrentUser, access: Access, store: Store):
    return {
        "user_id": user.id,
        "permissions": sorted(access(user.id)),
        "store_writable": not isinstance(store, ReadOnlyDomainStore),
    }


@router.post("/packs/{pack_id}/versions/{version}/transition")
def transition(
    pack_id: str,
    version: str,
    body: TransitionBody,
    user: CurrentUser,
    store: Store,
    access: Access,
):
    if isinstance(store, ReadOnlyDomainStore):
        raise _error(
            503,
            "domain_store_unavailable",
            "Domain knowledge changes need a configured store; none is approved here.",
        )
    _require(access, user.id, TRANSITION_PERMISSION[body.to])
    if body.to == "approved":
        # Only a valid, compatible version may become active.
        candidate = _get(store, pack_id, version)
        current = next((pack for pack in active(store) if pack.id == pack_id), None)
        analysis = analyze(candidate)
        changes = importer.compare(current, candidate)
        compatibility = importer.compatibility(current, candidate, changes)
        if not analysis["activatable"] or not compatibility["ok"]:
            raise _error(
                409,
                "version_not_activatable",
                "This version cannot become active.",
                {"blocking": analysis["report"]["blocking"], "compatibility": compatibility},
            )
    try:
        return store.transition(pack_id, version, body.to, user.id, body.reason.strip())
    except StoreUnavailable:
        raise _error(
            503,
            "domain_store_unavailable",
            "Domain knowledge changes need a configured store; none is approved here.",
        ) from None
    except VersionMissing:
        raise _error(404, "version_not_found", f"{pack_id} {version} does not exist.") from None
    except GovernanceError as exc:
        raise _error(403, "governance_rejected", str(exc)) from None


def _parse(body: ImportBody, store: DomainStore):
    try:
        return importer.parse(
            body.format,
            body.content,
            store,
            body.csv_kind,
            body.pack_id,
            body.base_version,
            body.new_version,
        )
    except importer.ImportRejected as exc:
        raise _error(422, "import_rejected", str(exc)) from None


@router.post("/import/dry-run")
def import_dry_run(body: ImportBody, _: CurrentUser, store: Store):
    raw, normalizations = _parse(body, store)
    return importer.dry_run(raw, store, normalizations)


@router.post("/import/apply")
def import_apply(body: ApplyBody, user: CurrentUser, store: Store, access: Access):
    if isinstance(store, ReadOnlyDomainStore):
        raise _error(
            503,
            "domain_store_unavailable",
            "Domain knowledge changes need a configured store; none is approved here.",
        )
    _require(access, user.id, PROPOSE)
    raw, normalizations = _parse(body, store)
    try:
        return importer.apply(
            raw, store, user.id, body.reason, body.expected_sha256, normalizations
        )
    except importer.ImportRejected as exc:
        raise _error(422, "import_rejected", str(exc), exc.report) from None
    except StoreUnavailable:
        raise _error(
            503,
            "domain_store_unavailable",
            "Domain knowledge changes need a configured store; none is approved here.",
        ) from None
    except VersionConflict as exc:
        raise _error(409, "version_conflict", str(exc)) from None


@router.get("/domains")
def domains(_: CurrentUser, store: Store, pack: str | None = Query(default=None, max_length=80)):
    index = _index(store, pack)
    return {
        "pack": {
            "id": index.pack.id,
            "version": index.pack.version,
            "synthetic": index.pack.synthetic,
        },
        "domains": index.domains(),
        "decisions": [item.model_dump(mode="json") for item in index.pack.decisions],
        "analysis": analyze(index.pack),
    }


@router.get("/entities")
def entities(
    _: CurrentUser,
    store: Store,
    pack: str | None = Query(default=None, max_length=80),
    domain: str | None = Query(default=None, max_length=80),
):
    return _index(store, pack).entities_in(domain)


@router.get("/entities/{entity_id}")
def entity(
    entity_id: str,
    _: CurrentUser,
    store: Store,
    pack: str | None = Query(default=None, max_length=80),
):
    result = _index(store, pack).entity(entity_id)
    if result is None:
        raise _error(404, "entity_not_found", "No entity has that ID.")
    return result


@router.get("/search")
def search(
    _: CurrentUser,
    store: Store,
    q: str = Query(min_length=1, max_length=120),
    pack: str | None = Query(default=None, max_length=80),
):
    return _index(store, pack).search(q)


@router.get("/graph")
def graph(
    _: CurrentUser,
    store: Store,
    pack: str | None = Query(default=None, max_length=80),
    domain: str | None = Query(default=None, max_length=80),
    focus: str | None = Query(default=None, max_length=80),
    depth: int = Query(default=1, ge=0, le=3),
):
    return _index(store, pack).graph(domain, focus, depth)


@router.get("/path")
def path(
    _: CurrentUser,
    store: Store,
    source: str = Query(max_length=80),
    target: str = Query(max_length=80),
    pack: str | None = Query(default=None, max_length=80),
):
    result = _index(store, pack).path(source, target)
    if result is None:
        raise _error(404, "entity_not_found", "Both ends must be entities of the pack.")
    return {
        "source": source,
        "target": target,
        "hops": result,
        "connected": bool(result) or source == target,
    }


@router.get("/impact/{item_id}")
def impact(
    item_id: str,
    user: CurrentUser,
    store: Store,
    projects: Projects,
    pack: str | None = Query(default=None, max_length=80),
):
    index = _index(store, pack)
    try:
        owned = [(item.id, item) for item in projects.list(user.id)]
        storage = "available"
    except StorageNotConfigured:
        owned, storage = [], "not_configured"
    result = index.impact(item_id, owned)
    if result is None:
        raise _error(404, "item_not_found", "No pack item has that ID.")
    return {**result, "project_storage": storage}


@router.get("/graph-provider")
def graph_provider(
    _: CurrentUser,
    store: Store,
    provider: Graph,
    pack: str | None = Query(default=None, max_length=80),
):
    return provider.status(_index(store, pack).pack)


@router.post("/suggest")
def suggest_route(body: SuggestBody, _: CurrentUser, store: Store):
    return suggest(body.text, _index(store, body.pack_id))


@router.post("/adopt")
def adopt_route(body: AdoptBody, _: CurrentUser, store: Store):
    """Returns the updated definition for the editor to save with the project's normal revision check."""
    index = _index(store, body.pack_id)
    try:
        definition, report = adopt(
            body.definition, index.pack, body.entity_ids, body.include_required
        )
    except KeyError as exc:
        raise _error(404, "entity_not_found", f"Unknown entity: {exc.args[0]}") from None
    except AdoptionConflict as exc:
        raise _error(409, "adoption_conflict", str(exc), {"ids": exc.ids}) from None
    return {"definition": definition.model_dump(mode="json"), "report": report}


@router.post("/overrides")
def overrides_route(body: OverridesBody, _: CurrentUser, store: Store):
    index = _index(store, body.pack_id)
    return {
        "pack": {"id": index.pack.id, "version": index.pack.version},
        "overrides": overrides(body.definition, index.pack),
    }


@router.get("/traverse")
def traverse(
    _: CurrentUser,
    store: Store,
    start: str = Query(min_length=1, max_length=200),
    direction: Literal["out", "in", "both"] = "out",
    depth: int = Query(default=2, ge=1, le=6),
    limit: int = Query(default=50, ge=1, le=200),
    kinds: str | None = Query(default=None, max_length=200),
    pack: str | None = Query(default=None, max_length=80),
):
    """Bounded multi-hop traversal; every result carries the path that reaches it and why each hop holds."""
    graph = pack_graph(_index(store, pack).pack)
    try:
        return graph.reach(
            start,
            direction=direction,
            max_depth=depth,
            max_results=limit,
            kinds=set(kinds.split(",")) if kinds else None,
        )
    except KeyError:
        raise _error(404, "node_not_found", "No pack item has that ID.") from None


@router.get("/packs/{pack_id}/versions/{version}/impact")
def proposal_impact(
    pack_id: str, version: str, user: CurrentUser, store: Store, projects: Projects
):
    """What a version would change relative to the active one, and which of your projects use the changed items.

    Projects keep their adopted copies: nothing changes in them until someone re-adopts."""
    candidate = _get(store, pack_id, version)
    current = next((pack for pack in active(store) if pack.id == pack_id), None)
    changes = importer.compare(current, candidate)
    changed = {item["item_id"] for item in changes}
    if current is not None:
        for rel in current.relationships + candidate.relationships:
            if rel.id in changed:
                changed |= {rel.source_id, rel.target_id}
    try:
        owned = projects.list(user.id)
        storage = "available"
    except StorageNotConfigured:
        owned, storage = [], "not_configured"
    hits = []
    for definition in owned:
        entities = sorted(
            e.id
            for e in definition.business.entities
            if e.origin and e.origin.pack_id == pack_id and e.origin.item_id in changed
        )
        if entities:
            hits.append(
                {
                    "project_id": definition.id,
                    "revision": definition.revision,
                    "entities": entities,
                    "adopted_versions": sorted(
                        {
                            e.origin.pack_version
                            for e in definition.business.entities
                            if e.origin and e.origin.pack_id == pack_id
                        }
                    ),
                    "applied": False,
                }
            )
    return {
        "pack_id": pack_id,
        "version": version,
        "base_version": current.version if current else None,
        "changes": changes,
        "compatibility": importer.compatibility(current, candidate, changes),
        "projects": hits,
        "project_storage": storage,
        "note": "Projects keep the definitions they adopted. Nothing in them changes until someone re-adopts from an approved version.",
    }
