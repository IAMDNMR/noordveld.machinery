"""The lifecycle of a direct order, as pure data and pure functions (no graph, no I/O), so every rule can be tested alone.

Direct order:  NEW -> ALLOCATED -> FULFILMENT_PENDING -> FULFILLING -> READY_TO_SHIP -> SHIPPED -> DELIVERED -> COMPLETED
Shipment:      CREATED -> DISPATCHED -> IN_TRANSIT -> DELIVERED          (the order is SHIPPED from dispatch until delivery)
Dealer service (only when the customer asked for it): CREATED -> PART_RECEIVED -> STARTED -> INSTALLED -> COMPLETED; completing it completes the order.
Exceptions:    REJECTED, ALLOCATION_FAILED, ALLOCATION_RELEASED, CANCELLED, SHIPMENT_EXCEPTION, DELIVERY_FAILED, SERVICE_CANCELLED.

One vocabulary: these are OrderStatus nodes, the same ones the earlier demo orders use (NEW, CONFIRMED, PROCESSING, ALLOCATED, SHIPPED,
DELIVERED). Orders of the earlier channels keep their own forward-only flow (services/orders.py); this module governs `DIRECT_ORDER` only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DIRECT = "DIRECT_ORDER"

LABEL = {
    "NEW": "Order placed", "ALLOCATED": "Stock allocated", "FULFILMENT_PENDING": "Fulfilment pending", "FULFILLING": "Fulfilling", "READY_TO_SHIP": "Ready to ship",
    "SHIPPED": "Shipped", "DELIVERED": "Delivered", "COMPLETED": "Completed",
    "REJECTED": "Rejected", "ALLOCATION_FAILED": "Allocation failed", "ALLOCATION_RELEASED": "Allocation released", "CANCELLED": "Cancelled",
    "SHIPMENT_EXCEPTION": "Shipment exception", "DELIVERY_FAILED": "Delivery failed", "SERVICE_CANCELLED": "Service cancelled",
    # earlier channels
    "CONFIRMED": "Confirmed", "PROCESSING": "Processing",
}
# statuses added to the existing OrderStatus vocabulary, with their sequence (existing: NEW 1 … DELIVERED 6)
NEW_STATUS_SEQUENCE = {
    "FULFILMENT_PENDING": 40, "FULFILLING": 41, "READY_TO_SHIP": 42, "COMPLETED": 70,
    "REJECTED": 90, "ALLOCATION_FAILED": 91, "ALLOCATION_RELEASED": 92, "CANCELLED": 93, "SHIPMENT_EXCEPTION": 94, "DELIVERY_FAILED": 95, "SERVICE_CANCELLED": 96,
}
EXCEPTIONS = frozenset({"REJECTED", "ALLOCATION_FAILED", "ALLOCATION_RELEASED", "CANCELLED", "SHIPMENT_EXCEPTION", "DELIVERY_FAILED", "SERVICE_CANCELLED"})


PROCESSOR = "processor"
OWNER_OR_PROCESSOR = "owner_or_processor"

# Stock is released only while it is still reserved and has not left the depot.
EARLY = frozenset({"NEW", "ALLOCATION_FAILED", "ALLOCATION_RELEASED", "ALLOCATED", "FULFILMENT_PENDING"})  # an owner may still cancel here


@dataclass(frozen=True)
class Action:
    label: str
    from_statuses: frozenset[str]
    to_status: str | None  # None: the order keeps its status (the shipment or service moves)
    actor: str = PROCESSOR
    shipment: frozenset[str] | None = None  # required state of the current shipment (None = no requirement)
    service: frozenset[str] | None = None  # required state of the dealer service
    no_shipment: bool = False  # there must be no active shipment
    note: str = ""


def _s(*x: str) -> frozenset[str]:
    return frozenset(x)


ACTIONS: dict[str, Action] = {
    "allocate": Action("Allocate stock", _s("NEW", "ALLOCATION_FAILED", "ALLOCATION_RELEASED"), "ALLOCATED"),
    "release_allocation": Action("Release allocation", _s("ALLOCATED", "FULFILMENT_PENDING", "FULFILLING", "READY_TO_SHIP"), "ALLOCATION_RELEASED", no_shipment=True),
    "start_fulfilment": Action("Start fulfilment", _s("ALLOCATED"), "FULFILMENT_PENDING"),
    "begin_fulfilling": Action("Begin picking and packing", _s("FULFILMENT_PENDING"), "FULFILLING"),
    "mark_ready": Action("Mark ready to ship", _s("FULFILLING"), "READY_TO_SHIP"),
    "create_shipment": Action("Create shipment", _s("READY_TO_SHIP"), None, no_shipment=True),
    "dispatch": Action("Dispatch shipment", _s("READY_TO_SHIP"), "SHIPPED", shipment=_s("CREATED")),
    "in_transit": Action("Mark in transit", _s("SHIPPED"), None, shipment=_s("DISPATCHED")),
    "deliver": Action("Mark delivered", _s("SHIPPED"), "DELIVERED", shipment=_s("IN_TRANSIT")),
    "shipment_exception": Action("Report shipment exception", _s("SHIPPED"), "SHIPMENT_EXCEPTION", shipment=_s("DISPATCHED", "IN_TRANSIT")),
    "resume_shipment": Action("Resume shipment", _s("SHIPMENT_EXCEPTION"), "SHIPPED", shipment=_s("EXCEPTION")),
    "delivery_failed": Action("Report failed delivery", _s("SHIPPED", "SHIPMENT_EXCEPTION"), "DELIVERY_FAILED", shipment=_s("DISPATCHED", "IN_TRANSIT", "EXCEPTION")),
    "service_receive_part": Action("Dealer: receive part", _s("DELIVERED"), None, service=_s("CREATED"), note="Recorded by the Order Processor on behalf of the dealer."),
    "service_start": Action("Dealer: start service", _s("DELIVERED"), None, service=_s("PART_RECEIVED"), note="Recorded by the Order Processor on behalf of the dealer."),
    "service_install": Action("Dealer: install part", _s("DELIVERED"), None, service=_s("STARTED"), note="Recorded by the Order Processor on behalf of the dealer."),
    "service_complete": Action("Dealer: complete service", _s("DELIVERED"), "COMPLETED", service=_s("INSTALLED"), note="Recorded by the Order Processor on behalf of the dealer."),
    "service_cancel": Action("Cancel dealer service", _s("DELIVERED"), "SERVICE_CANCELLED", service=_s("CREATED", "PART_RECEIVED", "STARTED", "INSTALLED")),
    "complete_order": Action("Complete order", _s("DELIVERED", "SERVICE_CANCELLED"), "COMPLETED"),
    "reject": Action("Reject order", _s("NEW", "ALLOCATION_FAILED"), "REJECTED"),
    "cancel": Action("Cancel order", _s("NEW", "ALLOCATION_FAILED", "ALLOCATION_RELEASED", "ALLOCATED", "FULFILMENT_PENDING", "FULFILLING", "READY_TO_SHIP", "DELIVERY_FAILED"),
                     "CANCELLED", OWNER_OR_PROCESSOR),
}

# the service/shipment effect each action has on its own record (the repository applies it in the same transaction as the status change)
SHIPMENT_EFFECT = {"dispatch": "DISPATCHED", "in_transit": "IN_TRANSIT", "deliver": "DELIVERED", "shipment_exception": "EXCEPTION", "resume_shipment": "IN_TRANSIT",
                   "delivery_failed": "DELIVERY_FAILED"}
SERVICE_EFFECT = {"service_receive_part": "PART_RECEIVED", "service_start": "STARTED", "service_install": "INSTALLED", "service_complete": "COMPLETED", "service_cancel": "CANCELLED"}


def blocked(action: str, ctx: dict[str, Any], *, is_processor: bool, is_owner: bool) -> str | None:
    """Why `action` cannot run on this order now; None when it can. ctx: status, channel, shipment_status, service_required, service_status,
    allocation_status."""
    a = ACTIONS.get(action)
    if a is None:
        return "Unknown action."
    if ctx.get("channel") != DIRECT:
        return "This order follows the earlier workflow."
    status = ctx["status"]
    if status not in a.from_statuses:
        return f"Not available while the order is {LABEL.get(status, status)}."
    if a.actor == PROCESSOR and not is_processor:
        return "Only an Order Processor can do this."
    if a.actor == OWNER_OR_PROCESSOR and not (is_processor or is_owner):
        return "Only the person who placed the order or an Order Processor can do this."
    if a.actor == OWNER_OR_PROCESSOR and not is_processor and status not in EARLY:
        return "The order is already being fulfilled; ask the Order Processor to cancel it."
    shipment = ctx.get("shipment_status")
    active_shipment = shipment in ("CREATED", "DISPATCHED", "IN_TRANSIT", "EXCEPTION")
    if a.no_shipment and active_shipment and action != "cancel":
        return "A shipment already exists for this order."
    if a.shipment is not None and shipment not in a.shipment:
        return "The shipment is not in the right state." if shipment else "There is no shipment yet."
    if a.service is not None and ctx.get("service_status") not in a.service:
        return "The dealer service is not in the right state." if ctx.get("service_status") else "This order has no dealer service."
    if action == "complete_order" and status == "DELIVERED" and ctx.get("service_required"):
        return "Dealer service was requested: complete or cancel the service first."
    if action == "allocate" and ctx.get("allocation_status") == "RESERVED":
        return "Stock is already reserved for this order."
    return None


def available_actions(ctx: dict[str, Any], *, is_processor: bool, is_owner: bool) -> list[dict[str, Any]]:
    """Every action whose status precondition holds for this order, with whether it can run now: the UI shows only these, the server re-checks."""
    out = []
    for name, a in ACTIONS.items():
        if ctx.get("channel") == DIRECT and ctx["status"] in a.from_statuses:
            reason = blocked(name, ctx, is_processor=is_processor, is_owner=is_owner)
            if reason in ("Only an Order Processor can do this.",) or (reason and reason.startswith("The order is already being fulfilled")):
                continue  # not this user's action at all
            out.append({"action": name, "label": a.label, "allowed": reason is None, "reason": reason, "to_status": a.to_status, "note": a.note or None})
    return out


STAGES = ("Order", "Allocation", "Fulfilment", "Shipment", "Tracking", "Dealer Service", "Completed")


def stages(ctx: dict[str, Any]) -> list[dict[str, str]]:
    """The seven stages the customer follows, each 'done', 'current', 'pending', 'exception' or 'skipped', from the recorded state alone."""
    status, shipment, service = ctx["status"], ctx.get("shipment_status"), ctx.get("service_status")
    rank = {"NEW": 0, "ALLOCATED": 1, "FULFILMENT_PENDING": 2, "FULFILLING": 2, "READY_TO_SHIP": 3, "SHIPPED": 4, "DELIVERED": 5, "COMPLETED": 7}
    if status in EXCEPTIONS:
        return [{"stage": s, "state": "exception" if s == _exception_stage(status) else ("done" if _done_before(status, s, ctx) else "pending")} for s in STAGES]
    r = rank.get(status, 0)
    out = []
    for i, stage in enumerate(STAGES):
        if stage == "Dealer Service":
            state = "skipped" if not ctx.get("service_required") else ("done" if status == "COMPLETED" or service == "COMPLETED" else "current" if status == "DELIVERED" else "pending")
        elif stage == "Tracking":
            state = "done" if r >= 5 else "current" if shipment in ("DISPATCHED", "IN_TRANSIT") else "pending"
        elif stage == "Shipment":
            state = "done" if r >= 5 or shipment in ("DISPATCHED", "IN_TRANSIT", "DELIVERED") else "current" if r == 3 else "pending"
        elif stage == "Fulfilment":
            state = "done" if r >= 3 else "current" if r == 2 else "pending"
        elif stage == "Allocation":
            state = "done" if r >= 1 else "pending"
        elif stage == "Order":
            state = "done"
        else:  # Completed
            state = "done" if status == "COMPLETED" else "pending"
        out.append({"stage": stage, "state": state})
    # the first stage that is not done is where the order is now
    for item in out:
        if item["state"] == "pending" and not any(x["state"] == "current" for x in out):
            item["state"] = "current"
    return out


def _exception_stage(status: str) -> str:
    return {"REJECTED": "Order", "CANCELLED": "Order", "ALLOCATION_FAILED": "Allocation", "ALLOCATION_RELEASED": "Allocation", "SHIPMENT_EXCEPTION": "Tracking",
            "DELIVERY_FAILED": "Tracking", "SERVICE_CANCELLED": "Dealer Service"}[status]


def _done_before(status: str, stage: str, ctx: dict[str, Any]) -> bool:
    order = {s: i for i, s in enumerate(STAGES)}
    return order[stage] < order[_exception_stage(status)]
