"""Demo sign-in and the current user. There is no password or identity provider: the demo signs in as a seeded demo user and the
backend keeps the user id in a signed, httpOnly cookie. The role is always read from the user record."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.api.dependencies import CurrentUser, OrdersSvc
from app.core.config import get_settings
from app.core.roles import PERMISSIONS
from app.core.session import COOKIE, MAX_AGE, sign

router = APIRouter(tags=["accounts"])


class SignIn(BaseModel):
    user_id: str


def _me(user) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role.value, "customer": user.customer_name,
            "permissions": sorted(PERMISSIONS[user.role])}


@router.get("/auth/demo-users")
def demo_users(orders: OrdersSvc) -> list[dict]:
    """The demo accounts that can be signed in as (names and roles only)."""
    return [{"id": u["id"], "name": u["name"], "role": u["role"], "customer": u.get("customer_name")} for u in orders.demo_users()]


@router.post("/auth/login")
def login(body: SignIn, response: Response, orders: OrdersSvc) -> dict:
    user = orders.user(body.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail={"code": "unknown_user", "message": "No such demo user."})
    s = get_settings()
    response.set_cookie(COOKIE, sign(user.id, s.session_secret), max_age=MAX_AGE, httponly=True, samesite="lax", secure=s.session_cookie_secure, path="/")
    return _me(user)


@router.post("/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE, path="/")
    return {"signed_out": True}


@router.get("/me")
def me(user: CurrentUser) -> dict:
    return _me(user)
