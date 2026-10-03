"""FastAPI dependencies: one GraphClient per process, services built per request."""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.graph.client import GraphClient
from app.graph.repositories.catalogue import CatalogueRepository
from app.graph.repositories.parts import PartRepository
from app.services.cart import CartService
from app.services.catalogue import CatalogueService
from app.services.parts import PartService


@lru_cache
def get_graph() -> GraphClient:
    return GraphClient(get_settings())


Graph = Annotated[GraphClient, Depends(get_graph)]


def get_part_service(graph: Graph) -> PartService:
    return PartService(PartRepository(graph))


def get_catalogue_service(graph: Graph) -> CatalogueService:
    return CatalogueService(CatalogueRepository(graph))


def get_cart_service(graph: Graph) -> CartService:
    return CartService(PartRepository(graph))


Parts = Annotated[PartService, Depends(get_part_service)]
Catalogue = Annotated[CatalogueService, Depends(get_catalogue_service)]
Cart = Annotated[CartService, Depends(get_cart_service)]
