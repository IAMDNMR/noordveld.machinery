"""Verify executable output, not filenames: export, load standalone runtime, persist and execute TMS."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.design_studio.compiler import compile_project, update_plan
from app.design_studio.runtime_demo import synthetic_transport
from app.design_studio.knowledge.provider import LocalKnowledgeProvider
from app.domain_knowledge.store import ReadOnlyDomainStore
from tests.support.frontend import with_frontend


@pytest.fixture
def generated(tmp_path):
    compiled = compile_project(with_frontend(synthetic_transport()), ReadOnlyDomainStore(), LocalKnowledgeProvider())
    assert compiled['status'] == 'generated', compiled['plan']
    for name, content in compiled['files'].items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    spec = importlib.util.spec_from_file_location('validation', tmp_path / 'runtime/validation.py')
    validation = importlib.util.module_from_spec(spec)
    previous = sys.modules.get('validation')
    sys.modules['validation'] = validation
    spec.loader.exec_module(validation)
    spec = importlib.util.spec_from_file_location('isolated_generated_server', tmp_path / 'runtime/server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        yield tmp_path, compiled, module
    finally:
        if previous is None:
            sys.modules.pop('validation', None)
        else:
            sys.modules['validation'] = previous


def user(role, tenant='demo_noordveld'):
    return {'tenant': tenant, 'role': 'role_' + role, 'actor': tenant + ':' + role}


def arrange(root, module):
    schema = json.loads((root / 'runtime/schema.json').read_text())
    runtime = module.Runtime(schema, root / 'operations.sqlite')
    planner = user('planner')
    carrier = runtime.save_record(planner, 'ent_carrier', {'carrier_code': 'C001', 'name': 'Synthetic Logistics', 'eligible': True})
    vehicle = runtime.save_record(planner, 'ent_vehicle', {'vehicle_code': 'V001', 'capacity_kg': 1000})
    shipment = runtime.save_record(planner, 'ent_shipment', {'shipment_code': 'S001', 'destination': 'Rotterdam', 'weight_kg': 500, 'carrier_code': 'C001', 'vehicle_code': 'V001', 'route': 'Test route'})
    return runtime, carrier, vehicle, shipment


def test_exported_runtime_independent_tests_and_syntax(generated):
    root, compiled, _ = generated
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'runtime', '-p', 'test_runtime.py', '-v'], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    schema = json.loads((root / 'runtime/schema.json').read_text())
    expected = (3 + 3 * len(schema['entities']) + len(schema['rules'])
                + sum(1 + sum(step['kind'] == 'end' for step in workflow['states'])
                      + sum(edge['condition']['kind'] != 'always' for edge in workflow['transitions'])
                      for workflow in schema['workflows'])
                + sum(ref['required'] for ref in schema['references']))
    assert f'Ran {expected} tests' in result.stderr and 'OK' in result.stderr
    assert 'skipped' not in result.stderr
    for category in ('test_entity_', 'test_rule_', 'test_workflow_'):
        assert category in result.stderr
    import shutil
    node = shutil.which('node')
    assert node
    result = subprocess.run([node, '--check', str(root / 'runtime/app.js')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert compiled['manifest']['files']['runtime/server.py']['kind'] == 'executable'
    plan = update_plan(compiled['manifest'], {'runtime/app.js': 'user-edited'}, compiled['files'])
    assert 'runtime/app.js' in str(plan) and 'conflict' in str(plan)




def test_real_transport_lifecycle_persists_and_enforces_permissions(generated):
    root, _, module = generated
    runtime, carrier, vehicle, shipment = arrange(root, module)
    planner, warehouse, dispatcher, partner = (user(role) for role in ('planner', 'warehouse', 'dispatcher', 'carrier'))
    instance = runtime.create_instance(planner, 'wf_transport', {'ent_shipment': shipment['id']})
    with pytest.raises(module.Fault) as denied:
        runtime.advance(dispatcher, instance['id'], 1, {})
    assert denied.value.status == 403
    instance = runtime.advance(planner, instance['id'], 1, {})
    assert instance['state'] == 'st_plan'
    with pytest.raises(module.Fault) as missing:
        runtime.advance(planner, instance['id'], 2, {})
    assert missing.value.status == 422
    instance = runtime.advance(planner, instance['id'], 2, {'ent_carrier': carrier['id'], 'ent_vehicle': vehicle['id']})
    assert instance['state'] == 'st_handoff'
    with pytest.raises(module.Fault):
        runtime.advance(warehouse, instance['id'], 3, {})
    with pytest.raises(module.Fault) as forged:
        runtime.save_record(dispatcher, 'ent_shipment', {'warehouse_ready': True}, shipment['id'], 1)
    assert forged.value.status == 403
    shipment = runtime.save_record(warehouse, 'ent_shipment', {'warehouse_ready': True}, shipment['id'], 1)
    instance = runtime.advance(warehouse, instance['id'], 3, {})
    assert instance['state'] == 'st_dispatch'
    instance = runtime.advance(dispatcher, instance['id'], 4, {})
    shipment = runtime.save_record(dispatcher, 'ent_shipment', {'tracking_status': 'DELIVERED'}, shipment['id'], shipment['revision'])
    instance = runtime.advance(dispatcher, instance['id'], 5, {})
    assert instance['state'] == 'st_pod'
    with pytest.raises(module.Fault):
        runtime.advance(partner, instance['id'], 6, {})
    shipment = runtime.save_record(partner, 'ent_shipment', {'received_by': 'Synthetic Receiver', 'pod_reference': 'POD-001'}, shipment['id'], shipment['revision'])
    instance = runtime.advance(partner, instance['id'], 6, {})
    assert instance['state'] == 'st_delivered'
    restarted = module.Runtime(runtime.schema, root / 'operations.sqlite')
    assert restarted.instance(dispatcher, instance['id'])['state'] == 'st_delivered'
    assert restarted.records(partner, 'ent_shipment')[0]['data']['pod_reference'] == 'POD-001'
    assert len(restarted.history(dispatcher, instance['id'])) == 7
    with pytest.raises(module.Fault):
        restarted.instance(user('dispatcher', 'demo_harbor'), instance['id'])
    assert restarted.records(user('dispatcher', 'demo_harbor'), 'ent_shipment') == []






def test_unimplemented_rules_and_changed_specification_fail_closed(generated):
    root, _, module = generated
    runtime, carrier, vehicle, shipment = arrange(root, module)
    instance = runtime.create_instance(user('planner'), 'wf_transport', {'ent_shipment': shipment['id']})
    step = next(s for s in runtime.workflows['wf_transport']['states'] if s['id'] == instance['state'])
    step['preconditions'] = ['Business owner must confirm eligibility']
    with pytest.raises(module.Fault) as prose:
        runtime.advance(user('planner'), instance['id'], 1, {})
    assert prose.value.status == 409
    assert runtime.instance(user('planner'), instance['id'])['revision'] == 1
    step['preconditions'] = []
    runtime.advance(user('planner'), instance['id'], 1, {})
    runtime.rules['rule_route']['execution'] = None
    with pytest.raises(module.Fault) as unsupported:
        runtime.advance(user('planner'), instance['id'], 2, {'ent_carrier': carrier['id'], 'ent_vehicle': vehicle['id']})
    assert unsupported.value.status == 409
    assert runtime.instance(user('planner'), instance['id'])['revision'] == 2
    with pytest.raises(module.Fault):
        module.Runtime({**runtime.schema, 'fingerprint': 'different'}, root / 'operations.sqlite')


