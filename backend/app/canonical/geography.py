"""Where a place is and which country, region and timezone it belongs to: ONE resolver over the location record and the geography reference layer.

Two separate things are combined here, and kept separate in the result:

  location            the Location / Plant / Warehouse / ... record as the reader holds it (graph or canonical file). Never written to.
  geography_profile   additive reference geography (reference/geography.json, data_status REFERENCE): country, region and timezone of a country code, the centre of a named
                      city, and the logistics type a node label implies. It fills ONLY a field the location record leaves empty and says so in `field_sources`.

A protected Location is therefore never changed or "completed" in place: callers that want the combined view call resolve_location_context(); callers that want the record
itself read the record. Coordinate quality is stated, not implied: a reference city centre is REFERENCE, not a surveyed position.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.canonical.io import CANON_DIR

PROTECTED_STATUSES = ("SOURCE_DERIVED", "DERIVED", "REAL")
LOGISTICS_TYPE_BY_LABEL = {"Plant": "PLANT", "Warehouse": "WAREHOUSE", "Dealer": "DEALER", "Supplier": "SUPPLIER", "TransportTerminal": "TERMINAL"}
REFERENCE_PROVENANCE = {"data_status": "REFERENCE", "source_type": "REFERENCE", "source": "backend/data/canonical/reference/geography.json"}
FIELDS = ("latitude", "longitude", "geo_basis", "country", "region", "timezone", "logistics_type")


@lru_cache(maxsize=4)
def _reference(root: str) -> dict[str, Any]:
    return json.loads((Path(root) / "reference" / "geography.json").read_text(encoding="utf-8"))


def reference(root: Path = CANON_DIR) -> dict[str, Any]:
    return _reference(str(root))


def country_profile(country_code: str | None, city: str | None = None, root: Path = CANON_DIR) -> dict[str, str | None]:
    """country name, region and timezone of a country code; a 'CC:City' override wins for the timezone. Unknown code -> all None (never guessed)."""
    ref = reference(root)
    c = ref["countries"].get(country_code or "")
    if not c:
        return {"country": None, "region": None, "timezone": None}
    return {"country": c["name"], "region": c["region"], "timezone": ref["timezone_overrides"].get(f"{country_code}:{city}", c["timezone"])}


def coordinate_class(data_status: str | None, geo_basis: str | None) -> str | None:
    """SOURCE_DERIVED (supplied data), REFERENCE (a reference city centre), SYNTHETIC_DEMO or USER_PROVIDED. Never 'verified': none of these is a surveyed position."""
    if geo_basis is None:
        return None
    if geo_basis == "REFERENCE_CITY_CENTRE":
        return "REFERENCE"
    if data_status in PROTECTED_STATUSES:
        return "SOURCE_DERIVED"
    if data_status == "USER_PROVIDED":
        return "USER_PROVIDED"
    return "SYNTHETIC_DEMO"


def _blank(v: Any) -> bool:
    return v is None or v == "" or v == []


def resolve_location_context(location_id: str, reader: Any = None, root: Path = CANON_DIR) -> dict[str, Any]:
    """The combined view of one place. `reader` is any object with .location(id) returning a canonical-named record (the logistics FileReader or GraphReader); by default the files."""
    if reader is None:
        from app.logistics.readers import FileReader

        reader = FileReader(root)
    rec = reader.location(location_id)
    if rec is None:
        return {"location_id": location_id, "found": False}
    ref = reference(root)
    own = {"latitude": rec.get("latitude"), "longitude": rec.get("longitude"), "geo_basis": rec.get("geo_basis"), "country": rec.get("country"), "region": rec.get("region"),
           "timezone": rec.get("timezone"), "logistics_type": rec.get("location_type")}
    profile: dict[str, Any] = {}
    cc, name = rec.get("country_code"), rec.get("name") or rec.get("city")
    for f, v in country_profile(cc, rec.get("city") or name, root).items():
        if v is not None:
            profile[f] = v
    if name in ref["city_coordinates"]:
        profile["latitude"], profile["longitude"] = ref["city_coordinates"][name]
        profile["geo_basis"] = "REFERENCE_CITY_CENTRE"
    implied = LOGISTICS_TYPE_BY_LABEL.get(rec.get("graph_label") or "")
    if implied:
        profile["logistics_type"] = implied
    sources, resolved = {}, {}
    for f in FIELDS:
        if not _blank(own[f]):
            # a coordinate that is itself a reference city centre says so: it is reference geography whichever record carries it
            from_ref = own["geo_basis"] == "REFERENCE_CITY_CENTRE" and f in ("latitude", "longitude", "geo_basis")
            resolved[f], sources[f] = own[f], "GEOGRAPHY_REFERENCE" if from_ref else "LOCATION"
        elif f in profile:
            resolved[f], sources[f] = profile[f], "DERIVED_FROM_LABEL" if f == "logistics_type" else "GEOGRAPHY_REFERENCE"
        else:
            resolved[f], sources[f] = None, "NONE"
    if resolved["geo_basis"] is None and resolved["latitude"] is not None:
        resolved["geo_basis"], sources["geo_basis"] = "UNSTATED", "NONE"
    fields = {f: {"record_value": None if _blank(own[f]) else own[f], "overlay_value": profile.get(f), "value_source": sources[f]} for f in FIELDS}
    return {"location_id": location_id, "found": True, "fields": fields, "name": rec.get("name"), "graph_label": rec.get("graph_label"), "country_code": cc,
            "protected": rec.get("data_status") in PROTECTED_STATUSES, "location": own, "geography_profile": profile, "resolved": resolved, "field_sources": sources,
            "coordinate_class": coordinate_class(rec.get("data_status"), resolved["geo_basis"]),
            "provenance": {"location": {k: rec.get(k) for k in ("data_status", "source_type", "source_record_id")}, "geography_profile": REFERENCE_PROVENANCE}}
