"""Explicit, reviewed UI field selections for catalog workflows. Never permission grants.

Each entry maps a state ID to entity IDs, editable attribute IDs, and relationship
suffixes. These are task design choices, not inferred from labels at runtime.
"""
VERSION = '2026.10.19'
CONTRACTS = {}
PERMISSIONS = {
    'order_part_issue': 'parts.read', 'order_fitment_issue': 'parts.read',
    'order_details_issue': 'orders.place', 'order_availability_issue': 'orders.place',
    'tl_no_carrier': 'transport.plan.write', 'tl_capacity_issue': 'transport.plan.write',
    'tl_wait_goods': 'transport.dispatch', 'tl_pod_issue': 'exception.resolve',
    'tl_delay_issue': 'exception.resolve', 'wh_stock_issue': 'stock.adjust',
    'wh_incomplete_issue': 'pick.execute',
}


def group(prefix, entity, entries):
    for step, fields, relations in entries:
        CONTRACTS[prefix + step] = {entity: (fields.split(), relations.split())}


group('st_apr_approval_', 'ent_apr_request', [('submit','subject reason amount requested_on',''),('decide','decision decision_note','')])
group('st_doc_register_', 'ent_doc_document', [('register','title kind reference linked_to valid_until',''),('publish','status','')])
group('st_task_lifecycle_', 'ent_task_task', [('create','title description priority due_date',''),('assign','assignee due_date',''),('work','status','')])
group('st_inv_count_', 'ent_inv_stock_count', [('count','counted_qty counted_on variance reason','stock_level'),('approve','decision',''),('recount','counted_qty counted_on variance reason','')])
CONTRACTS['st_inv_count_post'] = {'ent_inv_stock_level': ('on_hand'.split(), []), 'ent_inv_stock_movement': ('kind quantity moved_on'.split(), ['item','location'])}
group('st_mfg_work_order_', 'ent_mfg_work_order', [('plan','kind description planned_start planned_hours status','machine'),('expedite','planned_start description',''),('execute','status',''),('inspect','inspection_result',''),('rework','rework_note status',''),('close','status','')])
group('st_svc_case_', 'ent_svc_service_case', [('log','description priority opened_on service_date status','customer machine'),('triage','priority description',''),('quote','description',''),('close','status','')])
CONTRACTS['st_svc_case_claim']={'ent_svc_warranty_claim':(['claim_amount','decision','note'],['service_case'])}
group('st_svc_case_', 'ent_svc_service_visit', [('schedule','scheduled_at','service_case'),('visit','outcome parts_used',''),('part_wait','parts_used outcome','')])
group('st_crm_opportunity_', 'ent_crm_opportunity', [('qualify','title stage value_amount expected_close','customer'),('propose','value_amount discount_pct expected_close',''),('approve','decision',''),('revise','value_amount discount_pct expected_close',''),('negotiate','stage loss_reason','')])
CONTRACTS['st_crm_opportunity_propose']['ent_crm_activity']=(['kind','due_date','done'],['opportunity'])
group('st_eco_order_', 'ent_eco_order', [('enter','channel total_amount currency order_date status','customer'),('payment','payment_status',''),('chase','payment_status',''),('confirm','status','')])
CONTRACTS['st_eco_order_enter']['ent_eco_order_line']=(['quantity','unit_price'],['order','item'])
CONTRACTS['st_eco_order_backorder']={'ent_eco_order_line':(['quantity'],[])}
group('st_fin_billing_', 'ent_fin_invoice', [('draft','amount currency issue_date due_date status','customer order'),('approve','decision',''),('amend','amount currency due_date',''),('issue','issue_date status',''),('close','status','')])
group('st_fin_billing_', 'ent_fin_payment', [('payment','amount_received received_on method','invoice'),('follow_up','amount_received received_on method','')])
group('st_pro_requisition_', 'ent_pro_requisition', [('raise','quantity estimated_cost needed_by justification status','item'),('approve','decision','')])
group('st_pro_requisition_', 'ent_pro_purchase_order', [('order','total_amount order_date expected_date status','requisition supplier'),('close','status','')])
group('st_pro_requisition_', 'ent_pro_goods_receipt', [('receive','quantity_received received_on condition','purchase_order'),('reconcile','quantity_received condition','')])
group('st_wms_fulfilment_', 'ent_wms_pick_list', [('allocate','status created_on','order location'),('shortage','status',''),('handoff','status','')])
group('st_wms_fulfilment_', 'ent_wms_pick_line', [('pick','quantity_picked','pick_list order_line stock_level'),('short_pick','quantity_picked','')])
CONTRACTS['st_wms_fulfilment_pack']={'ent_wms_pack_unit':(['packages','gross_weight_kg','packed_on'],['pick_list'])}
group('st_wfm_leave_', 'ent_wfm_leave_request', [('submit','start_date end_date days kind','employee'),('adjust','start_date end_date days kind',''),('decide','decision note','')])
CONTRACTS['st_wfm_leave_record']={'ent_wfm_employee':(['leave_balance_days'],[])}
group('st_bw_contract_', 'ent_bw_service_contract', [('draft','start_date end_date response_hours status','customer'),('approve','decision',''),('revise','start_date end_date response_hours',''),('activate','status','')])

# Legacy reference packs include imported/system-owned records. Empty field lists
# deliberately keep those read-only; they do not simulate missing integrations.
group('tl_', 'ent_transport_request', [('request','requested_pickup_date requested_delivery_date special_handling','order warehouse')])
group('tl_', 'ent_transport_plan', [('plan','planned_departure planned_arrival','transport_request route'),('assign','','carrier vehicle')])
group('tl_', 'ent_proof_of_delivery', [('pod','delivered_at received_by evidence_reference','shipment')])
group('tl_', 'ent_transport_exception', [('resolve','kind raised_at resolution','shipment')])
CONTRACTS['tl_dispatch']={'ent_shipment':([],['transport_plan','carrier','route'])}
CONTRACTS['tl_track']={'ent_tracking_event':([],[])}
CONTRACTS['wh_pick']={'ent_pick_task':(['quantity'],['order_line','warehouse'])}
CONTRACTS['wh_pack']={'ent_pack_unit':(['weight_kg'],[])}
CONTRACTS['wh_handoff']={'ent_fulfilment_handoff':(['released_at'],['pack_unit','transport_request']), 'ent_transport_request':(['requested_pickup_date','requested_delivery_date','special_handling'],[])}
group('order_', 'ent_order', [('enter_details','requester_name requester_email requester_phone receiver_name receiver_phone dealer_service_required','ship_to dealer')])
CONTRACTS['order_review']={'ent_order':([],[]),'ent_order_line':(['quantity','machine_model'],['part'])}
CONTRACTS['order_allocate']={'ent_inventory':([],[]),'ent_order':([],[]),'ent_status_event':([],[])}
CONTRACTS['order_handle_allocation']={'ent_order':([],[]),'ent_status_event':([],[])}
CONTRACTS['order_fulfil']={'ent_order':([],[]),'ent_status_event':([],[])}
CONTRACTS['order_ship']={'ent_shipment':([],[]),'ent_tracking_event':([],[])}
CONTRACTS['order_dealer_service']={'ent_status_event':([],[])}
group('claim_', 'ent_warranty_claim', [('submit','failure_description','part dealer'),('review','','')])


def apply_contracts(document, entities):
    changed = False
    if document.get("id") in ("noordveld_transport", "noordveld_spare_parts"):
        if document.get("usage") != "source_reference":
            document["usage"] = "source_reference"
            changed = True
        document["version"] = "2026.10.19.1"
    for workflow in document.get('workflows', []):
        for step in workflow['states']:
            permission = PERMISSIONS.get(step['id'])
            if permission and not step.get('permission'):
                role = next(r for r in document['business']['roles'] if r['id'] == step['role_id'])
                if permission not in role['permissions']:
                    raise ValueError(f"Task permission is not held: {step['id']}")
                step['permission'] = permission
                changed = True
            contract = CONTRACTS.get(step['id'])
            if contract is None:
                continue
            fields, relationships = {}, {}
            for entity_id, (attributes, suffixes) in contract.items():
                entity = entities[entity_id]
                known = {a['id']: a for a in entity['attributes']}
                if entity_id not in step['writes_entity_ids'] or any(a not in known for a in attributes):
                    raise ValueError(f"Invalid task input contract {step['id']}/{entity_id}")
                # Attribute ownership must agree with the task. Never show another role's input as editable.
                fields[entity_id] = [a for a in attributes if known[a].get('owner_role_id') in (None, step['role_id'])]
                relationships[entity_id] = []
                for suffix in suffixes:
                    matches = [r['id'] for r in entity['relationships'] if r['id'].endswith('_' + suffix)]
                    if len(matches) != 1:
                        raise ValueError(f"Ambiguous relationship {entity_id}/{suffix}")
                    relationships[entity_id].extend(matches)
            if step.get('input_fields') != fields or step.get('input_relationships') != relationships:
                step.update(input_fields=fields, input_relationships=relationships)
                changed = True
    if changed:
        document['version'] = '2026.10.19.1' if document.get('usage') == 'source_reference' else VERSION
    return changed


def main():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / 'app/design_studio/knowledge/packs'
    documents = {p: json.loads(p.read_text(encoding='utf-8')) for p in root.glob('*.json')}
    entities = {e['id']: e for d in documents.values() for e in d['business'].get('entities', [])}
    changed = []
    for path, document in documents.items():
        scoped_entities = {**entities, **{e['id']: e for e in document['business'].get('entities', [])}}
        if apply_contracts(document, scoped_entities):
            changed.append(path)
    import sys
    sys.path.insert(0, str(root.parents[3]))
    from app.design_studio.knowledge.provider import build_packs
    build_packs({d['id']: d for d in documents.values()})
    for path in changed:
        path.write_text(json.dumps(documents[path], indent=1, ensure_ascii=False)+'\n', encoding='utf-8')
    print('Updated task contracts:', ', '.join(sorted(documents[p]['id'] for p in changed)))


if __name__ == '__main__':
    main()


