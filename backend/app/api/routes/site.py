"""Website and launch-film facts from the graph. Read-only."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response

from app.api.dependencies import Sites

router = APIRouter(tags=["site"])


@router.get("/site/overview")
def overview(service: Sites, response: Response) -> dict[str, Any]:
    """Machines, plants, brands and catalogue size for the company website."""
    # The same for every visitor and slow to read (about 1.7 s): let browsers and the CDN reuse it for a few minutes.
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=600"
    return service.overview()


@router.get("/showcase/launch-film")
def launch_film(service: Sites) -> dict[str, Any]:
    """The records the Agentic E-Commerce launch film shows: one machine, one part, its supply and one delivery."""
    return service.film()
