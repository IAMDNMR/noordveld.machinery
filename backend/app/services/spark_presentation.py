"""How Spark shows an answer: conversation first, a richer block only when the verified data earns it.

The interpreter model already says what the user wants to see (``SparkPlan.view``: a direct answer, a comparison,
a chart or the graph). This module combines that with the shape of the tool results. Every table cell and chart value
is copied from tool records, never from the model, and a block the data cannot support falls back to text.
"""

import re

from app.schemas.agent import AgentResponse
from app.schemas.intelligence import QueryResponse, ResultItem
from app.schemas.spark import ChartSpec, SparkPresentation, TableSpec

_NUMBER = re.compile(r"^-?\d+(?:[.,]\d+)?$")
#: a table wider than this stops being readable in a chat column
_MAX_COLUMNS = 4


def present(view: str, intelligence: QueryResponse | None, shopping: AgentResponse | None,
            account: dict | None) -> SparkPresentation:
    result = SparkPresentation()
    if intelligence is not None:
        _intelligence(result, view, intelligence)
    if shopping is not None:
        result.shopping = _shopping(view, shopping)
    if account is not None:
        result.account = _account(view, account)
    return result


def _intelligence(result: SparkPresentation, view: str, answer: QueryResponse) -> None:
    records = answer.results
    if answer.clarification:
        result.intelligence = "choices"
        return
    if view == "graph":
        result.intelligence = "graph"
        return
    if not records:
        result.intelligence = "text"
        return
    if view == "chart":
        chart = _chart(records)
        if chart:
            result.intelligence, result.chart = "chart", chart
            return
        result.note = "These records have no comparable numbers to chart, so they are shown as text."
    table = _table(records)
    if view == "compare" and table:
        result.intelligence, result.table = "table", table
    elif len(records) == 1 or _covered(answer.answer.summary, records) or _background(records):
        # the sentence already says what was asked; the records stay one click away
        result.intelligence, result.table = "text", table
    elif table:
        result.intelligence, result.table = "table", table
    else:
        result.intelligence = "cards"


def _covered(summary: str, records: list[ResultItem]) -> bool:
    """A few records the answer sentence already names one by one."""
    text = summary.casefold()
    return len(records) <= 3 and all(r.title.casefold() in text for r in records)


def _background(records: list[ResultItem]) -> bool:
    """Connections around the subject (an overview), which support the sentence rather than answer the question."""
    return all(r.kind in ("relationship", "path") for r in records)


def _table(records: list[ResultItem]) -> TableSpec | None:
    """Rows with consistent attributes: one kind, and fact labels every record has (with at least one recorded value)."""
    if len(records) < 2 or len({r.kind for r in records}) != 1 or any(r.groups for r in records):
        return None
    labels = [f.label for f in records[0].facts]
    shared = [label for label in labels
              if all(any(f.label == label for f in r.facts) for r in records)
              and any(_fact(r, label) for r in records)][:_MAX_COLUMNS]
    if not shared:
        return None
    detail = "Name" if any(r.subtitle for r in records) else None
    return TableSpec(
        columns=[_heading(records[0].kind), *([detail] if detail else []), *shared],
        rows=[{"key": r.key, "title": r.title, "part_number": r.part_number,
               "cells": [*([r.subtitle] if detail else []), *(_fact(r, label) for label in shared)]} for r in records],
    )


def _chart(records: list[ResultItem]) -> ChartSpec | None:
    """A numeric fact recorded on every record, for at least two records. Unknown values are never drawn as zero."""
    if len(records) < 2:
        return None
    for fact in records[0].facts:
        values = [_fact(r, fact.label) for r in records]
        if all(v is not None and _NUMBER.match(v.strip()) for v in values):
            numbers = [float(v.replace(",", ".")) for v in values]
            if any(numbers):
                return ChartSpec(metric=fact.label, rows=[{"name": r.title, "value": n} for r, n in zip(records, numbers)])
    return None


def _fact(record: ResultItem, label: str) -> str | None:
    return next((f.value for f in record.facts if f.label == label), None)


def _heading(kind: str) -> str:
    return {"part": "Part", "warehouse": "Location", "service_plan": "Service plan"}.get(kind, kind.replace("_", " ").capitalize())


def _shopping(view: str, answer: AgentResponse) -> str:
    if answer.state != "recommendation" or not answer.candidates:
        return "text"  # a question or a no-match: the reply is a sentence with its real options
    return "compare" if view == "compare" and len(answer.candidates) > 1 else "product"


def _account(view: str, answer: dict) -> str:
    """Details stay open only when the user has a choice to make in them; a status update is a sentence."""
    if answer.get("clarification"):
        return "text"
    contexts = answer.get("contexts") or {}
    discovery, logistics = contexts.get("DISCOVERY") or {}, contexts.get("LOGISTICS") or {}
    choice = (logistics.get("lookup") == "ROUTE_OPTIONS"
              or (discovery.get("decision") or {}).get("decision") == "RECOMMEND")
    return "detail" if choice or view == "compare" else "text"
