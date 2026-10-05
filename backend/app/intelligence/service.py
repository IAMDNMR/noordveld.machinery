"""Question orchestration, language model first:

question -> the language model (intent + typed entities, structured output) -> validation against the intent registry -> entity resolution
against Neo4j -> one approved, parameterised query -> evidence and provenance -> deterministic answer, optionally reworded by
the model from that evidence and checked against it.

The model understands and explains; the backend decides what may run; Neo4j supplies every fact. There is no keyword routing: if the
model cannot be used the request fails with a clear error (LLMUnavailable / LLMInvalidResponse) rather than silently running a
different router. Exact identifiers (part numbers, model codes) are still read deterministically, as entity assistance only.
"""
from __future__ import annotations

import logging
import re
import time

from app.graph.repositories.intelligence import IntelligenceRepository
from app.graph.repositories.parts import PartRepository
from app.intelligence.casual import content_text
from app.intelligence.contract import enforce_result_kinds
from app.intelligence.grounding import contradicts, demo_names, drop_false_demo_qualifier, grounding_records, is_grounded, keep_demo_qualifier
from app.intelligence.handlers import HANDLERS, Context, humanize
from app.intelligence.identifiers import identifiers
from app.intelligence.models import Intent, Kind, Outcome, ParsedQuestion, Resolved
from app.intelligence.provenance import data_class, summarise
from app.intelligence.registry import HINTS, REGISTRY, answerable_intents, spec_for
from app.intelligence.resolver import EntityResolver, Resolution
from app.llm import LLMClient, LLMError, LLMInvalidResponse, LLMParse, LLMUnavailable
from app.schemas.intelligence import Answer, Candidate, Clarification, EntityRef, Fact, QueryRequest, QueryResponse, Stage, Subject
from app.services.part_status import status_label

log = logging.getLogger(__name__)

_KIND_NOUN = {Kind.PART: "part", Kind.MACHINE: "machine", Kind.SUPPLIER: "supplier", Kind.DEALER: "dealer", Kind.ASSEMBLY: "assembly", Kind.CATEGORY: "category", Kind.ORDER: "order", Kind.WAREHOUSE: "warehouse"}
_PATH_LABELS = {"supplier": "Supplier", "dealer": "Dealer", "machine": "Machine", "warehouse": "Warehouse", "assembly": "Assembly", "category": "Category"}
UNSUPPORTED_TEXT = "I can currently investigate parts, machines, fitment, suppliers, dealers, assemblies, compliance, inventory and graph relationships."
OUT_OF_SCOPE_TEXT = ("I can help with Noordveld Parts Intelligence questions about parts, machines, fitment, suppliers, assemblies, availability, compliance, "
                     "relationships and provenance. Please ask a question related to those areas.")
NOT_FOUND_CODES = {Kind.PART: "PART_NOT_FOUND", Kind.MACHINE: "MACHINE_NOT_FOUND", Kind.SUPPLIER: "SUPPLIER_NOT_FOUND", Kind.DEALER: "DEALER_NOT_FOUND",
                   Kind.ASSEMBLY: "ASSEMBLY_NOT_FOUND", Kind.CATEGORY: "CATEGORY_NOT_FOUND", Kind.ORDER: "ORDER_NOT_FOUND", Kind.WAREHOUSE: "WAREHOUSE_NOT_FOUND"}


class IntelligenceService:
    def __init__(self, repo: IntelligenceRepository, parts: PartRepository, llm: LLMClient | None) -> None:
        self._repo = repo
        self._parts = parts
        self._llm = llm
        self._resolver = EntityResolver(repo)

    # ── understanding (language model) ───────────────────────────────────────────────────────────────────
    def _interpret(self, question: str) -> LLMParse:
        """The model's structured reading of the question. Raises LLMUnavailable / LLMInvalidResponse: there is no other router to fall back to."""
        if self._llm is None:
            raise LLMUnavailable("the language model is not configured")
        key = " ".join(question.lower().split())
        cache: dict[str, LLMParse] = self._llm.__dict__.setdefault("_parse_cache", {})  # the same question is understood once; the free tier allows few requests a minute
        if key in cache:
            return cache[key]
        intents = {i.value: HINTS[i] for i in answerable_intents()}
        parse = self._llm.parse_question(question, intents)
        if not isinstance(parse, LLMParse):
            raise LLMError("the language model returned an unusable structure")
        if len(cache) >= 256:
            cache.pop(next(iter(cache)))
        cache[key] = parse
        return parse

    def _plain_request(self, question: str) -> LLMParse | None:
        """Only when the model returned no usable structure at all for a short request: read it as a search for the part it names, rather than fail.
        The model's own reading is never overridden (it decides intent and constraints); a question with an identifier is left to the model."""
        text = content_text(question)
        if not text or identifiers(question):
            return None
        return LLMParse(Intent.PART_SEARCH.value, (text,), need=text, entities={"part": text})

    def _annotate_machines(self, blocker: dict, found: Resolution, text: str) -> None:
        """Machine choices say how many parts of the asked kind each has, and list the ones that have some first."""
        cands: list[Resolved] = blocker.get("candidates") or []
        if not cands or cands[0].kind is not Kind.MACHINE:
            return
        category = found.one(Kind.CATEGORY)
        if category is None and not text:
            return
        what = category.label if category else text
        counted = []
        for c in cands:
            if category:
                n = self._repo.machine_parts(c.id, category.label, 1)[0]
            else:
                n = self._parts.search(text=text, category=None, machine=c.label, availability=None, orderable=None, sort="relevance", offset=0, limit=1)[0]
            note = f"{n} {what} {'part' if n == 1 else 'parts'}" if n else f"no {what} part"
            counted.append((n, Resolved(c.kind, c.id, c.label, " · ".join(x for x in (c.detail, note) if x), c.data_status, c.tier)))
        blocker["candidates"] = [r for _, r in sorted(counted, key=lambda x: -x[0])]

    def _understand(self, question: str, req: QueryRequest, llm: LLMParse) -> tuple[ParsedQuestion, Resolution, str]:
        # only an intent in the approved registry can ever run; anything else is rejected without a query
        intent = Intent(llm.intent) if llm.intent in Intent._value2member_map_ else Intent.UNSUPPORTED
        typed = tuple(v for v in llm.entities.values() if v.strip()) or llm.mentions
        # The model extracts the need (what kind of part) and the machine independently. The backend then picks the approved query from those validated
        # constraints: a need with or without a machine is a part search (a machine is only a filter on it), a machine alone lists its parts.
        machine_named = llm.entities.get("machine", "").strip()
        need = (llm.need or "").strip()
        if not need and machine_named and llm.entities.get("part") and not identifiers(llm.entities["part"]):
            need = llm.entities["part"].strip()  # an older reading that put the need in `part`
        if need and llm.in_scope and intent in (Intent.MACHINE_TO_PART, Intent.MACHINE_GRAPH, Intent.UNSUPPORTED):
            intent = Intent.PART_SEARCH
        mentions = tuple(dict.fromkeys(m for m in (*typed, need, *identifiers(question)) if m and m.strip()))  # exact identifiers assist; they never choose the intent
        if intent is Intent.PART_SEARCH and not mentions:
            mentions = tuple(x for x in (content_text(question),) if x)  # the model named nothing: search for what was said, not the whole catalogue
        found = self._resolver.resolve(mentions, req.selected)
        if intent is Intent.PART_SEARCH and not machine_named:  # a word that only occurs in a machine's description ("belt" in "Belt Conveyor Module") is not a machine the user named
            machines = found.by_kind.get(Kind.MACHINE, [])
            if machines and all(r.tier >= 2 and _squash(r.label) not in _squash(question) for r in machines):
                found.by_kind.pop(Kind.MACHINE)
        _narrow_by_question(found, question)
        # a need that names a category ("hydraulic", even misspelled) IS that category: it filters, it is not a text to search for
        need_is_category = bool(need) and self._resolver.resolve((need,)).one(Kind.CATEGORY) is not None
        text = ("" if need_is_category else need) if need else llm.entities.get("part", "")
        parsed = ParsedQuestion(None if intent is Intent.UNSUPPORTED else intent, mentions, text, "llm", llm.clarification_question, bool(llm.filters.get("single")),
                                llm.requires_clarification and not need, dict(llm.filters), need=need, machine_named=machine_named)
        return parsed, found, "selection" if req.selected else "llm"

    # ── query ────────────────────────────────────────────────────────────────────────────────────
    def query(self, req: QueryRequest) -> QueryResponse:
        started = time.perf_counter()
        question = " ".join(req.question.split())
        t0 = time.perf_counter()
        try:
            llm = self._interpret(question)
        except LLMInvalidResponse:  # no usable structure came back for a short request: read it plainly rather than fail
            llm = self._plain_request(question)
            if llm is None:
                raise
        stages = [Stage(name="understanding", ms=_ms(t0))]

        # scope guardrail: decided by the model, enforced here, before any graph access
        registered = llm.intent in Intent._value2member_map_ and llm.intent != Intent.UNSUPPORTED.value
        if not llm.in_scope:
            return self._unsupported(question, OUT_OF_SCOPE_TEXT, started, stages, scope="OUT_OF_SCOPE")
        if not registered and not llm.requires_clarification:
            return self._unsupported(question, None, started, stages)  # in the domain, but not something the approved intents can answer

        t0 = time.perf_counter()
        parsed, found, by = self._understand(question, req, llm)
        extra: dict = {}
        if parsed.needs_clarification and parsed.clarification and (parsed.intent is None or not found.all_unique()):
            many = [r for kind in found.by_kind for r in found.many(kind)]
            blocker = {"question": parsed.clarification, "candidates": many, "code": "AMBIGUOUS" if many else None}
            return self._clarify(question, parsed.intent or Intent.UNSUPPORTED, blocker, found, started, by, stages)
        if parsed.intent is None:
            return self._unsupported(question, parsed.clarification, started, stages)
        intent = parsed.intent
        spec = spec_for(intent)

        if intent is Intent.GEO_LOCATION:
            geo = self._place(parsed.filters)
            if isinstance(geo, dict):
                return self._clarify(question, intent, geo, found, started, by, stages)
            extra["geo"] = geo
        elif intent is Intent.MACHINE_LIST:
            extra["place"] = (parsed.filters.get("location") or parsed.filters.get("place") or "").strip().lower() or None
            extra["brand"] = str(parsed.filters.get("brand") or "").strip().lower() or None
        elif intent is Intent.ENTITY_PATH:
            ends = self._path_ends(found, parsed.filters)
            if isinstance(ends, dict):
                return self._clarify(question, intent, ends, found, started, by, stages)
            extra["path"] = ends
        elif intent is Intent.PART_SEARCH and parsed.machine_named and found.one(Kind.MACHINE) is None:
            # the question names a machine: the search is for parts that fit THAT machine. It must resolve to exactly one, or nothing is searched (never dropped, never guessed).
            many = found.many(Kind.MACHINE)
            if many:
                blocker = {"question": f"“{parsed.machine_named}” matches more than one machine. Which machine do you mean?", "candidates": many, "code": "AMBIGUOUS"}
                self._annotate_machines(blocker, found, parsed.need)
            else:
                blocker = {"question": f"I could not identify a machine called “{parsed.machine_named}” in the Noordveld catalogue, so I have not searched. Which machine do you mean?",
                           "candidates": [], "code": NOT_FOUND_CODES[Kind.MACHINE]}
            return self._clarify(question, intent, blocker, found, started, by, stages)
        elif intent is Intent.PART_SEARCH and parsed.single and found.one(Kind.PART) is None and found.many(Kind.PART):
            blocker = {"question": "Several parts match. Which part do you mean?", "candidates": found.many(Kind.PART), "code": "AMBIGUOUS"}
            return self._clarify(question, intent, blocker, found, started, by, stages)
        elif intent is Intent.PART_TO_PART and len(found.many(Kind.PART)) == 2 and all(r.tier == 0 for r in found.many(Kind.PART)):
            first, second = found.many(Kind.PART)  # two exactly named parts: compare them, do not ask which one
            found.by_kind[Kind.PART] = [first]
            extra["other_part"] = second
        elif spec.required is not None:
            blocker = self._missing(spec.required, found, parsed)
            if blocker:
                self._annotate_machines(blocker, found, parsed.text)
                return self._clarify(question, intent, blocker, found, started, by, stages)
        stages.insert(1, Stage(name="entities", ms=_ms(t0)))

        entities = {r.kind: r for r in found.all_unique()}
        # only the kinds the approved query takes are "understood": a word that merely occurs in a supplier's or assembly's name is not a constraint
        entities = {k: v for k, v in entities.items() if k in ((Kind.PART, *spec.optional) if intent is Intent.PART_SEARCH else (spec.required, *spec.optional))}
        part = entities.get(Kind.PART)
        if intent is Intent.PART_SEARCH and part is not None and (part.tier < 2 or parsed.single):
            text = part.label  # a named part is the answer; the other words of the question are not a search
        else:
            text = parsed.text if parsed.need else (parsed.text or (parsed.mentions[0] if parsed.mentions and not {Kind.MACHINE, Kind.CATEGORY} & entities.keys() else ""))
        ctx = Context(question, text, req.limit, self._repo, self._parts, entities, extra)
        t1 = time.perf_counter()
        outcome = HANDLERS[intent](ctx)
        enforce_result_kinds(intent, outcome)  # only the requested entity type is a result; the rest is supporting evidence
        subject = self._subject(intent, spec.required, entities, extra)
        if subject is not None:
            outcome.summary = _name_in_summary(outcome.summary, subject)
        stages.append(Stage(name="graph", ms=_ms(t1)))
        t2 = time.perf_counter()
        answer = self._answer(question, intent, outcome, subject)
        stages.append(Stage(name="answer", ms=_ms(t2)))
        refs = [self._ref(r) for r in entities.values()]
        return QueryResponse(
            question=question, intent=intent.value, intent_label=spec.label, understood_by=by, entities=refs, subject=subject, answer=answer,
            results=outcome.results, total=outcome.total, evidence=outcome.evidence[:60], provenance=summarise(outcome.results, outcome.evidence), graph_path=outcome.path,
            warnings=outcome.warnings, actions=outcome.actions, stages=stages, elapsed_ms=_ms(started),
        )

    # ── helpers ──────────────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _ref(r: Resolved) -> EntityRef:
        return EntityRef(kind=r.kind.value, key=r.label, label=r.label, detail=r.detail, match="exact" if r.tier == 0 else "alias" if r.tier == 1 else "partial", data_class=data_class(r.data_status))

    def _subject(self, intent: Intent, required: Kind | None, entities: dict[Kind, Resolved], extra: dict) -> Subject | None:
        """The entity the answer is anchored on: the intent's required entity, else its one optional entity (a machine for shared parts, a part
        for missing information), else a path's first end. None when the results are themselves the entities (search, a machine overview)."""
        if intent in _NO_SUBJECT:
            return None
        anchor = extra["path"][0] if intent is Intent.ENTITY_PATH else entities.get(required) if required else None
        if anchor is None and required is None:
            anchor = next(iter(entities.values()), None)
        if anchor is None or anchor.kind is Kind.CATEGORY:
            return None
        row = self._repo.subject(anchor.kind.value, anchor.id)
        if not row:
            return None
        facts = [Fact(label=label, value=value) for label, value in _subject_facts(anchor.kind, row) if value]
        name = row.get("name") if row.get("name") != row["label"] else None
        return Subject(kind=anchor.kind.value, key=anchor.id, label=row["label"], name=name, facts=facts, data_class=data_class(row.get("data_status")))

    @staticmethod
    def _missing(kind: Kind, found: Resolution, parsed: ParsedQuestion) -> dict | None:
        if found.one(kind) is not None:
            return None
        many = found.many(kind)
        noun = _KIND_NOUN[kind]
        if many:
            return {"question": f"I found more than one {noun} that could match. Which {noun} do you mean?", "candidates": many, "code": "AMBIGUOUS"}
        if kind is Kind.ORDER:
            return {"question": "Which order do you mean? Give the order number exactly as it appears on the order.", "candidates": [], "code": NOT_FOUND_CODES[kind] if parsed.mentions else None}
        others = [f"{_KIND_NOUN[r.kind]} {r.label}" for r in found.all_unique()]
        hint = f" I found {', '.join(others)}, but this question needs a {noun}." if others else ""
        return {"question": f"Which {noun} do you mean? I could not find a {noun} matching your question in the graph.{hint}", "candidates": [], "code": NOT_FOUND_CODES[kind] if parsed.mentions and not others else None}

    def _place(self, filters: dict):
        """(kind, city, country code, mode, place name) for a question about dealers / suppliers / warehouses in or near a place the model named."""
        kind = filters.get("place_kind") if filters.get("place_kind") in ("DEALER", "SUPPLIER", "WAREHOUSE") else "DEALER"
        mode = "near" if filters.get("proximity") == "near" else "in"
        wanted = " ".join(str(filters.get("place") or "").lower().replace(",", " ").split())
        if not wanted:
            return {"question": "Which city or country? Location is never assumed. Name a city or country to see the dealers, suppliers or warehouses recorded there.", "candidates": [], "code": None}
        places = self._repo.places()
        words = f" {wanted} "
        for c in places["countries"]:
            if c["name"] and f" {c['name'].lower()} " in words or c["cc"] and wanted == c["cc"].lower():
                return kind, None, c["cc"], mode, c["name"]
        for c in places["cities"]:
            if c["city"] and f" {c['city'].lower()} " in words:
                return kind, c["city"], c["cc"], mode, c["city"]
        return {"question": f"I could not find {filters.get('place')} among the cities or countries recorded for dealers, suppliers or warehouses. Name another city or country.", "candidates": [], "code": "PLACE_NOT_FOUND"}

    @staticmethod
    def _path_ends(found: Resolution, filters: dict):
        """The two ends of a connection question: two entities, or an entity and a kind the model named ("... and a supplier"); else a clarification."""
        unique = sorted(found.all_unique(), key=lambda r: r.kind is not Kind.PART)
        two_parts = found.many(Kind.PART) if len(found.many(Kind.PART)) == 2 else []
        ends = unique + [p for p in two_parts if p not in unique]
        if len(ends) >= 2:
            return ends[0], ends[1]
        label = _PATH_LABELS.get(str(filters.get("target_kind") or "").lower().rstrip("s"))
        if len(ends) == 1 and label and label != ends[0].kind.title():
            return ends[0], label
        return {"question": "Connected to what? Name two things, for example a part and a machine, supplier, dealer or assembly.", "candidates": [], "code": None}

    def _clarify(self, question: str, intent: Intent, blocker: dict, found: Resolution, started: float, by: str, stages: list[Stage]) -> QueryResponse:
        candidates = [Candidate(kind=c.kind.value, key=c.label, label=c.label, detail=c.detail) for c in blocker["candidates"]]
        spec = spec_for(intent)
        return QueryResponse(
            question=question, intent=intent.value, intent_label=spec.label, understood_by=by, entities=[self._ref(r) for r in found.all_unique()],
            answer=Answer(summary=blocker["question"], grounded=True, source="template"), results=[], total=0, evidence=[], provenance=[], graph_path=[], warnings=[], actions=[],
            clarification=Clarification(question=blocker["question"], candidates=candidates, code=blocker.get("code")), scope="NEEDS_CLARIFICATION", stages=stages,
            elapsed_ms=_ms(started),
        )

    def _unsupported(self, question: str, llm_question: str | None, started: float, stages: list[Stage], scope: str = "IN_SCOPE") -> QueryResponse:
        spec = spec_for(Intent.UNSUPPORTED)
        text = llm_question or UNSUPPORTED_TEXT
        return QueryResponse(
            question=question, intent=Intent.UNSUPPORTED.value, intent_label=spec.label, understood_by="llm", entities=[], answer=Answer(summary=text, grounded=True, source="template"),
            results=[], total=0, evidence=[], provenance=[], graph_path=[], warnings=[], actions=[],
            clarification=Clarification(question=text, candidates=[]), scope=scope, stages=stages, elapsed_ms=_ms(started),  # type: ignore[arg-type]
        )

    def _answer(self, question: str, intent: Intent, outcome: Outcome, subject: Subject | None = None) -> Answer:
        """The deterministic summary, or the model's rewording of it from the verified evidence when that passes the grounding and demo-qualifier checks."""
        demo = any(i.data_class == "SYNTHETIC_DEMO" for i in outcome.results) or any(e.data_class == "SYNTHETIC_DEMO" for e in outcome.evidence)
        template = Answer(summary=outcome.summary, grounded=True, source="template", demo=demo)
        if self._llm is None or not (outcome.results or outcome.evidence):
            return template
        payload = grounding_records(outcome, subject)  # the structured evidence object: every fact the answer can use, none truncated away
        try:
            text = self._llm.generate_grounded_response(question, intent.value, payload, outcome.summary)
        except LLMError as exc:
            log.info("grounded wording skipped: %s", type(exc).__name__)
            return template
        names = demo_names([*(i.title for i in outcome.results), *(i.subtitle or "" for i in outcome.results), *(e.entity for e in outcome.evidence), *(e.target for e in outcome.evidence)])
        text = keep_demo_qualifier(text, names)
        others = {e.entity for e in outcome.evidence if e.data_class != "SYNTHETIC_DEMO"} | {i.title for i in outcome.results if i.data_class != "SYNTHETIC_DEMO"}
        text = drop_false_demo_qualifier(text, names, others)  # never label source-derived data as demo either
        denied = contradicts(text, outcome)
        if denied:  # the wording denies a value the graph holds: never shown, the evidence-backed answer is used
            log.info("model summary rejected: it contradicts the evidence (%s)", denied)
            return template
        if names and "(demo)" in outcome.summary and "(demo)" not in text:
            log.info("model summary rejected: it dropped the demo qualifier")
            return template
        if is_grounded(text, payload, outcome.summary, question):
            return Answer(summary=text, grounded=True, source="llm", demo=demo)
        log.info("model summary rejected by the grounding check")
        return template


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"\(demo\)", "", text.lower()))


def _narrow_by_question(found: Resolution, question: str) -> None:
    """Several candidates of one kind, but the question spells out exactly one of their full names ("... the Cooling module, KFT series"):
    that one is meant. Never a guess: the whole name must appear in the question, and only a single candidate may qualify."""
    asked = _squash(question)
    for kind, candidates in found.by_kind.items():
        if len(candidates) > 1:
            named = [c for c in candidates if len(_squash(c.label)) >= 6 and _squash(c.label) in asked]
            if len(named) == 1:
                found.by_kind[kind] = named


_NO_SUBJECT = {Intent.PART_SEARCH, Intent.MACHINE_GRAPH, Intent.MACHINE_LIST, Intent.LOW_STOCK_PARTS, Intent.GEO_LOCATION}


def _subject_facts(kind: Kind, row: dict) -> list[tuple[str, str | None]]:
    if kind is Kind.PART:
        category = " · ".join(x for x in (row.get("category"), row.get("subcategory")) if x) or None
        return [("Category", category), ("Catalogue status", status_label(row.get("part_status")) if row.get("part_status") else None), ("Source", row.get("source"))]
    if kind is Kind.MACHINE:
        return [("Machine type", row.get("machine_type")), ("Family", row.get("family"))]
    if kind in (Kind.SUPPLIER, Kind.DEALER):
        return [("Location (stated)", ", ".join(x for x in (row.get("city"), row.get("country")) if x) or None)]
    if kind is Kind.ASSEMBLY:
        return [("BOM status", humanize(row.get("bom_status"))), ("Identified by part", row.get("identified_by"))]
    if kind is Kind.ORDER:
        return [("Order status", humanize(row.get("order_status")))]
    if kind is Kind.WAREHOUSE:
        return [("Location (stated)", ", ".join(x for x in (row.get("city"), row.get("country")) if x) or None), ("Type", humanize(row.get("warehouse_type"))),
                ("Operating status", humanize(row.get("operating_status")))]
    return []


def _name_in_summary(summary: str, subject: Subject) -> str:
    """Name the entity where the summary first mentions it: "AB-1000 (Bucket, general purpose) ...", "ZZ-1 Wheel Loader ..."."""
    if not subject.name or subject.name.lower() in summary.lower() or subject.label not in summary:
        return summary
    named = subject.name if subject.name.startswith(subject.label) else f"{subject.label} ({subject.name})"
    return summary.replace(subject.label, named, 1)


def _ms(since: float) -> int:
    return int((time.perf_counter() - since) * 1000)
