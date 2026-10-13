"""Agentic Shopping endpoints: read the request with the language model, answer from the graph. Nothing is ordered here."""
from __future__ import annotations

from fastapi import APIRouter

from app.agent.service import LABELS
from app.api.dependencies import Agents, CommerceEngine
from app.commerce_agent.agent import commerce_domains
from app.llm import LLMError
from app.question_catalog import SHOPPING_CATALOG
from app.schemas.agent import AgentRequest, AgentResponse, AgentSuggestion, Interpretation

router = APIRouter(prefix="/agent", tags=["agentic shopping"])


@router.post("/recommend", response_model=AgentResponse)
def recommend(body: AgentRequest, service: Agents, engine: CommerceEngine) -> AgentResponse:
    """Find the right part for a request. Read-only: the user adds it to the cart; no order is placed. `commerce_domains` names the order, shipment and warranty
    questions the request also contains; they are answered by POST /commerce/agent, which requires a signed-in user (nothing about them is read here)."""
    try:
        response = service.recommend(body.request)
    except LLMError:
        # the shopping agent reads requests with the language model; without it, the questions the commerce assistant answers by its own rules (orders, shipments,
        # warranty, and part searches) are still answered on the same screen. With nothing to answer, the language model's outage is reported as before (503).
        domains = commerce_domains(body.request, engine, parts_answered=False)
        if not domains:
            raise
        return AgentResponse(request=body.request, state="out_of_scope", interpretation=Interpretation(), steps=[], commerce_domains=domains,
                             question=UNAVAILABLE, notes=[UNAVAILABLE])
    response.commerce_domains = commerce_domains(body.request, engine, parts_answered=response.state != "out_of_scope")
    return response


UNAVAILABLE = "The shopping agent's language service is not responding right now, so price and delivery comparison is unavailable. The answers below come from the records."


@router.get("/pipeline")
def pipeline() -> list[dict[str, str]]:
    """The agent's steps, in order, so the interface never defines them itself."""
    return [{"key": k, "label": v} for k, v in LABELS.items()]


@router.get("/catalog")
def catalog() -> list[dict]:
    """The question catalog for the Agentic E-Commerce screen: parts, delivery, orders, shipments, warranty and combined questions."""
    return SHOPPING_CATALOG


@router.get("/suggestions", response_model=list[AgentSuggestion])
def suggestions(service: Agents) -> list[AgentSuggestion]:
    return service.suggestions()
