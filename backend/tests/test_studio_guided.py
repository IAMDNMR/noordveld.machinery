from pathlib import Path
from tempfile import TemporaryDirectory
import pytest
from fastapi.testclient import TestClient
from app.design_studio.local_app import create_local_app
from app.design_studio.discovery import blank_definition
from app.design_studio.approval import digest
from app.schemas.application_definition import StudioFlow
from tests.support.frontend import enable_frontend_fixture, generate_for_review
from tests.support.studio_model import FoundationModel

@pytest.fixture
def journey(monkeypatch):
    enable_frontend_fixture(monkeypatch)
    monkeypatch.setenv('DESIGN_KNOWLEDGE_SOURCE', 'local')
    monkeypatch.setenv('DESIGN_STUDIO_LOCAL_DEV', '1')
    monkeypatch.setenv('APP_ENV', 'local')
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.delenv('VERCEL_ENV', raising=False)
    monkeypatch.setattr('app.api.routes.studio_conversation.get_studio_llm', FoundationModel)
    with TemporaryDirectory(prefix='noordveld-studio-') as root:
        with TestClient(create_local_app(Path(root) / 'studio.sqlite')) as c:
            c.post('/api/v1/auth/login', json={'user_id': 'studio-alice'})
            p = c.post('/api/v1/design-studio/projects', json=blank_definition().model_dump(mode='json')).json()
            url = f"/api/v1/design-studio/projects/{p['id']}/studio"
            result = c.post(url + '/turn', json={'guided': True, 'expected_revision': p['revision'], 'message': 'Build a transport management system for transport requests and deliveries.'})
            assert result.status_code == 200, result.text
            yield c, url, result.json()['state']


def test_serial_review_reload_and_conflicts(journey):
    c, url, state = journey
    assert state['flow'] == {'active': 'brief', 'reviewed': [], 'ready': True}
    assert not state['definition']['workflow_definitions']
    assert state['questions'] == []
    assert c.get(url + '/state').json()['flow'] == state['flow']
    assert c.post(url + '/continue', json={'expected_revision': state['revision'], 'stage': 'knowledge'}).status_code == 409
    original = state['revision']
    for stage, expected in [('brief', 'knowledge'), ('knowledge', 'workflow'), ('workflow', 'data'), ('data', 'screen'), ('screen', 'rules'), ('rules', 'roles'), ('roles', 'checks')]:
        if stage == 'screen':
            state = generate_for_review(c, url, state)
        result = c.post(url + '/continue', json={'expected_revision': state['revision'], 'stage': stage})
        assert result.status_code == 200, result.text
        state = result.json()['state']
        assert state['flow']['active'] == expected
        # Screens are ready from the process itself; only Validation waits for approvals.
        assert state['flow']['ready'] == (expected != 'checks'), result.json()['turn']
        assert result.json()['turn']['proposal'] is None
        assert state['stages']['export']['status'] == 'not_started'
    assert c.post(url + '/continue', json={'expected_revision': state['revision'], 'stage': 'checks'}).status_code == 409
    assert state['approval']['process']['state'] == 'none'
    overview = c.get("/api/v1/design-studio/project-dashboard").json()
    assert overview["counts"]["reviewed"] == 1
    assert overview["counts"]["approved"] == 0
    assert overview["projects"][0]["design_reviewed"] is True
    assert c.post(url + '/continue', json={'expected_revision': original, 'stage': 'brief'}).status_code == 409


def test_a_typed_question_gets_the_assistants_own_answer_not_the_fixed_ready_sentence(journey, monkeypatch):
    c, url, state = journey

    class Answering(FoundationModel):
        def studio_json(self, system, prompt):
            assert 'HOW TO TALK WITH THE PERSON' in system  # the guided assistant is told to answer, ask one clear question, or say what it cannot do
            return {'reply': 'Nothing is needed from you except to review the requirements.', 'actions': [], 'questions': [], 'ask': None}

    monkeypatch.setattr('app.api.routes.studio_conversation.get_studio_llm', Answering)
    asked = c.post(url + '/turn', json={'guided': True, 'expected_revision': state['revision'], 'message': 'what do you want from me?'})
    assert asked.status_code == 200, asked.text
    reply = asked.json()['turn']['reply']
    assert 'Nothing is needed from you' in reply and 'draft is ready to review' not in reply
    # The automatic drafting of a stage (no typed message) still ends with the fixed invitation to review.
    drafted = c.post(url + '/continue', json={'expected_revision': asked.json()['state']['revision'], 'stage': 'brief'})
    assert drafted.status_code == 200, drafted.text










def test_validation_repairs_are_proposed_together_without_reopening_reviewed_stages(journey, monkeypatch):
    from app.assistant import studio_agent
    from app.assistant.studio_actions import LinkRequirement, apply_actions, parse_actions
    from app.design_studio.knowledge.provider import LocalKnowledgeProvider
    from app.design_studio.stages import STAGES
    c, url, state = journey
    for stage, _ in STAGES[:7]:
        if stage == 'screen':
            state = generate_for_review(c, url, state)
        response = c.post(url + '/continue', json={'expected_revision': state['revision'], 'stage': stage})
        assert response.status_code == 200, response.text
        state = response.json()['state']
    from app.schemas.application_definition import ApplicationDefinition
    definition = ApplicationDefinition.model_validate(state['definition'])
    step = next(s for w in definition.workflow_definitions for s in w.states if s.kind not in ('start', 'end'))
    requirement = next(r for r in definition.business.requirements if r.id not in step.requirement_ids)
    created = state['definition']
    monkeypatch.setattr(studio_agent, 'run', lambda *args, **kwargs: studio_agent.Plan(reply='Repair draft', actions=[LinkRequirement(type='link_requirement', requirement=requirement.id, step=step.id)]))
    result = c.post(url + '/turn', json={'guided': True, 'stage': 'checks', 'expected_revision': created['revision'], 'message': 'Repair all design gaps'})
    assert result.status_code == 200, result.text
    turn = result.json()['turn']
    assert turn['proposal'] is not None
    assert not turn['applied']
    assert result.json()['state']['revision'] == created['revision']
    assert result.json()['state']['flow']['active'] == 'checks'
    assert result.json()['state']['flow']['reviewed'] == state['flow']['reviewed']
    proposal = turn['proposal']
    applied = c.post(url + '/apply', json={
        'expected_revision': created['revision'], 'base_sha256': proposal['base_sha256'],
        'candidate_sha256': proposal['candidate_sha256'], 'actions': proposal['actions'],
    })
    assert applied.status_code == 200, applied.text
    repaired_state = c.get(url + '/state').json()
    repaired = repaired_state['definition']
    assert requirement.id in next(s for w in repaired['workflow_definitions'] for s in w['states'] if s['id'] == step.id)['requirement_ids']
    assert not repaired['approvals']
    assert repaired_state['flow']['active'] == 'workflow'
    assert repaired_state['flow']['reviewed'] == ['brief', 'knowledge']


def test_step_insertion_persists_and_rule_confirmation_still_requires_review(journey):
    c, url, state = journey
    locked = c.post(url + '/act', json={'expected_revision': state['revision'], 'actions': [{
        'type': 'confirm_rule', 'rule': 'future_rule', 'source': {'kind': 'document', 'reference': 'QA'},
    }]})
    assert locked.status_code == 409 and 'stage_action_unavailable' in locked.text
    for stage in ('brief', 'knowledge'):
        response = c.post(url + '/continue', json={'expected_revision': state['revision'], 'stage': stage})
        assert response.status_code == 200, response.text
        state = response.json()['state']
    workflow = state['definition']['workflow_definitions'][0]
    anchor = next(step for step in workflow['states'] if step['kind'] not in ('start', 'end'))
    route = next(edge for edge in workflow['transitions'] if edge['source'] == anchor['id'])
    response = c.post(url + '/act', json={'expected_revision': state['revision'], 'actions': [{
        'type': 'insert_step', 'workflow': workflow['id'], 'after': anchor['id'], 'transition_id': route['id'],
        'step': {'name': 'QA check selected path', 'kind': 'review', 'role': state['definition']['business']['roles'][0]['name']},
    }]})
    assert response.status_code == 200, response.text
    saved = c.get(url + '/state').json()
    assert saved['revision'] > state['revision']
    steps = saved['definition']['workflow_definitions'][0]['states']
    assert any(step['label'] == 'QA check selected path' for step in steps)
    for stage in ('workflow', 'data', 'screen'):
        if stage == 'screen':
            saved = generate_for_review(c, url, saved)
        response = c.post(url + '/continue', json={'expected_revision': saved['revision'], 'stage': stage})
        assert response.status_code == 200, response.text
        saved = response.json()['state']
    # A rule confirmation test needs an explicitly supplied policy, not a model-invented one.
    supplied = c.post(url + '/act', json={'expected_revision': saved['revision'], 'actions': [{
        'type': 'add_rule', 'description': 'A QA fixture shipment needs coordinator review.',
    }]})
    assert supplied.status_code == 200, supplied.text
    saved = supplied.json()['state']
    rule = saved['definition']['business']['rules'][0]
    response = c.post(url + '/act', json={'expected_revision': saved['revision'], 'actions': [{
        'type': 'confirm_rule', 'rule': rule['id'], 'source': {'kind': 'document', 'reference': 'Isolated QA policy fixture'},
    }]})
    assert response.status_code == 200, response.text
    proposal = response.json()['turn']['proposal']
    assert proposal and response.json()['state']['revision'] == saved['revision'], response.json()['turn']
    assert c.get(url + '/state').json()['definition']['business']['rules'][0]['status'] == rule['status']
    applied = c.post(url + '/apply', json={
        'expected_revision': saved['revision'], 'base_sha256': proposal['base_sha256'],
        'candidate_sha256': proposal['candidate_sha256'], 'actions': proposal['actions'],
    })
    assert applied.status_code == 200, applied.text
    assert c.get(url + '/state').json()['definition']['business']['rules'][0]['status'] == 'confirmed'
    current = c.get(url + '/state').json()
    revised = c.post(url + '/act', json={'expected_revision': current['revision'], 'actions': [{
        'type': 'insert_step', 'workflow': workflow['id'], 'after': anchor['id'], 'transition_id': route['id'],
        'step': {'name': 'QA revision from a later stage', 'kind': 'review', 'role': current['definition']['business']['roles'][0]['name']},
    }]})
    assert revised.status_code == 200, revised.text
    reopened = c.get(url + '/state').json()
    assert reopened['flow']['active'] == 'workflow'
    assert any(step['label'] == 'QA revision from a later stage' for step in reopened['definition']['workflow_definitions'][0]['states'])
