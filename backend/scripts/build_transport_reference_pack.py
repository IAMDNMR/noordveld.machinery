"""Build the Design Studio reference pack `noordveld_transport`: transport (TMS) and warehouse (WMS) workflows.

Entities, relationships and application roles come from the domain pack `noordveld_machinery` (the single source). Rules that
are already confirmed in `noordveld_spare_parts` (stock availability, allocation) are copied verbatim with their source. Every
rule this pack introduces is an assumption, and every open business decision stays open. Deterministic; reads files only.

    python scripts/build_domain_pack.py && python scripts/build_transport_reference_pack.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.design_studio.knowledge.models import ReferencePack  # noqa: E402
from app.domain_knowledge.models import DomainPack  # noqa: E402

DOMAIN_PACK = ROOT / "app/domain_knowledge/packs/noordveld_machinery-1.1.0.json"
SPARE_PARTS = ROOT / "app/design_studio/knowledge/packs/noordveld_spare_parts.json"
OUT = ROOT / "app/design_studio/knowledge/packs/noordveld_transport.json"
VERSION = "2026.10.2"
TYPE_MAP = {"code": "string"}
ENTITIES = ["order", "order_line", "warehouse", "pick_task", "pack_unit", "fulfilment_handoff", "transport_request", "transport_plan", "vehicle", "carrier", "route",
            "shipment", "tracking_event", "proof_of_delivery", "transport_exception"]
COMPANY = {"id": "noordveld", "name": "Noordveld Machinery (synthetic demo company)", "industry": "Industrial machinery and spare parts", "operating_context": "The synthetic demonstration company used throughout this repository; its definitions come from the Noordveld demo data.", "business_units": [], "systems_of_record": []}
ASSUMED = {"kind": "synthetic_assumption", "reference": "TMS/WMS design assumption: the business has not stated this rule"}


def ent_id(entity_id: str) -> str:
    return f"ent_{entity_id}"


def attribute(attr) -> dict:
    editable = attr.value_source == "user_entered" and attr.mutability == "user_updated"
    item = {"id": attr.id, "name": attr.name[:120], "type": TYPE_MAP.get(attr.type, attr.type), "required": attr.required, "key": attr.key,
            "value_source": attr.value_source, "writable": editable, "sensitivity": attr.sensitivity}
    return item


def entities(domain: DomainPack) -> list[dict]:
    known = {item.id: item for item in domain.entities}
    selected = set(ENTITIES)
    result = []
    for entity_id in ENTITIES:
        entity = known[entity_id]
        relationships = [{"id": rel.id[:80], "name": rel.type.replace("_", " ").lower(), "target": ent_id(rel.target_id), "cardinality": rel.cardinality, "required": rel.required}
                         for rel in domain.relationships if rel.source_id == entity_id and rel.target_id in selected]
        result.append({"id": ent_id(entity_id), "name": entity.canonical_name, "description": entity.description[:1000],
                       "source_system": f"Domain pack {domain.id} {domain.version}: {entity_id}", "attributes": [attribute(a) for a in entity.attributes][:60],
                       "relationships": relationships})
    return result


def roles(domain: DomainPack) -> list[dict]:
    result = []
    for role in domain.app_roles:
        item = {"id": role.id, "name": role.name, "responsibilities": [role.description], "permissions": sorted(role.permissions)}
        if role.id == "tms_dispatcher":
            item["approval_authority"] = ["Resolve delayed and failed deliveries, including cancelling a transport"]
        if role.id == "wms_inventory_manager":
            item["approval_authority"] = ["Decide what to do when stock is unavailable"]
        result.append(item)
    result.append({"id": "tms_platform", "name": "Platform (automated checks in transport)", "responsibilities": ["Applies rules automatically"], "permissions": []})
    result.append({"id": "wms_platform", "name": "Platform (automated checks in the warehouse)", "responsibilities": ["Applies rules automatically"], "permissions": []})
    return result


def build() -> dict:
    domain = DomainPack.model_validate_json(DOMAIN_PACK.read_text(encoding="utf-8"))
    spare = json.loads(SPARE_PARTS.read_text(encoding="utf-8"))
    copied = [rule for rule in spare["business"]["rules"] if rule["id"] in ("rule_availability", "rule_allocation")]
    rules = copied + [
        {"id": "rule_carrier_eligibility", "description": "A carrier may be assigned only if it is eligible for the route and the goods.", "type": "decision", "status": "assumption",
         "source": ASSUMED, "outcomes": ["ELIGIBLE", "NOT_ELIGIBLE"]},
        {"id": "rule_capacity_check", "description": "A plan may be dispatched only if the assigned vehicle's capacity covers the load.", "type": "decision", "status": "assumption",
         "source": ASSUMED, "outcomes": ["WITHIN_CAPACITY", "EXCEEDS_CAPACITY"]},
        {"id": "rule_handoff_complete", "description": "Goods are released to transport only when every pick task of the handoff is packed.", "type": "decision", "status": "assumption",
         "source": ASSUMED, "outcomes": ["COMPLETE", "INCOMPLETE"]},
        {"id": "rule_goods_ready", "description": "Dispatch waits until the warehouse has released the goods, when they leave a managed warehouse.", "type": "decision", "status": "assumption",
         "source": ASSUMED, "outcomes": ["READY", "NOT_READY"]},
        {"id": "rule_delivery_outcome", "description": "A tracked shipment ends as delivered, delayed past its planned arrival, or failed.", "type": "decision", "status": "assumption",
         "source": ASSUMED, "outcomes": ["DELIVERED", "DELAYED", "FAILED"]},
        {"id": "rule_pod_required", "description": "A delivery is complete only when proof of delivery is recorded.", "type": "decision", "status": "assumption",
         "source": ASSUMED, "outcomes": ["POD_RECORDED", "POD_MISSING"]},
        # The rule already says who decides; the binding only reads the choice the dispatcher records (any other value is refused).
        {"id": "rule_exception_resolution", "description": "A dispatcher resolves a delayed or failed delivery by retrying it or cancelling the transport.", "type": "decision",
         "status": "assumption", "source": ASSUMED, "outcomes": ["RETRY_DELIVERY", "CANCEL_TRANSPORT"],
         "execution": {"kind": "value", "field": "ent_transport_exception.resolution"}},
        {"id": "rule_tracking_sequence", "description": "Tracking events must start with ORDER_CONFIRMED or PICKED, follow the allowed transitions and never be dated backwards.",
         "type": "validation", "status": "confirmed", "source": {"kind": "implemented_code", "reference": "app/logistics/rules.py sequence_errors and TRANSITIONS"}, "outcomes": []},
    ]
    requirement = lambda rid, text, prio, *criteria: {"id": rid, "statement": text, "priority": prio, "status": "draft", "acceptance_criteria": [{"id": f"ac_{rid}_{i}", "statement": c} for i, c in enumerate(criteria, 1)]}  # noqa: E731
    requirements = [
        requirement("req_transport_request", "A transport request can be registered for an order.", "must", "A request names the order, the collection point and the delivery address."),
        requirement("req_transport_planning", "A planner can plan how a request is moved.", "must", "A plan is linked to its request and, when chosen, to a route."),
        requirement("req_carrier_assignment", "Only an eligible carrier can be assigned, and a vehicle where the carrier assigns one.", "must", "An ineligible carrier is refused with the reason."),
        requirement("req_capacity", "A plan is dispatched only if the vehicle capacity covers the load.", "must", "A plan that exceeds capacity cannot be dispatched and is returned for re-assignment."),
        requirement("req_dispatch", "A dispatcher dispatches a plan once its goods are ready.", "must", "Dispatch is refused while the warehouse has not released the goods."),
        requirement("req_tracking", "Tracking events are recorded in a valid sequence.", "must", "An event that cannot follow the previous one is refused."),
        requirement("req_delivery_pod", "A delivery is confirmed with proof of delivery.", "must", "A delivery without proof of delivery is not closed."),
        requirement("req_exceptions", "Delayed or failed deliveries are resolved by a dispatcher.", "must", "Each exception ends in a retry or a cancellation, with a reason."),
        requirement("req_warehouse_fulfilment", "Allocated order lines are picked and packed before release to transport.", "must", "Goods are released only when every pick task is packed."),
        requirement("req_warehouse_handoff", "A warehouse handoff creates the transport request.", "must", "The handoff names the pack units it releases."),
        {"id": "nfr_audit", "statement": "Every transport and warehouse status change is recorded with who, when and why.", "kind": "non_functional", "category": "auditability",
         "priority": "must", "status": "draft", "acceptance_criteria": [{"id": "ac_audit_1", "statement": "A status history lists each change with its actor and time."}]},
        {"id": "nfr_access", "statement": "Each action is limited to the roles that hold its permission.", "kind": "non_functional", "category": "security", "priority": "must", "status": "draft",
         "acceptance_criteria": [{"id": "ac_access_1", "statement": "A user without the permission cannot perform the action."}]},
    ]
    exceptions = [
        {"id": "exc_no_carrier", "name": "No eligible carrier", "trigger": "No carrier is eligible for the route and the goods.", "recovery": "Re-plan with another route or constraints.", "resolution": "recover", "resolution_state_id": "tl_plan"},
        {"id": "exc_capacity_exceeded", "name": "Capacity exceeded", "trigger": "The assigned vehicle cannot carry the load.", "recovery": "Assign another vehicle or carrier.", "resolution": "recover", "resolution_state_id": "tl_assign"},
        {"id": "exc_goods_not_ready", "name": "Goods not released", "trigger": "The warehouse has not released the goods for dispatch.", "recovery": "Wait for the warehouse handoff and check again.", "resolution": "recover", "resolution_state_id": "tl_check_ready"},
        {"id": "exc_delivery_delayed", "name": "Delivery delayed or failed", "trigger": "The shipment is past its planned arrival or the delivery failed.", "recovery": "A dispatcher decides to retry or cancel.", "resolution": "escalate", "resolution_state_id": "tl_resolve"},
        {"id": "exc_pod_missing", "name": "Proof of delivery missing", "trigger": "Delivery was reported but no proof of delivery is recorded.", "recovery": "Record the proof of delivery.", "resolution": "recover", "resolution_state_id": "tl_pod"},
        {"id": "exc_stock_unavailable", "name": "Stock unavailable", "trigger": "A line has no known stock at the depot.", "recovery": "The order cannot be fulfilled from this depot.", "resolution": "terminate", "resolution_state_id": "wh_end_unfulfilled"},
        {"id": "exc_pick_incomplete", "name": "Pick incomplete", "trigger": "A pick task is not packed when the handoff is attempted.", "recovery": "Finish picking and packing.", "resolution": "recover", "resolution_state_id": "wh_pick"},
    ]
    decisions = [{"id": item.id, "question": item.question, "status": "open", "affects": [a for a in item.affects if a.startswith("rule_")] or ["tl_plan"]}
                 for item in domain.decisions if item.id in ("dec_carrier_selection", "dec_delay_threshold", "dec_pod_requirements", "dec_partial_handoff")]
    for item in decisions:
        if item["id"] == "dec_partial_handoff":
            item["affects"] = ["rule_handoff_complete", "wh_handoff"]
        if item["id"] == "dec_delay_threshold":
            item["affects"] = ["rule_delivery_outcome"]

    def step(sid, label, kind, role, **extra):
        return {"id": sid, "label": label, "kind": kind, "role_id": role, **extra} if role else {"id": sid, "label": label, "kind": kind, **extra}

    def edge(eid, source, target, field=None, value=None):
        return {"id": eid, "source": source, "target": target, "condition": {"kind": "always"} if field is None else {"kind": "equals", "field": field, "value": value}}

    transport = {"version": 1, "id": "wf_transport_lifecycle", "name": "Transport lifecycle", "states": [
        step("tl_start", "A shipment must be moved", "start", None),
        # "An order exists" and "a transport request exists" are the step's reads and writes: the runtime refuses the step until both records are linked.
        step("tl_request", "Register the transport request", "form", "tms_planner", permission="transport.request.write", requirement_ids=["req_transport_request"],
             reads_entity_ids=["ent_order"], writes_entity_ids=["ent_transport_request"]),
        step("tl_plan", "Plan the transport", "form", "tms_planner", permission="transport.plan.write", requirement_ids=["req_transport_planning"],
             reads_entity_ids=["ent_transport_request", "ent_route"], writes_entity_ids=["ent_transport_plan"], exception_ids=["exc_no_carrier"]),
        step("tl_check_eligibility", "Is a carrier eligible?", "branch", "tms_platform", outputs=["rule_carrier_eligibility"], requirement_ids=["req_carrier_assignment"],
             reads_entity_ids=["ent_transport_plan", "ent_carrier", "ent_route"], rule_ids=["rule_carrier_eligibility"], exception_ids=["exc_no_carrier"]),
        step("tl_no_carrier", "No eligible carrier", "exception", "tms_planner", requirement_ids=["req_carrier_assignment"], exception_ids=["exc_no_carrier"]),
        step("tl_assign", "Assign carrier and vehicle", "form", "tms_planner", permission="transport.assign", requirement_ids=["req_carrier_assignment", "nfr_access"],
             reads_entity_ids=["ent_carrier", "ent_vehicle"], writes_entity_ids=["ent_transport_plan"], exception_ids=["exc_capacity_exceeded"]),
        step("tl_check_capacity", "Does the vehicle cover the load?", "branch", "tms_platform", outputs=["rule_capacity_check"], requirement_ids=["req_capacity"],
             reads_entity_ids=["ent_transport_plan", "ent_vehicle"], rule_ids=["rule_capacity_check"], exception_ids=["exc_capacity_exceeded"]),
        step("tl_capacity_issue", "Capacity exceeded", "exception", "tms_planner", requirement_ids=["req_capacity"], exception_ids=["exc_capacity_exceeded"]),
        step("tl_check_ready", "Has the warehouse released the goods?", "branch", "tms_platform", outputs=["rule_goods_ready"], requirement_ids=["req_dispatch"],
             reads_entity_ids=["ent_transport_request"], rule_ids=["rule_goods_ready"], exception_ids=["exc_goods_not_ready"]),
        step("tl_wait_goods", "Goods not released", "exception", "tms_dispatcher", requirement_ids=["req_dispatch"], exception_ids=["exc_goods_not_ready"]),
        step("tl_dispatch", "Dispatch", "action", "tms_dispatcher", permission="transport.dispatch", requirement_ids=["req_dispatch", "nfr_access"],
             reads_entity_ids=["ent_transport_plan"], writes_entity_ids=["ent_shipment"]),
        step("tl_track", "Record tracking events", "action", "tms_dispatcher", permission="tracking.write", requirement_ids=["req_tracking", "nfr_audit"],
             reads_entity_ids=["ent_shipment"], writes_entity_ids=["ent_tracking_event"], rule_ids=["rule_tracking_sequence"]),
        step("tl_check_delivery", "How did the delivery end?", "branch", "tms_platform", outputs=["rule_delivery_outcome"], requirement_ids=["req_exceptions", "req_delivery_pod"],
             reads_entity_ids=["ent_shipment", "ent_tracking_event"], rule_ids=["rule_delivery_outcome"], exception_ids=["exc_delivery_delayed"]),
        step("tl_pod", "Record proof of delivery", "form", "tms_carrier_partner", permission="pod.submit", requirement_ids=["req_delivery_pod"],
             reads_entity_ids=["ent_shipment"], writes_entity_ids=["ent_proof_of_delivery"], exception_ids=["exc_pod_missing"]),
        step("tl_check_pod", "Is proof of delivery recorded?", "branch", "tms_platform", outputs=["rule_pod_required"], requirement_ids=["req_delivery_pod"],
             reads_entity_ids=["ent_proof_of_delivery"], rule_ids=["rule_pod_required"], exception_ids=["exc_pod_missing"]),
        step("tl_pod_issue", "Proof of delivery missing", "exception", "tms_dispatcher", requirement_ids=["req_delivery_pod"], exception_ids=["exc_pod_missing"]),
        step("tl_delay_issue", "Delivery delayed or failed", "exception", "tms_dispatcher", requirement_ids=["req_exceptions"], exception_ids=["exc_delivery_delayed"]),
        step("tl_resolve", "Resolve the exception", "form", "tms_dispatcher", permission="exception.resolve", outputs=["rule_exception_resolution"], requirement_ids=["req_exceptions"],
             reads_entity_ids=["ent_shipment"], writes_entity_ids=["ent_transport_exception"], rule_ids=["rule_exception_resolution"]),
        step("tl_end_delivered", "Delivered and confirmed", "end", None, outcome="success"),
        step("tl_end_cancelled", "Transport cancelled", "end", None, outcome="cancelled"),
    ], "transitions": [
        edge("tl_t1", "tl_start", "tl_request"), edge("tl_t2", "tl_request", "tl_plan"), edge("tl_t3", "tl_plan", "tl_check_eligibility"),
        edge("tl_t4", "tl_check_eligibility", "tl_assign", "rule_carrier_eligibility", "ELIGIBLE"), edge("tl_t5", "tl_check_eligibility", "tl_no_carrier", "rule_carrier_eligibility", "NOT_ELIGIBLE"),
        edge("tl_t6", "tl_no_carrier", "tl_plan"), edge("tl_t7", "tl_assign", "tl_check_capacity"),
        edge("tl_t8", "tl_check_capacity", "tl_check_ready", "rule_capacity_check", "WITHIN_CAPACITY"), edge("tl_t9", "tl_check_capacity", "tl_capacity_issue", "rule_capacity_check", "EXCEEDS_CAPACITY"),
        edge("tl_t10", "tl_capacity_issue", "tl_assign"),
        edge("tl_t11", "tl_check_ready", "tl_dispatch", "rule_goods_ready", "READY"), edge("tl_t12", "tl_check_ready", "tl_wait_goods", "rule_goods_ready", "NOT_READY"),
        edge("tl_t13", "tl_wait_goods", "tl_check_ready"), edge("tl_t14", "tl_dispatch", "tl_track"), edge("tl_t15", "tl_track", "tl_check_delivery"),
        edge("tl_t16", "tl_check_delivery", "tl_pod", "rule_delivery_outcome", "DELIVERED"), edge("tl_t17", "tl_check_delivery", "tl_delay_issue", "rule_delivery_outcome", "DELAYED"),
        edge("tl_t18", "tl_check_delivery", "tl_delay_issue", "rule_delivery_outcome", "FAILED"), edge("tl_t19", "tl_pod", "tl_check_pod"),
        edge("tl_t20", "tl_check_pod", "tl_end_delivered", "rule_pod_required", "POD_RECORDED"), edge("tl_t21", "tl_check_pod", "tl_pod_issue", "rule_pod_required", "POD_MISSING"),
        edge("tl_t22", "tl_pod_issue", "tl_pod"), edge("tl_t23", "tl_delay_issue", "tl_resolve"),
        edge("tl_t24", "tl_resolve", "tl_track", "rule_exception_resolution", "RETRY_DELIVERY"), edge("tl_t25", "tl_resolve", "tl_end_cancelled", "rule_exception_resolution", "CANCEL_TRANSPORT"),
    ]}
    warehouse = {"version": 1, "id": "wf_warehouse_fulfilment", "name": "Warehouse fulfilment and handoff", "states": [
        step("wh_start", "An order line needs fulfilling", "start", None),
        step("wh_check_stock", "Is stock available?", "branch", "wms_platform", outputs=["rule_availability"], requirement_ids=["req_warehouse_fulfilment"],
             reads_entity_ids=["ent_order_line", "ent_warehouse"], rule_ids=["rule_availability"], exception_ids=["exc_stock_unavailable"]),
        step("wh_stock_issue", "Stock unavailable", "exception", "wms_inventory_manager", requirement_ids=["req_warehouse_fulfilment"], exception_ids=["exc_stock_unavailable"]),
        step("wh_allocate", "Allocate stock to the order line", "action", "wms_platform", requirement_ids=["req_warehouse_fulfilment"],
             reads_entity_ids=["ent_order_line", "ent_warehouse"], rule_ids=["rule_allocation"]),
        step("wh_pick", "Pick the goods", "form", "wms_operator", permission="pick.execute", requirement_ids=["req_warehouse_fulfilment"],
             reads_entity_ids=["ent_order_line", "ent_warehouse"], writes_entity_ids=["ent_pick_task"], exception_ids=["exc_pick_incomplete"]),
        step("wh_pack", "Pack the goods", "form", "wms_operator", permission="pack.execute", requirement_ids=["req_warehouse_fulfilment"],
             reads_entity_ids=["ent_pick_task"], writes_entity_ids=["ent_pack_unit"]),
        step("wh_check_complete", "Is everything packed?", "branch", "wms_platform", outputs=["rule_handoff_complete"], requirement_ids=["req_warehouse_handoff"],
             reads_entity_ids=["ent_pick_task", "ent_pack_unit"], rule_ids=["rule_handoff_complete"], exception_ids=["exc_pick_incomplete"]),
        step("wh_incomplete_issue", "Pick incomplete", "exception", "wms_operator", requirement_ids=["req_warehouse_handoff"], exception_ids=["exc_pick_incomplete"]),
        step("wh_handoff", "Hand off to transport", "form", "wms_operator", permission="handoff.create", requirement_ids=["req_warehouse_handoff", "nfr_audit"],
             reads_entity_ids=["ent_pack_unit"], writes_entity_ids=["ent_fulfilment_handoff", "ent_transport_request"]),
        step("wh_end_handed_off", "Handed off to transport", "end", None, outcome="success"),
        step("wh_end_unfulfilled", "Cannot be fulfilled", "end", None, outcome="failure"),
    ], "transitions": [
        edge("wh_t1", "wh_start", "wh_check_stock"), edge("wh_t2", "wh_check_stock", "wh_allocate", "rule_availability", "AVAILABLE"),
        edge("wh_t3", "wh_check_stock", "wh_stock_issue", "rule_availability", "INSUFFICIENT_STOCK"),
        edge("wh_t3b", "wh_check_stock", "wh_stock_issue", "rule_availability", "STOCK_UNKNOWN"),
        edge("wh_t3c", "wh_check_stock", "wh_stock_issue", "rule_availability", "NO_ROUTE"), edge("wh_t4", "wh_stock_issue", "wh_end_unfulfilled"),
        edge("wh_t5", "wh_allocate", "wh_pick"), edge("wh_t6", "wh_pick", "wh_pack"), edge("wh_t7", "wh_pack", "wh_check_complete"),
        edge("wh_t8", "wh_check_complete", "wh_handoff", "rule_handoff_complete", "COMPLETE"), edge("wh_t9", "wh_check_complete", "wh_incomplete_issue", "rule_handoff_complete", "INCOMPLETE"),
        edge("wh_t10", "wh_incomplete_issue", "wh_pick"), edge("wh_t11", "wh_handoff", "wh_end_handed_off"),
    ]}
    pack = {
        "id": "noordveld_transport", "usage": "source_reference", "version": "2026.10.19.1", "layer": "business", "company": COMPANY, "title": "Noordveld transport and warehouse (TMS/WMS)",
        "description": "Transport lifecycle and warehouse fulfilment workflows. Entities, relationships and roles come from the domain pack noordveld_machinery; "
                       "rules introduced here are assumptions and the open decisions stay open. Synthetic demonstration knowledge.",
        "synthetic": True, "domains": [{"id": "transport_warehouse", "name": "Transport and warehouse operations", "subdomains": ["Transport management", "Warehouse operations"],
                                        "keywords": ["transport", "tms", "dispatch", "carrier", "vehicle", "proof of delivery", "consignment", "warehouse", "wms", "picking", "packing", "handoff", "fulfilment"]}],
        "domain_id": "transport_warehouse", "capability": {"id": "cap_move_and_fulfil", "name": "Fulfil orders from the warehouse and move them to the customer"}, "depends_on": [],
        "business": {
            "requirements": requirements, "roles": roles(domain), "entities": entities(domain), "rules": rules, "exceptions": exceptions, "decisions": decisions,
            "integrations": [{"id": "int_carrier_tracking", "name": "Carrier tracking feed", "system": "Carrier tracking system", "direction": "inbound", "events": ["Tracking events"],
                              "entity_ids": ["ent_tracking_event"], "failure_handling": "", "contract_status": "deferred"}],
            "terms": [{"id": "term_handoff", "term": "Handoff", "definition": "The point where packed goods are released from the warehouse to transport."},
                      {"id": "term_pod", "term": "Proof of delivery", "definition": "The confirmation that a shipment reached the receiver."}]},
        "workflows": [transport, warehouse], "evidence": [],
    }
    return ReferencePack.model_validate(pack).model_dump(mode="json")


if __name__ == "__main__":
    data = build()
    OUT.write_text(json.dumps(data, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(data['business']['entities'])} entities, {len(data['workflows'])} workflows, "
          f"{sum(len(w['states']) for w in data['workflows'])} steps")
