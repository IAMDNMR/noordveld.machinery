"""A knowledge provider that reads packs from a graph instead of from files.

The graph holds each pack version's document next to its decomposed semantic nodes, so one store both describes the knowledge (for the
explorer, search and impact analysis) and serves it (to the generator). The reader is injected: tests give it the in-memory graph; a future
deployment gives it a read-only session on the dedicated knowledge graph. Nothing here opens a connection.
"""

from __future__ import annotations

import pickle
from typing import Protocol

from app.design_studio.knowledge.models import Capability, KnowledgeDomain, ReferencePack
from app.design_studio.knowledge.provider import PackUnavailable, build_packs


class GraphReader(Protocol):
    def documents(self, statuses: tuple[str, ...] = ...) -> list[dict]: ...
    def capability_documents(self) -> list[dict]: ...


class GraphKnowledgeProvider:
    """Serves the latest version of each pack the graph holds. Deprecated packs are never served; draft packs only when asked for."""

    def __init__(self, reader: GraphReader, statuses: tuple[str, ...] = ("approved", "in_review")):
        self._context_reader = getattr(reader, "context_catalog", None)
        self._reference_reader = getattr(reader, "process_references", None)
        newest: dict[str, dict] = {}
        self._documents = reader.documents(statuses)
        for document in self._documents:
            current = newest.get(document["id"])
            if current is None or _key(document["version"]) > _key(current["version"]):
                newest[document["id"]] = document
        self._packs = build_packs(newest)
        # Callers get their own copies; unpickling a snapshot is several times faster than a deep model copy.
        self._frozen = {pack_id: pickle.dumps(pack) for pack_id, pack in self._packs.items()}
        self._reads: dict = {}
        self._capabilities = [
            Capability.model_validate(item) for item in reader.capability_documents()
        ]

    def context_catalog(self, version=None):
        return self._read(("catalog", version), lambda: self._context_reader(version) if self._context_reader else None)

    def process_references(self):
        return self._read(("references",), lambda: self._reference_reader() if self._reference_reader else [])

    def _read(self, key, load):
        # Read once per provider; the graph provider is rebuilt whenever the stored knowledge changes.
        if key not in self._reads:
            self._reads[key] = pickle.dumps(load())
        return pickle.loads(self._reads[key])

    def packs(self) -> list[ReferencePack]:
        return [pickle.loads(frozen) for frozen in self._frozen.values()]

    def pack(self, pack_id: str) -> ReferencePack:
        if pack_id not in self._packs:
            raise PackUnavailable(pack_id)
        return pickle.loads(self._frozen[pack_id])

    def pack_version(self, pack_id: str, version: str) -> ReferencePack:
        document = next(
            (d for d in self._documents if d["id"] == pack_id and d["version"] == version), None
        )
        if document is None:
            raise PackUnavailable(f"{pack_id}@{version}")
        documents = {p.id: p.model_dump(mode="json") for p in self._packs.values()}
        documents[pack_id] = document
        return build_packs(documents)[pack_id].model_copy(deep=True)

    def domains(self) -> list[KnowledgeDomain]:
        seen: dict[str, KnowledgeDomain] = {}
        for pack in self._packs.values():
            for domain in pack.domains:
                seen.setdefault(domain.id, domain)
        return [domain.model_copy(deep=True) for domain in seen.values()]

    def capabilities(self) -> list[Capability]:
        return [item.model_copy(deep=True) for item in self._capabilities]


def _key(version: str) -> tuple:
    return tuple(
        int(part) if part.isdigit() else 0 for part in version.replace("-", ".").split(".")
    )
