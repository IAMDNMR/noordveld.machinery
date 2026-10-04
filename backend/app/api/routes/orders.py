"""Orders, purchase requests and the user's cart. Authorization is enforced here (permission per route) and again in the service
(ownership): an End User sees only their customer's orders; only an Order Processor can change a status."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import OrdersSvc, require
from app.services.orders import Forbidden, Missing, TransitionError, User

router = APIRouter(tags=["orders"])


class Item(BaseModel):
    part_id: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=99)


class RequestBody(BaseModel):
    items: list[Item] = Field(min_length=1, max_length=50)
    idempotency_key: str = Field(min_length=8, max_length=80)


class StatusBody(BaseModel):
    status: str = Field(min_length=2, max_length=24)
    expected_status: str | None = None


class CartBody(BaseModel):
    lines: list[Item] = Field(max_length=50)


def _call(fn, *args):
    try:
        return fn(*args)
    except Forbidden as exc:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": str(exc)}) from exc
    except Missing as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"No order {exc}."}) from exc
    except TransitionError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc


AnyReader = Annotated[User, Depends(require("catalogue.read"))]  # any signed-in role; the service narrows the scope


@router.get("/orders")
def list_orders(user: AnyReader, orders: OrdersSvc) -> list[dict]:
    return _call(orders.list, user)


@router.get("/orders/{order_id}")
def order_detail(order_id: str, user: AnyReader, orders: OrdersSvc) -> dict:
    return _call(orders.detail, user, order_id)


@router.post("/orders/{order_id}/status")
def update_status(order_id: str, body: StatusBody, user: Annotated[User, Depends(require("orders.update_status"))], orders: OrdersSvc) -> dict:
    return _call(orders.update_status, user, order_id, body.status, body.expected_status)


@router.post("/requests", status_code=201)
def create_request(body: RequestBody, user: Annotated[User, Depends(require("requests.create"))], orders: OrdersSvc) -> dict:
    return _call(orders.create_request, user, [(i.part_id, i.quantity) for i in body.items], body.idempotency_key)


@router.get("/me/cart")
def my_cart(user: Annotated[User, Depends(require("cart.read"))], orders: OrdersSvc) -> list[dict]:
    return _call(orders.cart, user)


@router.put("/me/cart")
def put_cart(body: CartBody, user: Annotated[User, Depends(require("cart.write"))], orders: OrdersSvc) -> list[dict]:
    return _call(orders.put_cart, user, [(i.part_id, i.quantity) for i in body.lines])
