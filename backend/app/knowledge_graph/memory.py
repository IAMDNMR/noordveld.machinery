"""An in-memory knowledge graph that applies the same operations a real graph would, and answers the explorer's questions.

This is the test double and the reference behaviour for the read queries. It enforces what the database constraints would (a unique key
per label, relationship endpoints that the schema allows) so a projection that would be rejected by a real graph fails here first.
It does not claim that the rendered Cypher runs on Neo4j: that needs a dedicated development instance (see docs).
"""

from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import json
from typing import Any

from app.knowledge_graph import schema
from app.knowledge_graph.projection import NodeOp, Projection, RelOp, normalize

MAX_HOPS = 4


class GraphError(ValueError):
    pass


class InMemoryGraph:
    def __init__(self):
        self.nodes: dict[str, tuple[str, dict[str, Any]]] = {}
        self.rels: dict[tuple, dict[str, Any]] = {}
        self._out: dict[str, list[tuple]] = defaultdict(list)
        self._in: dict[str, list[tuple]] = defaultdict(list)

    # ── writing (MERGE semantics: running the same operations twice changes nothing) ──
    def apply(self, nodes: list[NodeOp], rels: list[RelOp]) -> "InMemoryGraph":
        for node in nodes:
            if node.label not in schema.NODE_LABELS:
                raise GraphError(f"unknown label {node.label}")
            existing = self.nodes.get(node.key)
            if existing and existing[0] != node.label:
                raise GraphError(
                    f"key {node.key} is already a {existing[0]}: a unique constraint would reject {node.label}"
                )
            self.nodes[node.key] = (node.label, {**(existing[1] if existing else {}), **node.props})
        for rel in rels:
            source, target = self.nodes.get(rel.source[1]), self.nodes.get(rel.target[1])
            if source is None or target is None:
                raise GraphError(
                    f"{rel.type} refers to a missing node ({rel.source[1]} -> {rel.target[1]})"
                )
            sources, targets, _ = schema.REL_TYPES[rel.type]
            if source[0] not in sources or target[0] not in targets:
                raise GraphError(f"{rel.type} may not connect {source[0]} to {target[0]}")
            identity = (
                rel.type,
                rel.source[1],
                rel.target[1],
                rel.props.get("def_id") or rel.props.get("mode") or rel.props.get("condition_key"),
            )
            if identity not in self.rels:
                self._out[rel.source[1]].append(identity)
                self._in[rel.target[1]].append(identity)
            self.rels[identity] = {**self.rels.get(identity, {}), **rel.props}
        return self

    def load(self, projection: Projection) -> "InMemoryGraph":
        return self.apply(*projection.operations())

    def counts(self) -> dict[str, int]:
        return {"nodes": len(self.nodes), "relationships": len(self.rels)}

    # ── reading ──
    def node(self, key: str) -> dict[str, Any] | None:
        found = self.nodes.get(key)
        return {"label": found[0], **found[1]} if found else None

    def of_label(self, label: str, **where) -> list[dict[str, Any]]:
        return [
            {"label": lab, **props}
            for lab, props in self.nodes.values()
            if lab == label and all(props.get(k) == v for k, v in where.items())
        ]

    def documents(self, statuses: tuple[str, ...] = ("approved", "in_review")) -> list[dict]:
        """The pack documents the graph holds. The graph serves packs as well as describing them."""
        return [
            json.loads(props["document"])
            for label, props in self.nodes.values()
            if label == "DKPackVersion"
            and props.get("status") in statuses
            and props.get("document")
        ]

    def capability_documents(self) -> list[dict]:
        return [
            {
                "id": p["capability_id"],
                "name": p["name"],
                "description": p["description"],
                "depends_on": sorted(
                    self._neighbour_ids(
                        f"capability|{p['capability_id']}", "DK_REQUIRES_CAPABILITY", "out"
                    )
                ),
                "provided_by": p["provided_by"],
                "level": p["level"],
                "note": p["note"],
            }
            for p in self.of_label("DKCapability")
        ]

    def _neighbour_ids(self, key: str, kind: str, direction: str) -> list[str]:
        edges = self._out[key] if direction == "out" else self._in[key]
        return [
            e[2].split("|", 1)[1] if direction == "out" else e[1] for e in edges if e[0] == kind
        ]

    def search(self, text: str, scope: str | None = None, limit: int = 25) -> list[dict]:
        """Business-term search: a term, one of its synonyms, an entity or a concept name. Says which word matched, so a person can see why."""
        wanted = normalize(text)
        if not wanted:
            return []
        hits = []
        for key, (label, props) in self.nodes.items():
            if scope and props.get("scope") not in (scope, schema.SCOPE_SHARED):
                continue
            via, rank = None, None
            if label == "DKTerm":
                if props.get("term_normalized") == wanted:
                    via, rank = "term", 0
                elif wanted in (props.get("synonyms_normalized") or []):
                    via, rank = f"synonym of “{props['name']}”", 1
                elif wanted in props.get("term_normalized", ""):
                    via, rank = "part of the term", 3
            elif label in (
                "DKEntity",
                "DKRole",
                "DKRule",
                "DKProcess",
                "DKRequirement",
                "DKCapability",
                "DKDomain",
            ):
                name = normalize(props.get("name", ""))
                if name == wanted:
                    via, rank = "name", 1
                elif wanted in name:
                    via, rank = "part of the name", 4
            if via is not None:
                hits.append(
                    {
                        "key": key,
                        "label": label,
                        "name": props.get("name"),
                        "pack_id": props.get("pack_id"),
                        "version": props.get("version"),
                        "scope": props.get("scope"),
                        "matched": via,
                        "provenance": props.get("provenance_kind"),
                        "verification": props.get("verification"),
                        "status": props.get("status"),
                        "_rank": rank,
                    }
                )
        hits.sort(key=lambda h: (h["_rank"], h["name"] or "", h["key"]))
        return [{k: v for k, v in h.items() if k != "_rank"} for h in hits[:limit]]

    def explore(
        self, key: str, hops: int = 2, kinds: set[str] | None = None, limit: int = 200
    ) -> dict:
        """The neighbourhood of a node, at most MAX_HOPS away, in both directions. Bounded on purpose: a graph answer is never unbounded."""
        if key not in self.nodes:
            raise GraphError(f"no such node {key}")
        hops = max(1, min(hops, MAX_HOPS))
        seen = {key: 0}
        edges: dict[tuple, dict] = {}
        queue = deque([key])
        while queue and len(seen) < limit:
            current = queue.popleft()
            if seen[current] >= hops:
                continue
            for identity in [*self._out[current], *self._in[current]]:
                kind = identity[0]
                if kinds and kind not in kinds or kind == "DK_IN_PACK":
                    continue
                other = identity[2] if identity[1] == current else identity[1]
                edges[identity] = self.rels[identity]
                if other not in seen:
                    seen[other] = seen[current] + 1
                    queue.append(other)
        return {
            "center": key,
            "hops": hops,
            "nodes": [
                {"key": k, "distance": d, **self.node(k)}
                for k, d in seen.items()
                if k in self.nodes and "document" not in self.nodes[k][1]
            ],
            "edges": [
                {
                    "type": i[0],
                    "source": i[1],
                    "target": i[2],
                    **{
                        k: v
                        for k, v in props.items()
                        if k in ("cardinality", "required", "mode", "reason", "condition", "type")
                    },
                }
                for i, props in edges.items()
            ],
            "truncated": len(seen) >= limit,
        }

    def path(
        self, source: str, target: str, kind: str = "DK_RELATES_TO", max_hops: int = 6
    ) -> list[str] | None:
        """The shortest chain of relationships between two entities (any direction), or None."""
        parents: dict[str, str | None] = {source: None}
        queue = deque([(source, 0)])
        while queue:
            current, depth = queue.popleft()
            if current == target:
                chain = []
                while current is not None:
                    chain.append(current)
                    current = parents[current]
                return chain[::-1]
            if depth >= max_hops:
                continue
            for identity in [*self._out[current], *self._in[current]]:
                if identity[0] != kind:
                    continue
                other = identity[2] if identity[1] == current else identity[1]
                if other not in parents:
                    parents[other] = current
                    queue.append((other, depth + 1))
        return None

    def compare_versions(self, pack_id: str, old: str, new: str) -> dict:
        """What changed between two versions of a pack, by item: added, removed, or changed (a different content hash)."""

        def snapshot(version: str) -> dict[str, str]:
            result = {}
            for label, props in self.nodes.values():
                if (
                    props.get("pack_id") == pack_id
                    and props.get("version") == version
                    and label not in ("DKPackVersion", "DKReview")
                ):
                    comparable = {
                        k: v for k, v in props.items() if k not in ("dk_key", "version", "document")
                    }
                    result[f"{label}:{props['item_id']}"] = hashlib.sha256(
                        json.dumps(comparable, sort_keys=True, default=str).encode()
                    ).hexdigest()[:12]
            return result

        before, after = snapshot(old), snapshot(new)
        return {
            "pack_id": pack_id,
            "from": old,
            "to": new,
            "added": sorted(set(after) - set(before)),
            "removed": sorted(set(before) - set(after)),
            "changed": sorted(k for k in set(before) & set(after) if before[k] != after[k]),
        }

    def impact(self, key: str, hops: int = 3) -> dict:
        """What depends on a definition: walking *backwards* along the relationships that mean 'relies on', so a change can be assessed before it is made."""
        relies = {
            "DK_RELATES_TO",
            "DK_USES",
            "DK_APPLIES_RULE",
            "DK_GOVERNS",
            "DK_OVERRIDES",
            "DK_DEPENDS_ON",
            "DK_INCLUDES",
            "DK_HAS_ATTRIBUTE",
            "DK_AFFECTS",
            "DK_PERFORMED_BY",
            "DK_EXTENDS",
        }
        if key not in self.nodes:
            raise GraphError(f"no such node {key}")
        seen = {key: 0}
        queue = deque([key])
        while queue:
            current = queue.popleft()
            if seen[current] >= min(hops, MAX_HOPS):
                continue
            for identity in self._in[current]:
                if identity[0] in relies and identity[1] not in seen:
                    seen[identity[1]] = seen[current] + 1
                    queue.append(identity[1])
        affected = [
            {
                "key": k,
                "distance": d,
                "label": self.nodes[k][0],
                "name": self.nodes[k][1].get("name"),
                "pack_id": self.nodes[k][1].get("pack_id"),
                "version": self.nodes[k][1].get("version"),
                "scope": self.nodes[k][1].get("scope"),
            }
            for k, d in seen.items()
            if k != key
        ]
        packs = sorted({(a["pack_id"], a["version"]) for a in affected if a["pack_id"]})
        return {
            "item": key,
            "affected": sorted(affected, key=lambda a: (a["distance"], a["key"])),
            "packs": [{"pack_id": p, "version": v} for p, v in packs],
            "companies": sorted(
                {a["scope"] for a in affected if str(a["scope"]).startswith("company:")}
            ),
        }

    def verify(self) -> list[str]:
        """Integrity checks a real graph would enforce or that a review would ask for."""
        problems = []
        for key, (label, props) in self.nodes.items():
            if props.get("dk_key") != key:
                problems.append(f"{key}: dk_key differs from the key")
            for needed in ("scope", "provenance_kind", "verification", "status"):
                if label not in ("DKCapability",) and needed not in props:
                    problems.append(f"{key}: missing {needed}")
            if props.get("provenance_kind") not in (*schema.PROVENANCE_KINDS, None):
                problems.append(f"{key}: unknown provenance {props.get('provenance_kind')}")
            if label not in (
                "DKPackVersion",
                "DKCompany",
                "DKCapability",
                "DKSystem",
                "DKOrgUnit",
            ) and not any(e[0] == "DK_IN_PACK" for e in self._out[key]):
                problems.append(f"{key}: not in any pack version")
            if (
                props.get("provenance_kind") in ("synthetic", "assumption")
                and props.get("verification") == "verified"
            ):
                problems.append(f"{key}: a synthetic or assumed item cannot be verified")
        return problems
