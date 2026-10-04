"""Language-model providers. `create_llm` is the only place a provider is chosen (LLM_PROVIDER); business code sees only LLMClient."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings
from app.llm.base import LLMClient, LLMError, LLMInvalidResponse, LLMParse, LLMUnavailable, ShoppingParse

__all__ = ["LLMClient", "LLMError", "LLMInvalidResponse", "LLMParse", "LLMUnavailable", "ShoppingParse", "create_llm", "PROVIDERS"]

PROVIDERS = ("groq", "gemini")


@lru_cache(maxsize=4)
def create_llm(settings: Settings) -> LLMClient | None:
    """The configured provider, one per process (so its rate limit and request cache are shared), or None when its key is missing."""
    if settings.llm_provider not in PROVIDERS:
        raise ValueError(f"LLM_PROVIDER must be one of {', '.join(PROVIDERS)}")
    if not settings.llm_configured:
        return None
    if settings.llm_provider == "gemini":
        from app.llm.gemini import GeminiClient

        return GeminiClient(settings)
    from app.llm.groq import GroqClient

    return GroqClient(settings)
