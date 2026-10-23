"""Targeted edits to retained application source, with the shared generation checks."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.design_studio.application_blueprint import application_blueprint
from app.design_studio.frontend_generation import (
    FrontendGenerationError,
    SYSTEM,
    build_source,
    guard_open_business_limits,
    input_digest,
    validate_proposal,
)
from app.schemas.generated_frontend import FrontendPage, FrontendProposal


class SourceEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=20, max_length=2000)
    files: dict[str, str] = Field(min_length=1)
    pages: list[FrontendPage] | None = None


def edit_frontend(definition, llm, brief: str, progress=None):
    """Merge only named files. Failed checks leave the previously saved build intact."""
    existing = definition.generated_frontend
    if existing is None:
        raise FrontendGenerationError("Generate an interface before editing its source.")
    if progress:
        progress({"phase": "editing"})
    context = {
        "instruction": brief,
        "selected": definition.assistant_context.selected if definition.assistant_context else None,
        "conversation": [
            {"role": item.role, "text": item.text}
            for item in definition.assistant_context.history[-6:]
        ]
        if definition.assistant_context
        else [],
        "application_blueprint": application_blueprint(definition),
        "business": definition.business.model_dump(mode="json"),
        "workflow_definitions": [
            w.model_dump(mode="json") for w in definition.workflow_definitions
        ],
        "pages": [p.model_dump() for p in existing.pages],
        "files": existing.files,
        "sdk_types": existing.sdk_source,
    }
    response = llm.studio_frontend(
        SYSTEM + "\nEDIT THE EXISTING APPLICATION. Return JSON {summary,files,pages?}. "
        "files contains COMPLETE source for changed or new files ONLY. Preserve every unrelated "
        "layout, module and customization. Do not remove files. Include all affected consumers "
        "when an interface changes. Omit pages unless page bindings change. Use the supplied SDK "
        "contract for real actions; never simulate business behaviour or invent missing policy.",
        json.dumps(context, ensure_ascii=False),
    )
    try:
        edit = SourceEdit.model_validate(response)
    except ValidationError as exc:
        raise FrontendGenerationError(
            "The edit did not return valid changed source files and page bindings."
        ) from exc
    if any(
        not re.fullmatch(r"src/[a-zA-Z0-9_/-]+\.(tsx|ts|css)", name)
        or ".." in name
        or name in {"src/main.tsx", "src/studio-sdk.tsx"}
        for name in edit.files
    ):
        raise FrontendGenerationError(
            "Edited source paths must stay inside the application's src/ directory."
        )
    files = {**existing.files, **edit.files}
    proposal = FrontendProposal(
        design_summary=edit.summary,
        files=files,
        pages=edit.pages if edit.pages is not None else existing.pages,
    )
    validate_proposal(proposal, definition, complete=True)
    guard_open_business_limits(definition, files)
    if progress:
        progress({"phase": "building", "files": sorted(edit.files)})
    built = build_source(files)
    artifact = existing.model_copy(
        update={
            **proposal.model_dump(),
            "pages": proposal.pages,
            "input_sha256": input_digest(definition),
            "source_sha256": sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "provider": str(getattr(llm, "name", "configured-model")),
            "bundle_js": built["js"],
            "bundle_css": built["css"],
            "sdk_source": built.get("sdk_source", existing.sdk_source),
            "entry_source": built.get("entry_source", existing.entry_source),
            "checks": built["checks"],
        }
    )
    from app.design_studio.ui_quality import check_ui, describe

    if progress:
        progress({"phase": "reviewing", "round": 0})
    report = check_ui(definition.model_copy(update={"generated_frontend": artifact}))
    if any(item["severity"] == "error" for item in report["findings"]):
        raise FrontendGenerationError(describe(report["findings"]))
    return artifact.model_copy(
        update={"checks": [*artifact.checks, "Targeted source edit passed browser checks."]}
    )
