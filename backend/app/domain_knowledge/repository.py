"""Read queries over one pack version: explorer details, search, neighbourhood graph, paths and impact.

The same questions have parameterized Cypher equivalents in `graph.READ_QUERIES`; this in-process index answers them
from the authoritative pack so nothing depends on a live graph.
"""

from __future__ import annotations

from collections import deque

from app.domain_knowledge.models import DomainPack
from app.domain_knowledge.validation import normalize
from app.schemas.application_definition import ApplicationDefinition


class KnowledgeIndex:
    def __init__(self, pack: DomainPack):
        self.pack = pack
        self.entities = {item.id: item for item in pack.entities}
        self.concepts = {item.id: item for item in pack.concepts}
        self.items = {item.id: (group, item) for group, item in pack.items()}

    def _brief(self, item_id: str) -> dict:
        group, item = self.items[item_id]
        name = (
            getattr(item, "canonical_name", None)
            or getattr(item, "name", None)
            or getattr(item, "question", None)
            or getattr(item, "description", item_id)
        )
        prov = getattr(item, "provenance", None)
        return {
            "id": item_id,
            "group": group,
            "name": name,
            "provenance": prov.model_dump() if prov else None,
        }

    def domains(self) -> list[dict]:
        result = []
        for domain in self.pack.domains:
            result.append(
                {
                    **domain.model_dump(mode="json"),
                    "entity_count": sum(
                        1 for item in self.pack.entities if item.domain_id == domain.id
                    ),
                    "process_ids": [
                        item.id for item in self.pack.processes if item.domain_id == domain.id
                    ],
                    "children": [
                        item.id for item in self.pack.domains if item.parent_id == domain.id
                    ],
                }
            )
        return result

    def entities_in(self, domain_id: str | None) -> list[dict]:
        return [
            {
                "id": item.id,
                "canonical_name": item.canonical_name,
                "domain_id": item.domain_id,
                "description": item.description,
                "attribute_count": len(item.attributes),
                "provenance": item.provenance.model_dump(),
                "operational_label": item.operational_label,
            }
            for item in self.pack.entities
            if domain_id in (None, item.domain_id)
        ]

    def entity(self, entity_id: str) -> dict | None:
        entity = self.entities.get(entity_id)
        if entity is None:
            return None
        attribute_ids = {item.id for item in entity.attributes}
        processes = [item for item in self.pack.processes if entity_id in item.entity_ids]
        process_ids = {item.id for item in processes}
        return {
            "entity": entity.model_dump(mode="json"),
            "concept": self.concepts[entity.concept_id].model_dump(mode="json")
            if entity.concept_id
            else None,
            "outgoing": [
                rel.model_dump(mode="json")
                for rel in self.pack.relationships
                if rel.source_id == entity_id
            ],
            "incoming": [
                rel.model_dump(mode="json")
                for rel in self.pack.relationships
                if rel.target_id == entity_id
            ],
            "rules": [
                rule.model_dump(mode="json")
                for rule in self.pack.rules
                if entity_id in rule.entity_ids
            ],
            "processes": [item.model_dump(mode="json") for item in processes],
            "events": [
                item.model_dump(mode="json")
                for item in self.pack.events
                if item.entity_id == entity_id
            ],
            "mappings": [
                item.model_dump(mode="json")
                for item in self.pack.mappings
                if item.entity_id == entity_id and item.attribute_id in attribute_ids
            ],
            "decisions": [
                item.model_dump(mode="json")
                for item in self.pack.decisions
                if entity_id in item.affects or process_ids & set(item.affects)
            ],
        }

    def search(self, query: str, limit: int = 30) -> list[dict]:
        wanted = normalize(query)
        if not wanted:
            return []
        hits = []
        for concept in self.pack.concepts:
            reasons = []
            if wanted == normalize(concept.canonical_name) or wanted == concept.id:
                reasons.append(("exact name", 0))
            elif wanted in normalize(concept.canonical_name):
                reasons.append(("name", 1))
            for synonym in concept.synonyms:
                if wanted in normalize(synonym.term):
                    reasons.append(
                        (f"synonym '{synonym.term}' in {synonym.domain_id or concept.domain_id}", 1)
                    )
            if any(wanted == acronym.lower() for acronym in concept.acronyms):
                reasons.append(("acronym", 1))
            if not reasons and wanted in normalize(concept.definition):
                reasons.append(("definition", 2))
            if reasons:
                entity = next(
                    (item.id for item in self.pack.entities if item.concept_id == concept.id), None
                )
                best = min(rank for _, rank in reasons)
                hits.append(
                    {
                        "concept_id": concept.id,
                        "entity_id": entity,
                        "canonical_name": concept.canonical_name,
                        "domain_id": concept.domain_id,
                        "kind": concept.kind,
                        "matched": [text for text, _ in reasons],
                        "rank": best,
                        "provenance": concept.provenance.model_dump(),
                    }
                )
        hits.sort(key=lambda item: (item["rank"], item["canonical_name"]))
        return hits[:limit]

    def graph(self, domain_id: str | None = None, focus: str | None = None, depth: int = 1) -> dict:
        if focus is not None:
            keep, frontier = {focus}, {focus}
            for _ in range(max(0, min(depth, 3))):
                frontier = {
                    rel.target_id if rel.source_id in frontier else rel.source_id
                    for rel in self.pack.relationships
                    if rel.source_id in frontier or rel.target_id in frontier
                } - keep
                keep |= frontier
        else:
            keep = {item.id for item in self.pack.entities if domain_id in (None, item.domain_id)}
        keep &= set(self.entities)
        nodes = [
            {
                "id": item.id,
                "label": item.canonical_name,
                "domain_id": item.domain_id,
                "provenance": item.provenance.kind,
            }
            for item in self.pack.entities
            if item.id in keep
        ]
        edges = [
            {
                "id": rel.id,
                "source": rel.source_id,
                "target": rel.target_id,
                "type": rel.type,
                "cardinality": rel.cardinality,
                "provenance": rel.provenance.kind,
            }
            for rel in self.pack.relationships
            if rel.source_id in keep and rel.target_id in keep
        ]
        return {"nodes": nodes, "edges": edges}

    def path(self, source: str, target: str, max_hops: int = 6) -> list[dict] | None:
        """Shortest relationship path, ignoring direction; each hop says which way the relationship points."""
        if source not in self.entities or target not in self.entities:
            return None
        previous: dict[str, tuple[str, dict] | None] = {source: None}
        queue = deque([(source, 0)])
        while queue:
            node, hops = queue.popleft()
            if node == target:
                break
            if hops >= max_hops:
                continue
            for rel in self.pack.relationships:
                for here, there, forward in (
                    (rel.source_id, rel.target_id, True),
                    (rel.target_id, rel.source_id, False),
                ):
                    if here == node and there not in previous:
                        previous[there] = (
                            node,
                            {
                                "relationship_id": rel.id,
                                "type": rel.type,
                                "from": here,
                                "to": there,
                                "forward": forward,
                            },
                        )
                        queue.append((there, hops + 1))
        if target not in previous:
            return []
        hops_out, node = [], target
        while previous[node] is not None:
            node, hop = previous[node]
            hops_out.append(hop)
        return list(reversed(hops_out))

    def impact(
        self, item_id: str, projects: list[tuple[str, ApplicationDefinition]] = ()
    ) -> dict | None:
        """What depends on an item: other knowledge in the pack, and project items and generated screens copied from it."""
        if item_id not in self.items:
            return None
        dependents = set()
        for rel in self.pack.relationships:
            if item_id in (rel.source_id, rel.target_id):
                dependents.add(rel.id)
        for group, item in self.pack.items():
            refs = {
                getattr(item, name, None)
                for name in (
                    "concept_id",
                    "entity_id",
                    "domain_id",
                    "broader_id",
                    "extends_id",
                    "parent_id",
                    "code_list_id",
                )
            }
            refs |= (
                set(getattr(item, "entity_ids", []) or [])
                | set(getattr(item, "rule_ids", []) or [])
                | set(getattr(item, "affects", []) or [])
            )
            refs |= set(getattr(item, "depends_on", []) or []) | set(
                getattr(item, "event_ids", []) or []
            )
            if group == "relationships":
                refs |= {item.source_id, item.target_id}
            if group == "entities":
                refs |= {attr.code_list_id for attr in item.attributes}
            if item_id in refs and item.id != item_id:
                dependents.add(item.id)
        project_hits = []
        for project_id, definition in projects:
            copied = [
                entity.id
                for entity in definition.business.entities
                if entity.origin
                and entity.origin.pack_id == self.pack.id
                and entity.origin.item_id in ({item_id} | dependents)
            ]
            screens = sorted(
                {
                    screen.id
                    for screen in definition.screens
                    for node in _walk(screen.components)
                    if node.trace and node.trace.entity_id in copied
                }
                | {
                    screen.id
                    for screen in definition.screens
                    if screen.trace and screen.trace.entity_id in copied
                }
            )
            steps = sorted(
                {
                    f"{workflow.id}/{state.id}"
                    for workflow in definition.workflow_definitions
                    for state in workflow.states
                    if set(state.reads_entity_ids + state.writes_entity_ids) & set(copied)
                }
            )
            if copied:
                project_hits.append(
                    {
                        "project_id": project_id,
                        "revision": definition.revision,
                        "entities": sorted(copied),
                        "steps": steps,
                        "screens": screens,
                    }
                )
        return {
            "item": self._brief(item_id),
            "dependents": [self._brief(ref) for ref in sorted(dependents)],
            "projects": project_hits,
        }


def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(node.children or [])
