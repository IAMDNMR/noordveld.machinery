"""Language-model providers. `create_llm` is the only place a provider is chosen (LLM_PROVIDER); business code sees only LLMClient."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from app.core.config import Settings
from app.llm.base import (
    CommerceParse,
    LLMClient,
    LLMError,
    LLMInvalidResponse,
    LLMParse,
    LLMUnavailable,
    ShoppingParse,
)

__all__ = [
    "PROVIDERS",
    "CommerceParse",
    "LLMClient",
    "LLMError",
    "LLMInvalidResponse",
    "LLMParse",
    "LLMUnavailable",
    "ShoppingParse",
    "create_llm",
    "create_reasoning_llm",
    "PROVIDERS",
]

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


@lru_cache(maxsize=4)
def create_reasoning_llm(settings: Settings) -> LLMClient | None:
    """The Spark reasoning model: `AI_PROVIDER` (nvidia, groq or gemini) when set, otherwise the project's `LLM_PROVIDER`.
    One provider, chosen by configuration; there is no silent failover between providers."""
    provider = settings.ai_provider or settings.llm_provider
    if provider == "nvidia":
        if not (
            settings.nvidia_api_key
            and (settings.nvidia_planner_model or settings.nvidia_fast_model)
        ):
            return None
        from app.llm.nvidia import NvidiaClient

        # The planner model is the default: the smaller one is 2-4x faster but proposed duplicates and malformed steps in testing. SPARK_MODEL=fast opts in.
        import os

        fast = os.environ.get("SPARK_MODEL", "").strip().lower() == "fast"
        return NvidiaClient(
            settings,
            model=(settings.nvidia_fast_model or settings.nvidia_planner_model)
            if fast
            else (settings.nvidia_planner_model or settings.nvidia_fast_model),
        )
    if provider not in PROVIDERS:
        raise ValueError(f"AI_PROVIDER must be one of nvidia, {', '.join(PROVIDERS)}")
    return create_llm(replace(settings, llm_provider=provider))
