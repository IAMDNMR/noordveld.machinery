"""Record identity and relationship links must remain independent in every domain."""
from app.design_studio.compiler import references
from app.design_studio.discovery import blank_definition
from app.schemas.application_definition import ApplicationDefinition


def documents(explicit=False):
    raw = blank_definition().model_dump(mode='json')
    raw['business']['entities'] = [
        {'id': 'ent_parent', 'name': 'Parent document', 'attributes': [
            {'id':'number','name':'Number','type':'string','key':True,'required':True}
        ]},
        {'id': 'ent_child', 'name': 'Child document', 'attributes': [
            {'id':'number','name':'Number','type':'string','key':True,'required':True,
             'reference': {'entity_id':'ent_parent','attribute_id':'number'} if explicit else None}
        ],'relationships':[{'id':'rel_parent','name':'Parent','target':'ent_parent','cardinality':'many_to_one','required':False}]}
    ]
    return ApplicationDefinition.model_validate(raw)


def test_generic_document_number_is_not_inferred_as_its_parent_reference():
    refs, collections = references(documents())
    assert refs[0].field == 'rel_parent'
    assert refs[0].enforcement == 'link'
    assert collections[0].via == 'rel_parent'


def test_explicit_shared_key_reference_is_retained():
    refs, _ = references(documents(explicit=True))
    assert refs[0].field == 'number'
    assert refs[0].enforcement == 'foreign_key'


def test_distinct_parent_key_attribute_still_binds_as_foreign_key():
    raw=documents().model_dump(mode='json')
    raw['business']['entities'][0]['attributes'][0]['id']='parent_number'
    raw['business']['entities'][1]['attributes'].append({'id':'parent_number','name':'Parent number','type':'string'})
    refs, _=references(ApplicationDefinition.model_validate(raw))
    assert refs[0].field == 'parent_number'
    assert refs[0].enforcement == 'foreign_key'
