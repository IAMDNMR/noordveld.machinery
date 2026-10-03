"""Filter options for the catalogue UI, straight from the graph."""
from __future__ import annotations

from app.graph.repositories.catalogue import CatalogueRepository
from app.schemas.catalogue import AvailabilityOption, CatalogueFilters, CategoryOption, MachineOption


class CatalogueService:
    def __init__(self, repo: CatalogueRepository) -> None:
        self._repo = repo

    def filters(self) -> CatalogueFilters:
        return CatalogueFilters(
            categories=[CategoryOption(**{**r["category"], "part_count": r["part_count"]}) for r in self._repo.categories()],
            machines=[MachineOption(**{**r["machine"], "part_count": r["part_count"]}) for r in self._repo.machines()],
            availability=[
                AvailabilityOption(state=r["state"], part_count=r["part_count"], data_status=r["data_status"])
                for r in self._repo.availability()
            ],
        )

    def ready(self) -> bool:
        return self._repo.ready()
