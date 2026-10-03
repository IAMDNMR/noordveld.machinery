"""Filter options: machines, categories, availability."""
from __future__ import annotations

from typing import Any

from app.graph.client import GraphClient
from app.graph.queries import catalogue as q


class CatalogueRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph

    def machines(self) -> list[dict[str, Any]]:
        return self._graph.read(q.MACHINES)

    def categories(self) -> list[dict[str, Any]]:
        return self._graph.read(q.CATEGORIES)

    def availability(self) -> list[dict[str, Any]]:
        return self._graph.read(q.AVAILABILITY)

    def ready(self) -> bool:
        return bool(self._graph.read(q.READY))
