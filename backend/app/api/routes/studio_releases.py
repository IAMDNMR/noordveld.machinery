"""Retained, authorized release downloads and their independent test history."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from app.api.dependencies import CurrentUser
from app.api.routes.design_studio import (
    ProjectUser,
    Projects,
    Knowledge,
    DomainPacks,
    _compiled,
    _error,
    _store_call,
    _summary,
)
from app.design_studio.releases import ReleaseStore, get_release_store, retain_package

router = APIRouter()
Releases = Annotated[ReleaseStore, Depends(get_release_store)]


class RetainRequest(BaseModel):
    expected_revision: int = Field(ge=1)


@router.get("/projects/{project_id}/releases")
def releases(project_id: str, user: ProjectUser, projects: Projects, store: Releases):
    _store_call(projects.current, user.id, project_id)
    return store.list(user.id, project_id)


@router.post("/projects/{project_id}/releases")
def retain(
    project_id: str,
    body: RetainRequest,
    user: ProjectUser,
    actor: CurrentUser,
    projects: Projects,
    knowledge: Knowledge,
    domain: DomainPacks,
    store: Releases,
):
    definition, result = _compiled(project_id, user, projects, knowledge, domain)
    if definition.revision != body.expected_revision:
        raise _error(
            409, "revision_conflict", "The project changed. Refresh before retaining a release."
        )
    if result["status"] != "generated":
        raise _error(
            409, "generation_blocked", "Only an approved generated package can be retained."
        )
    return retain_package(
        store, user.id, project_id, definition.revision, actor.id, result["files"], _summary(result)
    )


@router.get("/projects/{project_id}/releases/{release_id}/archive")
def archive(
    project_id: str, release_id: str, user: ProjectUser, projects: Projects, store: Releases
):
    _store_call(projects.current, user.id, project_id)
    try:
        data = store.archive(user.id, project_id, release_id)
    except KeyError:
        raise _error(404, "release_not_found", "No such release in this project.") from None
    except ValueError:
        raise _error(
            409, "release_corrupt", "The retained package failed its integrity check."
        ) from None
    return Response(
        data,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="studio-release.zip"',
            "Cache-Control": "private, no-store",
        },
    )
