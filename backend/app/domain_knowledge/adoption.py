"""Bridge from shared domain knowledge to a Design Studio project.

`suggest` proposes; nothing is copied. `adopt` copies only the entities the user selected, with relationships between
selected entities only, and stamps each with its origin so the project keeps a link to the shared definition. Missing
dependencies are reported, never added silently. Edits made in the project are project-specific overrides: they never
change the shared pack, and `overrides` lists them.
"""

from __future__ import annotations

import re

from app.domain_knowledge.models import DomainPack, Entity
from app.domain_knowledge.repository import KnowledgeIndex
from app.domain_knowledge.validation import normalize
from app.schemas.application_definition import ApplicationDefinition

PREFIX = "dk_"
TYPE_MAP = {
    "string": "string",
    "code": "string",
    "integer": "integer",
    "decimal": "decimal",
    "boolean": "boolean",
    "date": "date",
    "datetime": "datetime",
}


class AdoptionConflict(ValueError):
    def __init__(self, ids: list[str]):
        super().__init__(
            "Selected entities collide with project items that did not come from this pack"
        )
        self.ids = ids


def _words(text: str) -> str:
    return f" {normalize(text)} "


def suggest(text: str, index: KnowledgeIndex) -> dict:
    pack, haystack = index.pack, _words(text)
    domains = []
    for domain in pack.domains:
        matched = sorted({keyword for keyword in domain.keywords if _words(keyword) in haystack})
        if matched:
            domains.append(
                {
                    "domain_id": domain.id,
                    "name": domain.name,
                    "matched_keywords": matched,
                    "score": len(matched),
                }
            )
    domains.sort(key=lambda item: (-item["score"], item["domain_id"]))
    concepts, ambiguous = [], []
    term_owner: dict[str, set[str]] = {}
    for concept in pack.concepts:
        terms = [(concept.canonical_name, "name")] + [
            (syn.term, f"synonym in {syn.domain_id or concept.domain_id}")
            for syn in concept.synonyms
        ]
        hits = [(term, how) for term, how in terms if _words(term) in haystack]
        for term, _ in hits:
            term_owner.setdefault(normalize(term), set()).add(concept.id)
        if hits:
            entity = next((item for item in pack.entities if item.concept_id == concept.id), None)
            concepts.append(
                {
                    "concept_id": concept.id,
                    "entity_id": entity.id if entity else None,
                    "canonical_name": concept.canonical_name,
                    "domain_id": concept.domain_id,
                    "matched": [f"'{term}' ({how})" for term, how in hits],
                    "provenance": concept.provenance.model_dump(),
                }
            )
    for term, owners in sorted(term_owner.items()):
        if len(owners) > 1:
            ambiguous.append(
                {
                    "term": term,
                    "concept_ids": sorted(owners),
                    "message": f"'{term}' could mean {', '.join(sorted(owners))}; choose one.",
                }
            )
    selected = {item["entity_id"] for item in concepts if item["entity_id"]}
    domain_ids = {item["domain_id"] for item in domains}
    relationships = [
        rel.model_dump(mode="json")
        for rel in pack.relationships
        if rel.source_id in selected and rel.target_id in selected
    ]
    missing = sorted(
        {
            rel.target_id
            for rel in pack.relationships
            if rel.source_id in selected and rel.required and rel.target_id not in selected
        }
    )
    processes = [
        process
        for process in pack.processes
        if process.domain_id in domain_ids or selected & set(process.entity_ids)
    ]
    process_ids = {process.id for process in processes}
    return {
        "pack": {"id": pack.id, "version": pack.version, "synthetic": pack.synthetic},
        "domains": domains,
        "concepts": concepts,
        "ambiguous_terms": ambiguous,
        "relationships": relationships,
        "missing_dependencies": [
            {"entity_id": ref, "reason": "A selected entity requires it"} for ref in missing
        ],
        "processes": [
            {
                "id": p.id,
                "name": p.name,
                "design_template": p.design_template,
                "entity_ids": p.entity_ids,
            }
            for p in processes
        ],
        "rules": [
            rule.model_dump(mode="json")
            for rule in pack.rules
            if any(rule.id in p.rule_ids for p in processes)
        ],
        "decisions": [
            d.model_dump(mode="json")
            for d in pack.decisions
            if d.status == "open" and process_ids & set(d.affects)
        ],
    }


def _design_id(entity_id: str) -> str:
    return f"{PREFIX}{entity_id}"


def convert(entity: Entity, pack: DomainPack, selected: set[str]) -> dict:
    code_lists = {item.id: item.code_values for item in pack.concepts if item.kind == "code_list"}
    attributes = []
    for attr in entity.attributes:
        item = {
            "id": attr.id.replace(".", "_"),
            "name": attr.name[:120],
            "type": TYPE_MAP[attr.type],
            "required": attr.required,
            "key": attr.key,
            "description": attr.description,
            "value_source": attr.value_source,
            "writable": attr.value_source == "user_entered" and attr.mutability == "user_updated",
            "sensitivity": attr.sensitivity,
        }
        if attr.code_list_id:
            item["enum"] = code_lists[attr.code_list_id][:50]
        attributes.append(item)
    relationships = []
    for rel in pack.relationships:
        if rel.source_id == entity.id and rel.target_id in selected:
            relationships.append(
                {
                    "id": re.sub(r"[^a-z0-9_-]", "_", rel.id.lower())[:80],
                    "name": rel.type.replace("_", " ").lower()[:120],
                    "target": _design_id(rel.target_id),
                    "cardinality": rel.cardinality,
                    "required": rel.required,
                }
            )
    return {
        "id": _design_id(entity.id),
        "name": entity.canonical_name,
        "description": entity.description[:1000],
        "source_system": (entity.operational_label or "")[:200],
        "attributes": attributes,
        "relationships": relationships,
        "origin": {"pack_id": pack.id, "pack_version": pack.version, "item_id": entity.id},
    }


def required_closure(pack: DomainPack, entity_ids: list[str]) -> list[str]:
    """The selection plus every entity its required relationships reach, transitively. Deterministic."""
    selected, frontier = set(entity_ids), set(entity_ids)
    while frontier:
        nxt = {
            rel.target_id
            for rel in pack.relationships
            if rel.source_id in frontier and rel.required and rel.target_id not in selected
        }
        selected |= nxt
        frontier = nxt
    return sorted(selected)


def adopt(
    definition: ApplicationDefinition,
    pack: DomainPack,
    entity_ids: list[str],
    include_required: bool = False,
) -> tuple[ApplicationDefinition, dict]:
    known = {item.id: item for item in pack.entities}
    unknown = sorted(set(entity_ids) - set(known))
    if unknown:
        raise KeyError(", ".join(unknown))
    requested = sorted(set(entity_ids))
    if include_required:
        entity_ids = required_closure(pack, entity_ids)
    raw = definition.model_dump(mode="json")
    business = raw["business"]
    existing = {entity["id"]: entity for entity in business["entities"]}
    others = definition.business.item_ids() - set(existing)
    selected = set(entity_ids)
    conflicts, kept, added = [], [], []
    for entity_id in sorted(selected):
        design_id = _design_id(entity_id)
        current = existing.get(design_id)
        if design_id in others or (
            current is not None and (current.get("origin") or {}).get("pack_id") != pack.id
        ):
            conflicts.append(design_id)
        elif current is not None:
            kept.append(
                design_id
            )  # already adopted: the project's version, including its overrides, is kept
        else:
            added.append(design_id)
    if conflicts:
        raise AdoptionConflict(conflicts)
    for entity_id in sorted(selected):
        if _design_id(entity_id) in added:
            business["entities"].append(
                convert(
                    known[entity_id],
                    pack,
                    selected
                    | {
                        item["origin"]["item_id"]
                        for item in business["entities"]
                        if (item.get("origin") or {}).get("pack_id") == pack.id
                    },
                )
            )
    missing = sorted(
        {
            rel.target_id
            for rel in pack.relationships
            if rel.source_id in selected
            and rel.required
            and rel.target_id not in selected
            and _design_id(rel.target_id) not in existing
        }
    )
    excluded = sorted(
        {
            rel.id
            for rel in pack.relationships
            if rel.source_id in selected and rel.target_id not in selected
        }
    )
    report = {
        "added": added,
        "kept_existing": kept,
        "missing_dependencies": missing,
        "relationships_excluded": excluded,
        "added_as_required_dependency": sorted(
            _design_id(item) for item in set(entity_ids) - set(requested)
        ),
        "pack": {"id": pack.id, "version": pack.version},
    }
    return ApplicationDefinition.model_validate(raw), report


def overrides(definition: ApplicationDefinition, pack: DomainPack) -> list[dict]:
    """Project items adopted from the pack that now differ from it: deliberate project-specific overrides, or drift."""
    known = {item.id: item for item in pack.entities}
    adopted = {
        entity.origin.item_id
        for entity in definition.business.entities
        if entity.origin and entity.origin.pack_id == pack.id
    }
    result = []
    for entity in definition.business.entities:
        if not entity.origin or entity.origin.pack_id != pack.id:
            continue
        source = known.get(entity.origin.item_id)
        if source is None:
            result.append({"entity_id": entity.id, "state": "removed_from_pack", "fields": []})
            continue
        fresh = convert(source, pack, adopted)
        current = entity.model_dump(mode="json")
        fresh["origin"]["pack_version"] = current["origin"]["pack_version"]
        normalized = type(entity).model_validate(fresh).model_dump(mode="json")
        fields = sorted(key for key in normalized if normalized[key] != current.get(key))
        state = "overridden" if fields else "same"
        if entity.origin.pack_version != pack.version:
            state = "pack_newer" if not fields else "overridden_and_pack_newer"
        if fields or state != "same":
            result.append(
                {
                    "entity_id": entity.id,
                    "state": state,
                    "fields": fields,
                    "adopted_version": entity.origin.pack_version,
                    "current_version": pack.version,
                }
            )
    return result
