"""Part queries."""
from __future__ import annotations

from typing import Any

from app.graph.client import GraphClient
from app.graph.queries import parts as q


def search_tokens(text: str) -> list[str]:
    """Lower-cased words of a search text. Every word has to be found somewhere in the part's searchable text."""
    return [t.lower() for t in text.split()][:8]


class PartRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph

    def search(
        self,
        *,
        text: str,
        category: str | None,
        machine: str | None,
        availability: list[str] | None,
        orderable: bool | None,
        sort: str,
        offset: int,
        limit: int,
    ) -> tuple[int, list[str]]:
        """Matching part ids for one page, and the total number of matches."""
        rows = self._graph.read(
            q.LIST_PARTS,
            q=text.strip().lower(),
            tokens=search_tokens(text),
            category=category,
            machine=machine,
            availability=availability or None,
            orderable=orderable,
            sort=sort,
            offset=offset,
            limit=limit,
        )
        row = rows[0] if rows else {"total": 0, "part_ids": []}
        return int(row["total"]), list(row["part_ids"])

    def summaries(self, part_ids: list[str]) -> list[dict[str, Any]]:
        """Card data for the given ids, in the same order. Unknown ids are skipped."""
        if not part_ids:
            return []
        return self._graph.read(q.PART_SUMMARIES, part_ids=part_ids)

    def detail(self, key: str) -> dict[str, Any] | None:
        rows = self._graph.read(q.PART_DETAIL, key=key.strip().upper())
        return rows[0] if rows else None
