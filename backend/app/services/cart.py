"""Cart pricing. Stateless: the browser sends part ids and quantities, the graph supplies parts and prices."""

from __future__ import annotations

from app.graph.repositories.parts import PartRepository
from app.schemas.cart import Quote, QuoteLine, QuoteRequest, RejectedLine
from app.schemas.catalogue import Money
from app.services.part_status import is_orderable, rejection_reason, status_label
from app.services.parts import to_summary

NOTE = (
    "Demo catalogue prices exclude VAT and delivery. Choose transport during checkout to see the combined estimate. No payment is taken."
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
        rejected: list[RejectedLine] = []
        for part_id, qty in quantities.items():
            part = found.get(part_id)
            if part is None:
                continue
            status = part.availability.part_status if part.availability else None
            orderable = part.availability.orderable if part.availability else None
            if not is_orderable(
                status, orderable
            ):  # the order gate: never priced, never in the subtotal
                rejected.append(
                    RejectedLine(
                        part=part.model_copy(update={"price": None}),
                        quantity=qty,
                        status=status,
                        status_label=status_label(status),
                        reason=rejection_reason(status, orderable),
                    )
                )
                continue
            total = None
            if part.price is not None:
                total = Money(
                    amount=round(part.price.amount * qty, 2),
                    currency=part.price.currency,
                    data_status=part.price.data_status,
                )
            lines.append(QuoteLine(part=part, quantity=qty, line_total=total))

        unpriced = [line.part.part_id for line in lines if line.line_total is None]
        currencies = {line.line_total.currency for line in lines if line.line_total}
        subtotal = None
        if lines and not unpriced and len(currencies) == 1:
            subtotal = Money(
                amount=round(sum(line.line_total.amount for line in lines if line.line_total), 2),
                currency=currencies.pop(),
                data_status=lines[0].line_total.data_status if lines[0].line_total else None,
            )
        return Quote(
            lines=lines,
            rejected=rejected,
            unknown_part_ids=[i for i in quantities if i not in found],
            subtotal=subtotal,
            unpriced_part_ids=unpriced,
            note=NOTE,
        )
