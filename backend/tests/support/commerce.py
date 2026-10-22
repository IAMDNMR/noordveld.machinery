"""An in-memory DiscoveryReader for rules the canonical data does not exercise (no approved source, deprecated fitment, out of region, unknown stock ...).
It is the same lookup code as the file and graph readers, fed a small dataset."""
from __future__ import annotations

from typing import Any

from app.commerce.discovery_reader import _DatasetReader

PROV = {"data_status": "SYNTHETIC_DEMO", "source_type": "SYNTHETIC_DEMO", "source_record_id": None}


def machine(mid="M-1", model="ZX-100", mtype="Wheel Loader"):
    return {"machine_id": mid, "model": model, "machine_type": mtype, "name": f"{model} {mtype}", **PROV}


def part(pid="P-1", name="Gear pump", status="VERIFIED", **kw):
    base = {"part_id": pid, "part_number": f"PN-{pid}", "name": name, "description": None, "category_id": "C-1", "subcategory_id": "S-1", "status": status, "aliases": [], "common_names": [],
            "technical_terms": [], "symptoms": [], **PROV}
    return {**base, **kw}


def fit(pid="P-1", mid="M-1", status="APPROVED", approval="APPROVED", valid_to=None):
    return {"fitment_id": f"FITS:{pid}:{mid}", "machine_id": mid, "part_id": pid, "fitment_status": status, "approval_status": approval, "fitment_rule": "EXACT_MODEL", "valid_from": None,
            "valid_to": valid_to, **PROV}


def source(pid="P-1", n=1, status="APPROVED", regions=(), valid_to=None):
    return {"approved_source_id": f"AS-{pid}-{n}", "part_id": pid, "source_id": f"SUP-{n}", "source_kind": "SUPPLIER", "approval_status": status, "approved_regions": list(regions), "valid_from": None,
            "valid_to": valid_to, **PROV}


def stock(pid="P-1", loc="WH-1", qty=5, status="IN_STOCK"):
    return {"inventory_id": f"INV-{pid}-{loc}", "part_id": pid, "location_id": loc, "quantity": qty, "available_quantity": qty, "reserved_quantity": 0, "status": status, **PROV}


def price(pid="P-1", amount=10.0, n=1):
    return {"price_id": f"PRC-{pid}-{n}", "part_id": pid, "dealer_id": None, "region": None, "currency": "EUR", "unit_price": amount, "valid_from": "2026-01-01", "valid_to": "2026-12-31",
            "status": "DEMO_PRICE", **PROV}


def whouse(loc="WH-1", region="EUROPE", cc="NL"):
    return {"location_id": loc, "name": loc, "country_code": cc, "region": region, **PROV}


class MemoryDiscoveryReader(_DatasetReader):
    def __init__(self, **datasets: list[dict[str, Any]]) -> None:
        super().__init__()
        self._data = {"machines": [machine()], "parts": [part()], "categories": [{"category_id": "C-1", "name": "Hydraulics"}, {"category_id": "S-1", "name": "Gear pump"}], "fitment": [],
                      "approved_sources": [], "inventory": [], "pricing": [], "locations": [whouse()], "customers": [], **datasets}

    def _rows(self, name):
        return self._data[name]

    def region_of_country(self, country_code):
        return {"NL": "EUROPE", "DE": "EUROPE", "US": "USA"}.get(country_code or "")
