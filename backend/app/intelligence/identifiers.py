"""Exact identifier detection. This is entity assistance only: it finds things that LOOK like part numbers, machine models, order
numbers or legacy references so they can be looked up in the graph exactly. It never decides what a question means; the
language model does that (see service.py)."""
from __future__ import annotations

import re

# Part numbers, machine models, order and legacy numbers look like letters + digits (+ letters), in any case and with or
# without separators: "AB-1234-CD", "ab 1234 cd", "AB1234CD". A trailing word may be swallowed ("AB-1234 use"); the
# resolver drops trailing words until something matches.
_IDENT = re.compile(r"\b[A-Za-z]{1,5}[- ]?\d{2,5}(?:[- ]?[A-Za-z]{1,3}\b)*")
_BARE_NUMBER = re.compile(r"\b\d{3,5}\b")


def identifiers(question: str) -> tuple[str, ...]:
    found: list[str] = []
    for m in _IDENT.finditer(question):
        text = m.group(0).strip()
        if text.lower() not in {f.lower() for f in found}:
            found.append(text)
    for m in _BARE_NUMBER.finditer(question):
        if not any(m.group(0) in f for f in found):
            found.append(m.group(0))
    return tuple(found)
