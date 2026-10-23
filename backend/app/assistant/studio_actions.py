"""The typed actions the Design Studio agent can take, and the deterministic engine that applies them.

The agent (a language model, or the local rules) only ever *names* actions from this closed vocabulary. It never writes a patch,
an identifier of its own, a permission, or JSON for the schema. This module resolves every reference against the saved
specification, builds the item with the same Pydantic models the structured editor uses, and validates the whole candidate.
An action that cannot be applied is rejected with a reason; the rest still apply. Nothing here stores anything.

Impact decides whether a turn may apply an action directly or must show it for review first (`REVIEW_ACTIONS`).
"""

from __future__ import annotations

from typing import Annotated, Any, Callable, Literal
import re

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from app.design_studio.knowledge.provider import (
    KnowledgeProvider,
    PackConflict,
    PackUnavailable,
    apply_pack,
)
from app.schemas.application_definition import ApplicationDefinition, RuleExecution, RuleSource, ScreenSection


class ActionError(ValueError):
    """The action cannot be applied to this specification. The message is shown to the user."""


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


Text = Annotated[str, Field(min_length=1, max_length=300)]
LongText = Annotated[str, Field(min_length=1, max_length=1000)]


SECTION_NAMES = {
    "stats": "the number cards",
    "pipelines": "the where-work-is overview",
    "steps": "the step list",
    "exceptions": "the when-something-goes-wrong list",
    "records": "the records a process produces",
    "finished": "recently finished work",
}
# The colours the Screens stage offers by name, and the plain words people use for them in chat.
THEME_COLOURS = {
    "forest green": "#24583e", "ocean blue": "#245f8b", "indigo": "#5b4bb1",
    "teal": "#0c6b70", "copper": "#9a4f28", "slate": "#37475b",
}
COLOUR_WORDS = {
    "blue": "#245f8b", "green": "#24583e", "purple": "#5b4bb1", "violet": "#5b4bb1", "orange": "#b8570f",
    "brown": "#9a4f28", "grey": "#37475b", "gray": "#37475b", "red": "#a33a32", "pink": "#a8427a",
    "yellow": "#9a7b0a", "black": "#1f2933",
}


def colour_hex(value: Any) -> str | None:
    """A #RRGGBB code for what the model sent as the colour (a code, a menu name or a plain word like "blue"), or None."""
    text = str(value or "").strip().lower()
    if re.fullmatch(r"#?[0-9a-f]{6}", text):
        return "#" + text.lstrip("#")
    if not re.fullmatch(r"[a-z ]{1,30}", text):
        return None  # only plain colour words; anything with punctuation (CSS, markup) is not a colour name
    names = {**COLOUR_WORDS, **THEME_COLOURS}
    return names.get(text) or next((code for word, code in names.items() if word in text), None)


class SetTheme(Strict):
    type: Literal["set_theme"]
    primary: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class SetScreenSections(Strict):
    type: Literal["set_screen_sections"]
    hide: list[ScreenSection] = Field(default_factory=list, max_length=6)
    show: list[ScreenSection] = Field(default_factory=list, max_length=6)


class SetBrief(Strict):
    type: Literal["set_brief"]
    name: Annotated[str, Field(max_length=120)] | None = None
    description: Annotated[str, Field(max_length=1000)] | None = None
    goal: Annotated[str, Field(max_length=2000)] | None = None
    problem: Annotated[str, Field(max_length=2000)] | None = None
    domain_id: Annotated[str, Field(max_length=80)] | None = None
    subdomain: Annotated[str, Field(max_length=120)] | None = None
    capability: Annotated[str, Field(max_length=200)] | None = None
    purpose: Annotated[str, Field(max_length=1000)] | None = None
    user_types: list[Text] = Field(default_factory=list, max_length=20)
    outcomes: list[Text] = Field(default_factory=list, max_length=20)
    constraints: list[Text] = Field(default_factory=list, max_length=20)
    dependencies: list[Text] = Field(default_factory=list, max_length=20)


class AnswerQuestion(Strict):
    type: Literal["answer_question"]
    question_id: Annotated[str, Field(max_length=80)]
    answer: Annotated[str, Field(min_length=1, max_length=2000)]


class SetIntakeContext(Strict):
    type: Literal["set_intake_context"]
    region: Literal["global", "eu", "india"] | None = None
    industry_id: Annotated[str, Field(max_length=80)] | None = None
    skip: list[Literal["region", "industry"]] = Field(default_factory=list, max_length=2)


class AddRequirement(Strict):
    type: Literal["add_requirement"]
    statement: LongText
    priority: Literal["must", "should", "could"] = "should"
    kind: Literal["functional", "non_functional"] = "functional"
    category: (
        Literal[
            "security",
            "usability",
            "performance",
            "accessibility",
            "auditability",
            "reliability",
            "compliance",
            "other",
        ]
        | None
    ) = None
    acceptance_criteria: list[Text] = Field(default_factory=list, max_length=10)


class AdoptPack(Strict):
    type: Literal["adopt_pack"]
    pack_id: Annotated[str, Field(max_length=80)]


class UpdateKnowledge(Strict):
    type: Literal["update_knowledge"]
    pack_id: Annotated[str, Field(max_length=80)]


class ReconcileDuplicate(Strict):
    type: Literal["reconcile_duplicate"]
    kind: Literal["rule", "exception", "requirement"]
    keep: Text
    duplicate: Text


class AddRole(Strict):
    type: Literal["add_role"]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    responsibilities: list[Text] = Field(default_factory=list, max_length=10)
    permissions: list[Annotated[str, Field(max_length=80)]] = Field(
        default_factory=list, max_length=20
    )


class AttributeSpec(Strict):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    type: Literal["string", "integer", "decimal", "boolean", "date", "datetime"] = "string"
    required: bool = False
    key: bool = False


class RelationSpec(Strict):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    target: Annotated[str, Field(min_length=1, max_length=120)]
    cardinality: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"] = "many_to_one"


class AddEntity(Strict):
    type: Literal["add_entity"]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=1000)] = ""
    attributes: list[AttributeSpec] = Field(default_factory=list, max_length=30)
    relationships: list[RelationSpec] = Field(default_factory=list, max_length=15)


class AddAttribute(Strict):
    type: Literal["add_attribute"]
    entity: Annotated[str, Field(min_length=1, max_length=120)]
    attribute: AttributeSpec


class SetAttributeRequired(Strict):
    type: Literal["set_attribute_required"]
    entity: Annotated[str, Field(min_length=1, max_length=120)]
    attribute: Annotated[str, Field(min_length=1, max_length=120)]
    required: bool


class AddRule(Strict):
    type: Literal["add_rule"]
    description: LongText
    condition: Annotated[str, Field(max_length=1000)] = ""
    evidence_quote: Annotated[str, Field(max_length=1000)] = ""
    outcomes: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(
        default_factory=list, max_length=10
    )


class BindRule(Strict):
    type: Literal["bind_rule"]
    rule: Text
    execution: RuleExecution
    steps: list[Text] = Field(min_length=1, max_length=30)


class AddException(Strict):
    type: Literal["add_exception"]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    trigger: Annotated[str, Field(min_length=1, max_length=500)]
    recovery: Annotated[str, Field(min_length=1, max_length=1000)]
    # Optional: the step that handles it and where it ends up, so one action describes the exception completely.
    handled_at: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    resolution: Literal["recover", "terminate", "escalate"] | None = None
    resolves_to: Annotated[str, Field(min_length=1, max_length=120)] | None = None


class ConfirmRule(Strict):
    type: Literal["confirm_rule"]
    rule: Text
    source: RuleSource

class UpdateException(Strict):
    type: Literal["update_exception"]
    exception: Annotated[str, Field(min_length=1, max_length=120)]
    step: Annotated[str, Field(min_length=1, max_length=120)]
    resolution: Literal["recover", "terminate", "escalate"]
    resolution_step: Annotated[str, Field(min_length=1, max_length=120)]


class AddDecision(Strict):
    type: Literal["add_decision"]
    question: Annotated[str, Field(min_length=1, max_length=500)]


class AnswerDecision(Strict):
    type: Literal["answer_decision"]
    decision_id: Annotated[str, Field(max_length=80)]
    answer: Annotated[str, Field(min_length=1, max_length=1000)]


STEP_KINDS = ("form", "search", "review", "approval", "action", "exception", "branch")
# What a model calls a step that is not one of ours. The process always gets its own Start and Completed, so those are dropped.
KIND_ALIASES = {"decision": "branch", "gateway": "branch", "check": "review", "handler": "exception", "exception_handler": "exception", "manual": "form"}
BOUNDARY_KINDS = {"start", "end", "complete", "completed", "terminal", "finish", "done"}


class StepSpec(Strict):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    kind: Literal["form", "search", "review", "approval", "action", "exception", "branch"] = "form"

    @field_validator("kind", mode="before")
    @classmethod
    def known_kind(cls, value):
        """One unfamiliar kind word must not throw away a whole process: map it, or treat it as an action."""
        kind = str(value or "form").strip().lower()
        return kind if kind in STEP_KINDS else KIND_ALIASES.get(kind, "action")
    role: Annotated[str, Field(max_length=120)] | None = None
    requirements: list[Annotated[str, Field(max_length=80)]] = Field(
        default_factory=list, max_length=10
    )
    reads: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=10)
    writes: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=10)
    input_fields: dict[str, list[str]] | None = None
    input_relationships: dict[str, list[str]] | None = None


class CreateWorkflow(Strict):
    type: Literal["create_workflow"]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    steps: list[StepSpec] = Field(min_length=1, max_length=30)

    @field_validator("steps", mode="before")
    @classmethod
    def without_boundaries(cls, steps):
        return [s for s in steps if not (isinstance(s, dict) and str(s.get("kind", "")).strip().lower() in BOUNDARY_KINDS)] if isinstance(steps, list) else steps


class InsertStep(Strict):
    type: Literal["insert_step"]
    workflow: Annotated[str, Field(max_length=120)] | None = None
    after: Annotated[str, Field(min_length=1, max_length=120)]
    transition_id: Annotated[str, Field(max_length=120)] | None = None
    step: StepSpec


class AddApproval(Strict):
    type: Literal["add_approval"]
    before: Annotated[str, Field(min_length=1, max_length=120)]
    workflow: Annotated[str, Field(max_length=120)] | None = None
    role: Annotated[str, Field(max_length=120)] | None = None
    name: Annotated[str, Field(max_length=120)] | None = None


class RenameStep(Strict):
    type: Literal["rename_step"]
    step: Annotated[str, Field(min_length=1, max_length=120)]
    name: Annotated[str, Field(min_length=1, max_length=120)]


class AssignStepRole(Strict):
    type: Literal["assign_step_role"]
    step: Annotated[str, Field(min_length=1, max_length=120)]
    role: Annotated[str, Field(min_length=1, max_length=120)]


class LinkRequirement(Strict):
    """Record that a process step serves a requirement (traceability only: it changes no behaviour)."""

    type: Literal["link_requirement"]
    requirement: Annotated[str, Field(min_length=1, max_length=300)]
    step: Annotated[str, Field(min_length=1, max_length=120)]


class MergeProcess(Strict):
    """Fold a drafted process into the verified process that already covers it (see design_studio/process_overlap.py)."""

    type: Literal["merge_process"]
    keep: Annotated[str, Field(min_length=1, max_length=120)]
    duplicate: Annotated[str, Field(min_length=1, max_length=120)]


class SetStepData(Strict):
    """What a step reads and what it changes: its inputs and outputs. Replaces both lists; entities are named or given by id."""

    type: Literal["set_step_data"]
    step: Annotated[str, Field(min_length=1, max_length=120)]
    reads: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=15)
    writes: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=15)
    input_fields: dict[str, list[str]] | None = None
    input_relationships: dict[str, list[str]] | None = None


Action = Annotated[
    SetIntakeContext
    | SetTheme
    | SetScreenSections
    | SetBrief
    | AnswerQuestion
    | AddRequirement
    | AdoptPack
    | UpdateKnowledge
    | ReconcileDuplicate
    | AddRole
    | AddEntity
    | AddAttribute
    | SetAttributeRequired
    | AddRule
    | BindRule
    | ConfirmRule
    | AddException
    | UpdateException
    | AddDecision
    | AnswerDecision
    | CreateWorkflow
    | InsertStep
    | AddApproval
    | RenameStep
    | AssignStepRole
    | LinkRequirement
    | MergeProcess
    | SetStepData,
    Field(discriminator="type"),
]
ACTIONS = TypeAdapter(Action)

# Roles, rules, approvals, process structure and reference knowledge decide who may do what and how the business runs. The agent
# shows them for review; it applies the remaining, additive and easily reversed ones itself. Either way each change is a revision.
REVIEW_ACTIONS = frozenset(
    {
        "reconcile_duplicate",
        "update_knowledge",
        "bind_rule",
        "confirm_rule",
        "update_exception",
        "adopt_pack",
        "add_role",
        "add_rule",
        "add_exception",
        "create_workflow",
        "insert_step",
        "add_approval",
        "assign_step_role",
        "set_step_data",
        "answer_decision",
        "merge_process",
    }
)
# A business decision is company policy: it is always reviewed, and only someone with decision authority (studio.review) may apply it.
DECISION_ACTIONS = frozenset(
    {"answer_decision", "bind_rule", "confirm_rule", "update_knowledge", "reconcile_duplicate"}
)


def parse_actions(raw: Any) -> tuple[list[Any], list[dict]]:
    """Validate what the model proposed. Unknown or malformed actions are dropped with a reason, never repaired."""
    valid, rejected = [], []
    for item in (raw if isinstance(raw, list) else [])[:25]:
        # A model sometimes wraps an action as {"add_role": {...}}; that is only a different spelling of the same closed vocabulary.
        if (
            isinstance(item, dict)
            and "type" not in item
            and len(item) == 1
            and next(iter(item)) in HANDLERS
            and isinstance(next(iter(item.values())), dict)
        ):
            item = {"type": next(iter(item)), **next(iter(item.values()))}
        if isinstance(item, dict) and item.get("type") == "set_theme":
            # The model sometimes names the field "color" or gives a word ("blue") instead of a code: the same request, spelled differently.
            chosen = next((item[k] for k in ("primary", "color", "colour", "value", "hex") if item.get(k)), None)
            code = colour_hex(chosen)
            item = {"type": "set_theme", "primary": code} if code else item
        try:
            valid.append(ACTIONS.validate_python(item))
        except ValidationError as exc:
            kind = item.get("type") if isinstance(item, dict) else None
            first = exc.errors()[0]
            reason = f"{'.'.join(str(p) for p in first['loc'][1:]) or 'action'}: {first['msg']}"
            if kind == "set_theme":
                reason = "that colour was not recognised; choose Forest green, Ocean blue, Indigo, Teal, Copper or Slate, or give a #RRGGBB code"
            rejected.append({"type": str(kind), "reason": reason})
    return valid, rejected


def high_impact(actions: list[Any]) -> bool:
    return any(action.type in REVIEW_ACTIONS for action in actions)


# ── helpers ────────────────────────────────────────────────────────────


def slug(text: str, limit: int = 40) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:limit].strip("_")
    return value if value and value[0].isalpha() else f"x_{value}".strip("_")[:limit]


def _unique_id(prefix: str, name: str, taken: set[str]) -> str:
    base = f"{prefix}_{slug(name)}"[:70].strip("_")
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}_{n}"
        n += 1
    taken.add(candidate)
    return candidate


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _find(items: list[dict], ref: str, fields: tuple[str, ...], kind: str) -> dict:
    """An item by id, exact name, or - when unambiguous - by a containing name. Anything else is an error, never a guess."""
    wanted = _norm(ref)
    for item in items:
        if item["id"] == ref or any(_norm(str(item.get(field, ""))) == wanted for field in fields):
            return item
    partial = [
        item
        for item in items
        if wanted
        and any(
            wanted in _norm(str(item.get(field, "")))
            or (
                len(_norm(str(item.get(field, "")))) > 3
                and _norm(str(item.get(field, ""))) in wanted
            )
            for field in fields
        )
    ]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise ActionError(
            f"“{ref}” matches several {kind}s ({', '.join(p.get('name') or p.get('label') or p['id'] for p in partial[:4])}). Say which one."
        )
    raise ActionError(f"There is no {kind} called “{ref}”.")


def _business_ids(raw: dict) -> set[str]:
    business = raw["business"]
    return {
        item["id"]
        for group in (
            "requirements",
            "roles",
            "entities",
            "rules",
            "exceptions",
            "decisions",
            "integrations",
            "terms",
        )
        for item in business[group]
    }


def _all_steps(raw: dict) -> list[tuple[dict, dict]]:
    return [
        (workflow, state)
        for workflow in raw["workflow_definitions"]
        for state in workflow["states"]
    ]


def _find_step(raw: dict, ref: str, workflow_ref: str | None = None) -> tuple[dict, dict]:
    pool = _all_steps(raw)
    if "/" in ref:  # the context lists steps as workflow/step
        workflow_ref, ref = (workflow_ref or ref.split("/", 1)[0]), ref.split("/", 1)[1]
    if workflow_ref:
        workflow = _find(raw["workflow_definitions"], workflow_ref, ("name",), "process")
        pool = [(w, s) for w, s in pool if w["id"] == workflow["id"]]
    wanted = _norm(ref)
    exact = [(w, s) for w, s in pool if s["id"] == ref or _norm(s["label"]) == wanted]
    if len(exact) == 1:
        return exact[0]
    near = exact or [(w, s) for w, s in pool if wanted and wanted in _norm(s["label"])]
    if len(near) == 1:
        return near[0]
    if not near:
        raise ActionError("The referenced process step was not found. Refresh the process and choose an existing step.")
    raise ActionError(
        f"“{ref}” matches several steps ({', '.join(s['label'] for _, s in near[:4])}). Say which one."
    )


def _ensure_role(raw: dict, name: str, changes: list[dict]) -> dict:
    roles = raw["business"]["roles"]
    try:
        return _find(roles, name, ("name",), "role")
    except ActionError as exc:
        if "several" in str(exc):
            raise
    role = {
        "id": _unique_id("role", name, _business_ids(raw)),
        "name": name.strip()[:120],
        "responsibilities": [],
        "permissions": [],
        "approval_authority": [],
        "origin": None,
    }
    roles.append(role)
    changes.append(
        {
            "area": "roles",
            "kind": "added",
            "item_id": role["id"],
            "summary": f"Role “{role['name']}”",
        }
    )
    return role


def _grant(role: dict, permission: str) -> None:
    if permission not in role["permissions"]:
        role["permissions"].append(permission)


# ── actions ────────────────────────────────────────────────────────────
# Each takes the raw definition dict (mutated in place), the action, and the change list, and raises ActionError when it cannot apply.


def _set_intake_context(raw, action: SetIntakeContext, changes, provider):
    from app.design_studio.knowledge.system_context import catalog_for

    previous = raw["business"]["brief"].get("intake")
    catalog = catalog_for(provider, previous["catalog_version"] if previous else None)
    if not catalog:
        raise ActionError(
            "Industry context is unavailable. You can continue with the shared process draft."
        )
    context = dict(
        previous
        or {
            "region": None,
            "industry_id": None,
            "skipped": [],
            "catalog_version": catalog["version"],
        }
    )
    skipped = set(context["skipped"])
    if action.industry_id is not None and action.industry_id not in {
        r["id"] for r in catalog["industries"]
    }:
        raise ActionError("Choose an industry from the available catalog.")
    for topic, field, value in [
        ("region", "region", action.region),
        ("industry", "industry_id", action.industry_id),
    ]:
        if value is not None and topic in action.skip:
            raise ActionError("Answer or skip a question, not both.")
        if value is not None:
            context[field] = value
            skipped.discard(topic)
        if topic in action.skip:
            skipped.add(topic)
            context[field] = None
    context["skipped"] = sorted(skipped)
    if context == previous:
        raise ActionError("These setup preferences are already saved.")
    raw["business"]["brief"]["intake"] = context
    changes.append(
        {
            "area": "brief",
            "kind": "changed",
            "item_id": "intake_context",
            "summary": "Saved optional region and industry preferences; skipped answers remain unknown.",
        }
    )


def _set_brief(raw, action: SetBrief, changes, provider):
    brief, touched = raw["business"]["brief"], []
    for field in ("goal", "problem", "subdomain", "capability", "purpose"):
        value = getattr(action, field)
        if value and value.strip() and brief[field] != value.strip():
            brief[field] = value.strip()
            touched.append(field)
    if action.domain_id:
        known = {domain.id for domain in provider.domains()}
        if action.domain_id not in known:
            raise ActionError(f"“{action.domain_id}” is not a known business domain.")
        if brief["domain_id"] != action.domain_id:
            brief["domain_id"] = action.domain_id
            touched.append("domain")
    for field in ("user_types", "outcomes", "constraints", "dependencies"):
        added = [
            item.strip()
            for item in getattr(action, field)
            if item.strip() and item.strip().lower() not in {x.lower() for x in brief[field]}
        ]
        if added:
            brief[field] = (brief[field] + added)[:50]
            touched.append(field.replace("_", " "))
    if action.name and action.name.strip() and raw["metadata"]["name"] != action.name.strip():
        raw["metadata"]["name"] = action.name.strip()
        touched.append("name")
    if (
        action.description is not None
        and action.description.strip()
        and raw["metadata"]["description"] != action.description.strip()
    ):
        raw["metadata"]["description"] = action.description.strip()
        raw["metadata"]["purpose"] = raw["metadata"]["purpose"] or action.description.strip()[:1000]
        touched.append("description")
    if not touched:
        raise ActionError("The brief already says that.")
    changes.append(
        {
            "area": "brief",
            "kind": "changed",
            "item_id": "brief",
            "summary": f"Requirements brief: {', '.join(touched)}",
        }
    )


def _answer_question(raw, action: AnswerQuestion, changes, provider):
    question = next(
        (q for q in raw["business"]["questions"] if q["id"] == action.question_id), None
    )
    if question is None:
        raise ActionError("That question is not on the list.")
    question["answer"], question["status"] = action.answer.strip(), "answered"
    changes.append(
        {
            "area": "questions",
            "kind": "changed",
            "item_id": question["id"],
            "summary": f"Answered: {question['text']}",
        }
    )


def _add_requirement(raw, action: AddRequirement, changes, provider):
    business = raw["business"]
    if any(
        _norm(item["statement"]) == _norm(action.statement) for item in business["requirements"]
    ):
        raise ActionError("That requirement is already recorded.")
    category = action.category if action.kind == "non_functional" else None
    if action.kind == "non_functional" and category is None:
        category = "other"
    ident = _unique_id(
        "nfr" if action.kind == "non_functional" else "req",
        action.statement[:40],
        _business_ids(raw),
    )
    business["requirements"].append(
        {
            "id": ident,
            "statement": action.statement.strip(),
            "kind": action.kind,
            "category": category,
            "priority": action.priority,
            "status": "draft",
            "acceptance_criteria": [
                {"id": f"ac_{ident}_{i + 1}"[:79], "statement": text.strip()}
                for i, text in enumerate(action.acceptance_criteria)
            ],
            "deferral_reason": "",
            "origin": None,
        }
    )
    changes.append(
        {
            "area": "requirements",
            "kind": "added",
            "item_id": ident,
            "summary": f"Requirement: {action.statement.strip()[:90]}",
        }
    )


def _adopt_pack(raw, action: AdoptPack, changes, provider):
    try:
        pack = provider.pack(action.pack_id)
        if not pack.verified:
            raise ActionError("Only verified knowledge, checked against official documentation, can be used in a project.")
        if pack.usage == "source_reference":
            raise ActionError(
                "This pack is source reference knowledge. Choose a reusable blueprint to generate the application."
            )
        definition, added = apply_pack(
            ApplicationDefinition.model_validate(raw), action.pack_id, provider
        )
    except PackUnavailable:
        raise ActionError(f"There is no reference pack “{action.pack_id}”.") from None
    except PackConflict as exc:
        raise ActionError(
            f"Some reference items clash with existing items ({', '.join(exc.ids[:4])})."
        ) from None
    if not any(added.values()):
        raise ActionError("That reference knowledge is already part of the project.")
    raw.clear()
    raw.update(definition.model_dump(mode="json"))
    parts = ", ".join(f"{count} {group}" for group, count in added.items() if count)
    changes.append(
        {
            "area": "knowledge",
            "kind": "added",
            "item_id": action.pack_id,
            "summary": f"Reference knowledge “{action.pack_id}”: {parts}",
        }
    )


def _add_role(raw, action: AddRole, changes, provider):
    roles = raw["business"]["roles"]
    if any(_norm(role["name"]) == _norm(action.name) for role in roles):
        raise ActionError(f"The role “{action.name}” already exists.")
    permissions = []
    for permission in action.permissions:
        if (
            re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*", permission)
            and permission not in permissions
        ):
            permissions.append(permission)
    role = {
        "id": _unique_id("role", action.name, _business_ids(raw)),
        "name": action.name.strip(),
        "responsibilities": [r.strip() for r in action.responsibilities],
        "permissions": permissions,
        "approval_authority": [],
        "origin": None,
    }
    roles.append(role)
    changes.append(
        {
            "area": "roles",
            "kind": "added",
            "item_id": role["id"],
            "summary": f"Role “{role['name']}”",
        }
    )


def _update_knowledge(raw, action: UpdateKnowledge, changes, provider):
    from app.design_studio.knowledge.upgrades import UpgradeConflict, update_reference

    try:
        updated = update_reference(
            ApplicationDefinition.model_validate(raw), action.pack_id, provider
        )
    except (UpgradeConflict, PackUnavailable, PackConflict) as exc:
        raise ActionError(str(exc)) from None
    raw.update(updated.model_dump(mode="json"))
    changes.append(
        {
            "area": "knowledge",
            "kind": "changed",
            "item_id": action.pack_id,
            "summary": f"Update {action.pack_id} to {provider.pack(action.pack_id).version}; preserve non-conflicting project edits",
        }
    )


_BASE_IDS = ("string", "integer", "decimal", "boolean", "date", "datetime")


def _attribute(spec: AttributeSpec, taken: set[str]) -> dict:
    ident, n = slug(spec.name, 60), 2
    base = ident
    while ident in taken:
        ident, n = f"{base}_{n}", n + 1
    taken.add(ident)
    return {
        "id": ident,
        "name": spec.name.strip(),
        "type": spec.type,
        "required": spec.required or spec.key,
        "key": spec.key,
        "allow_unknown": False,
        "description": "",
        "validations": [],
        "value_source": "user_entered",
        "writable": True,
        "default": None,
        "format": None,
        "minimum": None,
        "maximum": None,
        "min_length": None,
        "max_length": None,
        "pattern": None,
        "enum": [],
        "sensitivity": "internal",
        "owner_role_id": None,
        "reference": None,
    }


def _add_entity(raw, action: AddEntity, changes, provider):
    entities = raw["business"]["entities"]
    if any(_norm(item["name"]) == _norm(action.name) for item in entities):
        raise ActionError(f"The data entity “{action.name}” already exists.")
    ident = _unique_id("ent", action.name, _business_ids(raw))
    taken: set[str] = set()
    attributes = [_attribute(spec, taken) for spec in action.attributes]
    if not any(a["key"] for a in attributes):
        key = _attribute(AttributeSpec(name=f"{action.name} ID", type="string", key=True), taken)
        attributes.insert(0, key)
    entity = {
        "id": ident,
        "name": action.name.strip(),
        "description": action.description.strip(),
        "owner_role_id": None,
        "source_system": "",
        "attributes": attributes,
        "relationships": [],
        "origin": None,
    }
    entities.append(entity)
    notes = []
    for relation in action.relationships:
        try:
            target = _find(entities, relation.target, ("name",), "data entity")
        except ActionError:
            notes.append(relation.target)
            continue
        entity["relationships"].append(
            {
                "id": _unique_id(
                    "rel", f"{slug(relation.name)}", {r["id"] for r in entity["relationships"]}
                ),
                "name": relation.name.strip(),
                "target": target["id"],
                "cardinality": relation.cardinality,
                "required": False,
            }
        )
    suffix = f" (relationship to unknown {', '.join(notes)} skipped)" if notes else ""
    changes.append(
        {
            "area": "entities",
            "kind": "added",
            "item_id": ident,
            "summary": f"Data entity “{entity['name']}” with {len(attributes)} attributes{suffix}",
        }
    )


def _entity_and_attribute(raw, entity_ref: str, attribute_ref: str | None = None):
    entity = _find(raw["business"]["entities"], entity_ref, ("name",), "data entity")
    attribute = (
        _find(entity["attributes"], attribute_ref, ("name",), "attribute")
        if attribute_ref
        else None
    )
    return entity, attribute


def _add_attribute(raw, action: AddAttribute, changes, provider):
    entity, _ = _entity_and_attribute(raw, action.entity)
    if any(_norm(a["name"]) == _norm(action.attribute.name) for a in entity["attributes"]):
        raise ActionError(f"{entity['name']} already has “{action.attribute.name}”.")
    entity["attributes"].append(
        _attribute(action.attribute, {a["id"] for a in entity["attributes"]})
    )
    changes.append(
        {
            "area": "entities",
            "kind": "changed",
            "item_id": entity["id"],
            "summary": f"{entity['name']}: added attribute “{action.attribute.name}”",
        }
    )


def _set_required(raw, action: SetAttributeRequired, changes, provider):
    entity, attribute = _entity_and_attribute(raw, action.entity, action.attribute)
    if attribute["required"] == action.required:
        raise ActionError(
            f"{entity['name']}.{attribute['name']} is already {'mandatory' if action.required else 'optional'}."
        )
    if not action.required and attribute["key"]:
        raise ActionError(
            f"{attribute['name']} identifies a {entity['name']} record, so it must stay mandatory."
        )
    attribute["required"] = action.required
    changes.append(
        {
            "area": "entities",
            "kind": "changed",
            "item_id": f"{entity['id']}.{attribute['id']}",
            "summary": f"{entity['name']}.{attribute['name']} is now {'mandatory' if action.required else 'optional'}",
        }
    )


def _add_rule(raw, action: AddRule, changes, provider):
    if any(
        _norm(rule["description"]) == _norm(action.description) for rule in raw["business"]["rules"]
    ):
        raise ActionError(
            "This rule already exists. Bind or update the existing rule instead of adding a duplicate."
        )
    ident = _unique_id("rule", action.description[:40], _business_ids(raw))
    outcomes, seen = [], set()
    for item in action.outcomes:
        name = re.sub(r"[^A-Za-z0-9_]+", "_", item.strip()).strip("_").upper()
        if name and name[0].isalpha() and name not in seen:
            outcomes.append(name)
            seen.add(name)
    kind = "decision" if len(outcomes) >= 2 else "policy"
    if kind == "policy":
        outcomes = []
    # A rule written in conversation is the user's statement, not verified policy: it stays an assumption until the owner confirms it.
    raw["business"]["rules"].append(
        {
            "id": ident,
            "description": action.description.strip(),
            "type": kind,
            "status": "assumption",
            "source": {
                "kind": "workshop",
                "reference": "Stated in the Design Studio conversation; confirm with the business owner",
            },
            "condition": action.condition.strip(),
            "outcomes": outcomes,
            "origin": None,
            "execution": None,
        }
    )
    changes.append(
        {
            "area": "rules",
            "kind": "added",
            "item_id": ident,
            "summary": f"Rule (assumption): {action.description.strip()[:90]}",
        }
    )


def _bind_rule(raw, action: BindRule, changes, provider):
    rule = _find(raw["business"]["rules"], action.rule, ("description",), "rule")
    for reference in action.steps:
        workflow, step = _find_step(raw, reference)
        if step["kind"] in ("start", "end"):
            raise ActionError("Executable rules must be linked to an actionable or branch step.")
        if rule["id"] not in step["rule_ids"]:
            step["rule_ids"].append(rule["id"])
    rule["execution"] = action.execution.model_dump(mode="json")
    # A binding is implementation, not evidence that an assumption is confirmed.
    changes.append(
        {
            "area": "rules",
            "kind": "changed",
            "item_id": rule["id"],
            "summary": f"Bound executable logic for {rule['description'][:90]}",
        }
    )


def _add_exception(raw, action: AddException, changes, provider):
    if any(_norm(item["name"]) == _norm(action.name) for item in raw["business"]["exceptions"]):
        raise ActionError(
            "This exception already exists. Update its recovery instead of creating a duplicate."
        )
    ident = _unique_id("exc", action.name, _business_ids(raw))
    raw["business"]["exceptions"].append(
        {
            "id": ident,
            "name": action.name.strip(),
            "trigger": action.trigger.strip(),
            "recovery": action.recovery.strip(),
            "resolution": None,
            "resolution_state_id": None,
            "origin": None,
        }
    )
    changes.append(
        {
            "area": "exceptions",
            "kind": "added",
            "item_id": ident,
            "summary": f"Exception “{action.name.strip()}”",
        }
    )
    wiring = (action.handled_at, action.resolution, action.resolves_to)
    if any(wiring):
        if not all(wiring):
            raise ActionError("An exception handled in the same action needs handled_at, resolution and resolves_to together.")
        _update_exception(
            raw,
            UpdateException(
                type="update_exception",
                exception=ident,
                step=action.handled_at,
                resolution=action.resolution,
                resolution_step=action.resolves_to,
            ),
            changes,
            provider,
        )


def decision_words(question: str) -> frozenset[str]:
    """The words of a business question without its examples in brackets ("(e.g., nearest, largest capacity)"), so two ways of asking
    the same thing compare equal."""
    return frozenset(re.findall(r"[a-z0-9]+", re.sub(r"\([^)]*\)", " ", question.lower())))


def same_decision(first: str, second: str) -> bool:
    a, b = decision_words(first), decision_words(second)
    return bool(a and b) and len(a & b) / min(len(a), len(b)) >= 0.85


def _add_decision(raw, action: AddDecision, changes, provider):
    business = raw["business"]
    if any(_norm(d["question"]) == _norm(action.question) or same_decision(d["question"], action.question) for d in business["decisions"]):
        raise ActionError("That decision is already open.")
    ident = _unique_id("dec", action.question[:40], _business_ids(raw))
    business["decisions"].append(
        {
            "id": ident,
            "question": action.question.strip(),
            "status": "open",
            "answer": "",
            "deferral_reason": "",
            "affects": [],
            "origin": None,
        }
    )
    changes.append(
        {
            "area": "decisions",
            "kind": "added",
            "item_id": ident,
            "summary": f"Open decision: {action.question.strip()[:90]}",
        }
    )


def _answer_decision(raw, action: AnswerDecision, changes, provider):
    decision = _find(raw["business"]["decisions"], action.decision_id, ("question",), "decision")
    decision["status"], decision["answer"] = "decided", action.answer.strip()
    changes.append(
        {
            "area": "decisions",
            "kind": "changed",
            "item_id": decision["id"],
            "summary": f"Decided: {decision['question'][:80]}",
        }
    )


HUMAN = ("form", "search", "review", "approval", "action", "exception")


def _build_step(
    raw, workflow_id: str, spec: StepSpec, changes: list[dict], taken: set[str]
) -> dict:
    kind = (
        "review" if spec.kind == "branch" else spec.kind
    )  # a decision needs a business rule to branch on; the agent does not invent one
    ident = _unique_id("st", f"{slug(workflow_id, 20)}_{spec.name}", taken)
    state: dict[str, Any] = {
        "id": ident,
        "label": spec.name.strip(),
        "kind": kind,
        "outputs": [],
        "outcome": None,
        "role_id": None,
        "permission": None,
        "requirement_ids": [],
        "reads_entity_ids": [],
        "writes_entity_ids": [],
        "rule_ids": [],
        "exception_ids": [],
        "preconditions": [],
        "postconditions": [],
    }
    business = raw["business"]
    known_requirements = {item["id"] for item in business["requirements"]}
    state["requirement_ids"] = [
        r for r in dict.fromkeys(spec.requirements) if r in known_requirements
    ]
    for field, names in (("reads_entity_ids", spec.reads), ("writes_entity_ids", spec.writes)):
        for name in names:
            try:
                entity_id = _find(business["entities"], name, ("name",), "data entity")["id"]
            except ActionError:
                continue
            if entity_id not in state[field]:
                state[field].append(entity_id)
    if spec.role:
        role = _ensure_role(raw, spec.role, changes)
        state["role_id"] = role["id"]
        permission = f"{slug(workflow_id.replace('wf_', ''), 24)}.{slug(spec.name, 40)}"
        state["permission"] = permission
        _grant(role, permission)
    for key in ("input_fields", "input_relationships"):
        if getattr(spec, key) is not None:
            state[key] = getattr(spec, key)
    return state


def _edge(source: str, target: str, taken: set[str]) -> dict:
    return {
        "id": _unique_id("tr", f"{source}_{target}", taken),
        "source": source,
        "target": target,
        "condition": {"kind": "always", "field": None, "value": None},
    }


def _create_workflow(raw, action: CreateWorkflow, changes, provider):
    workflows = raw["workflow_definitions"]
    if any(_norm(w["name"]) == _norm(action.name) for w in workflows):
        raise ActionError(f"A process called “{action.name}” already exists.")
    from app.design_studio.process_overlap import covered_by

    covering = covered_by(raw, action.name, [step.name for step in action.steps], provider)
    if covering:
        raise ActionError(
            f"“{covering}” is a verified process that already covers “{action.name}”. Extend it with insert_step instead of creating a second process."
        )
    taken_workflows = {w["id"] for w in workflows}
    workflow_id = _unique_id("wf", action.name, taken_workflows)
    taken_states = {s["id"] for _, s in _all_steps(raw)}
    start = {
        "id": _unique_id("st", f"{workflow_id}_start", taken_states),
        "label": "Start",
        "kind": "start",
        "outputs": [],
        "outcome": None,
        "role_id": None,
        "permission": None,
        "requirement_ids": [],
        "reads_entity_ids": [],
        "writes_entity_ids": [],
        "rule_ids": [],
        "exception_ids": [],
        "preconditions": [],
        "postconditions": [],
    }
    states = [start] + [
        _build_step(raw, workflow_id, spec, changes, taken_states) for spec in action.steps
    ]
    end = {
        **start,
        "id": _unique_id("st", f"{workflow_id}_done", taken_states),
        "label": "Completed",
        "kind": "end",
        "outcome": "success",
    }
    states.append(end)
    taken_edges = {t["id"] for w in workflows for t in w["transitions"]}
    transitions = [_edge(a["id"], b["id"], taken_edges) for a, b in zip(states, states[1:])]
    workflows.append(
        {
            "version": 1,
            "id": workflow_id,
            "name": action.name.strip(),
            "states": states,
            "transitions": transitions,
        }
    )
    raw["workflows"].append(workflow_id)
    changes.append(
        {
            "area": "workflow",
            "kind": "added",
            "item_id": workflow_id,
            "summary": f"Process “{action.name.strip()}” with {len(action.steps)} steps",
        }
    )


def _insert_step(raw, action: InsertStep, changes, provider):
    workflow, anchor = _find_step(raw, action.after, action.workflow)
    if anchor["kind"] == "end":
        raise ActionError("Nothing can follow an end of the process.")
    outgoing = [t for t in workflow["transitions"] if t["source"] == anchor["id"]]
    if action.transition_id:
        outgoing = [edge for edge in outgoing if edge["id"] == action.transition_id]
        if not outgoing:
            raise ActionError("The selected path no longer leaves this step. Refresh the process and choose a path.")
    if len(outgoing) != 1 or (not action.transition_id and outgoing[0]["condition"]["kind"] != "always"):
        raise ActionError(
            f"“{anchor['label']}” has several paths, so where the new step goes is a design choice. Name the exact path or use the process editor."
        )
    taken = {s["id"] for _, s in _all_steps(raw)}
    new = _build_step(raw, workflow["id"], action.step, changes, taken)
    edges = {t["id"] for w in raw["workflow_definitions"] for t in w["transitions"]}
    old_target = outgoing[0]["target"]
    outgoing[0]["target"] = new["id"]
    workflow["states"].append(new)
    workflow["transitions"].append(_edge(new["id"], old_target, edges))
    changes.append(
        {
            "area": "step",
            "kind": "added",
            "item_id": f"{workflow['id']}/{new['id']}",
            "summary": f"Step “{new['label']}” after “{anchor['label']}”",
        }
    )


def _add_approval(raw, action: AddApproval, changes, provider):
    workflow, target = _find_step(raw, action.before, action.workflow)
    if target["kind"] in ("start", "end"):
        raise ActionError("An approval goes before a working step, not the start or an end.")
    incoming = [t for t in workflow["transitions"] if t["target"] == target["id"]]
    if not incoming:
        raise ActionError(f"Nothing leads into “{target['label']}” yet.")
    name = (action.name or f"Approve before {target['label']}").strip()[:120]
    spec = StepSpec(
        name=name, kind="approval", role=action.role, requirements=list(target["requirement_ids"])
    )
    taken = {s["id"] for _, s in _all_steps(raw)}
    approval = _build_step(raw, workflow["id"], spec, changes, taken)
    edges = {t["id"] for w in raw["workflow_definitions"] for t in w["transitions"]}
    for edge in incoming:
        edge["target"] = approval["id"]
    workflow["states"].append(approval)
    workflow["transitions"].append(_edge(approval["id"], target["id"], edges))
    business = raw["business"]
    ident = _unique_id("dec", f"approval_{name}", _business_ids(raw))
    business["decisions"].append(
        {
            "id": ident,
            "question": f"Who approves “{target['label']}”, and what happens when the approval is rejected?",
            "status": "open",
            "answer": "",
            "deferral_reason": "",
            "affects": [approval["id"]],
            "origin": None,
        }
    )
    changes.append(
        {
            "area": "step",
            "kind": "added",
            "item_id": f"{workflow['id']}/{approval['id']}",
            "summary": f"Approval step before “{target['label']}” (rejection path left as an open decision)",
        }
    )


def _rename_step(raw, action: RenameStep, changes, provider):
    workflow, step = _find_step(raw, action.step)
    if step["label"] == action.name.strip():
        raise ActionError("The step already has that name.")
    before, step["label"] = step["label"], action.name.strip()
    changes.append(
        {
            "area": "step",
            "kind": "changed",
            "item_id": f"{workflow['id']}/{step['id']}",
            "summary": f"Renamed step “{before}” to “{step['label']}”",
        }
    )


def _assign_role(raw, action: AssignStepRole, changes, provider):
    workflow, step = _find_step(raw, action.step)
    if step["kind"] in ("start", "end"):
        raise ActionError("A start or end has no responsible role.")
    role = _ensure_role(raw, action.role, changes)
    step["role_id"] = role["id"]
    if step["permission"]:
        _grant(role, step["permission"])
    else:
        step["permission"] = (
            f"{slug(workflow['id'].replace('wf_', ''), 24)}.{slug(step['label'], 40)}"
        )
        _grant(role, step["permission"])
    changes.append(
        {
            "area": "step",
            "kind": "changed",
            "item_id": f"{workflow['id']}/{step['id']}",
            "summary": f"“{step['label']}” is now performed by {role['name']}",
        }
    )


def _link_requirement(raw, action: LinkRequirement, changes, provider):
    requirement = _find(
        raw["business"]["requirements"], action.requirement, ("statement",), "requirement"
    )
    workflow, step = _find_step(raw, action.step)
    if step["kind"] in ("start", "end"):
        raise ActionError("A start or an end does not serve a requirement.")
    if requirement["id"] in step["requirement_ids"]:
        raise ActionError(f"\u201c{step['label']}\u201d already serves that requirement.")
    step["requirement_ids"].append(requirement["id"])
    changes.append(
        {
            "area": "step",
            "kind": "changed",
            "item_id": f"{workflow['id']}/{step['id']}",
            "summary": f"\u201c{step['label']}\u201d serves \u201c{requirement['statement'][:70]}\u201d",
        }
    )


def _set_step_data(raw, action: SetStepData, changes, provider):
    workflow, step = _find_step(raw, action.step)
    if step["kind"] in ("start", "end"):
        raise ActionError("A start or an end does not read or change data.")
    entities = raw["business"]["entities"]
    resolved = {
        field: list(
            dict.fromkeys(_find(entities, name, ("name",), "data entity")["id"] for name in names)
        )  # an unknown entity is refused, never skipped
        for field, names in (
            ("reads_entity_ids", action.reads),
            ("writes_entity_ids", action.writes),
        )
    }
    for key in ("input_fields", "input_relationships"):
        value = getattr(action, key)
        if value is not None:
            resolved[key] = value
        elif step.get(key) is not None:
            resolved[key] = {
                entity: fields
                for entity, fields in step[key].items()
                if entity in resolved["writes_entity_ids"]
            }
    if all(
        set(step.get(field, [])) == set(value)
        if field in ("reads_entity_ids", "writes_entity_ids")
        else step.get(field) == value
        for field, value in resolved.items()
    ):
        raise ActionError(f"“{step['label']}” already uses exactly that data.")
    step.update(resolved)
    name = {e["id"]: e["name"] for e in entities}
    described = "; ".join(
        f"{verb} {', '.join(name[i] for i in resolved[field]) or 'nothing'}"
        for verb, field in (("reads", "reads_entity_ids"), ("changes", "writes_entity_ids"))
    )
    changes.append(
        {
            "area": "step",
            "kind": "changed",
            "item_id": f"{workflow['id']}/{step['id']}",
            "summary": f"“{step['label']}” {described}",
        }
    )


def _update_exception(raw, action: UpdateException, changes, provider):
    scenario = _find(raw["business"]["exceptions"], action.exception, ("name",), "exception")
    workflow, step = _find_step(raw, action.step)
    target_workflow, target = _find_step(raw, action.resolution_step)
    if workflow["id"] != target_workflow["id"]:
        raise ActionError("Exception handling and resolution must belong to the same workflow.")
    if step["kind"] in ("start", "end"):
        raise ActionError("A start or end cannot handle an exception.")
    if action.resolution == "terminate" and target["kind"] != "end":
        raise ActionError("A terminating exception must resolve to an end state.")
    if action.resolution != "terminate" and target["kind"] in ("start", "end"):
        raise ActionError("Recovery or escalation must resolve to an actionable step.")
    scenario.update(resolution=action.resolution, resolution_state_id=target["id"])
    if scenario["id"] not in step["exception_ids"]:
        step["exception_ids"].append(scenario["id"])
    changes.append(
        {
            "area": "exceptions",
            "kind": "changed",
            "item_id": scenario["id"],
            "summary": f"{scenario['name']}: handled at {step['label']}; {action.resolution} to {target['label']}",
        }
    )


def _reconcile_duplicate(raw, action: ReconcileDuplicate, changes, provider):
    from app.design_studio.knowledge.deduplication import reconcile

    try:
        reconcile(raw, action.kind, action.keep, action.duplicate)
    except ValueError as exc:
        raise ActionError(str(exc)) from None
    changes.append(
        {
            "area": action.kind,
            "kind": "changed",
            "item_id": action.keep,
            "summary": f"Reconcile duplicate {action.duplicate} into {action.keep}; retain source and process references",
        }
    )


def _confirm_rule(raw, action: ConfirmRule, changes, provider):
    if action.source.kind == "synthetic_assumption" or not action.source.reference.strip():
        raise ActionError("Confirm a rule using a business owner or an identifiable source, not a synthetic assumption.")
    rule = next((item for item in raw["business"]["rules"] if item["id"] == action.rule), None)
    if rule is None:
        raise ActionError("That rule no longer exists. Refresh the rules and try again.")
    rule["status"] = "confirmed"
    rule["source"] = action.source.model_dump()
    changes.append({"area": "rule", "kind": "changed", "item_id": rule["id"], "summary": f"Confirm rule: {rule['description']} · {action.source.reference}"})


def _merge_process(raw, action: MergeProcess, changes, provider):
    from app.design_studio.process_overlap import find_overlaps, merge_processes
    from app.schemas.application_definition import ApplicationDefinition

    pair = next(
        (f for f in find_overlaps(ApplicationDefinition.model_validate(raw), provider) if (f["keep"], f["duplicate"]) == (action.keep, action.duplicate)),
        None,
    )
    if pair is None:
        raise ActionError("Only a drafted process that a verified process already covers can be merged into it.")
    try:
        notes = merge_processes(raw, action.keep, action.duplicate)
    except ValueError as exc:
        raise ActionError(str(exc)) from None
    changes.append({"area": "workflow", "kind": "changed", "item_id": action.keep, "summary": " ".join(notes)})


def _set_theme(raw, action: SetTheme, changes, provider):
    primary = action.primary.lower()
    if raw["theme"]["primary"].lower() == primary:
        return
    raw["theme"]["primary"] = primary
    changes.append({"area": "screens", "kind": "changed", "item_id": "theme", "summary": f"Application colour changed to {primary}"})


def _set_screen_sections(raw, action: SetScreenSections, changes, provider):
    current = list(raw["theme"].get("hidden_sections") or [])
    wanted = [s for s in dict.fromkeys([*current, *action.hide]) if s not in action.show]
    if wanted == current:
        return
    raw["theme"]["hidden_sections"] = wanted
    hidden, shown = [s for s in wanted if s not in current], [s for s in current if s not in wanted]
    parts = ([f"hidden {', '.join(SECTION_NAMES[s] for s in hidden)}"] if hidden else []) + (
        [f"shown {', '.join(SECTION_NAMES[s] for s in shown)}"] if shown else []
    )
    changes.append({"area": "screens", "kind": "changed", "item_id": "theme", "summary": "Screens: " + "; ".join(parts)})


HANDLERS: dict[str, Callable] = {
    "set_screen_sections": _set_screen_sections,
    "set_theme": _set_theme,
    "set_intake_context": _set_intake_context,
    "set_brief": _set_brief,
    "answer_question": _answer_question,
    "add_requirement": _add_requirement,
    "adopt_pack": _adopt_pack,
    "add_role": _add_role,
    "add_entity": _add_entity,
    "add_attribute": _add_attribute,
    "set_attribute_required": _set_required,
    "add_rule": _add_rule,
    "add_exception": _add_exception,
    "add_decision": _add_decision,
    "answer_decision": _answer_decision,
    "create_workflow": _create_workflow,
    "insert_step": _insert_step,
    "add_approval": _add_approval,
    "rename_step": _rename_step,
    "assign_step_role": _assign_role,
    "link_requirement": _link_requirement,
    "set_step_data": _set_step_data,
    "update_exception": _update_exception,
    "bind_rule": _bind_rule,
    "confirm_rule": _confirm_rule,
    "merge_process": _merge_process,
    "update_knowledge": _update_knowledge,
    "reconcile_duplicate": _reconcile_duplicate,
}


def apply_actions(
    definition: ApplicationDefinition, actions: list[Any], provider: KnowledgeProvider
) -> tuple[ApplicationDefinition, list[dict], list[dict]]:
    """Apply the actions in order. Each is validated against the whole specification; one that fails is rejected and the rest continue."""
    current = definition
    changes: list[dict] = []
    rejected: list[dict] = []
    for action in actions:
        raw = current.model_dump(mode="json")
        local: list[dict] = []
        try:
            HANDLERS[action.type](raw, action, local, provider)
            current = ApplicationDefinition.model_validate(raw)
        except ActionError as exc:
            rejected.append({"type": action.type, "reason": str(exc)})
            continue
        except ValidationError as exc:
            first = exc.errors()[0]
            rejected.append(
                {
                    "type": action.type,
                    "reason": f"This change does not fit the specification ({'.'.join(str(p) for p in first['loc'])}: {first['msg']}).",
                }
            )
            continue
        changes.extend(local)
    return current, changes, rejected


ACTION_TYPES = tuple(HANDLERS)
