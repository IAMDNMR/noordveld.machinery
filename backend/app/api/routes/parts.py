"""Part endpoints. Handlers only parse the request and call a service."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import Parts
from app.schemas.catalogue import PartDetail, PartPage
from app.services.parts import SORTS

router = APIRouter(prefix="/parts", tags=["parts"])


@router.get("", response_model=PartPage)
def list_parts(
    service: Parts,
    q: Annotated[str, Query(max_length=120, description="Part name, part number, legacy reference, category or machine")] = "",
    category: Annotated[str | None, Query(max_length=80)] = None,
    machine: Annotated[str | None, Query(max_length=40, description="Machine model code, via the FITS relationship")] = None,
    availability: Annotated[list[str] | None, Query(description="Availability states; repeat to combine")] = None,
    orderable: bool | None = None,
    sort: Annotated[str, Query(pattern="^(" + "|".join(SORTS) + ")$")] = "relevance",
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=60)] = 24,
) -> PartPage:
    return service.search(
        q=q, category=category, machine=machine, availability=availability, orderable=orderable,
        sort=sort, offset=offset, limit=limit,
    )


@router.get("/{key}", response_model=PartDetail)
def get_part(key: str, service: Parts) -> PartDetail:
    """A part by unified part number or part id."""
    return service.detail(key)
