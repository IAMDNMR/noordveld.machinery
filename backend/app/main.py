"""API entry point. Scaffolding only: routes and business logic come in the next phase.

Run (from backend/):  python -m uvicorn app.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

app = FastAPI(title="Noordveld Parts Intelligence API", version="0.0.0")
app.add_middleware(CORSMiddleware, allow_origins=list(get_settings().cors_origins), allow_methods=["GET"], allow_headers=["*"])


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
