"""Item-level comparison of two definitions: which requirements, steps, screens… were added, removed or changed.

Used to explain exactly what invalidated an approval and to compare revisions. Comparison is by stable ID, so a
renamed label shows as a change to that item rather than a removal and an addition.
"""

from __future__ import annotations

from app.schemas.application_definition import ApplicationDefinition

BUSINESS_GROUPS = (
    "requirements",
    "roles",
    "entities",
    "rules",
    "exceptions",
    "decisions",
    "integrations",
    "terms",
    "questions",
)
# Which approval each area belongs to: process approval covers the business design and workflows; design covers all.
PROCESS_AREAS = frozenset(
    {"brief", "knowledge", "workflow", "step", "transition", *BUSINESS_GROUPS}
)


def _by_id(items: list[dict]) -> dict[str, dict]:
    return {item["id"]: item for item in items}


def _compare_group(
    area: str, before: list[dict], after: list[dict], changes: list[dict], prefix: str = ""
) -> None:
    old, new = _by_id(before), _by_id(after)
    for item_id in sorted(old.keys() | new.keys()):
        ref = f"{prefix}{item_id}"
        if item_id not in new:
            changes.append({"area": area, "item_id": ref, "change": "removed"})
        elif item_id not in old:
            changes.append({"area": area, "item_id": ref, "change": "added"})
        elif old[item_id] != new[item_id]:
            fields = sorted(
                key
                for key in old[item_id].keys() | new[item_id].keys()
                if old[item_id].get(key) != new[item_id].get(key)
            )
            changes.append({"area": area, "item_id": ref, "change": "changed", "fields": fields})


def compare(base: ApplicationDefinition, target: ApplicationDefinition) -> list[dict]:
    a, b = base.model_dump(mode="json"), target.model_dump(mode="json")
    changes: list[dict] = []
    old_frontend, new_frontend = a.get("generated_frontend"), b.get("generated_frontend")
    if old_frontend != new_frontend:
        changes.append(
            {
                "area": "frontend",
                "item_id": "generated_frontend",
                "change": "added"
                if not old_frontend
                else "removed"
                if not new_frontend
                else "changed",
                "fields": ["source", "pages", "build"],
            }
        )
    for key in ("metadata", "theme"):
        if a[key] != b[key]:
            changes.append(
                {
                    "area": key,
                    "item_id": key,
                    "change": "changed",
                    "fields": sorted(
                        field for field in a[key] if a[key][field] != b[key].get(field)
                    ),
                }
            )
    if a["business"]["brief"] != b["business"]["brief"]:
        changes.append(
            {
                "area": "brief",
                "item_id": "brief",
                "change": "changed",
                "fields": sorted(
                    field
                    for field in a["business"]["brief"]
                    if a["business"]["brief"][field] != b["business"]["brief"][field]
                ),
            }
        )
    if a["business"]["knowledge"] != b["business"]["knowledge"]:
        changes.append({"area": "knowledge", "item_id": "knowledge", "change": "changed"})
    for group in BUSINESS_GROUPS:
        _compare_group(group, a["business"][group], b["business"][group], changes)
    _compare_group(
        "workflow",
        [
            {k: v for k, v in w.items() if k not in ("states", "transitions")}
            for w in a["workflow_definitions"]
        ],
        [
            {k: v for k, v in w.items() if k not in ("states", "transitions")}
            for w in b["workflow_definitions"]
        ],
        changes,
    )
    old_workflows, new_workflows = (
        _by_id(a["workflow_definitions"]),
        _by_id(b["workflow_definitions"]),
    )
    for workflow_id in sorted(old_workflows.keys() & new_workflows.keys()):
        _compare_group(
            "step",
            old_workflows[workflow_id]["states"],
            new_workflows[workflow_id]["states"],
            changes,
            f"{workflow_id}/",
        )
        _compare_group(
            "transition",
            old_workflows[workflow_id]["transitions"],
            new_workflows[workflow_id]["transitions"],
            changes,
            f"{workflow_id}/",
        )
    _compare_group("screen", a["screens"], b["screens"], changes)
    if a["navigation"] != b["navigation"]:
        changes.append({"area": "navigation", "item_id": "navigation", "change": "changed"})
    if a["fixtures"] != b["fixtures"] or a["local_state"] != b["local_state"]:
        changes.append({"area": "data_fixtures", "item_id": "fixtures", "change": "changed"})
    return changes


def invalidating_changes(
    approved: ApplicationDefinition, current: ApplicationDefinition, scope: str
) -> list[dict]:
    """Changes since the approved revision that fall inside the approval's scope."""
    changes = compare(approved, current)
    return [item for item in changes if scope == "design" or item["area"] in PROCESS_AREAS]
