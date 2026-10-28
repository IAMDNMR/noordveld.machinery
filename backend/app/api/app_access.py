"""Server-side gate for the business applications (Agentic Shopping, orders, parts store, ...).

One identity, many applications: the person signs in once, and each application checks, on the server, that this person holds an
access grant for it in the organization they are working in. Hiding a link in the workspace is a convenience; this is the control.

* With an organization directory configured, an application route needs a signed-in person, an organization they belong to, and a
  grant for that application there (or the organization permission `app.launch`).
  The read-only profile (`app_viewer`) can read but never change anything.
* With no directory configured (today's public demo and every environment without an identity provider), nothing changes: the
  route behaves exactly as before. That is a stated limit, not a decision that anonymous access is acceptable for real customers.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request

from app.api.dependencies import OrdersSvc
from app.core.config import get_settings
from app.core.session import COOKIE, verify
from app.orgs.directory import OrgDirectory, get_org_directory
from app.orgs.permissions import APP_VIEWER

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _refuse(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def active_organization(request: Request, directory: OrgDirectory, user_id: str) -> str:
    memberships = directory.organizations_of(user_id)
    chosen = request.headers.get("x-org-id") or request.query_params.get("org")
    if chosen is not None:
        if not any(item["id"] == chosen for item in memberships):
            raise _refuse(404, "organization_not_found", "You do not belong to that organization.")
        return chosen
    if len(memberships) == 1:
        return memberships[0]["id"]
    raise _refuse(400, "organization_required", "Choose an organization (X-Org-Id).")


def require_app(app_id: str):
    """A router or route guard: the signed-in person must hold access to `app_id` in their organization."""

    def guard(
        request: Request,
        directory: Annotated[OrgDirectory, Depends(get_org_directory)],
        orders: OrdersSvc,
        nv_session: Annotated[str | None, Cookie(alias=COOKIE)] = None,
    ) -> None:
        if not directory.configured:
            return
        user = orders.user(verify(nv_session, get_settings().session_secret))
        if user is None:
            raise _refuse(401, "not_signed_in", "Sign in to continue.")
        org = active_organization(request, directory, user.id)
        grants = [
            item["app_role"]
            for item in directory.app_grants(user.id, org)
            if item["app_id"] == app_id
        ]
        creator_preview = "app.launch" in directory.permissions(user.id, org) and bool(
            directory.roles(user.id, org)
        )
        if not grants and not creator_preview:
            directory.record(
                user.id,
                "access.denied",
                org,
                f"{request.method} {request.url.path}: no access to {app_id}",
            )
            raise _refuse(
                403,
                "app_access_required",
                "You have not been given access to this application. Ask your organization administrator.",
            )
        if grants and set(grants) == {APP_VIEWER} and request.method not in READ_METHODS:
            directory.record(
                user.id,
                "access.denied",
                org,
                f"{request.method} {request.url.path}: read-only on {app_id}",
            )
            raise _refuse(403, "read_only", "Your access to this application is read-only.")
        request.state.org_id = org

    return guard


def require_any_app(*app_ids: str):
    """Enter a combined workspace using any grant; retain each feature's denial.

    Reuse the existing guards so organization selection, viewer restrictions and
    creator previews cannot drift from the standalone applications.
    """
    guards = {app_id: require_app(app_id) for app_id in app_ids}

    def guard(
        request: Request,
        directory: Annotated[OrgDirectory, Depends(get_org_directory)],
        orders: OrdersSvc,
        nv_session: Annotated[str | None, Cookie(alias=COOKIE)] = None,
    ) -> None:
        denied = {}
        for app_id, check in guards.items():
            try:
                check(request, directory, orders, nv_session)
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
                denied[app_id] = exc
        if len(denied) == len(guards):
            raise next(iter(denied.values()))
        request.state.app_access_denials = denied

    return guard


def check_app_operation(request: Request, app_id: str) -> None:
    """Apply a feature denial captured by the combined-workspace entry guard."""
    denial = request.state.app_access_denials.get(app_id)
    if denial is not None:
        raise denial
