"""Demo sign-in is permitted only on an undeployed loopback application."""

from __future__ import annotations

import os

from fastapi import Request


PUBLIC_COMMERCE_DEMO_ENV = "PUBLIC_COMMERCE_DEMO"


def public_commerce_demo_enabled() -> bool:
    """Explicit opt-in for a deployed demo site: sign in as a seeded demo user without a password. Off unless set to 1/true/yes/on."""
    return os.environ.get(PUBLIC_COMMERCE_DEMO_ENV, "").strip().strip("\"'").lower() in {"1", "true", "yes", "on"}


def local_demo_request(request: Request) -> bool:
    # Neither the Host header nor a client-controlled role is sufficient alone.
    # Vercel deployments (including previews) are never demo environments, unless the public demo switch is set explicitly.
    if public_commerce_demo_enabled():
        return True
    if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
        return False
    if os.environ.get("APP_ENV", "local").lower() not in {"local", "development", "test"}:
        return False
    host = request.url.hostname
    peer = request.client.host if request.client else ""
    return (
        host in {"localhost", "127.0.0.1", "::1"} and peer in {"localhost", "127.0.0.1", "::1"}
    ) or (host == "testserver" and peer == "testclient")


