"""Demo sign-in and the current user. There is no password or identity provider: the demo signs in as a seeded demo user and the
backend keeps the user id in a signed, httpOnly cookie. The role is always read from the user record."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.dependencies import CurrentUser, OrdersSvc
from app.core.config import get_settings
from app.core.demo_access import local_demo_request, public_studio_enabled, studio_demo_request
from app.core.roles import PERMISSIONS
from app.core.session import COOKIE, MAX_AGE, sign, verify

router = APIRouter(tags=["accounts"])


def require_demo_context(request: Request) -> None:
    if not local_demo_request(request):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Not found."})


def require_studio_demo_context(request: Request) -> None:
    if not studio_demo_request(request):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Not found."})


class SignIn(BaseModel):
    user_id: str


WORKSPACE_MAX_AGE = 365 * 24 * 3600  # an anonymous workspace is the only way back to its projects, so it must outlast a day


def _keep_workspace(response: Response, visitor_id: str) -> None:
    """Remember this browser's anonymous workspace for a year (and again at every visit). The projects themselves are stored in the
    database either way; this cookie is what shows them to their owner."""
    settings = get_settings()
    response.set_cookie(
        "nv_studio_session",
        sign(visitor_id, "studio:" + settings.session_secret, max_age=WORKSPACE_MAX_AGE),
        max_age=WORKSPACE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/api/v1",
    )


def _me(user) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role.value,
        "customer": user.customer_name,
        "permissions": sorted(PERMISSIONS[user.role]),
    }


@router.get("/auth/demo-users", dependencies=[Depends(require_demo_context)])
def demo_users(orders: OrdersSvc) -> list[dict]:
    """The demo accounts that can be signed in as (names and roles only)."""
    return [
        {"id": u["id"], "name": u["name"], "role": u["role"], "customer": u.get("customer_name")}
        for u in orders.demo_users()
    ]


@router.post("/auth/login", dependencies=[Depends(require_demo_context)])
def login(body: SignIn, response: Response, orders: OrdersSvc) -> dict:
    user = orders.user(body.user_id)
    if user is None:
        raise HTTPException(
            status_code=401, detail={"code": "unknown_user", "message": "No such demo user."}
        )
    s = get_settings()
    response.set_cookie(
        COOKIE,
        sign(user.id, s.session_secret),
        max_age=MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=s.session_cookie_secure,
        path="/",
    )
    return _me(user)


@router.post("/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE, path="/")
    return {"signed_out": True}


@router.get("/me")
def me(user: CurrentUser) -> dict:
    return _me(user)


@router.post("/studio-session/demo", dependencies=[Depends(require_studio_demo_context)])
def studio_demo(
    request: Request,
    response: Response,
    orders: OrdersSvc,
    nv_studio_session: Annotated[str | None, Cookie(alias="nv_studio_session")] = None,
) -> dict:
    """Local: the single Studio preview identity. Public demo: this browser's own anonymous workspace. Independent of the commerce session."""
    from app.design_studio.preview_identity import cached, remember

    if public_studio_enabled() and not local_demo_request(request):
        from app.design_studio.visitors import is_visitor, new_visitor_id, visitor_user

        settings = get_settings()
        existing = verify(nv_studio_session, "studio:" + settings.session_secret)
        visitor_id = existing if is_visitor(existing) else new_visitor_id()
        _keep_workspace(response, visitor_id)
        return _me(visitor_user(visitor_id))

    user = cached()
    if user is None:
        account = next((item for item in orders.demo_users() if item["role"] == "END_USER"), None)
        user = orders.user(account["id"]) if account else None
    if user is None:
        raise HTTPException(
            503,
            detail={
                "code": "studio_preview_unavailable",
                "message": "The local Studio preview account is unavailable.",
            },
        )
    settings = get_settings()
    remember(user)
    response.set_cookie(
        "nv_studio_session",
        sign(user.id, "studio:" + settings.session_secret),
        max_age=MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/api/v1",
    )
    return _me(user)


@router.get("/studio-session/me", dependencies=[Depends(require_studio_demo_context)])
def studio_me(user: CurrentUser, response: Response) -> dict:
    from app.design_studio.visitors import is_visitor

    if is_visitor(user.id):
        _keep_workspace(response, user.id)  # every visit renews it, so a workspace in use never expires
    return _me(user)


@router.post("/studio-session/logout")
def studio_logout(response: Response) -> dict:
    response.delete_cookie("nv_studio_session", path="/api/v1")
    return {"signed_out": True}
