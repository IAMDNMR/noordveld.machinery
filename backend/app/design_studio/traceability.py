"""Requirement → step → role/entity/rule/exception → screen/component → exported artefact, and change impact."""

from __future__ import annotations

from app.design_studio.process import needs_screen, ordered_states, outgoing, steps
from app.schemas.application_definition import ApplicationDefinition, Component

# Where each kind of item is written in the review export (codegen.MANIFESTS keeps these in step).
ARTEFACTS = {
    "requirement": "design/requirements.json",
    "role": "design/roles.json",
    "entity": "design/entities.json",
    "rule": "design/rules.json",
    "exception": "design/rules.json",
    "decision": "design/rules.json",
    "integration": "design/entities.json",
    "step": "design/process.json",
    "screen": "design/screens.json",
    "term": "design/requirements.json",
}


def _walk(nodes: list[Component]):
    for node in nodes:
        yield node
        yield from _walk(node.children or [])


def _kinds(definition: ApplicationDefinition) -> dict[str, str]:
    business = definition.business
    kinds = {}
    for kind, group in (
        ("requirement", business.requirements),
        ("role", business.roles),
        ("entity", business.entities),
        ("rule", business.rules),
        ("exception", business.exceptions),
        ("decision", business.decisions),
        ("integration", business.integrations),
        ("term", business.terms),
    ):
        kinds.update({item.id: kind for item in group})
    return kinds


def report(definition: ApplicationDefinition) -> dict:
    business = definition.business
    step_screens: dict[tuple[str, str], list[str]] = {}
    req_screens: dict[str, set[str]] = {}
    req_components: dict[str, set[str]] = {}
    entity_screens: dict[str, set[str]] = {}
    untraced = []
    for screen in definition.screens:
        trace = screen.trace
        if trace and trace.step_id:
            step_screens.setdefault((trace.workflow_id, trace.step_id), []).append(screen.id)
            for ref in trace.requirement_ids:
                req_screens.setdefault(ref, set()).add(screen.id)
        elif definition.workflow_definitions:
            untraced.append({"screen_id": screen.id, "title": screen.title})
        for node in _walk(screen.components):
            if node.trace:
                for ref in node.trace.requirement_ids:
                    req_components.setdefault(ref, set()).add(node.id)
                if node.trace.entity_id:
                    entity_screens.setdefault(node.trace.entity_id, set()).add(screen.id)

    # The generated React interface replaces the component draft. Include its
    # declared bindings instead of reporting every model page as missing.
    if definition.generated_frontend:
        step_screens, req_screens, req_components, entity_screens = {}, {}, {}, {}
        untraced = []
        requirements_by_step = {
            f"{workflow.id}/{state.id}": state.requirement_ids
            for workflow in definition.workflow_definitions for state in workflow.states
        }
        for page in definition.generated_frontend.pages:
            for ref in page.step_ids:
                if "/" not in ref:
                    continue
                workflow_id, step_id = ref.split("/", 1)
                step_screens.setdefault((workflow_id, step_id), []).append(page.id)
                for requirement in requirements_by_step.get(ref, []):
                    req_screens.setdefault(requirement, set()).add(page.id)
            for entity in page.entity_ids:
                entity_screens.setdefault(entity, set()).add(page.id)

    step_rows, handoffs = [], []
    req_steps: dict[str, list[dict]] = {}
    entity_use: dict[str, dict[str, list[str]]] = {
        entity.id: {"read_by": [], "written_by": []} for entity in business.entities
    }
    for workflow in definition.workflow_definitions:
        by_id = {state.id: state for state in workflow.states}
        for state in ordered_states(workflow):
            ref = f"{workflow.id}/{state.id}"
            screens = step_screens.get((workflow.id, state.id), [])
            step_rows.append(
                {
                    "workflow_id": workflow.id,
                    "step_id": state.id,
                    "label": state.label,
                    "kind": state.kind,
                    "role_id": state.role_id,
                    "permission": state.permission,
                    "requires_screen": needs_screen(state),
                    "screens": screens,
                    "requirement_ids": state.requirement_ids,
                    "reads_entity_ids": state.reads_entity_ids,
                    "writes_entity_ids": state.writes_entity_ids,
                    "rule_ids": state.rule_ids,
                    "exception_ids": state.exception_ids,
                }
            )
            for requirement_id in state.requirement_ids:
                req_steps.setdefault(requirement_id, []).append(
                    {"workflow_id": workflow.id, "step_id": state.id}
                )
            for entity_id in state.reads_entity_ids:
                entity_use[entity_id]["read_by"].append(ref)
            for entity_id in state.writes_entity_ids:
                entity_use[entity_id]["written_by"].append(ref)
            for edge in outgoing(workflow, state.id):
                target = by_id[edge.target]
                if state.role_id and target.role_id and state.role_id != target.role_id:
                    handoffs.append(
                        {
                            "workflow_id": workflow.id,
                            "from_step": state.id,
                            "to_step": target.id,
                            "from_role": state.role_id,
                            "to_role": target.role_id,
                            "requires_authorisation": target.permission,
                        }
                    )

    requirements = []
    for requirement in business.requirements:
        linked_steps = req_steps.get(requirement.id, [])
        screens = sorted(req_screens.get(requirement.id, set()))
        requirements.append(
            {
                "id": requirement.id,
                "statement": requirement.statement,
                "kind": requirement.kind,
                "priority": requirement.priority,
                "status": requirement.status,
                "acceptance_criteria": [item.id for item in requirement.acceptance_criteria],
                "steps": linked_steps,
                "screens": screens,
                "components": sorted(req_components.get(requirement.id, set())),
                "covered_by_process": bool(linked_steps),
                "covered_by_screens": bool(screens),
            }
        )
    active = [row for row in requirements if row["status"] in ("draft", "agreed")]
    return {
        "screen_evidence": "declared_frontend_bindings" if definition.generated_frontend else "component_traces",
        "behavior_validated": False,
        "requirements": requirements,
        "covered_requirements": [
            row["id"] for row in active if row["covered_by_process"] and row["covered_by_screens"]
        ],
        "requirements_without_process": [
            row["id"] for row in active if not row["covered_by_process"]
        ],
        "requirements_without_screens": [
            row["id"]
            for row in active
            if row["covered_by_process"] and not row["covered_by_screens"]
        ],
        "steps": step_rows,
        "steps_without_screens": [
            f"{row['workflow_id']}/{row['step_id']}"
            for row in step_rows
            if row["requires_screen"] and not row["screens"]
        ],
        "screens_without_trace": untraced,
        "handoffs": handoffs,
        "entities": [
            {
                "id": entity.id,
                **entity_use[entity.id],
                "screens": sorted(entity_screens.get(entity.id, set())),
            }
            for entity in business.entities
        ],
        "assumption_rules": [
            {"id": rule.id, "description": rule.description, "source": rule.source.reference}
            for rule in business.rules
            if rule.status == "assumption"
        ],
        "unresolved_decisions": [
            {
                "id": item.id,
                "question": item.question,
                "status": item.status,
                "deferral_reason": item.deferral_reason,
            }
            for item in business.decisions
            if item.status != "decided"
        ],
    }


def impact(definition: ApplicationDefinition, item_id: str) -> dict | None:
    """What depends on one business item or workflow step: the parts to re-review when it changes."""
    kinds = _kinds(definition)
    step_ids = {state.id for _, state in steps(definition)}
    if item_id not in kinds and item_id not in step_ids:
        return None
    kind = kinds.get(item_id, "step")
    affected_steps = []
    for workflow, state in steps(definition):
        refs = {
            state.role_id,
            *state.requirement_ids,
            *state.reads_entity_ids,
            *state.writes_entity_ids,
            *state.rule_ids,
            *state.exception_ids,
        }
        conditions = {edge.condition.field for edge in outgoing(workflow, state.id)}
        if state.id == item_id or item_id in refs or item_id in conditions:
            affected_steps.append(f"{workflow.id}/{state.id}")
    affected_refs = set(affected_steps)
    screens, components = set(), set()
    for screen in definition.screens:
        trace = screen.trace
        if trace and (f"{trace.workflow_id}/{trace.step_id}" in affected_refs or item_id in trace.requirement_ids):
            screens.add(screen.id)
        for node in _walk(screen.components):
            t = node.trace
            if t and (
                f"{t.workflow_id}/{t.step_id}" in affected_refs
                or item_id in (t.entity_id, t.rule_id, t.exception_id)
                or item_id in t.requirement_ids
            ):
                components.add(node.id)
                screens.add(screen.id)
    if definition.generated_frontend:
        screens = {
            page.id for page in definition.generated_frontend.pages
            if affected_refs.intersection(page.step_ids) or item_id in page.entity_ids
        }
        components = set()  # Source pages do not carry component-level trace evidence.
    business = definition.business
    related = sorted(
        {decision.id for decision in business.decisions if item_id in decision.affects}
        | {
            entity.id
            for entity in business.entities
            if any(rel.target == item_id for rel in entity.relationships)
            or entity.owner_role_id == item_id
        }
        | {
            integration.id
            for integration in business.integrations
            if item_id in integration.entity_ids
        }
    )
    artefacts = sorted(
        {
            "src/definition.json",
            ARTEFACTS[kind],
            "design/traceability.json",
            "design/validation-report.json",
        }
        | ({"design/process.json"} if affected_steps else set())
        | ({"design/screens.json", "src/App.tsx"} if screens else set())
    )
    return {
        "item_id": item_id,
        "kind": kind,
        "steps": affected_steps,
        "screens": sorted(screens),
        "components": sorted(components),
        "related_items": related,
        "artefacts": artefacts,
        "approvals_invalidated_by_change": ["process", "design"]
        if kind != "screen"
        else ["design"],
    }
