"""Signed, expiring links to the live demo of one project: the application with sample data, opened in its own tab.

The link names a project and its owner and is signed with the site secret, so it cannot be forged or pointed at another project. It
opens a read-only page: records and cases live in that page only and nothing is saved. Anyone holding the link can open it until it
expires; the project itself, its Studio and every other project stay behind the normal sign-in."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

TTL_SECONDS = 7 * 24 * 3600
PURPOSE = "studio-live-demo:"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _mac(payload: str, secret: str) -> str:
    return _b64(hmac.new((PURPOSE + secret).encode(), payload.encode(), hashlib.sha256).digest())


def make_token(owner_id: str, project_id: str, secret: str, now: float | None = None) -> str:
    payload = _b64(
        json.dumps(
            {"o": owner_id, "p": project_id, "exp": int((now or time.time()) + TTL_SECONDS)}, separators=(",", ":")
        ).encode()
    )
    return f"{payload}.{_mac(payload, secret)}"


def read_token(token: str, secret: str, now: float | None = None) -> tuple[str, str] | None:
    """(owner id, project id) of a valid, unexpired link; None for anything else."""
    if not token or token.count(".") != 1 or not secret:
        return None
    payload, mac = token.split(".")
    if not hmac.compare_digest(mac, _mac(payload, secret)):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except ValueError:
        return None
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("o"), str)
        or not isinstance(data.get("p"), str)
        or int(data.get("exp", 0)) < (now or time.time())
    ):
        return None
    return data["o"], data["p"]
