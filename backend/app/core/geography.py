"""Country names as a user writes them, to read a place in a request ("Hamburg, Germany").

City coordinates, countries' regions and timezones are canonical reference data now (backend/data/canonical/reference/geography.json) and the map positions the site shows come
from graph locations: nothing about where a city is lives in code. This module keeps only the names people type.
"""
from __future__ import annotations

# Country names as a user writes them -> ISO code. Reference data to read a place name; which country holds a plant, depot, dealer or destination comes from the graph.
COUNTRY_NAMES: dict[str, str] = {
    "austria": "AT", "belgium": "BE", "bulgaria": "BG", "croatia": "HR", "cyprus": "CY", "czechia": "CZ", "czech republic": "CZ", "denmark": "DK",
    "estonia": "EE", "finland": "FI", "france": "FR", "germany": "DE", "greece": "GR", "hungary": "HU", "ireland": "IE", "italy": "IT", "latvia": "LV",
    "lithuania": "LT", "luxembourg": "LU", "malta": "MT", "netherlands": "NL", "the netherlands": "NL", "holland": "NL", "poland": "PL", "portugal": "PT",
    "romania": "RO", "slovakia": "SK", "slovenia": "SI", "spain": "ES", "sweden": "SE", "deutschland": "DE", "nederland": "NL", "belgie": "BE",
}
