"""Catalog part C: procurement, sales/CRM, after-sales service and warranty, finance and billing, workforce, and one synthetic company layer."""
from __future__ import annotations

from catalog_dsl import A, Pack, S, rec, run


def procurement() -> Pack:
    p = Pack("cat_procurement", "pro", "Procurement and purchasing", "Purchase requisitions, approval above a spending limit, purchase orders and goods receipt.",
             deps=("core_foundations", "cat_inventory"), caps=("approval_workflow", "audit_history", "search_filter", "document_handling", "notifications"),
             domain_id="procurement_purchasing", capability="Purchase to receipt",
             domain={"id": "procurement_purchasing", "name": "Procurement and purchasing", "subdomains": ["Requisitions", "Approval", "Purchase orders", "Goods receipt"],
                     "keywords": ["procurement", "purchasing", "purchase order", "requisition", "supplier", "suppliers", "vendor", "buyer", "sourcing", "goods receipt", "p2p", "purchase", "buying"],
                     "description": "Buying what the company needs, with the right approvals."})
    p.role("requester", "Requester", [], ["Asks for something to be bought"])
    p.role("buyer", "Buyer", [], ["Places and closes purchase orders"])
    p.role("approver", "Purchasing approver", [], ["Approves requisitions above the limit"], ["Requisitions above the spending limit"])
    p.role("receiver", "Goods receiver", [], ["Records what arrived"])
    p.entity("requisition", "Purchase requisition", "A request to buy an item.",
             [A("quantity", "Quantity", "decimal", req=True, min=1), A("estimated_cost", "Estimated cost", "decimal", req=True, min=0), A("needed_by", "Needed by", "date"),
              A("justification", "Justification", maxlen=500), A("status", "Status", req=True, enum=["DRAFT", "SUBMITTED", "APPROVED", "REJECTED", "ORDERED"]),
              A("decision", "Decision", enum=["PENDING", "APPROVED", "REJECTED"], owner="role_pro_approver")], [("item", "Item", "ent_core_item", "many_to_one", True)])
    p.entity("purchase_order", "Purchase order", "An order placed with a supplier.",
             [A("total_amount", "Total amount", "decimal", req=True, min=0), A("order_date", "Order date", "date", req=True), A("expected_date", "Expected delivery", "date"),
              A("status", "Status", req=True, enum=["DRAFT", "SENT", "RECEIVED", "CLOSED", "CANCELLED"])],
             [("requisition", "Requisition", "requisition", "many_to_one", True), ("supplier", "Supplier", "ent_core_supplier", "many_to_one", True)])
    p.entity("goods_receipt", "Goods receipt", "Goods that arrived against a purchase order.",
             [A("quantity_received", "Quantity received", "decimal", req=True, min=0), A("received_on", "Received on", "date", req=True), A("condition", "Condition", req=True, enum=["OK", "DAMAGED", "INCOMPLETE"])],
             [("purchase_order", "Purchase order", "purchase_order", "many_to_one", True)])
    p.rule("limit", "A requisition above 5,000 needs approval before it is ordered.", "requisition.estimated_cost", "lte", 5000, outcomes=["WITHIN_LIMIT", "NEEDS_APPROVAL"])
    p.rule("decision", "The approver's recorded decision selects what happens to the requisition.", "requisition.decision", kind="value", outcomes=["APPROVED", "REJECTED"])
    p.rule("match", "Goods are accepted when the quantity received covers the quantity requested.", "goods_receipt.quantity_received", "gte", other="requisition.quantity", outcomes=["MATCH", "MISMATCH"])
    r1 = p.req("buy", "Needs are requested, approved when above the limit, ordered and received.", ["A requester raises a requisition for an item.", "A requisition above the limit is approved by someone else before ordering.", "Received goods are checked against what was requested."])
    p.req("supplier", "Purchase orders name the supplier and expected delivery.", ["A purchase order refers to a supplier and a requisition."], "should")
    p.exc("receipt_mismatch", "Receipt does not match", "Less arrived than was requested, or goods are damaged.", "The buyer reconciles with the supplier and receipt is recorded again.", to=("requisition", "receive"))
    p.dec("limit", "What spending limit may a buyer commit without approval, and does it differ by category?", [p.rule_id("limit")])
    p.flow("requisition", "Requisition to purchase order", [
        S("start", "Need identified", "start"), S("raise", "Raise the requisition", "form", "requester", reads=["ent_core_item"], writes=["requisition"]),
        S("limit", "Within the spending limit?", "branch", rules=["limit"], out=["limit"]), S("approve", "Approve the requisition", "approval", "approver", writes=["requisition"]),
        S("verdict", "Approver's decision", "branch", rules=["decision"], out=["decision"]),
        S("order", "Place the purchase order", "form", "buyer", reads=["requisition", "ent_core_supplier"], writes=["purchase_order"]),
        S("receive", "Record goods receipt", "form", "receiver", reads=["purchase_order", "requisition"], writes=["goods_receipt"]), S("match", "Does the receipt match?", "branch", rules=["match"], out=["match"]),
        S("reconcile", "Reconcile the difference", "exception", "buyer", writes=["goods_receipt"], exc=["receipt_mismatch"]), S("close", "Close the purchase order", "action", "buyer", writes=["purchase_order"]),
        S("done", "Purchase complete", "end", outcome="success"), S("rejected", "Requisition rejected", "end", outcome="cancelled")],
        [("start", "raise"), ("raise", "limit"), ("limit", "order", "limit", "WITHIN_LIMIT"), ("limit", "approve", "limit", "NEEDS_APPROVAL"), ("approve", "verdict"),
         ("verdict", "order", "decision", "APPROVED"), ("verdict", "rejected", "decision", "REJECTED"), ("order", "receive"), ("receive", "match"), ("match", "close", "match", "MATCH"),
         ("match", "reconcile", "match", "MISMATCH"), ("reconcile", "receive"), ("close", "done")], [r1])
    p.term("requisition", "Purchase requisition", "A request to buy an item.", ["purchase request", "buy request", "PR"], "ent_pro_requisition")
    p.term("po", "Purchase order", "An order placed with a supplier.", ["PO", "supplier order", "buying order"], "ent_pro_purchase_order")
    p.term("receipt", "Goods receipt", "Goods that arrived against a purchase order.", ["GRN", "goods received note", "delivery note", "inbound receipt"], "ent_pro_goods_receipt")
    p.scenario(records=[
        rec("req_small", "ent_pro_requisition", "role_pro_requester", {"quantity": 10, "estimated_cost": 1200, "needed_by": "2026-11-10", "status": "DRAFT"}, {"ent_core_item": "item1"}),
        rec("req_big", "ent_pro_requisition", "role_pro_requester", {"quantity": 4, "estimated_cost": 9000, "needed_by": "2026-11-20", "justification": "Replacement pump assemblies", "status": "DRAFT"}, {"ent_core_item": "item1"}),
        rec("po_small", "ent_pro_purchase_order", "role_pro_buyer", {"total_amount": 1200, "order_date": "2026-10-16", "status": "SENT"}, {"ent_pro_requisition": "req_small", "ent_core_supplier": "sup1"}),
        rec("po_big", "ent_pro_purchase_order", "role_pro_buyer", {"total_amount": 9000, "order_date": "2026-10-17", "status": "SENT"}, {"ent_pro_requisition": "req_big", "ent_core_supplier": "sup1"}),
        rec("gr_small", "ent_pro_goods_receipt", "role_pro_receiver", {"quantity_received": 10, "received_on": "2026-10-25", "condition": "OK"}, {"ent_pro_purchase_order": "po_small"}),
        rec("gr_big", "ent_pro_goods_receipt", "role_pro_receiver", {"quantity_received": 4, "received_on": "2026-11-05", "condition": "OK"}, {"ent_pro_purchase_order": "po_big"})],
        flows=[run("wf_pro_requisition", {"ent_core_item": "item1", "ent_pro_requisition": "req_small", "ent_core_supplier": "sup1", "ent_pro_purchase_order": "po_small", "ent_pro_goods_receipt": "gr_small"}),
               run("wf_pro_requisition", {"ent_core_item": "item1", "ent_pro_requisition": "req_big", "ent_core_supplier": "sup1", "ent_pro_purchase_order": "po_big", "ent_pro_goods_receipt": "gr_big"},
                   {"approve": [{"record": "req_big", "role": "role_pro_approver", "values": {"decision": "APPROVED"}}]})])
    return p


def crm() -> Pack:
    p = Pack("cat_crm", "crm", "Sales and customer management", "Sales opportunities from qualification to won or lost, with approval of larger discounts.",
             deps=("core_foundations",), caps=("approval_workflow", "audit_history", "search_filter", "reporting_dashboards"), domain_id="sales_crm", capability="Opportunity management",
             domain={"id": "sales_crm", "name": "Sales, CRM and customer management", "subdomains": ["Opportunities", "Activities", "Discount approval"],
                     "keywords": ["crm", "sales", "opportunity", "opportunities", "pipeline", "lead", "leads", "quote", "quotation", "prospect", "deal", "customer relationship", "account manager", "discount"],
                     "description": "Finding, winning and keeping customers."})
    p.role("rep", "Sales representative", [], ["Qualifies, proposes and negotiates opportunities"])
    p.role("manager", "Sales manager", [], ["Approves larger discounts"], ["Discounts above the standard limit"])
    p.entity("opportunity", "Opportunity", "A chance to sell something to a customer.",
             [A("title", "Title", req=True, maxlen=160), A("stage", "Stage", req=True, enum=["QUALIFIED", "PROPOSAL", "NEGOTIATION", "WON", "LOST"]), A("value_amount", "Value", "decimal", req=True, min=0),
              A("discount_pct", "Discount (%)", "decimal", min=0, max=100), A("expected_close", "Expected close", "date"),
              A("decision", "Discount decision", enum=["PENDING", "APPROVED", "REJECTED"], owner="role_crm_manager"), A("loss_reason", "Loss reason", maxlen=300)],
             [("customer", "Customer", "ent_core_customer", "many_to_one", True)])
    p.entity("activity", "Activity", "A call, meeting, email or demo linked to an opportunity.",
             [A("kind", "Kind", req=True, enum=["CALL", "MEETING", "EMAIL", "DEMO"]), A("due_date", "Due date", "date", req=True), A("done", "Done", "boolean")],
             [("opportunity", "Opportunity", "opportunity", "many_to_one", True)])
    p.rule("discount", "A discount above 10% needs a manager's approval.", "opportunity.discount_pct", "lte", 10, outcomes=["STANDARD", "NEEDS_APPROVAL"])
    p.rule("discount_decision", "The manager's recorded decision selects what happens to the discount.", "opportunity.decision", kind="value", outcomes=["APPROVED", "REJECTED"])
    p.rule("result", "The recorded stage decides whether the opportunity is won or lost.", "opportunity.stage", kind="value", outcomes=["WON", "LOST"])
    r1 = p.req("sell", "Opportunities are qualified, proposed, negotiated and closed as won or lost.", ["A rep records an opportunity for a customer.", "A discount above the standard limit is approved by a manager.", "An opportunity ends as won or lost."])
    p.req("follow", "Follow-up activities are planned against opportunities.", ["An activity has a kind and a due date."], "should")
    p.exc("discount_refused", "Discount refused", "The manager rejects the requested discount.", "The rep revises the proposal and submits it again.", to=("opportunity", "propose"))
    p.dec("discount", "What discount may a rep give without approval, and does it depend on deal size or customer segment?", [p.rule_id("discount")])
    p.flow("opportunity", "Opportunity to close", [
        S("start", "Lead identified", "start"), S("qualify", "Qualify the opportunity", "form", "rep", reads=["ent_core_customer"], writes=["opportunity"]),
        S("propose", "Prepare the proposal", "form", "rep", writes=["opportunity", "activity"]), S("disc", "Discount within the standard limit?", "branch", rules=["discount"], out=["discount"]),
        S("approve", "Approve the discount", "approval", "manager", writes=["opportunity"]), S("verdict", "Manager's decision", "branch", rules=["discount_decision"], out=["discount_decision"]),
        S("revise", "Revise the proposal", "exception", "rep", writes=["opportunity"], exc=["discount_refused"]), S("negotiate", "Negotiate and close", "form", "rep", writes=["opportunity"]),
        S("result", "Won or lost?", "branch", rules=["result"], out=["result"]), S("won", "Won", "end", outcome="success"), S("lost", "Lost", "end", outcome="failure")],
        [("start", "qualify"), ("qualify", "propose"), ("propose", "disc"), ("disc", "negotiate", "discount", "STANDARD"), ("disc", "approve", "discount", "NEEDS_APPROVAL"), ("approve", "verdict"),
         ("verdict", "negotiate", "discount_decision", "APPROVED"), ("verdict", "revise", "discount_decision", "REJECTED"), ("revise", "propose"), ("negotiate", "result"),
         ("result", "won", "result", "WON"), ("result", "lost", "result", "LOST")], [r1])
    p.term("opportunity", "Opportunity", "A chance to sell something to a customer.", ["deal", "lead", "prospect", "sales opportunity"], "ent_crm_opportunity")
    p.term("activity", "Activity", "A call, meeting, email or demo.", ["touchpoint", "follow-up", "interaction"], "ent_crm_activity")
    p.scenario(records=[
        rec("opp1", "ent_crm_opportunity", "role_crm_rep", {"title": "Hose replacement programme", "stage": "PROPOSAL", "value_amount": 25000, "discount_pct": 5, "expected_close": "2026-12-01"}, {"ent_core_customer": "cust1"}),
        rec("act1", "ent_crm_activity", "role_crm_rep", {"kind": "CALL", "due_date": "2026-10-22", "done": False}, {"ent_crm_opportunity": "opp1"}),
        rec("opp2", "ent_crm_opportunity", "role_crm_rep", {"title": "Fleet service contract", "stage": "PROPOSAL", "value_amount": 80000, "discount_pct": 15, "expected_close": "2027-01-15"}, {"ent_core_customer": "cust1"}),
        rec("act2", "ent_crm_activity", "role_crm_rep", {"kind": "MEETING", "due_date": "2026-10-28", "done": False}, {"ent_crm_opportunity": "opp2"})],
        flows=[run("wf_crm_opportunity", {"ent_core_customer": "cust1", "ent_crm_opportunity": "opp1", "ent_crm_activity": "act1"},
                   {"negotiate": [{"record": "opp1", "role": "role_crm_rep", "values": {"stage": "WON"}}]}, "won"),
               run("wf_crm_opportunity", {"ent_core_customer": "cust1", "ent_crm_opportunity": "opp2", "ent_crm_activity": "act2"},
                   {"approve": [{"record": "opp2", "role": "role_crm_manager", "values": {"decision": "APPROVED"}}],
                    "negotiate": [{"record": "opp2", "role": "role_crm_rep", "values": {"stage": "LOST", "loss_reason": "Customer chose a competitor"}}]}, "lost")])
    return p


def aftersales() -> Pack:
    p = Pack("cat_aftersales", "svc", "After-sales service and warranty", "Service cases for machines in the field, warranty claims and technician visits.",
             deps=("core_foundations", "cat_manufacturing"), caps=("approval_workflow", "audit_history", "search_filter", "document_handling", "notifications"),
             domain_id="aftersales_service", capability="Service and warranty",
             domain={"id": "aftersales_service", "name": "After-sales service, maintenance and warranty", "subdomains": ["Service cases", "Warranty claims", "Field visits"],
                     "keywords": ["service", "after-sales", "aftersales", "warranty", "claim", "claims", "repair", "field service", "service case", "ticket", "support", "technician visit", "rma", "complaint"],
                     "description": "Looking after machines and customers after the sale."})
    p.role("agent", "Service desk agent", [], ["Logs, triages and closes cases"])
    p.role("technician", "Field technician", [], ["Visits the customer and records the outcome"])
    p.role("warranty", "Warranty administrator", [], ["Decides warranty claims"], ["Warranty claims"])
    p.entity("service_case", "Service case", "A customer's problem with a machine.",
             [A("description", "Problem", req=True, maxlen=600), A("priority", "Priority", req=True, enum=["LOW", "NORMAL", "URGENT"]), A("status", "Status", req=True, enum=["OPEN", "TRIAGED", "SCHEDULED", "RESOLVED", "CLOSED"]),
              A("opened_on", "Opened on", "date", req=True), A("service_date", "Service date", "date")],
             [("customer", "Customer", "ent_core_customer", "many_to_one", True), ("machine", "Machine", "ent_mfg_machine", "many_to_one", True)])
    p.entity("warranty_claim", "Warranty claim", "A request to cover a repair under warranty.",
             [A("claim_amount", "Claim amount", "decimal", min=0), A("decision", "Decision", enum=["PENDING", "APPROVED", "REJECTED"], owner="role_svc_warranty"), A("note", "Note", maxlen=500)],
             [("service_case", "Service case", "service_case", "many_to_one", True)])
    p.entity("service_visit", "Service visit", "A technician's visit to repair a machine.",
             [A("scheduled_at", "Scheduled for", "datetime", req=True), A("outcome", "Outcome", enum=["FIXED", "PART_NEEDED", "NO_FAULT"], owner="role_svc_technician"), A("parts_used", "Parts used", maxlen=300)],
             [("service_case", "Service case", "service_case", "many_to_one", True)])
    p.rule("description", "A case describes the problem.", "service_case.description")
    p.rule("warranty", "A repair is in warranty when the service date is on or before the machine's warranty end.", "service_case.service_date", "lte", other="ent_mfg_machine.warranty_end", outcomes=["IN_WARRANTY", "OUT_OF_WARRANTY"])
    p.rule("claim_decision", "The warranty administrator's recorded decision selects what happens to the claim.", "warranty_claim.decision", kind="value", outcomes=["APPROVED", "REJECTED"])
    p.rule("outcome", "The technician's recorded outcome selects how the case continues.", "service_visit.outcome", kind="value", outcomes=["FIXED", "PART_NEEDED", "NO_FAULT"])
    r1 = p.req("resolve", "Service cases are logged, checked for warranty, scheduled, visited and closed.", ["A case records the customer, the machine and the problem.", "Warranty status is decided from the machine's warranty end date.", "A technician records the outcome of each visit."])
    p.req("claims", "Warranty claims are decided by a warranty administrator.", ["A claim is approved or rejected and the decision is recorded."], "should")
    p.exc("part_unavailable", "Part not available", "The visit found a fault that needs a part that is not on hand.", "The agent schedules a new visit once the part is available.", to=("case", "schedule"))
    p.dec("goodwill", "Does the company repair out-of-warranty faults as goodwill, and who may grant it?", [p.rule_id("warranty")])
    p.flow("case", "Service case", [
        S("start", "Customer reports a problem", "start"), S("log", "Log the case", "form", "agent", reads=["ent_core_customer", "ent_mfg_machine"], writes=["service_case"]),
        S("triage", "Triage the case", "form", "agent", reads=["ent_mfg_machine"], writes=["service_case"], rules=["description"]),
        S("warranty", "Is the machine in warranty?", "branch", rules=["warranty"], out=["warranty"]), S("claim", "Decide the warranty claim", "approval", "warranty", reads=["service_case"], writes=["warranty_claim"]),
        S("claim_check", "Claim decision", "branch", rules=["claim_decision"], out=["claim_decision"]), S("quote", "Quote a paid repair", "form", "agent", writes=["service_case"]),
        S("schedule", "Schedule the visit", "form", "agent", reads=["service_case"], writes=["service_visit"]), S("visit", "Carry out the visit", "form", "technician", writes=["service_visit"]),
        S("outcome", "Visit outcome", "branch", rules=["outcome"], out=["outcome"]), S("part_wait", "Wait for the part", "exception", "technician", writes=["service_visit"], exc=["part_unavailable"]),
        S("close", "Close the case", "action", "agent", writes=["service_case"]), S("done", "Case closed", "end", outcome="success")],
        [("start", "log"), ("log", "triage"), ("triage", "warranty"), ("warranty", "claim", "warranty", "IN_WARRANTY"), ("warranty", "quote", "warranty", "OUT_OF_WARRANTY"), ("claim", "claim_check"),
         ("claim_check", "schedule", "claim_decision", "APPROVED"), ("claim_check", "quote", "claim_decision", "REJECTED"), ("quote", "schedule"), ("schedule", "visit"), ("visit", "outcome"),
         ("outcome", "close", "outcome", "FIXED"), ("outcome", "part_wait", "outcome", "PART_NEEDED"), ("outcome", "close", "outcome", "NO_FAULT"), ("part_wait", "schedule"), ("close", "done")], [r1])
    p.term("case", "Service case", "A customer's problem with a machine.", ["ticket", "incident", "support case", "complaint"], "ent_svc_service_case")
    p.term("warranty", "Warranty", "Cover for repairs during a period after the sale.", ["guarantee", "coverage", "in-warranty"])
    p.term("visit", "Service visit", "A technician's visit to repair a machine.", ["field visit", "site visit", "call-out", "repair visit"], "ent_svc_service_visit")
    p.scenario(records=[
        rec("case1", "ent_svc_service_case", "role_svc_agent", {"description": "Hydraulic arm leaks under load", "priority": "URGENT", "status": "OPEN", "opened_on": "2026-10-15", "service_date": "2026-10-20"},
            {"ent_core_customer": "cust1", "ent_mfg_machine": "machine1"}),
        rec("claim1", "ent_svc_warranty_claim", "role_svc_warranty", {"claim_amount": 480}, {"ent_svc_service_case": "case1"}),
        rec("visit1", "ent_svc_service_visit", "role_svc_agent", {"scheduled_at": "2026-10-22T08:00:00Z"}, {"ent_svc_service_case": "case1"})],
        flows=[run("wf_svc_case", {"ent_core_customer": "cust1", "ent_mfg_machine": "machine1", "ent_svc_service_case": "case1", "ent_svc_warranty_claim": "claim1", "ent_svc_service_visit": "visit1"},
                   {"claim": [{"record": "claim1", "role": "role_svc_warranty", "values": {"decision": "APPROVED"}}],
                    "visit": [{"record": "visit1", "role": "role_svc_technician", "values": {"outcome": "FIXED", "parts_used": "Hydraulic seal kit"}}]})])
    return p


def finance() -> Pack:
    p = Pack("cat_finance", "fin", "Finance, billing and reporting", "Invoices from draft to payment, with review of large invoices and follow-up of short payments.",
             deps=("core_foundations", "cat_ecommerce"), caps=("approval_workflow", "audit_history", "search_filter", "reporting_dashboards", "document_handling"),
             domain_id="finance_billing", capability="Billing and collection",
             domain={"id": "finance_billing", "name": "Finance, billing and operational reporting", "subdomains": ["Invoicing", "Review", "Payments", "Receivables"],
                     "keywords": ["finance", "billing", "invoice", "invoices", "invoicing", "payment", "payments", "receivable", "receivables", "accounts receivable", "credit note", "reporting", "revenue", "collection"],
                     "description": "Getting paid correctly and seeing where the money is."})
    p.role("biller", "Billing clerk", [], ["Drafts and issues invoices"])
    p.role("controller", "Finance controller", [], ["Reviews large invoices"], ["Invoices above the review limit"])
    p.role("receivables", "Receivables clerk", [], ["Records payments and follows up"])
    p.entity("invoice", "Invoice", "A request for payment sent to a customer.",
             [A("amount", "Amount", "decimal", req=True, min=0), A("currency", "Currency", req=True, enum=["EUR", "USD", "GBP"]), A("issue_date", "Issue date", "date"), A("due_date", "Due date", "date"),
              A("status", "Status", req=True, enum=["DRAFT", "ISSUED", "PAID", "OVERDUE", "CANCELLED"]), A("decision", "Review decision", enum=["PENDING", "APPROVED", "REJECTED"], owner="role_fin_controller")],
             [("customer", "Customer", "ent_core_customer", "many_to_one", True), ("order", "Order", "ent_eco_order", "many_to_one")])
    p.entity("payment", "Payment", "Money received against an invoice.",
             [A("amount_received", "Amount received", "decimal", req=True, min=0), A("received_on", "Received on", "date", req=True), A("method", "Method", req=True, enum=["TRANSFER", "CARD", "DIRECT_DEBIT"])],
             [("invoice", "Invoice", "invoice", "many_to_one", True)])
    p.entity("credit_note", "Credit note", "A reduction of an invoice.", [A("amount", "Amount", "decimal", req=True, min=0), A("reason", "Reason", req=True, maxlen=300)], [("invoice", "Invoice", "invoice", "many_to_one", True)])
    p.rule("review", "An invoice above 10,000 is reviewed by the controller before it is issued.", "invoice.amount", "lte", 10000, outcomes=["AUTO_ISSUE", "NEEDS_REVIEW"])
    p.rule("decision", "The controller's recorded decision selects what happens to the invoice.", "invoice.decision", kind="value", outcomes=["APPROVED", "REJECTED"])
    p.rule("due", "An invoice has a due date before it is issued.", "invoice.due_date")
    p.rule("settlement", "An invoice is paid in full when the amount received covers it.", "payment.amount_received", "gte", other="invoice.amount", outcomes=["PAID_IN_FULL", "PARTIAL"])
    r1 = p.req("bill", "Invoices are drafted, reviewed when large, issued and settled by payment.", ["A clerk drafts an invoice for a customer.", "A large invoice is reviewed by the controller before it is issued.", "Payment is compared with the amount due."])
    p.req("report", "Open and overdue invoices can be seen at a glance.", ["The home view shows invoices in progress and completed."], "should")
    p.exc("invoice_rejected", "Invoice rejected on review", "The controller rejects a large invoice.", "The clerk amends the invoice and it is reviewed again.", to=("billing", "review"))
    p.exc("short_payment", "Short payment", "The amount received is less than the invoice.", "The receivables clerk follows up and records the further payment.", to=("billing", "payment"))
    p.dec("review", "What invoice amount needs the controller's review, and are credit notes reviewed the same way?", [p.rule_id("review")])
    p.flow("billing", "Invoice to payment", [
        S("start", "Invoice due", "start"), S("draft", "Draft the invoice", "form", "biller", reads=["ent_core_customer"], writes=["invoice"]),
        S("review", "Does it need review?", "branch", rules=["review"], out=["review"]), S("approve", "Review the invoice", "approval", "controller", writes=["invoice"]),
        S("verdict", "Controller's decision", "branch", rules=["decision"], out=["decision"]), S("amend", "Amend the invoice", "exception", "biller", writes=["invoice"], exc=["invoice_rejected"]),
        S("issue", "Issue the invoice", "action", "biller", writes=["invoice"], rules=["due"]), S("payment", "Record the payment", "form", "receivables", reads=["invoice"], writes=["payment"]),
        S("settle", "Paid in full?", "branch", rules=["settlement"], out=["settlement"]), S("follow_up", "Follow up the short payment", "exception", "receivables", writes=["payment"], exc=["short_payment"]),
        S("close", "Close the invoice", "action", "receivables", writes=["invoice"]), S("done", "Invoice settled", "end", outcome="success")],
        [("start", "draft"), ("draft", "review"), ("review", "issue", "review", "AUTO_ISSUE"), ("review", "approve", "review", "NEEDS_REVIEW"), ("approve", "verdict"),
         ("verdict", "issue", "decision", "APPROVED"), ("verdict", "amend", "decision", "REJECTED"), ("amend", "review"), ("issue", "payment"), ("payment", "settle"),
         ("settle", "close", "settlement", "PAID_IN_FULL"), ("settle", "follow_up", "settlement", "PARTIAL"), ("follow_up", "payment"), ("close", "done")], [r1])
    p.term("invoice", "Invoice", "A request for payment sent to a customer.", ["bill", "sales invoice", "statement"], "ent_fin_invoice")
    p.term("payment", "Payment", "Money received against an invoice.", ["remittance", "receipt", "settlement"], "ent_fin_payment")
    p.term("credit", "Credit note", "A reduction of an invoice.", ["credit memo", "refund note"], "ent_fin_credit_note")
    p.scenario(records=[
        rec("inv_small", "ent_fin_invoice", "role_fin_biller", {"amount": 4200, "currency": "EUR", "issue_date": "2026-10-16", "due_date": "2026-11-15", "status": "DRAFT"}, {"ent_core_customer": "cust1"}),
        rec("inv_big", "ent_fin_invoice", "role_fin_biller", {"amount": 15000, "currency": "EUR", "issue_date": "2026-10-17", "due_date": "2026-11-16", "status": "DRAFT"}, {"ent_core_customer": "cust1"}),
        rec("pay_small", "ent_fin_payment", "role_fin_receivables", {"amount_received": 4200, "received_on": "2026-11-01", "method": "TRANSFER"}, {"ent_fin_invoice": "inv_small"}),
        rec("pay_big", "ent_fin_payment", "role_fin_receivables", {"amount_received": 15000, "received_on": "2026-11-05", "method": "TRANSFER"}, {"ent_fin_invoice": "inv_big"})],
        flows=[run("wf_fin_billing", {"ent_core_customer": "cust1", "ent_fin_invoice": "inv_small", "ent_fin_payment": "pay_small"}),
               run("wf_fin_billing", {"ent_core_customer": "cust1", "ent_fin_invoice": "inv_big", "ent_fin_payment": "pay_big"},
                   {"approve": [{"record": "inv_big", "role": "role_fin_controller", "values": {"decision": "APPROVED"}}]})])
    return p


def workforce() -> Pack:
    p = Pack("cat_workforce", "wfm", "Workforce, tasks and approvals", "Leave requests approved by a manager, plus task management for the team.",
             deps=("core_foundations", "cap_task_management"), includes=("cap_task_management",), caps=("approval_workflow", "task_management", "audit_history", "search_filter"),
             domain_id="workforce_tasks", capability="Leave and task management",
             domain={"id": "workforce_tasks", "name": "Workforce, task management and approvals", "subdomains": ["Leave", "Tasks", "Approvals"],
                     "keywords": ["workforce", "employee", "employees", "leave", "holiday", "absence", "timesheet", "hr", "human resources", "task", "tasks", "to-do", "team", "approval", "approvals", "onboarding"],
                     "description": "Managing people's time and the work the team has to do."})
    p.role("employee", "Employee", [], ["Requests leave"])
    p.role("manager", "Team manager", [], ["Decides leave requests"], ["Leave requests"])
    p.role("hr", "HR administrator", [], ["Maintains employees and records approved leave"])
    p.entity("employee", "Employee", "A person who works for the company.",
             [A("name", "Name", req=True, maxlen=120), A("job_title", "Job title", maxlen=120), A("team", "Team", maxlen=80), A("status", "Status", req=True, enum=["ACTIVE", "ON_LEAVE", "LEFT"]),
              A("leave_balance_days", "Leave balance (days)", "decimal", req=True, min=0)], owner="hr")
    p.entity("leave_request", "Leave request", "A request for time off.",
             [A("start_date", "First day", "date", req=True), A("end_date", "Last day", "date", req=True), A("days", "Working days", "decimal", req=True, min=0), A("kind", "Kind", req=True, enum=["ANNUAL", "SICK", "UNPAID", "OTHER"]),
              A("decision", "Decision", enum=["PENDING", "APPROVED", "REJECTED"], owner="role_wfm_manager"), A("note", "Note", maxlen=300)],
             [("employee", "Employee", "employee", "many_to_one", True)])
    p.rule("dates", "The last day is not before the first day.", "leave_request.end_date", "gte", other="leave_request.start_date")
    p.rule("balance", "Leave can be approved only if the employee's balance covers the days requested.", "employee.leave_balance_days", "gte", other="leave_request.days", outcomes=["SUFFICIENT", "INSUFFICIENT"])
    p.rule("decision", "The manager's recorded decision selects what happens to the request.", "leave_request.decision", kind="value", outcomes=["APPROVED", "REJECTED"])
    r1 = p.req("leave", "Leave is requested, checked against the balance, decided by a manager and recorded.", ["An employee requests leave for a period.", "A request that exceeds the balance is sent back.", "Only a manager can approve or reject."])
    p.req("tasks", "The team's work is tracked as tasks.", ["Tasks can be created, assigned and completed."], "should")
    p.exc("balance_short", "Balance too low", "The days requested exceed the leave balance.", "The employee changes the request and it is checked again.", to=("leave", "submit"))
    p.dec("carryover", "May unused leave be carried over, and how many days?", [p.rule_id("balance")])
    p.flow("leave", "Leave request", [
        S("start", "Leave needed", "start"), S("submit", "Submit the request", "form", "employee", reads=["employee"], writes=["leave_request"], rules=["dates"]),
        S("balance", "Does the balance cover it?", "branch", rules=["balance"], out=["balance"]), S("adjust", "Adjust the request", "exception", "employee", writes=["leave_request"], exc=["balance_short"]),
        S("decide", "Decide the request", "approval", "manager", writes=["leave_request"]), S("verdict", "Manager's decision", "branch", rules=["decision"], out=["decision"]),
        S("record", "Record the leave", "action", "hr", reads=["leave_request"], writes=["employee"]), S("done", "Leave recorded", "end", outcome="success"), S("rejected", "Request rejected", "end", outcome="cancelled")],
        [("start", "submit"), ("submit", "balance"), ("balance", "decide", "balance", "SUFFICIENT"), ("balance", "adjust", "balance", "INSUFFICIENT"), ("adjust", "submit"), ("decide", "verdict"),
         ("verdict", "record", "decision", "APPROVED"), ("verdict", "rejected", "decision", "REJECTED"), ("record", "done")], [r1])
    p.term("leave", "Leave", "Time off work.", ["holiday", "vacation", "absence", "time off", "PTO"], "ent_wfm_leave_request")
    p.term("employee", "Employee", "A person who works for the company.", ["staff member", "colleague", "team member", "worker"], "ent_wfm_employee")
    p.scenario(records=[
        rec("emp1", "ent_wfm_employee", "role_wfm_hr", {"name": "Alex Jansen (synthetic)", "job_title": "Service engineer", "team": "Field service", "status": "ACTIVE", "leave_balance_days": 20}),
        rec("lr1", "ent_wfm_leave_request", "role_wfm_employee", {"start_date": "2026-11-02", "end_date": "2026-11-06", "days": 5, "kind": "ANNUAL"}, {"ent_wfm_employee": "emp1"})],
        flows=[run("wf_wfm_leave", {"ent_wfm_employee": "emp1", "ent_wfm_leave_request": "lr1"}, {"decide": [{"record": "lr1", "role": "role_wfm_manager", "values": {"decision": "APPROVED"}}]})])
    return p


def company() -> Pack:
    p = Pack("company_brightwell", "bw", "Brightwell Machinery Service (synthetic company)",
             "A synthetic company that sells machinery spare parts, services machines in the field and bills customers. It reuses shared domain knowledge and adds its own service-contract process.",
             layer="company", deps=("core_foundations", "cat_inventory", "cat_ecommerce", "cat_warehouse", "cat_transport", "cat_manufacturing", "cat_aftersales", "cat_finance", "cap_documents"),
             includes=("cat_inventory", "cat_ecommerce", "cat_warehouse", "cat_transport", "cat_manufacturing", "cat_aftersales", "cat_finance", "cap_documents"),
             caps=("approval_workflow", "audit_history", "search_filter", "reporting_dashboards", "document_handling"), capability="Spare parts and field service",
             company={"id": "brightwell", "name": "Brightwell Machinery Service (synthetic)", "industry": "Industrial machinery service and spare parts",
                      "operating_context": "Sells spare parts online and by phone, delivers them, services installed machines under warranty and service contracts, and invoices customers. Synthetic: invented for the reference catalog.",
                      "business_units": ["Spare parts sales", "Warehouse and logistics", "Field service", "Finance"], "systems_of_record": ["ERP (synthetic)", "Warehouse system (synthetic)"]})
    p.role("account_manager", "Account manager", [], ["Drafts and activates service contracts"])
    p.role("commercial_lead", "Commercial lead", [], ["Approves service contracts"], ["Service contracts"])
    p.entity("service_contract", "Service contract", "An agreement that gives a customer priority service on their machines.",
             [A("start_date", "Starts", "date", req=True), A("end_date", "Ends", "date", req=True), A("response_hours", "Response time (hours)", "integer", req=True, min=1),
              A("status", "Status", req=True, enum=["DRAFT", "ACTIVE", "EXPIRED"]), A("decision", "Approval decision", enum=["PENDING", "APPROVED", "REJECTED"], owner="role_bw_commercial_lead")],
             [("customer", "Customer", "ent_core_customer", "many_to_one", True)])
    p.rule("dates", "A contract ends on or after the day it starts.", "service_contract.end_date", "gte", other="service_contract.start_date")
    p.rule("decision", "The commercial lead's recorded decision selects what happens to the contract.", "service_contract.decision", kind="value", outcomes=["APPROVED", "REJECTED"])
    r1 = p.req("contract", "Service contracts are drafted, approved by the commercial lead and activated.", ["An account manager drafts a contract for a customer.", "A different person approves it before it becomes active."])
    p.exc("contract_declined", "Contract declined", "The commercial lead declines the contract terms.", "The account manager revises the terms and submits again.", to=("contract", "draft"))
    p.dec("sla", "What response times may Brightwell offer, and which customers are entitled to them?", [p.rule_id("dates")])
    p.flow("contract", "Service contract onboarding", [
        S("start", "Customer wants a contract", "start"), S("draft", "Draft the contract", "form", "account_manager", reads=["ent_core_customer"], writes=["service_contract"], rules=["dates"]),
        S("approve", "Approve the contract", "approval", "commercial_lead", writes=["service_contract"]), S("verdict", "Commercial lead's decision", "branch", rules=["decision"], out=["decision"]),
        S("revise", "Revise the terms", "exception", "account_manager", writes=["service_contract"], exc=["contract_declined"]),
        S("activate", "Activate the contract", "action", "account_manager", writes=["service_contract"]), S("done", "Contract active", "end", outcome="success")],
        [("start", "draft"), ("draft", "approve"), ("approve", "verdict"), ("verdict", "activate", "decision", "APPROVED"), ("verdict", "revise", "decision", "REJECTED"), ("revise", "draft"), ("activate", "done")], [r1])
    p.override("ent_core_customer", "Brightwell serves customers in three languages and records the preferred one.", add_attributes=[A("preferred_language", "Preferred language", enum=["EN", "NL", "DE"])])
    p.override("rule_inv_variance", "Brightwell's synthetic company setting: a tighter stock count tolerance than the shared default.",
               patch={"description": "A count difference of more than 2 units needs approval before stock is adjusted (Brightwell setting).",
                      "execution": {"kind": "compare", "field": "ent_inv_stock_count.variance", "operator": "lte", "value": 2, "other_field": None, "pass_outcome": "WITHIN_TOLERANCE", "fail_outcome": "NEEDS_APPROVAL"}})
    p.override("ent_svc_service_case", "Brightwell tracks whether a case falls under a service contract.", add_attributes=[A("under_contract", "Under a service contract", "boolean")])
    p.term("contract", "Service contract", "An agreement that gives a customer priority service on their machines.", ["SLA", "maintenance agreement", "support contract", "service agreement"], "ent_bw_service_contract")
    p.scenario(records=[rec("contract1", "ent_bw_service_contract", "role_bw_account_manager", {"start_date": "2026-11-01", "end_date": "2027-10-31", "response_hours": 8, "status": "DRAFT"}, {"ent_core_customer": "cust1"})],
               flows=[run("wf_bw_contract", {"ent_core_customer": "cust1", "ent_bw_service_contract": "contract1"}, {"approve": [{"record": "contract1", "role": "role_bw_commercial_lead", "values": {"decision": "APPROVED"}}]})])
    return p


def all_packs() -> list[Pack]:
    return [procurement(), crm(), aftersales(), finance(), workforce(), company()]
