"""A minimal signed session for the demo: the cookie carries a user id and an expiry, signed with HMAC-SHA256.

There is no password and no identity provider: the demo signs in as one of the seeded demo users. The role is never read from the
cookie or the browser; it is looked up on the user record for every request.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

COOKIE = "nv_session"
MAX_AGE = 12 * 3600


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(user_id: str, secret: str, now: float | None = None) -> str:
    payload = _b64(json.dumps({"uid": user_id, "exp": int((now or time.time()) + MAX_AGE)}, separators=(",", ":")).encode())
    mac = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{mac}"


def verify(token: str | None, secret: str, now: float | None = None) -> str | None:
    """The user id of a valid, unexpired token; None for anything else (tampered, expired, malformed)."""
    if not token or token.count(".") != 1:
        return None
    payload, mac = token.split(".")
    expected = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(mac, expected):
        return None
    try:
        data = json.loads(_unb64(payload))
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("uid"), str) or int(data.get("exp", 0)) < (now or time.time()):
        return None
    return data["uid"]
