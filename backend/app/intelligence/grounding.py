"""Checks a model-written summary against the evidence it was given. A summary that fails is discarded for the deterministic one."""
from __future__ import annotations

import json
import re
from typing import Any

# Anything with a digit is a number, part number, model code or id. All of them must already appear in the evidence or draft.
_WITH_DIGIT = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*\d[A-Za-z0-9\-]*")
_CLAIM_WORDS = re.compile(r"interchangeab|replacement|alternative|equivalent|substitut|compatible with all|guarantee|certified|in stock|out of stock|zero|no stock", re.I)
MAX_WORDS = 70
MAX_IDENTIFIERS = 4  # the cards list the items; a sentence that recites them all is rejected


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def is_grounded(candidate: str, evidence: list[dict[str, Any]], draft: str, question: str) -> bool:
    if not candidate or len(candidate.split()) > MAX_WORDS:
        return False
    if len(_WITH_DIGIT.findall(candidate)) > MAX_IDENTIFIERS:
        return False
    allowed_text = json.dumps(evidence, ensure_ascii=False) + " " + draft + " " + question
    allowed = {_norm(t) for t in _WITH_DIGIT.findall(allowed_text)}
    if any(_norm(t) not in allowed for t in _WITH_DIGIT.findall(candidate)):
        return False
    source = (draft + " " + json.dumps(evidence)).lower()
    return all(m.group(0).lower() in source for m in _CLAIM_WORDS.finditer(candidate))
