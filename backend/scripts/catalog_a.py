"""Catalog part A: shared foundations, reusable capabilities, inventory, e-commerce / order management."""
from __future__ import annotations

from catalog_dsl import A, Pack, S, rec, run


def core() -> Pack:
    p = Pack("core_foundations", "core", "Core business foundations", "Customers, suppliers, items and locations that every domain reuses, so each concept is modelled once.",
             layer="reusable", caps=("identity_access", "audit_history", "search_filter"))
    p.role("steward", "Master data steward", ["core.maintain"], ["Keeps customers, suppliers, items and locations correct"])
    p.entity("customer", "Customer", "A person or organization that buys from the company.",
             [A("name", "Name", req=True, maxlen=120), A("email", "Email", fmt="email", sens="personal"), A("phone", "Phone", fmt="phone", sens="personal"),
              A("country", "Country", maxlen=60), A("segment", "Segment", enum=["SMALL", "MID", "ENTERPRISE"])], owner="steward")
    p.entity("supplier", "Supplier", "An organization the company buys from.",
             [A("name", "Name", req=True, maxlen=120), A("email", "Email", fmt="email", sens="personal"), A("country", "Country", maxlen=60),
              A("status", "Status", req=True, enum=["ACTIVE", "ON_HOLD"])], owner="steward")
    p.entity("item", "Item", "Something the company stocks, sells, buys or services: a product, part or material.",
             [A("sku", "Item code", req=True, maxlen=60), A("name", "Name", req=True, maxlen=160), A("uom", "Unit of measure", req=True, enum=["EA", "KG", "M", "L", "BOX"]),
              A("unit_cost", "Unit cost", "decimal", min=0), A("status", "Status", req=True, enum=["ACTIVE", "DISCONTINUED"])], owner="steward")
    p.entity("location", "Location", "A place where the company keeps or handles things.",
             [A("name", "Name", req=True, maxlen=120), A("kind", "Kind", req=True, enum=["WAREHOUSE", "SITE", "DEPOT", "STORE"]), A("city", "City", maxlen=80), A("country", "Country", maxlen=60)], owner="steward")
    p.term("customer", "Customer", "A person or organization that buys from the company.", ["client", "account", "buyer"], "ent_core_customer")
    p.term("supplier", "Supplier", "An organization the company buys from.", ["vendor", "provider"], "ent_core_supplier")
    p.term("item", "Item", "Something the company stocks, sells, buys or services.", ["product", "article", "part", "SKU", "material"], "ent_core_item")
    p.term("location", "Location", "A place where the company keeps or handles things.", ["site", "warehouse", "depot", "facility", "store"], "ent_core_location")
    p.scenario(records=[
        rec("cust1", "ent_core_customer", "role_core_steward", {"name": "Northwind Works (synthetic)", "email": "buyer@northwind.example", "country": "NL", "segment": "MID"}, shared=True),
        rec("sup1", "ent_core_supplier", "role_core_steward", {"name": "Delta Components (synthetic)", "country": "DE", "status": "ACTIVE"}, shared=True),
        rec("item1", "ent_core_item", "role_core_steward", {"sku": "HYD-HOSE-12", "name": "Hydraulic hose 12 mm", "uom": "EA", "unit_cost": 18.5, "status": "ACTIVE"}, shared=True),
        rec("loc1", "ent_core_location", "role_core_steward", {"name": "Central warehouse", "kind": "WAREHOUSE", "city": "Rotterdam", "country": "NL"}, shared=True),
    ], flows=[])
    return p


def tasks() -> Pack:
    p = Pack("cap_task_management", "task", "Task management capability", "Assigning, tracking and completing units of work.", layer="reusable",
             caps=("task_management", "audit_history", "identity_access"))
    p.role("coordinator", "Task coordinator", [], ["Creates and assigns tasks"])
    p.role("worker", "Task assignee", [], ["Works on and completes assigned tasks"])
    p.entity("task", "Task", "A unit of work with an owner, a due date and a status.",
             [A("title", "Title", req=True, maxlen=200), A("description", "Description", maxlen=1000), A("priority", "Priority", req=True, enum=["LOW", "NORMAL", "HIGH"]),
              A("status", "Status", req=True, enum=["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"]), A("due_date", "Due date", "date"), A("assignee", "Assigned to", maxlen=120)])
    due = p.rule("due", "A task needs a due date before it is assigned.", "task.due_date")
    result = p.rule("result", "The recorded task status decides how the task ends.", "task.status", kind="value", outcomes=["DONE", "CANCELLED"])
    r1 = p.req("track", "Work can be created, assigned and tracked as tasks.", ["A coordinator creates a task with a priority.", "An assignee can see and complete it."])
    p.exc("blocked", "Task cannot proceed", "The assignee cannot continue because something outside their control is missing.", "The coordinator reassigns or cancels the task.", to=("lifecycle", "work"))
    p.flow("lifecycle", "Task lifecycle", [
        S("start", "Work identified", "start"), S("create", "Create the task", "form", "coordinator", writes=["task"]),
        S("assign", "Assign the task", "form", "coordinator", writes=["task"], rules=["due"]), S("work", "Work on the task", "form", "worker", writes=["task"]),
        S("result", "Task result", "branch", rules=["result"], out=["result"]), S("done", "Task completed", "end", outcome="success"), S("cancelled", "Task cancelled", "end", outcome="cancelled")],
        [("start", "create"), ("create", "assign"), ("assign", "work"), ("work", "result"), ("result", "done", "result", "DONE"), ("result", "cancelled", "result", "CANCELLED")], [r1])
    p.term("task", "Task", "A unit of work with an owner, a due date and a status.", ["to-do", "action item", "assignment", "job"], "ent_task_task")
    p.scenario(records=[rec("task1", "ent_task_task", "role_task_coordinator", {"title": "Prepare the quarterly stock review", "priority": "NORMAL", "status": "OPEN", "due_date": "2026-11-30", "assignee": "Sam"})],
               flows=[run("wf_task_lifecycle", {"ent_task_task": "task1"}, {"work": [{"record": "task1", "role": "role_task_worker", "values": {"status": "DONE"}}]})])
    return p


def approvals() -> Pack:
    p = Pack("cap_approvals", "apr", "Approvals capability", "A request that a different person must approve or reject before work continues.", layer="reusable",
             caps=("approval_workflow", "audit_history", "identity_access"))
    p.role("requester", "Requester", [], ["Asks for approval"])
    p.role("approver", "Approver", [], ["Decides approval requests"], ["Approval requests"])
    p.entity("request", "Approval request", "Something that needs a decision from someone other than the requester.",
             [A("subject", "Subject", req=True, maxlen=200), A("reason", "Reason", maxlen=500), A("amount", "Amount", "decimal", min=0), A("requested_on", "Requested on", "date", req=True),
              A("decision", "Decision", enum=["PENDING", "APPROVED", "REJECTED"], owner="role_apr_approver"), A("decision_note", "Decision note", maxlen=500, owner="role_apr_approver")])
    decision = p.rule("decision", "The approver's recorded decision selects what happens next.", "request.decision", kind="value", outcomes=["APPROVED", "REJECTED"])
    r1 = p.req("decide", "A request is decided by a person other than the requester, and the decision is recorded.", ["The requester cannot approve their own request.", "The decision and its time are in the history."])
    p.flow("approval", "Approval", [
        S("start", "Approval needed", "start"), S("submit", "Submit the request", "form", "requester", writes=["request"]),
        S("decide", "Decide the request", "approval", "approver", writes=["request"]), S("verdict", "Decision", "branch", rules=["decision"], out=["decision"]),
        S("approved", "Approved", "end", outcome="success"), S("rejected", "Rejected", "end", outcome="failure")],
        [("start", "submit"), ("submit", "decide"), ("decide", "verdict"), ("verdict", "approved", "decision", "APPROVED"), ("verdict", "rejected", "decision", "REJECTED")], [r1])
    p.term("approval", "Approval", "A decision by someone other than the requester that lets work continue.", ["sign-off", "authorisation", "authorization", "release"], "ent_apr_request")
    p.scenario(records=[rec("apr1", "ent_apr_request", "role_apr_requester", {"subject": "Extra budget for the pilot", "amount": 1800, "requested_on": "2026-10-15"})],
               flows=[run("wf_apr_approval", {"ent_apr_request": "apr1"}, {"decide": [{"record": "apr1", "role": "role_apr_approver", "values": {"decision": "APPROVED"}}]}, "approved")])
    return p


def documents() -> Pack:
    p = Pack("cap_documents", "doc", "Document handling capability", "Keeping references to the documents a process depends on. File storage is not implemented.", layer="reusable",
             caps=("document_handling", "audit_history", "identity_access"))
    p.role("curator", "Document curator", [], ["Registers and publishes documents"])
    p.entity("document", "Document", "A reference to a document held in another system.",
             [A("title", "Title", req=True, maxlen=200), A("kind", "Kind", req=True, enum=["CONTRACT", "INVOICE", "DRAWING", "MANUAL", "CERTIFICATE", "OTHER"]),
              A("reference", "Where it is kept", req=True, maxlen=300, desc="A link or path in the system that holds the file."), A("linked_to", "Linked to", maxlen=200),
              A("status", "Status", req=True, enum=["DRAFT", "CURRENT", "SUPERSEDED"]), A("valid_until", "Valid until", "date")], owner="curator")
    p.integration("storage", "Document file storage", "Document store", "bidirectional", ["Document uploaded", "Document retrieved"], ["document"], "Not connected: only the reference is stored.")
    current = p.rule("current", "A document must be marked current to be published.", "document.status", "eq", "CURRENT")
    r1 = p.req("register", "Documents are registered with where they are kept and published when current.", ["A curator registers a document reference.", "Only a current document is published."], "should")
    p.flow("register", "Register a document", [
        S("start", "Document received", "start"), S("register", "Register the document", "form", "curator", writes=["document"]),
        S("publish", "Publish the document", "action", "curator", writes=["document"], rules=["current"]), S("done", "Document published", "end", outcome="success")],
        [("start", "register"), ("register", "publish"), ("publish", "done")], [r1])
    p.term("document", "Document", "A reference to a document held in another system.", ["file", "attachment", "paperwork", "record"], "ent_doc_document")
    p.scenario(records=[rec("doc1", "ent_doc_document", "role_doc_curator", {"title": "Service manual HX-200", "kind": "MANUAL", "reference": "dms://manuals/hx-200", "status": "DRAFT"})],
               flows=[run("wf_doc_register", {"ent_doc_document": "doc1"}, {"publish": [{"record": "doc1", "role": "role_doc_curator", "values": {"status": "CURRENT"}}]})])
    return p


def inventory() -> Pack:
    p = Pack("cat_inventory", "inv", "Inventory and supply chain", "Stock levels, counts and movements, with approval of significant count differences.",
             deps=("core_foundations",), caps=("audit_history", "search_filter", "approval_workflow", "reporting_dashboards"), domain_id="inventory_supply_chain", capability="Inventory control",
             domain={"id": "inventory_supply_chain", "name": "Inventory and supply chain", "subdomains": ["Stock control", "Cycle counting", "Replenishment"],
                     "keywords": ["inventory", "stock", "stocktake", "replenishment", "reorder", "supply chain", "on hand", "cycle count", "stock level", "safety stock"],
                     "description": "Knowing what is on hand where, and keeping it right."})
    p.role("clerk", "Stock clerk", [], ["Counts stock and posts movements"])
    p.role("planner", "Inventory planner", [], ["Investigates disputed counts"])
    p.role("manager", "Inventory manager", [], ["Approves significant count differences"], ["Stock count differences"])
    p.entity("stock_level", "Stock level", "How much of an item is on hand at a location.",
             [A("on_hand", "On hand", "decimal", req=True, min=0), A("reserved", "Reserved", "decimal", min=0), A("reorder_point", "Reorder point", "decimal", min=0)],
             [("item", "Item", "ent_core_item", "many_to_one", True), ("location", "Location", "ent_core_location", "many_to_one", True)], owner="clerk")
    p.entity("stock_count", "Stock count", "A physical count of one stock level, and how it differs from the system.",
             [A("counted_qty", "Counted quantity", "decimal", req=True, min=0), A("counted_on", "Counted on", "date", req=True), A("variance", "Difference (units, absolute)", "decimal", req=True, min=0),
              A("reason", "Reason for the difference", maxlen=300), A("decision", "Decision", enum=["PENDING", "APPROVED", "REJECTED"], owner="role_inv_manager")],
             [("stock_level", "Stock level", "stock_level", "many_to_one", True)])
    p.entity("stock_movement", "Stock movement", "Stock received, issued, transferred or adjusted.",
             [A("kind", "Kind", req=True, enum=["RECEIPT", "ISSUE", "TRANSFER", "ADJUSTMENT"]), A("quantity", "Quantity", "decimal", req=True, min=0), A("moved_on", "Moved on", "date", req=True)],
             [("item", "Item", "ent_core_item", "many_to_one", True), ("location", "Location", "ent_core_location", "many_to_one", True)])
    p.rule("variance", "A count difference of more than 5 units needs approval before stock is adjusted.", "stock_count.variance", "lte", 5, outcomes=["WITHIN_TOLERANCE", "NEEDS_APPROVAL"])
    p.rule("reason_given", "A reason is recorded before a difference is approved.", "stock_count.reason")
    p.rule("decision", "The manager's decision selects what happens to the count.", "stock_count.decision", kind="value", outcomes=["APPROVED", "REJECTED"])
    r1 = p.req("count", "Stock is counted, and significant differences are approved before stock levels change.", ["A clerk records a count and its difference.", "A difference above tolerance needs a manager's approval.", "An approved count updates the stock level and writes a movement."])
    p.req("visibility", "Current stock by item and location can be found quickly.", ["Stock levels can be searched by item or location."], "should")
    p.exc("count_disputed", "Count disputed", "The manager rejects a count because the difference is not credible.", "A planner investigates and the stock is counted again.", to=("count", "count"))
    p.exc("negative_stock", "Stock would go negative", "A movement would take on-hand stock below zero.", "The movement is held until the record is corrected.", to=("count", "post"))
    p.dec("tolerance", "What count difference may a clerk post without approval, and does it differ by item value?", [p.rule_id("variance")])
    p.flow("count", "Stock count and adjustment", [
        S("start", "Count scheduled", "start"), S("count", "Count the stock", "form", "clerk", reads=["stock_level"], writes=["stock_count"]),
        S("tol", "Within tolerance?", "branch", rules=["variance"], out=["variance"]),
        S("approve", "Approve the difference", "approval", "manager", writes=["stock_count"], rules=["reason_given"]),
        S("verdict", "Manager's decision", "branch", rules=["decision"], out=["decision"]),
        S("recount", "Investigate and recount", "exception", "planner", writes=["stock_count"], exc=["count_disputed"]),
        S("post", "Post the stock adjustment", "action", "clerk", reads=["stock_count"], writes=["stock_level", "stock_movement"]), S("done", "Stock updated", "end", outcome="success")],
        [("start", "count"), ("count", "tol"), ("tol", "post", "variance", "WITHIN_TOLERANCE"), ("tol", "approve", "variance", "NEEDS_APPROVAL"), ("approve", "verdict"),
         ("verdict", "post", "decision", "APPROVED"), ("verdict", "recount", "decision", "REJECTED"), ("recount", "count"), ("post", "done")], [r1])
    p.term("stock", "Stock level", "How much of an item is on hand at a location.", ["inventory level", "stock on hand", "on-hand quantity"], "ent_inv_stock_level")
    p.term("count", "Stock count", "A physical count compared with the system.", ["stocktake", "cycle count", "physical inventory"], "ent_inv_stock_count")
    p.term("reorder", "Reorder point", "The stock level at which replenishment is triggered.", ["minimum stock", "safety stock level"])
    p.scenario(records=[
        rec("stock1", "ent_inv_stock_level", "role_inv_clerk", {"on_hand": 50, "reserved": 0, "reorder_point": 10}, {"ent_core_item": "item1", "ent_core_location": "loc1"}, shared=True),
        rec("count_ok", "ent_inv_stock_count", "role_inv_clerk", {"counted_qty": 48, "counted_on": "2026-10-15", "variance": 2}, {"ent_inv_stock_level": "stock1"}),
        rec("count_big", "ent_inv_stock_count", "role_inv_clerk", {"counted_qty": 36, "counted_on": "2026-10-15", "variance": 14, "reason": "Damaged goods written off"}, {"ent_inv_stock_level": "stock1"}),
        rec("move1", "ent_inv_stock_movement", "role_inv_clerk", {"kind": "ADJUSTMENT", "quantity": 2, "moved_on": "2026-10-15"}, {"ent_core_item": "item1", "ent_core_location": "loc1"}),
        rec("move2", "ent_inv_stock_movement", "role_inv_clerk", {"kind": "ADJUSTMENT", "quantity": 14, "moved_on": "2026-10-15"}, {"ent_core_item": "item1", "ent_core_location": "loc1"}),
    ], flows=[
        run("wf_inv_count", {"ent_inv_stock_level": "stock1", "ent_inv_stock_count": "count_ok", "ent_inv_stock_movement": "move1"}),
        run("wf_inv_count", {"ent_inv_stock_level": "stock1", "ent_inv_stock_count": "count_big", "ent_inv_stock_movement": "move2"},
            {"approve": [{"record": "count_big", "role": "role_inv_manager", "values": {"decision": "APPROVED"}}]})])
    return p


def ecommerce() -> Pack:
    p = Pack("cat_ecommerce", "eco", "E-commerce and order management", "Customer orders from entry through availability, payment and confirmation.",
             deps=("core_foundations", "cat_inventory"), caps=("audit_history", "search_filter", "reporting_dashboards", "notifications"), domain_id="ecommerce_orders", capability="Order management",
             domain={"id": "ecommerce_orders", "name": "E-commerce and order management", "subdomains": ["Order entry", "Payment", "Order confirmation"],
                     "keywords": ["order", "orders", "e-commerce", "ecommerce", "webshop", "web shop", "checkout", "cart", "basket", "online store", "order management", "sales order", "customer order"],
                     "description": "Taking customer orders and getting them confirmed."})
    p.role("agent", "Order agent", [], ["Enters and confirms orders"])
    p.role("payments", "Payments clerk", [], ["Records and chases payment"])
    p.entity("order", "Customer order", "A customer's request to buy items.",
             [A("channel", "Channel", req=True, enum=["WEB", "PHONE", "EMAIL", "MARKETPLACE"]), A("status", "Status", req=True, enum=["NEW", "CONFIRMED", "IN_FULFILMENT", "COMPLETED", "CANCELLED"]),
              A("payment_status", "Payment status", enum=["PENDING", "PAID", "FAILED"], owner="role_eco_payments"), A("total_amount", "Total amount", "decimal", req=True, min=0),
              A("currency", "Currency", req=True, enum=["EUR", "USD", "GBP"]), A("order_date", "Order date", "date", req=True)],
             [("customer", "Customer", "ent_core_customer", "many_to_one", True)], owner="agent")
    p.entity("order_line", "Order line", "One item and quantity on a customer order.",
             [A("quantity", "Quantity", "integer", req=True, min=1), A("unit_price", "Unit price", "decimal", req=True, min=0)],
             [("order", "Order", "order", "many_to_one", True), ("item", "Item", "ent_core_item", "many_to_one", True)], owner="agent")
    p.rule("availability", "An order line can be filled only if on-hand stock covers the quantity.", "ent_inv_stock_level.on_hand", "gte", other="order_line.quantity", outcomes=["IN_STOCK", "SHORT"])
    p.rule("payment", "The recorded payment status decides whether the order is confirmed.", "order.payment_status", kind="value", outcomes=["PAID", "PENDING", "FAILED"])
    r1 = p.req("order", "Orders are entered, checked against stock and payment, and confirmed.", ["An agent enters an order with its lines.", "An order is confirmed only when stock is available and payment is received.", "A failed payment cancels the order."])
    p.req("track", "Everyone can see where an order stands.", ["The order's current step and history are visible."], "should")
    p.exc("backorder", "Stock is short", "On-hand stock does not cover an order line.", "The agent resolves the shortage and the check is repeated.", to=("order", "avail"))
    p.exc("payment_late", "Payment not received", "Payment is still pending when the order is ready to confirm.", "The payments clerk chases payment and the check is repeated.", to=("order", "pay_check"))
    p.dec("backorder", "Does the company accept backorders, or cancel the order when stock is short?", [p.rule_id("availability")])
    p.dec("terms", "Which payment terms apply to which customer segment?", [p.rule_id("payment")])
    p.flow("order", "Order to confirmation", [
        S("start", "Customer order received", "start"),
        S("enter", "Enter the order", "form", "agent", reads=["ent_core_customer", "ent_inv_stock_level"], writes=["order", "order_line"]),
        S("avail", "Is the stock available?", "branch", rules=["availability"], out=["availability"]),
        S("backorder", "Resolve the shortage", "exception", "agent", writes=["order_line"], exc=["backorder"]),
        S("payment", "Record the payment", "form", "payments", writes=["order"]), S("pay_check", "Payment status", "branch", rules=["payment"], out=["payment"]),
        S("chase", "Chase the payment", "exception", "payments", writes=["order"], exc=["payment_late"]), S("confirm", "Confirm the order", "action", "agent", writes=["order"]),
        S("done", "Order confirmed", "end", outcome="success"), S("cancelled", "Order cancelled", "end", outcome="cancelled")],
        [("start", "enter"), ("enter", "avail"), ("avail", "payment", "availability", "IN_STOCK"), ("avail", "backorder", "availability", "SHORT"), ("backorder", "avail"),
         ("payment", "pay_check"), ("pay_check", "confirm", "payment", "PAID"), ("pay_check", "chase", "payment", "PENDING"), ("pay_check", "cancelled", "payment", "FAILED"),
         ("chase", "pay_check"), ("confirm", "done")], [r1])
    p.term("order", "Customer order", "A customer's request to buy items.", ["sales order", "purchase order from a customer", "web order"], "ent_eco_order")
    p.term("line", "Order line", "One item and quantity on an order.", ["line item", "order item", "basket line"], "ent_eco_order_line")
    p.scenario(records=[
        rec("order1", "ent_eco_order", "role_eco_agent", {"channel": "WEB", "status": "NEW", "total_amount": 92.5, "currency": "EUR", "order_date": "2026-10-15"}, {"ent_core_customer": "cust1"}, shared=True),
        rec("line1", "ent_eco_order_line", "role_eco_agent", {"quantity": 5, "unit_price": 18.5}, {"ent_eco_order": "order1", "ent_core_item": "item1"}, shared=True)],
        flows=[run("wf_eco_order", {"ent_eco_order": "order1", "ent_eco_order_line": "line1", "ent_core_customer": "cust1", "ent_inv_stock_level": "stock1"},
                   {"payment": [{"record": "order1", "role": "role_eco_payments", "values": {"payment_status": "PAID"}}]})])
    return p


def all_a() -> list[Pack]:
    return [core(), tasks(), approvals(), documents(), inventory(), ecommerce()]
