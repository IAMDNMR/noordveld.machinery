"""Anonymous visitors of the public Design Studio demo: one private workspace per browser, no sign-in.

The identity is a random id inside the signed Studio session cookie (the same signature as every Studio session). It is not an
account: it holds the END_USER role, owns only the projects it creates, and is meaningful only while the public demo switch is on.
"""

from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException

from app.core.demo_access import VISITOR_PREFIX
from app.core.roles import Role
from app.services.orders import User

MAX_PROJECTS = 3  # live projects per visitor; Trash does not count so a visitor can start over
# Requests that call the language model, speech or code-generation providers cost money: bounded per visitor (best effort per server
# instance, since instances do not share memory) and for the whole instance.
EXPENSIVE_SUFFIXES = (
    "/studio/turn",
    "/assistant",
    "/voice/transcribe",
    "/voice/speak",
    "/frontend/generate",
)
VISITOR_PER_HOUR = 40
INSTANCE_PER_HOUR = 600
_WINDOW = 3600.0

_lock = Lock()
_visitor_hits: dict[str, deque[float]] = defaultdict(deque)
_instance_hits: deque[float] = deque()


def new_visitor_id() -> str:
    return VISITOR_PREFIX + secrets.token_hex(12)


def is_visitor(user_id: str | None) -> bool:
    return (
        bool(user_id)
        and user_id.startswith(VISITOR_PREFIX)
        and len(user_id) == len(VISITOR_PREFIX) + 24
    )


def visitor_user(user_id: str) -> User:
    return User(
        id=user_id,
        name="Guest",
        email="guest@studio-demo.invalid",
        role=Role.END_USER,
        customer_id=None,
        customer_name="Design Studio demo",
    )


def _refuse(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def check_rate(user_id: str, now: float | None = None) -> None:
    """Raise 429 when this visitor or this instance has used its hourly allowance of expensive requests."""
    now = time.monotonic() if now is None else now
    with _lock:
        for hits in (_instance_hits, _visitor_hits[user_id]):
            while hits and hits[0] <= now - _WINDOW:
                hits.popleft()
        if len(_visitor_hits[user_id]) >= VISITOR_PER_HOUR:
            raise _refuse(
                429,
                "demo_rate_limited",
                "The demo allows a limited number of assistant requests per hour. Please try again later.",
            )
        if len(_instance_hits) >= INSTANCE_PER_HOUR:
            raise _refuse(
                429, "demo_busy", "The demo is busy right now. Please try again in a few minutes."
            )
        _visitor_hits[user_id].append(now)
        _instance_hits.append(now)
        if len(_visitor_hits) > 5000:  # forget idle visitors
            for key in [k for k, v in _visitor_hits.items() if not v][:1000]:
                _visitor_hits.pop(key, None)


class LimitedProjects:
    """A project store that stops a visitor from creating more than MAX_PROJECTS live projects; everything else is the real store."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def create(self, owner, definition):
        if is_visitor(owner):
            live = [
                p
                for p in self._inner.list(owner)
                if not (
                    p.project_lifecycle and p.project_lifecycle.status in ("trashed", "archived")
                )
            ]
            if len(live) >= MAX_PROJECTS:
                raise _refuse(
                    409,
                    "demo_project_limit",
                    f"The demo keeps up to {MAX_PROJECTS} projects per visitor. Move one to Trash to start another.",
                )
        return self._inner.create(owner, definition)
