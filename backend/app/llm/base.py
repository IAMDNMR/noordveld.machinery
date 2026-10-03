"""Provider-independent language-model interface for Parts Intelligence.

The model's whole job is language: work out what a question asks, and word an answer from evidence the backend already
verified. It is never given Cypher to write and never decides a fact. Swap providers by implementing `LLMClient`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMError(Exception):
    """The model could not be used for this request (message never contains credentials)."""


class LLMUnavailable(LLMError):
    """Not configured, rate limited, unreachable or timed out."""


class LLMInvalidResponse(LLMError):
    """The model answered, but not in the required structure."""


@dataclass(frozen=True)
class LLMParse:
    """Structured understanding of a question. `mentions` are the entity names or numbers the user wrote, unresolved."""

    intent: str
    mentions: tuple[str, ...] = ()
    requires_clarification: bool = False
    clarification_question: str | None = None
    filters: dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    name: str

    def parse_question(self, question: str, intents: dict[str, str]) -> LLMParse:
        """Classify the question into one of `intents` (name -> description) and extract entity mentions."""

    def resolve_entities(self, question: str, intents: dict[str, str]) -> tuple[str, ...]:
        """Entity mentions only (names, part numbers, model codes as written)."""

    def generate_grounded_response(self, question: str, intent: str, evidence: list[dict[str, Any]], draft: str) -> str:
        """Reword `draft` using ONLY `evidence`. Must not add facts. The caller validates the result."""
