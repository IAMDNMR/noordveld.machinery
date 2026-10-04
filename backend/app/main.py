"""API entry point.

Run (from backend/):  python -m uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.dependencies import Catalogue, get_graph
from app.api.routes import accounts, agent, catalogue, intelligence, orders, parts, site
from app.core.config import get_settings
from app.core.exceptions import GraphUnavailableError, NotFoundError
from app.core.logging import setup_logging
from app.llm import LLMError, LLMInvalidResponse, LLMUnavailable

log = logging.getLogger(__name__)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title="Noordveld Parts Intelligence API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["GET", "POST", "PUT"], allow_headers=["*"], allow_credentials=True
    )

    @app.exception_handler(NotFoundError)
    async def not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return _error(404, "not_found", str(exc))

    @app.exception_handler(GraphUnavailableError)
    async def graph_unavailable(_: Request, __: GraphUnavailableError) -> JSONResponse:
        return _error(503, "graph_unavailable", "The parts catalogue is temporarily unavailable.")

    @app.exception_handler(LLMUnavailable)
    async def llm_unavailable(_: Request, exc: LLMUnavailable) -> JSONResponse:
        log.warning("question understanding unavailable: %s", exc)
        return _error(503, "llm_unavailable", "The question-understanding service is not available right now, so the question could not be answered. Please try again in a moment.")

    @app.exception_handler(LLMError)
    async def llm_invalid(_: Request, exc: LLMError) -> JSONResponse:
        log.warning("question understanding failed: %s", type(exc).__name__)
        return _error(502, "llm_invalid_response", "The question could not be understood reliably. Please rephrase it and try again.")

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}
        return _error(exc.status_code, detail.get("code", "error"), detail.get("message", ""))

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error: %s", type(exc).__name__)
        return _error(500, "internal_error", "Something went wrong.")

    system = APIRouter(tags=["system"])

    @system.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @system.get("/health/ready")
    def ready(service: Catalogue) -> dict[str, str]:
        service.ready()  # raises GraphUnavailableError -> 503
        return {"status": "ready"}

    app.include_router(system)
    app.include_router(parts.router, prefix="/api/v1")
    app.include_router(catalogue.router, prefix="/api/v1")
    app.include_router(intelligence.router, prefix="/api/v1")
    app.include_router(agent.router, prefix="/api/v1")
    app.include_router(site.router, prefix="/api/v1")
    app.include_router(accounts.router, prefix="/api/v1")
    app.include_router(orders.router, prefix="/api/v1")
    app.add_event_handler("shutdown", lambda: get_graph().close())
    return app


app = create_app()
