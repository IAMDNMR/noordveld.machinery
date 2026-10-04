"""The result-type contract: an intent returns the entity type it was asked for, nothing else.

A question walks through intermediate nodes (a part, a warehouse, a supplier...). Those are supporting evidence. Only the requested
entity type may appear as a result card; anything else a handler returns is removed here and logged, so a query that over-reaches
cannot leak intermediate nodes into the answer. The allowed kinds per intent live in registry.RESULT_KINDS.
"""
from __future__ import annotations

import logging

from app.intelligence.models import Intent, Outcome
from app.intelligence.registry import RESULT_KINDS

log = logging.getLogger(__name__)


def enforce_result_kinds(intent: Intent, outcome: Outcome) -> int:
    """Removes results whose kind the intent may not return. Returns how many were removed (0 for a correct handler)."""
    allowed = RESULT_KINDS[intent]
    kept = [r for r in outcome.results if r.kind in allowed]
    dropped = len(outcome.results) - len(kept)
    if dropped:
        log.warning("intent %s returned %d result(s) outside %s: removed", intent.value, dropped, allowed)
        outcome.results = kept
        outcome.total = max(len(kept), outcome.total - dropped)
    return dropped
