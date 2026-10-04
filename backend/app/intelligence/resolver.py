"""Entity resolution against Neo4j. Several equally good matches are returned as candidates, never silently chosen between."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.graph.repositories.intelligence import IntelligenceRepository
from app.intelligence.models import Kind, Resolved
from app.schemas.intelligence import SelectedEntity

MAX_CANDIDATES = 6


@dataclass
class Resolution:
    """Best matches per kind: the lowest (most exact) tier found for that kind, across every mention."""

    by_kind: dict[Kind, list[Resolved]] = field(default_factory=dict)

    def one(self, kind: Kind) -> Resolved | None:
        found = self.by_kind.get(kind, [])
        return found[0] if len(found) == 1 else None

    def many(self, kind: Kind) -> list[Resolved]:
        found = self.by_kind.get(kind, [])
        return found if len(found) > 1 else []

    def all_unique(self) -> list[Resolved]:
        return [found[0] for found in self.by_kind.values() if len(found) == 1]


def _to_resolved(row: dict) -> Resolved:
    return Resolved(Kind(row["kind"]), row["id"], row["label"], row.get("detail"), row.get("data_status"), int(row["tier"]))


class EntityResolver:
    def __init__(self, repo: IntelligenceRepository) -> None:
        self._repo = repo

    def _lookup(self, mention: str) -> list[Resolved]:
        words = mention.split()[:6]
        # "NV 4500 loader" -> the whole phrase, then without trailing words; "supplies water pump" -> then without leading words
        tries = [words[:n] for n in range(len(words), 0, -1)] + [words[n:] for n in range(1, len(words))]
        for attempt in tries:
            rows = self._repo.resolve(" ".join(attempt))
            if rows:
                return [_to_resolved(r) for r in rows]
        return []

    def resolve(self, mentions: tuple[str, ...], selected: list[SelectedEntity] | None = None) -> Resolution:
        picked: dict[Kind, list[Resolved]] = {}
        for sel in selected or []:  # the user already disambiguated: accept only an exact match of that kind
            exact = [r for r in self._lookup(sel.key) if r.kind == sel.kind and r.tier == 0]
            if len(exact) == 1:
                picked[Kind(sel.kind)] = exact
        pool: dict[Kind, dict[str, Resolved]] = {}
        for mention in mentions:
            for r in self._lookup(mention):
                if r.kind in picked:
                    continue
                best = pool.setdefault(r.kind, {})
                current = next(iter(best.values()), None)
                if current is None or r.tier < current.tier:
                    best.clear()
                if current is None or r.tier <= current.tier:
                    best[r.id] = r
        resolution = Resolution(dict(picked))
        for kind, best in pool.items():
            resolution.by_kind[kind] = list(best.values())[:MAX_CANDIDATES]
        return resolution
