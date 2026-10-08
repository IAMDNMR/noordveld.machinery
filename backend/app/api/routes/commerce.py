"""Commerce context endpoints: structured JSON for the three journeys. No language-model text is produced here.

Every route needs a signed-in user with the `commerce.context` permission. The principal (OEM / DEALER / END_CUSTOMER) is derived from the signed session and the optional
`user_role`; ownership is checked before any context is built (app/commerce/access.py). Business outcomes (NOT_FOUND, NOT_ELIGIBLE, REQUIRES_CLARIFICATION ...) are in the body's
`decision.status` with HTTP 200; HTTP errors are for authentication (401), authorization (403) and malformed requests (422).
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.dependencies import CommerceEngine, CommerceService, require
from app.commerce.access import AccessDenied, Principal, principal_for
from app.commerce.service import ServiceRequest
from app.services.orders import User

router = APIRouter(prefix="/commerce", tags=["commerce context"])

Ref = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:\-]*$")]
Country = Annotated[str, Field(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")]
Caller = Annotated[User, Depends(require("commerce.context"))]


class Scope(BaseModel):
    """Who is asking, as far as the request can narrow it. The account's own role always limits this."""

    model_config = ConfigDict(extra="forbid")
    user_role: Literal["OEM", "DEALER", "END_CUSTOMER"] | None = None
    dealer_id: Ref | None = None


class DiscoveryBody(Scope):
    request: str = Field(min_length=3, max_length=500)
    machine_id: Ref | None = None
    machine_instance_id: Ref | None = None
    destination_country: Country | None = None


class LogisticsBody(Scope):
    shipment_id: Ref | None = None
    order_id: Ref | None = None


class WarrantyBody(Scope):
    claim_id: Ref | None = None
    machine_instance_id: Ref | None = None
    part_id: Ref | None = None

    @model_validator(mode="after")
    def _one_way_in(self) -> WarrantyBody:
        if self.claim_id and (self.machine_instance_id or self.part_id):
            raise ValueError("give either claim_id or machine_instance_id with part_id, not both")
        if bool(self.machine_instance_id) != bool(self.part_id):
            raise ValueError("machine_instance_id and part_id go together")
        return self


class RequestBody(Scope):
    """The agent adapter: a normalised intent (or none) with whatever references are known. Each flow takes the references it needs and ignores the rest."""

    request: str = Field(default="", max_length=500)
    intent: Literal["DISCOVERY", "LOGISTICS", "WARRANTY"] | None = None
    machine_id: Ref | None = None
    machine_instance_id: Ref | None = None
    destination_country: Country | None = None
    shipment_id: Ref | None = None
    order_id: Ref | None = None
    claim_id: Ref | None = None
    part_id: Ref | None = None


def _principal(user: User, scope: Scope) -> Principal:
    try:
        return principal_for(user, scope.user_role, scope.dealer_id)
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)}) from exc


def _guard(fn, *args, **kw) -> Any:
    try:
        return fn(*args, **kw)
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)}) from exc


@router.post("/discovery/context")
def discovery_context(body: DiscoveryBody, user: Caller, engine: CommerceEngine) -> dict:
    p = _principal(user, body)
    return _guard(engine.build_discovery_context, body.request, principal=p, machine_id=body.machine_id, machine_instance_id=body.machine_instance_id,
                  destination_country=body.destination_country.upper() if body.destination_country else None).to_dict()


@router.post("/logistics/context")
def logistics_context(body: LogisticsBody, user: Caller, engine: CommerceEngine) -> dict:
    p = _principal(user, body)
    return _guard(engine.build_logistics_context, principal=p, shipment_id=body.shipment_id, order_id=body.order_id).to_dict()


@router.post("/warranty/context")
def warranty_context(body: WarrantyBody, user: Caller, engine: CommerceEngine) -> dict:
    p = _principal(user, body)
    return _guard(engine.build_warranty_context, principal=p, claim_id=body.claim_id, machine_instance_id=body.machine_instance_id, part_id=body.part_id).to_dict()


@router.post("/request")
def request_context(body: RequestBody, user: Caller, service: CommerceService) -> dict:
    """The agent adapter: pick the flow (a supplied intent, else a conservative cue match) and return its structured context."""
    p = _principal(user, body)
    return _guard(service.handle, ServiceRequest(
        text=body.request, intent=body.intent, principal=p, machine_id=body.machine_id, machine_instance_id=body.machine_instance_id,
        destination_country=body.destination_country.upper() if body.destination_country else None, shipment_id=body.shipment_id, order_id=body.order_id, claim_id=body.claim_id,
        part_id=body.part_id)).to_dict()
