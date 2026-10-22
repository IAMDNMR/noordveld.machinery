"""Deterministic completeness and consistency analysis of a whole design.

Structural integrity (duplicate IDs, dangling references) is already enforced by the schema; this module judges whether
the design is complete enough to approve. Errors block approval and generation; warnings must be acknowledged when
approving; info is reported only. Finding IDs are stable: `<code>:<artefact>`.
"""

from __future__ import annotations

from app.design_studio import approval
from app.design_studio.knowledge.provider import KnowledgeProvider, stale_items
from app.design_studio.process import human_destinations, needs_screen, outgoing, steps
from app.schemas.application_definition import ApplicationDefinition, Component

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

# Per finding code: the kind of issue, the editor tab that resolves it, and why it matters.
# "defect" is a gap in the design; "business_decision" needs the business owner; "assumption" is unconfirmed policy.
EXPLANATIONS: dict[str, tuple[str, str, str]] = {
    "PROCESS_MISSING": (
        "defect",
        "workflow",
        "Screens and artefacts are derived from the process; without one nothing can be generated.",
    ),
    "REQUIREMENTS_MISSING": (
        "defect",
        "brief",
        "Without requirements nothing can be checked or traced.",
    ),
    "GOAL_MISSING": ("defect", "brief", "The goal is what reviewers approve the design against."),
    "NFR_MISSING": (
        "defect",
        "brief",
        "Security, accessibility and audit needs are easy to miss and costly to add later.",
    ),
    "REQ_DEFERRAL_REASON": (
        "defect",
        "brief",
        "A deferral without a reason cannot be reviewed or revisited.",
    ),
    "REQ_NO_CRITERIA": (
        "defect",
        "brief",
        "Without acceptance criteria nobody can tell whether the requirement is met.",
    ),
    "REQ_DRAFT": (
        "information",
        "brief",
        "Draft requirements have not been agreed; approving proceeds on unagreed scope.",
    ),
    "REQ_UNCOVERED": (
        "defect",
        "workflow",
        "A requirement no step satisfies will not appear in the application.",
    ),
    "QUESTION_OPEN": (
        "information",
        "brief",
        "An unanswered question may hide a missing requirement.",
    ),
    "DECISION_OPEN": (
        "business_decision",
        "rules",
        "Only the business owner can decide this; the design must not assume an answer.",
    ),
    "DECISION_NO_ANSWER": (
        "business_decision",
        "rules",
        "A decision marked decided needs the actual decision recorded.",
    ),
    "DECISION_DEFERRAL_REASON": (
        "business_decision",
        "rules",
        "A deferral without a reason cannot be reviewed or revisited.",
    ),
    "DECISION_DEFERRED": (
        "business_decision",
        "rules",
        "The design proceeds without this decision; the gap stays visible in every report.",
    ),
    "RULE_ASSUMPTION": (
        "assumption",
        "rules",
        "An unconfirmed rule may not be the real policy; it must not be presented as approved.",
    ),
    "RULE_UNUSED": (
        "information",
        "rules",
        "A rule no step applies has no effect on the application.",
    ),
    "EXCEPTION_NO_RESOLUTION": (
        "defect",
        "rules",
        "An exception without recovery, termination or escalation leaves the process undefined when it happens.",
    ),
    "EXCEPTION_UNHANDLED": (
        "defect",
        "workflow",
        "An exception no step handles will not be shown or recovered from.",
    ),
    "ESCALATION_NO_AUTHORITY": (
        "defect",
        "rules",
        "Escalating to someone without approval authority does not resolve the exception.",
    ),
    "ENTITY_NO_KEY": (
        "defect",
        "data",
        "Records without a key cannot be referenced or updated reliably.",
    ),
    "ENTITY_UNUSED": (
        "information",
        "data",
        "An entity no step reads or writes has no effect on the application.",
    ),
    "REFERENCE_NO_OWNER": (
        "information",
        "roles",
        "A record other records must point at (an item, a warehouse) cannot be created if no role maintains it, so those records cannot be created either.",
    ),
    "PROCESS_OVERLAP": (
        "information",
        "workflow",
        "Two processes for the same business activity make people do it twice and split its records and requirements between them.",
    ),
    "STEP_REPEATED": (
        "information",
        "workflow",
        "The same step twice in a row makes the person do the same work twice.",
    ),
    "ROLE_UNUSED": (
        "information",
        "roles",
        "A role with no steps has no responsibilities in the process.",
    ),
    "STEP_NO_ROLE": ("defect", "workflow", "A step without an owner is nobody's job."),
    "STEP_NO_REQUIREMENT": (
        "defect",
        "workflow",
        "A step that serves no requirement cannot be traced or justified.",
    ),
    "END_NO_OUTCOME": (
        "defect",
        "workflow",
        "Reports need to know whether an end is a success, failure or cancellation.",
    ),
    "EXCEPTION_STEP_NO_SCENARIO": (
        "defect",
        "workflow",
        "The screen for this step cannot explain what went wrong.",
    ),
    "BRANCH_INCOMPLETE": ("defect", "workflow", "A decision with one path is not a decision."),
    "BRANCH_MIXED": (
        "defect",
        "workflow",
        "Mixing conditional and unconditional paths makes the route ambiguous.",
    ),
    "CONDITION_OPAQUE": (
        "defect",
        "workflow",
        "A branch on an undefined output has no business meaning to review.",
    ),
    "OUTCOME_UNHANDLED": (
        "defect",
        "workflow",
        "A decision outcome without a path leaves the process stuck.",
    ),
    "STEP_PERMISSION": ("defect", "workflow", "The responsible role could not perform the step."),
    "WRITE_NO_PERMISSION": (
        "defect",
        "workflow",
        "Data a person can change needs an explicit authorization check.",
    ),
    "SENSITIVE_NO_PERMISSION": (
        "defect",
        "workflow",
        "Personal or confidential data must only be shown or changed under a permission.",
    ),
    "INTEGRATION_DEFERRED": (
        "information",
        "rules",
        "The integration's contract is not defined yet; nothing depending on it can be generated.",
    ),
    "INTEGRATION_NO_FAILURE": (
        "defect",
        "rules",
        "A defined integration must say what happens when the other system fails.",
    ),
    "KNOWLEDGE_STALE": (
        "information",
        "knowledge",
        "The reference this item came from has changed; the copy may be out of date.",
    ),
    "STEP_NO_SCREEN": (
        "defect",
        "approval",
        "A person acts at this step but has no screen to do it on.",
    ),
    "SCREEN_NO_TRACE": (
        "information",
        "screen",
        "A screen not linked to a step cannot be traced to a requirement.",
    ),
    "COMPONENT_NO_TRACE": (
        "defect",
        "screen",
        "A generated component without a trace cannot be traced back to the specification.",
    ),
    "ACTION_NOT_IN_PROCESS": (
        "defect",
        "screen",
        "A screen action must follow a real process transition, or the application does something the process does not allow.",
    ),
    "SYSTEM_FIELD_EDITABLE": (
        "defect",
        "screen",
        "System-managed values must not be typed in by users.",
    ),
    "FIELD_VALIDATION_MISSING": (
        "defect",
        "screen",
        "An input must enforce the rules its attribute declares.",
    ),
    "PROCESS_NOT_APPROVED": (
        "defect",
        "approval",
        "Screens must be approved against the process that is approved.",
    ),
}


class Findings:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, code: str, severity: str, artefacts: list[str], message: str, remediation: str):
        category, tab, why = EXPLANATIONS[code]
        self.items.append(
            {
                "id": f"{code}:{'+'.join(artefacts) or 'design'}",
                "code": code,
                "severity": severity,
                "category": category,
                "artefacts": artefacts,
                "message": message,
                "remediation": remediation,
                "rationale": why,
                "tab": tab,
            }
        )


def _walk(nodes: list[Component]):
    for node in nodes:
        yield node
        yield from _walk(node.children or [])


def unmaintained_reference_data(definition: ApplicationDefinition):
    """Entities that other entities require a link to, that no step writes, that have no owner role, and that come from no import."""
    business = definition.business
    written = {entity_id for _, state in steps(definition) for entity_id in state.writes_entity_ids}
    imported = {ref for integration in business.integrations for ref in integration.entity_ids}
    required = {
        relationship.target
        for entity in business.entities
        for relationship in entity.relationships
        if relationship.required and relationship.target != entity.id
    }
    return [
        entity
        for entity in business.entities
        if entity.id in required and entity.id not in written | imported and not entity.owner_role_id
    ]


def analyze(
    definition: ApplicationDefinition,
    provider: KnowledgeProvider | None = None,
    scope: str = "design",
) -> dict:
    found = Findings()
    business = definition.business
    rules = {rule.id: rule for rule in business.rules}
    roles = {role.id: role for role in business.roles}
    referenced: dict[str, set[str]] = {
        "requirement": set(),
        "rule": set(),
        "exception": set(),
        "entity": set(),
        "role": set(),
    }
    for _, state in steps(definition):
        referenced["requirement"].update(state.requirement_ids)
        referenced["rule"].update(state.rule_ids)
        referenced["exception"].update(state.exception_ids)
        referenced["entity"].update(state.reads_entity_ids + state.writes_entity_ids)
        if state.role_id:
            referenced["role"].add(state.role_id)
    for workflow in definition.workflow_definitions:
        referenced["rule"].update(
            edge.condition.field for edge in workflow.transitions if edge.condition.field in rules
        )

    # ── scope of the brief and the process ──
    if not definition.workflow_definitions:
        found.add(
            "PROCESS_MISSING",
            "error",
            [],
            "The design has no business process.",
            "Apply a reference pack or create a process on the Process tab.",
        )
    if not business.requirements:
        found.add(
            "REQUIREMENTS_MISSING",
            "error",
            [],
            "No requirements are recorded.",
            "Add at least one requirement with acceptance criteria.",
        )
    if not business.brief.goal.strip():
        found.add(
            "GOAL_MISSING",
            "warning",
            [],
            "The business goal is empty.",
            "Describe the goal in the brief.",
        )
    if business.requirements and not any(
        item.kind == "non_functional" for item in business.requirements
    ):
        found.add(
            "NFR_MISSING",
            "warning",
            [],
            "No non-functional requirements (security, accessibility, auditability…) are recorded.",
            "Add the non-functional requirements that apply, or note that none do.",
        )

    for requirement in business.requirements:
        artefact = [requirement.id]
        if requirement.status == "deferred" and not requirement.deferral_reason.strip():
            found.add(
                "REQ_DEFERRAL_REASON",
                "error",
                artefact,
                f"Deferred requirement '{requirement.id}' has no deferral reason.",
                "Record why it is deferred.",
            )
        if requirement.status in ("draft", "agreed"):
            if not requirement.acceptance_criteria:
                found.add(
                    "REQ_NO_CRITERIA",
                    "error",
                    artefact,
                    f"Requirement '{requirement.id}' has no acceptance criteria.",
                    "Add acceptance criteria, or defer it with a reason.",
                )
            if requirement.status == "draft":
                found.add(
                    "REQ_DRAFT",
                    "warning",
                    artefact,
                    f"Requirement '{requirement.id}' is still a draft.",
                    "Agree, defer or reject it.",
                )
            if requirement.id not in referenced["requirement"]:
                severity = "error" if requirement.priority == "must" else "warning"
                found.add(
                    "REQ_UNCOVERED",
                    severity,
                    artefact,
                    f"Requirement '{requirement.id}' is not satisfied by any process step.",
                    "Link it to the steps that satisfy it.",
                )

    for question in business.questions:
        if question.status == "open":
            optional = question.id in {"q_outcomes", "q_security", "q_accessibility", "q_performance", "q_constraints"}
            found.add(
                "QUESTION_OPEN",
                "info" if optional else "warning",
                [question.id],
                f"{'Optional detail not specified' if optional else 'Unanswered question'}: {question.text}",
                "Answer it or mark it not applicable.",
            )

    for decision in business.decisions:
        artefact = [decision.id]
        if decision.status == "open":
            found.add(
                "DECISION_OPEN",
                "error",
                artefact,
                f"Business decision needed: {decision.question}",
                "The business owner decides it, or it is explicitly deferred with a reason.",
            )
        elif decision.status == "decided" and not decision.answer.strip():
            found.add(
                "DECISION_NO_ANSWER",
                "error",
                artefact,
                f"Decision '{decision.id}' is marked decided without an answer.",
                "Record the decision.",
            )
        elif decision.status == "deferred":
            if not decision.deferral_reason.strip():
                found.add(
                    "DECISION_DEFERRAL_REASON",
                    "error",
                    artefact,
                    f"Deferred decision '{decision.id}' has no reason.",
                    "Record why it is deferred.",
                )
            else:
                found.add(
                    "DECISION_DEFERRED",
                    "warning",
                    artefact,
                    f"Decision deferred: {decision.question}",
                    "Acknowledge that the design proceeds without this decision.",
                )

    for rule in business.rules:
        if rule.status == "assumption":
            found.add(
                "RULE_ASSUMPTION",
                "warning",
                [rule.id],
                f"{'Blueprint default needs project confirmation' if rule.origin else 'Rule needs confirmation'}: {rule.description} Source: {rule.source.reference}",
                "Confirm it with the business owner or replace it.",
            )
        if rule.id not in referenced["rule"]:
            found.add(
                "RULE_UNUSED",
                "info",
                [rule.id],
                f"Rule '{rule.id}' is not applied by any step or condition.",
                "Link it to a step, or remove it.",
            )

    step_roles = {state.id: state.role_id for _, state in steps(definition)}
    for exception in business.exceptions:
        if exception.resolution == "escalate":
            target_role = roles.get(step_roles.get(exception.resolution_state_id) or "")
            if target_role is None or not target_role.approval_authority:
                found.add(
                    "ESCALATION_NO_AUTHORITY",
                    "warning",
                    [exception.id],
                    f"Exception '{exception.id}' escalates to a step whose role has no approval authority.",
                    "Escalate to a step owned by a role with authority, or record that authority on the role.",
                )
        if exception.resolution is None:
            found.add(
                "EXCEPTION_NO_RESOLUTION",
                "error",
                [exception.id],
                f"Exception '{exception.id}' has no recovery or terminal outcome.",
                "Set where the process recovers to or ends.",
            )
        if exception.id not in referenced["exception"]:
            found.add(
                "EXCEPTION_UNHANDLED",
                "warning",
                [exception.id],
                f"Exception '{exception.id}' is not handled by any step.",
                "Link it to the step where it can occur.",
            )

    connected = set(referenced["entity"])
    pending_entities = list(connected)
    by_entity = {entity.id: entity for entity in business.entities}
    while pending_entities:
        source = by_entity.get(pending_entities.pop())
        for relation in source.relationships if source else []:
            if relation.target not in connected:
                connected.add(relation.target)
                pending_entities.append(relation.target)
    for entity in business.entities:
        if not any(attribute.key for attribute in entity.attributes):
            found.add(
                "ENTITY_NO_KEY",
                "warning",
                [entity.id],
                f"Entity '{entity.id}' has no key attribute.",
                "Mark the attribute that identifies a record.",
            )
        if entity.id not in connected:
            found.add(
                "ENTITY_UNUSED",
                "info",
                [entity.id],
                f"Entity '{entity.id}' is not read or written by any step.",
                "Link it to steps, or remove it.",
            )

    if provider is not None and scope == "design":
        from app.design_studio.process_overlap import find_overlaps

        names = {w.id: w.name for w in definition.workflow_definitions}
        for overlap in find_overlaps(definition, provider):
            found.add(
                "PROCESS_OVERLAP",
                "warning",
                [overlap["duplicate"], overlap["keep"]],
                f"Process '{names[overlap['duplicate']]}' {'duplicates' if overlap['approved'] else 'may duplicate'} the verified process '{names[overlap['keep']]}'. {overlap['because']}",
                "Merge it into the verified process, or keep it if it is a different activity."
                if not overlap["approved"]
                else "Merge it into the verified process.",
            )

    for workflow in definition.workflow_definitions:
        by_id = {state.id: state for state in workflow.states}
        for edge in workflow.transitions:
            first, second = by_id.get(edge.source), by_id.get(edge.target)
            if (
                first
                and second
                and first.id != second.id
                and first.kind not in ("start", "end")
                and (first.label.strip().lower(), first.kind, first.role_id)
                == (second.label.strip().lower(), second.kind, second.role_id)
            ):
                found.add(
                    "STEP_REPEATED",
                    "info",
                    [f"{workflow.id}/{second.id}"],
                    f"Step '{second.label}' repeats the step before it in '{workflow.name}'.",
                    "Merge the two steps.",
                )

    for entity in unmaintained_reference_data(definition):
        found.add(
            "REFERENCE_NO_OWNER",
            "warning",
            [entity.id],
            f"Nobody maintains '{entity.name}', but other records must point at one.",
            "Give a role the job of maintaining it.",
        )

    for integration in business.integrations:
        if integration.contract_status == "deferred":
            found.add(
                "INTEGRATION_DEFERRED",
                "info" if integration.failure_handling.strip() else "warning",
                [integration.id],
                f"Integration '{integration.name}' is explicitly deferred. {integration.failure_handling}" if integration.failure_handling.strip() else f"Integration '{integration.name}' has no defined contract yet.",
                "Define the exchange, its data and failure handling, or keep it explicitly deferred.",
            )
        elif not integration.failure_handling.strip():
            found.add(
                "INTEGRATION_NO_FAILURE",
                "error",
                [integration.id],
                f"Integration '{integration.name}' does not say what happens when {integration.system} fails.",
                "Describe the failure handling.",
            )

    for role in business.roles:
        if role.id not in referenced["role"]:
            found.add(
                "ROLE_UNUSED",
                "info",
                [role.id],
                f"Role '{role.id}' has no process step.",
                "Assign it to steps, or remove it.",
            )

    for workflow, state in steps(definition):
        artefact = [f"{workflow.id}/{state.id}"]
        edges = outgoing(workflow, state.id)
        if state.kind not in ("start", "end") and state.role_id is None:
            found.add(
                "STEP_NO_ROLE",
                "error",
                artefact,
                f"Step '{state.label}' has no responsible role.",
                "Assign the role that performs it.",
            )
        if state.kind not in ("start", "end") and not state.requirement_ids:
            found.add(
                "STEP_NO_REQUIREMENT",
                "warning",
                artefact,
                f"Step '{state.label}' does not satisfy any requirement.",
                "Link the requirements it serves.",
            )
        if state.kind == "end" and state.outcome is None:
            found.add(
                "END_NO_OUTCOME",
                "warning",
                artefact,
                f"End '{state.label}' does not say whether it is a success, failure or cancellation.",
                "Set the end outcome.",
            )
        if state.kind == "exception" and not state.exception_ids:
            found.add(
                "EXCEPTION_STEP_NO_SCENARIO",
                "warning",
                artefact,
                f"Exception step '{state.label}' names no exception scenario.",
                "Link the scenarios it handles.",
            )
        if state.kind == "branch" and len(edges) < 2:
            found.add(
                "BRANCH_INCOMPLETE",
                "error",
                artefact,
                f"Decision '{state.label}' has fewer than two outgoing paths.",
                "Add a path for each outcome.",
            )
        conditional = [edge for edge in edges if edge.condition.kind != "always"]
        if conditional and len(conditional) != len(edges):
            found.add(
                "BRANCH_MIXED",
                "warning",
                artefact,
                f"Step '{state.label}' mixes conditional and unconditional paths.",
                "Make every path conditional, or none.",
            )
        for edge in conditional:
            if edge.condition.field not in rules:
                found.add(
                    "CONDITION_OPAQUE",
                    "warning",
                    [f"{workflow.id}/{edge.id}"],
                    f"Transition '{edge.id}' branches on '{edge.condition.field}', which is not a business rule.",
                    "Branch on a decision rule's outcome instead.",
                )
        for output in state.outputs:
            rule = rules.get(output)
            if rule is None or not rule.outcomes:
                continue
            handled = {
                str(edge.condition.value)
                for edge in edges
                if edge.condition.field == output and edge.condition.kind == "equals"
            }
            missing = [outcome for outcome in rule.outcomes if outcome not in handled]
            if missing and not any(
                edge.condition.kind == "not_equals" and edge.condition.field == output
                for edge in edges
            ):
                found.add(
                    "OUTCOME_UNHANDLED",
                    "error",
                    [f"{workflow.id}/{state.id}"],
                    f"Step '{state.label}' has no path for {rule.id} = {', '.join(missing)}.",
                    "Add a transition for each outcome.",
                )
        if (
            state.permission
            and state.role_id
            and state.permission not in roles[state.role_id].permissions
        ):
            found.add(
                "STEP_PERMISSION",
                "error",
                artefact,
                f"Step '{state.label}' requires '{state.permission}', which its role does not hold.",
                "Grant it to the role or change the step.",
            )
        if needs_screen(state) and state.permission is None:
            entities = {entity.id: entity for entity in business.entities}
            writable = [
                entity_id
                for entity_id in state.writes_entity_ids
                if any(not a.system_managed and a.writable for a in entities[entity_id].attributes)
            ]
            if writable:
                found.add(
                    "WRITE_NO_PERMISSION",
                    "warning",
                    artefact,
                    f"Step '{state.label}' lets a person change {', '.join(writable)} without a required permission.",
                    "Set the permission the step requires.",
                )
            sensitive = sorted(
                {
                    entity_id
                    for entity_id in state.reads_entity_ids + state.writes_entity_ids
                    if any(
                        a.sensitivity in ("personal", "confidential")
                        for a in entities[entity_id].attributes
                    )
                }
            )
            if sensitive:
                found.add(
                    "SENSITIVE_NO_PERMISSION",
                    "warning",
                    artefact,
                    f"Step '{state.label}' shows personal or confidential data ({', '.join(sensitive)}) without a required permission.",
                    "Set the permission the step requires.",
                )

    if provider is not None:
        for item in stale_items(definition, provider):
            current = item["current_version"] or "unavailable"
            found.add(
                "KNOWLEDGE_STALE",
                "warning",
                [item["item_id"]],
                f"'{item['item_id']}' came from {item['pack_id']} {item['pack_version']}; the pack is now {current}.",
                "Review the item against the current reference pack.",
            )

    if scope == "design":
        # A model-generated interface must declare a page for every step. Without one, the schema-driven client gives every step
        # its screen (the process board and the step's own action page), so there is nothing to check.
        screened = {
            tuple(step.split("/", 1))
            for page in (definition.generated_frontend.pages if definition.generated_frontend else [])
            for step in page.step_ids
        }
        for workflow, state in steps(definition) if definition.generated_frontend else []:
            if needs_screen(state) and (workflow.id, state.id) not in screened:
                found.add(
                    "STEP_NO_SCREEN",
                    "error",
                    [f"{workflow.id}/{state.id}"],
                    f"Step '{state.label}' needs a screen but has none.",
                    "Generate the application's interface in Screens & UI.",
                )
        # Without a generated interface the screens are derived from the process, so stored screens are not shown to anyone.
        if definition.workflow_definitions and definition.generated_frontend:
            for screen in definition.screens:
                if screen.trace is None or screen.trace.step_id is None:
                    found.add(
                        "SCREEN_NO_TRACE",
                        "warning",
                        [screen.id],
                        f"Screen '{screen.title}' is not linked to a process step.",
                        "Remove it, or keep it as an intentional extra screen.",
                    )
        attributes = {
            (entity.id, attribute.id): attribute
            for entity in business.entities
            for attribute in entity.attributes
        }
        workflows = {workflow.id: workflow for workflow in definition.workflow_definitions}
        screen_step = {
            screen.id: (screen.trace.workflow_id, screen.trace.step_id)
            for screen in definition.screens
            if screen.trace and screen.trace.step_id
        }
        for screen in definition.screens:
            origin = screen_step.get(screen.id)
            allowed = set()
            if origin and origin[0] in workflows:
                allowed = {
                    target
                    for _, target, _ in human_destinations(
                        workflows[origin[0]], origin[1], set(rules)
                    )
                }
            for node in _walk(screen.components):
                if screen.trace and screen.trace.generated and node.trace is None:
                    found.add(
                        "COMPONENT_NO_TRACE",
                        "warning",
                        [f"{screen.id}/{node.id}"],
                        f"Component '{node.id}' on generated screen '{screen.title}' has no trace.",
                        "Regenerate the screen or link the component.",
                    )
                for event in node.events or []:
                    if event.action == "navigate" and origin:
                        target = screen_step.get(event.target)
                        if target is None or target[0] != origin[0] or target[1] not in allowed:
                            found.add(
                                "ACTION_NOT_IN_PROCESS",
                                "error",
                                [f"{screen.id}/{node.id}"],
                                f"Button '{node.props.get('label', node.id)}' on '{screen.title}' leads somewhere the process does not go from this step.",
                                "Point it at a screen the process reaches next, or change the process.",
                            )
                if (
                    node.kind == "field"
                    and node.trace
                    and node.trace.entity_id
                    and node.trace.attribute_id
                ):
                    attribute = attributes.get((node.trace.entity_id, node.trace.attribute_id))
                    if attribute is None:
                        continue
                    if attribute.system_managed or not attribute.writable:
                        found.add(
                            "SYSTEM_FIELD_EDITABLE",
                            "error",
                            [f"{screen.id}/{node.id}"],
                            f"'{attribute.name}' is {attribute.value_source.replace('_', ' ')} but appears as an input on '{screen.title}'.",
                            "Show it as a read-only value; regenerating the screen fixes it.",
                        )
                    kinds = {rule["kind"] for rule in node.props.get("validations", [])}
                    missing = [
                        kind
                        for kind, needed in (
                            ("required", attribute.required),
                            ("email", attribute.format == "email"),
                            ("minimum", attribute.minimum is not None),
                            ("maximum", attribute.maximum is not None),
                        )
                        if needed and kind not in kinds
                    ]
                    if missing:
                        found.add(
                            "FIELD_VALIDATION_MISSING",
                            "error",
                            [f"{screen.id}/{node.id}"],
                            f"Input '{attribute.name}' on '{screen.title}' does not enforce: {', '.join(missing)}.",
                            "Restore the validations, or regenerate the screen.",
                        )
        if not approval.is_valid(definition, "process"):
            found.add(
                "PROCESS_NOT_APPROVED",
                "error",
                [],
                "The process is not approved in its current form.",
                "Approve the process before approving the screens.",
            )

    items = sorted(found.items, key=lambda item: (SEVERITY_ORDER[item["severity"]], item["id"]))
    counts = {
        severity: sum(1 for item in items if item["severity"] == severity)
        for severity in SEVERITY_ORDER
    }
    return {"scope": scope, "findings": items, "counts": counts, "blocking": counts["error"] > 0}
