"""Other names a business uses for a verified pack process ("replenishment" for "Automatic reorder").

A drafted process and a verified one can be the same activity under different names that share no noun, which word matching cannot
tell apart from two real processes. This catalogue declares such names, kept apart from the verified packs and governed like the
process references: every entry says why the names are equivalent, and only an entry a named reviewer has approved can stop a
second process being drafted. A proposed entry only raises a finding for a person to judge.

To approve an entry, set its review_state to "reviewed" with reviewed_by and reviewed_on. To retire one, set it to "deprecated".
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas.application_definition import ID_PATTERN, Strict

CATALOG_PATH = Path(__file__).with_name("process_synonyms.json")


class ProcessSynonyms(Strict):
    workflow_id: str = Field(pattern=ID_PATTERN)
    pack_id: str = Field(pattern=ID_PATTERN)
    names: list[Annotated[str, Field(min_length=3, max_length=80)]] = Field(min_length=1, max_length=10)
    basis: str = Field(min_length=20, max_length=600)  # why these names mean this process, from what the pack itself says
    review_state: Literal["proposed", "reviewed", "deprecated"] = "proposed"
    reviewed_by: str | None = Field(default=None, max_length=120)
    reviewed_on: date | None = None

    @model_validator(mode="after")
    def reviewer_named(self):
        if self.review_state == "reviewed" and not (self.reviewed_by and self.reviewed_on):
            raise ValueError("A reviewed entry needs a named reviewer and a date")
        return self


def validate_synonyms(documents) -> list[ProcessSynonyms]:
    entries = [ProcessSynonyms.model_validate(document) for document in documents]
    owner: dict[str, str] = {}
    for entry in entries:
        if entry.review_state == "deprecated":
            continue
        for name in entry.names:
            key = " ".join(name.lower().split())
            if owner.setdefault(key, entry.workflow_id) != entry.workflow_id:
                raise ValueError(f"'{name}' names two processes; one name must mean one process")
    return entries


@lru_cache(maxsize=1)
def load_synonyms() -> tuple[ProcessSynonyms, ...]:
    return tuple(validate_synonyms(json.loads(CATALOG_PATH.read_text(encoding="utf-8"))))


def synonyms_of(workflow_id: str, reviewed_only: bool = False) -> list[tuple[str, ProcessSynonyms]]:
    """(name, entry) for each other name of a process. Deprecated entries never count; proposed ones count unless reviewed_only."""
    wanted = ("reviewed",) if reviewed_only else ("reviewed", "proposed")
    return [
        (name, entry)
        for entry in load_synonyms()
        if entry.workflow_id == workflow_id and entry.review_state in wanted
        for name in entry.names
    ]
