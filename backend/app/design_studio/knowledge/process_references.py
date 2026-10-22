"""Evidence-backed vendor processes, separate from executable customer policy."""

from collections import Counter
from datetime import date
from pathlib import Path
from typing import Literal
import json

from pydantic import Field, model_validator

from app.schemas.application_definition import Strict

CATEGORIES = ("entity", "relationship", "activity", "rule", "status", "exception")
CATALOG_PATH = Path(__file__).with_name("process_references.json")


class ReferenceSource(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    title: str = Field(min_length=1, max_length=250)
    url: str = Field(pattern=r"^https://[^\s]+$", max_length=1000)
    publisher: str = Field(min_length=1, max_length=120)
    product_version: str = Field(min_length=1, max_length=120)
    checked_on: date


class ReferenceClaim(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: Literal["entity", "relationship", "activity", "rule", "status", "exception"]
    text: str = Field(min_length=1, max_length=1200)
    source_ids: list[str] = Field(min_length=1, max_length=10)
    locator: str = Field(min_length=1, max_length=300)
    subject: str | None = None
    target: str | None = None


class ProcessReference(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    name: str = Field(min_length=1, max_length=200)
    blueprint_id: str
    blueprint_version: str
    domain_id: str | None
    system: str = Field(min_length=1, max_length=150)
    applicability: Literal["direct", "analogous"]
    applicability_note: str = Field(min_length=1, max_length=1000)
    regions: list[Literal["shared", "EU", "India"]] = Field(default_factory=lambda: ["shared"])
    review_state: Literal["draft", "reviewed", "deprecated"] = "draft"
    reviewed_by: str | None = None
    reviewed_on: date | None = None
    sources: list[ReferenceSource] = Field(min_length=1, max_length=30)
    claims: list[ReferenceClaim] = Field(min_length=1, max_length=200)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_integrity(self):
        source_ids = {source.id for source in self.sources}
        if len(source_ids) != len(self.sources) or len({claim.id for claim in self.claims}) != len(
            self.claims
        ):
            raise ValueError("Reference source and claim IDs must be unique")
        entities = {claim.id for claim in self.claims if claim.kind == "entity"}
        for claim in self.claims:
            if set(claim.source_ids) - source_ids:
                raise ValueError("Every claim must cite a source in this reference")
            if claim.kind == "relationship" and (
                claim.subject not in entities or claim.target not in entities
            ):
                raise ValueError("Relationship endpoints must name entity claims in this reference")
        if self.review_state == "reviewed" and (not self.reviewed_by or not self.reviewed_on):
            raise ValueError("Reviewed references require an explicit reviewer and date")
        return self


def validate_references(documents):
    references = [ProcessReference.model_validate(document) for document in documents]
    keys = {(item.id, item.version) for item in references}
    if len(keys) != len(references):
        raise ValueError("Duplicate process reference version")
    return references


def load_references():
    return [
        item.model_dump(mode="json")
        for item in validate_references(json.loads(CATALOG_PATH.read_text(encoding="utf-8")))
    ]


def reference_context(provider, definition):
    reader = getattr(provider, "process_references", None)
    documents = reader() if reader else []
    newest = {}
    for item in validate_references(documents):
        if item.review_state == "deprecated":
            continue
        previous = newest.get(item.id)
        if previous is None or tuple(map(int, item.version.split("."))) > tuple(
            map(int, previous.version.split("."))
        ):
            newest[item.id] = item
    references = list(newest.values())
    blueprint_ids = {
        pack.id for pack in provider.packs() if pack.usage == "blueprint" and pack.company is None
    }
    covered = {item.blueprint_id for item in references}
    adopted = {item.pack_id for item in definition.business.knowledge}
    domain = definition.business.brief.domain_id
    matched = [
        item
        for item in references
        if item.blueprint_id in adopted or (domain is not None and item.domain_id == domain)
    ]
    return {
        "source": getattr(provider, "source", "local"),
        "total": len(references),
        "blueprints_covered": len(covered & blueprint_ids),
        "blueprints_total": len(blueprint_ids),
        "uncovered_blueprints": sorted(blueprint_ids - covered),
        "reviewed": sum(item.review_state == "reviewed" for item in references),
        "matched": [describe(item) for item in sorted(matched, key=lambda item: item.id)],
        "note": "Vendor documentation informs draft designs. It does not confirm customer policy, country compliance, live pricing or a working integration.",
    }


def describe(reference):
    document = reference.model_dump(mode="json")
    counts = Counter(claim.kind for claim in reference.claims)
    document["coverage"] = {kind: counts[kind] for kind in CATEGORIES}
    document["research_gaps"] = [kind for kind in CATEGORIES if not counts[kind]]
    document["executable"] = False
    return document
