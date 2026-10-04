"""City-centre coordinates, used only to draw maps.

This is geographic reference data (where a city is), not Noordveld business data: which plant, warehouse, dealer, supplier
or customer is in which city always comes from the graph. The graph itself stores no coordinates, and nothing here is used to
compute distances or relationships. A city that is not listed simply gets no map position.
"""
from __future__ import annotations

CITY_COORDINATES: dict[str, tuple[float, float]] = {
    "Almelo": (52.3567, 6.6625), "Antwerpen": (51.2194, 4.4025), "Assen": (52.9925, 6.5642), "Bremen": (53.0793, 8.8017),
    "Coevorden": (52.6606, 6.7411), "Dortmund": (51.5136, 7.4653), "Duesseldorf": (51.2277, 6.7735), "Eindhoven": (51.4416, 5.4697),
    "Emmen": (52.7792, 6.9069), "Enschede": (52.2215, 6.8937), "Gent": (51.0543, 3.7174), "Groningen": (53.2194, 6.5665),
    "Hamburg": (53.5511, 9.9937), "Hannover": (52.3759, 9.7320), "Heerenveen": (52.9600, 5.9200), "Koeln": (50.9375, 6.9603),
    "Lingen": (52.5236, 7.3187), "Meppen": (52.6906, 7.2924), "Muenster": (51.9607, 7.6261), "Oldenburg": (53.1435, 8.2146),
    "Osnabrueck": (52.2799, 8.0472), "Rotterdam": (51.9244, 4.4777), "Utrecht": (52.0907, 5.1214), "Venlo": (51.3704, 6.1724),
    "Zwolle": (52.5168, 6.0830),
}


def coordinates(city: str | None) -> tuple[float | None, float | None]:
    point = CITY_COORDINATES.get((city or "").strip())
    return point if point else (None, None)
