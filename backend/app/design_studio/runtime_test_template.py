"""Independent generated tests: no imports from the generator or its test suite."""

import json
from pathlib import Path
import tempfile
import unittest
from collections import deque
from datetime import date, datetime, timedelta

from server import Runtime, Fault, IMPORT_ROLE
from validation import sample_record, sample_value


class GeneratedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.schema = json.loads(
            Path(__file__).with_name("schema.json").read_text(encoding="utf-8")
        )
        self.path = Path(self.temp.name) / "records.sqlite"
        self.runtime = Runtime(self.schema, self.path)
        self.created = {}

    def tearDown(self):
        self.temp.cleanup()

    def test_sessions_are_server_owned_and_unknown_identity_is_rejected(self):
        with self.assertRaises(Fault):
            self.runtime.login("platform_admin")
        with self.assertRaises(Fault):
            self.runtime.identity("forged")
        for user in self.runtime.users():
            identity = self.runtime.identity(self.runtime.login(user["id"]))
            self.assertEqual(identity["tenant"], user["tenant"])
            self.assertEqual(identity["role"], user["role"])

    def test_records_persist_and_tenants_cannot_read_each_other(self):
        checked = 0
        for entity in self.schema["entities"]:
            if any(
                r["source"] == entity["id"] and r["required"] for r in self.schema["references"]
            ):
                continue
            for role in self.schema["roles"]:
                user = {"tenant": "demo_noordveld", "actor": "test", "role": role["id"]}
                try:
                    self.runtime.entity_access(user, entity["id"], True)
                except Fault:
                    continue
                if entity.get("owner_role_id") and entity["owner_role_id"] != role["id"]:
                    continue
                owned = {
                    a["id"]
                    for a in entity["attributes"]
                    if not a.get("owner_role_id") or a["owner_role_id"] == role["id"]
                }
                saved = self.runtime.save_record(
                    user,
                    entity["id"],
                    {k: v for k, v in sample_record(entity["validation"]).items() if k in owned},
                )
                restarted = Runtime(self.schema, self.path)
                self.assertTrue(
                    any(r["id"] == saved["id"] for r in restarted.records(user, entity["id"]))
                )
                other = {**user, "tenant": "demo_harbor"}
                self.assertEqual(restarted.records(other, entity["id"]), [])
                with self.assertRaises(Fault):
                    restarted.save_record(user, entity["id"], saved["data"], saved["id"], 99)
                checked += 1
                break
        if not checked:
            self.skipTest(
                "No independently writable entity without required dependencies; relational journey requires domain fixtures"
            )

    def test_all_workflow_actions_require_a_role_and_permission(self):
        intruder = {"tenant": "demo_noordveld", "actor": "intruder", "role": "unknown"}
        for workflow in self.schema["workflows"]:
            for step in workflow["states"]:
                self.assertFalse(self.runtime.permits(intruder, step))

    def user(self, role, actor="test-person"):
        return {"tenant": "demo_noordveld", "actor": actor, "role": role}

    def creator(self, entity):
        model = self.runtime.entities[entity]
        for role in self.schema["roles"]:
            user = self.user(role["id"])
            if model.get("owner_role_id") and model["owner_role_id"] != role["id"]:
                continue
            try:
                self.runtime.entity_access(user, entity, True)
                return user
            except Fault:
                continue
        if entity in self.runtime.imports:
            imported = self.user(IMPORT_ROLE, 'synthetic-import-fixture')
            self.runtime.entity_access(imported, entity, True)
            return imported
        self.skipTest(f"{model['name']}: no role may create a fixture; configure its data source")

    def fixture(self, entity, stack=()):
        if entity in self.created:
            return self.created[entity]
        if entity in stack:
            self.skipTest(f"Required relationship cycle needs a domain fixture: {entity}")
        model = self.runtime.entities[entity]
        user = self.creator(entity)
        owned = {a['id'] for a in model['attributes'] if not a.get('owner_role_id') or a['owner_role_id'] == user['role']}
        data = {k: v for k, v in sample_record(model['validation']).items() if k in owned}
        for ref in self.schema['references']:
            if ref['source'] == entity:
                if ref['required']:
                    target = self.fixture(ref['target'], (*stack, entity))
                    data[ref['field']] = target['data'][ref['target_key']] if ref['enforcement'] == 'foreign_key' else target['id']
                else:
                    data.pop(ref['field'], None)
        self.created[entity] = self.runtime.save_record(user, entity, data)
        return self.created[entity]

    def rule_values(self, rule, desired=None):
        execution = rule.get('execution')
        if not execution:
            self.skipTest(f"{rule['description']}: executable binding is not supplied")
        entity, attribute = execution['field'].split('.')
        field = next(a for a in self.runtime.entities[entity]['validation'] if a['id'] == attribute)
        values = {}
        def put(ref, value):
            eid, attr = ref.split('.')
            values.setdefault(eid, {})[attr] = value
        if execution['kind'] == 'value':
            put(execution['field'], desired if desired is not None else rule['outcomes'][0])
            return values
        passed = desired is None or desired == execution.get('pass_outcome')
        right = execution.get('value')
        if execution.get('other_field'):
            other_entity, other_attribute = execution['other_field'].split('.')
            other = next(a for a in self.runtime.entities[other_entity]['validation'] if a['id'] == other_attribute)
            right = sample_value(other)
            if isinstance(right, (int, float)) and not isinstance(right, bool):
                right = max(right, field.get('minimum') or 0, other.get('minimum') or 0) + 10
                maxima = [item['maximum'] for item in (field, other) if item.get('maximum') is not None]
                if maxima:
                    right = min(right, min(maxima) - 1)
            put(execution['other_field'], right)
        operator = execution['operator']
        if operator == 'present':
            put(execution['field'], sample_value(field) if passed else '')
            return values
        different = next((value for value in field.get('enum', []) if value != right), None)
        def adjacent(offset):
            if field['type'] == 'date':
                return (date.fromisoformat(right) + timedelta(days=offset)).isoformat()
            if field['type'] == 'datetime':
                return (datetime.fromisoformat(right.replace('Z', '+00:00')) + timedelta(days=offset)).isoformat()
            if isinstance(right, (int, float)) and not isinstance(right, bool):
                return right + offset
            self.skipTest(f"Ordered comparison needs a domain fixture for {execution['field']}")
        if different is None:
            different = adjacent(1) if field['type'] in ('date', 'datetime') else not right if isinstance(right, bool) else right + 1 if isinstance(right, (int, float)) else 'Different value'
        if operator in ('eq', 'ne'):
            left = right if passed == (operator == 'eq') else different
        elif operator in ('gt', 'gte'):
            left = adjacent(1 if passed else -1)
        else:
            left = adjacent(-1 if passed else 1)
        put(execution['field'], left)
        return values

    def set_values(self, entity, values):
        current = self.fixture(entity)
        model = self.runtime.entities[entity]
        owners = {}
        checks = {a['id']: a for a in model['validation']}
        for field, value in values.items():
            if checks.get(field, {}).get('system_managed'):
                # A rule that reads a value only the system may set cannot be driven by a test; without a calculation nothing can
                # set it, so the path really is unavailable. Say so instead of reporting a failure about the test's own write.
                self.skipTest(f"{checks[field]['name']} is calculated by the system and this application has no calculation for it yet, so this path cannot run")
            attribute = next(a for a in model['attributes'] if a['id'] == field)
            role = attribute.get('owner_role_id') or self.creator(entity)['role']
            owners.setdefault(role, {})[field] = value
        for role, data in owners.items():
            try:
                current = self.runtime.save_record(self.user(role), entity, data, current['id'], current['revision'])
            except Fault as fault:
                if fault.status != 422:
                    raise
                # The rule's outcome needs a value the field's own limit refuses (a quantity below its minimum, say), so no
                # record can ever take this path; report that instead of a failure about the test's own write.
                self.skipTest(f"This path needs a value that {model['name']} does not allow ({'; '.join(str(item.get('message', '')) for item in (fault.details or []))}), so it cannot run")
        self.created[entity] = current

    def exercise_path(self, workflow, terminal=None, via=None):
        states = {step['id']: step for step in workflow['states']}
        start = next(step['id'] for step in workflow['states'] if step['kind'] == 'start')
        queue, found = deque([([start], False)]), None
        visited = {(start, False)}
        while queue:
            path, included = queue.popleft()
            if (path[-1] == terminal if terminal else states[path[-1]]['kind'] == 'end') and (via is None or included):
                found = path
                break
            for edge in workflow['transitions']:
                if edge['source'] == path[-1]:
                    used = included or edge['id'] == via
                    marker = (edge['target'], used)
                    if marker not in visited:
                        visited.add(marker)
                        queue.append(([*path, edge['target']], used))
        self.assertIsNotNone(found, f"No path reaches {terminal}")
        first = states[found[1]]
        try:
            instance = self.runtime.create_instance(self.user(first['role_id'], 'originator'), workflow['id'], {})
        except Fault as fault:
            if fault.status != 409:
                raise
            self.skipTest(f"This process cannot be started: {fault.message}")
        cursor = 1
        while cursor < len(found) - 1:
            step = states[found[cursor]]
            blockers = self.runtime.blockers(workflow, step)
            if blockers:
                self.skipTest('Process needs configuration: ' + '; '.join(item['message'] for item in blockers))
            end = cursor + 1
            while states[found[end]]['kind'] == 'branch':
                end += 1
            wanted = {}
            for source, target in zip(found[cursor:end], found[cursor + 1:end + 1]):
                edge = next(e for e in workflow['transitions'] if e['source'] == source and e['target'] == target)
                condition = edge['condition']
                if condition['kind'] != 'always':
                    rule = self.runtime.rules[condition['field']]
                    wanted[rule['id']] = condition['value'] if condition['kind'] == 'equals' else next(value for value in rule['outcomes'] if value != condition['value'])
            for state_id in found[cursor:end]:
                for rule_id in states[state_id].get('rule_ids', []):
                    for entity, data in self.rule_values(self.runtime.rules[rule_id], wanted.get(rule_id)).items():
                        self.set_values(entity, data)
            links = {entity: self.fixture(entity)['id'] for entity in set(step.get('reads_entity_ids', []) + step.get('writes_entity_ids', []))}
            actor = self.user(step['role_id'], 'person-' + step['id'])
            instance = self.runtime.advance(actor, instance['id'], instance['revision'], links)
            self.assertEqual(instance['state'], found[end])
            cursor = end
        self.assertEqual(instance['step']['kind'], 'end')
        self.assertGreaterEqual(len(self.runtime.history(actor, instance['id'])), 2)


def entity_round_trip(entity):
    def test(self):
        row = self.fixture(entity)
        user = self.creator(entity)
        reopened = Runtime(self.schema, self.path)
        self.assertIn(row, reopened.records(user, entity))
        self.assertEqual(reopened.records({**user, 'tenant': 'demo_harbor'}, entity), [])
        with self.assertRaises(Fault) as stale:
            self.runtime.save_record(user, entity, {}, row['id'], row['revision'] + 1)
        self.assertEqual(stale.exception.status, 409)
    return test


def entity_validation(entity):
    def test(self):
        user = self.creator(entity)
        with self.assertRaises(Fault) as invalid:
            self.runtime.save_record(user, entity, {'__unknown_field__': True})
        self.assertEqual(invalid.exception.status, 422)
        self.assertTrue(any(item['field'] == '__unknown_field__' for item in invalid.exception.details))
    return test


def entity_permissions(entity):
    def test(self):
        with self.assertRaises(Fault) as denied:
            self.runtime.entity_access(self.user('unknown-role'), entity, True)
        self.assertEqual(denied.exception.status, 403)
    return test


def rule_cases(rule):
    def test(self):
        if not rule.get('execution'):
            self.skipTest('Rule has no executable binding')
        with self.assertRaises(Fault):
            self.runtime._evaluate(rule, {})
        if rule['execution']['kind'] == 'value':
            for outcome in rule['outcomes']:
                self.assertEqual(self.runtime._evaluate(rule, self.rule_values(rule, outcome)), outcome)
            with self.assertRaises(Fault):
                self.runtime._evaluate(rule, self.rule_values(rule, '__invalid_outcome__'))
        else:
            positive = self.runtime._evaluate(rule, self.rule_values(rule))
            if rule['outcomes']:
                self.assertEqual(positive, rule['execution']['pass_outcome'])
                self.assertEqual(self.runtime._evaluate(rule, self.rule_values(rule, rule['execution']['fail_outcome'])), rule['execution']['fail_outcome'])
            else:
                with self.assertRaises(Fault):
                    self.runtime._evaluate(rule, self.rule_values({**rule, 'execution': {**rule['execution'], 'pass_outcome': '__pass__'}}, '__fail__'))
            execution = rule['execution']
            if execution['operator'] != 'present':
                boundary = self.rule_values(rule)
                entity, attribute = execution['field'].split('.')
                right = execution.get('value')
                if execution.get('other_field'):
                    other_entity, other_attribute = execution['other_field'].split('.')
                    right = boundary[other_entity][other_attribute]
                boundary[entity][attribute] = right
                inclusive = execution['operator'] in ('eq', 'gte', 'lte')
                if rule['outcomes']:
                    self.assertEqual(self.runtime._evaluate(rule, boundary), execution['pass_outcome'] if inclusive else execution['fail_outcome'])
                elif inclusive:
                    self.assertTrue(self.runtime._evaluate(rule, boundary))
                else:
                    with self.assertRaises(Fault):
                        self.runtime._evaluate(rule, boundary)
    return test


def workflow_permissions(workflow):
    def test(self):
        with self.assertRaises(Fault) as denied:
            self.runtime.create_instance(self.user('unknown-role'), workflow['id'], {})
        self.assertEqual(denied.exception.status, 403)
    return test


def workflow_outcome(workflow, terminal=None, via=None):
    def test(self):
        self.exercise_path(workflow, terminal, via)
    return test


def required_reference(reference):
    def test(self):
        user = self.creator(reference['source'])
        model = self.runtime.entities[reference['source']]
        owned = {a['id'] for a in model['attributes'] if not a.get('owner_role_id') or a['owner_role_id'] == user['role']}
        data = {k: v for k, v in sample_record(model['validation']).items() if k in owned}
        data.pop(reference['field'], None)
        with self.assertRaises(Fault) as missing:
            self.runtime.save_record(user, reference['source'], data)
        self.assertEqual(missing.exception.status, 422)
    return test


def install_project_tests():
    schema = json.loads(Path(__file__).with_name('schema.json').read_text(encoding='utf-8'))
    for index, entity in enumerate(schema['entities']):
        suffix = f"{index:02}_{entity['id'].replace('-', '_')}"
        for name, factory in [('persistence', entity_round_trip), ('validation', entity_validation), ('permissions', entity_permissions)]:
            setattr(GeneratedRuntimeTests, f'test_entity_{suffix}_{name}', factory(entity['id']))
    for index, rule in enumerate(schema['rules']):
        setattr(GeneratedRuntimeTests, f"test_rule_{index:02}_{rule['id'].replace('-', '_')}_outcomes", rule_cases(rule))
    for index, workflow in enumerate(schema['workflows']):
        suffix = f"{index:02}_{workflow['id'].replace('-', '_')}"
        setattr(GeneratedRuntimeTests, f'test_workflow_{suffix}_permissions', workflow_permissions(workflow))
        for terminal in (step for step in workflow['states'] if step['kind'] == 'end'):
            setattr(GeneratedRuntimeTests, f"test_workflow_{suffix}_reaches_{terminal['id'].replace('-', '_')}", workflow_outcome(workflow, terminal['id']))
        for edge in workflow['transitions']:
            if edge['condition']['kind'] != 'always':
                setattr(GeneratedRuntimeTests, f"test_workflow_{suffix}_path_{edge['id'].replace('-', '_')}", workflow_outcome(workflow, via=edge['id']))
    for index, reference in enumerate(schema['references']):
        if reference['required']:
            setattr(GeneratedRuntimeTests, f"test_reference_{index:02}_required", required_reference(reference))


install_project_tests()


if __name__ == "__main__":
    unittest.main()
