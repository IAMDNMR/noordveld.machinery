"""Report defects left after bounded model repair without inventing semantic links."""

from __future__ import annotations

from app.schemas.application_definition import ApplicationDefinition

def settle(definition: ApplicationDefinition, findings: list[dict]) -> tuple[ApplicationDefinition, list[str]]:
    """Keep unresolved findings explicit. Word overlap is not evidence that an
    activity implements a requirement or is a safe exception recovery path.
    """
    return definition, [f"{item['code']}: {item['message']}" for item in findings]
