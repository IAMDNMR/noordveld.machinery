"""Curated primary-source process fragments for every current Studio blueprint.

No network calls, model calls or graph writes. Research is paraphrased and versioned;
missing categories stay visible instead of being filled with invented rules.
"""

import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.design_studio.knowledge.process_references import CATALOG_PATH, validate_references
from app.design_studio.knowledge.system_context import load_catalog

CHECKED = "2026-10-20"
VERSION = "2026.10.20"
ODOO = "https://www.odoo.com/documentation/19.0/applications/"
ORACLE = "https://docs.oracle.com/en/cloud/saas/transportation/25c/otmol/"
FRAPPE = "https://docs.frappe.io/"
MS = "https://learn.microsoft.com/en-us/"


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def build():
    systems = {item["id"]: item for item in load_catalog()["systems"]}
    from app.design_studio.knowledge.provider import LocalKnowledgeProvider

    for pack in LocalKnowledgeProvider().packs():
        if pack.id in ("core_foundations", "reusable_parts_commerce"):
            systems[pack.id] = {
                "name": pack.title,
                "blueprint_version": pack.version,
                "domain_id": pack.domain_id,
            }
    result = []

    def add(blueprint, system, sources, entities, facts, relationships=(), analogous=None):
        profile = systems[blueprint]
        claims = [
            {
                "id": "entity_" + slug(name),
                "kind": "entity",
                "text": name,
                "source_ids": ["source_0"],
                "locator": sources[0][2],
            }
            for name in entities
        ]
        for index, (kind, text, source_index) in enumerate(facts):
            claims.append(
                {
                    "id": f"{kind}_{index}",
                    "kind": kind,
                    "text": text,
                    "source_ids": [f"source_{source_index}"],
                    "locator": sources[source_index][2],
                }
            )
        for index, (left, right, text, source_index) in enumerate(relationships):
            claims.append(
                {
                    "id": f"relationship_{index}",
                    "kind": "relationship",
                    "text": text,
                    "subject": "entity_" + slug(left),
                    "target": "entity_" + slug(right),
                    "source_ids": [f"source_{source_index}"],
                    "locator": sources[source_index][2],
                }
            )
        result.append(
            {
                "id": "ref_" + blueprint,
                "version": VERSION,
                "name": profile["name"] + " — documented process reference",
                "blueprint_id": blueprint,
                "blueprint_version": profile["blueprint_version"],
                "domain_id": profile["domain_id"],
                "system": system,
                "applicability": "analogous" if analogous else "direct",
                "applicability_note": analogous
                or "Documented vendor behavior is a reference pattern. Applicability to the customer must be reviewed.",
                "regions": ["shared"],
                "review_state": "draft",
                "sources": [
                    {
                        "id": f"source_{i}",
                        "publisher": publisher,
                        "product_version": version,
                        "title": title,
                        "url": url,
                        "checked_on": CHECKED,
                    }
                    for i, (publisher, version, title, url) in enumerate(sources)
                ],
                "claims": claims,
                "limitations": [
                    "Partial source extraction, not an exhaustive implementation specification.",
                    "No customer policy, country-specific compliance, real price or external connection is confirmed by this reference.",
                ],
            }
        )

    field = [
        (
            "Microsoft",
            "Online documentation checked 2026-10-20",
            "Work order lifecycle and system statuses",
            MS + "dynamics365/field-service/work-order-status-booking-status",
        )
    ]
    add(
        "cat_aftersales",
        "Dynamics 365 Field Service",
        field,
        ["Work order", "Booking"],
        [
            (
                "activity",
                "Create work, schedule and dispatch it, perform the service, review completion, then process billing and inventory.",
                0,
            ),
            (
                "status",
                "Work order system statuses: Unscheduled, Scheduled, In Progress, Completed, Posted, Canceled.",
                0,
            ),
            (
                "rule",
                "Work-order and booking lifecycles are separate; booking changes can update the parent work order.",
                0,
            ),
            (
                "exception",
                "Follow-up work can return a work order to an unscheduled state when the booking status is configured not to complete it.",
                0,
            ),
        ],
        [("Work order", "Booking", "A work order can have multiple resource bookings.", 0)],
    )

    add(
        "cat_agriculture_operations",
        "ERPNext Agriculture",
        [
            (
                "Frappe",
                "Unversioned documentation checked 2026-10-20",
                "Crops and land introduction",
                FRAPPE + "erpnext/crops-and-land-introduction",
            )
        ],
        ["Land unit", "Crop"],
        [
            (
                "activity",
                "Record growing areas and crops, plan crop activities, collect analysis data, and record harvest sale or warehouse transfer.",
                0,
            ),
        ],
        [
            (
                "Land unit",
                "Crop",
                "Crop activities are organized around the physical areas used for growing crops.",
                0,
            )
        ],
    )

    add(
        "cap_approvals",
        "Microsoft Power Automate",
        [
            (
                "Microsoft",
                "Online documentation checked 2026-10-20",
                "Create an approval flow that requires everyone to approve",
                MS + "power-automate/all-assigned-must-approve",
            )
        ],
        ["Approval request", "Approver"],
        [
            (
                "activity",
                "Send approval requests and wait for responses from the assigned approvers.",
                0,
            ),
            (
                "rule",
                "For the Everyone must approve type, wait for every assigned approver to approve or for one approver to reject.",
                0,
            ),
            ("status", "The documented approval response choices are Approve and Reject.", 0),
        ],
        [("Approval request", "Approver", "An approval request is assigned to approvers.", 0)],
    )

    project = [
        (
            "Frappe",
            "Unversioned documentation checked 2026-10-20",
            "Tasks",
            FRAPPE + "erpnext/tasks",
        )
    ]
    add(
        "cat_construction_delivery",
        "ERPNext Projects",
        project,
        ["Project", "Task"],
        [
            (
                "activity",
                "Represent work as project tasks and inspect task dependencies in a Gantt view.",
                0,
            ),
        ],
        [("Project", "Task", "Tasks represent actionable work within project management.", 0)],
        analogous="Project/task coordination is analogous to construction work packages. Construction permits, site safety and contractual acceptance are not established by this source.",
    )

    add(
        "cap_documents",
        "Odoo Documents",
        [
            (
                "Odoo",
                "saas-17.4",
                "Documents",
                "https://www.odoo.com/documentation/saas-17.4/applications/productivity/documents.html",
            )
        ],
        ["Document", "Workspace"],
        [
            ("activity", "Store, view and organize files in workspaces.", 0),
            (
                "rule",
                "An email alias can route incoming documents to a workspace using its assigned tag.",
                0,
            ),
        ],
        [("Document", "Workspace", "Workspaces organize stored documents.", 0)],
    )

    add(
        "cat_ecommerce",
        "Odoo eCommerce",
        [("Odoo", "19.0", "Order handling", ODOO + "websites/ecommerce/order_handling.html")],
        ["Sales order", "Delivery order", "Invoice"],
        [
            ("activity", "An online purchase proceeds through sale, delivery and invoicing.", 0),
            (
                "status",
                "Quotation represents an unfinished checkout; Quotation Sent can mean checkout completed while payment remains unconfirmed.",
                0,
            ),
            (
                "rule",
                "Delivery processing requires Inventory; service and subscription products do not generate delivery orders.",
                0,
            ),
            (
                "exception",
                "Returns and refunds have separate handling; refund issuance requires a compatible payment provider.",
                0,
            ),
        ],
        [
            (
                "Sales order",
                "Delivery order",
                "Confirmation creates a delivery order for applicable products.",
                0,
            ),
            (
                "Sales order",
                "Invoice",
                "Customer invoicing is a separate step; automatic invoicing depends on configuration and registered payment.",
                0,
            ),
        ],
    )

    add(
        "cat_education_services",
        "Frappe Education",
        [
            (
                "Frappe",
                "Unversioned documentation checked 2026-10-20",
                "Student Applicant",
                FRAPPE + "education/student-applicant",
            )
        ],
        ["Student applicant", "Student", "Program enrollment"],
        [
            (
                "activity",
                "Use the enrollment action on an applicant to create the student and open program enrollment.",
                0,
            ),
        ],
        [
            (
                "Student applicant",
                "Student",
                "Enrollment creates a student record for the applicant.",
                0,
            ),
            (
                "Student",
                "Program enrollment",
                "The enrollment action continues to the program enrollment form.",
                0,
            ),
        ],
    )

    add(
        "cat_finance",
        "Odoo Accounting",
        [("Odoo", "19.0", "Customer invoices", ODOO + "finance/accounting/customer_invoices.html")],
        ["Customer", "Invoice", "Journal entry"],
        [
            (
                "activity",
                "Prepare a customer invoice and post it to generate its accounting entry.",
                0,
            ),
            ("status", "Customer invoices start in Draft and change to Posted when posted.", 0),
        ],
        [
            (
                "Customer",
                "Invoice",
                "Selecting the customer supplies invoice details from its customer record.",
                0,
            ),
            (
                "Invoice",
                "Journal entry",
                "Posting an invoice creates a journal entry according to the configuration.",
                0,
            ),
        ],
    )

    add(
        "cat_healthcare_admin",
        "Frappe Health",
        [
            (
                "Frappe",
                "v13",
                "Patient Encounter",
                "https://healthcare.frappe.io/docs/v13/user/manual/en/healthcare/patient_encounter",
            )
        ],
        ["Patient encounter", "Appointment"],
        [
            (
                "activity",
                "Record an encounter and optionally select an existing appointment to populate its administrative details.",
                0,
            ),
        ],
        [
            (
                "Patient encounter",
                "Appointment",
                "Selecting an appointment fetches patient, department and practitioner details.",
                0,
            )
        ],
    )

    add(
        "cat_hospitality_booking",
        "ERPNext Hospitality",
        [
            (
                "Frappe",
                "Unversioned documentation checked 2026-10-20",
                "Hospitality",
                FRAPPE + "erpnext/hospitality",
            )
        ],
        ["Hotel room", "Hotel room reservation", "Invoice"],
        [
            (
                "activity",
                "Create rooms, register room reservations and create invoices from reservations.",
                0,
            ),
        ],
        [
            (
                "Hotel room reservation",
                "Hotel room",
                "A hotel room reservation refers to a room.",
                0,
            ),
            (
                "Hotel room reservation",
                "Invoice",
                "The documented hotel module supports invoicing from room reservations.",
                0,
            ),
        ],
    )
    result[-1]["limitations"].append(
        "The source describes the hospitality module as early development; do not infer production completeness."
    )

    tickets = [
        (
            "Frappe",
            "Unversioned documentation checked 2026-10-20",
            "Ticket",
            FRAPPE + "helpdesk/ticket",
        ),
        (
            "Frappe",
            "Unversioned documentation checked 2026-10-20",
            "Service Level Agreement",
            FRAPPE + "helpdesk/service-level-agreement",
        ),
    ]
    add(
        "cat_it_service_management",
        "Frappe Helpdesk",
        tickets,
        ["Ticket"],
        [
            (
                "activity",
                "Capture the reported issue, assign its support details, communicate with the customer and resolve the ticket.",
                0,
            ),
            ("rule", "SLA conditions determine the applicable response and resolution policy.", 1),
            (
                "exception",
                "A ticket that matches no SLA policy has no first-response or resolution target.",
                1,
            ),
        ],
    )

    add(
        "cat_inventory",
        "Odoo Inventory",
        [
            (
                "Odoo",
                "19.0",
                "Inventory adjustments",
                ODOO
                + "inventory_and_mrp/inventory/warehouses_storage/inventory_management/count_products.html",
            )
        ],
        ["Product", "Inventory count"],
        [
            (
                "activity",
                "Record the physical count, inspect differences and apply the inventory adjustment.",
                0,
            ),
        ],
        [
            (
                "Inventory count",
                "Product",
                "The counted quantity records the observed quantity for a product.",
                0,
            )
        ],
    )

    add(
        "cat_manufacturing",
        "Odoo Manufacturing",
        [
            (
                "Odoo",
                "19.0",
                "Work order dependencies",
                ODOO
                + "inventory_and_mrp/manufacturing/advanced_configuration/work_order_dependencies.html",
            )
        ],
        ["Manufacturing order", "Work order", "Bill of materials"],
        [
            (
                "activity",
                "Confirm a manufacturing order using its bill of materials, inspect work orders and plan their schedule.",
                0,
            ),
            (
                "status",
                "Dependent work orders show Blocked; work orders without unmet dependencies show To Do.",
                0,
            ),
            ("rule", "Completing a blocking work order makes its dependent work available.", 0),
            (
                "exception",
                "The documented exception action can break a dependency link; it is not permission to silently ignore dependencies.",
                0,
            ),
        ],
        [
            (
                "Manufacturing order",
                "Work order",
                "The manufacturing order contains its required work orders.",
                0,
            ),
            (
                "Manufacturing order",
                "Bill of materials",
                "The selected bill of materials defines work-order dependencies.",
                0,
            ),
        ],
    )

    add(
        "cat_procurement",
        "Odoo Purchase",
        [
            (
                "Odoo",
                "19.0",
                "Call for tenders",
                ODOO + "inventory_and_mrp/purchase/manage_deals/calls_for_tenders.html",
            )
        ],
        ["Request for quotation", "Vendor"],
        [
            (
                "activity",
                "Prepare alternative vendor quotations and compare their product lines, prices and delivery times before choosing purchases.",
                0,
            ),
        ],
        [
            (
                "Request for quotation",
                "Vendor",
                "Alternative quotation requests are addressed to different vendors.",
                0,
            )
        ],
    )

    add(
        "cat_property_operations",
        "Dynamics 365 Asset Management",
        [
            (
                "Microsoft",
                "Online documentation checked 2026-10-20",
                "Create work orders from maintenance requests",
                MS
                + "dynamics365/supply-chain/asset-management/manage-maintenance-requests/create-work-order-from-a-maintenance-request",
            )
        ],
        ["Maintenance request", "Work order", "Asset"],
        [
            (
                "activity",
                "Select maintenance requests, supply asset and job details, then create their work order.",
                0,
            ),
            (
                "rule",
                "A maintenance request can refer to only one work order; a work order can include multiple maintenance requests.",
                0,
            ),
            (
                "exception",
                "An asset warranty agreement can trigger a notification during work-order creation.",
                0,
            ),
        ],
        [
            (
                "Maintenance request",
                "Work order",
                "Selected maintenance requests are converted into a work order.",
                0,
            ),
            (
                "Maintenance request",
                "Asset",
                "Asset information is supplied for the maintenance request.",
                0,
            ),
        ],
        analogous="Asset maintenance is an analogous reference for property maintenance. Tenancy, rental law and property-specific inspection requirements are not covered.",
    )

    add(
        "cat_public_service_requests",
        "Dynamics 365 case management",
        [
            (
                "Microsoft",
                "Online documentation checked 2026-10-20",
                "Case management overview",
                MS + "dynamics365/fin-ops-core/dev-itpro/organization-administration/cases",
            )
        ],
        ["Case"],
        [
            (
                "activity",
                "Create cases, manage resolution, organize case hierarchies and merge similar cases.",
                0,
            ),
        ],
        analogous="Generic case management can inform public-service request handling. Jurisdiction-specific eligibility, statutory deadlines and appeal procedures need separate primary sources.",
    )

    add(
        "cat_crm",
        "Odoo CRM",
        [("Odoo", "19.0", "Pipeline Analysis", ODOO + "sales/crm/performance/win_loss.html")],
        ["Lead", "Opportunity"],
        [
            (
                "activity",
                "Qualify leads when enabled, move opportunities through pipeline stages and record whether business was won or lost.",
                0,
            ),
            ("status", "The documented terminal sales outcomes are won and lost.", 0),
        ],
        [
            (
                "Lead",
                "Opportunity",
                "Lead qualification can precede creation of a formal opportunity.",
                0,
            )
        ],
    )

    add(
        "cap_task_management",
        "Frappe Framework",
        [
            (
                "Frappe",
                "Unversioned documentation checked 2026-10-20",
                "Assignments and Todos",
                FRAPPE + "framework/assignments-and-todos",
            )
        ],
        ["Document", "ToDo"],
        [
            (
                "activity",
                "Use document assignment to track work assigned to yourself or another user.",
                0,
            ),
        ],
        [("Document", "ToDo", "Assignments associate tracked work with a document.", 0)],
    )

    otm = [
        (
            "Oracle",
            "25c",
            "Setting Up Itineraries",
            ORACLE + "planning/itinerary_manager/manage_itinerary/setting_up_itineraries.htm",
        ),
        (
            "Oracle",
            "25c",
            "Rate Offering",
            ORACLE + "planning/rate_manager/create_rate_offering.htm",
        ),
        (
            "Oracle",
            "25c",
            "Itineraries and Bulk Plan",
            ORACLE + "bulk_plan_manager/data_setup/itineraries_and_bulk_plan.htm",
        ),
        ("Oracle", "25c", "Accept Tender", ORACLE + "planning/shipment_manager/accept_tender.htm"),
    ]
    add(
        "cat_transport",
        "Oracle Transportation Management",
        otm,
        ["Itinerary", "Order release", "Shipment"],
        [
            (
                "activity",
                "Find itineraries matching order origins and destinations, filter against itinerary rules and select the lowest-cost qualifying itinerary.",
                0,
            ),
            (
                "activity",
                "Itineraries guide single-leg and multi-leg shipment creation through a transport network.",
                2,
            ),
            (
                "rule",
                "Rate qualification checks shipment dimensions and weight, time, geography and optional equipment or service requirements.",
                1,
            ),
            (
                "rule",
                "Rate records provide location-to-location costs; offering details provide contractual defaults.",
                1,
            ),
            (
                "rule",
                "Rate offerings include a transport mode and validity dates; an offer outside its date range does not qualify.",
                1,
            ),
            (
                "exception",
                "Template or read-only offerings are used for sourcing and maintenance, not shipment building or execution.",
                1,
            ),
            (
                "status",
                "Accept Tender updates the SECURE RESOURCES shipment status to ACCEPTED or BOOKED as applicable.",
                3,
            ),
        ],
        [
            (
                "Order release",
                "Itinerary",
                "An itinerary provides a movement template for order releases.",
                2,
            ),
            ("Shipment", "Itinerary", "Shipment routes follow the selected itinerary.", 0),
        ],
    )
    # These entities are documented by Rate Offering, not by the itinerary source.
    for name in ["Rate offering", "Rate record", "Transport mode"]:
        result[-1]["claims"].append(
            {
                "id": "entity_" + slug(name),
                "kind": "entity",
                "text": name,
                "source_ids": ["source_1"],
                "locator": "Rate Offering / Rate Header",
            }
        )
    for left, right, text in [
        ("Rate offering", "Rate record", "One rate offering can have several rate records."),
        ("Rate offering", "Transport mode", "An offering specifies how goods are transported."),
    ]:
        result[-1]["claims"].append(
            {
                "id": "relationship_" + slug(left + "_" + right),
                "kind": "relationship",
                "text": text,
                "subject": "entity_" + slug(left),
                "target": "entity_" + slug(right),
                "source_ids": ["source_1"],
                "locator": "Rate Offering / Rate Header",
            }
        )

    add(
        "cat_warehouse",
        "Odoo Inventory",
        [
            (
                "Odoo",
                "19.0",
                "Two-step receipt and delivery",
                ODOO
                + "inventory_and_mrp/inventory/shipping_receiving/daily_operations/receipts_delivery_two_steps.html",
            )
        ],
        ["Product", "Input area", "Stock location", "Output location"],
        [
            (
                "activity",
                "Receive products into an input area, then transfer them to stock; for delivery, pick to an output area before shipping.",
                0,
            ),
            (
                "rule",
                "In the documented two-step receipt configuration, products are unavailable for further processing until transferred into stock.",
                0,
            ),
        ],
        [
            ("Input area", "Stock location", "Receipt moves goods from input to storage.", 0),
            (
                "Stock location",
                "Output location",
                "Delivery picking moves goods into the output area.",
                0,
            ),
        ],
    )

    add(
        "cat_workforce",
        "Frappe HR",
        [
            (
                "Frappe",
                "Unversioned documentation checked 2026-10-20",
                "Leave Application",
                FRAPPE + "hr/leave-application",
            )
        ],
        ["Employee", "Leave application", "Leave approver"],
        [
            (
                "activity",
                "Choose employee, leave type and dates, supply the reason and approver, save the request and submit the approver decision.",
                0,
            ),
            (
                "status",
                "A saved application becomes Open; the approver can approve, reject or cancel the application.",
                0,
            ),
        ],
        [
            (
                "Employee",
                "Leave application",
                "Employees request leave through a leave application.",
                0,
            ),
            ("Leave application", "Leave approver", "The application selects a leave approver.", 0),
        ],
    )

    add(
        "core_foundations",
        "Odoo Contacts",
        [
            (
                "Odoo",
                "20.0",
                "Contacts",
                "https://www.odoo.com/documentation/20.0/applications/essentials/contacts.html",
            )
        ],
        ["Individual contact", "Company contact"],
        [
            (
                "activity",
                "Maintain contact records and link an individual contact to the associated company.",
                0,
            ),
        ],
        [
            (
                "Individual contact",
                "Company contact",
                "The company employer field associates an individual with a company contact.",
                0,
            )
        ],
        analogous="Contact master data is one part of shared foundations. Items, suppliers and location governance require additional references.",
    )

    add(
        "reusable_parts_commerce",
        "Odoo product variants",
        [
            (
                "Odoo",
                "19.0",
                "Product variants",
                ODOO + "sales/sales/products_prices/products/variants.html",
            )
        ],
        ["Product variant", "Attribute"],
        [
            (
                "activity",
                "Define attributes and values, then inspect the resulting product variant combinations.",
                0,
            ),
        ],
        [
            (
                "Product variant",
                "Attribute",
                "Variant combinations depend on configured attribute values.",
                0,
            )
        ],
        analogous="Product configuration is an analogous commerce pattern. Parts compatibility, supersession, restricted ordering and warranties need their own evidence.",
    )
    references = validate_references(result)
    missing = set(systems) - {item.blueprint_id for item in references}
    if missing:
        raise ValueError(f"Missing current blueprint references: {sorted(missing)}")
    return [item.model_dump(mode="json") for item in sorted(references, key=lambda item: item.id)]


if __name__ == "__main__":
    documents = build()
    CATALOG_PATH.write_text(json.dumps(documents, indent=2) + "\n", encoding="utf-8")
    print(f"{len(documents)} process references saved to {CATALOG_PATH.name}")
