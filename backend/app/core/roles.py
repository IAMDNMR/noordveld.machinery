"""Application roles and their permissions: two product workflow roles, not a general RBAC system.

The backend resolves the role from the signed session and checks a permission on every protected endpoint; the frontend uses the
role only to decide what to show. No permission edits catalogue, fitment, price, inventory, supplier or provenance facts: those
stay graph-backed and have no write endpoint at all.
"""
from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    END_USER = "END_USER"
    ORDER_PROCESSOR = "ORDER_PROCESSOR"


PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.END_USER: frozenset({
        "catalogue.read", "parts.read", "intelligence.query", "agentic_shopping.use",
        "cart.read", "cart.write", "orders.read_own", "requests.create",
    }),
    Role.ORDER_PROCESSOR: frozenset({
        "catalogue.read", "parts.read", "intelligence.query",
        "orders.read", "orders.process", "orders.update_status",
        "fulfilment.read", "inventory.read", "shipment.read", "tracking.read",
    }),
}


def allowed(role: Role, permission: str) -> bool:
    return permission in PERMISSIONS[role]
