"""The deterministic decision core, without a graph or a model."""
from app.agent.ranking import Constraints, Facts, decide, tradeoffs


def part(n, price=100.0, fit="CONFIRMED", status="VERIFIED", orderable=True, availability="IN_STOCK", units=5, **kw):
    return Facts(part_id=n, part_number=n, name=n, fitment_status=fit, part_status=status, orderable=orderable, price=price,
                 availability=availability, units=units, **kw)


def test_conditional_and_unverified_parts_are_never_ranked():
    d = decide([part("A", fit="CONDITIONAL"), part("B", status="IDENTIFICATION_REQUIRED"), part("C", orderable=False)], Constraints())
    assert d.ranked == [] and [f.part_number for f in d.excluded_conditional] == ["A"] and len(d.excluded_unverified) == 2


def test_budget_is_a_hard_limit_and_an_unknown_price_never_fits():
    d = decide([part("A", 900), part("B", None), part("C", 400)], Constraints(budget_max=500))
    assert [f.part_number for f in d.ranked] == ["C"] and [f.part_number for f in d.over_budget] == ["A"] and [f.part_number for f in d.unpriced] == ["B"]


def test_nothing_within_budget_is_reported_not_relaxed():
    d = decide([part("A", 900)], Constraints(budget_max=10))
    assert d.ranked == [] and d.blocked_by == "budget"


def test_require_stock_is_hard_and_prefer_only_ranks():
    parts = [part("A", 50, availability="BACKORDER", units=0), part("B", 80)]
    assert [f.part_number for f in decide(parts, Constraints(availability="require")).ranked] == ["B"]
    assert decide([parts[0]], Constraints(availability="require")).blocked_by == "availability"
    assert [f.part_number for f in decide(parts, Constraints(availability="prefer", preference="cheapest")).ranked] == ["B", "A"]


def test_cheapest_fastest_and_default_rankings():
    parts = [part("A", 50, availability="BACKORDER", units=0, supplier_lead_days=20), part("B", 90), part("C", 70, availability="LIMITED", units=2)]
    assert [f.part_number for f in decide(parts, Constraints(preference="cheapest")).ranked] == ["A", "C", "B"]
    assert [f.part_number for f in decide(parts, Constraints(preference="fastest")).ranked][-1] == "A"
    assert [f.part_number for f in decide(parts, Constraints()).ranked] == ["B", "C", "A"]


def test_fastest_uses_recorded_delivery_days():
    parts = [part("A", 50, delivery_days=4), part("B", 90, delivery_days=1)]
    assert [f.part_number for f in decide(parts, Constraints(preference="fastest")).ranked] == ["B", "A"]


def test_tradeoffs_only_where_both_values_are_known():
    best = part("A", 100, delivery_days=1)
    assert tradeoffs(part("B", 60, availability="BACKORDER", units=0, delivery_days=None, supplier_lead_days=9), best) == ["Lower price", "Lower availability", "Longer delivery"]
    assert tradeoffs(part("C", 100, availability=None), best) == []
