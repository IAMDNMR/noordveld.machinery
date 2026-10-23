"""Design Studio routes; draft persistence disabled by default."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from app.api.dependencies import CurrentUser
from app.core.config import get_settings
from app.core.demo_access import studio_demo_request
from app.core.session import verify
from app.design_studio import approval
from app.design_studio.completeness import analyze
from app.design_studio.discovery import blank_definition, discover
from app.design_studio.knowledge.provider import (
    KnowledgeProvider,
    PackConflict,
    PackUnavailable,
    apply_pack,
    get_knowledge_provider,
)
from app.design_studio.process import is_business_aware
from app.design_studio.service import (
    TEMPLATES,
    export_zip,
    requirement_plan,
    starter_from_request,
    template,
)
from app.design_studio.codegen import archive_files, generate_archive, zip_files
from app.design_studio.compiler import compile_project, project_graph, update_plan
from app.domain_knowledge.store import DomainStore, get_domain_store
from app.design_studio.projects import DisabledProjectStore, ProjectStore, RevisionConflict
from app.design_studio.store import (
    DisabledDraftStore,
    DraftForbidden,
    DraftMissing,
    DraftStore,
    StorageCorrupt,
    StorageNotConfigured,
)
from app.design_studio.diff import compare, invalidating_changes
from app.design_studio.record_validation import entity_rules, validate_record
from app.design_studio.traceability import impact, report
from app.schemas.design_studio import (
    DesignDraftRequest,
    DesignGenerateRequest,
    DesignGenerateResponse,
    ScreenSpec,
)
from app.schemas.application_definition import (
    ApplicationDefinition,
    ApprovalRecord,
    WorkflowDefinition,
)
from app.orgs.directory import OrgDirectory, get_org_directory
from app.orgs.audited import AuditedRoute
from app.orgs.permissions import PERMISSION_CAPABILITY
from app.services.orders import User
from pydantic import BaseModel, Field


def require_studio_identity(request: Request) -> None:
    """Until an approved IdP is integrated, demo identity is local-only, or the explicit public demo switch (anonymous visitors)."""
    if not studio_demo_request(request):
        raise HTTPException(
            503,
            detail={
                "code": "trusted_identity_unavailable",
                "message": "Design Studio requires verified sign-in in this environment.",
            },
        )


def _required_permission(method: str, path: str) -> str:
    if method == "POST" and path.endswith("/frontend/generate"):
        return "studio.edit"
    if path.endswith("/approve"):
        return "studio.approve"
    if method == "POST" and path.endswith(("/runtime/launch", "/runtime/stop")):
        return "app.launch"
    if method == "POST" and path.endswith(("/runtime/test", "/releases")):
        return "studio.generate"
    if "/releases/" in path and path.endswith("/archive"):
        return "studio.generate"
    if path.endswith(("/compile/archive", "/export")) and method == "GET":
        return "studio.generate"
    if method in ("GET", "HEAD"):
        return "studio.use"
    if method == "POST" and path.endswith("/projects"):
        return "project.create"
    if method == "POST" and any(
        path.endswith(tail)
        for tail in (
            "/assistant",
            "/validate",
            "/analyze",
            "/analysis",
            "/intake",
            "/generate",
            "/discovery",
            "/validate-record",
            "/export",
            "/compile/update-plan",
            "/knowledge/apply",
            "/application-definition/validate",
            "/application-definition/analyze",
            "/application-definition/export",
            "/voice/transcribe",
            "/voice/speak",
        )
    ):
        return "studio.use"  # computes an answer; stores nothing
    return "studio.edit"


def _action_name(path: str) -> str:
    for tail, name in (
        ("/approve", "approve"),
        ("/runtime/launch", "launch"),
        ("/runtime/test", "test"),
        ("/runtime/stop", "stop"),
        ("/studio/apply", "apply"),
        ("/studio/revert", "revert"),
        ("/studio/resolve", "resolve"),
        ("/knowledge/apply", "adopt_knowledge"),
    ):
        if path.endswith(tail):
            return name
    return "create_project" if path.endswith("/projects") else "operate"


SENSITIVE_TAILS = (
    "/frontend/generate",
    "/releases",
    "/approve",
    "/runtime/launch",
    "/runtime/test",
    "/runtime/stop",
    "/studio/apply",
    "/studio/revert",
    "/studio/resolve",
    "/knowledge/apply",
)


def studio_gate(
    request: Request,
    user: CurrentUser,
    directory: Annotated[OrgDirectory, Depends(get_org_directory)],
) -> None:
    """Organization-scoped authorization. Without a configured directory (local demo mode only, behind require_studio_identity)
    the older owner-only rules apply; with one, the user needs the permission in the active organization, and a project must
    belong to that organization. Platform roles add nothing here: a platform administrator is not a member of a customer's organization."""
    if not directory.configured:
        return
    memberships = directory.organizations_of(user.id)
    org = (
        request.headers.get("x-org-id")
        or request.query_params.get("org")
        or (memberships[0]["id"] if len(memberships) == 1 else None)
    )
    if org is None:
        raise HTTPException(
            400,
            detail={
                "code": "organization_required",
                "message": "Choose an organization (X-Org-Id) for Design Studio.",
            },
        )
    needed = _required_permission(request.method, request.url.path)
    if needed not in directory.permissions(user.id, org) or not directory.roles(user.id, org):
        directory.record(
            user.id,
            "access.denied",
            org,
            f"{request.method} {request.url.path}: needs {needed}",
            target=request.path_params.get("project_id"),
            outcome="denied",
        )
        raise HTTPException(
            403,
            detail={
                "code": "studio_permission_required",
                "message": f"Your role in this organization does not include {needed}.",
            },
        )
    project_id = request.path_params.get("project_id")
    if project_id is not None:
        if directory.project_org(project_id) != org:
            raise HTTPException(
                404,
                detail={
                    "code": "project_not_found",
                    "message": "No such project in this organization.",
                },
            )
        # Project-level access, on top of the organization permission. A person with no access at all gets the same answer as for a
        # project that does not exist, so identifiers cannot be probed; a person with some access but not this capability is told why.
        capability = PERMISSION_CAPABILITY.get(needed)
        held = directory.project_capabilities(user.id, org, project_id)
        if capability is not None and not held:
            directory.record(
                user.id,
                "access.denied",
                org,
                f"{request.method} {request.url.path}: no access to the project",
                target=project_id,
                outcome="denied",
            )
            raise HTTPException(
                404,
                detail={
                    "code": "project_not_found",
                    "message": "No such project in this organization.",
                },
            )
        if capability is not None and capability not in held:
            directory.record(
                user.id,
                "access.denied",
                org,
                f"{request.method} {request.url.path}: needs {capability} on the project",
                target=project_id,
                outcome="denied",
            )
            raise HTTPException(
                403,
                detail={
                    "code": "project_access_required",
                    "message": f"Your access to this project does not include {capability}. Ask a project owner.",
                },
            )
    if request.method == "POST" and (
        request.url.path.endswith(SENSITIVE_TAILS) or request.url.path.endswith("/projects")
    ):
        # Marked here, recorded with its outcome by AuditedRoute once the handler has finished (a refusal or failure is never logged as a success).
        request.state.audit_pending = {
            "directory": directory,
            "actor": user.id,
            "org": org,
            "action": "studio." + _action_name(request.url.path),
            "target": project_id,
            "detail": f"{needed} {request.url.path}",
        }
    request.state.org_id = org


def project_user(
    request: Request,
    user: CurrentUser,
    directory: Annotated[OrgDirectory, Depends(get_org_directory)],
) -> User:
    """For a project routed through an organization: the user whose private store the project lives in (its creator), so that
    members with permission can reach it. The real acting user is still `CurrentUser` where it matters (approvals, audit)."""
    project_id = request.path_params.get("project_id")
    if directory.configured and project_id is not None:
        owner = directory.project_creator(project_id)
        if owner is not None:
            return replace(user, id=owner)
    return user


ProjectUser = Annotated[User, Depends(project_user)]


def limit_visitors(
    request: Request, nv_studio_session: Annotated[str | None, Cookie(alias="nv_studio_session")] = None
) -> None:
    """Public demo only: bound the requests that cost money (language model, speech, code generation) per visitor and per instance."""
    from app.core.demo_access import public_studio_enabled

    if not public_studio_enabled() or request.method != "POST":
        return
    from app.design_studio.visitors import EXPENSIVE_SUFFIXES, check_rate, is_visitor

    visitor = verify(nv_studio_session, "studio:" + get_settings().session_secret)
    if is_visitor(visitor) and request.url.path.endswith(EXPENSIVE_SUFFIXES):
        check_rate(visitor)


def deployed_without_processes(request: Request) -> None:
    """Launching or testing a generated application starts local processes, which a serverless deployment cannot do."""
    import os

    if os.environ.get("VERCEL") and request.method == "POST" and request.url.path.endswith(("/runtime/launch", "/runtime/test", "/runtime/stop")):
        raise HTTPException(
            409,
            detail={"code": "runtime_local_only", "message": "Running a generated application is available when the Studio runs locally. Download the application to run it."},
        )


router = APIRouter(
    prefix="/design-studio",
    tags=["design-studio"],
    dependencies=[
        Depends(require_studio_identity),
        Depends(studio_gate),
        Depends(limit_visitors),
        Depends(deployed_without_processes),
    ],
    route_class=AuditedRoute,
)


def get_design_store() -> DraftStore:
    from app.design_studio.postgres_activation import configured_stores

    stores = configured_stores()
    if stores is not None:
        return stores[0]
    return DisabledDraftStore()


Store = Annotated[DraftStore, Depends(get_design_store)]


def get_project_store() -> ProjectStore:
    from app.design_studio.postgres_activation import configured_stores

    stores = configured_stores()
    if stores is not None:
        from app.core.demo_access import public_studio_enabled

        if public_studio_enabled():
            from app.design_studio.visitors import LimitedProjects

            return LimitedProjects(stores[1])
        return stores[1]
    return DisabledProjectStore()


Projects = Annotated[ProjectStore, Depends(get_project_store)]
Knowledge = Annotated[KnowledgeProvider, Depends(get_knowledge_provider)]
DomainPacks = Annotated[DomainStore, Depends(get_domain_store)]


class ProjectUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    definition: ApplicationDefinition


class IntakeRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)


class ApplyPackRequest(BaseModel):
    pack_id: str = Field(min_length=1, max_length=80)
    definition: ApplicationDefinition


class DiscoveryRequest(BaseModel):
    definition: ApplicationDefinition
    brief_text: str | None = Field(default=None, max_length=4000)


class ApproveRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    scope: Literal["process", "design"]
    acknowledged_warnings: list[str] = Field(default_factory=list, max_length=500)
    comment: str = Field(default="", max_length=1000)


class RecordCheck(BaseModel):
    entity_id: str = Field(min_length=1, max_length=80)
    record: dict[str, str | int | float | bool | None] = Field(max_length=200)
    mode: Literal["create", "update"] = "create"


class GenerateRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class UpdatePlanRequest(BaseModel):
    previous_manifest: dict | None = None
    current_sha256: dict[str, str] = Field(default_factory=dict, max_length=2000)


def _error(status: int, code: str, message: str, details: object = None) -> HTTPException:
    detail: dict = {"code": code, "message": message}
    if details is not None:
        detail["details"] = details
    return HTTPException(status, detail=detail)


def _store_call(method, *args):
    try:
        return method(*args)
    except StorageNotConfigured:
        raise HTTPException(
            503,
            detail={
                "code": "draft_storage_unavailable",
                "message": "Draft storage is not configured. Export your mockup to keep a copy.",
            },
        ) from None
    except StorageCorrupt:
        raise HTTPException(
            503,
            detail={
                "code": "design_storage_error",
                "message": "Saved design storage failed validation. No data was changed.",
            },
        ) from None
    except DraftMissing:
        raise HTTPException(
            404, detail={"code": "draft_not_found", "message": "Draft not found."}
        ) from None
    except DraftForbidden:
        raise HTTPException(
            403,
            detail={"code": "draft_forbidden", "message": "This draft belongs to another user."},
        ) from None
    except RevisionConflict:
        raise HTTPException(
            409,
            detail={
                "code": "revision_conflict",
                "message": "The project has a newer revision or the ID is already in use.",
            },
        ) from None


def _current_at(
    projects: ProjectStore, owner: str, project_id: str, expected_revision: int
) -> ApplicationDefinition:
    current = _store_call(projects.current, owner, project_id)
    if current.revision != expected_revision:
        raise _error(
            409,
            "revision_conflict",
            "The project has a newer revision. Reload it before continuing.",
        )
    return current


@router.get("/templates")
def templates(_: CurrentUser) -> list[dict[str, str]]:
    return [{"id": item[0], "name": item[1]} for item in TEMPLATES]


@router.get("/templates/{template_id}", response_model=ScreenSpec)
def get_template(template_id: str, _: CurrentUser):
    spec = template(template_id)
    if spec is None:
        raise HTTPException(
            404, detail={"code": "template_not_found", "message": "Template not found."}
        )
    return spec


@router.post("/generate", response_model=DesignGenerateResponse)
def generate(body: DesignGenerateRequest, _: CurrentUser):
    if body.provider is not None:
        raise HTTPException(
            503,
            detail={
                "code": "model_unavailable",
                "message": "Design Studio model access is not configured.",
            },
        )
    return DesignGenerateResponse(
        spec=starter_from_request(body.message, body.current_spec),
        assistant_message="This is a deterministic starter, not an AI-generated design. Review fields and validation.",
        provider="local",
        model="starter-1",
    )


@router.post("/intake")
def intake(body: IntakeRequest, _: CurrentUser, knowledge: Knowledge):
    plan = requirement_plan(body.message)
    draft, domains = discover(blank_definition(), knowledge, body.message)
    plan["questions"] = [question.text for question in draft.business.questions]
    plan["domain_suggestions"] = domains
    return plan


# ── domain knowledge and discovery (pure: nothing is stored) ──


@router.get("/knowledge/domains")
def knowledge_domains(_: CurrentUser, knowledge: Knowledge):
    return [domain.model_dump(mode="json") for domain in knowledge.domains()]


@router.get("/knowledge/packs")
def knowledge_packs(_: CurrentUser, knowledge: Knowledge):
    return [
        {
            "id": pack.id,
            "usage": pack.usage,
            "version": pack.version,
            "layer": pack.layer,
            "title": pack.title,
            "description": pack.description,
            "synthetic": pack.synthetic,
            "domain_id": pack.domain_id,
            "depends_on": pack.depends_on,
            "counts": {
                group: len(getattr(pack.business, group))
                for group in (
                    "requirements",
                    "roles",
                    "entities",
                    "rules",
                    "exceptions",
                    "decisions",
                    "integrations",
                    "terms",
                )
            }
            | {"workflows": len(pack.workflows)},
        }
        for pack in knowledge.packs()
    ]


@router.get("/knowledge/packs/{pack_id}")
def knowledge_pack(pack_id: str, _: CurrentUser, knowledge: Knowledge):
    try:
        return knowledge.pack(pack_id).model_dump(mode="json")
    except PackUnavailable:
        raise _error(404, "pack_not_found", "Reference pack not found.") from None


@router.post("/knowledge/apply")
def knowledge_apply(body: ApplyPackRequest, _: CurrentUser, knowledge: Knowledge):
    try:
        definition, added = apply_pack(body.definition, body.pack_id, knowledge)
    except PackUnavailable:
        raise _error(404, "pack_not_found", "Reference pack not found.") from None
    except PackConflict as exc:
        raise _error(
            409,
            "pack_conflict",
            "Some reference items use IDs that already exist in this design. Nothing was applied.",
            {"ids": exc.ids},
        ) from None
    return {"definition": definition.model_dump(mode="json"), "added": added}


@router.post("/discovery")
def discovery(body: DiscoveryRequest, _: CurrentUser, knowledge: Knowledge):
    definition, domains = discover(body.definition, knowledge, body.brief_text)
    return {
        "definition": definition.model_dump(mode="json"),
        "domain_suggestions": domains,
        "mode": "deterministic_rules",
    }


# ── unsaved definitions ──


@router.post("/drafts")
def save_draft(body: DesignDraftRequest, user: CurrentUser, store: Store):
    return _store_call(store.save, user.id, body.spec)


@router.get("/drafts")
def list_drafts(user: CurrentUser, store: Store):
    return _store_call(store.list, user.id)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str, user: CurrentUser, store: Store):
    return _store_call(store.get, user.id, draft_id)


@router.put("/drafts/{draft_id}")
def update_draft(draft_id: str, body: DesignDraftRequest, user: CurrentUser, store: Store):
    return _store_call(store.save, user.id, body.spec, draft_id, body.expected_revision)


@router.post("/export")
def export(body: DesignDraftRequest, _: CurrentUser):
    return Response(
        export_zip(body.spec),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="noordveld-screen.zip"'},
    )


@router.post("/application-definition/validate")
def validate_application(body: ApplicationDefinition, _: CurrentUser):
    return {"valid": True, "definition": body.model_dump(mode="json")}


@router.post("/application-definition/analyze")
def analyze_application(body: ApplicationDefinition, _: CurrentUser, knowledge: Knowledge):
    return {
        "process": analyze(body, knowledge, "process"),
        "design": analyze(body, knowledge, "design"),
        "traceability": report(body),
        "approval": approval.status(body),
        "note": "Approval shown here is computed from the submitted definition; only the saved project's approval is authoritative.",
    }


@router.post("/workflow/validate")
def validate_workflow(body: WorkflowDefinition, _: CurrentUser):
    return {"valid": True, "workflow": body.model_dump(mode="json")}


@router.post("/application-definition/export")
def export_application(body: ApplicationDefinition, _: CurrentUser):
    if is_business_aware(body):
        # An unsaved definition's approval cannot be trusted; business designs export only from an approved saved project.
        raise _error(
            409,
            "approval_required",
            "Save the project and approve its design, then export it from the saved project.",
        )
    return Response(
        generate_archive(body),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="noordveld-application-mockup.zip"'},
    )


# ── saved projects ──


@router.post("/projects")
def create_project(
    request: Request,
    body: ApplicationDefinition,
    user: CurrentUser,
    projects: Projects,
    directory: Annotated[OrgDirectory, Depends(get_org_directory)],
):
    # Approvals are written only by the approve endpoint; a client cannot create one.
    if directory.configured and directory.project_org(body.id) not in (None, request.state.org_id):
        raise _error(
            409,
            "revision_conflict",
            "The project has a newer revision or the ID is already in use.",
        )
    saved = _store_call(
        projects.create,
        user.id,
        body.model_copy(
            update={
                "approvals": [],
                "studio_flow": None,
                "assistant_context": None,
                "project_lifecycle": None,
                "generated_frontend": None,
                "frontend_required": True,
            }
        ),
    )
    if directory.configured:
        directory.register_project(saved.id, request.state.org_id, user.id)
    return saved


@router.get("/projects")
def list_projects(
    request: Request,
    user: CurrentUser,
    projects: Projects,
    directory: Annotated[OrgDirectory, Depends(get_org_directory)],
    include_inactive: bool = False,
):
    if directory.configured:
        # Only the projects this person may open: the listing is access-controlled like every other project route (an unassigned project is not even named).
        visible = []
        for entry in directory.projects_visible_to(user.id, request.state.org_id):
            try:
                visible.append(
                    _store_call(projects.current, entry["created_by"], entry["project_id"])
                )
            except HTTPException as error:
                # Deletion receipts reserve the ID; the directory's historical
                # registration is retained for audit, without a discoverable app.
                if error.status_code == 404:
                    continue
                raise
    else:
        visible = _store_call(projects.list, user.id)
    return [
        project
        for project in visible
        if include_inactive
        or not project.project_lifecycle
        or project.project_lifecycle.status == "active"
    ]


@router.get("/projects/{project_id}")
def get_project(project_id: str, user: ProjectUser, projects: Projects):
    return _store_call(projects.current, user.id, project_id)


@router.put("/projects/{project_id}")
def update_project(
    project_id: str, body: ProjectUpdate, user: ProjectUser, actor: CurrentUser, projects: Projects
):
    current = _store_call(projects.current, user.id, project_id)
    # Keep the stored approval records; an edit makes them stale through their digests, never by client choice.
    definition = body.definition.model_copy(
        update={
            "approvals": current.approvals,
            "studio_flow": current.studio_flow,
            "assistant_context": current.assistant_context,
            "project_lifecycle": current.project_lifecycle,
            "generated_frontend": current.generated_frontend,
            "frontend_required": current.frontend_required,
        }
    )
    return _store_call(
        projects.update, user.id, project_id, body.expected_revision, definition, "update", actor.id
    )


@router.get("/projects/{project_id}/history")
def project_history(project_id: str, user: ProjectUser, projects: Projects):
    return _store_call(projects.history, user.id, project_id)


class ConversationRequest(BaseModel):
    model_config = {"extra": "forbid"}
    message: str = Field(min_length=1, max_length=4000)
    expected_revision: int = Field(ge=1)
    base_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ApplyConversationRequest(ConversationRequest):
    candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.get("/projects/{project_id}/assistant/context")
def conversation_context(project_id: str, user: ProjectUser, projects: Projects):
    from app.assistant.providers import get_assistant, get_speech

    current = _store_call(projects.current, user.id, project_id)
    return {
        "revision": current.revision,
        "base_sha256": approval.digest(current, "design"),
        "mode": "local_rules",
        "assistant": get_assistant().status(),
        "speech": get_speech().status(),
        "domain_releases": current.business.knowledge.model_dump(mode="json")
        if hasattr(current.business.knowledge, "model_dump")
        else current.model_dump(mode="json")["business"]["knowledge"],
    }


def _conversation(project_id, body, user, projects):
    from app.assistant.design import respond

    current = _current_at(projects, user.id, project_id, body.expected_revision)
    if approval.digest(current, "design") != body.base_sha256:
        raise _error(
            409, "proposal_stale", "The saved content changed. Reload and review a fresh proposal."
        )
    try:
        result, candidate = respond(current, body.message)
    except ValueError:
        raise _error(
            422,
            "proposal_invalid",
            "This change does not fit the current schema or artifact limits. Use the process editor to review it.",
        ) from None
    return current, result, candidate


@router.post("/projects/{project_id}/assistant")
def project_conversation(
    project_id: str,
    body: ConversationRequest,
    user: ProjectUser,
    projects: Projects,
    knowledge: Knowledge,
):
    current, result, candidate = _conversation(project_id, body, user, projects)
    if candidate is not None:
        result["validation"] = analyze(candidate, knowledge, "process")
    elif body.message.strip().lower() in {"find missing validations", "show validation findings"}:
        checks = analyze(current, knowledge, "design")
        result.update(
            answer="These are the saved design's validation findings. Follow each remediation before approval.",
            detail=checks["findings"],
            validation=checks,
        )
    return result


@router.post("/projects/{project_id}/assistant/apply")
def apply_conversation(
    project_id: str,
    body: ApplyConversationRequest,
    user: ProjectUser,
    actor: CurrentUser,
    projects: Projects,
):
    _, result, candidate = _conversation(project_id, body, user, projects)
    if candidate is None or result["candidate_sha256"] != body.candidate_sha256:
        raise _error(
            409,
            "proposal_mismatch",
            "Review a supported proposal before applying it. Nothing was changed.",
        )
    # Recompute from authoritative content; the client cannot supply arbitrary patches or approval records.
    return _store_call(
        projects.update,
        user.id,
        project_id,
        body.expected_revision,
        candidate,
        "assistant:apply",
        actor.id,
    )


@router.get("/projects/{project_id}/analysis")
def project_analysis(project_id: str, user: ProjectUser, projects: Projects, knowledge: Knowledge):
    current = _store_call(projects.current, user.id, project_id)
    return {
        "revision": current.revision,
        "process": analyze(current, knowledge, "process"),
        "design": analyze(current, knowledge, "design"),
        "approval": approval.status(current),
    }


@router.get("/projects/{project_id}/traceability")
def project_traceability(project_id: str, user: ProjectUser, projects: Projects):
    current = _store_call(projects.current, user.id, project_id)
    return {"revision": current.revision, **report(current)}


@router.get("/projects/{project_id}/impact/{item_id}")
def project_impact(project_id: str, item_id: str, user: ProjectUser, projects: Projects):
    result = impact(_store_call(projects.current, user.id, project_id), item_id)
    if result is None:
        raise _error(404, "item_not_found", "No business item or process step has that ID.")
    return result


@router.post("/projects/{project_id}/approve")
def approve_project(
    project_id: str,
    body: ApproveRequest,
    user: ProjectUser,
    actor: CurrentUser,
    projects: Projects,
    knowledge: Knowledge,
    directory: Annotated[OrgDirectory, Depends(get_org_directory)],
):
    """Approve the exact current revision with a separate organization approver."""
    if directory.configured and directory.project_creator(project_id) == actor.id:
        raise _error(
            403,
            "separate_approver_required",
            "The person who created this project cannot approve it; another approver in the organization must.",
        )
    current = _current_at(projects, user.id, project_id, body.expected_revision)
    result = analyze(current, knowledge, body.scope)
    if result["blocking"]:
        errors = [item for item in result["findings"] if item["severity"] == "error"]
        raise _error(
            422,
            "design_incomplete",
            f"{len(errors)} blocking finding(s) must be resolved before approval.",
            {"findings": errors},
        )
    warnings = sorted(item["id"] for item in result["findings"] if item["severity"] == "warning")
    missing = [item for item in warnings if item not in set(body.acknowledged_warnings)]
    if missing:
        raise _error(
            422,
            "warnings_unacknowledged",
            f"{len(missing)} warning(s) must be acknowledged before approval.",
            {"finding_ids": missing},
        )
    record = ApprovalRecord(
        scope=body.scope,
        revision=current.revision + 1,
        content_sha256=approval.digest(current, body.scope),
        approved_by=actor.id,
        approved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        warnings_acknowledged=warnings,
        comment=body.comment.strip(),
    )
    approved = current.model_copy(
        update={
            "approvals": [item for item in current.approvals if item.scope != body.scope] + [record]
        }
    )
    return _store_call(
        projects.update,
        user.id,
        project_id,
        current.revision,
        approved,
        f"approve:{body.scope}",
        actor.id,
    )


@router.get("/projects/{project_id}/audit")
def project_audit(project_id: str, user: ProjectUser, projects: Projects):
    """Who changed the project, when, and how (edit, approval, generation). Revisions themselves are immutable."""
    return _store_call(projects.audit_trail, user.id, project_id)


def _revision(history: list[ApplicationDefinition], number: int) -> ApplicationDefinition:
    found = next((item for item in history if item.revision == number), None)
    if found is None:
        raise _error(404, "revision_not_found", f"Revision {number} does not exist.")
    return found


@router.get("/projects/{project_id}/compare")
def project_compare(
    project_id: str,
    user: ProjectUser,
    projects: Projects,
    base: int = Query(ge=1),
    target: int = Query(ge=1),
):
    history = _store_call(projects.history, user.id, project_id)
    return {
        "base": base,
        "target": target,
        "changes": compare(_revision(history, base), _revision(history, target)),
    }


@router.get("/projects/{project_id}/approval-changes")
def project_approval_changes(project_id: str, user: ProjectUser, projects: Projects):
    """For each approval: the changes since the approved revision that make it stale (empty while it is valid)."""
    history = _store_call(projects.history, user.id, project_id)
    current = history[-1]
    result = {}
    for record in current.approvals:
        approved = _revision(history, record.revision)
        result[record.scope] = {
            "approved_revision": record.revision,
            "state": approval.status(current)[record.scope]["state"],
            "changes": invalidating_changes(approved, current, record.scope),
        }
    return result


@router.post("/projects/{project_id}/validate-record")
def project_validate_record(
    project_id: str, body: RecordCheck, user: ProjectUser, projects: Projects
):
    """Authoritative server validation of a record against the current specification's attribute rules."""
    current = _store_call(projects.current, user.id, project_id)
    entity = next((item for item in current.business.entities if item.id == body.entity_id), None)
    if entity is None:
        raise _error(404, "entity_not_found", "No entity has that ID in this project.")
    errors = validate_record(entity_rules(entity), body.record, body.mode)
    return {"valid": not errors, "errors": errors, "revision": current.revision}


@router.get("/projects/{project_id}/artifacts")
def project_artifacts(project_id: str, user: ProjectUser, projects: Projects, knowledge: Knowledge):
    """What an export of the current revision contains and how each file is classified; nothing is downloaded."""
    files = archive_files(_store_call(projects.current, user.id, project_id), knowledge)
    catalogue = (
        json.loads(files["design/artifacts.json"]) if "design/artifacts.json" in files else None
    )
    return {"catalogue": catalogue, "manifest": json.loads(files["manifest.json"])}


@router.get("/projects/{project_id}/export")
def export_project(project_id: str, user: ProjectUser, projects: Projects, knowledge: Knowledge):
    definition = _store_call(projects.current, user.id, project_id)
    if is_business_aware(definition) and not approval.is_valid(definition, "design"):
        raise _error(409, "approval_required", "Approve the current design before exporting it.")
    return Response(
        generate_archive(definition, knowledge),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="noordveld-application-mockup.zip"'},
    )


# ── Domain-to-application compilation ──


def _compiled(
    project_id: str, user, projects: ProjectStore, knowledge: KnowledgeProvider, domain: DomainStore
) -> tuple[ApplicationDefinition, dict]:
    definition = _store_call(projects.current, user.id, project_id)
    from app.design_studio.frontend_generation import FrontendGenerationError

    try:
        return definition, compile_project(definition, domain, knowledge)
    except FrontendGenerationError as exc:
        raise _error(409, "frontend_outdated", str(exc)) from None


def _summary(result: dict) -> dict:
    from app.design_studio.releases import fingerprint

    return {key: value for key, value in result.items() if key != "files"} | {
        "package_sha256": fingerprint(result["files"]),
        "files": {
            path: {
                "kind": result["manifest"]["files"].get(path, {}).get("kind", "manifest"),
                "bytes": len(data),
            }
            for path, data in sorted(result["files"].items())
        },
    }


@router.get("/projects/{project_id}/compile")
def compile_preview(
    project_id: str,
    user: ProjectUser,
    projects: Projects,
    knowledge: Knowledge,
    domain: DomainPacks,
):
    """Resolve, specify, plan, generate and check the current revision. Read-only: nothing is stored or written."""
    return _summary(_compiled(project_id, user, projects, knowledge, domain)[1])


@router.get("/projects/{project_id}/compile/file")
def compile_file(
    project_id: str,
    user: ProjectUser,
    projects: Projects,
    knowledge: Knowledge,
    domain: DomainPacks,
    path: str = Query(min_length=1, max_length=300),
):
    files = _compiled(project_id, user, projects, knowledge, domain)[1]["files"]
    if path not in files:
        raise _error(404, "file_not_found", "The compilation produces no file at that path.")
    return Response(files[path], media_type="text/plain; charset=utf-8")


@router.get("/projects/{project_id}/compile/archive")
def compile_archive(
    project_id: str,
    user: ProjectUser,
    projects: Projects,
    knowledge: Knowledge,
    domain: DomainPacks,
):
    """The generated application, only from an approved, unblocked revision whose checks pass."""
    _, result = _compiled(project_id, user, projects, knowledge, domain)
    if result["status"] != "generated":
        raise _error(
            409,
            "generation_blocked",
            "Generation is blocked for the current revision.",
            {
                "reasons": result["plan"]["reasons"],
                "failed_checks": [item for item in result["checks"] if item["status"] == "fail"],
            },
        )
    return Response(
        zip_files(result["files"]),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="noordveld-application.zip"'},
    )


@router.post("/projects/{project_id}/compile/update-plan")
def compile_update_plan(
    project_id: str,
    body: UpdatePlanRequest,
    user: ProjectUser,
    projects: Projects,
    knowledge: Knowledge,
    domain: DomainPacks,
):
    """How to apply this generation to an existing workspace without overwriting files a person changed."""
    _, result = _compiled(project_id, user, projects, knowledge, domain)
    return update_plan(body.previous_manifest, body.current_sha256, result["files"])


@router.get("/projects/{project_id}/dependencies")
def project_dependencies(
    project_id: str,
    user: ProjectUser,
    projects: Projects,
    knowledge: Knowledge,
    domain: DomainPacks,
    start: str = Query(min_length=1, max_length=300),
    direction: Literal["out", "in", "both"] = "out",
    depth: int = Query(default=4, ge=1, le=6),
    limit: int = Query(default=50, ge=1, le=200),
    kinds: str | None = Query(default=None, max_length=200),
):
    """Explained, bounded paths from one item (requirement:…, entity:…, step:…, domain:…) through the process to generated files."""
    definition, result = _compiled(project_id, user, projects, knowledge, domain)
    graph = project_graph(definition, result)
    try:
        return graph.reach(
            start,
            direction=direction,
            max_depth=depth,
            max_results=limit,
            kinds=set(kinds.split(",")) if kinds else None,
        )
    except KeyError:
        raise _error(
            404, "node_not_found", "No item has that ID in this project's dependency graph."
        ) from None


# The conversation, voice and live state of the voice-first workspace. Included last: it uses the helpers defined above.
from app.api.routes.studio_conversation import router as _conversation_router  # noqa: E402

router.include_router(_conversation_router)

from app.api.routes.studio_projects import router as _projects_router  # noqa: E402

router.include_router(_projects_router)

from app.api.routes.studio_releases import router as _releases_router  # noqa: E402

router.include_router(_releases_router)

from app.api.routes.studio_frontend import router as _frontend_router  # noqa: E402

router.include_router(_frontend_router)

from app.api.routes.studio_templates import router as _templates_router  # noqa: E402

router.include_router(_templates_router)
