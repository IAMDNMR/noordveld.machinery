"""The systems a workspace can show. Each entry says honestly whether it can be used operationally today.

`operational`: an application that exists in this repository and runs against its own data (it has a route).
`in_design`: being modelled in Design Studio; generated artifacts exist at most as previews and contracts.
`planned`: named in the roadmap with no project yet.
Nothing here is ever labelled operational because a design or a generated preview exists for it.
"""

from __future__ import annotations

# app_roles are application-specific, never global. A user holds one only through an explicit grant for an organization.
APPLICATIONS: list[dict] = [
    {
        "id": "parts_store",
        "name": "Parts Store",
        "domain": "Spare-parts commerce",
        "route": "/parts-store",
        "status": "operational",
        "description": "Browse the parts catalogue, check fitment and place an order.",
        "app_roles": ["customer", "dealer"],
    },
    {
        "id": "orders",
        "name": "Order processing",
        "domain": "Order management",
        "route": "/orders",
        "status": "operational",
        "description": "Follow orders through allocation, shipment and delivery; processors move them along.",
        "app_roles": ["customer", "order_processor"],
    },
    {
        "id": "parts_intelligence",
        "name": "Parts Intelligence",
        "domain": "Machinery and parts intelligence",
        "route": "/parts-intelligence",
        "status": "operational",
        "description": "Ask which part fits which machine, with the evidence.",
        "app_roles": ["customer", "dealer", "oem_parts_manager"],
    },
    {
        "id": "agentic_shopping",
        "name": "Agentic Shopping",
        "domain": "Spare-parts commerce",
        "route": "/agentic-shopping",
        "status": "operational",
        "description": "Describe what you need; get ranked options with the evidence, then hand the cart to checkout.",
        "app_roles": ["customer", "dealer"],
    },
    {
        "id": "tms",
        "name": "Transport Management",
        "domain": "Transport management",
        "route": None,
        "status": "in_design",
        "description": "Transport requests, planning, carrier assignment, dispatch, tracking and proof of delivery.",
        "app_roles": ["transport_planner", "dispatcher", "carrier_partner"],
    },
    {
        "id": "wms",
        "name": "Warehouse Management",
        "domain": "Warehouse management",
        "route": None,
        "status": "in_design",
        "description": "Allocation, picking, packing and the handoff to transport.",
        "app_roles": ["warehouse_operator", "inventory_manager"],
    },
    {
        "id": "service_warranty",
        "name": "After-sales service and warranty",
        "domain": "Service and warranty",
        "route": None,
        "status": "planned",
        "description": "Service records, technician visits and warranty claims.",
        "app_roles": ["service_technician", "warranty_reviewer", "equipment_owner"],
    },
    {
        "id": "procurement",
        "name": "Procurement and suppliers",
        "domain": "Procurement",
        "route": None,
        "status": "planned",
        "description": "Suppliers, approved sources and backorders.",
        "app_roles": ["procurement_officer"],
    },
]
BY_ID = {item["id"]: item for item in APPLICATIONS}
# Which Design Studio project templates map to which application, so a project shows up under the right system.
PROJECT_APPLICATION_HINTS = {"tms": ("transport", "tms"), "wms": ("warehouse", "wms")}
