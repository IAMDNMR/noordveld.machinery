"""Deterministic question understanding. Tried first; the LLM is only asked when this cannot decide, so most questions never reach it.

It decides an intent from keywords and pulls out mentions (identifier-like tokens and a residual phrase). It never touches
the database: mentions are resolved against the graph afterwards by the resolver.
"""
from __future__ import annotations

import re

from app.intelligence.models import Intent, ParsedQuestion

# part numbers / machine models / legacy numbers look like letters + digits (+ letters), e.g. "AB-1234-CD", "AB 1234"
_IDENT = re.compile(r"\b[A-Za-z]{1,5}[- ]?\d{2,5}(?:-[A-Za-z]{1,3}|[ ][A-Z]{1,3}\b)*")
_BARE_NUMBER = re.compile(r"\b\d{3,5}\b")

# first match wins; order matters (more specific first)
_RULES: tuple[tuple[Intent, re.Pattern[str]], ...] = (
    (Intent.DATA_QUALITY, re.compile(r"data quality|missing (data|relationship)|coverage|data gaps?|incomplete", re.I)),
    (Intent.PART_PROVENANCE, re.compile(r"provenance|where (does|did) .*(data|come)|data status|data source|synthetic|real or demo|is (it|this) (real|verified)|source of", re.I)),
    (Intent.PART_TO_COMPLIANCE, re.compile(r"complian|certif|standard\b|regulat|iso\b", re.I)),
    (Intent.PART_TO_SUPPLIER, re.compile(r"supplier|suppl(y|ies|ied)\b|vendor|who makes", re.I)),
    (Intent.PART_TO_DEALER, re.compile(r"dealer|stocked by|distributor|who stocks", re.I)),
    (Intent.PART_TO_INVENTORY, re.compile(r"\bstock|inventory|in stock|how many (are )?(available|left)|units", re.I)),
    (Intent.PART_TO_LOCATION, re.compile(r"where .*(available|stored|located|find|buy)|location|which (city|country)|warehouse", re.I)),
    (Intent.PART_TO_PART, re.compile(r"related|co-?ordered|ordered together|alternative|replace|interchang|equivalent|substitut|similar", re.I)),
    (Intent.PART_TO_CATEGORY, re.compile(r"categor|what (kind|type) of part|part type", re.I)),
    (Intent.PART_TO_ASSEMBLY, re.compile(r"assembl|component|bill of material|\bbom\b|part of|contain|made up|consist", re.I)),
    (Intent.PART_GRAPH, re.compile(r"relationship|graph|connect|network|linked", re.I)),
    (Intent.PART_TO_MACHINE, re.compile(r"\bfit|used (by|on|in)|\buse\b|\buses\b|compatib|work(s)? (with|on)|which machines|what machines|for which machine", re.I)),
)

_PARTS_OF_MACHINE = re.compile(r"\bparts?\b.*\b(for|of|on|in)\b|\bparts?\b|\bcomponents? for\b", re.I)
_SEARCH = re.compile(r"\b(find|search|look( for)?|parts?)\b", re.I)

_STOP = frozenset(
    "a an and any are as at be by can could do does for from give has have how i in is it its me of on or please show tell that the their these this to us "
    "was we what when where which who whom with would you your find search list look need get display "
    "part parts machine machines fit fits used uses use compatible related supplier suppliers dealer dealers assembly assemblies category categories "
    "provenance relationships relationship graph stock inventory available availability compliance location locations connected".split()
)


def _mentions(question: str) -> tuple[str, ...]:
    found: list[str] = []
    for m in _IDENT.finditer(question):
        text = m.group(0).strip()
        if text.lower() not in {f.lower() for f in found}:
            found.append(text)
    for m in _BARE_NUMBER.finditer(question):
        if not any(m.group(0) in f for f in found):
            found.append(m.group(0))
    return tuple(found)


def _residue(question: str, mentions: tuple[str, ...]) -> str:
    text = question
    for m in mentions:
        text = text.replace(m, " ")
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]+", text) if w.lower() not in _STOP]
    return " ".join(words[:5])


def parse(question: str) -> ParsedQuestion:
    q = " ".join(question.split())
    mentions = _mentions(q)
    residue = _residue(q, mentions)
    # a phrase is also a mention: it can name a part ("water pump"), supplier, dealer, assembly or category
    all_mentions = mentions + ((residue,) if residue else ())

    for intent, pattern in _RULES:
        if pattern.search(q):
            return ParsedQuestion(intent, all_mentions, residue)
    if _PARTS_OF_MACHINE.search(q) or _SEARCH.search(q):
        return ParsedQuestion(Intent.PART_SEARCH, all_mentions, residue)
    return ParsedQuestion(None, all_mentions, residue)
