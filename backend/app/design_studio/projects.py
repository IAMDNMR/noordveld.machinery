"""Versioned project storage contract and isolated in-memory test adapter.

Production storage is intentionally disabled until approved durable infrastructure
and identity guarantees are established.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol

from app.schemas.application_definition import ApplicationDefinition
from app.design_studio.store import (
    DraftForbidden,
    DraftMissing,
    RevisionConflict,
    StorageNotConfigured,
)


@dataclass(frozen=True)
class AuditEvent:
    project_id: str
    revision: int
    actor_id: str
    operation: str
    at: str = ""


# Labels for what a revision did. Plain edits are "update"; server workflows label their own revisions.
OPERATIONS = frozenset(
    {
        "create",
        "project:rename",
        "project:archive",
        "project:trash",
        "project:restore",
        "update",
        "approve:process",
        "approve:design",
        "generate:screens",
        "generate:frontend",
        "select:template",
        "assistant:apply",
        "assistant:context",
        "assistant:revert",
        "studio:resolve",
    }
)


def preserve_lifecycle(
    current: ApplicationDefinition, candidate: ApplicationDefinition, operation: str
) -> ApplicationDefinition:
    """Design edits and revision restores cannot implicitly archive or untrash a project."""
    updates = {}
    if not operation.startswith("project:"):
        updates["project_lifecycle"] = current.project_lifecycle
    if operation != "assistant:context":
        updates["assistant_context"] = current.assistant_context
    return candidate.model_copy(update=updates)


def update_context(current: ApplicationDefinition, candidate: ApplicationDefinition) -> ApplicationDefinition:
    """Private mutable metadata has its own CAS counter, never a new app revision.

    Only this server operation writes it. Application content and its audit record
    remain unchanged, so a chat message cannot invalidate a build or test run.
    """
    previous = current.assistant_context.version if current.assistant_context else 0
    context = candidate.assistant_context
    if context is None or context.version != previous:
        raise RevisionConflict()
    return current.model_copy(deep=True, update={"assistant_context": context.model_copy(deep=True, update={"version": previous + 1})})


class ProjectStore(Protocol):
    def list(self, owner: str) -> list[ApplicationDefinition]: ...
    def create(self, owner: str, definition: ApplicationDefinition) -> ApplicationDefinition: ...
    def current(self, owner: str, project_id: str) -> ApplicationDefinition: ...
    def update(
        self,
        owner: str,
        project_id: str,
        expected_revision: int,
        definition: ApplicationDefinition,
        operation: str = "update",
        actor_id: str | None = None,
    ) -> ApplicationDefinition: ...
    def history(self, owner: str, project_id: str) -> list[ApplicationDefinition]: ...
    def audit_trail(self, owner: str, project_id: str) -> list[dict]: ...


class DisabledProjectStore:
    def list(self, owner: str) -> list[ApplicationDefinition]:
        raise StorageNotConfigured()

    def create(self, owner: str, definition: ApplicationDefinition) -> ApplicationDefinition:
        raise StorageNotConfigured()

    def current(self, owner: str, project_id: str) -> ApplicationDefinition:
        raise StorageNotConfigured()

    def update(
        self,
        owner: str,
        project_id: str,
        expected_revision: int,
        definition: ApplicationDefinition,
        operation: str = "update",
        actor_id: str | None = None,
    ) -> ApplicationDefinition:
        raise StorageNotConfigured()

    def history(self, owner: str, project_id: str) -> list[ApplicationDefinition]:
        raise StorageNotConfigured()

    def audit_trail(self, owner: str, project_id: str) -> list[dict]:
        raise StorageNotConfigured()


class MemoryProjectStore:
    """For isolated tests, never for production durability."""

    def __init__(self):
        self._data: dict[str, tuple[str, list[ApplicationDefinition]]] = {}
        self._events: list[AuditEvent] = []
        self._lock = RLock()

    def _versions(self, owner: str, project_id: str) -> list[ApplicationDefinition]:
        item = self._data.get(project_id)
        if item is None:
            raise DraftMissing()
        if item[0] != owner:
            raise DraftForbidden()
        return item[1]

    def list(self, owner: str) -> list[ApplicationDefinition]:
        with self._lock:
            return [
                versions[-1].model_copy(deep=True)
                for stored_owner, versions in self._data.values()
                if stored_owner == owner
            ]

    def create(self, owner: str, definition: ApplicationDefinition) -> ApplicationDefinition:
        with self._lock:
            if definition.id in self._data:
                raise RevisionConflict()
            first = definition.model_copy(deep=True, update={"revision": 1})
            self._data[first.id] = (owner, [first])
            self._events.append(
                AuditEvent(first.id, 1, owner, "create", datetime.now(timezone.utc).isoformat())
            )
            return first.model_copy(deep=True)

    def current(self, owner: str, project_id: str) -> ApplicationDefinition:
        with self._lock:
            return self._versions(owner, project_id)[-1].model_copy(deep=True)

    def update(
        self,
        owner: str,
        project_id: str,
        expected_revision: int,
        definition: ApplicationDefinition,
        operation: str = "update",
        actor_id: str | None = None,
    ) -> ApplicationDefinition:
        if operation not in OPERATIONS:
            raise ValueError("Unknown operation")
        with self._lock:
            versions = self._versions(owner, project_id)
            if definition.id != project_id or expected_revision != versions[-1].revision:
                raise RevisionConflict()
            if operation == "assistant:context":
                versions[-1] = update_context(versions[-1], definition)
                return versions[-1].model_copy(deep=True)
            definition = preserve_lifecycle(versions[-1], definition, operation)
            updated = definition.model_copy(deep=True, update={"revision": expected_revision + 1})
            versions.append(updated)
            self._events.append(
                AuditEvent(
                    project_id,
                    updated.revision,
                    actor_id or owner,
                    operation,
                    datetime.now(timezone.utc).isoformat(),
                )
            )
            return updated.model_copy(deep=True)

    def history(self, owner: str, project_id: str) -> list[ApplicationDefinition]:
        with self._lock:
            return [version.model_copy(deep=True) for version in self._versions(owner, project_id)]

    def audit_trail(self, owner: str, project_id: str) -> list[dict]:
        with self._lock:
            self._versions(owner, project_id)
            return [
                {
                    "revision": event.revision,
                    "actor": event.actor_id,
                    "operation": event.operation,
                    "at": event.at,
                }
                for event in self._events
                if event.project_id == project_id
            ]

    def audit(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._events)
