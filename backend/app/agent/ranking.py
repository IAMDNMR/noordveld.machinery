"""The agent's decision, deterministic and graph-only.

The language model reads the request (machine, part, budget, priority, availability wish, place, quantity); everything below works on facts the
graph returned for each candidate part. Rules, in order:

1. Only parts recorded as FITTING the machine are candidates (the search already guarantees this).
2. Fitment must be CONFIRMED; conditional fitment is never recommended as compatible.
3. The part must be VERIFIED and orderable (the same order gate as the cart).
4. A budget is a hard limit: price must be recorded and <= the budget. An unknown price never "fits" a budget.
5. The part must be available now: a depot holds known stock >= the quantity (IN_STOCK / LOW_STOCK), and when a destination is given a recorded
   route from that depot reaches it. ON_ORDER, OUT_OF_STOCK and UNKNOWN are not available now. Only when the user explicitly accepts waiting
   (availability "future") may an ON_ORDER part be admitted, always ranked after parts available now.
6. Ranking: cheapest -> price, then fulfilment days; fastest -> available now first, then recorded route days, then price; default -> available now,
   then availability state, then price. Ties end on the part number, so the order is total and repeatable. Unknown values rank last, never as zero.
7. Nothing is relaxed silently: if every compatible verified part fails a constraint, the result says so and why.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.agent.supply import STATE_LABEL, STATE_RANK

AVAILABILITY_RANK = STATE_RANK
AVAILABILITY_LABEL = STATE_LABEL
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
    availability: str | None  # best depot state: IN_STOCK / LOW_STOCK / ON_ORDER / OUT_OF_STOCK / UNKNOWN
    units: int | None  # known depot units; None when nothing is recorded
    supplier: str | None = None
    supplier_lead_days: int | None = None
    delivery_days: int | None = None  # recorded route days from the chosen depot to the requested destination
    delivery_from: str | None = None  # that depot
    stock_ok: bool | None = None  # a depot holds known stock >= the quantity; None = derive from availability and units
    route_ok: bool | None = None  # a recorded route exists from such a depot to the destination; None = no destination asked for

    @property
    def in_stock(self) -> bool:
        return (self.units or 0) > 0 and self.availability in ("IN_STOCK", "LOW_STOCK")

    @property
    def available_now(self) -> bool:
        have = self.in_stock if self.stock_ok is None else self.stock_ok
        return have and self.route_ok is not False

    @property
    def on_order(self) -> bool:
        return self.availability == "ON_ORDER"

    @property
    def fulfilment_days(self) -> int | None:
        """Recorded days to the customer: the route estimate when a destination was given; supplier lead time when the part is only on order."""
        if self.delivery_days is not None:
            return self.delivery_days
        if not self.available_now and self.supplier_lead_days is not None:
            return self.supplier_lead_days
        return None


@dataclass
class Constraints:
    budget_max: float | None = None
    preference: str = "none"  # cheapest | fastest | none
    availability: str = "none"  # none | prefer (both: available now only) | future (the user accepts waiting for on-order stock)
    destination: bool = False  # a destination was asked for, so a recorded route is required


@dataclass
class Decision:
    ranked: list[Facts] = field(default_factory=list)  # valid options, best first
    excluded_unverified: list[Facts] = field(default_factory=list)
    excluded_conditional: list[Facts] = field(default_factory=list)
    over_budget: list[Facts] = field(default_factory=list)
    unpriced: list[Facts] = field(default_factory=list)  # excluded only because a budget was set and no price is recorded
    not_available: list[Facts] = field(default_factory=list)  # no depot can supply the quantity now (out of stock, on order, unknown, too few)
    no_route: list[Facts] = field(default_factory=list)  # stock exists but no recorded route reaches the destination
    basis: str = ""

    @property
    def blocked_by(self) -> str | None:
        if self.ranked:
            return None
        if self.no_route and not self.not_available:
            return "route"
        if self.not_available or self.no_route:
            return "availability"
        if self.over_budget or self.unpriced:
            return "budget"
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
    admitted = []
    for f in pool:
        if f.available_now or (c.availability == "future" and f.on_order):
            admitted.append(f)
        elif f.stock_ok and f.route_ok is False:
            d.no_route.append(f)
        else:
            d.not_available.append(f)
    pool = admitted

    price = lambda f: f.price if f.price is not None else UNKNOWN  # noqa: E731
    avail = lambda f: AVAILABILITY_RANK.get(f.availability or "", 5)  # noqa: E731
    days = lambda f: f.fulfilment_days if f.fulfilment_days is not None else UNKNOWN  # noqa: E731
    now = lambda f: 0 if f.available_now else 1  # noqa: E731
    if c.preference == "cheapest":
        key, d.basis = (lambda f: (now(f), price(f), days(f), f.part_number)), "lowest recorded price, then fulfilment days"
    elif c.preference == "fastest":
        key, d.basis = (lambda f: (now(f), days(f), price(f), f.part_number)), "fastest recorded route (available now first), then price"
    else:
        key, d.basis = (lambda f: (now(f), avail(f), price(f), f.part_number)), "availability, then price"
    d.ranked = sorted(pool, key=key)
    return d


def tradeoffs(option: Facts, best: Facts) -> list[str]:
    """How an alternative differs from the recommendation, only where both values are recorded."""
    out = []
    if option.price is not None and best.price is not None and option.price != best.price:
        out.append("Lower price" if option.price < best.price else "Higher price")
    a, b = AVAILABILITY_RANK.get(option.availability or "", 5), AVAILABILITY_RANK.get(best.availability or "", 5)
    if a != b and a < 3 and b < 3:
        out.append("Better availability" if a < b else "Lower availability")
    if option.fulfilment_days is not None and best.fulfilment_days is not None and option.fulfilment_days != best.fulfilment_days:
        out.append("Faster delivery" if option.fulfilment_days < best.fulfilment_days else "Longer delivery")
    return out
