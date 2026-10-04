"""Agentic Shopping endpoints: read the request with the language model, answer from the graph. Nothing is ordered here."""
from __future__ import annotations

from fastapi import APIRouter

from app.agent.service import LABELS
from app.api.dependencies import Agents
from app.schemas.agent import AgentRequest, AgentResponse, AgentSuggestion

router = APIRouter(prefix="/agent", tags=["agentic shopping"])


@router.post("/recommend", response_model=AgentResponse)
def recommend(body: AgentRequest, service: Agents) -> AgentResponse:
    """Find the right part for a request. Read-only: the user adds it to the cart; no order is placed."""
    return service.recommend(body.request)


@router.get("/pipeline")
def pipeline() -> list[dict[str, str]]:
    """The agent's steps, in order, so the interface never defines them itself."""
    return [{"key": k, "label": v} for k, v in LABELS.items()]


@router.get("/suggestions", response_model=list[AgentSuggestion])
def suggestions(service: Agents) -> list[AgentSuggestion]:
    return service.suggestions()
