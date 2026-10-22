"""Neo4j reader boundaries and proposed knowledge in the guided missing-domain path."""
import json
from app.knowledge_graph.neo4j import Neo4jKnowledgeRepository
from app.design_studio.knowledge.provider import LocalKnowledgeProvider
from app.knowledge_graph.provider import GraphKnowledgeProvider
from app.assistant import studio_agent
from app.design_studio.discovery import blank_definition
from app.schemas.application_definition import StudioFlow

class Reader:
    def __init__(self):
        self.local = LocalKnowledgeProvider()
    def documents(self, statuses):
        return [p.model_dump(mode='json') for p in self.local.packs() if p.status in statuses]
    def capability_documents(self):
        return [p.model_dump(mode='json') for p in self.local.capabilities()]






def test_missing_domain_uses_a_model_blueprint_without_a_questionnaire():
    class Model:
        def studio_json(self, system, prompt):
            context = json.loads(prompt)['specification']
            assert context['build_domain_blueprint'] is True
            assert 'PROJECT FOUNDATION' in system
            return {'reply': 'Proposed telescope scheduling design.', 'actions': [
                {'type': 'add_role', 'name': 'Observer', 'responsibilities': ['Reserve a telescope']},
                {'type': 'add_entity', 'name': 'Reservation', 'attributes': [{'name': 'Title', 'type': 'string', 'required': True, 'key': False}]},
                {'type': 'create_workflow', 'name': 'Reserve telescope', 'steps': [{'name': 'Book telescope', 'kind': 'form', 'role': 'Observer', 'writes': ['Reservation']}]}
            ], 'questions': [], 'ask': None}
    definition = blank_definition()
    definition.business.brief.goal = 'Create an astronomy observatory telescope reservation application'
    definition.studio_flow = StudioFlow(reviewed=['brief'])
    plan = studio_agent.run(Model(), 'Prepare this domain draft', [], None, definition, [], {}, LocalKnowledgeProvider(), None)
    assert plan.knowledge == {'generated_blueprint': True}
    assert {a.type for a in plan.actions} == {'add_role', 'add_entity', 'create_workflow'}
    assert not plan.questions
