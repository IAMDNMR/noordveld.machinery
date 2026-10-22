"""Bounded local design assistant. Pure functions: no providers, storage, or execution.

Commands are intentionally explicit. Arbitrary model patches are never accepted.
The API recomputes the candidate on apply and binds review to both fingerprints.
"""

from __future__ import annotations

import re

from app.design_studio.approval import digest
from app.design_studio.diff import compare
from app.design_studio.traceability import impact, report
from app.schemas.application_definition import ApplicationDefinition

HELP = (
    'Ask "show processes", "explain STEP_ID", "which requirements are not covered?", '
    '"open decisions", or "impact ITEM_ID". Propose "rename step STEP_ID to LABEL" or '
    '"add exception branch after STEP_ID". '
    "Permission, approval, financial and integration changes require the dedicated review workflow."
)


def respond(
    definition: ApplicationDefinition, message: str
) -> tuple[dict, ApplicationDefinition | None]:
    text = message.strip()
    result = {
        "mode": "local_rules",
        "state": "answer",
        "answer": "",
        "evidence": [],
        "assumptions": [],
        "changes": [],
        "candidate_sha256": None,
        "revision": definition.revision,
        "base_sha256": digest(definition, "design"),
    }
    steps = [
        (workflow, step) for workflow in definition.workflow_definitions for step in workflow.states
    ]
    field_question = re.fullmatch(
        r"(?:explain|explain why) (?:field )?([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)(?: is required)?",
        text,
        re.I,
    )
    if field_question:
        entity = next((e for e in definition.business.entities if e.id == field_question[1]), None)
        attribute = (
            next((a for a in entity.attributes if a.id == field_question[2]), None)
            if entity
            else None
        )
        if attribute:
            result.update(
                answer=f"{entity.name}.{attribute.name} is {'required' if attribute.required else 'optional'} in the saved data model. {attribute.description or 'No business rationale is recorded; confirm it with the owner before changing the requirement.'}",
                detail=attribute.model_dump(mode="json"),
                evidence=[{"kind": "attribute", "reference": f"{entity.id}.{attribute.id}"}],
            )
            return result, None
    branch = re.fullmatch(r"add exception branch after ([a-z][a-z0-9_]*)", text, re.I)
    if branch:
        matches = [(w, s) for w, s in steps if s.id == branch[1]]
        if len(matches) != 1:
            result["answer"] = "Choose a unique step ID from Show processes. Nothing was changed."
            return result, None
        workflow, step = matches[0]
        edges = [edge for edge in workflow.transitions if edge.source == step.id]
        if (
            len(edges) != 1
            or edges[0].condition.kind != "always"
            or step.kind in {"start", "end", "approval", "branch"}
        ):
            result["answer"] = (
                "Choose an activity with one unconditional outgoing path. Existing gateways and approvals require manual design review."
            )
            return result, None
        # IDs derive from content, never random time or an external model. Repeated proposals are equivalent.
        suffix = __import__("hashlib").sha256(f"{workflow.id}/{step.id}".encode()).hexdigest()[:10]
        gate, recovery, decision, output = (
            f"assist_{kind}_{suffix}" for kind in ("gate", "recovery", "decision", "exception")
        )
        if any(s.id in {gate, recovery} for _, s in steps):
            result["answer"] = (
                "An assistant exception branch already exists here. Inspect and edit that branch."
            )
            return result, None
        raw = definition.model_dump(mode="json")
        target = edges[0].target
        draft = next(w for w in raw["workflow_definitions"] if w["id"] == workflow.id)
        next(e for e in draft["transitions"] if e["id"] == edges[0].id)["target"] = gate
        draft["states"].extend(
            [
                {
                    "id": gate,
                    "label": "Exception detected? (policy unresolved)",
                    "kind": "branch",
                    "outputs": [output],
                    "requirement_ids": step.requirement_ids,
                },
                {
                    "id": recovery,
                    "label": "Review exception and recovery (owner unresolved)",
                    "kind": "exception",
                    "requirement_ids": step.requirement_ids,
                },
            ]
        )
        draft["transitions"].extend(
            [
                {
                    "id": f"assist_normal_{suffix}",
                    "source": gate,
                    "target": target,
                    "condition": {"kind": "equals", "field": output, "value": False},
                },
                {
                    "id": f"assist_exception_{suffix}",
                    "source": gate,
                    "target": recovery,
                    "condition": {"kind": "equals", "field": output, "value": True},
                },
                {
                    "id": f"assist_resume_{suffix}",
                    "source": recovery,
                    "target": target,
                    "condition": {"kind": "always"},
                },
            ]
        )
        raw["business"]["decisions"].append(
            {
                "id": decision,
                "question": f"What detects the exception after {step.id}, who may resolve it, and is resuming at {target} correct?",
                "status": "open",
                "affects": step.requirement_ids,
            }
        )
        candidate = ApplicationDefinition.model_validate(raw)
        result.update(
            state="proposed",
            answer="Review an exception-path draft. Detection policy, responsible role and recovery require business decisions before approval.",
            changes=[
                {
                    "path": f"{workflow.id}/{step.id}",
                    "before": f"{step.id} → {target}",
                    "after": f"{step.id} → {gate}; normal → {target}; exception → {recovery} → {target}",
                }
            ],
            assumptions=[
                "Resuming at the original next step is a proposal, not verified policy. No detection threshold or permission is assigned."
            ],
            candidate_sha256=digest(candidate, "design"),
            diff=compare(definition, candidate),
            evidence=[{"kind": "process_step", "reference": f"{workflow.id}/{step.id}"}],
        )
        return result, candidate
    command = re.fullmatch(r"rename step ([a-z][a-z0-9_]*) to (.{1,120})", text, re.I)
    if command:
        step_id, label = command.groups()
        matches = [(workflow, step) for workflow, step in steps if step.id == step_id]
        if len(matches) != 1:
            result["answer"] = "Choose a unique step ID from Show processes. Nothing was changed."
            return result, None
        workflow, step = matches[0]
        raw = definition.model_dump(mode="json")
        for item in raw["workflow_definitions"]:
            if item["id"] == workflow.id:
                for state in item["states"]:
                    if state["id"] == step_id:
                        state["label"] = label.strip()
        candidate = ApplicationDefinition.model_validate(raw)
        if digest(candidate, "design") == result["base_sha256"]:
            result["answer"] = "This step already has that label. Nothing was changed."
            return result, None
        result.update(
            state="proposed",
            answer="Review this draft label change. Applying it saves a new revision; it does not deploy anything.",
            changes=[
                {
                    "path": f"{workflow.id}/{step.id}/label",
                    "before": step.label,
                    "after": label.strip(),
                }
            ],
            candidate_sha256=digest(candidate, "design"),
            impact=impact(definition, step.id),
            approval_effect="Process and design approvals become stale when their content changes.",
            diff=compare(definition, candidate),
        )
        result["evidence"] = [{"kind": "process_step", "reference": f"{workflow.id}/{step.id}"}]
        return result, candidate
    if text.lower().startswith("explain "):
        step_id = text[8:].strip()
        matches = [(workflow, step) for workflow, step in steps if step.id == step_id]
        if len(matches) == 1:
            workflow, step = matches[0]
            edges = [
                edge.model_dump(mode="json")
                for edge in workflow.transitions
                if edge.source == step.id
            ]
            result.update(
                answer=f"{step.label}: {step.kind}. Responsible role: {step.role_id or 'unassigned'}. Required permission: {step.permission or 'not specified'}.",
                detail={"step": step.model_dump(mode="json"), "next_paths": edges},
                evidence=[
                    {"kind": "process_step", "reference": f"{workflow.id}/{step.id}"},
                    *[{"kind": "business_rule", "reference": rule} for rule in step.rule_ids],
                    *[{"kind": "requirement", "reference": req} for req in step.requirement_ids],
                ],
            )
            return result, None
    if text.lower().startswith("impact "):
        found = impact(definition, text[7:].strip())
        if found:
            result.update(
                answer="These artifacts depend on the selected item and need review after a change.",
                detail=found,
            )
            return result, None
    if "requirement" in text.lower():
        trace = report(definition)
        result.update(
            answer="Coverage is derived from linked process steps and screens; it is not proof of production implementation.",
            detail={
                key: trace[key]
                for key in (
                    "covered_requirements",
                    "requirements_without_process",
                    "requirements_without_screens",
                )
            },
            evidence=[
                {"kind": "requirement", "reference": req.id}
                for req in definition.business.requirements
            ],
        )
        return result, None
    if "decision" in text.lower():
        result.update(
            answer="These business decisions remain unresolved. The assistant does not choose company policy.",
            detail=report(definition)["unresolved_decisions"],
        )
        return result, None
    if "process" in text.lower() or "warehouse" in text.lower() or "transport" in text.lower():
        result.update(
            answer="Saved process definitions and their explicit paths. Select a step ID with Explain to inspect its rules and permissions.",
            detail=[
                {
                    "id": w.id,
                    "name": w.name,
                    "steps": [{"id": s.id, "label": s.label, "kind": s.kind} for s in w.states],
                    "paths": [edge.model_dump(mode="json") for edge in w.transitions],
                }
                for w in definition.workflow_definitions
            ],
            evidence=[{"kind": "process_step", "reference": f"{w.id}/{s.id}"} for w, s in steps],
        )
        return result, None
    result["answer"] = HELP
    return result, None
