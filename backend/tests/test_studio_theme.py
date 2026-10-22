from app.assistant.studio_actions import parse_actions, apply_actions
from app.design_studio.discovery import blank_definition
from app.design_studio.knowledge.provider import LocalKnowledgeProvider
from app.design_studio.runtime_generation import presentation


def test_colour_change_is_validated_and_does_not_change_business_content():
    original=blank_definition()
    actions, invalid=parse_actions([{'type':'set_theme','primary':'#245F8B'}])
    assert not invalid
    updated, changes, rejected=apply_actions(original,actions,LocalKnowledgeProvider())
    assert not rejected and len(changes)==1
    assert updated.theme.primary=='#245f8b'
    assert updated.business==original.business
    assert updated.workflow_definitions==original.workflow_definitions
    assert presentation(updated)['tokens']['--accent']=='#245f8b'


def test_theme_rejects_css_and_handles_light_colours_with_dark_text():
    actions, invalid=parse_actions([{'type':'set_theme','primary':'red;display:none'}])
    assert not actions and invalid
    d=blank_definition()
    d.theme.primary='#ffffff'
    assert presentation(d)['tokens']['--accent-ink']=='#14181a'
    d.theme.primary='#24583e'
    assert presentation(d)['tokens']['--accent-ink']=='#ffffff'
