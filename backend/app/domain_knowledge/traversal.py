"""Bounded, explainable multi-hop traversal over typed knowledge graphs.

`KnowledgeGraph` holds typed nodes and labelled, directed edges, each with a sentence that explains it. Queries are
breadth-first with explicit depth and result limits. A path never revisits a node, so cycles cannot loop, and only
the shortest path to each node is kept. Two builders exist: one for a domain pack, and one for a Design Studio project
including its generated artifacts (`project_graph`).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from app.domain_knowledge.models import DomainPack

MAX_DEPTH = 6
MAX_RESULTS = 200


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    type: str
    explanation: str


@dataclass
class KnowledgeGraph:
    nodes: dict[str, dict] = field(default_factory=dict)
    out: dict[str, list[Edge]] = field(default_factory=dict)
    into: dict[str, list[Edge]] = field(default_factory=dict)

    def node(self, node_id: str, kind: str, label: str, **extra) -> None:
        self.nodes.setdefault(node_id, {"id": node_id, "kind": kind, "label": label, **extra})

    def edge(self, source: str, target: str, type_: str, explanation: str) -> None:
        if source not in self.nodes or target not in self.nodes:
            return
        item = Edge(source, target, type_, explanation)
        if item not in self.out.setdefault(source, []):
            self.out[source].append(item)
            self.into.setdefault(target, []).append(item)

    def _steps(self, node_id: str, direction: str, types: frozenset[str] | None):
        if direction in ("out", "both"):
            for item in self.out.get(node_id, []):
                if types is None or item.type in types:
                    yield item, item.target, True
        if direction in ("in", "both"):
            for item in self.into.get(node_id, []):
                if types is None or item.type in types:
                    yield item, item.source, False

    def reach(
        self,
        start: str,
        *,
        direction: str = "out",
        max_depth: int = 3,
        max_results: int = 50,
        kinds: set[str] | None = None,
        edge_types: set[str] | None = None,
        target: str | None = None,
    ) -> dict:
        """Shortest explained path to each reachable node (optionally only `kinds`, or only `target`)."""
        if start not in self.nodes:
            raise KeyError(start)
        if not 1 <= max_depth <= MAX_DEPTH or not 1 <= max_results <= MAX_RESULTS:
            raise ValueError(f"Depth must be 1–{MAX_DEPTH} and results 1–{MAX_RESULTS}")
        types = frozenset(edge_types) if edge_types else None
        previous: dict[str, tuple[str, Edge, bool] | None] = {start: None}
        queue, results, truncated, expanded = deque([(start, 0)]), [], False, 0
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            expanded += 1
            for item, nxt, forward in sorted(
                self._steps(current, direction, types), key=lambda step: (step[1], step[0].type)
            ):
                if nxt in previous:
                    continue
                previous[nxt] = (current, item, forward)
                queue.append((nxt, depth + 1))
                if (
                    target is None and (kinds is None or self.nodes[nxt]["kind"] in kinds)
                ) or nxt == target:
                    if len(results) >= max_results:
                        truncated = True
                        queue.clear()
                        break
                    results.append(self._path(nxt, previous))
                    if nxt == target:
                        queue.clear()
                        break
        return {
            "start": self.nodes[start],
            "direction": direction,
            "max_depth": max_depth,
            "max_results": max_results,
            "results": results,
            "truncated": truncated,
            "nodes_expanded": expanded,
        }

    def _path(self, end: str, previous: dict) -> dict:
        hops, node = [], end
        while previous[node] is not None:
            before, item, forward = previous[node]
            hops.append(
                {
                    "from": before,
                    "to": node,
                    "type": item.type,
                    "forward": forward,
                    "explanation": item.explanation,
                }
            )
            node = before
        hops.reverse()
        return {
            "node": self.nodes[end],
            "depth": len(hops),
            "hops": hops,
            "explanation": " → ".join(hop["explanation"] for hop in hops),
        }


def pack_graph(pack: DomainPack) -> KnowledgeGraph:
    graph = KnowledgeGraph()
    for domain in pack.domains:
        graph.node(domain.id, "domain", domain.name)
    for concept in pack.concepts:
        graph.node(concept.id, "concept", concept.canonical_name)
    for entity in pack.entities:
        graph.node(entity.id, "entity", entity.canonical_name, domain_id=entity.domain_id)
        for attr in entity.attributes:
            graph.node(
                f"{entity.id}.{attr.id}",
                "attribute",
                f"{entity.canonical_name}.{attr.id}",
                type=attr.type,
            )
    for group, kind in (
        ("events", "event"),
        ("rules", "rule"),
        ("processes", "process"),
        ("decisions", "decision"),
        ("mappings", "mapping"),
    ):
        for item in getattr(pack, group):
            graph.node(
                item.id,
                kind,
                getattr(item, "name", None)
                or getattr(item, "question", None)
                or getattr(item, "description", item.id),
            )
    roles = sorted({role for process in pack.processes for role in process.roles})
    for role in roles:
        graph.node(f"role:{role}", "role", role)

    for domain in pack.domains:
        if domain.parent_id:
            graph.edge(
                domain.id,
                domain.parent_id,
                "SUBDOMAIN_OF",
                f"{domain.name} is part of {domain.parent_id}",
            )
        for dep in domain.depends_on:
            graph.edge(domain.id, dep, "DEPENDS_ON", f"{domain.name} depends on {dep}")
    for entity in pack.entities:
        graph.edge(
            entity.domain_id,
            entity.id,
            "CONTAINS",
            f"domain {entity.domain_id} contains {entity.canonical_name}",
        )
        if entity.concept_id:
            graph.edge(
                entity.id,
                entity.concept_id,
                "REPRESENTS",
                f"{entity.canonical_name} represents concept {entity.concept_id}",
            )
        for attr in entity.attributes:
            graph.edge(
                entity.id,
                f"{entity.id}.{attr.id}",
                "HAS_ATTRIBUTE",
                f"{entity.canonical_name} has {attr.id} ({attr.type})",
            )
    for rel in pack.relationships:
        graph.edge(
            rel.source_id,
            rel.target_id,
            rel.type,
            f"{rel.source_id} {rel.type} {rel.target_id} ({rel.cardinality.replace('_', ' ')})",
        )
    for event in pack.events:
        graph.edge(
            event.id,
            event.entity_id,
            "CHANGES",
            f"{event.name} changes {event.entity_id} {event.from_state or '∅'}→{event.to_state}",
        )
    for rule in pack.rules:
        for ref in rule.entity_ids:
            graph.edge(rule.id, ref, "GOVERNS", f"rule {rule.id} governs {ref}")
    for process in pack.processes:
        graph.edge(
            process.domain_id,
            process.id,
            "HAS_PROCESS",
            f"domain {process.domain_id} runs {process.name}",
        )
        for ref in process.entity_ids:
            graph.edge(process.id, ref, "USES", f"{process.name} reads or writes {ref}")
        for ref in process.rule_ids:
            graph.edge(process.id, ref, "APPLIES", f"{process.name} applies rule {ref}")
        for ref in process.event_ids:
            graph.edge(process.id, ref, "EMITS", f"{process.name} emits {ref}")
        for role in process.roles:
            graph.edge(
                f"role:{role}",
                process.id,
                "PERFORMS",
                f"role {role} performs steps of {process.name}",
            )
    for decision in pack.decisions:
        for ref in decision.affects:
            graph.edge(decision.id, ref, "AFFECTS", f"open decision {decision.id} affects {ref}")
    for mapping in pack.mappings:
        graph.edge(
            mapping.id,
            f"{mapping.entity_id}.{mapping.attribute_id}",
            "MAPS_TO",
            f"{mapping.source_system} {mapping.source_entity}.{mapping.source_attribute} maps to {mapping.entity_id}.{mapping.attribute_id}",
        )
    return graph
