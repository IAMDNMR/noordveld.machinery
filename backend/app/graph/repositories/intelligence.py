"""Graph access for Parts Intelligence: one method per named query, rows returned as-is."""
from __future__ import annotations

import re
from typing import Any

from app.graph.client import GraphClient
from app.graph.queries import intelligence as q

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalise(text: str) -> str:
    """'NVM 1010-HY' -> 'nvm1010hy'."""
    return _NON_ALNUM.sub("", text.lower())


class IntelligenceRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._g = graph

    # resolution
    def resolve(self, mention: str) -> list[dict[str, Any]]:
        text = " ".join(mention.lower().split())
        return self._g.read(q.RESOLVE, norm=normalise(mention), text=text)

    # part facets
    def part_core(self, key: str) -> dict[str, Any] | None:
        rows = self._g.read(q.PART_CORE, key=key.strip().upper())
        return rows[0] if rows else None

    def _facet(self, query: str, part_id: str) -> list[dict[str, Any]]:
        return self._g.read(query, part_id=part_id)

    def fitment(self, part_id: str) -> list[dict[str, Any]]:
        return self._facet(q.PART_FITMENT, part_id)

    def related(self, part_id: str) -> list[dict[str, Any]]:
        return self._facet(q.PART_RELATED, part_id)

    def assemblies(self, part_id: str) -> list[dict[str, Any]]:
        return self._facet(q.PART_ASSEMBLIES, part_id)

    def suppliers(self, part_id: str) -> list[dict[str, Any]]:
        return self._facet(q.PART_SUPPLIERS, part_id)

    def dealers(self, part_id: str) -> list[dict[str, Any]]:
        return self._facet(q.PART_DEALERS, part_id)

    def warehouses(self, part_id: str) -> list[dict[str, Any]]:
        return self._facet(q.PART_WAREHOUSES, part_id)

    def compliance(self, part_id: str) -> list[dict[str, Any]]:
        return self._facet(q.PART_COMPLIANCE, part_id)

    def relationships(self, part_id: str) -> list[dict[str, Any]]:
        return self._facet(q.PART_RELATIONSHIPS, part_id)

    def counts(self, part_id: str) -> dict[str, Any]:
        rows = self._facet(q.PART_COUNTS, part_id)
        return rows[0] if rows else {}

    def category(self, part_id: str) -> dict[str, Any]:
        rows = self._facet(q.PART_CATEGORY, part_id)
        return rows[0] if rows else {}

    # other entities
    def machine_core(self, machine_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.MACHINE_CORE, machine_id=machine_id)
        return rows[0] if rows else None

    def _listing(self, query: str, limit: int, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        rows = self._g.read(query, limit=limit, **params)
        row = rows[0] if rows else {"total": 0, "rows": []}
        return int(row["total"]), list(row["rows"])

    def machine_parts(self, machine_id: str, category: str | None, limit: int) -> tuple[int, list[dict[str, Any]]]:
        return self._listing(q.MACHINE_PARTS, limit, machine_id=machine_id, category=category)

    def supplier_core(self, supplier_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.SUPPLIER_CORE, id=supplier_id)
        return rows[0] if rows else None

    def supplier_parts(self, supplier_id: str, limit: int) -> tuple[int, list[dict[str, Any]]]:
        return self._listing(q.SUPPLIER_PARTS, limit, id=supplier_id)

    def dealer_core(self, dealer_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.DEALER_CORE, id=dealer_id)
        return rows[0] if rows else None

    def dealer_parts(self, dealer_id: str, limit: int) -> tuple[int, list[dict[str, Any]]]:
        return self._listing(q.DEALER_PARTS, limit, id=dealer_id)

    def assembly_core(self, assembly_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.ASSEMBLY_CORE, id=assembly_id)
        return rows[0] if rows else None

    def assembly_parts(self, assembly_id: str, limit: int) -> tuple[int, list[dict[str, Any]]]:
        return self._listing(q.ASSEMBLY_PARTS, limit, id=assembly_id)

    def category_parts(self, name: str, limit: int) -> tuple[int, list[dict[str, Any]]]:
        return self._listing(q.CATEGORY_PARTS, limit, name=name)

    # whole-graph counts
    def data_quality(self) -> dict[str, Any]:
        return self._g.read(q.DATA_QUALITY)[0]

    def kpis(self) -> dict[str, Any]:
        return self._g.read(q.KPIS)[0]

    def graph_view(self, part_id: str) -> dict[str, Any]:
        rows = self._facet(q.PART_GRAPH_VIEW, part_id)
        return rows[0] if rows else {}

    def suggestion_seeds(self) -> dict[str, Any] | None:
        rows = self._g.read(q.SUGGESTION_SEEDS)
        return rows[0] if rows else None
