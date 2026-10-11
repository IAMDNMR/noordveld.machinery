"""The Commerce Agent: one message in, one evidence-grounded answer out, across discovery, logistics and warranty.

  message (+ the state the previous answer returned)
    -> understanding   which journeys, which references                (deterministic cues first; the language model only routes an unclear message)
    -> resolution      which machine / shipment / claim the references mean   (each step recorded; nothing is guessed, an ambiguity is a question)
    -> the commerce contexts   CommerceContextEngine.build_*_context   (the engine decides; this module decides nothing about fitment, stock, shipments or warranty)
    -> answer          composed from the contexts' own decision, facts and evidence (app/commerce/answer.py)

The agent adds no domain rule. It never reads a database, never builds a record, and never weakens a context's visibility: every context is already scoped to the principal by the engine,
and an AccessDenied from any journey is the answer to the whole request (HTTP 403 at the API). The language model may route an unclear message and may reword the lead sentence of an answer
(validated against the evidence); it can change neither the facts nor the references.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.commerce import answer as ans
from app.commerce import contract as c
from app.commerce.access import CommerceRole, Principal
from app.commerce.engine import CommerceContextEngine
from app.commerce.intent import DISCOVERY, LOGISTICS, WARRANTY
from app.commerce.intent import score as base_score
from app.llm.base import LLMError

log = logging.getLogger(__name__)

MULTI_DOMAIN, CLARIFICATION, UNKNOWN = "MULTI_DOMAIN", "CLARIFICATION", "UNKNOWN"
AGENT_INTENTS = (DISCOVERY, LOGISTICS, WARRANTY, MULTI_DOMAIN, CLARIFICATION, UNKNOWN)
ORDER = (DISCOVERY, WARRANTY, LOGISTICS)  # the order the journeys run in: what is needed comes first, how fast it arrives last
MIN_SCORE = 2

# Cues the three single-journey selector does not carry: speed and delay (logistics), the traceability questions (warranty), availability and "why" (discovery).
EXTRA_CUES: dict[str, tuple[tuple[str, int], ...]] = {
    DISCOVERY: ((r"\bdo you have\b", 2), (r"\b(why|how come)\b.{0,40}\b(recommend\w*|suggest\w*|this part|that part)\b", 3), (r"\bis (it|this|that) (available|in stock)\b", 2)),
    LOGISTICS: ((r"\bhow (quickly|fast|soon)\b", 2), (r"\burgent\w*|\bas soon as\b|\basap\b", 2), (r"\b(faster|quicker|speed (it )?up|expedite)\b", 2),
                (r"\btaking so long\b|\bdelay\w*|\bwhy is it (late|slow)\b", 2), (r"\bwhat (parts|items|products)\b.{0,30}\b(in|on|inside)\b|\bparts? (are )?in (this|the|my|that)\b", 3),
                (r"\b(what is|what's|whats) the status\b", 2)),
    WARRANTY: ((r"\bunder warranty\b", 2), (r"\b(installed|fitted) (correctly|properly)\b|\bwho (installed|fitted)\b|\breplaced before\b|\bbeen replaced\b", 3),
               (r"\b(not )?eligible\b|\beligibility\b", 2), (r"\bwhy is (this|the|my) claim\b", 3)),
}
FOLLOW_UP = re.compile(r"\b(this|that|it|its|they|them|these|those|status|why|faster|there)\b|\bthe (part|shipment|order|claim|machine|pump)\b", re.IGNORECASE)

PATTERNS = {
    "shipment_id": re.compile(r"\bSHP-(?:NET-)?\d{4}\b", re.IGNORECASE),
    "order_id": re.compile(r"\bORD-(?:NET-)?\d{4}\b", re.IGNORECASE),
    "claim_id": re.compile(r"\bCLM-[A-Z0-9]+(?:-\d+)?\b", re.IGNORECASE),
    "machine_instance_id": re.compile(r"\bMI-[A-Z]?\d{3,4}\b", re.IGNORECASE),
    "part_id": re.compile(r"\bPRT-\d{3}\b", re.IGNORECASE),
}
PART_NUMBER = re.compile(r"\bNVM-\d{4}-[A-Z]{2}\b", re.IGNORECASE)
REF_KEYS = ("shipment_id", "order_id", "claim_id", "machine_instance_id", "part_id", "machine_id")
STATE_KEYS = (*REF_KEYS, "machine_model", "part_number", "last_request", "last_domains")


# ── request / response ───────────────────────────────────────────────────────────────────────────
@dataclass
class AgentRequest:
    message: str
    principal: Principal
    state: dict[str, Any] = field(default_factory=dict)  # what the previous answer returned, plus anything the user selected in the interface
    destination_country: str | None = None


@dataclass
class Understanding:
    intent: str
    domains: list[str]
    references: dict[str, str]
    source: str  # RULES | STATE | LLM | NONE
    scores: dict[str, int]
    focus: list[str]
    reasons: list[str]


@dataclass
class Step:
    domain: str
    status: str
    decision: str
    summary: str
    resolution: list[str] = field(default_factory=list)
    context: dict[str, Any] | None = None
    clarification: dict[str, Any] | None = None


def extract_references(message: str, discovery: Any = None) -> dict[str, str]:
    """Identifiers written in the message, upper-cased. A part number is turned into its part id through the catalogue (never by guessing)."""
    refs = {k: m.group(0).upper() for k, p in PATTERNS.items() if (m := p.search(message or ""))}
    if "part_id" not in refs and discovery is not None and (m := PART_NUMBER.search(message or "")):
        number = m.group(0).upper()
        hit = next((p for p in discovery.parts() if p["part_number"].upper() == number), None)
        if hit:
            refs["part_id"] = hit["part_id"]
    return refs


def focus_of(message: str) -> list[str]:
    low = (message or "").lower()
    out = []
    for name, pattern in (("explain", r"\bwhy\b.{0,40}\b(recommend\w*|suggest\w*|this part|that part)\b"), ("availability", r"\b(available|in stock|do you have)\b"),
                          ("parts_in_shipment", r"\bwhat (parts|items|products)\b|\bparts? (are )?in\b"), ("faster", r"\b(faster|quicker|speed (it )?up|expedite|how (quickly|fast|soon))\b"),
                          ("why_slow", r"\btaking so long\b|\bdelay\w*|\bwhy is it (late|slow)\b"), ("status", r"\bstatus\b|\bwhere (is|are)\b"),
                          ("who_installed", r"\bwho (installed|fitted)\b"), ("installed_correctly", r"\b(installed|fitted) (correctly|properly)\b"),
                          ("replaced_before", r"\breplaced before\b|\bbeen replaced\b|\breplacement history\b"), ("why_not_eligible", r"\bwhy\b.{0,30}\b(not eligible|rejected|not covered)\b|\bwhy is (this|the|my) claim\b")):
        if re.search(pattern, low):
            out.append(name)
    return out


SPEED_WORDS = re.compile(r"\b(urgent(ly)?|asap|as soon as possible|immediately|quickly|quick|fast|soon)\b", re.IGNORECASE)


def clause_scores(clause: str) -> dict[str, int]:
    scores = {d: base_score(clause).get(d, 0) for d in ORDER}
    for domain, cues in EXTRA_CUES.items():
        scores[domain] += sum(w for pattern, w in cues if re.search(pattern, clause.lower()))
    return scores


def discovery_text(message: str) -> str:
    """The part of a multi-journey message that is the part search. The clauses about warranty or delivery are not search terms (they would only add unmatched words), so they are
    left out and urgency words are dropped; the other journeys still receive the whole message. A message with one journey is passed on unchanged."""
    clauses = [x.strip() for x in re.split(r"(?<=[.?!;])\s+|\s+(?:and|but|also)\s+(?=(?:tell|is|are|how|when|where|what|can|will)\b)", message or "") if x.strip()]
    kept = []
    for clause in clauses:
        s = clause_scores(clause)
        if s[DISCOVERY] > 0 and s[DISCOVERY] >= max(s[LOGISTICS], s[WARRANTY]):
            kept.append(re.sub(r"\s+([.?!,;])", r"\1", re.sub(r"\s{2,}", " ", SPEED_WORDS.sub(" ", clause))).strip())
    return " ".join(kept) if kept and len(clauses) > 1 else (message or "")


class CommerceAgent:
    def __init__(self, engine: CommerceContextEngine, llm: Any = None) -> None:
        self.engine = engine
        self.llm = llm

    # ── understanding ────────────────────────────────────────────────────────────────────────────
    def understand(self, req: AgentRequest) -> Understanding:
        text, state = req.message or "", req.state or {}
        scores = {d: base_score(text).get(d, 0) for d in ORDER}
        for domain, cues in EXTRA_CUES.items():
            scores[domain] += sum(w for pattern, w in cues if re.search(pattern, text.lower()))
        refs = extract_references(text, self.engine.discovery)
        if "shipment_id" in refs or "order_id" in refs:
            scores[LOGISTICS] += 3
        if "claim_id" in refs:
            scores[WARRANTY] += 3
        focus = focus_of(text)
        domains = [d for d in ORDER if scores[d] >= MIN_SCORE]
        reasons = [f"{d} {scores[d]}" for d in ORDER if scores[d]]
        source = "RULES"
        if not domains:
            last = [d for d in (state.get("last_domains") or []) if d in ORDER]
            if last and FOLLOW_UP.search(text):  # a short follow-up continues the journey the last answer was about
                domains, source = last, "STATE"
                reasons.append("follow-up of the previous answer")
            elif (parsed := self._route_with_model(text)) is not None:
                domains, source = parsed
                reasons.append("routed by the language model")
        if not domains:
            weak = any(scores.values()) or bool(refs)
            return Understanding(CLARIFICATION if weak else UNKNOWN, [], refs, "NONE", scores, focus, reasons or ["nothing in the message points to a commerce journey"])
        intent = domains[0] if len(domains) == 1 else MULTI_DOMAIN
        return Understanding(intent, domains, refs, source, scores, focus, reasons)

    def _route_with_model(self, text: str) -> tuple[list[str], str] | None:
        if self.llm is None or not hasattr(self.llm, "parse_commerce_request"):
            return None
        try:
            parsed = self.llm.parse_commerce_request(text)
        except LLMError as exc:  # unreachable, rate-limited or an unusable reply: the rules' answer (a question) stands
            log.info("commerce routing by model unavailable: %s", type(exc).__name__)
            return None
        domains = [d for d in ORDER if d in parsed.domains]
        return (domains, "LLM") if parsed.in_scope and domains else None

    # ── the run ──────────────────────────────────────────────────────────────────────────────────
    def handle(self, req: AgentRequest) -> dict[str, Any]:
        u = self.understand(req)
        state = {**{k: v for k, v in (req.state or {}).items() if k in STATE_KEYS and v}, **u.references}
        if u.intent in (CLARIFICATION, UNKNOWN):
            return self._respond(req, u, [], state)
        steps: list[Step] = []
        ctx: dict[str, Any] = {}  # raw context objects by journey, for hand-over between the steps
        for domain in u.domains:
            step = self._run(domain, req, u, state, ctx, steps)
            steps.append(step)
        return self._respond(req, u, steps, state)

    def _run(self, domain: str, req: AgentRequest, u: Understanding, state: dict[str, Any], ctx: dict[str, Any], done: list[Step]) -> Step:
        if domain == DISCOVERY:
            return self._discovery(req, u, state, ctx)
        if domain == WARRANTY:
            return self._warranty(req, u, state, ctx, multi=len(u.domains) > 1)
        return self._logistics(req, u, state, ctx, multi=len(u.domains) > 1)

    # discovery ........................................................................................
    def _discovery(self, req: AgentRequest, u: Understanding, state: dict[str, Any], ctx: dict[str, Any]) -> Step:
        notes: list[str] = []
        text = discovery_text(req.message) if len(u.domains) > 1 else req.message
        if text != req.message:
            notes.append(f"The part search used “{text}”; the other journeys were answered from the rest of the message.")
        if "explain" in u.focus and state.get("last_request"):
            text = state["last_request"]
            notes.append(f"Explaining the previous search: “{text}”.")
        elif "availability" in u.focus and state.get("part_number") and state.get("machine_model") and not PART_NUMBER.search(text):
            text = f"{state['part_number']} for {state['machine_model']}"
            notes.append(f"“This part” was read as {state['part_number']} for {state['machine_model']}, the part of the previous answer.")
        # a machine the message names wins; otherwise a machine instance the user selected (or the previous answer was about) says which machine is meant
        instance = None if _mentions_model(text, self.engine) else state.get("machine_instance_id")
        if instance:
            notes.append(f"The machine is taken from {instance}.")
        context = self.engine.build_discovery_context(text, principal=req.principal, machine_instance_id=instance, destination_country=req.destination_country)
        ctx[DISCOVERY] = context
        d = context.decision
        return Step(DISCOVERY, d.status, d.decision, d.summary, notes, context.to_dict(), context.clarification)

    # warranty .........................................................................................
    def _warranty(self, req: AgentRequest, u: Understanding, state: dict[str, Any], ctx: dict[str, Any], multi: bool) -> Step:
        e, p = self.engine, req.principal
        notes: list[str] = []
        claim_id, instance_id, part_id = state.get("claim_id"), state.get("machine_instance_id"), state.get("part_id")
        if u.references.get("claim_id"):
            claim_id, instance_id, part_id = u.references["claim_id"], None, None
        if not claim_id and not (instance_id and part_id):
            resolved = self._resolve_warranty(req, state, ctx, notes)
            if isinstance(resolved, Step):
                return resolved
            claim_id, instance_id, part_id = resolved
        context = (e.build_warranty_context(principal=p, claim_id=claim_id) if claim_id else e.build_warranty_context(principal=p, machine_instance_id=instance_id, part_id=part_id))
        ctx[WARRANTY] = context
        d = context.decision
        return Step(WARRANTY, d.status, d.decision, d.summary, notes, context.to_dict(), getattr(context, "clarification", None))

    def _resolve_warranty(self, req: AgentRequest, state: dict[str, Any], ctx: dict[str, Any], notes: list[str]) -> tuple[str | None, str | None, str | None] | Step:
        """Find the claim, or the machine and part, the question is about. Only from what is recorded; more than one answer is a question to the user."""
        e, p = self.engine, req.principal
        instance_id = state.get("machine_instance_id")
        if instance_id is None:
            discovered = ctx.get(DISCOVERY)
            machine_id = ((discovered.machine or {}).get("machine_id") if discovered is not None else None) or state.get("machine_id")
            if machine_id is None:
                context = e.build_warranty_context(principal=p)  # the engine's own clarification: what this asker may choose from
                ctx[WARRANTY] = context
                return Step(WARRANTY, context.decision.status, context.decision.decision, context.decision.summary, notes, context.to_dict(), getattr(context, "clarification", None))
            owned = self._instances_of(p, machine_id)
            if len(owned) == 1:
                instance_id = owned[0]["machine_instance_id"]
                notes.append(f"Your only recorded {(discovered.machine or {}).get('model') if discovered is not None else machine_id} is {instance_id}.")
            else:
                return self._ask("WARRANTY", "Which machine do you mean?" if owned else "Which machine (or claim) is the failed part on? Give a machine instance or claim number.",
                                 [{"machine_instance_id": i["machine_instance_id"], "serial_number": i.get("serial_number"), "model_year": i.get("model_year")} for i in owned], notes)
        else:
            e.access.instance(p, e.lifecycle.instance(instance_id))
        installed = [i for i in e.lifecycle.installations(instance_id) if i["status"] == "CURRENT"]
        wanted = self._failed_part_class(ctx)
        part_id = state.get("part_id")
        if part_id is None:
            matching = sorted({i["part_id"] for i in installed if wanted is None or i["part_id"] in wanted})
            if len(matching) == 1:
                part_id = matching[0]
                if wanted is not None:
                    notes.append(f"{part_id} is the only part installed on {instance_id} that is the kind of part you asked about.")
            else:
                return self._ask("WARRANTY", "Which installed part do you mean?", [{"machine_instance_id": instance_id, "part_id": x} for x in (matching or sorted({i["part_id"] for i in installed}))], notes)
        claims = [x for x in e.lifecycle.claims(instance_id) if x["part_id"] == part_id]
        if len(claims) == 1:
            notes.append(f"Claim {claims[0]['claim_id']} is the only claim recorded for {part_id} on {instance_id}.")
            return claims[0]["claim_id"], None, None
        if len(claims) > 1:
            return self._ask("WARRANTY", f"{len(claims)} claims are recorded for this part. Which one do you mean?",
                             [{"claim_id": x["claim_id"], "claim_date": x["claim_date"], "status": x["status"]} for x in claims], notes)
        return None, instance_id, part_id

    def _instances_of(self, p: Principal, machine_id: str) -> list[dict[str, Any]]:
        """The asker's own machines of this model. Only a customer can be narrowed this way; an OEM or dealer must name the machine."""
        if p.role != CommerceRole.END_CUSTOMER or not p.customer_id:
            return []
        lc = self.engine.lifecycle
        return [i for i in (lc.instance(x) for x in lc.instance_ids()) if i and i["machine_id"] == machine_id and i.get("owner_id") == p.customer_id]

    @staticmethod
    def _failed_part_class(ctx: dict[str, Any]) -> set[str] | None:
        """The parts of the kind the discovery step searched for (canonical matches), so "the failed pump" means an installed pump. None when there was no discovery step."""
        d = ctx.get(DISCOVERY)
        if d is None:
            return None
        return {x["part_id"] for x in d.candidate_parts if (x.get("semantic_match") or {}).get("status") == "CANONICAL_MATCH"}

    # logistics ........................................................................................
    def _logistics(self, req: AgentRequest, u: Understanding, state: dict[str, Any], ctx: dict[str, Any], multi: bool) -> Step:
        shipment_id = u.references.get("shipment_id") or (None if u.references.get("order_id") else state.get("shipment_id"))
        order_id = u.references.get("order_id") or (None if shipment_id else state.get("order_id"))
        if multi and not shipment_id and not order_id and DISCOVERY in ctx:
            # a replacement that has not been ordered has no shipment: the commerce logistics context tracks shipments and orders, it does not quote delivery for a part nobody has ordered
            summary = ("No shipment or order exists for the replacement yet, so there is no tracked delivery to report. The logistics context follows shipments and orders; "
                       "it does not estimate delivery for a part that has not been ordered.")
            return Step(LOGISTICS, c.INSUFFICIENT_DATA, "NO_SHIPMENT_FOR_UNORDERED_PART", summary, ["No shipment or order was referred to."], None, None)
        context = self.engine.build_logistics_context(principal=req.principal, shipment_id=shipment_id, order_id=order_id)
        ctx[LOGISTICS] = context
        d = context.decision
        return Step(LOGISTICS, d.status, d.decision, d.summary, [], context.to_dict(), context.clarification)

    @staticmethod
    def _ask(domain: str, question: str, options: list[dict[str, Any]], notes: list[str]) -> Step:
        return Step(domain, c.REQUIRES_CLARIFICATION, c.REQUIRES_CLARIFICATION, question, notes, None, {"question": question, "options": options})

    # ── the answer ───────────────────────────────────────────────────────────────────────────────
    def _respond(self, req: AgentRequest, u: Understanding, steps: list[Step], state: dict[str, Any]) -> dict[str, Any]:
        out = ans.compose(u, steps, req.message, llm=self.llm)
        out["state"] = self._next_state(state, u, steps)
        out["understanding"] = {"intent": u.intent, "domains": u.domains, "source": u.source, "scores": u.scores, "focus": u.focus, "references": u.references, "reasons": u.reasons}
        return out

    @staticmethod
    def _next_state(state: dict[str, Any], u: Understanding, steps: list[Step]) -> dict[str, Any]:
        """What the next message may rely on: the references the answer was about. Only identifiers and the last search text; never a decision."""
        nxt = {k: v for k, v in state.items() if k in STATE_KEYS and v}
        for s in steps:
            x = s.context or {}
            if s.domain == DISCOVERY:
                m = x.get("machine") or {}
                if m.get("machine_id"):
                    nxt["machine_id"], nxt["machine_model"] = m["machine_id"], m.get("model")
                part = x.get("recommended_part") or x.get("compatible_part")
                if part:
                    nxt["part_id"], nxt["part_number"] = part["part_id"], part["part_number"]
                if "explain" not in u.focus and "availability" not in u.focus:
                    nxt["last_request"] = x.get("user_request")
            elif s.domain == LOGISTICS and x.get("shipment"):
                nxt["shipment_id"] = x["shipment"]["shipment_id"]
                nxt["order_id"] = x["shipment"].get("order_id") or nxt.get("order_id")
            elif s.domain == WARRANTY and x.get("machine"):
                nxt["machine_instance_id"] = x["machine"].get("machine_instance_id")
                if x.get("claim"):
                    nxt["claim_id"] = x["claim"]["claim_id"]
                if x.get("current_part"):
                    nxt["part_id"] = x["current_part"]["part_id"]
        nxt["last_domains"] = list(u.domains)
        return nxt


def _mentions_model(text: str, engine: CommerceContextEngine) -> bool:
    """The message names a machine model itself (then that, not a remembered machine, is what is meant)."""
    low = (text or "").lower()
    return any(re.search(r"(?<![a-z0-9])" + r"[\s\-_/]?".join(re.escape(g) for g in re.findall(r"[a-z]+|\d+", m["model"].lower())) + r"(?![a-z0-9])", low) for m in engine.discovery.machines())
