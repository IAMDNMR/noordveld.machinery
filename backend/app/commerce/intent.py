"""Intent / flow selection: DISCOVERY, LOGISTICS or WARRANTY, from a request that has not already been classified.

The conversational agent normally supplies the intent itself (it has the whole conversation). This selector is the conservative fallback: weighted cue phrases, and it answers only when
one flow is clearly ahead. One weak keyword never selects a flow; a tie or a narrow lead is REQUIRES_CLARIFICATION. It is a lookup of phrases, not a model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DISCOVERY, LOGISTICS, WARRANTY = "DISCOVERY", "LOGISTICS", "WARRANTY"
INTENTS = (DISCOVERY, LOGISTICS, WARRANTY)
MIN_SCORE, MIN_LEAD = 2, 2  # a flow needs at least two points and a lead of at least two over the next flow

CUES: dict[str, tuple[tuple[str, int], ...]] = {
    DISCOVERY: ((r"\b(fits?|fitting|compatible|compatibility)\b", 2), (r"\b(i need|we need|need an?|looking for|want to buy|find me|find an?|recommend\w*)\b", 1),
                (r"\b(pumps?|filters?|hoses?|seals?|valves?|bearings?|cylinders?|gaskets?|sensors?|belts?|bolts?)\b", 1),
                (r"\bwhich (part|pump|filter|hose|seal|valve|bearing|cylinder)s?\b", 2), (r"\b(part|parts|spares?|replacement)\b", 1), (r"\bfor my\b", 1)),
    LOGISTICS: ((r"\bwhere (is|are)\b", 3), (r"\b(shipments?|shipping|tracking|track|deliver\w*|eta|arrive|arrival|in transit|dispatch\w*|freight|courier)\b", 2), (r"\b(order|orders)\b", 1),
                (r"\b(when will|how long)\b", 1)),
    WARRANTY: ((r"\bwarranty\b", 3), (r"\b(covered|coverage|claim|claims|defect\w*|faulty|failed|failure|broke\w*)\b", 2), (r"\binstalled\b", 1), (r"\breplaced\b", 1)),
}


@dataclass(frozen=True)
class IntentChoice:
    intent: str | None
    scores: dict[str, int]
    source: str  # PROVIDED | DETECTED | UNCLEAR
    reason: str


def score(text: str) -> dict[str, int]:
    low = text.lower()
    return {intent: sum(w for pattern, w in cues if re.search(pattern, low)) for intent, cues in CUES.items()}


def select_intent(text: str, provided: str | None = None) -> IntentChoice:
    scores = score(text or "")
    if provided:
        if provided not in INTENTS:
            raise ValueError(f"unknown intent {provided!r}")
        return IntentChoice(provided, scores, "PROVIDED", "The caller supplied a normalised intent.")
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    (top, top_score), (_, second) = ranked[0], ranked[1]
    if top_score >= MIN_SCORE and top_score - second >= MIN_LEAD:
        return IntentChoice(top, scores, "DETECTED", f"{top} leads with {top_score} against {second}.")
    if top_score == 0:
        return IntentChoice(None, scores, "UNCLEAR", "Nothing in the request points to discovery, logistics or warranty.")
    return IntentChoice(None, scores, "UNCLEAR", f"No flow is clearly ahead ({top} {top_score}, next {second}); a weak or shared cue does not select a flow.")
