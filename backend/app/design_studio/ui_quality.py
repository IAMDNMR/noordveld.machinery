"""UI quality gate: render a generated interface in a real browser and report measurable defects.

The checks live in frontend/scripts/check-studio-ui.mjs. They only report what is wrong (unstyled classes, overflow,
hidden navigation, accessibility); they never prescribe an application's content or layout, so they cannot become a template.
"""

from __future__ import annotations

import json
import subprocess

from app.design_studio.frontend_generation import FRONTEND, FrontendGenerationError, app_document, run_tool
from app.schemas.application_definition import ApplicationDefinition

SCRIPT = FRONTEND / "scripts/check-studio-ui.mjs"


def check_ui(definition: ApplicationDefinition) -> dict:
    """{"findings": [{id, severity, message, evidence}], "metrics": {...}} for the saved frontend."""
    try:
        result = run_tool(SCRIPT, {"html": app_document(definition)}, 120)
        return json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise FrontendGenerationError("The UI quality check could not run.") from exc


def describe(findings: list[dict]) -> str:
    """Findings as plain text, for a person or for the model's fix request."""
    return "\n".join(
        f"- [{item['severity']}] {item['message']}"
        + (f" Evidence: {json.dumps(item['evidence'], ensure_ascii=False)}" if item.get("evidence") else "")
        for item in findings
    )
