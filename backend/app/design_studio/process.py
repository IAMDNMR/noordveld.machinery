"""Shared, side-effect-free queries over a definition's workflows. Used by completeness, traceability and generation."""

from __future__ import annotations

from app.schemas.application_definition import (
    ApplicationDefinition,
    WorkflowDefinition,
    WorkflowState,
)

HUMAN_KINDS = frozenset({"search", "form", "review", "approval", "exception", "end"})


def needs_screen(state: WorkflowState) -> bool:
    """A person acts or is informed here. Branches never need a screen; an action needs one only when a permission
    shows that a user performs it (an action without one is an automated platform step)."""
    return state.kind in HUMAN_KINDS or (state.kind == "action" and state.permission is not None)


def outgoing(workflow: WorkflowDefinition, state_id: str):
    return [edge for edge in workflow.transitions if edge.source == state_id]


def ordered_states(workflow: WorkflowDefinition) -> list[WorkflowState]:
    """Breadth-first from the start, following transition order; deterministic."""
    by_id = {state.id: state for state in workflow.states}
    start = next(state.id for state in workflow.states if state.kind == "start")
    seen, queue = [start], [start]
    while queue:
        current = queue.pop(0)
        for edge in outgoing(workflow, current):
            if edge.target not in seen:
                seen.append(edge.target)
                queue.append(edge.target)
    return [by_id[state_id] for state_id in seen]


def steps(definition: ApplicationDefinition):
    for workflow in definition.workflow_definitions:
        for state in workflow.states:
            yield workflow, state


def is_business_aware(definition: ApplicationDefinition) -> bool:
    business = definition.business
    return bool(
        definition.workflow_definitions
        or business.requirements
        or business.roles
        or business.entities
        or business.rules
        or business.exceptions
        or business.decisions
        or business.integrations
    )


def human_destinations(
    workflow: WorkflowDefinition, state_id: str, rule_ids: set[str] | frozenset[str] = frozenset()
) -> list[tuple[tuple[str, ...], str, str | None]]:
    """(conditions, target step, deciding rule) for each step needing a screen that is reachable from `state_id`,
    walking through automated steps. The deciding rule is the last business rule the path branches on."""
    by_id = {state.id: state for state in workflow.states}
    results: list[tuple[tuple[str, ...], str, str | None]] = []

    def walk(source: str, conditions: tuple[str, ...], rule: str | None, seen: frozenset[str]):
        for edge in outgoing(workflow, source):
            condition, deciding = conditions, rule
            if edge.condition.kind != "always":
                operator = "=" if edge.condition.kind == "equals" else "≠"
                condition = conditions + (
                    f"{edge.condition.field} {operator} {edge.condition.value}",
                )
                if edge.condition.field in rule_ids:
                    deciding = edge.condition.field
            target = by_id[edge.target]
            if needs_screen(target):
                if (condition, target.id, deciding) not in results:
                    results.append((condition, target.id, deciding))
            elif target.id not in seen:
                walk(target.id, condition, deciding, seen | {target.id})

    walk(state_id, (), None, frozenset({state_id}))
    return results
