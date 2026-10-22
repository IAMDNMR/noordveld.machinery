"""Project dashboard and recoverable lifecycle controls, using the versioned project store."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import CurrentUser
from app.api.routes.design_studio import (
    ProjectUser,
    Projects,
    Knowledge,
    _current_at,
    _error,
    _store_call,
    list_projects,
)
from app.design_studio import approval, guided
from app.design_studio.completeness import analyze
from app.design_studio.stages import STAGES
from app.design_studio.runtime_launcher import manager
from app.orgs.directory import OrgDirectory, get_org_directory
from app.schemas.application_definition import ApplicationDefinition, ProjectLifecycle

router = APIRouter()


class ProjectAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    action: Literal["rename", "archive", "trash", "restore", "delete"]
    name: str | None = Field(default=None, min_length=1, max_length=120)


def project_status(project: ApplicationDefinition) -> Literal["active", "archived", "trashed"]:
    return project.project_lifecycle.status if project.project_lifecycle else "active"


@router.get("/project-dashboard")
def dashboard(
    request: Request,
    user: CurrentUser,
    projects: Projects,
    knowledge: Knowledge,
    directory: Annotated[OrgDirectory, Depends(get_org_directory)],
):
    visible = list_projects(request, user, projects, directory, include_inactive=True)
    release_store = getattr(request.app.state, "release_store", None)
    if release_store is None:
        from app.design_studio.postgres_activation import configured_release_store

        release_store = configured_release_store()
    rows, activity = [], []
    for project in visible:
        owner = directory.project_creator(project.id) if directory.configured else user.id
        events = _store_call(projects.audit_trail, owner, project.id)
        latest = events[-1] if events else {}
        current_stage = guided.active(project)
        reviewed_stages = guided.reviewed(project)
        approval_state = approval.status(project)["design"]["state"]
        findings = analyze(project, knowledge, "design")
        capabilities = (
            directory.project_capabilities(user.id, request.state.org_id, project.id)
            if directory.configured
            else {"edit"}
        )
        can_edit = "edit" in capabilities and (
            not directory.configured
            or "studio.edit" in directory.permissions(user.id, request.state.org_id)
        )
        rows.append(
            {
                "id": project.id,
                "name": project.metadata.name,
                "description": project.metadata.description,
                "domain": project.business.brief.domain_id or project.metadata.domain,
                "revision": project.revision,
                "status": project_status(project),
                "stage": current_stage,
                "stage_label": dict(STAGES)[current_stage],
                "reviewed": len(reviewed_stages),
                "design_reviewed": "roles" in reviewed_stages or approval_state == "valid",
                "stage_count": len(STAGES),
                "errors": findings["counts"]["error"],
                "warnings": findings["counts"]["warning"],
                "design_approval": approval_state,
                "screens": len(project.screens),
                "entities": len(project.business.entities),
                "updated_at": latest.get("at", ""),
                "can_edit": can_edit,
                "can_delete": can_edit
                and (not directory.configured or "manage" in capabilities)
                and callable(getattr(projects, "delete_permanently", None)),
                "runtime": manager.status(project.id, project.revision),
                "release": release_store.latest_summary(owner, project.id, project.revision)
                if release_store
                else None,
            }
        )
        activity.extend(
            {**event, "project_id": project.id, "project_name": project.metadata.name}
            for event in events
        )
    rows.sort(key=lambda row: row["updated_at"], reverse=True)
    activity.sort(key=lambda event: event.get("at", ""), reverse=True)
    active = [row for row in rows if row["status"] == "active"]
    return {
        "can_create": not directory.configured
        or "project.create" in directory.permissions(user.id, request.state.org_id),
        "projects": rows,
        "activity": activity[:12],
        "counts": {
            "active": len(active),
            "archived": sum(row["status"] == "archived" for row in rows),
            "trashed": sum(row["status"] == "trashed" for row in rows),
            "needs_attention": sum(
                row["errors"] > 0
                or (row.get("release") or {}).get("test_status") in ("failed", "interrupted")
                for row in active
            ),
            "approved": sum(row["design_approval"] == "valid" for row in active),
            "reviewed": sum(row["design_reviewed"] for row in active),
        },
    }


@router.post("/projects/{project_id}/manage")
def manage_project(
    request: Request,
    project_id: str,
    body: ProjectAction,
    user: ProjectUser,
    actor: CurrentUser,
    projects: Projects,
    directory: Annotated[OrgDirectory, Depends(get_org_directory)],
):
    current = _current_at(projects, user.id, project_id, body.expected_revision)
    status = project_status(current)
    if body.action == "delete":
        if directory.configured and "manage" not in directory.project_capabilities(
            actor.id, request.state.org_id, project_id
        ):
            raise _error(
                403, "project_owner_required", "Only a project owner can permanently delete it."
            )
        delete = getattr(projects, "delete_permanently", None)
        if not callable(delete):
            raise _error(
                409,
                "deletion_unavailable",
                "Permanent deletion requires the durable SQL project store.",
            )
        if status != "trashed" or body.name != current.metadata.name:
            raise _error(
                409,
                "deletion_not_confirmed",
                "Only a project in Trash can be permanently deleted. Confirm its exact name.",
            )
        if manager.status(project_id, current.revision).get("running"):
            raise _error(
                409,
                "application_running",
                "Stop this application before deleting its Studio project.",
            )
        _store_call(delete, user.id, project_id, body.expected_revision, body.name, actor.id)
        return {"id": project_id, "revision": current.revision, "status": "deleted"}
    candidate = current.model_copy(deep=True)
    if body.action == "rename":
        name = (body.name or "").strip()
        if not name or status == "trashed":
            raise _error(
                422,
                "invalid_project_action",
                "Restore the project before renaming it, and enter a project name.",
            )
        candidate.metadata.name = name
    elif body.action == "archive":
        if status != "active":
            raise _error(409, "invalid_project_action", "Only active projects can be archived.")
        candidate.project_lifecycle = ProjectLifecycle(status="archived")
    elif body.action == "trash":
        if status == "trashed":
            raise _error(409, "invalid_project_action", "This project is already in Trash.")
        candidate.project_lifecycle = ProjectLifecycle(status="trashed", restore_status=status)
    else:
        if status == "active":
            raise _error(409, "invalid_project_action", "This project is already active.")
        restored = current.project_lifecycle.restore_status if status == "trashed" else "active"
        candidate.project_lifecycle = ProjectLifecycle(status=restored)
    saved = _store_call(
        projects.update,
        user.id,
        project_id,
        body.expected_revision,
        candidate,
        f"project:{body.action}",
        actor.id,
    )
    return {"id": saved.id, "revision": saved.revision, "status": project_status(saved)}
