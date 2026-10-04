"""TEST DOUBLE ONLY. Simulates what the language model returns, using keywords, so the backend (validation, entity resolution, the
query registry, Neo4j, evidence) can be tested end to end without calling Gemini. The application does not contain this logic:
it never routes a question by keyword. Real model routing is covered by the live tests in test_gemini_first.py.

Original description:

It decides an intent from keywords and pulls out mentions (identifier-like tokens and a residual phrase). It never touches
the database: mentions are resolved against the graph afterwards by the resolver.
"""
from __future__ import annotations

import re

from app.intelligence.identifiers import identifiers
from app.llm.base import LLMParse, LLMUnavailable

from app.intelligence.models import Intent

# Part numbers, machine models, order and legacy numbers look like letters + digits (+ letters), in any case and with or
# without separators: "AB-1234-CD", "ab 1234 cd", "AB1234CD". A trailing word may be swallowed ("AB-1234 use"); the
# resolver drops trailing words until something matches.
_IDENT = re.compile(r"\b[A-Za-z]{1,5}[- ]?\d{2,5}(?:[- ]?[A-Za-z]{1,3}\b)*")
_BARE_NUMBER = re.compile(r"\b\d{3,5}\b")

# first match wins; order matters (more specific first)
_RULES: tuple[tuple[Intent, re.Pattern[str]], ...] = (
    # "what machines are available / do you have / list all machines": the catalogue itself, not the machines of one part
    (Intent.MACHINE_LIST, re.compile(r"^(?!.*\b(fit|fits|use|uses|used|for|supplier|dealer|part|parts|stock)\b).*\b(machines?|models?|loaders?|excavators?|vehicles?|equipment)\b.*\b(ava\w*|offer\w*|have|sell|make|range|exist|list|catalogue)\b|^(list|show( me)?) (all |the )?(machines|models)\b|^all machines\b", re.I)),
    (Intent.ORDER_STATUS, re.compile(r"\border\b|\borders\b|\bORD-?\d|\bshipment|\btracking\b|\bshipped\b", re.I)),
    (Intent.ENTITY_PATH, re.compile(r"how (is|are|does) .+ (connected|related|linked|connect|relate|link)\b.* (to|with)\b|what (links|connects)\b|\bpath (between|from)\b|connection between|relationship between", re.I)),
    (Intent.DATA_QUALITY, re.compile(r"data quality|\bmissing\b|coverage|data gaps?|incomplete|not recorded", re.I)),
    (Intent.PART_PROVENANCE, re.compile(r"provenance|where (does|did) .*(data|come)|data status|data source|synthetic|real or demo|\bverifi|\bstatus\b|orderable|can (i|we) order|source of", re.I)),
    (Intent.PART_TO_COMPLIANCE, re.compile(r"complian|certif|standard\b|regulat|iso\b", re.I)),
    (Intent.PART_TO_SUPPLIER, re.compile(r"supplier|suppl(y|ies|ied)\b|vendor|who makes", re.I)),
    (Intent.PART_TO_DEALER, re.compile(r"dealer|stocked by|distributor|who stocks", re.I)),
    (Intent.PART_TO_LOCATION, re.compile(r"where .*(available|stored|located|find|buy)|location|which (city|country)|warehouse", re.I)),
    (Intent.PART_TO_INVENTORY, re.compile(r"\bstock|inventory|how many\b.*\b(available|left|units|in stock)|\bis\b.*\bavailable\b|\bunits\b|availability", re.I)),
    (Intent.PART_TO_PART, re.compile(r"related|co-?ordered|ordered together|alternative|replace|interchang|equivalent|substitut|similar", re.I)),
    (Intent.PART_TO_CATEGORY, re.compile(r"categor|what (kind|type) of part|part type", re.I)),
    (Intent.PART_TO_ASSEMBLY, re.compile(r"assembl|component|bill of material|\bbom\b|part of|contain|made up|consist", re.I)),
    (Intent.PART_GRAPH, re.compile(r"relationship|graph|connect|network|linked", re.I)),
    (Intent.PART_TO_MACHINE, re.compile(r"\bfit|used (by|on|in)|\buse\b|\buses\b|compatib|work(s)? (with|on)|which machines|what machines|for which machine", re.I)),
)

_PARTS_OF_MACHINE = re.compile(r"\bparts?\b.*\b(for|of|on|in)\b|\bparts?\b|\bcomponents? for\b", re.I)
_SEARCH = re.compile(r"\b(find|search|look( for)?|parts?)\b", re.I)
# "Tell me about X" expects one thing back: several matching parts must be offered as a choice, not listed as a search
_ABOUT = re.compile(r"\b(tell me about|describe|details (of|for|on)|information (on|about)|what is (the|a|an)?\s*\w|show me)\b", re.I)

_STOP = frozenset(
    "a an and any are as at be by can could do does for from give has have how i in is it its me of on or please show tell that the their these this to us "
    "was we what when where which who whom with would you your find search list look need get display about describe details detail information info "
    "part parts machine machines fit fits used uses use compatible related supplier suppliers supply supplies supplied dealer dealers assembly assemblies "
    "category categories provenance relationships relationship graph stock stocks stocked inventory available availability compliance compliant certified "
    "location locations connected connect connects link links linked between path missing verified verification status orderable many much there "
    "contain contains contained made up consist consists whats what's all".split()
)


def _mentions_old(question: str) -> tuple[str, ...]:
    found: list[str] = []
    for m in _IDENT.finditer(question):
        text = m.group(0).strip()
        if text.lower() not in {f.lower() for f in found}:
            found.append(text)
    for m in _BARE_NUMBER.finditer(question):
        if not any(m.group(0) in f for f in found):
            found.append(m.group(0))
    return tuple(found)


def _residue(question: str, mentions: tuple[str, ...]) -> str:
    text = question
    for m in mentions:
        text = text.replace(m, " ")
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]+", text) if w.lower() not in _STOP]
    return " ".join(words[:5])


_PLACE_NOUN = re.compile(r"\b(dealers?|suppliers?|warehouses?|depots?)\b", re.I)
_NEAR = re.compile(r"\b(near|nearest|closest|close to|around|nearby)\b", re.I)
_PLACE = re.compile(r"\b(?:in|near|around|at|close to|closest to|nearest to)\s+([A-Z][A-Za-z\-]+)")
_PATH_KIND = re.compile(r"\b(supplier|dealer|machine|warehouse|assembly|category)s?\b", re.I)


def model_parse(question: str) -> LLMParse:
    """What a model would return for `question`, decided by keywords (test double)."""
    q = " ".join(question.split())
    mentions = identifiers(q)
    residue = _residue(q, mentions)
    all_mentions = mentions + ((residue,) if residue else ())
    single = bool(_ABOUT.search(q))
    filters: dict = {"single": single} if single else {}
    intent = next((i for i, pattern in _RULES if pattern.search(q)), None)
    if intent is None and not single and (_PARTS_OF_MACHINE.search(q) or _SEARCH.search(q)):
        intent = Intent.PART_SEARCH
    if intent is None and single:
        intent = Intent.PART_SEARCH  # "tell me about X": one thing is wanted
    if intent is Intent.PART_TO_MACHINE and re.search(r"(which|what|list|show)( me)?( the| all)? parts?|parts? (fit|does|do|for|of|are|associated)", q, re.I):
        intent = Intent.MACHINE_TO_PART  # a model reads "which parts fit X" as parts of a machine
    # what a model infers from the kind of thing named (the application resolves the entity itself)
    if re.search(r"which parts does .* (supply|supplies)", q, re.I):
        intent = Intent.SUPPLIER_GRAPH
    elif re.search(r"(what|which parts) does .* stock", q, re.I):
        intent = Intent.DEALER_GRAPH
    elif re.search(r"parts are in (?!stock)|parts (make up|are in) the", q, re.I):
        intent = Intent.ASSEMBLY_TO_PART
    elif intent in (Intent.PART_GRAPH, Intent.PART_SEARCH) and re.search(r"(relationships|graph|connected).*(NV|KFT|BTS)-\d{3,4}", q):
        intent = Intent.MACHINE_GRAPH
    noun = _PLACE_NOUN.search(q)
    if noun and not mentions and intent not in (Intent.ORDER_STATUS, Intent.ENTITY_PATH):
        word = noun.group(1).lower()
        filters["place_kind"] = "SUPPLIER" if word.startswith("supplier") else "WAREHOUSE" if word.startswith(("warehouse", "depot")) else "DEALER"
        filters["proximity"] = "near" if _NEAR.search(q) else "in"
        place = _PLACE.search(q)
        if place:
            filters["place"] = place.group(1)
        intent = Intent.GEO_LOCATION
    if intent is Intent.ENTITY_PATH:
        kinds = [m.group(1).lower() for m in _PATH_KIND.finditer(q)]
        if kinds:
            filters["target_kind"] = kinds[0]
    entities = {"part": residue} if residue and intent is Intent.PART_SEARCH else {}
    return LLMParse(intent.value if intent else "UNSUPPORTED", all_mentions, filters=filters, entities=entities, in_scope=intent is not None)


class KeywordModel:
    """Stands in for Gemini in backend tests. Wording is left to the deterministic template."""

    name = "keyword-test-double"

    def __init__(self) -> None:
        self.calls = 0

    def parse_question(self, question: str, intents: dict[str, str]) -> LLMParse:
        self.calls += 1
        return model_parse(question)

    def resolve_entities(self, question: str, intents: dict[str, str]) -> tuple[str, ...]:
        return model_parse(question).mentions

    def generate_grounded_response(self, question, intent, evidence, draft):
        raise LLMUnavailable("test double does not word answers")
