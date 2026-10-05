"""Parts Store checkout: reference data for the screens, the order review, and Place Order. Every rule is enforced in app/services/checkout.py;
this module only validates the request shape and maps the service's errors to HTTP."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.dependencies import CheckoutSvc, require
from app.api.routes.orders import Item, _call
from app.services.orders import User

router = APIRouter(tags=["checkout"])
Buyer = Annotated[User, Depends(require("orders.place"))]


class ReviewBody(BaseModel):
    items: list[Item] = Field(min_length=1, max_length=50)
    ship_to_id: str = Field(min_length=1, max_length=40)


class Requester(BaseModel):
    name: str = Field(max_length=120)
    email: str = Field(max_length=200)
    phone: str = Field(max_length=40)
    company: str = Field(max_length=120)


class Delivery(BaseModel):
    ship_to_id: str = Field(min_length=1, max_length=40)
    receiver_name: str = Field(max_length=120)
    receiver_phone: str = Field(max_length=40)


class PlaceBody(BaseModel):
    items: list[Item] = Field(min_length=1, max_length=50)
    requester: Requester
    delivery: Delivery
    dealer_id: str = Field(min_length=1, max_length=40)
    dealer_service_required: bool = False
    depot_id: str = Field(min_length=1, max_length=40)
    route_id: str = Field(min_length=1, max_length=120)
    confirmed: bool = False
    idempotency_key: str = Field(min_length=8, max_length=80)


@router.get("/checkout/countries")
def countries(user: Buyer, checkout: CheckoutSvc) -> list[dict]:
    return _call(checkout.countries, user)


@router.get("/checkout/destinations")
def destinations(user: Buyer, checkout: CheckoutSvc, country: Annotated[str, Query(min_length=2, max_length=2)]) -> list[dict]:
    return _call(checkout.destinations, user, country)


@router.get("/checkout/dealers")
def dealers(user: Buyer, checkout: CheckoutSvc, country: Annotated[str | None, Query(min_length=2, max_length=2)] = None) -> list[dict]:
    return _call(checkout.dealers, user, country)


@router.post("/checkout/review")
def review(body: ReviewBody, user: Buyer, checkout: CheckoutSvc) -> dict:
    return _call(checkout.review, user, [i.model_dump() for i in body.items], body.ship_to_id)


@router.post("/orders", status_code=201)
def place_order(body: PlaceBody, user: Buyer, checkout: CheckoutSvc) -> dict:
    """Place Order: creates the order (never a request), reserves its stock and returns it with its current state."""
    return _call(checkout.place, user, body.model_dump())
