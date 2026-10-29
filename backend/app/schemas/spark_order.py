"""Spark's guided parts-order journey: the state the browser keeps between turns and the strict shape of what the model may extract from free text.

The model supplies only the user's own words as slots; every id, price, stock level and ranking comes from the graph and app/services/order_journey.py."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Short = Field(default=None, max_length=200)


class OrderSlots(BaseModel):
    """Everything the user has decided so far. Each value is re-validated against the graph on every turn, so a stale or tampered value is dropped, never trusted."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    part_id: str | None = Field(default=None, max_length=60)
    quantity: int | None = Field(default=None, ge=1, le=99)
    machine: str | None = Short
    machine_skipped: bool = False
    country: str | None = Field(default=None, min_length=2, max_length=2)
    ship_to_id: str | None = Field(default=None, max_length=40)
    route_id: str | None = Field(default=None, max_length=120)
    dealer_id: str | None = Field(default=None, max_length=40)
    service_required: bool = False
    budget_eur: float | None = Field(default=None, gt=0, le=10_000_000)
    needed_by: date | None = None
    timing_skipped: bool = False
    #: the user's stated delivery priority; it re-ranks the recorded options and persists across turns
    preference: Literal["fastest", "cheapest"] | None = None
    name: str | None = Short
    company: str | None = Short
    email: str | None = Short
    phone: str | None = Field(default=None, max_length=40)
    receiver_name: str | None = Short
    receiver_phone: str | None = Field(default=None, max_length=40)
    #: Spark fills every step it safely can (quantity 1, the only fitting machine, the recommended route, a dealer that
    #: holds stock, as soon as possible) and asks only for what it cannot know. Placing still needs the user's yes.
    auto: bool = False
    #: what Spark chose in auto mode, by field, said back in the summary; changing a field removes its entry
    assumed: dict[str, str] = Field(default_factory=dict, max_length=6)


class OrderTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    slots: OrderSlots = Field(default_factory=OrderSlots)
    # What the user just chose or typed into a form: merged over `slots`, then validated.
    patch: dict[str, Any] = Field(default_factory=dict)
    message: str | None = Field(default=None, max_length=500)
    confirm: bool = False
    #: reopen a completed step to change it; every other choice is kept
    revisit: Literal["fulfilment", "details"] | None = None
    # The total the user saw on the review card; a different current total blocks the order until it is re-confirmed.
    reviewed_total: float | None = None
    #: the server's seal on the exact summary the user reviewed; placing needs it, and any change to the order or its age voids it
    confirmation: str | None = Field(default=None, max_length=200)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=80)


class OrderMessage(BaseModel):
    """The model's reading of one free-text reply. `relevant` is false when the user asked about something else."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    relevant: bool
    #: a different part number the user switches to; the journey looks it up in the catalogue
    part: str | None = Field(default=None, max_length=60)
    #: the user wants to see or compare the delivery options again
    compare_options: bool | None = None
    quantity: int | None = Field(default=None, ge=1, le=99)
    machine: str | None = Field(default=None, max_length=80)
    skip_machine: bool | None = None
    destination: str | None = Field(default=None, max_length=120)
    needed_by: date | None = None
    budget_eur: float | None = Field(default=None, gt=0, le=10_000_000)
    install: bool | None = None
    preference: Literal["fastest", "cheapest"] | None = None
    #: the reply only agrees to go on with what is on screen ('ok, continue'); it never confirms an order
    proceed: bool | None = None
    name: str | None = Field(default=None, max_length=120)
    company: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    receiver_name: str | None = Field(default=None, max_length=120)
    receiver_phone: str | None = Field(default=None, max_length=40)
