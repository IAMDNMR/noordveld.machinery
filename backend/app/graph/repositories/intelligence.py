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

    def warehouse_stock(self, warehouse_id: str, limit: int) -> dict[str, Any]:
        rows = self._g.read(q.WAREHOUSE_STOCK, id=warehouse_id, limit=limit)
        return rows[0] if rows else {"recorded": 0, "in_stock": 0, "out_of_stock": 0, "not_stated": 0, "rows": []}

    def subject(self, kind: str, entity_id: str) -> dict[str, Any] | None:
        query = q.SUBJECT.get(kind)
        rows = self._g.read(query, id=entity_id) if query else []
        return rows[0] if rows else None

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
    def machines(self, place: str | None = None, brand: str | None = None) -> list[dict[str, Any]]:
        return self._g.read(q.MACHINE_LIST, place=place, brand=brand)

    def machine_core(self, machine_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.MACHINE_CORE, machine_id=machine_id)
        return rows[0] if rows else None

    def _listing(self, query: str, limit: int, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        rows = self._g.read(query, limit=limit, **params)
        row = rows[0] if rows else {"total": 0, "rows": []}
        return int(row["total"]), list(row["rows"])

    def shared_parts(self, machine: str | None, limit: int) -> tuple[int, list[dict[str, Any]]]:
        return self._listing(q.SHARED_PARTS, limit, machine=machine)

    def part_service_plans(self, part_id: str) -> list[dict[str, Any]]:
        return self._g.read(q.PART_SERVICE_PLANS, id=part_id)

    def part_orders(self, part_id: str) -> list[dict[str, Any]]:
        return self._g.read(q.PART_ORDERS, id=part_id)

    def low_stock_parts(self, limit: int) -> tuple[int, list[dict[str, Any]]]:
        return self._listing(q.LOW_STOCK_PARTS, limit)

    def machine_parts(self, machine_id: str, category: str | None, limit: int) -> tuple[int, list[dict[str, Any]]]:
        return self._listing(q.MACHINE_PARTS, limit, machine_id=machine_id, category=category)

    def category_names(self) -> list[dict[str, Any]]:
        return self._g.read(q.CATEGORY_NAMES)

    def machines_with_category(self, machine_id: str, category: str) -> list[dict[str, Any]]:
        return self._g.read(q.MACHINES_WITH_CATEGORY, machine_id=machine_id, category=category)

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

    def path_between(self, a: tuple[str, str, str], b: tuple[str, str, str]) -> list[dict[str, Any]]:
        """a and b are (label, id property, id). Labels and properties come from a fixed map in the service, never from user text."""
        return self._g.read(q.PATH_BETWEEN, a_label=a[0], a_prop=a[1], a_id=a[2], b_label=b[0], b_prop=b[1], b_id=b[2])

    def path_to_kind(self, a: tuple[str, str, str], label: str) -> list[dict[str, Any]]:
        return self._g.read(q.PATH_TO_KIND, a_label=a[0], a_prop=a[1], a_id=a[2], b_label=label)

    def order_status(self, order_id: str) -> dict[str, Any] | None:
        rows = self._g.read(q.ORDER_STATUS, id=order_id)
        return rows[0] if rows else None

    def places(self) -> dict[str, Any]:
        rows = self._g.read(q.PLACES)
        return rows[0] if rows else {"cities": [], "countries": []}

    def located(self, kind: str, city: str | None, country_code: str | None) -> list[dict[str, Any]]:
        query = {"DEALER": q.DEALERS_IN, "SUPPLIER": q.SUPPLIERS_IN, "WAREHOUSE": q.WAREHOUSES_IN}[kind]
        return self._g.read(query, city=city.lower() if city else None, cc=country_code)

    def entity(self, kind: str, entity_id: str) -> dict[str, Any] | None:
        """One node's detail row for the graph inspector. `kind` is checked against a fixed map by the caller."""
        if kind == "MACHINE":
            return self.machine_core(entity_id)
        if kind == "SUPPLIER":
            return self.supplier_core(entity_id)
        if kind == "DEALER":
            return self.dealer_core(entity_id)
        if kind == "ASSEMBLY":
            core = self.assembly_core(entity_id)
            if core is not None:
                core["part_count"] = self.assembly_parts(entity_id, 1)[0]
            return core
        query = {"WAREHOUSE": q.WAREHOUSE_CORE, "COMPLIANCE": q.COMPLIANCE_CORE, "CATEGORY": q.CATEGORY_CORE}[kind]
        rows = self._g.read(query, id=entity_id)
        return rows[0] if rows else None
