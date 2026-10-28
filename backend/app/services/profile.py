"""The user's consented profile: machines, default delivery site, preferred dealer, contact and delivery preferences.

Stored in a small local SQLite file, never in the business graph (AuraDB stays read-only for Spark). Nothing is stored without the user's consent;
withdrawing consent or erasing deletes the row. A profile only pre-fills what Spark would otherwise ask: every value is still validated against the
graph when used, and the order review always shows it for confirmation."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_FIELD = Field(default=None, max_length=200)


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    machines: list[str] = Field(default_factory=list, max_length=5)
    preferred_machine: str | None = Field(default=None, max_length=80)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    ship_to_id: str | None = Field(default=None, max_length=40)
    dealer_id: str | None = Field(default=None, max_length=40)
    name: str | None = _FIELD
    company: str | None = _FIELD
    email: str | None = _FIELD
    phone: str | None = Field(default=None, max_length=40)
    receiver_name: str | None = _FIELD
    receiver_phone: str | None = Field(default=None, max_length=40)
    delivery_preference: Literal["fastest", "cheapest"] | None = None
    delivery_notes: str | None = Field(default=None, max_length=300)


class ProfileWrite(Profile):
    #: storing anything requires an explicit yes; false erases the profile
    consent: bool


class ProfileStore:
    def __init__(self, path: str | Path) -> None:
        self._path, self._lock = str(path), threading.Lock()
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._memory = sqlite3.connect(":memory:", check_same_thread=False) if self._path == ":memory:" else None
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS profile (user_id TEXT PRIMARY KEY, data TEXT NOT NULL, consent_at TEXT NOT NULL)")

    def _db(self):
        db = self._memory or sqlite3.connect(self._path, timeout=5)
        outer = self

        class Ctx:
            def __enter__(self_inner):
                outer._lock.acquire()
                return db

            def __exit__(self_inner, *exc):
                try:
                    db.commit() if exc[0] is None else db.rollback()
                finally:
                    if outer._memory is None:
                        db.close()
                    outer._lock.release()

        return Ctx()

    def get(self, user_id: str) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT data, consent_at FROM profile WHERE user_id = ?", (user_id,)).fetchone()
        return {"profile": json.loads(row[0]), "consent_at": row[1]} if row else None

    def put(self, user_id: str, profile: Profile) -> None:
        with self._db() as db:
            db.execute("INSERT INTO profile (user_id, data, consent_at) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET data = excluded.data",
                       (user_id, profile.model_dump_json(), datetime.now(timezone.utc).isoformat(timespec="seconds")))

    def erase(self, user_id: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM profile WHERE user_id = ?", (user_id,))
