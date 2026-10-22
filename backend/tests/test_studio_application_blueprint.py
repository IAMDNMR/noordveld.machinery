"""Cross-domain application inventories and honest page-planning contracts."""
from copy import deepcopy

import pytest

from app.design_studio.application_blueprint import application_blueprint, plan_gaps
from app.design_studio.discovery import blank_definition
from app.design_studio.knowledge.provider import LocalKnowledgeProvider, apply_pack
from app.design_studio.templates import visual_references
from app.schemas.generated_frontend import FrontendProposal
from app.design_studio.traceability import report


@pytest.mark.parametrize('packs', [
    ['cat_aftersales_warranty'], ['cat_transport'], ['cat_warehouse'],
    ['cat_procurement', 'cat_inventory'], ['cat_ecommerce'],
])
def test_contract_inventory_covers_tasks_records_and_related_data_without_template(packs):
    definition = blank_definition()
    provider = LocalKnowledgeProvider()
    for pack in packs:
        definition, _ = apply_pack(definition, pack, provider)
    inventory = application_blueprint(definition)
    assert inventory['modules']
    assert len({s['id'] for s in inventory['surfaces']}) == len(inventory['surfaces'])
    tasks = [s for s in inventory['surfaces'] if s['kind'] == 'task']
    assert tasks
    used = {e for s in tasks for e in s['entity_ids']}
    lists = {s['entity_ids'][0] for s in inventory['surfaces'] if s['kind'] == 'list'}
    details = {s['entity_ids'][0] for s in inventory['surfaces'] if s['kind'] == 'detail'}
    assert used <= lists == details
    plan = FrontendProposal.model_validate({
        'design_summary': 'A complete inventory for the test application.',
        'pages': [{'id': 'workspace', 'title': 'Workspace', 'purpose': 'Task and record panels',
                   'step_ids': [ref for s in tasks for ref in s['step_ids']],
                   'entity_ids': list(lists), 'surface_ids': [s['id'] for s in inventory['surfaces']]}],
        'files': {'src/App.tsx': 'plan', 'src/styles.css': 'plan'},
    })
    assert plan_gaps(plan, definition) == []
    missing = plan.model_copy(deep=True)
    missing.pages[0].surface_ids = [s['id'] for s in tasks]
    assert 'omit application surfaces' in ';'.join(plan_gaps(missing, definition))
    mismatched = plan.model_copy(deep=True)
    mismatched.pages[0].entity_ids = []
    assert 'does not bind' in ';'.join(plan_gaps(mismatched, definition))
    before = deepcopy(definition.model_dump(mode='json'))
    visual_references(definition)
    assert definition.model_dump(mode='json') == before


def test_unlinked_requirement_is_visible_as_needing_design():
    definition = blank_definition()
    from app.schemas.application_definition import Requirement
    definition.business.requirements.append(Requirement(id='req_report', statement='Reporting by region', priority='must', status='draft'))
    item = application_blueprint(definition)['requirements'][0]
    assert item['status'] == 'needs_design' and item['resolution']


def test_model_pages_are_in_traceability_but_not_claimed_as_behavior_tests():
    definition, _ = apply_pack(blank_definition(), 'cat_transport', LocalKnowledgeProvider())
    from app.schemas.generated_frontend import GeneratedFrontend
    definition.generated_frontend = GeneratedFrontend(
        design_summary='Transport task workspace for the saved process.',
        pages=[{'id': 'transport', 'title': 'Transport', 'purpose': 'Plan and deliver',
                'step_ids': [f'{w.id}/{s.id}' for w in definition.workflow_definitions for s in w.states],
                'entity_ids': [e.id for e in definition.business.entities]}],
        files={'src/App.tsx':'source', 'src/styles.css':'style'}, input_sha256='0'*64,
        source_sha256='1'*64, provider='test', generated_at='test', bundle_js='test',
        bundle_css='', checks=[], sdk_source='', entry_source='',
    )
    evidence = report(definition)
    assert not evidence['steps_without_screens']
    assert evidence['screen_evidence'] == 'declared_frontend_bindings'
    assert evidence['behavior_validated'] is False
    assert any(row['screens'] == ['transport'] for row in evidence['requirements'])


def test_baseline_preview_allows_isolated_scripts_and_escapes_business_text():
    import base64
    import re
    from app.design_studio.runtime_generation import preview_document

    definition = blank_definition()
    definition.metadata.name = 'Test </script><script>alert(1)</script>'
    document = preview_document(definition)
    assert "script-src &#x27;unsafe-inline&#x27;" in document
    assert 'sandbox="allow-scripts"' in document and 'allow-same-origin' not in document
    inner = base64.b64decode(re.search(r'base64,([^\"]+)', document)[1]).decode()
    bootstrap = inner.split('id="studio-bootstrap" type="application/json">')[1].split('</script>')[0]
    assert '\\u003c/script>' in bootstrap and '<script>' not in bootstrap


def test_page_and_module_counts_are_not_limited_by_a_visual_template():
    proposal = FrontendProposal.model_validate({
        'design_summary': 'Large application with independently planned modules.',
        'pages': [{'id': f'page_{i}', 'title': f'Page {i}', 'purpose': 'Distinct business work'} for i in range(45)],
        'files': {f'src/Page{i}.tsx': 'implementation instructions' for i in range(30)},
    })
    assert len(proposal.pages) == 45 and len(proposal.files) == 30


def test_existing_automated_steps_can_be_explained_without_fabricating_a_task():
    definition, _ = apply_pack(blank_definition(), 'cat_transport', LocalKnowledgeProvider())
    context = next((w, s) for w in definition.workflow_definitions for s in w.states if s.kind == 'start')
    workflow, state = context
    plan = FrontendProposal.model_validate({
        'design_summary': 'Context for an existing automated process boundary.',
        'pages': [{'id': 'context', 'title': 'Process', 'purpose': 'Explain the process',
                   'step_ids': [f'{workflow.id}/{state.id}'], 'entity_ids': [],
                   'surface_ids': [f'task:{workflow.id}/{state.id}']}],
        'files': {'src/App.tsx': 'plan', 'src/styles.css': 'plan'},
    })
    assert 'Unknown application surface' not in ';'.join(plan_gaps(plan, definition))
    plan.pages[0].surface_ids.append('task:invented/not_real')
    assert 'Unknown application surface' in ';'.join(plan_gaps(plan, definition))


def test_conversational_visual_edit_is_a_rebuild_request_not_a_business_mutation():
    from app.assistant.studio_agent import plan_with_model
    class VisualModel:
        def studio_json(self, system, prompt):
            assert 'design_frontend' in system
            return {'reply': 'I will update the appearance.', 'actions': [], 'command': 'design_frontend', 'focus': 'screens'}
    plan = plan_with_model(VisualModel(), 'Use a navy theme and a split approval workspace', [], None, {})
    assert plan.command == 'design_frontend' and plan.focus == 'screen'
    assert plan.actions == []
