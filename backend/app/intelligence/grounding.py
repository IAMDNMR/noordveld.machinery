"""Checks a model-written summary against the evidence it was given. A summary that fails is discarded for the deterministic one."""
from __future__ import annotations

import json
import re
from typing import Any

from app.intelligence.models import Outcome
from app.schemas.intelligence import Subject

# Anything with a digit is a number, part number, model code or id. All of them must already appear in the evidence or draft.
_WITH_DIGIT = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*\d[A-Za-z0-9\-]*")
_CLAIM_WORDS = re.compile(r"interchangeab|replacement|alternative|equivalent|substitut|compatible with all|guarantee|certified|in stock|out of stock|zero|no stock", re.I)
MAX_WORDS = 70
MAX_IDENTIFIERS = 4  # the cards list the items; a sentence that recites them all is rejected


def demo_names(texts: list[str]) -> set[str]:
    """Names in the evidence that end with the demo qualifier."""
    return {t.strip() for t in texts if t and "(demo)" in t}


def keep_demo_qualifier(text: str, names: set[str]) -> str:
    """Puts "(demo)" back after any demo name the wording mentions without it."""
    for full in sorted(names, key=len, reverse=True):
        base = full.replace("(demo)", "").strip()
        if base:
            text = re.sub(re.escape(base) + r"(?!\s*\(demo\))", full, text)
    return text


def drop_false_demo_qualifier(text: str, demo: set[str], names: set[str]) -> str:
    """Removes "(demo)" after a name the evidence does NOT mark as demo (for example a source-derived part number)."""
    shielded = {f"\x00{i}\x00": full for i, full in enumerate(sorted(demo, key=len, reverse=True))}
    for key, full in shielded.items():  # real demo names keep their qualifier, even when they contain a number
        text = text.replace(full, key)
    candidates = set(names) | set(_WITH_DIGIT.findall(text))
    for name in sorted(candidates, key=len, reverse=True):
        base = name.replace("(demo)", "").strip()
        if base and f"{base} (demo)" not in demo:
            text = re.sub(re.escape(base) + r"\s*\(demo\)", base, text)
    for key, full in shielded.items():
        text = text.replace(key, full)
    return text


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


# ── the structured evidence object the wording step receives ─────────────────────────────────────────────────────
MAX_RECORDS = 11  # plus the summary record = the 12 the wording step accepts


def grounding_records(outcome: Outcome, subject: Subject | None = None, limit: int = MAX_RECORDS) -> list[dict[str, Any]]:
    """Everything the wording may say, as data: what the answer is about, how many results there are, and per result its kind, name,
    relationship, data class and EVERY fact (units, primary supplier, lead time, fitment status...), so nothing a sentence could need is
    cut away before the model sees it. Missing values are left out, never written as zero."""
    head: dict[str, Any] = {"total": outcome.total, "shown": min(len(outcome.results), limit)}
    if subject is not None:
        head["about"] = {"kind": subject.kind, "name": subject.label, "detail": subject.name, "data_class": subject.data_class,
                         "facts": {f.label: f.value for f in subject.facts if f.value is not None}}
    rows = [
        {"kind": i.kind, "name": i.title, "detail": i.subtitle, "relationship": i.relationship, "data_class": i.data_class,
         "facts": {f.label: f.value for f in i.facts if f.value is not None}, "groups": {g.label: g.values[:6] for g in i.groups}}
        for i in outcome.results[:limit]
    ] or [e.model_dump() for e in outcome.evidence[:limit]]
    return [head, *rows]


# ── post-generation validation: wording must never deny what the deterministic result holds ───────────────────────
_DENIAL = re.compile(r"\b(no|not|none|neither|cannot|unavailable|unknown|missing|without|lacks?|lacking)\b|n't", re.I)
_QUANTITY_LABELS = {"Units recorded", "Warehouse units recorded", "Quantity"}
_CONCEPTS = (  # (fact labels that prove the value is in the result, the words a sentence uses to name it)
    (_QUANTITY_LABELS, re.compile(r"\b(units?|quantit\w*|unit counts?|how many|stock levels?|on[- ]hand)\b", re.I)),
    ({"Lead time"}, re.compile(r"\blead[- ]times?\b", re.I)),
)
_NOUNS = {"supplier": r"suppliers?", "dealer": r"dealers?", "machine": r"machines?", "assembly": r"assembl(?:y|ies)", "order": r"orders?", "shipment": r"shipments?",
          "service_plan": r"service plans?", "warehouse": r"warehouses?", "compliance": r"compliance requirements?", "part": r"parts?"}


def _denies(text: str, words: re.Pattern[str]) -> bool:
    """A negation right next to a word naming the concept: 'does not contain specific unit counts', 'no primary supplier'."""
    return any(_DENIAL.search(text[max(0, m.start() - 40): m.end() + 25]) for m in words.finditer(text))


def contradicts(text: str, outcome: Outcome) -> str | None:
    """Why `text` contradicts the deterministic result, or None. The caller discards contradictory wording for the evidence-backed answer.

    Checked: a quantity or lead time denied while the result carries one; a primary supplier denied while one is marked; "no <entity>"
    while the result lists that entity; synthetic compliance data worded as established certification."""
    labels = {f.label for i in outcome.results for f in i.facts if f.value is not None}
    for have, words in _CONCEPTS:
        if labels & have and _denies(text, words):
            return f"denies {sorted(labels & have)[0].lower()}"
    if any(f.label == "Primary supplier" and f.value == "Yes" for i in outcome.results for f in i.facts) and _denies(text, re.compile(r"\bprimary\b", re.I)):
        return "denies the primary supplier"
    for kind in {i.kind for i in outcome.results}:
        noun = _NOUNS.get(kind)
        # "No suppliers are connected": existence denied. "No supplier is marked as primary" is a statement about a flag, not about existence.
        if noun and re.search(rf"\b(no|not any)\s+{noun}\b[^.;]{{0,30}}\b(recorded|connected|found|listed|available|exist\w*|linked|associated|stock\w*|hold\w*)\b", text, re.I):
            return f"denies the listed {kind}s"
    compliance = [i for i in outcome.results if i.kind == "compliance"]
    if compliance and all(i.data_class == "SYNTHETIC_DEMO" for i in compliance):
        if re.search(r"certif", text, re.I) and not re.search(r"demo|synthetic|not (?:established|real)|does not establish|no real", text, re.I):
            return "presents synthetic compliance data as established"
    return None
