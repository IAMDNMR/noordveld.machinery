"""Explicit synthetic execution fixture, not Noordveld policy or an approved customer design.

The runtime and generator contain no TMS IDs. This fixture is the input used to prove
the transport vertical. It deliberately does not rewrite the governed transport pack.
"""

from app.design_studio.discovery import blank_definition
from app.design_studio.approval import digest
from app.schemas.application_definition import ApplicationDefinition, ApprovalRecord


def synthetic_transport():
    raw = blank_definition().model_dump(mode="json")
    raw["id"] = "app_transport_runtime_demo"
    raw["revision"] = 1
    raw["metadata"]["name"] = "Transport Operations"
    raw["metadata"]["description"] = (
        "Synthetic execution reference. Policies here are test fixtures, not company policy."
    )
    roles = [
        ("planner", "Transport planner", ["transport.request", "transport.plan"]),
        ("warehouse", "Warehouse operator", ["warehouse.release"]),
        (
            "dispatcher",
            "Dispatcher",
            ["transport.dispatch", "transport.track", "transport.resolve"],
        ),
        ("carrier", "Carrier partner", ["delivery.confirm"]),
        ("reviewer", "Read-only reviewer", []),
    ]
    raw["business"]["roles"] = [
        {"id": "role_" + key, "name": name, "permissions": permissions}
        for key, name, permissions in roles
    ]

    def attr(id, name, type="string", **kwargs):
        return {"id": id, "name": name, "type": type, **kwargs}

    raw["business"]["entities"] = [
        {
            "id": "ent_carrier",
            "name": "Carriers",
            "attributes": [
                attr("carrier_code", "Carrier code", required=True, key=True),
                attr("name", "Carrier name", required=True),
                attr("eligible", "Eligible for this synthetic service", "boolean", required=True),
            ],
            "relationships": [],
        },
        {
            "id": "ent_vehicle",
            "name": "Vehicles",
            "attributes": [
                attr("vehicle_code", "Vehicle code", required=True, key=True),
                attr("capacity_kg", "Capacity (kg)", "decimal", required=True, minimum=1),
            ],
            "relationships": [],
        },
        {
            "id": "ent_shipment",
            "name": "Shipments",
            "description": "Transport requests, assignment, warehouse release, delivery and recovery.",
            "attributes": [
                attr("shipment_code", "Shipment reference", required=True, key=True),
                attr("destination", "Destination", required=True),
                attr("weight_kg", "Load weight (kg)", "decimal", required=True, minimum=1),
                attr("carrier_code", "Carrier"),
                attr("vehicle_code", "Vehicle"),
                attr("route", "Route"),
                attr(
                    "warehouse_ready",
                    "Warehouse released",
                    "boolean",
                    owner_role_id="role_warehouse",
                ),
                attr(
                    "tracking_status",
                    "Tracking status",
                    enum=["IN_TRANSIT", "DELIVERED", "DELAYED", "FAILED"],
                    owner_role_id="role_dispatcher",
                ),
                attr("received_by", "Received by", owner_role_id="role_carrier"),
                attr("pod_reference", "Proof of delivery reference", owner_role_id="role_carrier"),
                attr(
                    "resolution",
                    "Exception resolution",
                    enum=["RETRY", "CANCEL"],
                    owner_role_id="role_dispatcher",
                ),
            ],
            "relationships": [
                {
                    "id": "rel_carrier",
                    "name": "Assigned carrier",
                    "target": "ent_carrier",
                    "cardinality": "many_to_one",
                },
                {
                    "id": "rel_vehicle",
                    "name": "Assigned vehicle",
                    "target": "ent_vehicle",
                    "cardinality": "many_to_one",
                },
            ],
        },
    ]
    rule_source = {
        "kind": "synthetic_assumption",
        "reference": "Explicit isolated runtime test fixture; not a verified company policy.",
    }

    def rule(
        id,
        description,
        field,
        operator="present",
        value=None,
        other=None,
        outcomes=None,
        kind="compare",
    ):
        return {
            "id": id,
            "description": description,
            "type": "decision" if outcomes else "validation",
            "status": "assumption",
            "source": rule_source,
            "outcomes": outcomes or [],
            "execution": {
                "kind": kind,
                "field": field,
                "operator": operator,
                "value": value,
                "other_field": other,
                "pass_outcome": outcomes[0] if outcomes else None,
                "fail_outcome": outcomes[1] if outcomes else None,
            },
        }

    raw["business"]["rules"] = [
        rule("rule_route", "A route must be entered before assignment.", "ent_shipment.route"),
        rule(
            "rule_eligible",
            "The assigned carrier must be eligible in this synthetic fixture.",
            "ent_carrier.eligible",
            "eq",
            True,
        ),
        rule(
            "rule_capacity",
            "The assigned vehicle must cover the load.",
            "ent_vehicle.capacity_kg",
            "gte",
            other="ent_shipment.weight_kg",
            outcomes=["FITS", "OVER_CAPACITY"],
        ),
        rule(
            "rule_ready",
            "Warehouse release is required before dispatch.",
            "ent_shipment.warehouse_ready",
            "eq",
            True,
        ),
        rule(
            "rule_delivery",
            "Recorded tracking status selects the delivery path.",
            "ent_shipment.tracking_status",
            outcomes=["IN_TRANSIT", "DELIVERED", "DELAYED", "FAILED"],
            kind="value",
        ),
        rule("rule_receiver", "A receiver must be recorded.", "ent_shipment.received_by"),
        rule("rule_pod", "Proof of delivery must be recorded.", "ent_shipment.pod_reference"),
        rule(
            "rule_resolution",
            "An explicit dispatcher decision selects retry or cancellation.",
            "ent_shipment.resolution",
            outcomes=["RETRY", "CANCEL"],
            kind="value",
        ),
    ]
    for entity in raw["business"]["entities"]:
        entity["owner_role_id"] = "role_planner"
        for attribute in entity["attributes"]:
            attribute.setdefault("owner_role_id", "role_planner")
    states, edges = [], []

    def step(
        id,
        label,
        kind,
        role=None,
        permission=None,
        reads=None,
        writes=None,
        rules=None,
        outputs=None,
        outcome=None,
    ):
        states.append(
            {
                "id": id,
                "label": label,
                "kind": kind,
                "role_id": "role_" + role if role else None,
                "permission": permission,
                "reads_entity_ids": reads or [],
                "writes_entity_ids": writes or [],
                "rule_ids": rules or [],
                "outputs": outputs or [],
                "outcome": outcome,
            }
        )

    def edge(source, target, field=None, value=None):
        edges.append(
            {
                "id": "edge_" + str(len(edges) + 1),
                "source": source,
                "target": target,
                "condition": {"kind": "equals", "field": field, "value": value}
                if field
                else {"kind": "always"},
            }
        )

    step("st_start", "Start", "start")
    step(
        "st_request",
        "Validate transport request",
        "form",
        "planner",
        "transport.request",
        writes=["ent_shipment"],
    )
    step(
        "st_plan",
        "Plan route and assign carrier / vehicle",
        "form",
        "planner",
        "transport.plan",
        reads=["ent_shipment"],
        writes=["ent_carrier", "ent_vehicle"],
        rules=["rule_route", "rule_eligible"],
    )
    step(
        "st_capacity",
        "Check load capacity",
        "branch",
        rules=["rule_capacity"],
        outputs=["rule_capacity"],
    )
    step(
        "st_capacity_issue",
        "Resolve capacity exception",
        "exception",
        "planner",
        "transport.plan",
        reads=["ent_shipment"],
        writes=["ent_vehicle"],
    )
    step(
        "st_handoff",
        "Release warehouse handoff",
        "form",
        "warehouse",
        "warehouse.release",
        writes=["ent_shipment"],
        rules=["rule_ready"],
    )
    step(
        "st_dispatch",
        "Dispatch shipment",
        "action",
        "dispatcher",
        "transport.dispatch",
        reads=["ent_carrier", "ent_vehicle"],
        writes=["ent_shipment"],
        rules=["rule_ready", "rule_eligible"],
    )
    step(
        "st_tracking",
        "Record tracking update",
        "form",
        "dispatcher",
        "transport.track",
        writes=["ent_shipment"],
    )
    step(
        "st_delivery",
        "Evaluate delivery outcome",
        "branch",
        rules=["rule_delivery"],
        outputs=["rule_delivery"],
    )
    step(
        "st_exception",
        "Resolve delivery exception",
        "exception",
        "dispatcher",
        "transport.resolve",
        writes=["ent_shipment"],
        rules=["rule_resolution"],
        outputs=["rule_resolution"],
    )
    step(
        "st_pod",
        "Confirm delivery and proof",
        "form",
        "carrier",
        "delivery.confirm",
        writes=["ent_shipment"],
        rules=["rule_receiver", "rule_pod"],
    )
    step("st_delivered", "Delivered with proof", "end", outcome="success")
    step("st_cancelled", "Transport cancelled", "end", outcome="cancelled")
    for source, target in [
        ("st_start", "st_request"),
        ("st_request", "st_plan"),
        ("st_plan", "st_capacity"),
        ("st_capacity_issue", "st_plan"),
        ("st_handoff", "st_dispatch"),
        ("st_dispatch", "st_tracking"),
        ("st_tracking", "st_delivery"),
        ("st_pod", "st_delivered"),
    ]:
        edge(source, target)
    for target, value in [("st_handoff", "FITS"), ("st_capacity_issue", "OVER_CAPACITY")]:
        edge("st_capacity", target, "rule_capacity", value)
    for target, value in [
        ("st_tracking", "IN_TRANSIT"),
        ("st_pod", "DELIVERED"),
        ("st_exception", "DELAYED"),
        ("st_exception", "FAILED"),
    ]:
        edge("st_delivery", target, "rule_delivery", value)
    edge("st_exception", "st_tracking", "rule_resolution", "RETRY")
    edge("st_exception", "st_cancelled", "rule_resolution", "CANCEL")
    raw["workflows"] = ["wf_transport"]
    raw["workflow_definitions"] = [
        {
            "id": "wf_transport",
            "version": 1,
            "name": "Transport lifecycle",
            "states": states,
            "transitions": edges,
        }
    ]
    raw["business"]["brief"]["goal"] = (
        "Prove a synthetic transport lifecycle with persistent records and authorized actions."
    )
    raw["business"]["requirements"] = [
        {
            "id": "req_transport",
            "statement": "Execute the synthetic transport lifecycle with authorized, persistent actions.",
            "priority": "must",
            "status": "agreed",
            "acceptance_criteria": [
                {
                    "id": "ac_transport",
                    "statement": "Request, plan, assign, dispatch, track and confirm delivery or recover from an exception.",
                }
            ],
        }
    ]
    for state in states:
        state["requirement_ids"] = ["req_transport"]
        if state["kind"] == "branch":
            state["role_id"] = "role_planner"
    definition = ApplicationDefinition.model_validate(raw)
    # Test fixture approval only. No customer record or shared domain release is approved by this builder.
    definition.approvals = [
        ApprovalRecord(
            scope=scope,
            revision=1,
            content_sha256=digest(definition, scope),
            approved_by="synthetic_fixture_reviewer",
            approved_at="2026-10-15T00:00:00Z",
            comment="Isolated synthetic execution fixture only",
        )
        for scope in ("process", "design")
    ]
    return definition
