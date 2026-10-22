"""Storage contract. Production writes stay disabled until durable storage is approved."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Protocol
from uuid import uuid4

from app.schemas.design_studio import DesignDraft, ScreenSpec


class RevisionConflict(RuntimeError):
    pass


class StorageCorrupt(RuntimeError):
    pass


class StorageNotConfigured(RuntimeError):
    pass


class DraftMissing(LookupError):
    pass


class DraftForbidden(PermissionError):
    pass


class DraftStore(Protocol):
    def list(self, owner: str) -> list[DesignDraft]: ...
    def get(self, owner: str, draft_id: str) -> DesignDraft: ...
    def save(
        self,
        owner: str,
        spec: ScreenSpec,
        draft_id: str | None = None,
        expected_revision: int | None = None,
    ) -> DesignDraft: ...


class DisabledDraftStore:
    """Fail closed rather than silently storing drafts in an ephemeral serverless process."""

    def list(self, owner: str) -> list[DesignDraft]:
        raise StorageNotConfigured()

    def get(self, owner: str, draft_id: str) -> DesignDraft:
        raise StorageNotConfigured()

    def save(
        self,
        owner: str,
        spec: ScreenSpec,
        draft_id: str | None = None,
        expected_revision: int | None = None,
    ) -> DesignDraft:
        raise StorageNotConfigured()


class MemoryDraftStore:
    """Isolated test fixture only; not suitable for production persistence."""

    def __init__(self):
        self._drafts: dict[str, DesignDraft] = {}
        self._lock = RLock()

    def list(self, owner: str) -> list[DesignDraft]:
        with self._lock:
            return [
                draft.model_copy(deep=True)
                for draft in self._drafts.values()
                if draft.owner_id == owner
            ]

    def get(self, owner: str, draft_id: str) -> DesignDraft:
        with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                raise DraftMissing()
            if draft.owner_id != owner:
                raise DraftForbidden()
            return draft.model_copy(deep=True)

    def save(
        self,
        owner: str,
        spec: ScreenSpec,
        draft_id: str | None = None,
        expected_revision: int | None = None,
    ) -> DesignDraft:
        with self._lock:
            previous = self.get(owner, draft_id) if draft_id is not None else None
            if previous and (expected_revision is None or previous.revision != expected_revision):
                raise RevisionConflict()
            now = datetime.now(timezone.utc)
            draft = DesignDraft(
                id=draft_id or uuid4().hex,
                owner_id=owner,
                spec=spec.model_copy(deep=True),
                created_at=previous.created_at if previous else now,
                updated_at=now,
                revision=previous.revision + 1 if previous else 1,
            )
            self._drafts[draft.id] = draft
            return draft.model_copy(deep=True)
