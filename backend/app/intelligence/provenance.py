"""Provenance vocabulary: how graph `data_status` values map to what the UI shows. Unknown stays unknown."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import cast

from app.schemas.intelligence import DataClass, Evidence, ProvenanceSummary, ResultItem

_KNOWN: frozenset[str] = frozenset(
    {"REAL", "SOURCE_DERIVED", "DERIVED", "SYNTHETIC_DEMO", "USER_PROVIDED", "TEST_DATA", "INTERNAL_REFERENCE_ONLY", "NOT_CONNECTED"}
)

LABELS: dict[str, str] = {
    "REAL": "Real",
    "SOURCE_DERIVED": "Source-derived",
    "DERIVED": "Derived",
    "SYNTHETIC_DEMO": "Synthetic demo",
    "USER_PROVIDED": "User-provided",
    "TEST_DATA": "Test data",
    "INTERNAL_REFERENCE_ONLY": "Internal reference only",
    "UNKNOWN": "Unclassified",
    "NOT_CONNECTED": "Not connected",
}

MEANINGS: dict[str, str] = {
    "SOURCE_DERIVED": "Taken from the supplied Noordveld catalogue.",
    "DERIVED": "Computed from source data.",
    "SYNTHETIC_DEMO": "Demonstration data created for this project. Not enterprise truth.",
    "USER_PROVIDED": "Supplied by a user.",
    "REAL": "Confirmed live enterprise data.",
    "UNKNOWN": "The graph does not state where this value came from.",
    "NOT_CONNECTED": "No such data is connected to the graph.",
}


def data_class(status: str | None) -> DataClass:
    return cast(DataClass, status if status in _KNOWN else "UNKNOWN")


def summarise(items: Iterable[ResultItem], evidence: Iterable[Evidence]) -> list[ProvenanceSummary]:
    """How many results and evidence edges fall in each data class, so the UI can state it plainly."""
    counts: Counter[str] = Counter(i.data_class for i in items)
    counts.update(e.data_class for e in evidence)
    return [ProvenanceSummary(data_class=cast(DataClass, c), count=n) for c, n in sorted(counts.items())]
