"""An application inventory derived from the saved business contract, never a visual template.

Surfaces are responsibilities, not necessarily separate routes: a split workspace may
serve a list and detail together. Declaring a binding is planning evidence, not proof
that the generated interaction works.
"""

from app.design_studio.process import needs_screen


def preview_role(definition) -> str | None:
    """Prefer a project-authored working role; this selects preview context only."""
    working = {step.role_id for workflow in definition.workflow_definitions for step in workflow.states if needs_screen(step) and step.role_id}
    roles = definition.business.roles
    return next((r.id for r in roles if r.id in working and not r.origin), next((r.id for r in roles if r.id in working), None))


def application_blueprint(definition) -> dict:
    entities = {entity.id: entity for entity in definition.business.entities}
    surfaces, modules = [], []
    used, written = set(), set()
    requirement_steps: dict[str, list[str]] = {}
    for workflow in definition.workflow_definitions:
        tasks = []
        for step in workflow.states:
            ref = f"{workflow.id}/{step.id}"
            for requirement in step.requirement_ids:
                requirement_steps.setdefault(requirement, []).append(ref)
            used.update(step.reads_entity_ids + step.writes_entity_ids)
            written.update(step.writes_entity_ids)
            if not needs_screen(step):
                continue
            surface = {
                "id": f"task:{ref}", "kind": "task", "title": step.label,
                "step_ids": [ref],
                "entity_ids": list(dict.fromkeys(step.reads_entity_ids + step.writes_entity_ids)),
                "requirement_ids": step.requirement_ids, "role_ids": [step.role_id] if step.role_id else [],
            }
            surfaces.append(surface)
            tasks.append(surface["id"])
        modules.append({"id": workflow.id, "title": workflow.name, "surface_ids": tasks})
    # Related records are part of the same application, even when no step writes them.
    pending = list(used)
    while pending:
        entity = entities.get(pending.pop())
        for relationship in entity.relationships if entity else []:
            if relationship.target in entities and relationship.target not in used:
                used.add(relationship.target)
                pending.append(relationship.target)
    for entity in definition.business.entities:
        if entity.id not in used:
            continue
        kinds = ["list", "detail"]
        editable = any(a.writable and not a.system_managed for a in entity.attributes)
        if entity.id in written and editable:
            kinds.extend(["create", "edit"])
        for kind in kinds:
            surfaces.append({
                "id": f"record:{entity.id}:{kind}", "kind": kind,
                "title": f"{entity.name} · {kind}", "entity_ids": [entity.id],
                "step_ids": [], "requirement_ids": [], "role_ids": [],
            })
    requirements = []
    for requirement in definition.business.requirements:
        if requirement.status not in ("draft", "agreed"):
            continue
        steps = requirement_steps.get(requirement.id, [])
        requirements.append({
            "id": requirement.id, "statement": requirement.statement,
            "step_ids": steps, "status": "planned" if steps else "needs_design",
            "resolution": None if steps else "Link this requirement to its business process or explicitly record its implementation contract.",
        })
    return {
        "version": 1, "modules": modules, "surfaces": surfaces,
        "requirements": requirements,
        "decisions": [{"id": d.id, "question": d.question, "status": d.status} for d in definition.business.decisions if d.status != "decided"],
        "integrations": [{"id": i.id, "name": i.name, "status": i.contract_status} for i in definition.business.integrations],
        "note": "Planned surfaces may share a page. Runtime authorization remains authoritative. Page declarations do not certify behavior.",
    }


def plan_gaps(proposal, definition) -> list[str]:
    """Reject missing responsibilities and unrelated bindings before writing source."""
    inventory = {surface["id"]: surface for surface in application_blueprint(definition)["surfaces"]}
    # A page may also explain an existing automated decision or process boundary.
    # It is optional context, not a missing/unknown business capability.
    optional = {
        f"task:{workflow.id}/{step.id}": {
            "entity_ids": list(dict.fromkeys(step.reads_entity_ids + step.writes_entity_ids)),
            "step_ids": [f"{workflow.id}/{step.id}"],
        }
        for workflow in definition.workflow_definitions for step in workflow.states
        if not needs_screen(step)
    }
    covered, errors = set(), []
    for page in proposal.pages:
        for ref in page.surface_ids:
            surface = inventory.get(ref) or optional.get(ref)
            if surface is None:
                errors.append(f"Unknown application surface {ref}")
                continue
            if not set(surface["entity_ids"]) <= set(page.entity_ids) or not set(surface["step_ids"]) <= set(page.step_ids):
                errors.append(f"Page {page.id} does not bind the entities/steps required by {ref}")
            covered.add(ref)
    missing = sorted(set(inventory) - covered)
    if missing:
        errors.append("Pages omit application surfaces: " + ", ".join(missing))
    return errors
