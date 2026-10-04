"""The single part-status rule shared by the Parts Store, the cart and Parts Intelligence.

Status comes from the part's catalogue profile in the graph (`PartCatalogProfile.part_status`). Only a VERIFIED part that the
profile marks orderable may be priced into a cart or reach checkout.
"""
from __future__ import annotations

STATUS_LABELS: dict[str, str] = {
    "VERIFIED": "Verified",
    "IDENTIFICATION_REQUIRED": "Identification required",
    "AMBIGUOUS": "Ambiguous",
    "UNVERIFIED": "Unverified",
}

STATUS_REASONS: dict[str, str] = {
    "IDENTIFICATION_REQUIRED": "The machine variant or serial range must be confirmed before this part can be ordered.",
    "AMBIGUOUS": "The catalogue entry has more than one reading; the machine, variant or serial must be confirmed before ordering.",
    "UNVERIFIED": "The part has no verified origin and cannot be ordered until it is identified.",
}


def status_label(code: str | None) -> str:
    return STATUS_LABELS.get(code or "", "Unverified")


def is_orderable(part_status: str | None, orderable: bool | None) -> bool:
    return part_status == "VERIFIED" and orderable is True


def rejection_reason(part_status: str | None, orderable: bool | None) -> str:
    if part_status in STATUS_REASONS:
        return STATUS_REASONS[part_status]
    if part_status == "VERIFIED" and orderable is not True:
        return "This part is not orderable online."
    return "This part has no catalogue status and cannot be ordered."
