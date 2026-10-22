"""The application template library: browse it, open one template, get recommendations for a project and select one."""

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import CurrentUser
from app.api.routes.design_studio import ProjectUser, Projects, _current_at, _error, _store_call
from app.design_studio.templates import recommend, template, templates
from app.schemas.application_definition import TemplateSelection

router = APIRouter()


class SelectTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    template_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")


@router.get("/app-templates")
def list_templates(_: CurrentUser):
    # Full definitions: every gallery card renders its own live preview (ten templates are a few tens of kilobytes).
    items = [item.model_dump() for item in templates()]
    return {"templates": items, "categories": sorted({item["category"] for item in items})}


@router.get("/app-templates/{template_id}")
def get_template(template_id: str, _: CurrentUser):
    item = template(template_id)
    if item is None:
        raise _error(404, "template_not_found", "No application template has that ID.")
    return item.model_dump()


@router.get("/projects/{project_id}/app-templates/recommendations")
def recommendations(project_id: str, user: ProjectUser, projects: Projects):
    current = _store_call(projects.current, user.id, project_id)
    return {
        "selected": current.template.model_dump() if current.template else None,
        "recommendations": recommend(current),
    }


@router.post("/projects/{project_id}/app-template")
def select_template(project_id: str, body: SelectTemplate, user: ProjectUser, actor: CurrentUser, projects: Projects):
    item = template(body.template_id)
    if item is None:
        raise _error(404, "template_not_found", "No application template has that ID.")
    current = _current_at(projects, user.id, project_id, body.expected_revision)
    selection = TemplateSelection(template_id=item.id, version=item.version, selected_at=datetime.now(timezone.utc).isoformat())
    saved = _store_call(
        projects.update,
        user.id,
        project_id,
        body.expected_revision,
        current.model_copy(update={"template": selection}),
        "select:template",
        actor.id,
    )
    return {"revision": saved.revision, "template": selection.model_dump()}
