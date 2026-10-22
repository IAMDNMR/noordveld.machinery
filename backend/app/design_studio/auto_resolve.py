"""Settle, in one pass and without a language model, the validation findings whose resolution is a recorded fact of the design.

Nothing is deleted to make a warning go away and no business policy is decided. A rule, role or exception that nobody has
confirmed stays visible for a person. What this settles:

* a draft requirement that a process step already serves is agreed (it is in scope: the design implements it);
* an optional detail the Studio asks every project (accessibility standard, volumes...) is recorded as "not specified";
* a record that others must point at (an item, a warehouse) and that nobody maintains is given to the role whose steps use it most,
  because without a maintainer the records that need it can never be created. The assignment is reported and can be changed;
* a step repeated directly after itself (same name, kind and role; a model drafting artefact) is folded into the first, keeping
  every record it reads or writes and every rule and exception it handles.
"""

from __future__ import annotations

from collections import Counter

from app.design_studio import guided
from app.design_studio.completeness import unmaintained_reference_data
from app.schemas.application_definition import ApplicationDefinition

# Questions that never block anything and that most first versions leave open; the others (systems, outcomes) stay for a person.
OPTIONAL_QUESTIONS = {"q_security", "q_accessibility", "q_performance", "q_constraints"}
NOT_SPECIFIED = "Not specified for this version."


def assign_owners(raw: dict, definition: ApplicationDefinition) -> list[str]:
    """Give each record others must point at, and nobody maintains, to the role whose steps use it most. Edits `raw`; returns the changes."""
    business, changes = raw["business"], []
    for entity in unmaintained_reference_data(definition):
        users = Counter(
            state["role_id"]
            for workflow in raw["workflow_definitions"]
            for state in workflow["states"]
            if state.get("role_id")
            and (
                entity.id in [*state.get("reads_entity_ids", []), *state.get("writes_entity_ids", [])]
                or any(
                    relationship["target"] == entity.id
                    for other in business["entities"]
                    if other["id"] in state.get("writes_entity_ids", [])
                    for relationship in other.get("relationships", [])
                )
            )
        )
        if users:
            owner = users.most_common(1)[0][0]
            next(e for e in business["entities"] if e["id"] == entity.id)["owner_role_id"] = owner
            name = next(r["name"] for r in business["roles"] if r["id"] == owner)
            changes.append(f"{name} now maintains {entity.name} (other records must point at it)")
    return changes


def resolve(definition: ApplicationDefinition) -> tuple[ApplicationDefinition, list[str]]:
    """Return the definition with every safe fact recorded, and one plain sentence per change."""
    raw = definition.model_dump(mode="json")
    business = raw["business"]
    served = {
        requirement
        for workflow in raw["workflow_definitions"]
        for state in workflow["states"]
        for requirement in state.get("requirement_ids") or []
    }
    changes: list[str] = []
    for requirement in business["requirements"]:
        if requirement["status"] == "draft" and requirement["id"] in served:
            requirement["status"] = "agreed"
            changes.append(f"Agreed requirement (a process step implements it): {requirement['statement']}")
    for question in business["questions"]:
        if question["status"] == "open" and question["id"] in OPTIONAL_QUESTIONS:
            question["status"], question["answer"] = "not_applicable", NOT_SPECIFIED
            changes.append(f"Recorded as not specified for this version: {question['text']}")
    changes.extend(assign_owners(raw, definition))
    for workflow in raw["workflow_definitions"]:
        changes.extend(f"Merged a repeated step: {workflow['name']} · {label}" for label in _fold_repeats(workflow))
    if not changes:
        return definition, []
    resolved = ApplicationDefinition.model_validate(raw)
    # Settling findings is part of validation, not a new draft: stages that were reviewed stay reviewed.
    flow = definition.studio_flow
    if flow is not None:
        kept = guided.reviewed(definition)
        digests = {stage: guided.stage_digest(resolved, stage) for stage in kept}
        resolved = resolved.model_copy(
            update={"studio_flow": flow.model_copy(update={"reviewed": kept, "reviewed_digests": digests})}
        )
    return resolved, changes


def _fold_repeats(workflow: dict) -> list[str]:
    """Fold a step into the step it duplicates and joins directly. Returns the labels folded."""
    folded = []
    changed = True
    while changed:
        changed = False
        states = {state["id"]: state for state in workflow["states"]}
        for edge in workflow["transitions"]:
            first, second = states.get(edge["source"]), states.get(edge["target"])
            if (
                first is None
                or second is None
                or first is second
                or first["kind"] in ("start", "end")
                or (first["label"].strip().lower(), first["kind"], first.get("role_id"))
                != (second["label"].strip().lower(), second["kind"], second.get("role_id"))
            ):
                continue
            for key in ("reads_entity_ids", "writes_entity_ids", "rule_ids", "exception_ids", "requirement_ids"):
                first[key] = list(dict.fromkeys([*first.get(key, []), *second.get(key, [])]))
            workflow["transitions"] = [
                {**t, "source": first["id"] if t["source"] == second["id"] else t["source"],
                 "target": first["id"] if t["target"] == second["id"] else t["target"]}
                for t in workflow["transitions"]
            ]
            workflow["transitions"] = [t for t in workflow["transitions"] if t["source"] != t["target"]]
            seen, unique = set(), []
            for t in workflow["transitions"]:
                key = (t["source"], t["target"], str(t["condition"]))
                if key not in seen:
                    seen.add(key)
                    unique.append(t)
            workflow["transitions"] = unique
            workflow["states"] = [state for state in workflow["states"] if state["id"] != second["id"]]
            folded.append(first["label"])
            changed = True
            break
    return folded
