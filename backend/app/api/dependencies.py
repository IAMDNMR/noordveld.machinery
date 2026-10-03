"""FastAPI dependencies: one GraphClient per process, services built per request."""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.graph.client import GraphClient
from app.graph.repositories.catalogue import CatalogueRepository
from app.graph.repositories.parts import PartRepository
from app.graph.repositories.intelligence import IntelligenceRepository
from app.intelligence.service import IntelligenceService
from app.intelligence.workspace import Overview, PartWorkspace
from app.llm import LLMClient, create_llm
from app.services.cart import CartService
from app.services.catalogue import CatalogueService
from app.services.parts import PartService


@lru_cache
def get_graph() -> GraphClient:
    return GraphClient(get_settings())


@lru_cache
def get_llm() -> LLMClient | None:
    return create_llm(get_settings())


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


def get_question_service(graph: Graph, llm: Annotated[LLMClient | None, Depends(get_llm)]) -> IntelligenceService:
    return IntelligenceService(IntelligenceRepository(graph), PartRepository(graph), llm)


def get_workspace(graph: Graph) -> PartWorkspace:
    return PartWorkspace(IntelligenceRepository(graph))


def get_overview(graph: Graph) -> Overview:
    return Overview(IntelligenceRepository(graph))


Questions = Annotated[IntelligenceService, Depends(get_question_service)]
Workspaces = Annotated[PartWorkspace, Depends(get_workspace)]
Overviews = Annotated[Overview, Depends(get_overview)]
