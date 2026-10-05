"""European geography for the synthetic network: 27 EU member states, approximate city-centre coordinates, and the terminal /
corridor structure. Coordinates are approximate public geographic references (city centres) used only to compute straight-line
distances; every distance that is not a straight line is synthetic. No UK, no non-EU country, no US location appears here.
"""
from __future__ import annotations

import math

# code: (name, calling code, language group, postal format key)
COUNTRIES: dict[str, tuple[str, str, str]] = {
    "AT": ("Austria", "+43", "de"), "BE": ("Belgium", "+32", "nl"), "BG": ("Bulgaria", "+359", "bg"), "HR": ("Croatia", "+385", "hr"),
    "CY": ("Cyprus", "+357", "el"), "CZ": ("Czechia", "+420", "cs"), "DK": ("Denmark", "+45", "da"), "EE": ("Estonia", "+372", "et"),
    "FI": ("Finland", "+358", "fi"), "FR": ("France", "+33", "fr"), "DE": ("Germany", "+49", "de"), "GR": ("Greece", "+30", "el"),
    "HU": ("Hungary", "+36", "hu"), "IE": ("Ireland", "+353", "en"), "IT": ("Italy", "+39", "it"), "LV": ("Latvia", "+371", "lv"),
    "LT": ("Lithuania", "+370", "lt"), "LU": ("Luxembourg", "+352", "fr"), "MT": ("Malta", "+356", "en"), "NL": ("Netherlands", "+31", "nl"),
    "PL": ("Poland", "+48", "pl"), "PT": ("Portugal", "+351", "pt"), "RO": ("Romania", "+40", "ro"), "SK": ("Slovakia", "+421", "sk"),
    "SI": ("Slovenia", "+386", "sl"), "ES": ("Spain", "+34", "es"), "SE": ("Sweden", "+46", "sv"),
}
EU27 = tuple(sorted(COUNTRIES))
ISLANDS = frozenset({"IE", "MT", "CY"})  # no road link to the mainland: reachable by sea or air only

# (country, city, region, lat, lon). ASCII spellings, as the existing graph uses (Muenster, Koeln, Duesseldorf).
CITIES: list[tuple[str, str, str, float, float]] = [
    # Netherlands
    ("NL", "Amsterdam", "Noord-Holland", 52.37, 4.90), ("NL", "Rotterdam", "Zuid-Holland", 51.92, 4.48), ("NL", "Den Haag", "Zuid-Holland", 52.08, 4.31),
    ("NL", "Utrecht", "Utrecht", 52.09, 5.12), ("NL", "Amersfoort", "Utrecht", 52.16, 5.39), ("NL", "Eindhoven", "Noord-Brabant", 51.44, 5.48),
    ("NL", "Breda", "Noord-Brabant", 51.59, 4.78), ("NL", "Tilburg", "Noord-Brabant", 51.56, 5.09), ("NL", "Groningen", "Groningen", 53.22, 6.57),
    ("NL", "Zwolle", "Overijssel", 52.51, 6.09), ("NL", "Enschede", "Overijssel", 52.22, 6.89), ("NL", "Almelo", "Overijssel", 52.36, 6.66),
    ("NL", "Venlo", "Limburg", 51.37, 6.17), ("NL", "Maastricht", "Limburg", 50.85, 5.69), ("NL", "Emmen", "Drenthe", 52.78, 6.90),
    ("NL", "Assen", "Drenthe", 52.99, 6.56), ("NL", "Coevorden", "Drenthe", 52.66, 6.74), ("NL", "Arnhem", "Gelderland", 51.98, 5.91),
    ("NL", "Nijmegen", "Gelderland", 51.84, 5.86), ("NL", "Leeuwarden", "Friesland", 53.20, 5.80), ("NL", "Heerenveen", "Friesland", 52.96, 5.92),
    ("NL", "Almere", "Flevoland", 52.37, 5.22), ("NL", "Middelburg", "Zeeland", 51.50, 3.61),
    # Germany
    ("DE", "Hamburg", "Hamburg", 53.55, 9.99), ("DE", "Bremen", "Bremen", 53.08, 8.80), ("DE", "Hannover", "Niedersachsen", 52.37, 9.74),
    ("DE", "Osnabrueck", "Niedersachsen", 52.28, 8.05), ("DE", "Lingen", "Niedersachsen", 52.52, 7.32), ("DE", "Meppen", "Niedersachsen", 52.69, 7.29),
    ("DE", "Oldenburg", "Niedersachsen", 53.14, 8.21), ("DE", "Muenster", "Nordrhein-Westfalen", 51.96, 7.63), ("DE", "Dortmund", "Nordrhein-Westfalen", 51.51, 7.47),
    ("DE", "Koeln", "Nordrhein-Westfalen", 50.94, 6.96), ("DE", "Duesseldorf", "Nordrhein-Westfalen", 51.23, 6.77), ("DE", "Duisburg", "Nordrhein-Westfalen", 51.43, 6.76),
    ("DE", "Essen", "Nordrhein-Westfalen", 51.46, 7.01), ("DE", "Frankfurt", "Hessen", 50.11, 8.68), ("DE", "Kassel", "Hessen", 51.31, 9.48),
    ("DE", "Stuttgart", "Baden-Wuerttemberg", 48.78, 9.18), ("DE", "Mannheim", "Baden-Wuerttemberg", 49.49, 8.47), ("DE", "Muenchen", "Bayern", 48.14, 11.58),
    ("DE", "Nuernberg", "Bayern", 49.45, 11.08), ("DE", "Regensburg", "Bayern", 49.02, 12.10), ("DE", "Leipzig", "Sachsen", 51.34, 12.37),
    ("DE", "Dresden", "Sachsen", 51.05, 13.74), ("DE", "Berlin", "Berlin", 52.52, 13.40), ("DE", "Magdeburg", "Sachsen-Anhalt", 52.13, 11.63),
    ("DE", "Rostock", "Mecklenburg-Vorpommern", 54.09, 12.14),
    # Belgium
    ("BE", "Antwerpen", "Antwerpen", 51.22, 4.40), ("BE", "Mechelen", "Antwerpen", 51.03, 4.48), ("BE", "Gent", "Oost-Vlaanderen", 51.05, 3.72),
    ("BE", "Brussel", "Brussel", 50.85, 4.35), ("BE", "Leuven", "Vlaams-Brabant", 50.88, 4.70), ("BE", "Brugge", "West-Vlaanderen", 51.21, 3.22),
    ("BE", "Liege", "Liege", 50.63, 5.57), ("BE", "Charleroi", "Hainaut", 50.41, 4.44),
    # France
    ("FR", "Paris", "Ile-de-France", 48.86, 2.35), ("FR", "Lille", "Hauts-de-France", 50.63, 3.06), ("FR", "Dunkerque", "Hauts-de-France", 51.03, 2.38),
    ("FR", "Rouen", "Normandie", 49.44, 1.10), ("FR", "Le Havre", "Normandie", 49.49, 0.11), ("FR", "Strasbourg", "Grand Est", 48.57, 7.75),
    ("FR", "Metz", "Grand Est", 49.12, 6.18), ("FR", "Lyon", "Auvergne-Rhone-Alpes", 45.76, 4.84), ("FR", "Dijon", "Bourgogne-Franche-Comte", 47.32, 5.04),
    ("FR", "Marseille", "Provence-Alpes-Cote d'Azur", 43.30, 5.37), ("FR", "Toulouse", "Occitanie", 43.60, 1.44), ("FR", "Bordeaux", "Nouvelle-Aquitaine", 44.84, -0.58),
    ("FR", "Nantes", "Pays de la Loire", 47.22, -1.55), ("FR", "Rennes", "Bretagne", 48.11, -1.68),
    # Italy
    ("IT", "Milano", "Lombardia", 45.46, 9.19), ("IT", "Brescia", "Lombardia", 45.54, 10.22), ("IT", "Torino", "Piemonte", 45.07, 7.69),
    ("IT", "Verona", "Veneto", 45.44, 10.99), ("IT", "Bologna", "Emilia-Romagna", 44.49, 11.34), ("IT", "Genova", "Liguria", 44.41, 8.93),
    ("IT", "Firenze", "Toscana", 43.77, 11.26), ("IT", "Trieste", "Friuli-Venezia Giulia", 45.65, 13.78), ("IT", "Roma", "Lazio", 41.90, 12.50),
    ("IT", "Napoli", "Campania", 40.85, 14.27), ("IT", "Bari", "Puglia", 41.12, 16.87), ("IT", "Palermo", "Sicilia", 38.12, 13.36),
    # Poland
    ("PL", "Warszawa", "Mazowieckie", 52.23, 21.01), ("PL", "Krakow", "Malopolskie", 50.06, 19.94), ("PL", "Katowice", "Slaskie", 50.26, 19.02),
    ("PL", "Wroclaw", "Dolnoslaskie", 51.11, 17.04), ("PL", "Poznan", "Wielkopolskie", 52.41, 16.93), ("PL", "Gdansk", "Pomorskie", 54.35, 18.65),
    ("PL", "Lodz", "Lodzkie", 51.76, 19.46), ("PL", "Szczecin", "Zachodniopomorskie", 53.43, 14.55), ("PL", "Lublin", "Lubelskie", 51.25, 22.57),
    ("PL", "Bydgoszcz", "Kujawsko-Pomorskie", 53.12, 18.01),
    # Spain
    ("ES", "Madrid", "Comunidad de Madrid", 40.42, -3.70), ("ES", "Barcelona", "Cataluna", 41.39, 2.17), ("ES", "Valencia", "Comunidad Valenciana", 39.47, -0.38),
    ("ES", "Zaragoza", "Aragon", 41.65, -0.89), ("ES", "Bilbao", "Pais Vasco", 43.26, -2.93), ("ES", "Sevilla", "Andalucia", 37.39, -5.98),
    ("ES", "Valladolid", "Castilla y Leon", 41.65, -4.72), ("ES", "Vigo", "Galicia", 42.24, -8.72),
    # Austria
    ("AT", "Wien", "Wien", 48.21, 16.37), ("AT", "Linz", "Oberoesterreich", 48.31, 14.29), ("AT", "Graz", "Steiermark", 47.07, 15.44),
    ("AT", "Salzburg", "Salzburg", 47.81, 13.04), ("AT", "Innsbruck", "Tirol", 47.26, 11.39),
    # Czechia
    ("CZ", "Praha", "Praha", 50.08, 14.44), ("CZ", "Brno", "Jihomoravsky", 49.20, 16.61), ("CZ", "Ostrava", "Moravskoslezsky", 49.82, 18.26),
    ("CZ", "Plzen", "Plzensky", 49.75, 13.38), ("CZ", "Olomouc", "Olomoucky", 49.59, 17.25),
    # Nordics and Baltics
    ("SE", "Stockholm", "Stockholm", 59.33, 18.07), ("SE", "Goteborg", "Vastra Gotaland", 57.71, 11.97), ("SE", "Malmo", "Skane", 55.60, 13.00),
    ("SE", "Orebro", "Orebro", 59.27, 15.21),
    ("DK", "Kobenhavn", "Hovedstaden", 55.68, 12.57), ("DK", "Aarhus", "Midtjylland", 56.16, 10.20), ("DK", "Odense", "Syddanmark", 55.40, 10.39),
    ("DK", "Aalborg", "Nordjylland", 57.05, 9.92),
    ("FI", "Helsinki", "Uusimaa", 60.17, 24.94), ("FI", "Tampere", "Pirkanmaa", 61.50, 23.76), ("FI", "Turku", "Varsinais-Suomi", 60.45, 22.27),
    ("FI", "Oulu", "Pohjois-Pohjanmaa", 65.01, 25.47),
    ("LT", "Vilnius", "Vilnius", 54.69, 25.28), ("LT", "Kaunas", "Kaunas", 54.90, 23.90), ("LT", "Klaipeda", "Klaipeda", 55.71, 21.13),
    ("LV", "Riga", "Riga", 56.95, 24.11), ("LV", "Liepaja", "Kurzeme", 56.51, 21.01),
    ("EE", "Tallinn", "Harju", 59.44, 24.75), ("EE", "Tartu", "Tartu", 58.38, 26.72),
    # South and East
    ("PT", "Lisboa", "Lisboa", 38.72, -9.14), ("PT", "Porto", "Norte", 41.15, -8.61), ("PT", "Braga", "Norte", 41.55, -8.42), ("PT", "Coimbra", "Centro", 40.21, -8.43),
    ("RO", "Bucuresti", "Bucuresti-Ilfov", 44.43, 26.10), ("RO", "Cluj-Napoca", "Nord-Vest", 46.77, 23.59), ("RO", "Timisoara", "Vest", 45.75, 21.23),
    ("RO", "Constanta", "Sud-Est", 44.18, 28.65), ("RO", "Brasov", "Centru", 45.65, 25.61),
    ("HU", "Budapest", "Kozep-Magyarorszag", 47.50, 19.04), ("HU", "Debrecen", "Eszak-Alfold", 47.53, 21.63), ("HU", "Gyor", "Nyugat-Dunantul", 47.69, 17.63),
    ("HU", "Szeged", "Del-Alfold", 46.25, 20.15),
    ("SK", "Bratislava", "Bratislavsky", 48.15, 17.11), ("SK", "Kosice", "Kosicky", 48.72, 21.26), ("SK", "Zilina", "Zilinsky", 49.22, 18.74),
    ("SI", "Ljubljana", "Osrednjeslovenska", 46.06, 14.51), ("SI", "Maribor", "Podravska", 46.55, 15.65),
    ("HR", "Zagreb", "Grad Zagreb", 45.81, 15.98), ("HR", "Split", "Splitsko-dalmatinska", 43.51, 16.44), ("HR", "Osijek", "Osjecko-baranjska", 45.55, 18.69),
    ("GR", "Athina", "Attiki", 37.98, 23.73), ("GR", "Thessaloniki", "Kentriki Makedonia", 40.64, 22.94), ("GR", "Patra", "Dytiki Ellada", 38.25, 21.73),
    ("IE", "Dublin", "Leinster", 53.35, -6.26), ("IE", "Cork", "Munster", 51.90, -8.47), ("IE", "Limerick", "Munster", 52.66, -8.63),
    ("LU", "Luxembourg", "Luxembourg", 49.61, 6.13), ("LU", "Esch-sur-Alzette", "Luxembourg", 49.50, 5.98),
    ("MT", "Valletta", "Malta", 35.90, 14.51), ("MT", "Birkirkara", "Malta", 35.90, 14.46),
    ("CY", "Nicosia", "Nicosia", 35.19, 33.38), ("CY", "Limassol", "Limassol", 34.68, 33.04), ("CY", "Larnaca", "Larnaca", 34.92, 33.63),
    ("BG", "Sofia", "Sofia", 42.70, 23.32), ("BG", "Plovdiv", "Plovdiv", 42.14, 24.75), ("BG", "Varna", "Varna", 43.21, 27.91),
]
CITY = {(cc, name): (region, lat, lon) for cc, name, region, lat, lon in CITIES}
CITIES_BY_COUNTRY: dict[str, list[str]] = {}
for _cc, _name, *_ in CITIES:
    CITIES_BY_COUNTRY.setdefault(_cc, []).append(_name)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def city_km(a: tuple[str, str], b: tuple[str, str]) -> float:
    _, la, oa = CITY[a]
    _, lb, ob = CITY[b]
    return haversine_km(la, oa, lb, ob)


# ── terminals: (type, country, city) placed at real infrastructure hubs (TEN-T core ports, inland ports, rail and air cargo hubs) ──
SEAPORTS = [("NL", "Rotterdam"), ("BE", "Antwerpen"), ("DE", "Hamburg"), ("FR", "Le Havre"), ("PL", "Gdansk"), ("SE", "Goteborg"), ("DK", "Aarhus"),
            ("ES", "Barcelona"), ("IT", "Genova"), ("GR", "Athina"), ("RO", "Constanta"), ("IE", "Dublin"), ("MT", "Valletta"), ("CY", "Limassol")]
INLAND_PORTS = [("DE", "Duisburg"), ("DE", "Koeln"), ("DE", "Mannheim"), ("BE", "Liege"), ("FR", "Strasbourg"), ("DE", "Regensburg"), ("AT", "Wien"), ("HU", "Budapest")]
RAIL_TERMINALS = [("NL", "Venlo"), ("DE", "Duisburg"), ("DE", "Hamburg"), ("DE", "Nuernberg"), ("FR", "Lille"), ("FR", "Lyon"), ("PL", "Katowice"),
                  ("CZ", "Brno"), ("AT", "Wien"), ("IT", "Milano"), ("ES", "Zaragoza"), ("HU", "Budapest")]
AIR_TERMINALS = [("NL", "Amsterdam"), ("BE", "Liege"), ("DE", "Frankfurt"), ("FR", "Paris"), ("IT", "Milano"), ("ES", "Madrid"), ("PL", "Warszawa"),
                 ("AT", "Wien"), ("GR", "Athina"), ("DK", "Kobenhavn"), ("FI", "Helsinki"), ("SE", "Stockholm")]
CROSS_DOCKS = [("NL", "Venlo"), ("PL", "Katowice")]

# Corridor structure follows the TEN-T corridor axes (North Sea-Rhine-Mediterranean, Rhine-Alpine, Rhine-Danube, Baltic-Adriatic, Scandinavian-
# Mediterranean, Atlantic). Each link is (mode, city A, city B, corridor); terminals of the same mode in those cities are connected.
RAIL_LINKS = [("NL:Venlo", "DE:Duisburg", "North Sea-Rhine-Mediterranean"), ("DE:Duisburg", "DE:Hamburg", "North Sea-Baltic"),
              ("DE:Duisburg", "DE:Nuernberg", "Rhine-Alpine"), ("NL:Venlo", "FR:Lille", "North Sea-Rhine-Mediterranean"), ("FR:Lille", "FR:Lyon", "North Sea-Rhine-Mediterranean"),
              ("FR:Lyon", "IT:Milano", "Mediterranean"), ("DE:Nuernberg", "AT:Wien", "Rhine-Danube"), ("DE:Nuernberg", "IT:Milano", "Scandinavian-Mediterranean"),
              ("AT:Wien", "HU:Budapest", "Rhine-Danube"), ("AT:Wien", "CZ:Brno", "Baltic-Adriatic"), ("CZ:Brno", "PL:Katowice", "Baltic-Adriatic"),
              ("PL:Katowice", "DE:Hamburg", "North Sea-Baltic"), ("FR:Lyon", "ES:Zaragoza", "Mediterranean"), ("DE:Hamburg", "NL:Venlo", "North Sea-Baltic")]
WATER_LINKS = [("NL:Rotterdam", "DE:Duisburg", "Rhine"), ("BE:Antwerpen", "BE:Liege", "Albert Canal"), ("NL:Rotterdam", "BE:Antwerpen", "Scheldt-Rhine"),
               ("DE:Duisburg", "DE:Koeln", "Rhine"), ("DE:Koeln", "DE:Mannheim", "Rhine"), ("DE:Mannheim", "FR:Strasbourg", "Rhine"),
               ("DE:Mannheim", "DE:Regensburg", "Main-Danube"), ("DE:Regensburg", "AT:Wien", "Danube"), ("AT:Wien", "HU:Budapest", "Danube")]
SEA_LINKS = [("NL:Rotterdam", "SE:Goteborg", "North Sea"), ("NL:Rotterdam", "DK:Aarhus", "North Sea"), ("NL:Rotterdam", "PL:Gdansk", "North Sea-Baltic"),
             ("NL:Rotterdam", "IE:Dublin", "Atlantic"), ("NL:Rotterdam", "FR:Le Havre", "Atlantic"), ("NL:Rotterdam", "ES:Barcelona", "Atlantic-Mediterranean"),
             ("BE:Antwerpen", "NL:Rotterdam", "North Sea"), ("DE:Hamburg", "DK:Aarhus", "Baltic"), ("DE:Hamburg", "PL:Gdansk", "Baltic"), ("DE:Hamburg", "SE:Goteborg", "Baltic"),
             ("FR:Le Havre", "ES:Barcelona", "Atlantic-Mediterranean"), ("FR:Le Havre", "IE:Dublin", "Atlantic"), ("ES:Barcelona", "IT:Genova", "Mediterranean"),
             ("IT:Genova", "GR:Athina", "Mediterranean"), ("IT:Genova", "MT:Valletta", "Mediterranean"), ("MT:Valletta", "GR:Athina", "Mediterranean"),
             ("GR:Athina", "CY:Limassol", "Eastern Mediterranean"), ("GR:Athina", "RO:Constanta", "Black Sea-Aegean"), ("PL:Gdansk", "SE:Goteborg", "Baltic")]

# circuity: route km = straight-line km x factor (a synthetic estimate, never a live routing result)
CIRCUITY = {"ROAD": 1.30, "RAIL": 1.20, "INLAND_WATERWAY": 1.35, "SHORT_SEA": 1.15, "AIR": 1.0}
