"""Backend configuration, read from environment variables (and backend/.env when it exists). Secrets are never printed or logged."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
GRAPH_DIR = BACKEND_DIR / "graph"
ENV_FILE = BACKEND_DIR / ".env"


def _load_env_file(path: Path) -> None:
    """Minimal .env reader. Variables already set in the environment win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    neo4j_uri: str = ""
    neo4j_username: str = ""
    # repr=False keeps the password out of logs, tracebacks and debug output
    neo4j_password: str = field(default="", repr=False)
    neo4j_database: str = "neo4j"
    #: seconds a single graph query may run
    neo4j_query_timeout: float = 15.0
    #: origins allowed to call the API (the Vite dev server by default)
    cors_origins: tuple[str, ...] = ("http://localhost:5180",)
    log_level: str = "INFO"
    #: Gemini language layer (understanding and grounded wording only). Empty key = language model disabled.
    gemini_api_key: str = field(default="", repr=False)
    gemini_model: str = "gemini-2.5-flash"
    #: free tier allows 15 requests/minute; stay under it
    gemini_requests_per_minute: int = 12
    gemini_timeout: float = 20.0

    @property
    def llm_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def graph_configured(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_username and self.neo4j_password)


@lru_cache
def get_settings() -> Settings:
    _load_env_file(ENV_FILE)
    return Settings(
        neo4j_uri=os.environ.get("NEO4J_URI", ""),
        neo4j_username=os.environ.get("NEO4J_USERNAME", ""),
        neo4j_password=os.environ.get("NEO4J_PASSWORD", ""),
        neo4j_database=os.environ.get("NEO4J_DATABASE", "neo4j"),
        neo4j_query_timeout=float(os.environ.get("NEO4J_QUERY_TIMEOUT", "15")),
        cors_origins=tuple(o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5180").split(",") if o.strip()),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        gemini_model=os.environ.get("GEMINI_MODEL", "") or "gemini-2.5-flash",
        gemini_requests_per_minute=int(os.environ.get("GEMINI_REQUESTS_PER_MINUTE", "12")),
        gemini_timeout=float(os.environ.get("GEMINI_TIMEOUT", "20")),
    )
