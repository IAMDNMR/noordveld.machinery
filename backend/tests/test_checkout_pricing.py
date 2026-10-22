from app.services.fulfilment import cost_block, money_amount, route_cost


def test_costs_use_decimal_rounding_and_never_substitute_zero_for_missing_prices():
    assert cost_block(0.1, 0.2)['total'] == 0.3
    assert money_amount('1.005') == 1.01
    assert money_amount(float('nan')) is None
    assert money_amount(-1) is None
    assert cost_block(None, 12.5)['total'] is None
    assert cost_block(0, 0)['total'] == 0


def test_selected_route_controls_freight_and_incompatible_currency_is_not_added():
    lines = [{'line_total_eur': 50}, {'line_total_eur': 12.5}]
    assert route_cost(lines, {'freight': {'amount': 10, 'currency': 'EUR'}})['total'] == 72.5
    assert route_cost(lines, {'freight': {'amount': 20, 'currency': 'EUR'}})['total'] == 82.5
    assert route_cost(lines, {'freight': {'amount': 20, 'currency': 'USD'}})['total'] is None
    assert route_cost([{'line_total_eur': None}], {'freight': {'amount': 20, 'currency': 'EUR'}})['part_cost'] is None


def test_repository_passes_price_snapshot_to_atomic_creation_and_uses_nm_number():
    from app.graph.repositories.fulfilment import GraphFulfilmentRepository
    from app.graph.queries import checkout as q

    captured = {}
    class Result:
        def __init__(self, row): self.row = row
        def single(self): return self.row
    class Transaction:
        def run(self, query, **params):
            if query == q.NEXT_ORDER_NUMBER: return Result({'n': 1})
            if query == q.CREATE_ORDER:
                captured.update(params)
                return Result({'lines': 1})
            return Result({})
    class Graph:
        def transaction(self, work): return work(Transaction())
    cost = cost_block(50, 12.5)
    repo = GraphFulfilmentRepository(Graph())
    assert repo.create_order(key='test-key', user_id='user', actor={'id':'user','name':'Demo','role':'END_USER'},
        at='2026-10-22', today='2026-10-22', requester={}, receiver={}, shipto_id='ship', dealer_id='dealer', depot_id='depot',
        route_id='route', service_required=False, freight={'amount':12.5,'currency':'EUR'}, cost=cost,
        lines=[{'line_no':1,'part_id':'part','quantity':2,'unit_price_eur':25,'line_total_eur':50}]) == 'NM-ORD001'
    assert captured['cost'] == cost
    assert captured['lines'][0]['line_total_eur'] == 50
    assert 'part_cost: $cost.part_cost' in q.CREATE_ORDER

