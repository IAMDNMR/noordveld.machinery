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










