"""Who may see what, decided BEFORE any context is built.

Three commerce roles sit on top of the two account roles that already exist (app/core/roles.py):

  END_USER         -> END_CUSTOMER  (only their own machines, orders, shipments and warranty)
  ORDER_PROCESSOR  -> OEM           (everything), or DEALER when a dealer_id is given (only that dealer's orders, installations and claims)

An account can only narrow itself (a processor may act as a dealer); it can never widen itself (an end user can never act as OEM or dealer). The role is never taken
from the request body alone: `principal_for` combines the signed-in account with the requested role.

Ownership is checked on the records themselves (order.customer_id, machine.owner_id, order.dealer_id, installation.dealer_id), through the same readers the contexts use.
A principal who is not OEM gets the SAME refusal for a record that does not exist and for one that is not theirs, so the answer never confirms that someone else's record exists.

Visibility (what a permitted role sees inside a context) is a small declarative table applied to the structured result. It never replaces the ownership check.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.roles import Role


class CommerceRole(str, Enum):
    OEM = "OEM"
    DEALER = "DEALER"
    END_CUSTOMER = "END_CUSTOMER"


class AccessDenied(Exception):
    """The principal may not read this (HTTP 403). The message never says whether the record exists."""

    def __init__(self, code: str = "forbidden", message: str = "You do not have access to this record.") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Principal:
    role: CommerceRole
    user_id: str | None = None
    customer_id: str | None = None
    dealer_id: str | None = None

    @classmethod
    def system(cls) -> Principal:
        """A trusted in-process caller (tests, batch jobs). The API never builds this: it always derives the principal from the signed session."""
        return cls(CommerceRole.OEM, user_id="system")


def principal_for(user: Any, requested_role: str | None = None, dealer_id: str | None = None) -> Principal:
    """The principal for a signed-in account. `user` has .id, .role (Role) and .customer_id."""
    account = user.role
    wanted = CommerceRole(requested_role) if requested_role else None
    if account == Role.END_USER:
        if wanted not in (None, CommerceRole.END_CUSTOMER):
            raise AccessDenied("role_not_allowed", "This account can only act as an end customer.")
        if dealer_id:
            raise AccessDenied("role_not_allowed", "A dealer id can only be used with the DEALER role.")
        return Principal(CommerceRole.END_CUSTOMER, user_id=user.id, customer_id=user.customer_id)
    if account == Role.ORDER_PROCESSOR:
        if wanted in (None, CommerceRole.OEM):
            if dealer_id:
                raise AccessDenied("role_not_allowed", "A dealer id can only be used with the DEALER role.")
            return Principal(CommerceRole.OEM, user_id=user.id)
        if wanted == CommerceRole.DEALER:
            if not dealer_id:
                raise AccessDenied("dealer_required", "The DEALER role needs a dealer id.")
            return Principal(CommerceRole.DEALER, user_id=user.id, dealer_id=dealer_id)
        raise AccessDenied("role_not_allowed", "This account cannot act as an end customer.")
    raise AccessDenied("role_not_allowed", "This account has no commerce role.")


# ── ownership ────────────────────────────────────────────────────────────────────────────────────
def _no() -> AccessDenied:
    return AccessDenied()


class AccessPolicy:
    """Ownership rules over the same readers the contexts use. Every method returns None when allowed and raises AccessDenied when not."""

    def __init__(self, logistics: Any, lifecycle: Any) -> None:
        self._log = logistics
        self._life = lifecycle

    # orders and shipments
    def order(self, p: Principal, order: dict[str, Any] | None, destination_id: str | None = None) -> None:
        if p.role == CommerceRole.OEM:
            return
        if order is None:
            raise _no()
        if p.role == CommerceRole.END_CUSTOMER and p.customer_id and order.get("customer_id") == p.customer_id:
            return
        if p.role == CommerceRole.DEALER and p.dealer_id and (order.get("dealer_id") == p.dealer_id or (destination_id is not None and destination_id == p.dealer_id)):
            return
        raise _no()

    def shipment(self, p: Principal, shipment: dict[str, Any] | None) -> None:
        if p.role == CommerceRole.OEM:
            return
        if shipment is None:
            raise _no()
        order = self._log.order(shipment["order_id"]) if shipment.get("order_id") else None
        self.order(p, order, shipment.get("destination_location_id"))

    # machines, installations and claims
    def instance(self, p: Principal, instance: dict[str, Any] | None) -> None:
        if p.role == CommerceRole.OEM:
            return
        if instance is None:
            raise _no()
        if p.role == CommerceRole.END_CUSTOMER and p.customer_id and instance.get("owner_id") == p.customer_id:
            return
        if p.role == CommerceRole.DEALER and p.dealer_id:
            mid = instance["machine_instance_id"]
            if any(i.get("dealer_id") == p.dealer_id for i in self._life.installations(mid)) or any(c.get("dealer_id") == p.dealer_id for c in self._life.claims(mid)):
                return
        raise _no()

    def claim(self, p: Principal, claim: dict[str, Any] | None) -> None:
        if p.role == CommerceRole.OEM:
            return
        if claim is None:
            raise _no()
        instance = self._life.instance(claim["machine_instance_id"])
        if p.role == CommerceRole.DEALER and claim.get("dealer_id") == p.dealer_id and p.dealer_id:
            return
        self.instance(p, instance)


# ── visibility ───────────────────────────────────────────────────────────────────────────────────
# (context type, role) -> dotted paths removed from the structured result. `[*]` is every item of a list. Declared here, applied after the context is built, listed in the result.
HIDDEN: dict[tuple[str, CommerceRole], tuple[str, ...]] = {
    ("DISCOVERY", CommerceRole.END_CUSTOMER): ("availability[*].warehouses",),  # which depot holds the stock is the OEM's and the dealer's view; the customer sees available / not
    ("LOGISTICS", CommerceRole.END_CUSTOMER): ("shipment.remediation_flags", "route_legs[*].estimated_cost"),  # internal data-quality flags and per-leg freight cost
    ("WARRANTY", CommerceRole.END_CUSTOMER): ("technician.name", "traceability.installed_now[*].installed_by.name", "traceability.installed_before[*].installed_by.name"),  # a person's name
}


def _remove(node: Any, parts: list[str]) -> bool:
    head, rest = parts[0], parts[1:]
    star = head.endswith("[*]")
    key = head[:-3] if star else head
    if not isinstance(node, dict) or key not in node:
        return False
    child = node[key]
    if not rest:
        if star:
            return False
        del node[key]
        return True
    if star:
        return any([_remove(item, rest) for item in child]) if isinstance(child, list) else False
    return _remove(child, rest)


def apply_visibility(principal: Principal, context_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """Remove what this role may not see from the structured result and say what was removed. OEM sees everything."""
    removed = [path for path in HIDDEN.get((context_type, principal.role), ()) if _remove(data, path.split("."))]
    data["visibility"] = {"role": principal.role.value, "hidden_fields": sorted(removed)}
    return data
