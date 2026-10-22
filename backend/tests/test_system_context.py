import json

import pytest

from app.assistant.studio_actions import SetIntakeContext, apply_actions
from app.design_studio.discovery import blank_definition
from app.design_studio.knowledge.provider import LocalKnowledgeProvider, apply_pack, identify_domains
from app.design_studio.knowledge.system_context import discovery_context, load_catalog, validate_catalog, region_in_text








def test_model_context_carries_only_the_persons_setup_choices():
    from app.assistant.studio_agent import build_context
    from app.design_studio.stages import compute
    from app.design_studio.completeness import analyze
    provider = LocalKnowledgeProvider()
    definition, _ = apply_pack(blank_definition(), 'cat_transport', provider)
    definition, _, rejected = apply_actions(definition, [SetIntakeContext(type='set_intake_context', region='eu', skip=['industry'])], provider)
    assert not rejected
    analysis = analyze(definition, provider, 'design')
    context = build_context(definition, [], compute(definition, analysis, []), [], provider.domains(), None, provider)
    selection = context['setup_choices']
    assert selection['region'] == 'eu' and selection['industry_id'] is None and selection['skipped'] == ['industry']
    assert 'industry_system_context' not in context and 'vendor_process_references' not in context, "only the person's own choices reach the model, not unverified catalogues"
