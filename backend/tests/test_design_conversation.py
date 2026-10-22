"""Actual local HTTP journey, isolated SQLite and synthetic TMS; no providers."""
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from app.design_studio.local_app import create_local_app
from app.design_studio.approval import digest
from app.design_studio.discovery import blank_definition
from app.design_studio.knowledge.provider import LocalKnowledgeProvider, apply_pack

API = '/api/v1/design-studio/projects'


@pytest.fixture
def journey(monkeypatch):
    monkeypatch.setenv('DESIGN_STUDIO_LOCAL_DEV', '1')
    monkeypatch.setenv('APP_ENV', 'local')
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.delenv('VERCEL_ENV', raising=False)
    with TemporaryDirectory(prefix='noordveld-studio-') as root:
        with TestClient(create_local_app(Path(root) / 'studio.sqlite')) as client:
            client.post('/api/v1/auth/login', json={'user_id': 'studio-alice'})
            definition, _ = apply_pack(blank_definition(), 'noordveld_transport', LocalKnowledgeProvider())
            response = client.post(API, json=definition.model_dump(mode='json'))
            assert response.status_code == 200, response.text
            project = response.json()
            url = f"{API}/{project['id']}/assistant"
            context = client.get(url + '/context').json()
            body = {'message': 'rename step tl_dispatch to Dispatch prepared shipment',
                    'expected_revision': project['revision'], 'base_sha256': context['base_sha256']}
            yield client, url, body


def test_review_apply_revision_and_replay(journey):
    client, url, body = journey
    before = client.get(url.removesuffix('/assistant')).json()
    proposed = client.post(url, json=body)
    assert proposed.status_code == 200, proposed.text
    proposal = proposed.json()
    assert proposal['state'] == 'proposed' and proposal['evidence']
    assert proposal['validation']['blocking']  # unresolved company decisions remain visible
    assert client.get(url.removesuffix('/assistant')).json() == before
    apply = {**body, 'candidate_sha256': proposal['candidate_sha256']}
    assert client.post(url + '/apply', json={**apply, 'candidate_sha256': '0' * 64}).status_code == 409
    saved = client.post(url + '/apply', json=apply)
    assert saved.status_code == 200, saved.text
    assert saved.json()['revision'] == 2
    assert saved.json()['business'] == before['business']
    assert client.post(url + '/apply', json=apply).status_code == 409
    history = client.get(url.removesuffix('/assistant') + '/history').json()
    assert len(history) == 2 and history[0] == before
    audit = client.get(url.removesuffix('/assistant') + '/audit').json()
    assert 'assistant:apply' in str(audit)








