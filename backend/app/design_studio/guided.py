"""Sequential draft reviews, separate from formal process/design approval."""

from app.design_studio.stages import STAGES
from app.schemas.application_definition import ApplicationDefinition
from hashlib import sha256
import json

ALLOWED = {
    "brief": {"set_intake_context", "set_brief", "add_requirement", "answer_question"},
    "knowledge": {"set_intake_context", "update_knowledge", "adopt_pack", "set_brief"},
    "workflow": {
        "create_workflow",
        "insert_step",
        "add_approval",
        "rename_step",
        "assign_step_role",
        "link_requirement",
        "set_step_data",
        "add_role",
        "add_entity",
        "add_exception",
        "update_exception",
        "merge_process",
    },
    "data": {"add_entity", "add_attribute", "set_attribute_required", "set_step_data"},
    "screen": {"set_theme"},
    "rules": {"reconcile_duplicate", "bind_rule", "confirm_rule", "add_rule", "add_decision", "add_exception", "update_exception", "answer_decision"},
    "roles": {"add_role", "assign_step_role"},
    "checks": {
        "reconcile_duplicate",
        "update_knowledge",
        "bind_rule",
        "confirm_rule",
        "answer_question",
        "answer_decision",
        "link_requirement",
        "update_exception",
        "insert_step",
        "assign_step_role",
        "set_step_data",
        "merge_process",
        "add_role",
        "add_entity",
        "add_attribute",
        "set_attribute_required",
    },
    "export": set(),
}


def stage_digest(definition: ApplicationDefinition, stage: str) -> str:
    raw = definition.model_dump(mode="json")
    b = raw["business"]
    scopes = {
        "brief": {
            "brief": {
                k: v
                for k, v in b["brief"].items()
                if k not in ("domain_id", "capability", "subdomain")
            },
            "requirements": [r for r in b["requirements"] if not r.get("origin")],
        },
        "knowledge": {"knowledge": b["knowledge"], "domain_id": b["brief"]["domain_id"]},
        "workflow": raw["workflow_definitions"],
        "data": b["entities"],
        "screen": {"screens": raw["screens"], "theme": raw["theme"]},
        "rules": {k: b[k] for k in ("rules", "exceptions", "decisions", "integrations")},
        "roles": {
            "roles": b["roles"],
            "assignments": [
                (w["id"], s["id"], s.get("role_id"), s.get("permission"))
                for w in raw["workflow_definitions"]
                for s in w["states"]
            ],
        },
        "checks": raw["approvals"],
    }
    if definition.generated_frontend:
        scopes["screen"]["frontend"] = definition.generated_frontend.source_sha256
    return sha256(
        json.dumps(scopes[stage], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def reviewed(definition: ApplicationDefinition) -> list[str]:
    if not definition.studio_flow:
        return []
    valid = []
    for stage in definition.studio_flow.reviewed:
        previous = definition.studio_flow.reviewed_digests.get(stage)
        if previous and previous != stage_digest(definition, stage):
            break
        valid.append(stage)
    return valid


def active(definition: ApplicationDefinition) -> str:
    return STAGES[len(reviewed(definition))][0]


def ready(definition: ApplicationDefinition, stage: str) -> bool:
    if stage == "screen":
        # The schema-driven client already gives every process step and record its screens; a model-generated interface
        # is optional, but once there is one it must match the current process and data model.
        from app.design_studio.frontend_generation import is_current

        if definition.generated_frontend:
            return is_current(definition)
        return bool(definition.workflow_definitions and definition.business.entities)
    if stage == "checks":
        from app.design_studio import approval

        return approval.is_valid(definition, "process") and approval.is_valid(definition, "design")
    b = definition.business
    return {
        "brief": bool(b.brief.goal and b.requirements),
        "knowledge": bool(
            b.knowledge or (b.roles and b.entities and definition.workflow_definitions)
        ),
        "workflow": bool(definition.workflow_definitions),
        "data": bool(b.entities),
        "rules": bool(definition.workflow_definitions),
        "roles": bool(b.roles),
        "checks": bool(definition.workflow_definitions),
        "export": False,
    }[stage]


def statuses(definition: ApplicationDefinition, stages: dict) -> dict:
    current = active(definition)
    reviewed_stages = reviewed(definition)
    for key, label in STAGES:
        if key in reviewed_stages:
            if stages[key].get("counts", {}).get("errors", 0):
                stages[key] = {
                    **stages[key],
                    "status": "blocked",
                    "reason": "Previously reviewed draft has current validation issues. "
                    + stages[key]["reason"],
                }
            else:
                stages[key] = {
                    **stages[key],
                    "status": "completed",
                    "reason": "Draft reviewed. Formal approvals are checked before generation.",
                }
        elif key != current:
            stages[key] = {
                "status": "not_started",
                "reason": "Available after you review the previous stage and continue.",
                "counts": {},
            }
        elif key != "export" and ready(definition, key) and stages[key].get("status") == "blocked":
            # A draft with open errors of its own is not reviewable: say so now, not after the person has moved on.
            stages[key] = {
                **stages[key],
                "reason": "Fix this before you continue, or ask the assistant to repair it. " + stages[key]["reason"],
            }
        elif key != "export":
            stages[key] = {
                "status": "ready_for_review" if ready(definition, key) else "needs_input",
                "reason": "Review this draft, request changes if needed, then continue."
                if ready(definition, key)
                else (
                    "Screens are derived from the process and records. Add a process and its records first."
                    if key == "screen"
                    else "This stage needs a draft before you can continue. Ask the assistant to complete it."
                ),
                "counts": {},
            }
            if key in definition.studio_flow.reviewed and key not in reviewed_stages:
                stages[key]["reason"] = (
                    "This content changed after review. Review it again before continuing."
                )
    if current == "checks" and not ready(definition, current):
        stages[current]["reason"] = (
            "Review validation findings and complete process and design approvals here before generation. Draft reviews do not replace these approvals."
        )
    return stages
