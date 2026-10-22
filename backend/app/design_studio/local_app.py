"""Opt-in loopback-only Design Studio demo; no graph, provider, or business routes.

Run only with DESIGN_STUDIO_LOCAL_DEV=1 and a new database in a dedicated
noordveld-studio-* directory under the system temporary directory.
"""

from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.dependencies import current_user
from app.api.routes.design_studio import (
    get_design_store,
    get_project_store,
    router as studio_router,
)
from app.core.demo_access import local_demo_request
from app.core.roles import PERMISSIONS, Role
from app.core.session import COOKIE, MAX_AGE, sign, verify
from app.design_studio.sqlite_store import SqliteProjectStore, SqliteStudioStore
from app.design_studio.releases import ReleaseStore, get_release_store
from app.api.routes.domain_knowledge import router as domain_router
from app.design_studio.knowledge.provider import WithDomainPacks, get_knowledge_provider
from app.domain_knowledge.store import (
    SqliteDomainStore,
    active_version,
    get_domain_access,
    get_domain_store,
)
from app.api.routes.workspace import router as workspace_router
from app.orgs.directory import SqliteOrgDirectory, get_org_directory
from app.services.orders import User

USERS = {
    "studio-alice": User(
        "studio-alice", "Alice (local demo)", "alice@example.invalid", Role.END_USER
    ),
    "studio-bob": User(
        "studio-bob", "Bob (local demo)", "bob@example.invalid", Role.ORDER_PROCESSOR
    ),
    "studio-carol": User(
        "studio-carol", "Carol (local demo)", "carol@example.invalid", Role.END_USER
    ),
    "studio-dave": User("studio-dave", "Dave (local demo)", "dave@example.invalid", Role.END_USER),
    "studio-erin": User("studio-erin", "Erin (local demo)", "erin@example.invalid", Role.END_USER),
    "studio-frank": User(
        "studio-frank", "Frank (local demo)", "frank@example.invalid", Role.END_USER
    ),
    "studio-gina": User("studio-gina", "Gina (local demo)", "gina@example.invalid", Role.END_USER),
}


def seed_demo_directory(directory: SqliteOrgDirectory) -> None:
    """Synthetic organizations and people for the isolated local app and tests. Nothing here is production identity data."""
    # The demo organization shares its projects org-wide so the single-browser walkthrough works without assigning each project; an
    # organization chooses this explicitly. Every other organization starts with the default policy: nobody reaches a project unassigned.
    directory.seed_organization("org_noordveld", "Noordveld Machinery (demo)", "org")
    directory.seed_organization("org_harbor", "Harbor Freight (demo)")
    for user, org, role in (
        ("studio-alice", "org_noordveld", "project_owner"),
        ("studio-bob", "org_noordveld", "business_approver"),
        ("studio-carol", "org_noordveld", "org_admin"),
        ("studio-dave", "org_noordveld", "designer"),
        ("studio-gina", "org_harbor", "org_admin"),
    ):
        directory.seed_membership(user, org, role)
    directory.seed_platform_role(
        "studio-alice", "solution_architect"
    )  # proposes and reviews domain releases
    directory.seed_platform_role(
        "studio-erin", "platform_admin"
    )  # approves releases; NOT a member of any customer organization
    # Frank is a dealer: he uses applications but holds no organization role, so Design Studio is closed to him.
    directory.seed_app_grant("studio-frank", "org_noordveld", "parts_store", "dealer")
    directory.seed_app_grant("studio-frank", "org_noordveld", "parts_intelligence", "dealer")
    directory.seed_app_grant("studio-alice", "org_noordveld", "parts_store", "customer")


class SignIn(BaseModel):
    user_id: str


def _profile(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role.value,
        "customer": user.customer_name,
        "permissions": sorted(PERMISSIONS[user.role]),
    }


def create_local_app(db_path: Path, *, persistence=None) -> FastAPI:
    if (
        os.environ.get("DESIGN_STUDIO_LOCAL_DEV") != "1"
        or os.environ.get("APP_ENV") != "local"
        or os.environ.get("VERCEL")
        or os.environ.get("VERCEL_ENV")
    ):
        raise RuntimeError("The isolated Design Studio app requires explicit local-only mode")
    path = db_path.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if (
        not path.is_relative_to(temp_root)
        or not path.parent.name.startswith("noordveld-studio-")
        or path.name != "studio.sqlite"
        or not path.parent.is_dir()
    ):
        raise RuntimeError(
            "Use a dedicated Noordveld Studio directory under the system temporary directory"
        )

    if persistence is None:
        drafts = SqliteStudioStore(path)
        projects = SqliteProjectStore(path)
        domain_store = SqliteDomainStore(path.with_name("domain.sqlite"))
        directory = SqliteOrgDirectory(path.with_name("orgs.sqlite"))
    else:
        drafts, projects, domain_store, directory = persistence
    seed_demo_directory(directory)
    session_secret = secrets.token_urlsafe(32)
    app = FastAPI(title="Noordveld Design Studio isolated local demo")
    releases = ReleaseStore(path.with_name("releases.sqlite"))
    app.state.release_store = releases
    app.dependency_overrides[get_release_store] = lambda: releases

    @app.middleware("http")
    async def loopback_only(request: Request, call_next):
        if not local_demo_request(request):
            return JSONResponse(
                status_code=404, content={"error": {"code": "not_found", "message": "Not found."}}
            )
        return await call_next(request)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "error", "message": str(exc.detail)}
        )
        return JSONResponse(status_code=exc.status_code, content={"error": detail})

    def local_user(nv_session: Annotated[str | None, Cookie(alias=COOKIE)] = None) -> User:
        user = USERS.get(verify(nv_session, session_secret) or "")
        if user is None:
            raise HTTPException(
                401, detail={"code": "not_signed_in", "message": "Sign in to continue."}
            )
        return user

    @app.get("/api/v1/auth/demo-users")
    def demo_users():
        return [
            {"id": user.id, "name": user.name, "role": user.role.value, "customer": None}
            for user in USERS.values()
        ]

    @app.post("/api/v1/auth/login")
    def login(body: SignIn, response: Response):
        user = USERS.get(body.user_id)
        if user is None:
            raise HTTPException(
                401, detail={"code": "unknown_user", "message": "No such local demo user."}
            )
        response.set_cookie(
            COOKIE,
            sign(user.id, session_secret),
            max_age=MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
        )
        return _profile(user)

    @app.get("/api/v1/me")
    def me(user: User = Depends(local_user)):
        return _profile(user)

    @app.post("/api/v1/auth/logout")
    def logout(response: Response):
        response.delete_cookie(COOKIE, path="/")
        return {"signed_out": True}

    app.dependency_overrides[current_user] = local_user
    app.dependency_overrides[get_design_store] = lambda: drafts
    app.dependency_overrides[get_project_store] = lambda: projects
    app.dependency_overrides[get_domain_store] = lambda: domain_store
    # Local demo grants only: Alice proposes and reviews; Bob also approves and administers. Approval still needs
    # someone other than the proposer, so neither can activate their own change.
    app.dependency_overrides[get_org_directory] = lambda: directory
    app.dependency_overrides[get_domain_access] = lambda: (
        lambda user_id: directory.permissions(user_id, None)
    )
    knowledge = WithDomainPacks(
        get_knowledge_provider(), lambda pack_id: active_version(domain_store, pack_id)
    )
    app.dependency_overrides[get_knowledge_provider] = lambda: knowledge
    app.include_router(studio_router, prefix="/api/v1")
    app.include_router(domain_router, prefix="/api/v1")
    app.include_router(workspace_router, prefix="/api/v1")
    return app


def _from_environment() -> FastAPI:
    raw = os.environ.get("DESIGN_STUDIO_LOCAL_DB")
    if not raw:
        raise RuntimeError("DESIGN_STUDIO_LOCAL_DB must name a dedicated temporary SQLite file")
    return create_local_app(Path(raw))


app = _from_environment() if os.environ.get("DESIGN_STUDIO_LOCAL_DEV") == "1" else None
