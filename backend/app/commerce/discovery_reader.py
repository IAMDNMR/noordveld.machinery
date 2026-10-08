"""Where discovery facts come from. Two readers return the SAME canonical-named dictionaries (the pattern of the logistics and lifecycle readers):

  FileDiscoveryReader   the canonical dataset files (no database: tests and offline work)
  GraphDiscoveryReader  the Neo4j graph (read-only), through the existing canonical Exporter, so there is one graph-to-canonical mapping and no second set of queries

Both answer from the same canonical vocabulary (name, description, aliases, common_names, technical_terms, symptoms, subcategory); nothing is added or generated.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Protocol

from app.canonical.io import CANON_DIR, load_rows
from app.canonical.registry import BY_NAME
from app.graph.client import GraphClient


class DiscoveryReader(Protocol):
    def machines(self) -> list[dict[str, Any]]: ...
    def machine(self, machine_id: str) -> dict[str, Any] | None: ...
    def parts(self) -> list[dict[str, Any]]: ...
    def part(self, part_id: str) -> dict[str, Any] | None: ...
    def category_name(self, category_id: str | None) -> str | None: ...
    def fitments(self, machine_id: str, part_id: str) -> list[dict[str, Any]]: ...
    def approved_sources(self, part_id: str) -> list[dict[str, Any]]: ...
    def inventory(self, part_id: str) -> list[dict[str, Any]]: ...
    def prices(self, part_id: str) -> list[dict[str, Any]]: ...
    def location(self, location_id: str) -> dict[str, Any] | None: ...
    def customer(self, customer_id: str) -> dict[str, Any] | None: ...
    def region_of_country(self, country_code: str | None) -> str | None: ...


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k != "ingestion_timestamp"}


class _DatasetReader:
    """All the lookups, written once, over `_rows(dataset_name)`. A subclass only says where the rows come from."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._geo: dict[str, Any] | None = None

    def _rows(self, name: str) -> list[dict[str, Any]]:  # pragma: no cover - overridden
        raise NotImplementedError

    def _index(self, name: str, field: str) -> dict[str, dict[str, Any]]:
        key = f"idx:{name}:{field}"
        if key not in self._cache:
            self._cache[key] = {r[field]: r for r in self._rows(name)}
        return self._cache[key]

    def _group(self, name: str, field: str) -> dict[str, list[dict[str, Any]]]:
        key = f"grp:{name}:{field}"
        if key not in self._cache:
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for r in self._rows(name):
                grouped[r[field]].append(r)
            self._cache[key] = grouped
        return self._cache[key]

    def machines(self):
        return sorted(self._rows("machines"), key=lambda r: r["machine_id"])

    def machine(self, machine_id):
        return self._index("machines", "machine_id").get(machine_id)

    def parts(self):
        return sorted(self._rows("parts"), key=lambda r: r["part_id"])

    def part(self, part_id):
        return self._index("parts", "part_id").get(part_id)

    def category_name(self, category_id):
        row = self._index("categories", "category_id").get(category_id) if category_id else None
        return row["name"] if row else None

    def fitments(self, machine_id, part_id):
        return sorted((r for r in self._group("fitment", "part_id").get(part_id, []) if r["machine_id"] == machine_id), key=lambda r: r["fitment_id"])

    def approved_sources(self, part_id):
        return sorted(self._group("approved_sources", "part_id").get(part_id, []), key=lambda r: r["approved_source_id"])

    def inventory(self, part_id):
        return sorted(self._group("inventory", "part_id").get(part_id, []), key=lambda r: r["location_id"])

    def prices(self, part_id):
        return sorted(self._group("pricing", "part_id").get(part_id, []), key=lambda r: r["price_id"])

    def location(self, location_id):
        return self._index("locations", "location_id").get(location_id)

    def customer(self, customer_id):
        return self._index("customers", "customer_id").get(customer_id)

    def region_of_country(self, country_code):
        if self._geo is None:
            self._geo = json.loads((CANON_DIR / "reference" / "geography.json").read_text(encoding="utf-8"))["countries"]
        c = self._geo.get(country_code or "")
        return c["region"] if c else None


class FileDiscoveryReader(_DatasetReader):
    def __init__(self, root: Path = CANON_DIR) -> None:
        super().__init__()
        self.root = root

    def _rows(self, name):
        if name not in self._cache:
            spec = BY_NAME[name]
            self._cache[name] = [_clean(spec.model.model_validate(r).model_dump()) for r in load_rows(spec, self.root)[0]]
        return self._cache[name]


class GraphDiscoveryReader(_DatasetReader):
    """Reads each dataset once per reader through the canonical Exporter (read-only: it only runs MATCH queries) and then answers from memory.
    Build one per process or request scope; the graph client is shared and never closed here."""

    def __init__(self, graph: GraphClient) -> None:
        super().__init__()
        from app.canonical.export import Exporter  # imported here: the exporter is the one graph-to-canonical mapping, loaded only when the graph is used

        self._ex = Exporter(graph=graph)

    def _rows(self, name):
        if name not in self._cache:
            rows = getattr(self._ex, name)()
            spec = BY_NAME[name]
            self._cache[name] = [_clean(spec.model.model_validate(r).model_dump()) for r in rows]
        return self._cache[name]
