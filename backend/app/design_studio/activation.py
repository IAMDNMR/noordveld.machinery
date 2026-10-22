"""Read-only activation preflight. Configuration is never proof of provider approval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit


@dataclass(frozen=True)
class StorageCandidate:
    mode: str
    syntactically_valid: bool
    reason: str


def storage_candidate(environment: Mapping[str, str]) -> StorageCandidate:
    """Report eligibility without opening a connection or revealing a DSN."""
    mode = environment.get("DESIGN_STUDIO_STORAGE_BACKEND", "disabled").strip().lower()
    if mode == "disabled":
        return StorageCandidate(mode, False, "Production storage is disabled")
    if mode not in {"postgres", "cockroach"}:
        return StorageCandidate(
            mode, False, "Select PostgreSQL or CockroachDB durable storage"
        )
    raw = environment.get("DESIGN_STUDIO_DATABASE_URL", "")
    try:
        parsed = urlsplit(raw)
        valid = parsed.scheme in {"postgresql", "postgres"} and bool(
            parsed.hostname and parsed.path.strip("/")
        )
    except ValueError:
        valid = False
    if not valid:
        return StorageCandidate(
            mode, False, "A PostgreSQL connection URL with host and database is required"
        )
    return StorageCandidate(
        mode,
        True,
        "Candidate only: provider, schema, backup, identity and deployment approval are still required",
    )
