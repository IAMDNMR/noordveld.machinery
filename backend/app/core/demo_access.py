"""Demo sign-in is permitted only on an undeployed loopback application."""

from __future__ import annotations

import os

from fastapi import Request


def local_demo_request(request: Request) -> bool:
    # Neither the Host header nor a client-controlled role is sufficient alone.
    # Vercel deployments (including previews) are never demo environments.
    if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
        return False
    if os.environ.get("APP_ENV", "local").lower() not in {"local", "development", "test"}:
        return False
    host = request.url.hostname
    peer = request.client.host if request.client else ""
    return (
        host in {"localhost", "127.0.0.1", "::1"} and peer in {"localhost", "127.0.0.1", "::1"}
    ) or (host == "testserver" and peer == "testclient")


# ── public Design Studio demo ───────────────────────────────────────────────────────────────────────
# An explicit, opt-in switch for a deployed site where anyone may open the Studio without signing in. Each browser gets its own
# anonymous workspace (visitor identity, see app/design_studio/visitors.py); nobody can reach another visitor's or a real account's
# projects, and shared knowledge stays read-only. It never opens the commerce demo sign-in.
PUBLIC_STUDIO_ENV = "DESIGN_STUDIO_PUBLIC_DEMO"
VISITOR_PREFIX = "visitor-"


def public_studio_enabled() -> bool:
    """On when the variable is 1, true, yes or on (any case, quotes ignored); anything else, or unset, is off."""
    return os.environ.get(PUBLIC_STUDIO_ENV, "").strip().strip("\"'").lower() in {"1", "true", "yes", "on"}


def studio_demo_request(request: Request) -> bool:
    """May this request use the Studio without a verified sign-in: a local undeployed request, or the public demo switch is on."""
    return public_studio_enabled() or local_demo_request(request)
