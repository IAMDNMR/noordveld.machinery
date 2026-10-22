"""Agentic Shopping supply and destination rules, on fixtures: no graph, no model."""
from app.agent.ranking import Constraints, Facts, decide
from app.agent.supply import fold, part_supply, resolve_destination


def row(depot, state, qty, part="P1"):
    return {"part_id": part, "warehouse_id": depot, "name": f"Depot {depot}", "city": depot, "country_code": "NL", "stock_status": state, "available": qty, "data_status": "SYNTHETIC_DEMO"}


def route(depot, days, km=100.0, rid=None, shipto="S1"):
    return {"depot_id": depot, "shipto_id": shipto, "route_id": rid or f"R-{depot}-{days}", "option_id": "O", "option_name": "Road", "option_code": "RD", "mode": "ROAD",
            "service_level": "STANDARD", "distance_km": km, "days": days, "estimate_basis": "ESTIMATED", "legs": 1, "data_status": "SYNTHETIC_DEMO",
            "freight_total": 10.0, "freight_currency": "EUR", "rate_data_status": "SYNTHETIC_DEMO"}




def test_unknown_stock_is_unknown_never_zero_and_never_available():
    s = part_supply("P1", 1, [row("A", "UNKNOWN", None), row("B", "IN_STOCK", None)], None)  # a status without a quantity is UNKNOWN too
    assert s.availability == "UNKNOWN" and s.units is None and not s.stock_ok and not s.available_now
    assert all(d["available"] is None for d in s.depots)










def test_the_depot_is_chosen_by_the_fastest_route_not_by_most_stock():
    rows = [row("A", "IN_STOCK", 500), row("B", "IN_STOCK", 2)]
    s = part_supply("P1", 1, rows, [route("A", 5), route("B", 2)])
    assert s.depot["depot_id"] == "B" and s.route["estimated_days"] == 2






def facts(n, price, **kw):
    base = dict(part_id=n, part_number=n, name=n, fitment_status="CONFIRMED", part_status="VERIFIED", orderable=True, price=price, availability="IN_STOCK", units=5)
    return Facts(**{**base, **kw})








# ── destinations ─────────────────────────────────────────────────────────────────────────────────
DEST = [{"shipto_id": "S1", "city": "Hamburg", "country_code": "DE"}, {"shipto_id": "S2", "city": "Köln", "country_code": "DE"},
        {"shipto_id": "S3", "city": "Koeln", "country_code": "DE"}, {"shipto_id": "S4", "city": "Charleroi", "country_code": "BE"},
        {"shipto_id": "S5", "city": "Springfield", "country_code": "DE"}, {"shipto_id": "S6", "city": "Springfield", "country_code": "NL"}]








