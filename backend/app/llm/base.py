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
    """Structured understanding of a question. `mentions` are the entity names or numbers the user wrote, unresolved;
    `entities` says what kind each one is (part, machine, supplier, dealer, assembly, category, order, second_part).
    `filters` are optional qualifiers: place, place_kind, proximity, location, target_kind, single."""

    intent: str
    mentions: tuple[str, ...] = ()
    requires_clarification: bool = False
    clarification_question: str | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    entities: dict[str, str] = field(default_factory=dict)
    in_scope: bool = True  # the scope guardrail: is this a Parts Intelligence question at all?
    need: str | None = None  # the kind of part or need the user wants ('hydraulic', 'filter'), apart from any machine; None when none was named
    confidence: float | None = None


@dataclass(frozen=True)
class ShoppingParse:
    """Structured reading of an Agentic Shopping request ("what do you need done?"). Values are as the user wrote them, unresolved."""

    in_scope: bool
    machine: str | None = None
    part_type: str | None = None
    preference: str = "none"  # cheapest | fastest | none
    delivery_place: str | None = None
    quantity: int | None = None
    clarification_question: str | None = None
    budget_max: float | None = None  # "under €800", "budget is 200", "up to 500 euro"
    budget_currency: str | None = None  # ISO code as stated (EUR for €); None when not stated
    availability: str = "none"  # require ("must be in stock", "available now") | prefer ("preferably in stock") | future (accepts waiting for on-order stock) | none


class LLMClient(Protocol):
    name: str

    def parse_question(self, question: str, intents: dict[str, str]) -> LLMParse:
        """Classify the question into one of `intents` (name -> description) and extract entity mentions."""

    def resolve_entities(self, question: str, intents: dict[str, str]) -> tuple[str, ...]:
        """Entity mentions only (names, part numbers, model codes as written)."""

    def generate_grounded_response(self, question: str, intent: str, evidence: list[dict[str, Any]], draft: str) -> str:
        """Reword `draft` using ONLY `evidence`. Must not add facts. The caller validates the result."""

    def parse_shopping_request(self, request: str) -> ShoppingParse:
        """Read a purchase request: the machine, the part needed, the preference and the delivery place. Never decides a fact."""
