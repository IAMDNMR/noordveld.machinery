"""Additional operational sector blueprints; all rules are reviewable design assumptions."""
from catalog_dsl import Pack, A, S

SECTORS = [
 ('healthcare_admin','hca','Healthcare administration','Appointment coordination','appointment',['clinic','clinical appointment','patient scheduling','hospital administration'], [('service','Service requested','string'),('scheduled_at','Appointment time','datetime'),('attendance','Attendance','string')], ['Register the appointment request','Schedule the visit','Record attendance','Close the administrative visit']),
 ('education_services','edu','Education services','Enrolment coordination','enrolment',['school','student','enrolment','enrollment','college','training course'], [('course','Course','string'),('start_date','Start date','date'),('registration_reference','Registration reference','string')], ['Capture the enrolment request','Allocate course placement','Record registration','Close the enrolment']),
 ('hospitality_booking','hsp','Hospitality and reservations','Reservation fulfilment','reservation',['hotel','room reservation','hospitality','guest booking','accommodation'], [('arrival','Arrival date','date'),('departure','Departure date','date'),('allocation','Room or resource','string')], ['Capture the reservation','Allocate accommodation','Record guest arrival','Complete the stay']),
 ('construction_delivery','con','Construction delivery','Site work coordination','work_package',['construction','site work','contractor','building project'], [('site','Site','string'),('planned_date','Planned date','date'),('completion_reference','Completion evidence reference','string')], ['Register the work package','Plan crew and materials','Record site completion','Close the work package']),
 ('property_operations','propr','Property operations','Maintenance request resolution','maintenance_request',['property management','tenant maintenance','real estate','housing repairs'], [('property_reference','Property reference','string'),('appointment_date','Service date','date'),('completion_reference','Completion evidence reference','string')], ['Log the maintenance request','Schedule the contractor','Record the repair','Close the maintenance request']),
 ('agriculture_operations','agr','Agriculture operations','Harvest batch handling','harvest_batch',['agriculture','farm','harvest','crop','grower'], [('crop','Crop','string'),('harvest_date','Harvest date','date'),('storage_location','Storage location','string')], ['Register the harvest batch','Plan harvest handling','Record collection and storage','Close the batch handoff']),
 ('public_service_requests','pub','Public service administration','Citizen request handling','service_request',['municipal','citizen request','public service','council service'], [('service_category','Service category','string'),('assigned_team','Assigned team','string'),('resolution_reference','Resolution reference','string')], ['Register the service request','Route to the service team','Record the service outcome','Close the citizen request']),
 ('it_service_management','its','IT service management','Service ticket resolution','ticket',['it service','itsm','helpdesk','service desk','incident ticket'], [('service','Affected service','string'),('assigned_team','Support team','string'),('resolution','Resolution notes','string')], ['Capture the service ticket','Assign the support team','Record the resolution','Close the ticket']),
]


def all_packs():
 for domain, prefix, title, process, record, words, attributes, labels in SECTORS:
  p=Pack('cat_'+domain,prefix,title,process+'. Operational starting point; specialist, clinical, statutory and automated eligibility decisions are outside this blueprint.',
    domain={'id':domain,'name':title,'keywords':words,'subdomains':[process]},domain_id=domain)
  p.version='2026.10.19.2' if domain in ('hospitality_booking','healthcare_admin') else '2026.10.19.1'
  p.role('coordinator',title+' coordinator',[],['Register requests and coordinate delivery'])
  p.role('specialist',title+' specialist',[],['Plan and deliver assigned work'])
  attrs=[A('summary','Summary',req=True), *[A(k,n,t,req=True,owner=p.rid('specialist') if index in (1,2) else None) for index,(k,n,t) in enumerate(attributes)], A('closure_note','Closure note',owner=p.rid('coordinator'))]
  # Detail fields are collected at their own stage, not required on initial capture.
  for a in attrs[1:]: a['required']=False
  p.entity(record,title+' record',process,attrs,owner='coordinator')
  p.rule('summary','A request summary is captured before planning.',record+'.summary')
  p.rule('completion','Completion evidence is recorded before closing.',record+'.'+attributes[2][0])
  p.req('delivery',process+' is traceable from request to closure.', ['The responsible role completes each stage.','Completion evidence is recorded before closure.'])
  p.exc('incomplete','Completion details missing','Required completion evidence is missing.','The specialist adds or corrects completion details.',('delivery','deliver'))
  p.flow('delivery',process,[S('start','Request received','start'),S('capture',labels[0],'form','coordinator',writes=[record],rules=['summary']),S('plan',labels[1],'form','specialist',reads=[record],writes=[record]),S('deliver',labels[2],'form','specialist',writes=[record],exc=['incomplete']),S('close',labels[3],'action','coordinator',reads=[record],writes=[record],rules=['completion']),S('done','Completed','end',outcome='success')],[('start','capture'),('capture','plan'),('plan','deliver'),('deliver','close'),('close','done')],[])
  scopes={'capture':['summary',attributes[0][0]],'plan':[attributes[1][0]],'deliver':[attributes[2][0]],'close':['closure_note']}
  for s in p.workflows[0]['states']:
   key=s['id'].split('_')[-1]
   if key in scopes: s.update(input_fields={p.eid(record):scopes[key]},input_relationships={p.eid(record):[]})
  yield p

if __name__=='__main__':
 import sys
 from pathlib import Path
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from app.design_studio.knowledge.provider import LocalKnowledgeProvider, build_packs
 existing={p.id:p.model_dump(mode='json') for p in LocalKnowledgeProvider().packs()}
 built=list(all_packs()); documents={p.id:p.document() for p in built}
 build_packs({**existing,**documents})
 for p in built: p.write()
 print('Added sector blueprints:',len(built))
