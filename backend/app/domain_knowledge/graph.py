"""Neo4j contract for domain knowledge: a namespaced schema proposal, parameterized read queries and a dry-run write plan.

Authorization boundary: this module never writes. `GraphDomainProvider` is disabled unless constructed in read-only mode
with a caller-supplied read session; even then it runs only the named read queries below. Schema changes, constraints,
indexes and imports are produced as a reviewable plan and refused at execution until an operation-specific authorization
exists, which this build does not implement.

Every label starts with `DK` and every relationship type with `DK_`, so nothing collides with the operational graph's
labels (Part, Machine, Order...) or types (FITS, SUPPLIED_BY...). Nodes are keyed by `dk_key = pack_id|version|item_id`,
so versions coexist and a re-import is idempotent.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Callable, Literal

from app.domain_knowledge.models import DomainPack

LABELS = {
    "domains": "DKDomain",
    "concepts": "DKConcept",
    "entities": "DKEntity",
    "events": "DKEvent",
    "rules": "DKRule",
    "processes": "DKProcess",
    "decisions": "DKDecision",
    "mappings": "DKSourceMapping",
}
ATTRIBUTE_LABEL, PACK_LABEL = "DKAttribute", "DKPackVersion"
REL_TYPES = (
    "DK_IN_PACK",
    "DK_IN_DOMAIN",
    "DK_REPRESENTS",
    "DK_HAS_ATTRIBUTE",
    "DK_RELATES_TO",
    "DK_GOVERNS",
    "DK_USES",
    "DK_APPLIES_RULE",
    "DK_AFFECTS",
    "DK_MAPS_TO",
    "DK_BROADER",
    "DK_SUBDOMAIN_OF",
    "DK_DEPENDS_ON",
)
ALL_LABELS = (*LABELS.values(), ATTRIBUTE_LABEL, PACK_LABEL)
OPERATIONAL_SCHEMA = Path(__file__).resolve().parents[2] / "graph" / "schema"


def operational_names() -> tuple[set[str], set[str]]:
    """Labels and relationship types the operational graph already uses (from the checked-in schema contract)."""
    with (OPERATIONAL_SCHEMA / "node_schema.csv").open(encoding="utf-8", newline="") as handle:
        labels = {row["label"] for row in csv.DictReader(handle)}
    with (OPERATIONAL_SCHEMA / "relationship_schema.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        types = {row["relationship"] for row in csv.DictReader(handle)}
    return labels, types


def collisions() -> list[str]:
    labels, types = operational_names()
    return sorted((set(ALL_LABELS) & labels) | (set(REL_TYPES) & types))


SCHEMA_PROPOSAL = [
    f"CREATE CONSTRAINT dk_{label.lower()}_key IF NOT EXISTS FOR (n:{label}) REQUIRE n.dk_key IS UNIQUE"
    for label in ALL_LABELS
] + [
    "CREATE INDEX dk_entity_pack IF NOT EXISTS FOR (n:DKEntity) ON (n.pack_id, n.version)",
    "CREATE INDEX dk_concept_name IF NOT EXISTS FOR (n:DKConcept) ON (n.canonical_name)",
]

# Parameterized read queries for the questions the explorer answers. Hop limits are literals; values are parameters.
READ_QUERIES: dict[str, str] = {
    "entities_in_domain": "MATCH (e:DKEntity {pack_id: $pack_id, version: $version})-[:DK_IN_DOMAIN]->(d:DKDomain {item_id: $domain_id}) RETURN e.item_id AS id, e.canonical_name AS name ORDER BY id",
    "attributes_of_entity": "MATCH (:DKEntity {dk_key: $entity_key})-[:DK_HAS_ATTRIBUTE]->(a:DKAttribute) RETURN a.item_id AS id, a.type AS type, a.required AS required ORDER BY id",
    "entities_for_concept": "MATCH (e:DKEntity)-[:DK_REPRESENTS]->(:DKConcept {dk_key: $concept_key}) RETURN e.item_id AS id",
    "relationships_of_entity": "MATCH (e:DKEntity {dk_key: $entity_key})-[r:DK_RELATES_TO]-(other:DKEntity) RETURN r.def_id AS id, r.type AS type, startNode(r) = e AS outgoing, other.item_id AS other ORDER BY id",
    "processes_for_entity": "MATCH (p:DKProcess)-[:DK_USES]->(:DKEntity {dk_key: $entity_key}) RETURN p.item_id AS id, p.name AS name ORDER BY id",
    "rules_for_process": "MATCH (:DKProcess {dk_key: $process_key})-[:DK_APPLIES_RULE]->(r:DKRule) RETURN r.item_id AS id, r.status AS status ORDER BY id",
    "mappings_for_attribute": "MATCH (m:DKSourceMapping)-[:DK_MAPS_TO]->(:DKAttribute {dk_key: $attribute_key}) RETURN m.source_system AS system, m.source_entity AS entity, m.source_attribute AS attribute",
    "relationship_path": "MATCH (a:DKEntity {dk_key: $source_key}), (b:DKEntity {dk_key: $target_key}) MATCH p = shortestPath((a)-[:DK_RELATES_TO*..6]-(b)) RETURN [n IN nodes(p) | n.item_id] AS nodes, [r IN relationships(p) | r.type] AS types",
}


def key(pack: DomainPack, item_id: str) -> str:
    return f"{pack.id}|{pack.version}|{item_id}"


def write_plan(pack: DomainPack) -> list[dict]:
    """The idempotent MERGE statements an authorized import would run, with their parameters. Never executed here."""
    base = {"pack_id": pack.id, "version": pack.version}
    plan = [
        {
            "cypher": f"MERGE (p:{PACK_LABEL} {{dk_key: $dk_key}}) SET p += $props",
            "params": {
                "dk_key": f"{pack.id}|{pack.version}",
                "props": {
                    **base,
                    "status": pack.status,
                    "title": pack.title,
                    "synthetic": pack.synthetic,
                },
            },
        }
    ]
    for group, label in LABELS.items():
        rows = []
        for item in getattr(pack, group):
            props = {
                k: v
                for k, v in item.model_dump(mode="json").items()
                if isinstance(v, (str, int, float, bool)) and k != "id"
            }
            prov = item.provenance
            rows.append(
                {
                    "dk_key": key(pack, item.id),
                    "props": {
                        **base,
                        **props,
                        "item_id": item.id,
                        "provenance_kind": prov.kind,
                        "provenance_reference": prov.reference,
                        "verification": prov.verification,
                    },
                }
            )
        if rows:
            plan.append(
                {
                    "cypher": f"UNWIND $rows AS row MERGE (n:{label} {{dk_key: row.dk_key}}) SET n += row.props "
                    f"WITH n MATCH (p:{PACK_LABEL} {{dk_key: $pack_key}}) MERGE (n)-[:DK_IN_PACK]->(p)",
                    "params": {"rows": rows, "pack_key": f"{pack.id}|{pack.version}"},
                }
            )
    attributes = [
        {
            "dk_key": key(pack, f"{entity.id}.{attr.id}"),
            "entity_key": key(pack, entity.id),
            "props": {
                **base,
                "item_id": f"{entity.id}.{attr.id}",
                "type": attr.type,
                "required": attr.required,
                "key": attr.key,
                "value_source": attr.value_source,
                "sensitivity": attr.sensitivity,
            },
        }
        for entity in pack.entities
        for attr in entity.attributes
    ]
    if attributes:
        plan.append(
            {
                "cypher": f"UNWIND $rows AS row MATCH (e:DKEntity {{dk_key: row.entity_key}}) MERGE (a:{ATTRIBUTE_LABEL} {{dk_key: row.dk_key}}) "
                "SET a += row.props MERGE (e)-[:DK_HAS_ATTRIBUTE]->(a)",
                "params": {"rows": attributes},
            }
        )
    relations = [
        {
            "source": key(pack, rel.source_id),
            "target": key(pack, rel.target_id),
            "props": {
                "def_id": rel.id,
                "type": rel.type,
                "cardinality": rel.cardinality,
                "required": rel.required,
                "provenance_kind": rel.provenance.kind,
            },
        }
        for rel in pack.relationships
        if rel.source_id in {e.id for e in pack.entities}
        and rel.target_id in {e.id for e in pack.entities}
    ]
    if relations:
        plan.append(
            {
                "cypher": "UNWIND $rows AS row MATCH (a:DKEntity {dk_key: row.source}), (b:DKEntity {dk_key: row.target}) "
                "MERGE (a)-[r:DK_RELATES_TO {def_id: row.props.def_id}]->(b) SET r += row.props",
                "params": {"rows": relations},
            }
        )
    links = [
        ("DK_IN_DOMAIN", "entities", "DKEntity", lambda e: [e.domain_id], "DKDomain"),
        (
            "DK_REPRESENTS",
            "entities",
            "DKEntity",
            lambda e: [e.concept_id] if e.concept_id else [],
            "DKConcept",
        ),
        ("DK_USES", "processes", "DKProcess", lambda p: p.entity_ids, "DKEntity"),
        ("DK_APPLIES_RULE", "processes", "DKProcess", lambda p: p.rule_ids, "DKRule"),
        ("DK_GOVERNS", "rules", "DKRule", lambda r: r.entity_ids, "DKEntity"),
        (
            "DK_SUBDOMAIN_OF",
            "domains",
            "DKDomain",
            lambda d: [d.parent_id] if d.parent_id else [],
            "DKDomain",
        ),
        ("DK_DEPENDS_ON", "domains", "DKDomain", lambda d: d.depends_on, "DKDomain"),
        (
            "DK_BROADER",
            "concepts",
            "DKConcept",
            lambda c: [c.broader_id] if c.broader_id else [],
            "DKConcept",
        ),
    ]
    for rel_type, group, source_label, targets, target_label in links:
        rows = [
            {"source": key(pack, item.id), "target": key(pack, ref)}
            for item in getattr(pack, group)
            for ref in targets(item)
        ]
        if rows:
            plan.append(
                {
                    "cypher": f"UNWIND $rows AS row MATCH (a:{source_label} {{dk_key: row.source}}), (b:{target_label} {{dk_key: row.target}}) MERGE (a)-[:{rel_type}]->(b)",
                    "params": {"rows": rows},
                }
            )
    mappings = [
        {"source": key(pack, m.id), "target": key(pack, f"{m.entity_id}.{m.attribute_id}")}
        for m in pack.mappings
    ]
    if mappings:
        plan.append(
            {
                "cypher": f"UNWIND $rows AS row MATCH (a:DKSourceMapping {{dk_key: row.source}}), (b:{ATTRIBUTE_LABEL} {{dk_key: row.target}}) MERGE (a)-[:DK_MAPS_TO]->(b)",
                "params": {"rows": mappings},
            }
        )
    return plan


def isolation() -> dict:
    """Whether the domain graph can be isolated from the live operational graph. Names only: no value is read or returned.

    The existing NEO4J_* settings connect to the live operational graph and are never used for domain knowledge. A dedicated
    instance (separate credentials, proposed variable DOMAIN_GRAPH_URI) is a prerequisite for any domain-graph write; separate
    labels inside the operational graph are not isolation."""
    dedicated = bool(os.environ.get("DOMAIN_GRAPH_URI"))
    return {
        "operational_graph_configured": bool(os.environ.get("NEO4J_URI")),
        "dedicated_domain_graph_configured": dedicated,
        "writes_allowed": False,
        "blocker": None
        if dedicated
        else "No separate development or domain graph instance is configured. Create one with its own credentials before any domain-graph write; "
        "nothing is written to the operational graph.",
    }


class WriteNotAuthorized(PermissionError):
    pass


class GraphDisabled(RuntimeError):
    pass


ReadRunner = Callable[[str, dict], list[dict]]


class GraphDomainProvider:
    """Read-only access to an already-populated DK namespace. Disabled by default; no connection is made here."""

    def __init__(
        self, mode: Literal["disabled", "read_only"] = "disabled", read: ReadRunner | None = None
    ):
        if mode == "read_only" and read is None:
            raise GraphDisabled("Read-only mode needs a read session supplied by the caller")
        self.mode, self._read = mode, read

    def query(self, name: str, params: dict) -> list[dict]:
        if self.mode != "read_only" or self._read is None:
            raise GraphDisabled("Graph-backed domain knowledge is disabled")
        if name not in READ_QUERIES:
            raise KeyError(name)
        return self._read(READ_QUERIES[name], dict(params))

    def apply_schema(self) -> None:
        raise WriteNotAuthorized(
            "Creating constraints or indexes needs explicit, operation-specific authorization"
        )

    def apply_write_plan(self, plan: list[dict]) -> None:
        raise WriteNotAuthorized(
            "Writing domain knowledge to Neo4j needs explicit, operation-specific authorization"
        )

    def status(self, pack: DomainPack | None = None) -> dict:
        plan = write_plan(pack) if pack is not None else []
        return {
            "mode": self.mode,
            "writes_enabled": False,
            "isolation": isolation(),
            "namespace": {"labels": list(ALL_LABELS), "relationship_types": list(REL_TYPES)},
            "collisions_with_operational_graph": collisions(),
            "schema_proposal": SCHEMA_PROPOSAL,
            "read_queries": sorted(READ_QUERIES),
            "write_plan": {
                "pack_id": pack.id if pack else None,
                "version": pack.version if pack else None,
                "statements": len(plan),
                "rows": sum(len(step["params"].get("rows", [1])) for step in plan),
                "executed": False,
            },
            "note": "The knowledge graph is not populated by this application. The plan above is a dry run awaiting authorization.",
        }


def get_graph_provider() -> GraphDomainProvider:
    # No configuration enables it: a read session must be wired in code after approval.
    return GraphDomainProvider("disabled")
