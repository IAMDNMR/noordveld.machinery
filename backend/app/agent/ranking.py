"""The agent's decision, deterministic and graph-only.

The language model reads the request (machine, part, budget, priority, availability wish, place); everything below works on facts the graph
returned for each candidate part. Rules, in order:

1. Only parts recorded as FITTING the machine are candidates (the search already guarantees this).
2. Fitment must be CONFIRMED; conditional fitment is never recommended as compatible.
3. The part must be VERIFIED and orderable (the same order gate as the cart).
4. A budget is a hard limit: price must be recorded and <= the budget. An unknown price never "fits" a budget.
5. "Must be available now" is a hard limit (stock recorded > 0); "prefer in stock" only ranks.
6. Ranking: cheapest -> price, then availability; fastest -> fulfilment (stock first, then recorded delivery or supplier lead
   days), then price; default -> availability, then price. Unknown values rank last, never as zero.
7. Nothing is relaxed silently: if every compatible verified part fails a constraint, the result says so and why.
"""
from __future__ import annotations

from dataclasses import dataclass, field

AVAILABILITY_RANK = {"IN_STOCK": 0, "LIMITED": 1, "BACKORDER": 2}
AVAILABILITY_LABEL = {"IN_STOCK": "In stock", "LIMITED": "Limited", "BACKORDER": "Backorder"}
UNKNOWN = 10**9


@dataclass
class Facts:
    """What the graph holds for one candidate part (None = not recorded)."""

    part_id: str
    part_number: str
    name: str
    fitment_status: str | None
    part_status: str | None
    orderable: bool | None
    price: float | None
    availability: str | None  # IN_STOCK / LIMITED / BACKORDER
    units: int | None  # warehouse units recorded
    supplier: str | None = None
    supplier_lead_days: int | None = None
    delivery_days: int | None = None  # recorded estimate to the requested place, from a warehouse holding stock
    delivery_from: str | None = None

    @property
    def in_stock(self) -> bool:
        return (self.units or 0) > 0 and self.availability in ("IN_STOCK", "LIMITED")

    @property
    def fulfilment_days(self) -> int | None:
        """Recorded days to the customer: the delivery estimate when a place was given; supplier lead time when nothing is in stock."""
        if self.delivery_days is not None:
            return self.delivery_days
        if not self.in_stock and self.supplier_lead_days is not None:
            return self.supplier_lead_days
        return None


@dataclass
class Constraints:
    budget_max: float | None = None
    preference: str = "none"  # cheapest | fastest | none
    availability: str = "none"  # require | prefer | none


@dataclass
class Decision:
    ranked: list[Facts] = field(default_factory=list)  # valid options, best first
    excluded_unverified: list[Facts] = field(default_factory=list)
    excluded_conditional: list[Facts] = field(default_factory=list)
    over_budget: list[Facts] = field(default_factory=list)
    unpriced: list[Facts] = field(default_factory=list)  # excluded only because a budget was set and no price is recorded
    not_available: list[Facts] = field(default_factory=list)
    basis: str = ""

    @property
    def blocked_by(self) -> str | None:
        if self.ranked:
            return None
        if self.over_budget or self.unpriced:
            return "budget"
        if self.not_available:
            return "availability"
        if self.excluded_conditional and not self.excluded_unverified:
            return "fitment"
        return "verification"


def decide(candidates: list[Facts], c: Constraints) -> Decision:
    d = Decision()
    pool = []
    for f in candidates:
        if f.fitment_status != "CONFIRMED":
            d.excluded_conditional.append(f)
        elif not (f.part_status == "VERIFIED" and f.orderable is True):
            d.excluded_unverified.append(f)
        else:
            pool.append(f)
    if c.budget_max is not None:
        kept = []
        for f in pool:
            if f.price is None:
                d.unpriced.append(f)
            elif f.price > c.budget_max:
                d.over_budget.append(f)
            else:
                kept.append(f)
        pool = kept
    if c.availability == "require":
        d.not_available = [f for f in pool if not f.in_stock]
        pool = [f for f in pool if f.in_stock]

    price = lambda f: f.price if f.price is not None else UNKNOWN  # noqa: E731
    avail = lambda f: AVAILABILITY_RANK.get(f.availability or "", 3)  # noqa: E731
    days = lambda f: f.fulfilment_days if f.fulfilment_days is not None else UNKNOWN  # noqa: E731
    if c.preference == "cheapest":
        key, d.basis = (lambda f: (price(f), avail(f), f.part_number)), "lowest recorded price, then availability"
    elif c.preference == "fastest":
        key, d.basis = (lambda f: (0 if f.in_stock else 1, days(f), price(f), f.part_number)), "fastest recorded fulfilment (stock first), then price"
    else:
        key, d.basis = (lambda f: (0 if c.availability == "prefer" and f.in_stock else 1, avail(f), price(f), f.part_number)), "availability, then price"
    if c.availability == "prefer" and c.preference != "fastest":
        inner = key
        key = lambda f: (0 if f.in_stock else 1, *inner(f))  # noqa: E731
        d.basis = "in stock first, then " + d.basis
    d.ranked = sorted(pool, key=key)
    return d


def tradeoffs(option: Facts, best: Facts) -> list[str]:
    """How an alternative differs from the recommendation, only where both values are recorded."""
    out = []
    if option.price is not None and best.price is not None and option.price != best.price:
        out.append("Lower price" if option.price < best.price else "Higher price")
    a, b = AVAILABILITY_RANK.get(option.availability or "", 3), AVAILABILITY_RANK.get(best.availability or "", 3)
    if a != b and a < 3 and b < 3:
        out.append("Better availability" if a < b else "Lower availability")
    if option.fulfilment_days is not None and best.fulfilment_days is not None and option.fulfilment_days != best.fulfilment_days:
        out.append("Faster delivery" if option.fulfilment_days < best.fulfilment_days else "Longer delivery")
    return out
