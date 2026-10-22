"""Catalog part B: warehouse management, transport management, manufacturing / machinery / spare parts."""
from __future__ import annotations

from catalog_dsl import A, Pack, S, rec, run


def warehouse() -> Pack:
    p = Pack("cat_warehouse", "wms", "Warehouse management", "Allocating, picking, packing and handing off customer orders from a warehouse.",
             deps=("core_foundations", "cat_inventory", "cat_ecommerce"), caps=("audit_history", "search_filter", "reporting_dashboards", "notifications"),
             domain_id="warehouse_management", capability="Order fulfilment",
             domain={"id": "warehouse_management", "name": "Warehouse management", "subdomains": ["Allocation", "Picking", "Packing", "Handoff"],
                     "keywords": ["warehouse", "wms", "picking", "pick list", "packing", "fulfilment", "fulfillment", "put-away", "putaway", "dispatch area", "goods out", "bin", "pallet"],
                     "description": "Getting ordered goods out of the building correctly."})
    p.role("lead", "Warehouse lead", [], ["Allocates stock, resolves shortages and releases packed orders"])
    p.role("picker", "Picker", [], ["Picks the goods for an order"])
    p.role("packer", "Packer", [], ["Packs and weighs picked goods"])
    p.entity("pick_list", "Pick list", "The work of picking one customer order from one warehouse location.",
             [A("status", "Status", req=True, enum=["OPEN", "PICKING", "PICKED", "PACKED", "HANDED_OFF"]), A("created_on", "Created on", "date", req=True)],
             [("order", "Order", "ent_eco_order", "many_to_one", True), ("location", "Warehouse location", "ent_core_location", "many_to_one", True)])
    p.entity("pick_line", "Pick line", "The quantity actually picked for one order line.",
             [A("quantity_picked", "Quantity picked", "decimal", req=True, min=0)],
             [("pick_list", "Pick list", "pick_list", "many_to_one", True), ("order_line", "Order line", "ent_eco_order_line", "many_to_one", True), ("stock_level", "Stock level", "ent_inv_stock_level", "many_to_one", True)])
    p.entity("pack_unit", "Pack unit", "A parcel, carton or pallet packed for one pick list.",
             [A("packages", "Number of packages", "integer", req=True, min=1), A("gross_weight_kg", "Gross weight (kg)", "decimal", req=True, min=0), A("packed_on", "Packed on", "date", req=True)],
             [("pick_list", "Pick list", "pick_list", "many_to_one", True)])
    p.rule("allocation", "Stock can be allocated to an order line only if on-hand stock covers the quantity.", "ent_inv_stock_level.on_hand", "gte", other="ent_eco_order_line.quantity", outcomes=["ALLOCATED", "SHORT"])
    p.rule("pick_complete", "A pick is complete when the quantity picked covers the ordered quantity.", "pick_line.quantity_picked", "gte", other="ent_eco_order_line.quantity", outcomes=["COMPLETE", "PARTIAL"])
    p.rule("weight", "A pack unit has a recorded weight before handoff.", "pack_unit.gross_weight_kg")
    r1 = p.req("fulfil", "Ordered goods are allocated, picked, packed and handed off.", ["Stock is allocated before picking starts.", "The picked quantity is checked against the order.", "A packed order has a weight and package count."])
    p.req("shortage", "Shortages and partial picks are visible and resolved, not hidden.", ["A short allocation or partial pick is handled as an exception."], "should")
    p.exc("shortage", "Allocation is short", "On-hand stock does not cover an order line.", "The lead resolves the shortage and allocation is checked again.", to=("fulfilment", "allocate"))
    p.exc("short_pick", "Pick is partial", "The picker found less than ordered.", "The lead decides how to continue and the pick is repeated.", to=("fulfilment", "pick"))
    p.dec("partial", "May an order ship in parts when stock is short, and is each part picked and handed off separately?", [p.rule_id("allocation")])
    p.flow("fulfilment", "Order fulfilment", [
        S("start", "Order ready for fulfilment", "start"),
        S("allocate", "Allocate stock", "form", "lead", reads=["ent_eco_order", "ent_eco_order_line", "ent_inv_stock_level", "ent_core_location"], writes=["pick_list"]),
        S("alloc_check", "Is the stock allocated?", "branch", rules=["allocation"], out=["allocation"]),
        S("shortage", "Resolve the shortage", "exception", "lead", writes=["pick_list"], exc=["shortage"]),
        S("pick", "Pick the goods", "form", "picker", reads=["ent_eco_order_line", "ent_inv_stock_level", "pick_list"], writes=["pick_line"]),
        S("pick_check", "Is the pick complete?", "branch", rules=["pick_complete"], out=["pick_complete"]),
        S("short_pick", "Resolve the partial pick", "exception", "lead", writes=["pick_line"], exc=["short_pick"]),
        S("pack", "Pack and weigh", "form", "packer", reads=["pick_list"], writes=["pack_unit"], rules=["weight"]),
        S("handoff", "Hand off for shipping", "action", "lead", writes=["pick_list"]), S("done", "Handed off", "end", outcome="success")],
        [("start", "allocate"), ("allocate", "alloc_check"), ("alloc_check", "pick", "allocation", "ALLOCATED"), ("alloc_check", "shortage", "allocation", "SHORT"), ("shortage", "allocate"),
         ("pick", "pick_check"), ("pick_check", "pack", "pick_complete", "COMPLETE"), ("pick_check", "short_pick", "pick_complete", "PARTIAL"), ("short_pick", "pick"),
         ("pack", "handoff"), ("handoff", "done")], [r1])
    p.term("pick", "Pick list", "The work of picking one order.", ["picking list", "pick ticket", "picking order"], "ent_wms_pick_list")
    p.term("pack", "Pack unit", "A parcel, carton or pallet packed for shipping.", ["parcel", "carton", "package", "colli"], "ent_wms_pack_unit")
    p.term("handoff", "Handoff", "The point where packed goods are released to transport.", ["release", "goods out", "dispatch release"])
    p.scenario(records=[
        rec("pick1", "ent_wms_pick_list", "role_wms_lead", {"status": "OPEN", "created_on": "2026-10-15"}, {"ent_eco_order": "order1", "ent_core_location": "loc1"}),
        rec("pickline1", "ent_wms_pick_line", "role_wms_picker", {"quantity_picked": 5}, {"ent_wms_pick_list": "pick1", "ent_eco_order_line": "line1", "ent_inv_stock_level": "stock1"}),
        rec("pack1", "ent_wms_pack_unit", "role_wms_packer", {"packages": 1, "gross_weight_kg": 6.4, "packed_on": "2026-10-15"}, {"ent_wms_pick_list": "pick1"})],
        flows=[run("wf_wms_fulfilment", {"ent_eco_order": "order1", "ent_eco_order_line": "line1", "ent_inv_stock_level": "stock1", "ent_core_location": "loc1",
                                         "ent_wms_pick_list": "pick1", "ent_wms_pick_line": "pickline1", "ent_wms_pack_unit": "pack1"})])
    return p


def transport() -> Pack:
    p = Pack("cat_transport", "tms", "Transport management", "Planning, dispatching, tracking and confirming the delivery of shipments.",
             deps=("core_foundations", "cat_ecommerce", "cat_warehouse"), caps=("audit_history", "search_filter", "reporting_dashboards", "notifications", "external_integration"),
             domain_id="transport_management", capability="Shipment management",
             domain={"id": "transport_management", "name": "Transport management", "subdomains": ["Planning", "Dispatch", "Tracking", "Proof of delivery"],
                     "keywords": ["transport", "tms", "shipment", "shipments", "carrier", "freight", "fleet", "haulage", "logistics", "delivery", "deliveries", "dispatch", "route", "driver", "vehicle", "tracking", "proof of delivery"],
                     "description": "Moving goods from the warehouse to the customer."})
    p.role("planner", "Transport planner", [], ["Plans shipments and maintains carriers and vehicles"])
    p.role("dispatcher", "Dispatcher", [], ["Dispatches, tracks and resolves delivery exceptions"])
    p.role("driver", "Driver or carrier partner", [], ["Confirms delivery with proof"])
    p.entity("carrier", "Carrier", "A company or fleet that moves goods.",
             [A("name", "Name", req=True, maxlen=120), A("mode", "Mode", req=True, enum=["ROAD", "RAIL", "SEA", "AIR"]), A("status", "Status", req=True, enum=["ACTIVE", "SUSPENDED"])], owner="planner")
    p.entity("vehicle", "Vehicle", "A vehicle a carrier uses, with its load capacity.",
             [A("plate", "Registration", req=True, maxlen=20), A("capacity_kg", "Capacity (kg)", "decimal", req=True, min=1)], [("carrier", "Carrier", "carrier", "many_to_one", True)], owner="planner")
    p.entity("shipment", "Shipment", "One movement of goods for a customer order.",
             [A("destination", "Destination", req=True, maxlen=200), A("weight_kg", "Load weight (kg)", "decimal", req=True, min=1),
              A("planned_departure", "Planned departure", "datetime"), A("planned_arrival", "Planned arrival", "datetime"),
              A("status", "Status", req=True, enum=["PLANNED", "DISPATCHED", "IN_TRANSIT", "DELIVERED", "FAILED"]),
              A("tracking_status", "Tracking status", enum=["IN_TRANSIT", "DELIVERED", "DELAYED", "FAILED"], owner="role_tms_dispatcher"),
              A("resolution", "Exception resolution", enum=["RETRY", "CANCEL"], owner="role_tms_dispatcher"),
              A("received_by", "Received by", maxlen=120, owner="role_tms_driver"), A("pod_reference", "Proof of delivery reference", maxlen=120, owner="role_tms_driver")],
             [("order", "Order", "ent_eco_order", "many_to_one", True), ("pack_unit", "Pack unit", "ent_wms_pack_unit", "many_to_one"), ("carrier", "Carrier", "carrier", "many_to_one"), ("vehicle", "Vehicle", "vehicle", "many_to_one")])
    p.rule("carrier_active", "Only an active carrier may be assigned.", "carrier.status", "eq", "ACTIVE")
    p.rule("capacity", "The assigned vehicle must cover the shipment weight.", "vehicle.capacity_kg", "gte", other="shipment.weight_kg", outcomes=["FITS", "OVER_CAPACITY"])
    p.rule("tracking", "The recorded tracking status selects the delivery path.", "shipment.tracking_status", kind="value", outcomes=["IN_TRANSIT", "DELIVERED", "DELAYED", "FAILED"])
    p.rule("receiver", "The receiver is recorded before delivery is confirmed.", "shipment.received_by")
    p.rule("pod", "Proof of delivery is recorded before delivery is confirmed.", "shipment.pod_reference")
    p.rule("resolution", "A dispatcher's recorded choice selects retry or cancellation.", "shipment.resolution", kind="value", outcomes=["RETRY", "CANCEL"])
    r1 = p.req("deliver", "Shipments are planned, assigned, dispatched, tracked and confirmed with proof of delivery.", ["A planner assigns an active carrier and a vehicle that fits the load.", "A dispatcher records tracking updates.", "Delivery is confirmed with a receiver and a proof reference."])
    p.req("recover", "Delayed or failed deliveries are resolved explicitly.", ["A delay or failure leads to a recorded retry or cancellation."], "should")
    p.exc("overload", "Load exceeds vehicle capacity", "The assigned vehicle cannot carry the shipment.", "The planner changes the vehicle or the load and capacity is checked again.", to=("shipment", "assign"))
    p.exc("failed_delivery", "Delivery delayed or failed", "Tracking reports a delay or a failed delivery.", "The dispatcher records a retry or cancels the shipment.", to=("shipment", "track"))
    p.dec("delay", "How late is late? When does a delay become an exception, and who is told?", [p.rule_id("tracking")])
    p.dec("carrier", "Who selects the carrier: the planner, an automatic rule, or a customer preference, and on what criteria?", [p.rule_id("carrier_active")])
    p.integration("tracking_feed", "Carrier tracking feed", "Carrier systems", "inbound", ["Tracking event received"], ["shipment"], "Not connected: tracking is recorded by the dispatcher.")
    p.flow("shipment", "Shipment delivery", [
        S("start", "Shipment requested", "start"), S("plan", "Plan the shipment", "form", "planner", reads=["ent_eco_order"], writes=["shipment"]),
        S("assign", "Assign carrier and vehicle", "form", "planner", reads=["carrier", "vehicle"], writes=["shipment"], rules=["carrier_active"]),
        S("cap", "Does the load fit?", "branch", rules=["capacity"], out=["capacity"]), S("replan", "Resolve the overload", "exception", "planner", writes=["shipment"], exc=["overload"]),
        S("dispatch", "Dispatch the shipment", "action", "dispatcher", reads=["carrier", "vehicle"], writes=["shipment"]),
        S("track", "Record a tracking update", "form", "dispatcher", writes=["shipment"]), S("delivery", "Delivery outcome", "branch", rules=["tracking"], out=["tracking"]),
        S("resolve", "Resolve the delivery exception", "exception", "dispatcher", writes=["shipment"], rules=["resolution"], out=["resolution"], exc=["failed_delivery"]),
        S("pod", "Confirm delivery and proof", "form", "driver", writes=["shipment"], rules=["receiver", "pod"]),
        S("done", "Delivered with proof", "end", outcome="success"), S("cancelled", "Shipment cancelled", "end", outcome="cancelled")],
        [("start", "plan"), ("plan", "assign"), ("assign", "cap"), ("cap", "dispatch", "capacity", "FITS"), ("cap", "replan", "capacity", "OVER_CAPACITY"), ("replan", "assign"),
         ("dispatch", "track"), ("track", "delivery"), ("delivery", "track", "tracking", "IN_TRANSIT"), ("delivery", "pod", "tracking", "DELIVERED"), ("delivery", "resolve", "tracking", "DELAYED"),
         ("delivery", "resolve", "tracking", "FAILED"), ("resolve", "track", "resolution", "RETRY"), ("resolve", "cancelled", "resolution", "CANCEL"), ("pod", "done")], [r1])
    # Per-task UI contracts: sharing Shipment data does not mean sharing one giant form.
    p.version = "2026.10.2"
    task_inputs = {
        "plan": (["destination", "weight_kg", "planned_departure", "planned_arrival", "status"], ["order", "pack_unit"]),
        "assign": ([], ["carrier", "vehicle"]),
        "replan": (["weight_kg"], ["vehicle"]),
        "dispatch": (["status"], []),
        "track": (["tracking_status"], []),
        "resolve": (["resolution"], []),
        "pod": (["received_by", "pod_reference"], []),
    }
    for state in p.workflows[-1]["states"]:
        key = state["id"].removeprefix("st_tms_shipment_")
        if key in task_inputs:
            fields, relationships = task_inputs[key]
            state["input_fields"] = {p.eid("shipment"): fields}
            state["input_relationships"] = {p.eid("shipment"): [f"rel_tms_shipment_{item}" for item in relationships]}
    p.term("shipment", "Shipment", "One movement of goods for a customer order.", ["consignment", "load", "delivery", "freight"], "ent_tms_shipment")
    p.term("carrier", "Carrier", "A company or fleet that moves goods.", ["haulier", "transporter", "logistics provider", "3PL"], "ent_tms_carrier")
    p.term("pod", "Proof of delivery", "Confirmation that a shipment reached the receiver.", ["POD", "delivery receipt", "signed delivery note"])
    p.scenario(records=[
        rec("carrier1", "ent_tms_carrier", "role_tms_planner", {"name": "Harbour Haulage (synthetic)", "mode": "ROAD", "status": "ACTIVE"}, shared=True),
        rec("vehicle1", "ent_tms_vehicle", "role_tms_planner", {"plate": "TX-123-NL", "capacity_kg": 1200}, {"ent_tms_carrier": "carrier1"}, shared=True),
        rec("ship1", "ent_tms_shipment", "role_tms_planner", {"destination": "Northwind Works, Utrecht", "weight_kg": 640, "status": "PLANNED"}, {"ent_eco_order": "order1", "ent_tms_carrier": "carrier1", "ent_tms_vehicle": "vehicle1"})],
        flows=[run("wf_tms_shipment", {"ent_eco_order": "order1", "ent_tms_shipment": "ship1", "ent_tms_carrier": "carrier1", "ent_tms_vehicle": "vehicle1"},
                   {"track": [{"record": "ship1", "role": "role_tms_dispatcher", "values": {"tracking_status": "DELIVERED"}}],
                    "pod": [{"record": "ship1", "role": "role_tms_driver", "values": {"received_by": "J. de Vries", "pod_reference": "POD-4471"}}]})])
    return p


def manufacturing() -> Pack:
    p = Pack("cat_manufacturing", "mfg", "Manufacturing, machinery and spare parts", "Machines in service, their parts, and the work orders that build, maintain or repair them.",
             deps=("core_foundations", "cat_inventory"), caps=("audit_history", "search_filter", "document_handling", "reporting_dashboards"),
             domain_id="manufacturing_machinery", capability="Work order management",
             domain={"id": "manufacturing_machinery", "name": "Manufacturing, machinery and spare parts", "subdomains": ["Machine register", "Bill of materials", "Work orders", "Quality inspection"],
                     "keywords": ["manufacturing", "machinery", "machine", "machines", "spare part", "spare parts", "work order", "maintenance", "production", "bill of materials", "bom", "equipment", "asset", "inspection", "shop floor"],
                     "description": "Building, maintaining and repairing machines and keeping the right parts."})
    p.role("planner", "Maintenance and production planner", [], ["Plans work orders and maintains the machine register"])
    p.role("technician", "Technician", [], ["Carries out work orders"])
    p.role("quality", "Quality inspector", [], ["Inspects finished work"])
    p.entity("machine", "Machine", "A machine the company builds, owns or services.",
             [A("serial_no", "Serial number", req=True, maxlen=60), A("model", "Model", req=True, maxlen=80), A("installed_on", "Installed on", "date"),
              A("status", "Status", req=True, enum=["IN_SERVICE", "DOWN", "RETIRED"]), A("warranty_end", "Warranty ends", "date")],
             [("customer", "Owner", "ent_core_customer", "many_to_one")], owner="planner")
    p.entity("bom_line", "Machine part", "A part a machine needs, and how many (its bill of materials line).",
             [A("quantity", "Quantity per machine", "decimal", req=True, min=0)],
             [("machine", "Machine", "machine", "many_to_one", True), ("item", "Part", "ent_core_item", "many_to_one", True)], owner="planner")
    p.entity("work_order", "Work order", "A job to build, maintain or repair one machine.",
             [A("kind", "Kind", req=True, enum=["PRODUCTION", "MAINTENANCE", "REPAIR"]), A("description", "Work to do", req=True, maxlen=500), A("planned_start", "Planned start", "date"),
              A("planned_hours", "Planned hours", "decimal", min=0), A("status", "Status", req=True, enum=["PLANNED", "IN_PROGRESS", "INSPECTION", "DONE"]),
              A("inspection_result", "Inspection result", enum=["PASS", "FAIL"], owner="role_mfg_quality"), A("rework_note", "Rework note", maxlen=500)],
             [("machine", "Machine", "machine", "many_to_one", True)])
    p.rule("scope", "A work order states the work to do.", "work_order.description")
    p.rule("material", "A work order can start only if on-hand stock covers the parts it needs.", "ent_inv_stock_level.on_hand", "gte", other="bom_line.quantity", outcomes=["AVAILABLE", "SHORT"])
    p.rule("inspection", "The inspector's recorded result decides whether work is accepted.", "work_order.inspection_result", kind="value", outcomes=["PASS", "FAIL"])
    r1 = p.req("work", "Work orders are planned against machines and parts, carried out, inspected and closed.", ["A planner creates a work order for a machine.", "Parts availability is checked before work starts.", "Work is accepted only after a passing inspection."])
    p.req("register", "The machines in service and the parts they need are on record.", ["A machine has a serial number, model and warranty end date.", "A machine's parts list can be maintained."], "should")
    p.exc("part_shortage", "Part is not available", "On-hand stock does not cover a needed part.", "The planner expedites the part or re-plans the work.", to=("work_order", "plan"))
    p.exc("failed_inspection", "Inspection failed", "The inspector records a failing result.", "A technician reworks and the work is inspected again.", to=("work_order", "inspect"))
    p.dec("inspection", "What inspection criteria define a pass for each kind of work?", [p.rule_id("inspection")])
    p.flow("work_order", "Work order", [
        S("start", "Work requested", "start"),
        S("plan", "Plan the work order", "form", "planner", reads=["machine", "bom_line", "ent_inv_stock_level"], writes=["work_order"], rules=["scope"]),
        S("material", "Are the parts available?", "branch", rules=["material"], out=["material"]), S("expedite", "Expedite the missing part", "exception", "planner", writes=["work_order"], exc=["part_shortage"]),
        S("execute", "Carry out the work", "form", "technician", writes=["work_order"]), S("inspect", "Inspect the work", "form", "quality", writes=["work_order"]),
        S("verdict", "Inspection result", "branch", rules=["inspection"], out=["inspection"]), S("rework", "Rework", "exception", "technician", writes=["work_order"], exc=["failed_inspection"]),
        S("close", "Close the work order", "action", "planner", writes=["work_order"]), S("done", "Work completed", "end", outcome="success")],
        [("start", "plan"), ("plan", "material"), ("material", "execute", "material", "AVAILABLE"), ("material", "expedite", "material", "SHORT"), ("expedite", "plan"),
         ("execute", "inspect"), ("inspect", "verdict"), ("verdict", "close", "inspection", "PASS"), ("verdict", "rework", "inspection", "FAIL"), ("rework", "inspect"), ("close", "done")], [r1])
    p.term("machine", "Machine", "A machine the company builds, owns or services.", ["asset", "equipment", "unit", "installed base"], "ent_mfg_machine")
    p.term("part", "Spare part", "A part kept to repair or maintain machines.", ["replacement part", "service part", "consumable", "component"], "ent_mfg_bom_line")
    p.term("work_order", "Work order", "A job to build, maintain or repair a machine.", ["job card", "maintenance order", "repair order", "service order"], "ent_mfg_work_order")
    p.term("bom", "Bill of materials", "The parts a machine is made of or needs.", ["BOM", "parts list"])
    p.scenario(records=[
        rec("machine1", "ent_mfg_machine", "role_mfg_planner", {"serial_no": "HX-200-0417", "model": "HX-200", "installed_on": "2025-03-01", "status": "IN_SERVICE", "warranty_end": "2027-03-01"}, {"ent_core_customer": "cust1"}, shared=True),
        rec("bom1", "ent_mfg_bom_line", "role_mfg_planner", {"quantity": 2}, {"ent_mfg_machine": "machine1", "ent_core_item": "item1"}, shared=True),
        rec("wo1", "ent_mfg_work_order", "role_mfg_planner", {"kind": "MAINTENANCE", "description": "Replace the hydraulic hoses", "planned_start": "2026-10-20", "planned_hours": 3, "status": "PLANNED"}, {"ent_mfg_machine": "machine1"})],
        flows=[run("wf_mfg_work_order", {"ent_mfg_machine": "machine1", "ent_mfg_bom_line": "bom1", "ent_inv_stock_level": "stock1", "ent_mfg_work_order": "wo1"},
                   {"inspect": [{"record": "wo1", "role": "role_mfg_quality", "values": {"inspection_result": "PASS"}}]})])
    return p


def all_packs() -> list[Pack]:
    return [warehouse(), transport(), manufacturing()]
