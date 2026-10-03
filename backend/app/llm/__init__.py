"""Language-model providers. `create_llm` is the only place a provider is chosen."""
from __future__ import annotations

from app.core.config import Settings
from app.llm.base import LLMClient, LLMError, LLMInvalidResponse, LLMParse, LLMUnavailable

__all__ = ["LLMClient", "LLMError", "LLMInvalidResponse", "LLMParse", "LLMUnavailable", "create_llm"]


def create_llm(settings: Settings) -> LLMClient | None:
    """The configured model, or None when no key is set (deterministic questions still work)."""
    if not settings.llm_configured:
        return None
    from app.llm.gemini import GeminiClient

    return GeminiClient(settings)
