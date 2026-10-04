"""Website and launch-film facts from the graph. Read-only."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.dependencies import Sites

router = APIRouter(tags=["site"])


@router.get("/site/overview")
def overview(service: Sites) -> dict[str, Any]:
    """Machines, plants, brands and catalogue size for the company website."""
    return service.overview()


@router.get("/showcase/launch-film")
def launch_film(service: Sites) -> dict[str, Any]:
    """The records the Agentic E-Commerce launch film shows: one machine, one part, its supply and one delivery."""
    return service.film()
