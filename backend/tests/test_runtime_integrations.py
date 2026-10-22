import importlib.util
import json
import time

import pytest

from tests.test_generated_runtime import generated, arrange, user


@pytest.fixture
def bridge(generated, monkeypatch):
    root, _, module = generated
    runtime, _, _, shipment = arrange(root, module)
    runtime.schema['integrations'] = [{'id': 'tracking', 'direction': 'bidirectional', 'entity_ids': ['ent_shipment']}]
    spec = importlib.util.spec_from_file_location('portable_bridge', root / 'runtime/integrations.py')
    exchange = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exchange)
    monkeypatch.setenv('TEST_EXCHANGE_KEY', 'x' * 40)
    config = {'id': 'tracking', 'enabled': True, 'tenant': 'demo_noordveld', 'role': 'role_planner', 'secret_env': 'TEST_EXCHANGE_KEY',
              'entities': {'ent_shipment': {'destination': 'destination'}}}
    gateway = exchange.IntegrationGateway(runtime, [config], module.Fault)
    return runtime, shipment, gateway, module, config


def request(gateway, body, method='POST', target='/api/integrations/tracking/records', stamp=None):
    raw = json.dumps(body).encode() if body is not None else b''
    stamp = str(stamp or int(time.time()))
    headers = {'X-Studio-Timestamp': stamp, 'X-Studio-Signature': gateway.signature(b'x' * 40, stamp, method, target, raw)}
    return lambda: gateway.exchange('tracking', method, target, headers, raw)


def test_atomic_idempotent_updates_and_scoped_snapshot_export(bridge):
    runtime, shipment, gateway, module, _ = bridge
    body = {'event_id': 'event-1', 'entity_id': 'ent_shipment', 'record_id': shipment['id'], 'expected_revision': 1, 'data': {'destination': 'Amsterdam'}}
    result = request(gateway, body)()
    assert result['revision'] == 2 and 'data' not in result
    assert request(gateway, body)() == result
    with pytest.raises(module.Fault) as conflict:
        request(gateway, {**body, 'data': {'destination': 'Changed'}})()
    assert conflict.value.status == 409
    exported = request(gateway, None, 'GET', '/api/integrations/tracking/records?entity_id=ent_shipment&after=0')()
    assert exported['records'] == [{'record_id': shipment['id'], 'revision': 2, 'data': {'destination': 'Amsterdam'}}]
    assert runtime.records(user('planner', 'demo_harbor'), 'ent_shipment') == []
    events = runtime.record_history(user('planner'), 'ent_shipment', shipment['id'])
    assert sum(e['action'] == 'integration.receive' for e in events) == 1











