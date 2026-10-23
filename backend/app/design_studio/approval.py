"""Approval digests. An approval is bound to the revision it was recorded in and to the digest of what was approved;
any later change to that content makes it stale. Only the server writes approval records."""

from __future__ import annotations

from hashlib import sha256
import json

from app.schemas.application_definition import ApplicationDefinition

SCOPES = ("process", "design")


def _digest(payload: object) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def digest(definition: ApplicationDefinition, scope: str) -> str:
    raw = definition.model_dump(mode="json")
    if scope == "process":
        # Requirements, knowledge, roles, data, rules and the workflows: everything screen generation depends on.
        return _digest(
            {
                "business": raw["business"],
                "workflows": raw["workflows"],
                "workflow_definitions": raw["workflow_definitions"],
            }
        )
    raw.pop("project_lifecycle", None)
    raw.pop("studio_flow", None)
    raw.pop("assistant_context", None)
    raw.pop("approvals")
    raw.pop("revision")
    return _digest(raw)


def status(definition: ApplicationDefinition) -> dict[str, dict]:
    result = {}
    for scope in SCOPES:
        record = next((item for item in definition.approvals if item.scope == scope), None)
        if record is None:
            result[scope] = {"state": "none", "record": None}
        else:
            valid = record.revision <= definition.revision and record.content_sha256 == digest(
                definition, scope
            )
            result[scope] = {
                "state": "valid" if valid else "stale",
                "record": record.model_dump(mode="json"),
            }
    return result


def is_valid(definition: ApplicationDefinition, scope: str) -> bool:
    return status(definition)[scope]["state"] == "valid"
