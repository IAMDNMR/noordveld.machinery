"""Question orchestration:

question -> intent and entities (rules first, language model only if needed) -> resolve against Neo4j -> one fixed query
-> evidence and provenance -> deterministic answer, optionally reworded by the model and checked against the evidence.
"""
from __future__ import annotations

import logging
import time

from app.graph.repositories.intelligence import IntelligenceRepository
from app.graph.repositories.parts import PartRepository
from app.intelligence import rules
from app.intelligence.grounding import is_grounded
from app.intelligence.handlers import HANDLERS, Context
from app.intelligence.models import Intent, Kind, Outcome, ParsedQuestion, Resolved
from app.intelligence.provenance import data_class, summarise
from app.intelligence.registry import REGISTRY, answerable_intents, spec_for
from app.intelligence.resolver import EntityResolver, Resolution
from app.llm import LLMClient, LLMError
from app.schemas.intelligence import Answer, Candidate, Clarification, EntityRef, QueryRequest, QueryResponse

log = logging.getLogger(__name__)

_KIND_NOUN = {Kind.PART: "part", Kind.MACHINE: "machine", Kind.SUPPLIER: "supplier", Kind.DEALER: "dealer", Kind.ASSEMBLY: "assembly", Kind.CATEGORY: "category"}
UNSUPPORTED_TEXT = "I can currently investigate parts, machines, fitment, suppliers, dealers, assemblies, compliance, inventory and graph relationships."

# An intent chosen from keywords is about "a part" by default; the entity actually found can redirect it.
_BY_ENTITY: dict[tuple[Intent, Kind], Intent] = {
    (Intent.PART_TO_INVENTORY, Kind.DEALER): Intent.DEALER_GRAPH,
    (Intent.PART_TO_LOCATION, Kind.DEALER): Intent.DEALER_GRAPH,
    (Intent.PART_TO_INVENTORY, Kind.SUPPLIER): Intent.SUPPLIER_GRAPH,
    (Intent.PART_TO_LOCATION, Kind.SUPPLIER): Intent.SUPPLIER_GRAPH,
    (Intent.PART_TO_PART, Kind.ASSEMBLY): Intent.ASSEMBLY_TO_PART,
    (Intent.PART_SEARCH, Kind.ASSEMBLY): Intent.ASSEMBLY_TO_PART,
    (Intent.PART_SEARCH, Kind.SUPPLIER): Intent.SUPPLIER_GRAPH,
    (Intent.PART_SEARCH, Kind.DEALER): Intent.DEALER_GRAPH,
    (Intent.PART_SEARCH, Kind.MACHINE): Intent.MACHINE_TO_PART,
    (Intent.PART_TO_MACHINE, Kind.MACHINE): Intent.MACHINE_TO_PART,
    (Intent.PART_TO_ASSEMBLY, Kind.ASSEMBLY): Intent.ASSEMBLY_TO_PART,
    (Intent.PART_TO_SUPPLIER, Kind.SUPPLIER): Intent.SUPPLIER_GRAPH,
    (Intent.PART_TO_DEALER, Kind.DEALER): Intent.DEALER_GRAPH,
    (Intent.PART_GRAPH, Kind.MACHINE): Intent.MACHINE_GRAPH,
    (Intent.PART_GRAPH, Kind.SUPPLIER): Intent.SUPPLIER_GRAPH,
    (Intent.PART_GRAPH, Kind.DEALER): Intent.DEALER_GRAPH,
    (Intent.PART_TO_CATEGORY, Kind.CATEGORY): Intent.PART_SEARCH,
}


def refine(intent: Intent, found: Resolution, text: str = "") -> Intent:
    """Redirect an intent when the entity found is not a part but the matching intent for that entity exists."""
    part = found.one(Kind.PART)
    if spec_for(intent).required is Kind.PART and part is not None and part.tier < 2:
        return intent  # an exactly identified part always wins; a name that merely contains the words does not
    for (source, kind), target in _BY_ENTITY.items():
        if intent is not source:
            continue
        hit = found.one(kind)
        if intent is Intent.PART_SEARCH:
            # a free-text search becomes an entity overview only on an exact name or key, and a machine only when no other words were given
            if hit is not None and hit.tier == 0 and (kind is not Kind.MACHINE or not text):
                return target
            continue
        if hit is not None or found.many(kind):
            return target  # several candidates still redirect, so the user is asked to choose between them
    return intent


class IntelligenceService:
    def __init__(self, repo: IntelligenceRepository, parts: PartRepository, llm: LLMClient | None) -> None:
        self._repo = repo
        self._parts = parts
        self._llm = llm
        self._resolver = EntityResolver(repo)

    # ── understanding ────────────────────────────────────────────────────────────────────────────
    def _understand(self, question: str, req: QueryRequest) -> tuple[ParsedQuestion, Resolution, str]:
        parsed = rules.parse(question)
        found = self._resolver.resolve(parsed.mentions, req.selected)
        by = "selection" if req.selected else "rules"
        if parsed.intent is not None:
            return parsed, found, by
        if self._llm is not None:
            try:
                intents = {i.value: REGISTRY[i].description for i in answerable_intents()}
                llm = self._llm.parse_question(question, intents)
                intent = Intent(llm.intent) if llm.intent in Intent._value2member_map_ else Intent.UNSUPPORTED  # unknown intents are rejected
                mentions = tuple(dict.fromkeys(parsed.mentions + llm.mentions))
                found = self._resolver.resolve(mentions, req.selected)
                return ParsedQuestion(intent if intent is not Intent.UNSUPPORTED else None, mentions, parsed.text, "llm", llm.clarification_question), found, "llm"
            except (LLMError, ValueError) as exc:
                log.info("language model not used: %s", type(exc).__name__)
        # no usable intent: an entity on its own is shown as that entity's overview
        if found.one(Kind.PART):
            return ParsedQuestion(Intent.PART_SEARCH, parsed.mentions, parsed.text), found, by
        if found.one(Kind.MACHINE):
            return ParsedQuestion(Intent.MACHINE_GRAPH, parsed.mentions, parsed.text), found, by
        return parsed, found, by

    # ── query ────────────────────────────────────────────────────────────────────────────────────
    def query(self, req: QueryRequest) -> QueryResponse:
        started = time.perf_counter()
        question = " ".join(req.question.split())
        parsed, found, by = self._understand(question, req)

        if parsed.intent is None or parsed.intent is Intent.UNSUPPORTED:
            return self._unsupported(question, parsed.clarification, started)

        intent = refine(parsed.intent, found, parsed.text)
        spec = spec_for(intent)
        if spec.required is not None:
            blocker = self._missing(spec.required, found, parsed)
            if blocker:
                return self._clarify(question, intent, blocker, found, started, by)

        entities = {r.kind: r for r in found.all_unique()}
        if intent is not Intent.PART_SEARCH:
            entities = {k: v for k, v in entities.items() if k in (spec.required, *spec.optional)}
        text = parsed.text or (parsed.mentions[0] if parsed.mentions and not {Kind.MACHINE, Kind.CATEGORY} & entities.keys() else "")
        ctx = Context(question, text, req.limit, self._repo, self._parts, entities)
        outcome = HANDLERS[intent](ctx)
        answer = self._answer(question, intent, outcome)
        refs = [self._ref(r) for r in entities.values()]
        return QueryResponse(
            question=question, intent=intent.value, intent_label=spec.label, understood_by=by, entities=refs, answer=answer,
            results=outcome.results, total=outcome.total, evidence=outcome.evidence[:60], provenance=summarise(outcome.results, outcome.evidence), graph_path=outcome.path,
            warnings=outcome.warnings, actions=outcome.actions, elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    # ── helpers ──────────────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _ref(r: Resolved) -> EntityRef:
        return EntityRef(kind=r.kind.value, key=r.label, label=r.label, detail=r.detail, match="exact" if r.tier == 0 else "alias" if r.tier == 1 else "partial", data_class=data_class(r.data_status))

    @staticmethod
    def _missing(kind: Kind, found: Resolution, parsed: ParsedQuestion) -> dict | None:
        if found.one(kind) is not None:
            return None
        many = found.many(kind)
        noun = _KIND_NOUN[kind]
        if many:
            return {"question": f"I found more than one {noun} that could match. Which {noun} do you mean?", "candidates": many}
        others = [f"{_KIND_NOUN[r.kind]} {r.label}" for r in found.all_unique()]
        hint = f" I found {', '.join(others)}, but this question needs a {noun}." if others else ""
        return {"question": f"Which {noun} do you mean? I could not find a {noun} matching your question in the graph.{hint}", "candidates": []}

    def _clarify(self, question: str, intent: Intent, blocker: dict, found: Resolution, started: float, by: str) -> QueryResponse:
        candidates = [Candidate(kind=c.kind.value, key=c.label, label=c.label, detail=c.detail) for c in blocker["candidates"]]
        spec = spec_for(intent)
        return QueryResponse(
            question=question, intent=intent.value, intent_label=spec.label, understood_by=by, entities=[self._ref(r) for r in found.all_unique()],
            answer=Answer(summary=blocker["question"], grounded=True, source="template"), results=[], total=0, evidence=[], provenance=[], graph_path=[], warnings=[], actions=[],
            clarification=Clarification(question=blocker["question"], candidates=candidates), elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    def _unsupported(self, question: str, llm_question: str | None, started: float) -> QueryResponse:
        spec = spec_for(Intent.UNSUPPORTED)
        text = llm_question or UNSUPPORTED_TEXT
        return QueryResponse(
            question=question, intent=Intent.UNSUPPORTED.value, intent_label=spec.label, understood_by="rules", entities=[], answer=Answer(summary=text, grounded=True, source="template"),
            results=[], total=0, evidence=[], provenance=[], graph_path=[], warnings=[], actions=[],
            clarification=Clarification(question=text, candidates=[]), elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    def _answer(self, question: str, intent: Intent, outcome: Outcome) -> Answer:
        """The deterministic summary, or the model's rewording of it when that passes the grounding check."""
        if self._llm is None or not (outcome.results or outcome.evidence):
            return Answer(summary=outcome.summary, grounded=True, source="template")
        payload = [e.model_dump() for e in outcome.evidence] or [
            {"title": r.title, "subtitle": r.subtitle, **{f.label: f.value for f in r.facts}} for r in outcome.results[:30]
        ]
        try:
            text = self._llm.generate_grounded_response(question, intent.value, payload, outcome.summary)
        except LLMError as exc:
            log.info("grounded wording skipped: %s", type(exc).__name__)
            return Answer(summary=outcome.summary, grounded=True, source="template")
        if is_grounded(text, payload, outcome.summary, question):
            return Answer(summary=text, grounded=True, source="gemini")
        log.info("model summary rejected by the grounding check")
        return Answer(summary=outcome.summary, grounded=True, source="template")
