"""Reference-pack contract. A pack is versioned, declares its layer, and is validated with the same models as a project."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, ValidationInfo, model_validator

from app.domain_knowledge.models import Provenance

from app.schemas.application_definition import (
    ID_PATTERN,
    ApplicationDefinition,
    BusinessDefinition,
    Strict,
    WorkflowDefinition,
)


BUSINESS_GROUPS = (
    "requirements",
    "roles",
    "entities",
    "rules",
    "exceptions",
    "decisions",
    "integrations",
    "terms",
)


class KnowledgeDomain(Strict):
    """A design-knowledge domain. Deliberately not the operational graph's `Industry` (a customer's industry)."""

    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    subdomains: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=30
    )
    # Curated matching vocabulary for deterministic domain identification; no model is involved. Synonyms belong here too.
    keywords: list[Annotated[str, Field(min_length=2, max_length=60)]] = Field(
        default_factory=list, max_length=80
    )
    parent_id: str | None = Field(default=None, pattern=ID_PATTERN)
    description: str = Field(default="", max_length=500)


class BusinessCapabilityRef(Strict):
    """What the business does. Not the operational graph's `Capability` (a dealer's service capability)."""

    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=200)


class PackEvidence(Strict):
    """A claim that a pack item reflects implemented behaviour; regression tests check each one against the code."""

    item_id: str = Field(pattern=ID_PATTERN)
    kind: Literal[
        "order_action",
        "order_status",
        "checkout_error",
        "warranty_outcome",
        "role_permissions",
        "tracking_rule",
        "stock_states",
        "part_statuses",
        "quantity_limit",
    ]
    value: str = Field(min_length=1, max_length=200)


class Capability(Strict):
    """A reusable business capability, modelled once and used by many domains. `level` says what the generator really provides."""

    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    depends_on: list[Annotated[str, Field(pattern=ID_PATTERN)]] = Field(
        default_factory=list, max_length=10
    )
    provided_by: str = Field(
        min_length=1, max_length=80
    )  # a pack id, or "runtime" when every generated application has it
    level: Literal["implemented", "partial", "unsupported"]
    note: str = Field(min_length=1, max_length=600)


class GlossaryEntry(Strict):
    """Business vocabulary of a pack: the canonical term, what it means and the other words people use for it. Search reads this."""

    term: str = Field(min_length=1, max_length=120)
    definition: str = Field(min_length=1, max_length=1000)
    synonyms: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=20
    )
    refers_to: str | None = Field(
        default=None, pattern=ID_PATTERN
    )  # the entity, rule or role it describes


class CompanyRef(Strict):
    """The operating context of a company-specific layer."""

    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    industry: str = Field(default="", max_length=200)
    operating_context: str = Field(default="", max_length=1000)
    business_units: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=30
    )
    systems_of_record: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=30
    )


class ItemOverride(Strict):
    """An explicit, reasoned change a company makes to an item it reuses from shared knowledge. Never silent: it names the item, the
    fields and why. Lists of attributes merge by attribute ID; everything else is replaced field by field."""

    item_id: str = Field(pattern=ID_PATTERN)
    reason: str = Field(min_length=1, max_length=500)
    patch: dict[str, Any] = Field(default_factory=dict)
    add_attributes: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    add_permissions: list[Annotated[str, Field(max_length=80)]] = Field(
        default_factory=list, max_length=30
    )


class ProcessContext(Strict):
    """Searchable process-family/variant metadata with its own source, never guessed vendor policy."""

    workflow_id: str = Field(pattern=ID_PATTERN)
    family_id: str = Field(pattern=ID_PATTERN)
    variant: str = Field(min_length=1, max_length=120)
    region: str = Field(default="Unspecified", max_length=120)
    source_system: str | None = Field(default=None, max_length=120)
    provenance: Provenance


class ReferencePack(Strict):
    id: str = Field(pattern=ID_PATTERN)
    version: str = Field(min_length=1, max_length=40)
    # reusable: shared capabilities and core concepts. business: a domain. company: one company's extension of shared knowledge.
    layer: Literal["reusable", "business", "company"]
    usage: Literal["blueprint", "source_reference"] = Field(
        default="blueprint", exclude_if=lambda value: value == "blueprint"
    )
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    synthetic: bool
    domains: list[KnowledgeDomain] = Field(default_factory=list, max_length=30)
    domain_id: str | None = Field(default=None, pattern=ID_PATTERN)
    capability: BusinessCapabilityRef | None = None
    depends_on: list[Annotated[str, Field(pattern=ID_PATTERN)]] = Field(
        default_factory=list, max_length=12
    )
    # draft -> in_review -> approved -> deprecated. Nothing in this repository approves a pack: new synthetic packs are in_review.
    status: Literal["draft", "in_review", "approved", "deprecated"] = "approved"
    provenance: Provenance = Field(
        default_factory=lambda: Provenance(
            kind="synthetic", reference="Shipped reference pack", verification="unverified"
        )
    )
    # full: what the pack depends on is copied completely (the original behaviour). data_model: only the entities and terms of its
    # dependencies are copied, plus the roles and rules this pack's own items refer to; their processes, roles and open decisions
    # belong to those domains and arrive only when the domain is adopted itself, or listed in `includes`.
    dependency_mode: Literal["full", "data_model"] = "full"
    includes: list[Annotated[str, Field(pattern=ID_PATTERN)]] = Field(
        default_factory=list, max_length=20
    )
    uses_capabilities: list[Annotated[str, Field(pattern=ID_PATTERN)]] = Field(
        default_factory=list, max_length=20
    )
    glossary: list[GlossaryEntry] = Field(default_factory=list, max_length=100)
    company: CompanyRef | None = None
    overrides: list[ItemOverride] = Field(default_factory=list, max_length=100)
    business: BusinessDefinition = Field(default_factory=BusinessDefinition)
    workflows: list[WorkflowDefinition] = Field(default_factory=list, max_length=10)
    process_contexts: list[ProcessContext] = Field(
        default_factory=list, max_length=10, exclude_if=lambda value: not value
    )
    evidence: list[PackEvidence] = Field(default_factory=list, max_length=500)

    @property
    def verified(self) -> bool:
        """Only approved, non-synthetic knowledge checked against its source is ever served to a project."""
        return self.status == "approved" and not self.synthetic and self.provenance.verification == "verified"

    @model_validator(mode="after")
    def references_resolve(self, info: ValidationInfo):
        workflow_ids = {w.id for w in self.workflows}
        if any(c.workflow_id not in workflow_ids for c in self.process_contexts):
            raise ValueError("Process context refers to an unknown workflow")
        if len({c.workflow_id for c in self.process_contexts}) != len(self.process_contexts):
            raise ValueError("A workflow has at most one process context")
        # A pack must be applicable to an empty project together with what it depends on. Dependencies arrive through the validation
        # context ({"dependencies": {pack_id: ReferencePack}}); without it a pack is checked on its own, as before.
        if self.layer == "company" and self.company is None:
            raise ValueError("A company layer names its company")
        if any(item not in self.depends_on for item in self.includes):
            raise ValueError("A pack can only include packs it depends on")
        known_packs = ((info.context or {}).get("dependencies", {})) if info is not None else {}
        merged: dict[str, list] = {group: [] for group in BUSINESS_GROUPS}
        workflows: list = []
        seen: set[str] = set()

        def collect(pack_id: str):
            if pack_id in seen or pack_id not in known_packs:
                return
            seen.add(pack_id)
            for dep in known_packs[pack_id].depends_on:
                collect(dep)
            dependency = known_packs[pack_id]
            for group in BUSINESS_GROUPS:
                merged[group].extend(
                    item.model_dump(mode="json") for item in getattr(dependency.business, group)
                )
            workflows.extend(item.model_dump(mode="json") for item in dependency.workflows)

        for dep in self.depends_on:
            collect(dep)
        own = self.business.model_dump(mode="json")
        business = {**own, **{group: merged[group] + own[group] for group in BUSINESS_GROUPS}}
        all_workflows = workflows + [item.model_dump(mode="json") for item in self.workflows]
        if self.overrides:
            from app.design_studio.knowledge.overrides import apply_overrides

            business = apply_overrides(business, self.overrides)
        ApplicationDefinition.model_validate(
            {
                "version": 2,
                "id": "pack_check",
                "metadata": {"name": "pack", "description": "", "purpose": "", "domain": "other"},
                "screens": [
                    {
                        "id": "screen_pack_check",
                        "title": "Check",
                        "components": [
                            {
                                "kind": "text",
                                "id": "text_pack_check",
                                "props": {"content": ""},
                                "placement": {"span": 12},
                            }
                        ],
                    }
                ],
                "theme": {
                    "primary": "#00756A",
                    "background": "#FFFFFF",
                    "surface": "#F7F5F0",
                    "text": "#14181A",
                    "font": "inter",
                },
                "business": business,
                "workflow_definitions": all_workflows,
                "workflows": [item["id"] for item in all_workflows],
            }
        )
        known = {item["id"] for group in BUSINESS_GROUPS for item in business[group]} | {
            state["id"] for workflow in all_workflows for state in workflow["states"]
        }
        if any(item.item_id not in known for item in self.evidence):
            raise ValueError("Evidence refers to an unknown pack item")
        if any(
            entry.refers_to is not None and entry.refers_to not in known for entry in self.glossary
        ):
            raise ValueError("Glossary refers to an unknown pack item")
        return self
