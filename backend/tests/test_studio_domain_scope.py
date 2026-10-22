"""Business words shared by many apps must not import unrelated workflows."""

from app.design_studio.knowledge.planning import plan_application, reference_domains
from app.design_studio.knowledge.provider import LocalKnowledgeProvider, identify_domains


def test_procurement_does_not_import_leave_or_customer_checkout():
    provider = LocalKnowledgeProvider()
    prompt = (
        "Build an application for purchase requests and supplier management. "
        "Employees request items, managers approve them, and procurement creates purchase orders. "
        "Include a dashboard, approval inbox, supplier directory and order tracking. "
        "Track budgets and goods received, with sample data for the demo."
    )
    adopt = plan_application(prompt, provider)["adopt"]
    assert adopt and all(provider.pack(pack).domain_id == "procurement_purchasing" for pack in adopt), "only procurement knowledge, never leave or checkout"
    # Once the project has a domain, other domains are offered only when they cover the request on their own words.
    domains = reference_domains("procurement_purchasing", identify_domains(prompt, provider))
    assert domains[0] == "procurement_purchasing" and "workforce_tasks" not in domains


def test_project_domain_does_not_hide_other_verified_knowledge_it_needs():
    provider = LocalKnowledgeProvider()
    prompt = (
        "Build an end-to-end WMS for managing warehouse operations, from receiving inbound goods through putaway, "
        "storage, inventory control, replenishment, picking, packing, shipping and returns."
    )
    domains = reference_domains("warehouse_management", identify_domains(prompt, provider))
    assert domains[0] == "warehouse_management" and "inventory_supply_chain" in domains, (
        "a WMS also needs the verified stock control knowledge"
    )


def test_explicit_fifth_domain_is_not_silently_dropped():
    plan = plan_application(
        'Build TMS transport logistics shipments, WMS warehouse putaway picking packing, '
        'CRM customer sales leads opportunities, procurement suppliers requisitions purchasing, '
        'and after-sales warranty repair installation.', LocalKnowledgeProvider()
    )
    assert {domain['domain_id'] for domain in plan['domains']} == {
        'transport_management', 'warehouse_management', 'sales_crm',
        'procurement_purchasing', 'aftersales_service',
    }
