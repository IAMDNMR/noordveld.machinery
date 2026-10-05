"""Agentic Shopping supply and destination rules, on fixtures: no graph, no model."""
from app.agent.ranking import Constraints, Facts, decide
from app.agent.supply import fold, part_supply, resolve_destination


def row(depot, state, qty, part="P1"):
    return {"part_id": part, "warehouse_id": depot, "name": f"Depot {depot}", "city": depot, "country_code": "NL", "stock_status": state, "available": qty, "data_status": "SYNTHETIC_DEMO"}


def route(depot, days, km=100.0, rid=None, shipto="S1"):
    return {"depot_id": depot, "shipto_id": shipto, "route_id": rid or f"R-{depot}-{days}", "option_id": "O", "option_name": "Road", "option_code": "RD", "mode": "ROAD",
            "service_level": "STANDARD", "distance_km": km, "days": days, "estimate_basis": "ESTIMATED", "legs": 1, "data_status": "SYNTHETIC_DEMO",
            "freight_total": 10.0, "freight_currency": "EUR", "rate_data_status": "SYNTHETIC_DEMO"}


def test_in_stock_and_low_stock_with_a_quantity_are_available_now():
    s = part_supply("P1", 1, [row("A", "LOW_STOCK", 2)], None)
    assert s.availability == "LOW_STOCK" and s.units == 2 and s.stock_ok and s.available_now and s.route_ok is None


def test_unknown_stock_is_unknown_never_zero_and_never_available():
    s = part_supply("P1", 1, [row("A", "UNKNOWN", None), row("B", "IN_STOCK", None)], None)  # a status without a quantity is UNKNOWN too
    assert s.availability == "UNKNOWN" and s.units is None and not s.stock_ok and not s.available_now
    assert all(d["available"] is None for d in s.depots)


def test_on_order_and_out_of_stock_are_known_not_available_now():
    s = part_supply("P1", 1, [row("A", "ON_ORDER", 0), row("B", "OUT_OF_STOCK", 0)], None)
    assert s.availability == "ON_ORDER" and s.units == 0 and not s.stock_ok


def test_quantity_must_fit_in_one_depot():
    rows = [row("A", "IN_STOCK", 3), row("B", "IN_STOCK", 3)]
    assert part_supply("P1", 3, rows, None).stock_ok
    s = part_supply("P1", 5, rows, None)  # 6 units in total, but no single depot can supply 5
    assert s.units == 6 and not s.stock_ok


def test_a_destination_without_a_route_means_not_available_to_it():
    s = part_supply("P1", 1, [row("A", "IN_STOCK", 9)], [])
    assert s.stock_ok and s.route_ok is False and not s.available_now and s.route is None


def test_a_route_only_counts_from_a_depot_that_can_supply():
    rows = [row("A", "OUT_OF_STOCK", 0), row("B", "IN_STOCK", 9)]
    s = part_supply("P1", 1, rows, [route("A", 1), route("B", 4)])  # A is the faster route but holds nothing
    assert s.depot["depot_id"] == "B" and s.route["estimated_days"] == 4


def test_the_depot_is_chosen_by_the_fastest_route_not_by_most_stock():
    rows = [row("A", "IN_STOCK", 500), row("B", "IN_STOCK", 2)]
    s = part_supply("P1", 1, rows, [route("A", 5), route("B", 2)])
    assert s.depot["depot_id"] == "B" and s.route["estimated_days"] == 2


def test_changing_a_route_value_changes_the_chosen_depot_and_restoring_it_restores_the_choice():
    rows = [row("A", "IN_STOCK", 5), row("B", "IN_STOCK", 5)]
    original = [route("A", 2), route("B", 3)]
    assert part_supply("P1", 1, rows, original).depot["depot_id"] == "A"
    changed = [route("A", 9), route("B", 3)]  # a controlled change in the fixture
    assert part_supply("P1", 1, rows, changed).depot["depot_id"] == "B"
    assert part_supply("P1", 1, rows, original).depot["depot_id"] == "A"  # original value back, original result back


def test_equal_routes_end_on_the_depot_id_so_the_choice_is_repeatable():
    rows = [row("B", "IN_STOCK", 5), row("A", "IN_STOCK", 5)]
    picks = {part_supply("P1", 1, rows, [route("B", 2, rid="R2"), route("A", 2, rid="R1")]).depot["depot_id"] for _ in range(5)}
    assert picks == {"A"}


def facts(n, price, **kw):
    base = dict(part_id=n, part_number=n, name=n, fitment_status="CONFIRMED", part_status="VERIFIED", orderable=True, price=price, availability="IN_STOCK", units=5)
    return Facts(**{**base, **kw})


def test_equal_prices_are_tie_broken_by_part_number():
    d = decide([facts("B", 100.0), facts("A", 100.0), facts("C", 100.0)], Constraints(preference="cheapest"))
    assert [f.part_number for f in d.ranked] == ["A", "B", "C"]


def test_unknown_availability_is_not_ranked_and_a_missing_route_blocks_with_the_right_reason():
    d = decide([facts("A", 10.0, availability="UNKNOWN", units=None, stock_ok=False)], Constraints())
    assert d.ranked == [] and d.blocked_by == "availability"
    d = decide([facts("A", 10.0, stock_ok=True, route_ok=False)], Constraints(destination=True))
    assert d.ranked == [] and d.blocked_by == "route"


def test_fastest_uses_the_recorded_route_days_and_unknown_days_rank_last():
    d = decide([facts("A", 10.0, delivery_days=4, route_ok=True), facts("B", 99.0, delivery_days=1, route_ok=True), facts("C", 1.0, route_ok=True)],
               Constraints(preference="fastest", destination=True))
    assert [f.part_number for f in d.ranked] == ["B", "A", "C"]


# ── destinations ─────────────────────────────────────────────────────────────────────────────────
DEST = [{"shipto_id": "S1", "city": "Hamburg", "country_code": "DE"}, {"shipto_id": "S2", "city": "Köln", "country_code": "DE"},
        {"shipto_id": "S3", "city": "Koeln", "country_code": "DE"}, {"shipto_id": "S4", "city": "Charleroi", "country_code": "BE"},
        {"shipto_id": "S5", "city": "Springfield", "country_code": "DE"}, {"shipto_id": "S6", "city": "Springfield", "country_code": "NL"}]


def test_a_city_resolves_regardless_of_case_and_accents_and_spelling_variants():
    assert fold("Köln") == fold("Koeln") == "koeln"
    d = resolve_destination("hamburg", DEST)
    assert d.kind == "city" and d.shipto_ids == ["S1"] and d.country_code == "DE"
    assert sorted(resolve_destination("Köln", DEST).shipto_ids) == ["S2", "S3"]


def test_a_country_alone_is_not_a_destination_and_offers_its_recorded_cities():
    d = resolve_destination("Belgium", DEST)
    assert d.kind == "country" and d.country_code == "BE" and d.choices == ["Charleroi"] and d.shipto_ids == []


def test_an_unknown_place_is_never_guessed():
    d = resolve_destination("Atlantis", DEST)
    assert d.kind == "unknown" and d.shipto_ids == [] and "Hamburg" in d.choices


def test_the_same_city_name_in_two_countries_is_ambiguous_until_the_country_is_given():
    assert resolve_destination("Springfield", DEST).kind == "ambiguous"
    d = resolve_destination("Springfield, Netherlands", DEST)
    assert d.kind == "city" and d.country_code == "NL" and d.shipto_ids == ["S6"]
