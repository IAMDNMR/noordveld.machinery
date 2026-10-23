"""Validated business design, component draft and optional server-built frontend artifact."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator, ValidationInfo

from app.schemas.design_studio import ScreenSpec
from app.schemas.generated_frontend import GeneratedFrontend

Identifier = str
ID_PATTERN = r"^[a-z][a-z0-9_-]{1,79}$"
Kind = Literal["container", "text", "field", "table", "button"]
PERMISSION_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"


RefList = list[Annotated[str, Field(pattern=ID_PATTERN)]]


def _unique(values: list[str], what: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"Duplicate {what}")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Grid(Strict):
    mode: Literal["stack", "grid"]
    columns: int = Field(ge=1, le=12)

    @model_validator(mode="after")
    def stack_has_one_column(self):
        if self.mode == "stack" and self.columns != 1:
            raise ValueError("A stack has exactly one column")
        return self


class Layout(Strict):
    mobile: Grid
    tablet: Grid
    desktop: Grid


class Placement(Strict):
    span: int = Field(ge=1, le=12)


class Binding(Strict):
    source: Literal["fixture", "state"]
    dataset: str = Field(pattern=ID_PATTERN)
    field: str = Field(pattern=ID_PATTERN)


class Event(Strict):
    trigger: Literal["click", "change"]
    action: Literal["set_state", "navigate"]
    target: str = Field(pattern=ID_PATTERN)
    value: str | None = Field(default=None, max_length=200)


class Column(Strict):
    id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=120)


class Validation(Strict):
    kind: Literal["required", "email", "min_length", "max_length", "pattern", "minimum", "maximum"]
    value: str | int | float | bool | None = None
    message: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def safe_pattern(self):
        if self.kind == "pattern" and self.value not in ("digits", "letters", "alphanumeric"):
            raise ValueError("Unsupported pattern")
        if self.kind in ("minimum", "maximum") and (
            isinstance(self.value, bool) or not isinstance(self.value, (int, float))
        ):
            raise ValueError("A numeric bound needs a number")
        return self


class ContainerProps(Strict):
    title: str = Field(max_length=120)
    layout: Layout


class TextProps(Strict):
    content: str = Field(max_length=1000)


class FieldProps(Strict):
    field_type: Literal[
        "text", "number", "email", "telephone", "date", "select", "checkbox", "file"
    ]
    label: str = Field(min_length=1, max_length=120)
    help_text: str | None = Field(default=None, max_length=500)
    options: list[str] = Field(default_factory=list, max_length=100)
    validations: list[Validation] = Field(default_factory=list, max_length=20)


class TableProps(Strict):
    title: str = Field(min_length=1, max_length=120)
    columns: list[Column] = Field(min_length=1, max_length=30)
    searchable: bool = False
    filters: list[str] = Field(default_factory=list, max_length=20)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def unique_columns(self):
        if len({column.id for column in self.columns}) != len(self.columns):
            raise ValueError("Duplicate column ID")
        return self


class ButtonProps(Strict):
    label: str = Field(min_length=1, max_length=120)


PROPS = {
    "container": ContainerProps,
    "text": TextProps,
    "field": FieldProps,
    "table": TableProps,
    "button": ButtonProps,
}
CHILDREN = {
    "container": frozenset(PROPS),
    "text": frozenset(),
    "field": frozenset(),
    "table": frozenset(),
    "button": frozenset(),
}


class Trace(Strict):
    """Where a screen or component came from. Resolved against workflows and business in ApplicationDefinition."""

    generated: bool = False
    workflow_id: str | None = Field(default=None, pattern=ID_PATTERN)
    step_id: str | None = Field(default=None, pattern=ID_PATTERN)
    requirement_ids: RefList = Field(default_factory=list, max_length=30)
    entity_id: str | None = Field(default=None, pattern=ID_PATTERN)
    attribute_id: str | None = Field(default=None, pattern=ID_PATTERN)
    relationship_id: str | None = Field(
        default=None, pattern=ID_PATTERN, exclude_if=lambda value: value is None
    )
    rule_id: str | None = Field(default=None, pattern=ID_PATTERN)
    exception_id: str | None = Field(default=None, pattern=ID_PATTERN)
    # On a generated screen: digest of the screen as generated. A different digest now means a person edited it,
    # and regeneration must not overwrite that work.
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def coherent(self):
        _unique(self.requirement_ids, "trace requirement")
        if self.step_id is not None and self.workflow_id is None:
            raise ValueError("A traced step needs its workflow")
        if self.attribute_id is not None and self.entity_id is None:
            raise ValueError("A traced attribute needs its entity")
        if self.relationship_id is not None and self.entity_id is None:
            raise ValueError("A traced relationship needs its entity")
        return self


class Component(Strict):
    kind: Kind
    id: str = Field(pattern=ID_PATTERN)
    props: dict
    placement: Placement
    children: list[Component] | None = None
    binding: Binding | None = None
    events: list[Event] | None = None
    trace: Trace | None = None

    @model_validator(mode="after")
    def allowed_shape(self):
        self.props = PROPS[self.kind].model_validate(self.props).model_dump(mode="json")
        if self.kind == "container":
            if (
                self.children is None
                or len(self.children) > 100
                or self.binding is not None
                or self.events is not None
            ):
                raise ValueError("Invalid container")
            if any(child.kind not in CHILDREN[self.kind] for child in self.children):
                raise ValueError("Unsupported child")
        elif self.children is not None:
            raise ValueError("Only containers have children")
        elif self.kind == "button" and self.binding is not None:
            raise ValueError("Buttons cannot bind data")
        if self.events is not None and (
            len(self.events) > 10 or self.kind not in ("field", "button") and self.events
        ):
            raise ValueError("Unsupported component events")
        return self


class Screen(Strict):
    id: str = Field(pattern=ID_PATTERN)
    title: str = Field(min_length=1, max_length=120)
    components: list[Component] = Field(min_length=1, max_length=100)
    trace: Trace | None = None


class Metadata(Strict):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(max_length=1000)
    purpose: str = Field(max_length=1000)
    domain: Literal["finance", "crm", "inventory", "logistics", "manufacturing", "other"]


class Asset(Strict):
    asset_id: str = Field(pattern=ID_PATTERN)


# Parts of the generated screens a person may hide ("remove the steps from the screen"). Everything is shown unless listed here.
ScreenSection = Literal["stats", "pipelines", "steps", "exceptions", "records", "finished"]


class Theme(Strict):
    primary: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    background: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    surface: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    text: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    font: Literal["inter", "system", "serif"]
    logo: Asset | None = None
    hidden_sections: list[ScreenSection] = Field(default_factory=list, max_length=6)


class FixtureField(Strict):
    id: str = Field(pattern=ID_PATTERN)
    type: Literal["string", "number", "boolean"]


class Fixture(Strict):
    id: str = Field(pattern=ID_PATTERN)
    fields: list[FixtureField] = Field(max_length=40)
    rows: list[dict[str, str | int | float | bool | None]] = Field(max_length=100)

    @model_validator(mode="after")
    def valid_rows(self):
        types = {field.id: field.type for field in self.fields}
        if len(types) != len(self.fields):
            raise ValueError("Duplicate fixture field")
        for row in self.rows:
            if set(row) != set(types):
                raise ValueError("Fixture row fields differ from declaration")
            for key, value in row.items():
                if value is None:
                    continue
                typ = types[key]
                if not (
                    (typ == "string" and isinstance(value, str))
                    or (
                        typ == "number"
                        and isinstance(value, (int, float))
                        and not isinstance(value, bool)
                    )
                    or (typ == "boolean" and isinstance(value, bool))
                ):
                    raise ValueError("Fixture value type mismatch")
        return self


class LocalState(Strict):
    id: str = Field(pattern=ID_PATTERN)
    type: Literal["string", "number", "boolean"]
    initial: str | int | float | bool

    @model_validator(mode="after")
    def valid_initial(self):
        if not (
            (self.type == "string" and isinstance(self.initial, str))
            or (
                self.type == "number"
                and isinstance(self.initial, (int, float))
                and not isinstance(self.initial, bool)
            )
            or (self.type == "boolean" and isinstance(self.initial, bool))
        ):
            raise ValueError("Local state type mismatch")
        return self


class Navigation(Strict):
    screen_id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=120)


class WorkflowState(Strict):
    id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=120)
    kind: Literal[
        "start", "form", "search", "review", "approval", "branch", "action", "exception", "end"
    ]
    outputs: list[str] = Field(default_factory=list, max_length=30)
    # Terminal meaning of an end state; a failed or cancelled transaction is a valid, explicit outcome.
    outcome: Literal["success", "failure", "cancelled"] | None = None
    # Optional traceability into ApplicationDefinition.business; resolved there, not here.
    role_id: str | None = Field(default=None, pattern=ID_PATTERN)
    permission: str | None = Field(default=None, max_length=80, pattern=PERMISSION_PATTERN)
    requirement_ids: RefList = Field(default_factory=list, max_length=30)
    reads_entity_ids: RefList = Field(default_factory=list, max_length=30)
    writes_entity_ids: RefList = Field(default_factory=list, max_length=30)
    # None keeps legacy forms intact; an explicit map scopes inputs per task, including an empty map for a read-only action.
    input_fields: (
        dict[Annotated[str, Field(pattern=ID_PATTERN)], Annotated[RefList, Field(max_length=30)]]
        | None
    ) = Field(default=None, max_length=30, exclude_if=lambda value: value is None)
    input_relationships: (
        dict[Annotated[str, Field(pattern=ID_PATTERN)], Annotated[RefList, Field(max_length=30)]]
        | None
    ) = Field(default=None, max_length=30, exclude_if=lambda value: value is None)
    rule_ids: RefList = Field(default_factory=list, max_length=30)
    exception_ids: RefList = Field(default_factory=list, max_length=30)
    # What must hold before the step starts and what holds after it completes. Documentation, never evaluated.
    preconditions: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(
        default_factory=list, max_length=20
    )
    postconditions: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(
        default_factory=list, max_length=20
    )

    @model_validator(mode="after")
    def unique_references(self):
        for name in (
            "requirement_ids",
            "reads_entity_ids",
            "writes_entity_ids",
            "rule_ids",
            "exception_ids",
        ):
            _unique(getattr(self, name), f"reference in {name}")
        _unique(self.outputs, "output")
        for mapping in (self.input_fields, self.input_relationships):
            for refs in (mapping or {}).values():
                _unique(refs, "task input")
        if self.outcome is not None and self.kind != "end":
            raise ValueError("Only an end state has an outcome")
        return self


class WorkflowCondition(Strict):
    kind: Literal["always", "equals", "not_equals"]
    field: str | None = Field(default=None, pattern=ID_PATTERN)
    value: str | int | bool | None = None

    @model_validator(mode="after")
    def valid_condition(self):
        if self.kind != "always" and (self.field is None or self.value is None):
            raise ValueError("Conditional transition needs a field and value")
        if self.kind == "always" and (self.field is not None or self.value is not None):
            raise ValueError("Unconditional transition has no expression")
        return self


class WorkflowTransition(Strict):
    id: str = Field(pattern=ID_PATTERN)
    source: str = Field(pattern=ID_PATTERN)
    target: str = Field(pattern=ID_PATTERN)
    condition: WorkflowCondition


class WorkflowDefinition(Strict):
    version: Literal[1]
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    states: list[WorkflowState] = Field(min_length=2, max_length=100)
    transitions: list[WorkflowTransition] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def valid_graph(self):
        ids = {state.id for state in self.states}
        if len(ids) != len(self.states) or len({edge.id for edge in self.transitions}) != len(
            self.transitions
        ):
            raise ValueError("Duplicate workflow ID")
        starts = [state.id for state in self.states if state.kind == "start"]
        ends = {state.id for state in self.states if state.kind == "end"}
        if len(starts) != 1 or not ends:
            raise ValueError("Workflow needs one start and at least one end")
        if any(edge.source not in ids or edge.target not in ids for edge in self.transitions):
            raise ValueError("Transition refers to unknown state")
        outputs = {field for state in self.states for field in state.outputs}
        if any(
            edge.condition.kind != "always" and edge.condition.field not in outputs
            for edge in self.transitions
        ):
            raise ValueError("Condition refers to undeclared output")
        if any(edge.source in ends or edge.target == starts[0] for edge in self.transitions):
            raise ValueError("Invalid start or end transition")
        reached = {starts[0]}
        while True:
            expanded = reached | {
                edge.target for edge in self.transitions if edge.source in reached
            }
            if expanded == reached:
                break
            reached = expanded
        if reached != ids or not (reached & ends):
            raise ValueError("Unreachable workflow state")
        finishing = set(ends)
        while True:
            expanded = finishing | {
                edge.source for edge in self.transitions if edge.target in finishing
            }
            if expanded == finishing:
                break
            finishing = expanded
        if finishing != ids:
            raise ValueError("Workflow state cannot reach an end state")
        return self


# ── Business design: declarative knowledge stored with the project revision; never executed ────────────────────


class KnowledgeOrigin(Strict):
    """The reference-pack item an instantiated item was copied from, so later pack versions can mark it stale."""

    pack_id: str = Field(pattern=ID_PATTERN)
    pack_version: str = Field(min_length=1, max_length=40)
    item_id: str = Field(pattern=ID_PATTERN)


class IntakeContext(Strict):
    region: Literal["global", "eu", "india"] | None = None
    industry_id: str | None = Field(default=None, pattern=ID_PATTERN)
    catalog_version: str = Field(min_length=1, max_length=40)
    skipped: list[Literal["region", "industry"]] = Field(default_factory=list, max_length=2)


class BusinessBrief(Strict):
    intake: IntakeContext | None = Field(default=None, exclude_if=lambda value: value is None)
    goal: str = Field(default="", max_length=2000)
    problem: str = Field(default="", max_length=2000)
    domain_id: str | None = Field(default=None, pattern=ID_PATTERN)
    subdomain: str = Field(default="", max_length=120)
    capability: str = Field(default="", max_length=200)
    purpose: str = Field(default="", max_length=1000)
    user_types: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list, max_length=30
    )
    outcomes: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(
        default_factory=list, max_length=30
    )
    constraints: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(
        default_factory=list, max_length=50
    )
    dependencies: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(
        default_factory=list, max_length=50
    )


class AcceptanceCriterion(Strict):
    id: str = Field(pattern=ID_PATTERN)
    statement: str = Field(min_length=1, max_length=500)


class Requirement(Strict):
    id: str = Field(pattern=ID_PATTERN)
    statement: str = Field(min_length=1, max_length=1000)
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
    priority: Literal["must", "should", "could", "wont"]
    status: Literal["draft", "agreed", "deferred", "rejected"]
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list, max_length=20)
    deferral_reason: str = Field(default="", max_length=1000)
    origin: KnowledgeOrigin | None = None

    @model_validator(mode="after")
    def unique_criteria(self):
        _unique([item.id for item in self.acceptance_criteria], "acceptance criterion ID")
        if self.kind == "non_functional" and self.category is None:
            raise ValueError("A non-functional requirement needs a category")
        return self


class BusinessRole(Strict):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    responsibilities: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(
        default_factory=list, max_length=30
    )
    permissions: list[Annotated[str, Field(max_length=80, pattern=PERMISSION_PATTERN)]] = Field(
        default_factory=list, max_length=50
    )
    approval_authority: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(
        default_factory=list, max_length=20
    )
    origin: KnowledgeOrigin | None = None

    @model_validator(mode="after")
    def unique_permissions(self):
        _unique(self.permissions, "permission")
        return self


class AttributeReference(Strict):
    """The attribute's value must match an existing record's attribute (a foreign key)."""

    entity_id: str = Field(pattern=ID_PATTERN)
    attribute_id: str = Field(pattern=ID_PATTERN)


NUMERIC_TYPES = frozenset({"integer", "decimal"})
SAFE_PATTERNS = ("digits", "letters", "alphanumeric")


class EntityAttribute(Strict):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    type: Literal["string", "integer", "decimal", "boolean", "date", "datetime"]
    required: bool = False
    key: bool = False
    # True when the business distinguishes "unknown" from zero, false or empty; generated UI must not default it.
    allow_unknown: bool = False
    description: str = Field(default="", max_length=500)
    validations: list[Validation] = Field(default_factory=list, max_length=20)
    # Where the value comes from. Anything but user_entered is system-managed and never an editable input.
    value_source: Literal["user_entered", "system_generated", "calculated", "imported"] = (
        "user_entered"
    )
    # A user-entered value can still be read-only (set once, then fixed).
    writable: bool = True
    default: str | int | float | bool | None = None
    format: (
        Literal["email", "phone", "url", "postal_code", "currency_amount", "percentage"] | None
    ) = None
    minimum: float | None = None
    maximum: float | None = None
    min_length: int | None = Field(default=None, ge=0, le=10000)
    max_length: int | None = Field(default=None, ge=1, le=10000)
    # Only fixed, linear-time pattern classes: no user-supplied regular expressions.
    pattern: Literal["digits", "letters", "alphanumeric"] | None = None
    enum: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=50
    )
    sensitivity: Literal["public", "internal", "personal", "confidential"] = "internal"
    owner_role_id: str | None = Field(default=None, pattern=ID_PATTERN)
    reference: AttributeReference | None = None

    @property
    def system_managed(self) -> bool:
        return self.value_source != "user_entered"

    @model_validator(mode="after")
    def coherent(self):
        if self.key and not self.required:
            raise ValueError("A key attribute must be required")
        if self.key and self.allow_unknown:
            raise ValueError("A key attribute cannot be unknown")
        if self.system_managed and self.writable:
            raise ValueError("A system-managed attribute cannot be writable by users")
        if (
            self.minimum is not None or self.maximum is not None
        ) and self.type not in NUMERIC_TYPES:
            raise ValueError("Minimum and maximum apply to numbers only")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Minimum is greater than maximum")
        if (
            self.min_length is not None
            or self.max_length is not None
            or self.pattern
            or self.format
        ) and self.type != "string":
            raise ValueError("Length, pattern and format apply to text only")
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise ValueError("Minimum length is greater than maximum length")
        _unique(self.enum, "enumeration value")
        if self.enum and self.type != "string":
            raise ValueError("An enumeration applies to text only")
        if self.default is not None:
            if self.enum and self.default not in self.enum:
                raise ValueError("The default is not one of the allowed values")
            expected = {
                "string": str,
                "integer": int,
                "decimal": (int, float),
                "boolean": bool,
                "date": str,
                "datetime": str,
            }[self.type]
            if not isinstance(self.default, expected) or (
                self.type in NUMERIC_TYPES and isinstance(self.default, bool)
            ):
                raise ValueError("The default does not match the attribute type")
        return self


class EntityRelationship(Strict):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    target: str = Field(pattern=ID_PATTERN)
    cardinality: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"]
    # A required relationship must be satisfied when a record of the source entity is created.
    required: bool = False


class BusinessEntity(Strict):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    owner_role_id: str | None = Field(default=None, pattern=ID_PATTERN)
    source_system: str = Field(default="", max_length=200)
    attributes: list[EntityAttribute] = Field(default_factory=list, max_length=60)
    relationships: list[EntityRelationship] = Field(default_factory=list, max_length=30)
    origin: KnowledgeOrigin | None = None

    @model_validator(mode="after")
    def unique_members(self):
        _unique([item.id for item in self.attributes], "attribute ID")
        _unique([item.id for item in self.relationships], "relationship ID")
        return self


class RuleSource(Strict):
    kind: Literal[
        "business_owner",
        "implemented_code",
        "document",
        "graph_data",
        "workshop",
        "synthetic_assumption",
    ]
    reference: str = Field(min_length=1, max_length=300)


class RuleExecution(Strict):
    """Bounded executable predicate; prose conditions are never evaluated as code."""

    kind: Literal["compare", "value"]
    field: str = Field(pattern=r"^[a-z][a-z0-9_-]*\.[a-z][a-z0-9_-]*$")
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "present"] = "eq"
    other_field: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]*\.[a-z][a-z0-9_-]*$")
    value: str | int | float | bool | None = None
    pass_outcome: str | None = Field(default=None, max_length=60)
    fail_outcome: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def operands(self):
        if (
            self.kind == "compare"
            and self.operator != "present"
            and self.other_field is None
            and self.value is None
        ):
            raise ValueError("A comparison needs a second attribute or a literal value")
        return self


class BusinessRule(Strict):
    id: str = Field(pattern=ID_PATTERN)
    description: str = Field(min_length=1, max_length=1000)
    type: Literal["validation", "decision", "calculation", "policy"] = "policy"
    status: Literal["confirmed", "assumption"]
    source: RuleSource
    # Human-readable condition; documentation only, never evaluated.
    condition: str = Field(default="", max_length=1000)
    # Named results a decision can produce; transitions branch on these by rule ID.
    outcomes: list[
        Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")]
    ] = Field(default_factory=list, max_length=20)
    origin: KnowledgeOrigin | None = None
    execution: RuleExecution | None = None

    @model_validator(mode="after")
    def coherent(self):
        _unique(self.outcomes, "rule outcome")
        if self.status == "confirmed" and self.source.kind == "synthetic_assumption":
            raise ValueError("A synthetic assumption cannot be a confirmed rule")
        if self.type == "decision" and len(self.outcomes) < 2:
            raise ValueError("A decision rule needs at least two outcomes")
        if self.execution and self.execution.kind == "compare" and self.outcomes:
            if (
                self.execution.pass_outcome not in self.outcomes
                or self.execution.fail_outcome not in self.outcomes
            ):
                raise ValueError("Executable decision outcomes must be declared by the rule")
            if self.execution.pass_outcome == self.execution.fail_outcome:
                raise ValueError("Executable decision outcomes must be distinct")
        if self.execution and self.execution.kind == "value" and not self.outcomes:
            raise ValueError("A recorded decision value requires declared outcomes")
        return self


class ExceptionScenario(Strict):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    trigger: str = Field(min_length=1, max_length=500)
    recovery: str = Field(min_length=1, max_length=1000)
    # The workflow state the scenario leads to: recovery resumes there, terminate ends there, escalate hands it to
    # a step owned by someone with more authority.
    resolution: Literal["recover", "terminate", "escalate"] | None = None
    resolution_state_id: str | None = Field(default=None, pattern=ID_PATTERN)
    origin: KnowledgeOrigin | None = None

    @model_validator(mode="after")
    def coherent(self):
        if (self.resolution is None) != (self.resolution_state_id is None):
            raise ValueError("Resolution and resolution state are set together")
        return self


class BusinessDecision(Strict):
    """A business-owner decision the design depends on. Open decisions block approval; nothing is decided for the owner."""

    id: str = Field(pattern=ID_PATTERN)
    question: str = Field(min_length=1, max_length=500)
    status: Literal["open", "decided", "deferred"] = "open"
    answer: str = Field(default="", max_length=1000)
    deferral_reason: str = Field(default="", max_length=1000)
    affects: RefList = Field(default_factory=list, max_length=50)
    origin: KnowledgeOrigin | None = None


class Integration(Strict):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    system: str = Field(min_length=1, max_length=120)
    direction: Literal["inbound", "outbound", "bidirectional"]
    events: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=30
    )
    entity_ids: RefList = Field(default_factory=list, max_length=30)
    failure_handling: str = Field(default="", max_length=1000)
    # "defined" means the exchange, its data and its failure handling are specified; "deferred" keeps it visible as open.
    contract_status: Literal["defined", "deferred"] = "deferred"
    origin: KnowledgeOrigin | None = None


class Term(Strict):
    id: str = Field(pattern=ID_PATTERN)
    term: str = Field(min_length=1, max_length=120)
    definition: str = Field(min_length=1, max_length=1000)
    origin: KnowledgeOrigin | None = None


class DiscoveryQuestion(Strict):
    id: str = Field(pattern=ID_PATTERN)
    topic: str = Field(min_length=1, max_length=60)
    text: str = Field(min_length=1, max_length=500)
    answer: str = Field(default="", max_length=2000)
    status: Literal["open", "answered", "not_applicable"] = "open"


class KnowledgeLink(Strict):
    pack_id: str = Field(pattern=ID_PATTERN)
    pack_version: str = Field(min_length=1, max_length=40)


class BusinessDefinition(Strict):
    brief: BusinessBrief = Field(default_factory=BusinessBrief)
    requirements: list[Requirement] = Field(default_factory=list, max_length=200)
    roles: list[BusinessRole] = Field(default_factory=list, max_length=50)
    entities: list[BusinessEntity] = Field(default_factory=list, max_length=100)
    rules: list[BusinessRule] = Field(default_factory=list, max_length=200)
    exceptions: list[ExceptionScenario] = Field(default_factory=list, max_length=100)
    decisions: list[BusinessDecision] = Field(default_factory=list, max_length=100)
    integrations: list[Integration] = Field(default_factory=list, max_length=50)
    terms: list[Term] = Field(default_factory=list, max_length=200)
    questions: list[DiscoveryQuestion] = Field(default_factory=list, max_length=100)
    knowledge: list[KnowledgeLink] = Field(default_factory=list, max_length=10)

    def item_ids(self) -> set[str]:
        return {
            item.id
            for group in (
                self.requirements,
                self.roles,
                self.entities,
                self.rules,
                self.exceptions,
                self.decisions,
                self.integrations,
                self.terms,
            )
            for item in group
        }

    @model_validator(mode="after")
    def unique_ids_and_references(self, info: ValidationInfo):
        # One ID namespace across the section keeps every trace reference unambiguous.
        _unique(
            [
                item.id
                for group in (
                    self.requirements,
                    self.roles,
                    self.entities,
                    self.rules,
                    self.exceptions,
                    self.decisions,
                    self.integrations,
                    self.terms,
                )
                for item in group
            ],
            "business ID",
        )
        _unique([item.id for item in self.questions], "question ID")
        _unique([item.pack_id for item in self.knowledge], "knowledge pack")
        if info is not None and info.context and "dependencies" in info.context:
            # A reference-pack section may refer to what the packs it depends on define. Those references are checked, strictly,
            # on the merged definition (ReferencePack.references_resolve); here only the section's own uniqueness is.
            return self
        entity_ids = {entity.id for entity in self.entities}
        role_ids = {role.id for role in self.roles}
        if any(
            relation.target not in entity_ids
            for entity in self.entities
            for relation in entity.relationships
        ):
            raise ValueError("Relationship refers to unknown entity")
        if any(
            entity.owner_role_id is not None and entity.owner_role_id not in role_ids
            for entity in self.entities
        ):
            raise ValueError("Entity owner refers to unknown role")
        attributes = {
            entity.id: {attribute.id for attribute in entity.attributes} for entity in self.entities
        }
        for entity in self.entities:
            for attribute in entity.attributes:
                if attribute.owner_role_id is not None and attribute.owner_role_id not in role_ids:
                    raise ValueError("Attribute owner refers to unknown role")
                ref = attribute.reference
                if ref is not None and (
                    ref.entity_id not in attributes
                    or ref.attribute_id not in attributes[ref.entity_id]
                ):
                    raise ValueError("Attribute reference refers to unknown entity or attribute")
        if any(
            ref not in entity_ids
            for integration in self.integrations
            for ref in integration.entity_ids
        ):
            raise ValueError("Integration refers to unknown entity")
        return self


class ApprovalRecord(Strict):
    """Written only by the server's approve endpoint; bound to one revision and the digest of what was approved."""

    scope: Literal["process", "design"]
    revision: int = Field(ge=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_by: str = Field(min_length=1, max_length=120)
    approved_at: str = Field(min_length=1, max_length=40)
    warnings_acknowledged: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list, max_length=500
    )
    comment: str = Field(default="", max_length=1000)


class StudioFlow(Strict):
    reviewed: list[
        Literal["brief", "knowledge", "workflow", "data", "screen", "rules", "roles", "checks"]
    ] = Field(default_factory=list, max_length=8)
    reviewed_digests: dict[str, Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]] = Field(
        default_factory=dict, max_length=8, exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def ordered(self):
        order = ["brief", "knowledge", "workflow", "data", "screen", "rules", "roles", "checks"]
        if self.reviewed != order[: len(self.reviewed)]:
            raise ValueError("Stage reviews must be sequential")
        if set(self.reviewed_digests) - set(self.reviewed):
            raise ValueError("Review digests must belong to reviewed stages")
        return self


class TemplateSelection(Strict):
    """The application template a project was configured against, at its exact version."""

    template_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    selected_at: str = Field(min_length=1, max_length=40)


class ProjectLifecycle(Strict):
    status: Literal["active", "archived", "trashed"] = "active"
    restore_status: Literal["active", "archived"] = "active"


class ApplicationDefinition(Strict):
    version: Literal[2]
    id: str = Field(pattern=ID_PATTERN)
    metadata: Metadata
    screens: list[Screen] = Field(min_length=1, max_length=150)
    theme: Theme
    fixtures: list[Fixture] = Field(default_factory=list, max_length=20)
    local_state: list[LocalState] = Field(default_factory=list, max_length=100)
    navigation: list[Navigation] = Field(default_factory=list, max_length=150)
    workflows: list[str] = Field(default_factory=list, max_length=20)
    workflow_definitions: list[WorkflowDefinition] = Field(default_factory=list, max_length=20)
    business: BusinessDefinition = Field(default_factory=BusinessDefinition)
    approvals: list[ApprovalRecord] = Field(default_factory=list, max_length=2)
    generated_frontend: GeneratedFrontend | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    frontend_required: bool = Field(default=False, exclude_if=lambda value: not value)
    template: TemplateSelection | None = Field(default=None, exclude_if=lambda value: value is None)
    project_lifecycle: ProjectLifecycle | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    studio_flow: StudioFlow | None = None
    revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_references(self):
        ids = {self.id}
        screen_ids = set()
        for screen in self.screens:
            if screen.id in ids:
                raise ValueError("Duplicate ID")
            ids.add(screen.id)
            screen_ids.add(screen.id)
        fixture_map = {
            fixture.id: {field.id for field in fixture.fields} for fixture in self.fixtures
        }
        state_ids = {state.id for state in self.local_state}
        if len(fixture_map) != len(self.fixtures) or len(state_ids) != len(self.local_state):
            raise ValueError("Duplicate data ID")
        business = self.business
        workflow_states = {
            workflow.id: {state.id for state in workflow.states}
            for workflow in self.workflow_definitions
        }
        requirement_ids = {item.id for item in business.requirements}
        entity_attributes = {
            item.id: {attribute.id for attribute in item.attributes} for item in business.entities
        }
        entity_relationships = {
            item.id: {relationship.id for relationship in item.relationships}
            for item in business.entities
        }
        for rule in business.rules:
            if rule.execution:
                for ref in (rule.execution.field, rule.execution.other_field):
                    if ref:
                        entity, attribute = ref.split(".")
                        if attribute not in entity_attributes.get(entity, set()):
                            raise ValueError("Executable rule references an unknown attribute")
        rule_ids = {item.id for item in business.rules}
        exception_ids = {item.id for item in business.exceptions}

        def check_trace(trace: Trace | None):
            if trace is None:
                return
            if trace.workflow_id is not None and trace.workflow_id not in workflow_states:
                raise ValueError("Trace refers to unknown workflow")
            if (
                trace.step_id is not None
                and trace.step_id not in workflow_states[trace.workflow_id]
            ):
                raise ValueError("Trace refers to unknown workflow step")
            if any(ref not in requirement_ids for ref in trace.requirement_ids):
                raise ValueError("Trace refers to unknown requirement")
            if trace.entity_id is not None and (
                trace.entity_id not in entity_attributes
                or (
                    trace.attribute_id is not None
                    and trace.attribute_id not in entity_attributes[trace.entity_id]
                )
            ):
                raise ValueError("Trace refers to unknown entity or attribute")
            if (
                trace.relationship_id is not None
                and trace.relationship_id not in entity_relationships.get(trace.entity_id, set())
            ):
                raise ValueError("Trace refers to unknown relationship")
            if (trace.rule_id is not None and trace.rule_id not in rule_ids) or (
                trace.exception_id is not None and trace.exception_id not in exception_ids
            ):
                raise ValueError("Trace refers to unknown rule or exception")

        count = 0

        def visit(node: Component, depth: int, root: bool):
            nonlocal count
            count += 1
            if count > 5000 or depth > 4 or node.id in ids:
                raise ValueError("Duplicate ID or oversized component tree")
            ids.add(node.id)
            if root and node.kind == "field":
                raise ValueError("Form field must be in a section")
            if node.binding:
                binding = node.binding
                if binding.source == "fixture" and (
                    binding.dataset not in fixture_map
                    or binding.field not in fixture_map[binding.dataset]
                ):
                    raise ValueError("Unknown fixture binding")
                if binding.source == "state" and (
                    binding.dataset not in state_ids or binding.field != "value"
                ):
                    raise ValueError("Unknown local-state binding")
            for event in node.events or []:
                if event.action == "navigate" and event.target not in screen_ids:
                    raise ValueError("Unknown navigation target")
                if event.action == "set_state" and event.target not in state_ids:
                    raise ValueError("Unknown state target")
            check_trace(node.trace)
            for child in node.children or []:
                visit(child, depth + 1, False)

        for screen in self.screens:
            check_trace(screen.trace)
            for node in screen.components:
                visit(node, 1, True)
        if any(item.screen_id not in screen_ids for item in self.navigation):
            raise ValueError("Unknown screen in navigation")
        workflow_ids = set(workflow_states)
        if len(workflow_ids) != len(self.workflow_definitions) or any(
            ref not in workflow_ids for ref in self.workflows
        ):
            raise ValueError("Unknown or duplicate workflow reference")
        known = {
            "requirement_ids": requirement_ids,
            "reads_entity_ids": set(entity_attributes),
            "writes_entity_ids": set(entity_attributes),
            "rule_ids": rule_ids,
            "exception_ids": exception_ids,
        }
        roles = {item.id: set(item.permissions) for item in business.roles}
        rule_outcomes = {item.id: set(item.outcomes) for item in business.rules}
        all_states = set().union(*workflow_states.values()) if workflow_states else set()
        for workflow in self.workflow_definitions:
            for state in workflow.states:
                if state.role_id is not None and state.role_id not in roles:
                    raise ValueError("Workflow step refers to unknown role")
                if state.permission is not None and (
                    state.role_id is None or state.permission not in roles[state.role_id]
                ):
                    raise ValueError("Workflow step permission is not held by its role")
                for name, ids_ in known.items():
                    if any(ref not in ids_ for ref in getattr(state, name)):
                        raise ValueError(f"Workflow step has unknown reference in {name}")
                for mapping, members in (
                    (state.input_fields, entity_attributes),
                    (state.input_relationships, entity_relationships),
                ):
                    for entity_id, refs in (mapping or {}).items():
                        if entity_id not in state.writes_entity_ids or any(
                            ref not in members.get(entity_id, set()) for ref in refs
                        ):
                            raise ValueError(
                                "Task inputs must refer to fields or relationships of an entity this step writes"
                            )
            for edge in workflow.transitions:
                # A branch on a rule ID must use one of that rule's declared outcomes.
                if (
                    edge.condition.kind != "always"
                    and edge.condition.field in rule_outcomes
                    and str(edge.condition.value) not in rule_outcomes[edge.condition.field]
                ):
                    raise ValueError("Condition uses an outcome the rule does not declare")
        if any(
            item.resolution_state_id is not None and item.resolution_state_id not in all_states
            for item in business.exceptions
        ):
            raise ValueError("Exception resolution refers to unknown workflow state")
        affectable = business.item_ids() | all_states
        if any(
            ref not in affectable for decision in business.decisions for ref in decision.affects
        ):
            raise ValueError("Decision affects an unknown item")
        _unique([item.scope for item in self.approvals], "approval scope")
        return self


def convert_v1(spec: ScreenSpec, application_id: str = "app_imported") -> ApplicationDefinition:
    """Explicit conversion; does not mutate a stored v1 draft."""
    grid = {
        "mobile": {"mode": "stack", "columns": 1},
        "tablet": {"mode": "grid", "columns": 2},
        "desktop": {"mode": "grid", "columns": 2 if spec.layout == "two-column" else 1},
    }
    nodes = []
    for section in spec.sections:
        fields = [
            {
                "kind": "field",
                "id": field.id,
                "props": {
                    "field_type": field.type,
                    "label": field.label,
                    "help_text": field.help_text,
                    "options": field.options,
                    "validations": [rule.model_dump(mode="json") for rule in field.validations],
                },
                "placement": {"span": 6},
                "binding": None,
                "events": [],
            }
            for field in section.fields
        ]
        nodes.append(
            {
                "kind": "container",
                "id": section.id,
                "props": {"title": section.title, "layout": grid},
                "placement": {"span": 12},
                "children": fields,
            }
        )
    for table in spec.tables:
        nodes.append(
            {
                "kind": "table",
                "id": table.id,
                "props": {
                    "title": table.title,
                    "columns": [
                        {"id": f"{table.id}_col_{i}", "label": col}
                        for i, col in enumerate(table.columns)
                    ],
                    "searchable": table.searchable,
                    "filters": table.filters,
                    "page_size": table.page_size,
                },
                "placement": {"span": 12},
                "binding": None,
                "events": [],
            }
        )
    for i, label in enumerate(spec.buttons):
        nodes.append(
            {
                "kind": "button",
                "id": f"button_{i + 1}",
                "props": {"label": label},
                "placement": {"span": 12},
                "binding": None,
                "events": [],
            }
        )
    return ApplicationDefinition.model_validate(
        {
            "version": 2,
            "id": application_id,
            "metadata": {
                "name": spec.name,
                "description": spec.description,
                "purpose": spec.purpose,
                "domain": "other",
            },
            "screens": [{"id": "screen_main", "title": spec.name, "components": nodes}],
            "theme": {
                "primary": "#00756A",
                "background": "#FFFFFF",
                "surface": "#F7F5F0",
                "text": "#14181A",
                "font": "inter",
                "logo": None,
            },
        }
    )
