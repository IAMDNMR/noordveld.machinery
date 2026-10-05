"""Fictional names, contacts and address fragments. Everything is built from word lists by deterministic picks: no real company,
person, e-mail address or phone number is used. Every company name ends in "(demo)"; every e-mail uses the reserved .example domain;
every phone number uses the 555 01xx style block. Postal codes and street numbers are invented.
"""
from __future__ import annotations

import re
import unicodedata

from common import pick, stable_int
from geo import COUNTRIES

LEGAL = {"NL": "BV", "DE": "GmbH", "BE": "NV", "FR": "SAS", "IT": "S.r.l.", "ES": "S.L.", "PL": "Sp. z o.o.", "AT": "GmbH", "CZ": "s.r.o.", "SK": "s.r.o.",
         "SE": "AB", "DK": "A/S", "FI": "Oy", "PT": "Lda", "RO": "S.R.L.", "HU": "Kft.", "SI": "d.o.o.", "HR": "d.o.o.", "GR": "S.A.", "IE": "Ltd",
         "LT": "UAB", "LV": "SIA", "EE": "OU", "LU": "S.A.", "MT": "Ltd", "CY": "Ltd", "BG": "OOD"}
LANG_GROUP = {"NL": "nl", "BE": "nl", "DE": "de", "AT": "de", "LU": "fr", "FR": "fr", "IT": "it", "ES": "es", "PT": "pt", "PL": "pl", "CZ": "cs", "SK": "cs",
              "SE": "nord", "DK": "nord", "FI": "nord", "EE": "nord", "LV": "nord", "LT": "nord", "RO": "ro", "HU": "hu", "SI": "sl", "HR": "sl", "GR": "el",
              "CY": "el", "BG": "bg", "IE": "en", "MT": "en"}

DEALER_TRADE = {
    "nl": ["Machinehandel", "Materieel", "Werktuigen", "Techniek", "Machines"], "de": ["Maschinen", "Fahrzeugtechnik", "Baumaschinen", "Technik", "Industrietechnik"],
    "fr": ["Engins", "Materiel", "Equipements", "Machines", "Services"], "it": ["Macchine", "Attrezzature", "Movimentazione", "Tecnica", "Industriale"],
    "es": ["Maquinaria", "Equipos", "Manutencion", "Tecnica", "Industrial"], "pt": ["Maquinas", "Equipamentos", "Tecnica", "Industrial", "Servicos"],
    "pl": ["Maszyny", "Sprzet", "Technika", "Serwis", "Przemysl"], "cs": ["Stroje", "Technika", "Servis", "Zarizeni", "Prumysl"],
    "nord": ["Maskiner", "Teknik", "Service", "Maskinhandel", "Utrustning"], "ro": ["Utilaje", "Echipamente", "Tehnica", "Service", "Industrial"],
    "hu": ["Gepek", "Technika", "Szerviz", "Berendezes", "Ipari"], "sl": ["Stroji", "Tehnika", "Servis", "Oprema", "Industrija"],
    "el": ["Michanimata", "Technika", "Exoplismos", "Service", "Viomichania"], "bg": ["Mashini", "Tehnika", "Servis", "Oborudvane", "Industrial"],
    "en": ["Machinery", "Plant", "Equipment", "Handling", "Engineering"],
}
BRAND_WORDS = ["Nordhaven", "Veldmark", "Alpenrand", "Meridian", "Atlas", "Terrafort", "Axiom", "Orion", "Delta", "Prima", "Baltica", "Rivera", "Kestrel",
               "Falcon", "Marlin", "Aurora", "Summit", "Vector", "Beacon", "Granite", "Cobalt", "Lumen", "Harbor", "Ridge", "Anchor", "Sterling", "Quarry"]
SUPPLIER_TRADE = {
    "hydraulics": "Hydraulics", "seals": "Seals", "hoses": "Hose Systems", "fittings": "Fittings", "electrical": "Electrics", "sensors": "Sensorik",
    "controls": "Controls", "safety": "Safety Systems", "bearings": "Bearings", "fasteners": "Fasteners", "drivetrain": "Drivetrain", "material handling": "Handling Components",
    "conveyor components": "Conveyor Components", "structural": "Structures", "braking": "Braking Systems", "wheels/rollers": "Wheels and Rollers",
}
CUSTOMER_SECTOR = {
    "construction": ["Bouw", "Bau", "Construction", "Costruzioni", "Obras"], "quarrying": ["Steengroeve", "Steinbruch", "Carrieres", "Cave", "Kamenolom"],
    "aggregates": ["Grind", "Kies", "Granulats", "Aggregati", "Aridos"], "logistics": ["Logistiek", "Logistik", "Logistique", "Logistica", "Logistics"],
    "warehousing": ["Opslag", "Lager", "Entrepots", "Magazzini", "Almacenes"], "manufacturing": ["Industrie", "Fertigung", "Fabrication", "Produzione", "Fabricacion"],
    "agriculture": ["Agri", "Agrar", "Agricole", "Agricola", "Agro"], "ports": ["Haven", "Hafen", "Terminal", "Porto", "Puerto"],
    "recycling": ["Recycling", "Recycling", "Recyclage", "Riciclo", "Reciclaje"], "infrastructure": ["Infra", "Infrastruktur", "Infrastructures", "Infrastrutture", "Infraestructuras"],
    "utilities": ["Nutsbedrijf", "Versorgung", "Energie", "Servizi", "Servicios"], "industrial processing": ["Processing", "Verarbeitung", "Transformation", "Lavorazioni", "Procesos"],
    "material handling": ["Handling", "Foerdertechnik", "Manutention", "Movimentazione", "Manutencion"],
}
CUSTOMER_WORDS = ["Brink", "Maas", "Vennebos", "Kessel", "Roth", "Lindner", "Berger", "Moulin", "Ferrand", "Rinaldi", "Costa", "Serrano", "Kowal", "Nowak", "Svoboda",
                  "Dvorak", "Lund", "Berg", "Virtanen", "Koski", "Silva", "Pereira", "Popescu", "Ionescu", "Nagy", "Kovacs", "Horvat", "Novak", "Papas", "Dimitrov",
                  "Murphy", "Byrne", "Borg", "Camilleri", "Kask", "Tamm", "Ozols", "Kalnins", "Jonaitis", "Petrauskas", "Weber", "Fischer", "Hoffmann", "Wagner",
                  "Peeters", "Janssens", "Dubois", "Lambert", "Bianchi", "Conti", "Garcia", "Navarro", "Wisniewski", "Mazur", "Horak", "Vesely", "Nilsson", "Larsen"]
FIRST = {
    "nl": ["Marit", "Joris", "Inge", "Bram", "Sanne", "Daan", "Lotte", "Ruben", "Femke", "Thijs"], "de": ["Katrin", "Lukas", "Jana", "Matthias", "Sabine", "Jonas", "Heike", "Felix", "Nora", "Tobias"],
    "fr": ["Camille", "Hugo", "Elise", "Julien", "Manon", "Theo", "Claire", "Nicolas", "Lea", "Maxime"], "it": ["Giulia", "Marco", "Elena", "Luca", "Chiara", "Matteo", "Sara", "Paolo", "Elisa", "Davide"],
    "es": ["Lucia", "Javier", "Carmen", "Alvaro", "Marta", "Diego", "Laura", "Pablo", "Irene", "Sergio"], "pt": ["Ines", "Tiago", "Beatriz", "Rui", "Marta", "Andre", "Sofia", "Pedro", "Rita", "Nuno"],
    "pl": ["Agnieszka", "Piotr", "Katarzyna", "Tomasz", "Magdalena", "Marek", "Ewa", "Jakub", "Anna", "Michal"], "cs": ["Jana", "Petr", "Lucie", "Martin", "Eva", "Tomas", "Hana", "Jan", "Veronika", "Pavel"],
    "nord": ["Astrid", "Mikael", "Liv", "Anders", "Sanna", "Henrik", "Eero", "Maja", "Karl", "Ilse"], "ro": ["Ioana", "Andrei", "Elena", "Mihai", "Maria", "Radu", "Ana", "Vlad", "Cristina", "Stefan"],
    "hu": ["Zsofia", "Balazs", "Eszter", "Gabor", "Anna", "Peter", "Reka", "Daniel", "Katalin", "Tamas"], "sl": ["Maja", "Luka", "Nina", "Matej", "Ana", "Jure", "Petra", "Marko", "Eva", "Tadej"],
    "el": ["Eleni", "Nikos", "Maria", "Giorgos", "Katerina", "Dimitris", "Sofia", "Kostas", "Anna", "Yannis"], "bg": ["Elena", "Georgi", "Maria", "Ivan", "Desislava", "Dimitar", "Petya", "Nikolay", "Ivanka", "Stefan"],
    "en": ["Aoife", "Conor", "Niamh", "Sean", "Maeve", "Liam", "Clara", "Joseph", "Roberta", "Daniel"],
}
LAST = {
    "nl": ["Veldman", "Peeters", "Jonker", "Meijer", "de Wit", "Smit", "Bosman", "Hendriks", "Kuiper", "Vos"], "de": ["Brandt", "Keller", "Neumann", "Schaefer", "Vogel", "Lehmann", "Krueger", "Winter", "Albrecht", "Busch"],
    "fr": ["Lefevre", "Moreau", "Girard", "Faure", "Mercier", "Blanc", "Roux", "Fontaine", "Chevalier", "Andre"], "it": ["Ferrari", "Romano", "Greco", "Marino", "Gallo", "Fontana", "Rinaldi", "Villa", "Leone", "Bruno"],
    "es": ["Ortega", "Molina", "Delgado", "Castro", "Ramos", "Vidal", "Prieto", "Cano", "Soler", "Ibanez"], "pt": ["Carvalho", "Teixeira", "Moreira", "Correia", "Nunes", "Pinto", "Mendes", "Rocha", "Ferreira", "Lopes"],
    "pl": ["Kaminski", "Zielinski", "Szymanski", "Wozniak", "Dabrowski", "Kozlowski", "Jankowski", "Krawczyk", "Piotrowski", "Grabowski"], "cs": ["Novotny", "Prochazka", "Kucera", "Blazek", "Cerny", "Marek", "Pospisil", "Kral", "Urban", "Havel"],
    "nord": ["Lindqvist", "Holm", "Eriksen", "Saarinen", "Nyberg", "Aaltonen", "Berglund", "Mikkelsen", "Lindholm", "Salo"], "ro": ["Marin", "Stoica", "Dumitru", "Radu", "Munteanu", "Gheorghe", "Constantin", "Stan", "Matei", "Dragomir"],
    "hu": ["Szabo", "Toth", "Farkas", "Molnar", "Balogh", "Lakatos", "Papp", "Simon", "Fekete", "Meszaros"], "sl": ["Kovac", "Krajnc", "Zupan", "Potocnik", "Kos", "Vidmar", "Golob", "Mlakar", "Turk", "Kralj"],
    "el": ["Georgiou", "Dimitriou", "Nikolaou", "Vasiliou", "Papadakis", "Karras", "Ioannou", "Stavrou", "Antoniou", "Pappas"], "bg": ["Petrov", "Georgiev", "Iliev", "Stoyanov", "Todorov", "Kolev", "Angelov", "Marinov", "Hristov", "Vasilev"],
    "en": ["Doyle", "Walsh", "Kavanagh", "Brennan", "Farrell", "Quinn", "Vella", "Zammit", "Spiteri", "Galea"],
}
STREETS = {
    "nl": ["Industrieweg", "Havenstraat", "Ambachtsweg", "Logistiekpark", "Kanaalweg"], "de": ["Industriestrasse", "Hafenstrasse", "Gewerbering", "Logistikweg", "Am Kanal"],
    "fr": ["Rue de l'Industrie", "Avenue du Port", "Zone d'Activite Nord", "Route du Canal", "Rue des Ateliers"], "it": ["Via dell'Industria", "Via del Porto", "Zona Industriale", "Via dei Canali", "Via delle Officine"],
    "es": ["Calle de la Industria", "Avenida del Puerto", "Poligono Industrial", "Camino del Canal", "Calle de los Talleres"], "pt": ["Rua da Industria", "Avenida do Porto", "Zona Industrial", "Estrada do Canal", "Rua das Oficinas"],
    "pl": ["ul. Przemyslowa", "ul. Portowa", "Strefa Przemyslowa", "ul. Kanalowa", "ul. Warsztatowa"], "cs": ["Prumyslova", "Pristavni", "Logisticka", "Kanalova", "Dilenska"],
    "nord": ["Industrivagen", "Hamnvagen", "Logistikgatan", "Kanalvagen", "Verkstadsgatan"], "ro": ["Strada Industriei", "Strada Portului", "Zona Industriala", "Soseaua Canalului", "Strada Atelierelor"],
    "hu": ["Ipari ut", "Kikoto utca", "Logisztikai park", "Csatorna utca", "Muhely utca"], "sl": ["Industrijska cesta", "Pristaniska ulica", "Logisticna pot", "Kanalska cesta", "Delavniska ulica"],
    "el": ["Odos Viomichanias", "Odos Limaniou", "Viomichaniki Zoni", "Odos Kanaliou", "Odos Ergastirion"], "bg": ["ul. Industrialna", "ul. Pristanishtna", "Logisticheski park", "ul. Kanalna", "ul. Rabotilnitsa"],
    "en": ["Industrial Estate Road", "Harbour Road", "Logistics Park", "Canal Road", "Workshop Lane"],
}
ROLES = {
    "dealer": ["Parts Manager", "Service Manager", "Dealer Principal", "Workshop Manager", "Sales Manager"],
    "supplier": ["Account Manager", "Sales Engineer", "Logistics Coordinator", "Customer Service Lead"],
    "customer": ["Procurement Lead", "Fleet Manager", "Maintenance Manager", "Site Manager", "Purchasing Officer"],
}


def slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def group(cc: str) -> str:
    return LANG_GROUP[cc]


def company(kind: str, cc: str, *key) -> str:
    """A fictional company name. The same inputs always give the same name."""
    g = group(cc)
    brand = pick(BRAND_WORDS, kind, cc, *key, "brand")
    if kind == "dealer":
        return f"{brand} {pick(DEALER_TRADE[g], kind, cc, *key, 't')} (demo)"
    return f"{brand} {LEGAL[cc]} (demo)"


def person(kind: str, cc: str, *key) -> tuple[str, str]:
    g = group(cc)
    return f"{pick(FIRST[g], kind, cc, *key, 'f')} {pick(LAST[g], kind, cc, *key, 'l')} (demo)", pick(ROLES[kind], kind, cc, *key, 'r')


def email(person_name: str, company_name: str) -> str:
    first, last = person_name.replace(" (demo)", "").split(" ", 1)
    return f"{slug(first)}.{slug(last)}@{slug(company_name.replace('(demo)', ''))[:24]}.example"


def phone(cc: str, *key) -> str:
    code = COUNTRIES[cc][1]
    return f"{code} {10 + stable_int(*key, 'area', mod=89)} 555 01{stable_int(*key, 'num', mod=100):02d}"


def postal(cc: str, *key) -> str:
    d = lambda n, tag: f"{stable_int(*key, tag, mod=10 ** n):0{n}d}"
    letters = "ABCDEFGHJKLMNPRSTUVWXZ"
    L = lambda tag: letters[stable_int(*key, tag, mod=len(letters))]
    fmt = {"NL": lambda: f"{1000 + stable_int(*key, 'a', mod=8999)} {L('b')}{L('c')}", "PL": lambda: f"{d(2, 'a')}-{d(3, 'b')}", "CZ": lambda: f"{d(3, 'a')} {d(2, 'b')}",
           "SK": lambda: f"{d(3, 'a')} {d(2, 'b')}", "SE": lambda: f"{d(3, 'a')} {d(2, 'b')}", "GR": lambda: f"{d(3, 'a')} {d(2, 'b')}", "PT": lambda: f"{d(4, 'a')}-{d(3, 'b')}",
           "IE": lambda: f"D{d(2, 'a')} {L('b')}{d(3, 'c')}", "LT": lambda: f"LT-{d(5, 'a')}", "LV": lambda: f"LV-{d(4, 'a')}", "MT": lambda: f"VLT {d(4, 'a')}"}
    if cc in fmt:
        return fmt[cc]()
    width = {"DE": 5, "FR": 5, "IT": 5, "ES": 5, "FI": 5, "HR": 5, "EE": 5, "RO": 6, "BE": 4, "AT": 4, "DK": 4, "HU": 4, "SI": 4, "LU": 4, "CY": 4, "BG": 4}[cc]
    return d(width, "z")


def street(cc: str, *key) -> str:
    return f"{pick(STREETS[group(cc)], 'street', cc, *key)} {10 + stable_int(*key, 'no', mod=190)}"
