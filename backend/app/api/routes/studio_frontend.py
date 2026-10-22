"""Owner-scoped generation and an opaque, offline application preview."""

import logging
import time
from fastapi import APIRouter
from threading import BoundedSemaphore, Lock
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import CurrentUser
from app.api.routes.design_studio import Knowledge, ProjectUser, Projects, _current_at, _error, _store_call
from app.assistant.providers import get_studio_llm
from app.design_studio.frontend_generation import (
    FrontendGenerationError,
    generate_frontend,
    is_current,
    preview_document,
)
from app.llm.base import LLMInvalidResponse, LLMUnavailable

log = logging.getLogger(__name__)
router = APIRouter()
_generation_slots = BoundedSemaphore(2)
_progress_lock = Lock()
_progress: dict[str, dict] = {}
_outcomes: dict[str, dict] = {}


@router.get("/projects/{project_id}/frontend/blueprint")
def blueprint(project_id: str, user: ProjectUser, projects: Projects):
    from app.design_studio.application_blueprint import application_blueprint

    current = _store_call(projects.current, user.id, project_id)
    return {"revision": current.revision, **application_blueprint(current)}


class GenerateFrontendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    design_brief: str = Field(default="", max_length=4000)


@router.post("/projects/{project_id}/frontend/generate")
def generate(
    project_id: str,
    body: GenerateFrontendRequest,
    user: ProjectUser,
    actor: CurrentUser,
    projects: Projects,
):
    current = _current_at(projects, user.id, project_id, body.expected_revision)
    if current.project_lifecycle and current.project_lifecycle.status != "active":
        raise _error(
            409, "project_inactive", "Restore this project before generating application code."
        )
    llm = get_studio_llm()
    if llm is None:
        raise _error(
            503,
            "frontend_model_unavailable",
            "Configure the Studio language model to generate fresh application code.",
        )
    if not current.workflow_definitions or not current.business.entities:
        raise _error(
            409,
            "frontend_contract_missing",
            "Draft the business process and data model before generating the frontend.",
        )
    if not _generation_slots.acquire(blocking=False):
        raise _error(
            429,
            "frontend_generation_busy",
            "Two interfaces are already being generated. Try again after one finishes.",
        )
    with _progress_lock:
        if project_id in _progress:
            _generation_slots.release()
            raise _error(
                409,
                "frontend_generation_active",
                "This project's interface is already being generated.",
            )
        _progress[project_id] = {"phase": "preparing"}
        _outcomes.pop(project_id, None)
    outcome = {"status": "failed", "revision": body.expected_revision,
               "design_brief": body.design_brief,
               "message": "Generation did not finish. Your saved project is unchanged; retry to continue the draft."}
    try:
        try:
            started = time.perf_counter()

            def update_progress(event: dict):
                with _progress_lock:
                    _progress[project_id] = event
                log.info(
                    "frontend generation %.0fs %s",
                    time.perf_counter() - started,
                    str(event)[:300],
                )

            artifact = generate_frontend(
                current,
                llm,
                body.design_brief,
                progress=update_progress,
            )
        except FrontendGenerationError as exc:
            outcome["message"] = "The interface did not pass its completeness, code or browser checks. Retry to continue repairing the draft."
            outcome["diagnostics"] = str(exc)
            log.warning("frontend checks failed for %s: %s", project_id, str(exc)[:3000])
            raise _error(
                422,
                "frontend_build_failed",
                "The interface did not pass its code or browser checks. Your saved project is unchanged. Retry generation to continue repairing the draft.",
                {"diagnostics": str(exc)},
            ) from None
        except (LLMUnavailable, LLMInvalidResponse):
            raise _error(
                503,
                "frontend_model_failed",
                "The model could not finish generating application code. Your saved version is unchanged; try again.",
            ) from None
        candidate = current.model_copy(
            update={"generated_frontend": artifact, "frontend_required": True}
        )
        saved = _store_call(
            projects.update,
            user.id,
            project_id,
            body.expected_revision,
            candidate,
            "generate:frontend",
            actor.id,
        )
        outcome = {"status": "saved", "revision": saved.revision}
        return {"definition": saved, "checks": artifact.checks}
    finally:
        with _progress_lock:
            _progress.pop(project_id, None)
            if len(_outcomes) >= 128:
                _outcomes.pop(next(iter(_outcomes)))
            _outcomes[project_id] = outcome
        _generation_slots.release()


@router.get("/projects/{project_id}/frontend/progress")
def progress(project_id: str, user: ProjectUser, projects: Projects):
    _store_call(projects.current, user.id, project_id)
    with _progress_lock:
        return {"progress": _progress.get(project_id), "result": _outcomes.get(project_id)}


@router.get("/projects/{project_id}/frontend/preview")
def preview(project_id: str, user: ProjectUser, projects: Projects, knowledge: Knowledge):
    current = _store_call(projects.current, user.id, project_id)
    if not current.generated_frontend:
        # Every project has an interface: the schema-driven client derives its screens from the process and data model.
        from app.design_studio.runtime_generation import preview_document as baseline, screen_summary

        return {
            "html": baseline(current, knowledge),
            "current": True,
            "revision": current.revision,
            "checks": [],
            "kind": "baseline",
            "screens": screen_summary(current),
        }
    return {
        "kind": "generated",
        "html": preview_document(current),
        "current": is_current(current),
        "revision": current.revision,
        "checks": current.generated_frontend.checks,
    }
