"""Cart pricing. Stateless: the browser sends part ids and quantities, the graph supplies parts and prices."""
from __future__ import annotations

from app.graph.repositories.parts import PartRepository
from app.schemas.cart import Quote, QuoteLine, QuoteRequest
from app.schemas.catalogue import Money
from app.services.parts import to_summary

NOTE = (
    "Prepared quote only. Prices are demo figures from the Noordveld demo dataset, excluding VAT and delivery. "
    "Order placement is not connected, so nothing here is an order."
)


class CartService:
    def __init__(self, repo: PartRepository) -> None:
        self._repo = repo

    def quote(self, request: QuoteRequest) -> Quote:
        quantities: dict[str, int] = {}
        for item in request.items:  # merge repeated ids
            quantities[item.part_id] = quantities.get(item.part_id, 0) + item.quantity
        found = {r["part_id"]: to_summary(r) for r in self._repo.summaries(list(quantities))}

        lines: list[QuoteLine] = []
        for part_id, qty in quantities.items():
            part = found.get(part_id)
            if part is None:
                continue
            total = None
            if part.price is not None:
                total = Money(amount=round(part.price.amount * qty, 2), currency=part.price.currency, data_status=part.price.data_status)
            lines.append(QuoteLine(part=part, quantity=qty, line_total=total))

        unpriced = [l.part.part_id for l in lines if l.line_total is None]
        currencies = {l.line_total.currency for l in lines if l.line_total}
        subtotal = None
        if lines and not unpriced and len(currencies) == 1:
            subtotal = Money(
                amount=round(sum(l.line_total.amount for l in lines if l.line_total), 2),
                currency=currencies.pop(),
                data_status=lines[0].line_total.data_status if lines[0].line_total else None,
            )
        return Quote(
            lines=lines,
            unknown_part_ids=[i for i in quantities if i not in found],
            subtotal=subtotal,
            unpriced_part_ids=unpriced,
            note=NOTE,
        )
