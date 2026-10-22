"""Versioned domain-pack schema (layers A–F): registry, ontology, entities, relationships, behaviour and source mappings.

A pack is declarative knowledge. Nothing in it is executed. Every item has a stable ID in one pack-wide namespace and its
own provenance, so verified facts, derived inferences, synthetic demo data and assumptions never blur together.
Structural integrity (duplicate IDs, dangling references, incompatible endpoints, prohibited cycles) is enforced here;
judgement calls (possible duplicates, unconfirmed items) are reported by `validation.analyze`.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ID = r"^[a-z][a-z0-9_]{1,79}$"
REL_TYPE = r"^[A-Z][A-Z0-9_]{1,59}$"
SCHEMA_VERSION = 1

Status = Literal["draft", "under_review", "approved", "deprecated"]
Cardinality = Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"]
Text = Annotated[str, Field(min_length=1, max_length=300)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _unique(values: list[str], what: str) -> None:
    seen: set[str] = set()
    dupes = sorted({value for value in values if value in seen or seen.add(value)})
    if dupes:
        raise ValueError(f"Duplicate {what}: {', '.join(dupes)}")


class Provenance(Strict):
    """Where an item comes from and how far it can be trusted.

    verified_source: read from a source document or dataset. derived: inferred by a stated rule. synthetic: demo data.
    user_provided: stated in the project brief. assumption: not confirmed by anyone; never presented as policy.
    """

    kind: Literal["verified_source", "derived", "synthetic", "user_provided", "assumption"]
    reference: str = Field(min_length=1, max_length=300)
    verification: Literal["verified", "unverified", "needs_review"] = "unverified"

    @model_validator(mode="after")
    def coherent(self):
        if self.kind in ("assumption", "synthetic") and self.verification == "verified":
            raise ValueError(
                "An assumption or synthetic item cannot be verified business knowledge"
            )
        return self


class DomainDependency(Strict):
    """Why one domain needs another. `unclassified` is for dependencies carried over without the business having
    said whether they are mandatory; nothing is assumed to be required by default."""

    domain_id: str = Field(pattern=ID)
    kind: Literal["required", "optional", "conditional", "unclassified"]
    reason: str = Field(min_length=1, max_length=300)
    condition: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def coherent(self):
        if (self.kind == "conditional") != bool(self.condition.strip()):
            raise ValueError(
                f"Dependency on {self.domain_id}: a conditional dependency states its condition, and only it does"
            )
        return self


class Domain(Strict):
    id: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(max_length=1000)
    scope: str = Field(default="", max_length=1000)
    parent_id: str | None = Field(default=None, pattern=ID)
    depends_on: list[Annotated[str, Field(pattern=ID)]] = Field(default_factory=list, max_length=20)
    dependencies: list[DomainDependency] = Field(default_factory=list, max_length=20)
    capabilities: list[Text] = Field(default_factory=list, max_length=40)
    keywords: list[Annotated[str, Field(min_length=2, max_length=60)]] = Field(
        default_factory=list, max_length=80
    )
    provenance: Provenance


class Synonym(Strict):
    term: str = Field(min_length=1, max_length=120)
    # Synonyms hold within a domain; the same word may mean something else elsewhere.
    domain_id: str | None = Field(default=None, pattern=ID)
    note: str = Field(default="", max_length=300)


class Concept(Strict):
    """A business concept. Distinct from the database entity that may represent it (`Entity.concept_id`)."""

    id: str = Field(pattern=ID)
    canonical_name: str = Field(min_length=1, max_length=120)
    kind: Literal["business_concept", "event", "role", "measure", "code_list", "process_concept"]
    domain_id: str = Field(pattern=ID)
    definition: str = Field(min_length=1, max_length=1000)
    synonyms: list[Synonym] = Field(default_factory=list, max_length=30)
    acronyms: list[Annotated[str, Field(min_length=1, max_length=20)]] = Field(
        default_factory=list, max_length=10
    )
    broader_id: str | None = Field(default=None, pattern=ID)
    # Same meaning, different system or vocabulary. Never inferred from a similar name.
    equivalent_ids: list[Annotated[str, Field(pattern=ID)]] = Field(
        default_factory=list, max_length=10
    )
    semantic_type: str = Field(default="", max_length=80)
    unit: str = Field(default="", max_length=40)
    code_values: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=100
    )
    provenance: Provenance


class Attribute(Strict):
    id: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=120)
    type: Literal["string", "integer", "decimal", "boolean", "date", "datetime", "code"]
    semantic_type: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=500)
    required: bool = False
    key: bool = False
    unique: bool = False
    value_source: Literal["user_entered", "system_generated", "calculated", "imported"] = "imported"
    mutability: Literal["immutable", "system_updated", "user_updated"] = "system_updated"
    default: str | int | float | bool | None = None
    code_list_id: str | None = Field(default=None, pattern=ID)
    sensitivity: Literal["public", "internal", "personal", "confidential"] = "internal"
    provenance: Provenance | None = None

    @model_validator(mode="after")
    def coherent(self):
        if self.key and not self.required:
            raise ValueError(f"Key attribute {self.id} must be required")
        if self.value_source != "user_entered" and self.mutability == "user_updated":
            raise ValueError(f"System-managed attribute {self.id} cannot be user-updated")
        if self.type == "code" and self.code_list_id is None:
            raise ValueError(f"Code attribute {self.id} needs a code list")
        return self


class Entity(Strict):
    id: str = Field(pattern=ID)
    canonical_name: str = Field(min_length=1, max_length=120)
    domain_id: str = Field(pattern=ID)
    concept_id: str | None = Field(default=None, pattern=ID)
    description: str = Field(min_length=1, max_length=1000)
    attributes: list[Attribute] = Field(default_factory=list, max_length=80)
    natural_keys: list[Annotated[str, Field(pattern=ID)]] = Field(
        default_factory=list, max_length=5
    )
    # Composition/inheritance only where the domain justifies it.
    extends_id: str | None = Field(default=None, pattern=ID)
    # The operational graph label this entity describes. A read-only mapping, never a write target.
    operational_label: str | None = Field(default=None, pattern=r"^[A-Z][A-Za-z0-9]{1,59}$")
    provenance: Provenance

    @model_validator(mode="after")
    def coherent(self):
        names = [item.id for item in self.attributes]
        _unique(names, f"attribute in {self.id}")
        if any(key not in names for key in self.natural_keys):
            raise ValueError(f"Natural key of {self.id} is not one of its attributes")
        return self


class Relationship(Strict):
    id: str = Field(pattern=ID)
    source_id: str = Field(pattern=ID)
    type: str = Field(pattern=REL_TYPE)
    target_id: str = Field(pattern=ID)
    cardinality: Cardinality
    meaning: str = Field(min_length=1, max_length=500)
    required: bool = False
    # A hierarchy such as SUBCATEGORY_OF must not loop back on itself.
    acyclic: bool = False
    constraints: list[Text] = Field(default_factory=list, max_length=10)
    provenance: Provenance
    valid_from_version: str = Field(default="", max_length=40)


class Event(Strict):
    id: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=120)
    entity_id: str = Field(pattern=ID)
    from_state: str = Field(default="", max_length=60)
    to_state: str = Field(default="", max_length=60)
    provenance: Provenance


class Rule(Strict):
    id: str = Field(pattern=ID)
    description: str = Field(min_length=1, max_length=1000)
    type: Literal["validation", "decision", "calculation", "policy"]
    status: Literal["confirmed", "assumption"]
    entity_ids: list[Annotated[str, Field(pattern=ID)]] = Field(default_factory=list, max_length=20)
    provenance: Provenance

    @model_validator(mode="after")
    def coherent(self):
        if self.status == "confirmed" and self.provenance.kind == "assumption":
            raise ValueError(f"Rule {self.id} is an assumption and cannot be confirmed")
        return self


class Process(Strict):
    """A reusable process template. Steps live in the Design Studio pack it points to; projects may override them."""

    id: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=120)
    domain_id: str = Field(pattern=ID)
    description: str = Field(default="", max_length=1000)
    entity_ids: list[Annotated[str, Field(pattern=ID)]] = Field(default_factory=list, max_length=40)
    rule_ids: list[Annotated[str, Field(pattern=ID)]] = Field(default_factory=list, max_length=40)
    event_ids: list[Annotated[str, Field(pattern=ID)]] = Field(default_factory=list, max_length=40)
    roles: list[Text] = Field(default_factory=list, max_length=20)
    design_template: str = Field(default="", max_length=120)
    provenance: Provenance


class Decision(Strict):
    """A business-owner decision. Stays open until the owner decides it; the knowledge base never answers it."""

    id: str = Field(pattern=ID)
    question: str = Field(min_length=1, max_length=500)
    status: Literal["open", "decided"] = "open"
    answer: str = Field(default="", max_length=1000)
    affects: list[Annotated[str, Field(pattern=ID)]] = Field(default_factory=list, max_length=40)
    provenance: Provenance

    @model_validator(mode="after")
    def coherent(self):
        if (self.status == "decided") != bool(self.answer.strip()):
            raise ValueError(
                f"Decision {self.id}: a decided decision needs an answer and an open one has none"
            )
        return self


class AppRole(Strict):
    """A role of ONE generated application (a planner, a dispatcher, a warehouse operator…). Never a global role: a user
    holds it only through an explicit grant for an organization and that application."""

    id: str = Field(pattern=ID)
    application_id: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    permissions: list[
        Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$", max_length=80)]
    ] = Field(default_factory=list, max_length=40)
    provenance: Provenance


class SourceMapping(Strict):
    id: str = Field(pattern=ID)
    source_system: str = Field(min_length=1, max_length=120)
    source_entity: str = Field(min_length=1, max_length=120)
    source_attribute: str = Field(min_length=1, max_length=120)
    entity_id: str = Field(pattern=ID)
    attribute_id: str = Field(pattern=ID)
    transform: Literal[
        "none",
        "trim",
        "uppercase",
        "lowercase",
        "parse_decimal",
        "parse_date",
        "code_translation",
        "identifier_lookup",
    ] = "none"
    code_translation: dict[
        Annotated[str, Field(max_length=80)], Annotated[str, Field(max_length=80)]
    ] = Field(default_factory=dict, max_length=100)
    provenance: Provenance

    @model_validator(mode="after")
    def coherent(self):
        if (self.transform == "code_translation") != bool(self.code_translation):
            raise ValueError(
                f"Mapping {self.id}: a code translation needs its table, and only it has one"
            )
        return self


class DomainPack(Strict):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=ID)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: Status = "draft"
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    synthetic: bool
    domains: list[Domain] = Field(default_factory=list, max_length=40)
    concepts: list[Concept] = Field(default_factory=list, max_length=500)
    entities: list[Entity] = Field(default_factory=list, max_length=200)
    relationships: list[Relationship] = Field(default_factory=list, max_length=1000)
    events: list[Event] = Field(default_factory=list, max_length=200)
    rules: list[Rule] = Field(default_factory=list, max_length=300)
    processes: list[Process] = Field(default_factory=list, max_length=100)
    decisions: list[Decision] = Field(default_factory=list, max_length=100)
    mappings: list[SourceMapping] = Field(default_factory=list, max_length=1000)
    app_roles: list[AppRole] = Field(default_factory=list, max_length=100)

    GROUPS: ClassVar[tuple[str, ...]] = (
        "domains",
        "concepts",
        "entities",
        "relationships",
        "events",
        "rules",
        "processes",
        "decisions",
        "mappings",
        "app_roles",
    )

    def items(self):
        for group in self.GROUPS:
            for item in getattr(self, group):
                yield group, item

    @model_validator(mode="after")
    def integrity(self):
        _unique([item.id for _, item in self.items()], "pack item ID")
        domains = {item.id for item in self.domains}
        concepts = {item.id: item for item in self.concepts}
        entities = {item.id: item for item in self.entities}
        rules, events = {item.id for item in self.rules}, {item.id for item in self.events}
        all_ids = {item.id for _, item in self.items()}
        attributes = {
            (entity.id, attr.id) for entity in self.entities for attr in entity.attributes
        }
        code_lists = {item.id for item in self.concepts if item.kind == "code_list"}

        def need(ref: str | None, known, what: str, owner: str):
            if ref is not None and ref not in known:
                raise ValueError(f"{owner} refers to unknown {what} '{ref}'")

        for domain in self.domains:
            need(domain.parent_id, domains, "domain", domain.id)
            for dep in domain.depends_on:
                need(dep, domains, "domain", domain.id)
            if domain.dependencies and {item.domain_id for item in domain.dependencies} != set(
                domain.depends_on
            ):
                raise ValueError(
                    f"{domain.id}: dependencies and depends_on must name the same domains"
                )
            _unique([item.domain_id for item in domain.dependencies], f"dependency of {domain.id}")
        _acyclic(
            {item.id: [item.parent_id] if item.parent_id else [] for item in self.domains},
            "Domain hierarchy",
        )
        _acyclic({item.id: item.depends_on for item in self.domains}, "Domain dependencies")
        for concept in self.concepts:
            need(concept.domain_id, domains, "domain", concept.id)
            need(concept.broader_id, concepts, "concept", concept.id)
            for ref in concept.equivalent_ids:
                need(ref, concepts, "concept", concept.id)
            for synonym in concept.synonyms:
                need(synonym.domain_id, domains, "domain", concept.id)
            _unique([item.term.lower() for item in concept.synonyms], f"synonym of {concept.id}")
        _acyclic(
            {item.id: [item.broader_id] if item.broader_id else [] for item in self.concepts},
            "Concept hierarchy",
        )
        for entity in self.entities:
            need(entity.domain_id, domains, "domain", entity.id)
            need(entity.concept_id, concepts, "concept", entity.id)
            need(entity.extends_id, entities, "entity", entity.id)
            for attr in entity.attributes:
                need(attr.code_list_id, code_lists, "code list", f"{entity.id}.{attr.id}")
        _acyclic(
            {item.id: [item.extends_id] if item.extends_id else [] for item in self.entities},
            "Entity inheritance",
        )
        seen_edges = set()
        for rel in self.relationships:
            # Relationships connect entities or concepts; anything else (a rule, a mapping) is an incompatible endpoint.
            for end in (rel.source_id, rel.target_id):
                if end not in entities and end not in concepts:
                    raise ValueError(
                        f"Relationship {rel.id} has an endpoint '{end}' that is not an entity or concept"
                    )
            edge = (rel.source_id, rel.type, rel.target_id)
            if edge in seen_edges:
                raise ValueError(
                    f"Relationship {rel.id} duplicates {rel.source_id} {rel.type} {rel.target_id}"
                )
            seen_edges.add(edge)
        # An acyclic type may be self-referential (records form a tree), but its definitions must not loop between
        # different entities, or no record could ever terminate the chain.
        for rel_type in sorted({rel.type for rel in self.relationships if rel.acyclic}):
            graph: dict[str, list[str]] = {}
            for rel in self.relationships:
                if rel.acyclic and rel.type == rel_type and rel.source_id != rel.target_id:
                    graph.setdefault(rel.source_id, []).append(rel.target_id)
            _acyclic(graph, f"Acyclic relationship {rel_type}")
        for event in self.events:
            need(event.entity_id, entities, "entity", event.id)
        for rule in self.rules:
            for ref in rule.entity_ids:
                need(ref, entities, "entity", rule.id)
        for process in self.processes:
            need(process.domain_id, domains, "domain", process.id)
            for ref in process.entity_ids:
                need(ref, entities, "entity", process.id)
            for ref in process.rule_ids:
                need(ref, rules, "rule", process.id)
            for ref in process.event_ids:
                need(ref, events, "event", process.id)
        for decision in self.decisions:
            for ref in decision.affects:
                need(ref, all_ids, "item", decision.id)
        for role in self.app_roles:
            if not role.permissions:
                raise ValueError(f"Application role {role.id} grants nothing")
        for mapping in self.mappings:
            if (mapping.entity_id, mapping.attribute_id) not in attributes:
                raise ValueError(
                    f"Mapping {mapping.id} refers to unknown attribute {mapping.entity_id}.{mapping.attribute_id}"
                )
        return self


def _acyclic(graph: dict[str, list[str]], what: str) -> None:
    state: dict[str, int] = {}

    def visit(node: str, trail: tuple[str, ...]):
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            raise ValueError(f"{what} has a cycle: {' -> '.join(trail + (node,))}")
        state[node] = 1
        for nxt in graph.get(node, []):
            visit(nxt, trail + (node,))
        state[node] = 2

    for node in sorted(graph):
        visit(node, ())
