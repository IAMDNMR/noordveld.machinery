"""Deterministic serialization and the shipped (file-backed, read-only) domain packs."""

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

from app.domain_knowledge.models import DomainPack

PACK_DIR = Path(__file__).with_name("packs")


def canonical_bytes(pack: DomainPack) -> bytes:
    """Byte-identical for identical content: sorted keys, fixed separators, trailing newline."""
    return (
        json.dumps(pack.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, indent=1)
        + "\n"
    ).encode("utf-8")


def content_sha256(pack: DomainPack) -> str:
    """Fingerprint of the knowledge itself; lifecycle status is excluded so approving a version does not change it."""
    raw = pack.model_dump(mode="json")
    raw.pop("status")
    return sha256(
        json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@lru_cache
def shipped_packs() -> tuple[DomainPack, ...]:
    packs = []
    for path in sorted(PACK_DIR.glob("*.json")):
        packs.append(DomainPack.model_validate_json(path.read_text(encoding="utf-8")))
    ids = [(pack.id, pack.version) for pack in packs]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate shipped domain pack version")
    return tuple(packs)
