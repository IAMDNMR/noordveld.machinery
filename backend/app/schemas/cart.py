"""Cart quote models. The cart itself lives in the browser as part ids and quantities; the API only prices it."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.catalogue import Money, PartSummary


class QuoteItem(BaseModel):
    part_id: str = Field(min_length=1, max_length=40)
    quantity: int = Field(ge=1, le=999)


class QuoteRequest(BaseModel):
    items: list[QuoteItem] = Field(max_length=100)


class QuoteLine(BaseModel):
    part: PartSummary
    quantity: int
    line_total: Money | None = None  # null when the part has no price in the graph


class Quote(BaseModel):
    lines: list[QuoteLine]
    unknown_part_ids: list[str]
    subtotal: Money | None = None  # only when every line is priced
    unpriced_part_ids: list[str]
    order_placement_available: bool = False
    note: str
