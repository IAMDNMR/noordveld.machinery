"""Part search and detail. Maps graph rows to API models without adding, inferring or defaulting any value."""
from __future__ import annotations

from typing import Any

from app.core.exceptions import NotFoundError
from app.graph.repositories.parts import PartRepository
from app.schemas.catalogue import (
    Availability,
    FitmentBrief,
    Money,
    PartDetail,
    PartPage,
    PartSummary,
)

SORTS = ("relevance", "name", "price_asc", "price_desc")


def to_summary(row: dict[str, Any]) -> PartSummary:
    price = row.get("price")
    profile = row.get("profile")
    availability = None
    if profile or row.get("total_available") is not None:
        profile = profile or {}
        availability = Availability(
            state=profile.get("availability_state"),
            orderable=profile.get("orderable"),
            part_status=profile.get("part_status"),
            total_available=row.get("total_available"),
            data_status=profile.get("data_status"),
        )
    return PartSummary(
        part_id=row["part_id"],
        part_number=row["part_number"],
        name=row["name"],
        category=row.get("category"),
        subcategory=row.get("subcategory"),
        fitment=[FitmentBrief(**f) for f in sorted(row.get("fitment") or [], key=lambda f: f["model_code"])],
        price=Money(**price) if price and price.get("amount") is not None else None,
        availability=availability,
    )


def _price(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row or row.get("list_price_ex_vat") is None:
        return None
    return {**row, "amount": row["list_price_ex_vat"]}


class PartService:
    def __init__(self, repo: PartRepository) -> None:
        self._repo = repo

    def search(
        self,
        *,
        q: str,
        category: str | None,
        machine: str | None,
        availability: list[str] | None,
        orderable: bool | None,
        sort: str,
        offset: int,
        limit: int,
    ) -> PartPage:
        total, ids = self._repo.search(
            text=q, category=category, machine=machine, availability=availability, orderable=orderable,
            sort=sort, offset=offset, limit=limit,
        )
        items = [to_summary(r) for r in self._repo.summaries(ids)]
        return PartPage(items=items, total=total, offset=offset, limit=limit)

    def detail(self, key: str) -> PartDetail:
        row = self._repo.detail(key)
        if row is None:
            raise NotFoundError("Part", key)
        part = dict(row["part"])
        part["note"] = part.pop("spec_note_source", None)
        legacy = [{**l, "note": l.get("legacy_source_note")} for l in row["legacy"]]
        seen: set[tuple[str, str]] = set()
        related = []
        for r in row["related"]:
            ident = (r["part_id"], r["relation"])
            if ident not in seen:
                seen.add(ident)
                related.append(r)
        return PartDetail(
            part=part,
            fitment=sorted(row["fitment"], key=lambda f: f["model_code"]),
            specifications=row["specifications"],
            legacy_references=legacy,
            price=_price(row["price"]),
            profile=row["profile"],
            warehouses=row["warehouses"],
            dealers=row["dealers"],
            suppliers=row["suppliers"],
            compliance=row["compliance"],
            assemblies=row["assemblies"],
            related=related,
            identification=row["identification"],
        )
