"""Agentic Shopping: "get my need resolved".

request -> the language model reads it (machine, part, budget, priority, availability wish, delivery place; its own commerce scope) -> the
backend validates that reading -> the machine is resolved in Neo4j -> parts recorded as FITTING it are found -> the graph supplies
each candidate's price, fitment status, catalogue status, stock, supplier and delivery estimate -> ranking.decide() applies the
constraints and ranks deterministically -> the evidence and one plain sentence are built only from those facts.

The model never decides a fact, a price, a ranking, stock or a delivery time. If it cannot be reached the request fails clearly
(LLMUnavailable); there is no keyword fallback. Parts Intelligence investigates; this module acts. They share the graph, the
entity resolver and the part status rule, not their scope.
"""
from __future__ import annotations

import logging
import math
from collections import Counter

from app.agent.ranking import AVAILABILITY_LABEL, AVAILABILITY_RANK, Constraints, Decision, Facts, decide, tradeoffs
from app.graph.client import GraphClient
from app.graph.queries import agent as q
from app.graph.repositories.intelligence import IntelligenceRepository
from app.graph.repositories.parts import PartRepository
from app.intelligence.models import Kind
from app.intelligence.resolver import EntityResolver
from app.llm import LLMClient, LLMUnavailable
from app.schemas.agent import (AgentResponse, AgentSuggestion, Candidate, Delivery, DecisionView, EvidenceItem, Excluded, Interpretation, Option, ProvenanceRow,
                               Step, StockLocation, SupplierRef, WhyItem)
from app.schemas.catalogue import PartSummary
from app.services.part_status import status_label
from app.services.parts import to_summary

log = logging.getLogger(__name__)

LABELS = {"request": "Request received", "understand": "Understanding need", "machine": "Identifying machine", "part": "Identifying part",
          "fitment": "Checking fitment", "availability": "Checking availability", "fulfilment": "Evaluating fulfilment", "compare": "Comparing options",
          "recommend": "Preparing recommendation"}
ORDER = list(LABELS)
OUT_OF_SCOPE = ("I find and help order Noordveld machine parts. Describe the part you need and the machine it is for, for example "
                "\"I need a hydraulic hose for my wheel loader\". To investigate data instead, use Parts Intelligence.")


def eur(amount: float) -> str:
    return f"€{amount:,.2f}" if amount % 1 else f"€{amount:,.0f}"


def _avail(state: str | None) -> str:
    return AVAILABILITY_LABEL.get(state or "", "Availability not recorded")


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


class AgentService:
    def __init__(self, graph: GraphClient, llm: LLMClient | None) -> None:
        self._g = graph
        self._intel = IntelligenceRepository(graph)
        self._parts = PartRepository(graph)
        self._resolver = EntityResolver(self._intel)
        self._llm = llm

    # ── starter requests, built from the graph ───────────────────────────────────────────────────
    def suggestions(self) -> list[AgentSuggestion]:
        rows = self._g.read(q.SEEDS)
        if not rows:
            return []
        city = next(iter(sorted(self._g.read(q.CITIES)[0]["cities"] or [])), None)
        pick = [rows[i * len(rows) // 4] for i in range(min(4, len(rows)))]

        def thing(i: int) -> str:
            return (pick[i % len(pick)]["sub"] or pick[i % len(pick)]["part"]).lower()

        def a(word: str) -> str:
            return f"an {word}" if word[:1] in "aeiou" else f"a {word}"

        def machine(i: int) -> str:
            return pick[i % len(pick)]["machine"]

        # a budget the recorded price actually fits: the next round hundred above it
        price = pick[1 % len(pick)].get("price")
        budget = int(math.ceil((price + 1) / 100.0) * 100) if price else None
        rows_out = [
            (f"I need {a(thing(0))} for my {machine(0)}, preferably in stock.", thing(0), machine(0), "Prefer in stock"),
            (f"My {machine(1)} is down. I need {a(thing(1))}" + (f" under €{budget}" if budget else "") + " and I need it quickly.", thing(1), f"{machine(1)} is down",
             f"Under €{budget} · fastest" if budget else "As soon as possible"),
            (f"Find the cheapest {thing(2)} for the {machine(2)}.", thing(2), machine(2), "Lowest price"),
            (f"I need {a(thing(3))} for the {machine(3)}" + (f", delivered to {city}." if city else "."), thing(3), machine(3), f"Deliver to {city}" if city else "Prefer in stock"),
        ]
        seen: set[str] = set()
        out = []
        for text, need, context, action in rows_out:
            if text not in seen:
                seen.add(text)
                out.append(AgentSuggestion(request=text, need=need[0].upper() + need[1:], context=context, action=action))
        return out

    # ── one request ──────────────────────────────────────────────────────────────────────────────
    def recommend(self, request: str) -> AgentResponse:
        text = " ".join(request.split())
        if self._llm is None:
            raise LLMUnavailable("the language model is not configured")
        sp = self._llm.parse_shopping_request(text)
        # validation of the model's reading: only known values pass; a budget must be a positive number
        budget = sp.budget_max if isinstance(sp.budget_max, (int, float)) and sp.budget_max > 0 else None
        currency = (sp.budget_currency or ("EUR" if budget is not None else None))
        interp = Interpretation(part_type=sp.part_type, preference=sp.preference if sp.preference in ("cheapest", "fastest") else "none",  # type: ignore[arg-type]
                                delivery_place=sp.delivery_place, quantity=sp.quantity, budget_max=budget, budget_currency=currency,
                                availability=sp.availability if sp.availability in ("require", "prefer") else "none")  # type: ignore[arg-type]
        steps: list[Step] = []

        def step(key: str, status: str, message: str) -> None:  # a later word on the same step replaces the earlier one
            new = Step(key=key, label=LABELS[key], status=status, message=message)  # type: ignore[arg-type]
            at = next((n for n, s in enumerate(steps) if s.key == key), None)
            if at is None:
                steps.append(new)
            else:
                steps[at] = new

        def finish(**kw) -> AgentResponse:
            done = {s.key for s in steps}
            for key in ORDER:
                if key not in done:
                    step(key, "skipped", "Not reached")
            return AgentResponse(request=text, interpretation=interp, steps=sorted(steps, key=lambda s: ORDER.index(s.key)), **kw)

        step("request", "done", f'Request received: "{text}"')
        if not sp.in_scope:  # no graph access for a request that is not a purchase
            step("understand", "blocked", "This is not a parts request")
            return finish(state="out_of_scope", question=OUT_OF_SCOPE)
        step("understand", "done", "Understood: " + self._summary(interp, sp.machine))
        if budget is not None and currency != "EUR":
            step("compare", "blocked", f"The budget is in {currency}; prices are recorded in euros")
            return finish(state="need_detail", question=f"Prices are recorded in euros. What is your budget in euros? (You wrote {budget:g} {currency}.)")

        # machine: resolved in the graph, never assumed
        machine = None
        if sp.machine:
            found = self._resolver.resolve((sp.machine,))
            machine = found.one(Kind.MACHINE)
            if machine is None and found.many(Kind.MACHINE):
                many = found.many(Kind.MACHINE)
                step("machine", "blocked", f"“{sp.machine}” matches {len(many)} machines: {', '.join(m.label for m in many)}")
                return finish(state="choose_machine", question=f"Which {sp.machine} is it?", options=[Option(label=m.detail or m.label, refine=f"for my {m.label}") for m in many])
            if machine is None:
                step("machine", "blocked", f"No machine called “{sp.machine}” is in the catalogue")
                return finish(state="need_machine", question=f"I could not find “{sp.machine}” in the Noordveld catalogue. Which machine is it?", options=self._machine_options(sp.part_type))
            interp.machine = machine.label
            step("machine", "done", f"Identified machine: {machine.detail or machine.label} (from the catalogue)")

        if not sp.part_type:
            step("part", "blocked", "The part is not clear, so I will ask what you need")
            return finish(state="need_part", question="Which part do you need? I won't guess.", options=self._part_options(machine.label if machine else None))
        if machine is None:
            step("machine", "blocked", "No machine was named, so I will ask which one")
            return finish(state="need_machine", question=f"Which machine is the {sp.part_type} for? Fitment depends on the machine.", options=self._machine_options(sp.part_type))

        # parts recorded as fitting this machine
        parts = self._search(sp.part_type, machine.label)
        if not parts:
            elsewhere = sorted({f.model_code for p in self._search(sp.part_type, None) for f in p.fitment})
            step("part", "done", f"Looked for: {sp.part_type}")
            step("fitment", "blocked", f"No {sp.part_type} is recorded as fitting the {machine.label}")
            note = [f"A {sp.part_type} is recorded for {', '.join(elsewhere)}, not for the {machine.label}."] if elsewhere else []
            return finish(state="no_match", question=f"No {sp.part_type} is recorded as fitting the {machine.label}, so I will not recommend one.", notes=note)
        subs = Counter(p.subcategory or p.category or "Other" for p in parts)
        if len(subs) > 1:
            wanted = sp.part_type.lower()
            singular = " ".join(w[:-1] if w.endswith("s") and len(w) > 3 else w for w in wanted.split())
            # narrow only on the kind the user actually named ("brake pad" -> "Brake pad set"); one loose word ("hydraulic") is a choice for the user
            matching = [s for s in subs if s.lower() in (wanted, singular) or (len(singular.split()) > 1 and s.lower().startswith(singular))]
            if len(matching) == 1:
                parts = [p for p in parts if (p.subcategory or p.category or "Other") == matching[0]]
            else:
                step("part", "blocked", f"Several kinds of part match: {', '.join(sorted(subs))}")
                return finish(state="choose_type", question=f"Which kind of {sp.part_type} do you mean for the {machine.label}?",
                              options=[Option(label=f"{s} ({n})", refine=s.lower()) for s, n in sorted(subs.items())])
        interp.part_type = parts[0].subcategory or sp.part_type
        step("part", "done", f"Identified part type: {interp.part_type}")

        # facts per candidate, all from the graph
        facts = [self._facts(p, machine.label, sp.delivery_place) for p in parts]
        by_id = {p.part_id: p for p in parts}
        confirmed = [f for f in facts if f.fitment_status == "CONFIRMED"]
        step("fitment", "done" if confirmed else "blocked",
             f"{_plural(len(facts), 'part')} recorded as fitting the {machine.label}; {len(confirmed)} with confirmed fitment"
             + (f", {len(facts) - len(confirmed)} conditional (needs identification)" if len(confirmed) < len(facts) else ""))
        decision = decide(facts, Constraints(budget_max=budget, preference=interp.preference, availability=interp.availability))
        verified = [f for f in confirmed if f not in decision.excluded_unverified]
        counts = Counter(_avail(f.availability) for f in verified)
        step("availability", "done", f"Checked recorded availability for {_plural(len(verified), 'verified option')}: " + (", ".join(f"{n} {k.lower()}" for k, n in counts.items()) or "none"))
        excluded = [Excluded(part_number=f.part_number, name=f.name, status_label=status_label(f.part_status)) for f in decision.excluded_unverified] + \
                   [Excluded(part_number=f.part_number, name=f.name, status_label=status_label(f.part_status) if f.part_status != "VERIFIED" else "Fitment conditional")
                    for f in decision.excluded_conditional]

        if decision.blocked_by:
            return finish(**self._blocked(decision, interp, machine.label, step), excluded=excluded)

        ranked = decision.ranked
        best, alts = ranked[0], ranked[1:3]
        if sp.delivery_place:
            have = [f for f in ranked if f.delivery_days is not None]
            step("fulfilment", "done", f"Delivery estimates to {sp.delivery_place} recorded for {_plural(len(have), 'option')}" if have else f"No delivery estimate to {sp.delivery_place} is recorded")
        else:
            lead = [f for f in ranked if not f.in_stock and f.supplier_lead_days is not None]
            step("fulfilment", "done", f"{_plural(sum(1 for f in ranked if f.in_stock), 'option')} ship from recorded stock" + (f"; {len(lead)} would wait for supplier lead time" if lead else ""))
        step("compare", "done", f"Compared {_plural(len(ranked), 'valid option')} on {decision.basis}" + (f"; {len(decision.over_budget)} over your {eur(budget)} budget" if budget is not None and decision.over_budget else ""))
        step("recommend", "done", f"Recommending {best.part_number} — {best.name}")

        evidence, delivery = self._evidence(best, by_id[best.part_id], machine.label, sp.delivery_place, interp, decision, ranked)
        candidates = [self._candidate(f, by_id[f.part_id], f is best, best, budget, sp.delivery_place) for f in [best, *alts]]
        notes = []
        if sp.delivery_place and delivery is None:
            notes.append(f"No delivery estimate to {sp.delivery_place} is recorded for a warehouse that holds this part, so no delivery time is given.")
        if decision.not_available:
            notes.append("Not considered because you asked for stock now: " + ", ".join(f"{f.part_number} ({_avail(f.availability).lower()})" for f in decision.not_available) + ".")
        if decision.over_budget:
            notes.append(f"Over your {eur(budget)} budget: " + ", ".join(f"{f.part_number} ({eur(f.price)})" for f in decision.over_budget if f.price is not None) + ".")  # type: ignore[arg-type]
        if sp.quantity:
            notes.append(f"You asked for {sp.quantity}; choose the quantity in the cart.")
        return finish(state="recommendation", candidates=candidates, recommended=best.part_number, reason=self._reason(best, alts, machine.label, interp, decision),
                      evidence=evidence, comparison=self._compare(alts), excluded=excluded, delivery=delivery, notes=notes,
                      decision=self._decision(best, ranked, machine.label, interp), why=self._why(best, alts, candidates[0], machine.label, interp),
                      how_we_know=self._how_we_know(by_id[best.part_id], candidates[0], delivery is not None))

    # ── decisions explained ──────────────────────────────────────────────────────────────────────
    @staticmethod
    def _summary(i: Interpretation, machine: str | None) -> str:
        bits = [f"need {i.part_type}" if i.part_type else "need not stated", f"for {machine}" if machine else "machine not stated"]
        if i.budget_max is not None:
            bits.append(f"budget up to {eur(i.budget_max)}")
        if i.preference != "none":
            bits.append("priority: lowest price" if i.preference == "cheapest" else "priority: fastest")
        if i.availability != "none":
            bits.append("must be in stock" if i.availability == "require" else "prefer in stock")
        if i.delivery_place:
            bits.append(f"deliver to {i.delivery_place}")
        return ", ".join(bits)

    def _blocked(self, d: Decision, i: Interpretation, machine: str, step) -> dict:
        """No valid option: say exactly which constraint stopped it. The constraint is never relaxed."""
        need = (i.part_type or "part").lower()
        if d.blocked_by == "budget":
            priced = sorted([f for f in d.over_budget if f.price is not None], key=lambda f: f.price)  # type: ignore[arg-type,return-value]
            cheapest = f" The lowest recorded price is {eur(priced[0].price)} ({priced[0].part_number})." if priced else ""  # type: ignore[arg-type]
            unpriced = f" {_plural(len(d.unpriced), 'part')} have no recorded price, so they cannot be shown to fit a budget." if d.unpriced else ""
            n = len(d.over_budget) + len(d.unpriced)
            step("compare", "blocked", f"None of {_plural(n, 'compatible verified option')} is within {eur(i.budget_max)}")  # type: ignore[arg-type]
            return {"state": "no_match", "question": f"I found {_plural(n, f'compatible verified {need}')} for the {machine}, but none currently meets your {eur(i.budget_max)} budget.{cheapest}{unpriced}"}  # type: ignore[arg-type]
        if d.blocked_by == "availability":
            step("availability", "blocked", "No compatible verified option has stock recorded")
            return {"state": "no_match", "question": f"I found compatible verified {need} options for the {machine}, but none has stock recorded right now, and you asked for one that is available now."}
        if d.blocked_by == "fitment":
            step("fitment", "blocked", "Fitment is only conditional")
            return {"state": "no_match", "question": f"The {need} recorded for the {machine} fits only conditionally (the machine variant or serial must be identified first), so I will not recommend it as compatible."}
        step("compare", "blocked", "No verified option")
        return {"state": "no_match", "question": f"No verified {need} is recorded for the {machine}, so I will not recommend one."}

    @staticmethod
    def _reason(best: Facts, alts: list[Facts], machine: str, i: Interpretation, d: Decision) -> str:
        """One sentence, built only from graph facts and the deterministic decision."""
        bits = [f"it fits the {machine} (confirmed fitment)", "it is verified"]
        if i.budget_max is not None and best.price is not None:
            bits.append(f"at {eur(best.price)} it is within your {eur(i.budget_max)} budget")
        if best.in_stock:
            bits.append(f"it is {_avail(best.availability).lower()} with {best.units} units recorded")
        if not alts:
            bits.append("it is the only valid option")
        elif i.preference == "cheapest":
            bits.append("it has the lowest recorded price of the valid options")
        elif i.preference == "fastest":
            if best.delivery_days is not None:
                bits.append(f"it has the fastest recorded delivery ({best.delivery_days} days)")
            else:
                bits.append("it ships from recorded stock" if best.in_stock else "it has the shortest recorded supplier lead time")
        else:
            dearer = [a.part_number for a in alts if best.price is not None and a.price is not None and a.price > best.price]
            if dearer:
                bits.append(f"it costs less than {' and '.join(dearer)}")
        last = bits.pop()
        return f"Recommended because {', '.join(bits)} and {last}." if bits else f"Recommended because {last}."

    @staticmethod
    def _compare(alts: list[Facts]) -> str:
        if not alts:
            return "No other valid option fits this machine and your requirements."
        return "Compared with " + " and ".join(f"{a.part_number} ({eur(a.price) if a.price is not None else 'price not recorded'}, {_avail(a.availability).lower()})" for a in alts) + "."

    def _candidate(self, f: Facts, p: PartSummary, recommended: bool, best: Facts, budget: float | None, place: str | None) -> Candidate:
        """Every decision field with an explicit state. Inventory, fulfilment and delivery are kept apart: how many, how supplied, when it arrives."""
        stock = [StockLocation(warehouse=w["name"] or w["warehouse_id"], city=w.get("city"), available=int(w["available"]))
                 for w in self._intel.warehouses(f.part_id) if (w.get("available") or 0) > 0]
        sups = [SupplierRef(name=x["name"] or x["supplier_id"], lead_time_days=x.get("lead_time_days"), primary=bool(x.get("is_primary"))) for x in self._intel.suppliers(f.part_id)]
        sups.sort(key=lambda x: not x.primary)

        fitment_label = {"CONFIRMED": "Confirmed fit", "CONDITIONAL": "Conditional fit · verification required"}.get((f.fitment_status or "").upper(), "Fitment not verified")
        if f.units is None:
            inventory = "Not recorded"
        elif stock:
            inventory = f"{f.units} units at {stock[0].city or stock[0].warehouse}" if len(stock) == 1 else f"{f.units} units across {len(stock)} warehouses"
        else:
            inventory = f"{f.units} units in stock"

        row = self._g.read(q.DELIVERY, part_id=f.part_id, city=place.strip().lower()) if place else []
        if f.in_stock:
            if row:
                fulfilment = f"Ships from {row[0]['warehouse']}"
            elif len(stock) == 1:
                fulfilment = f"Available from stock in {stock[0].city or stock[0].warehouse}"
            elif stock:
                fulfilment = f"Available from connected stock ({len(stock)} warehouses)"
            else:
                fulfilment = "Available from stock"
        elif f.supplier_lead_days is not None:
            fulfilment = f"Supplier lead time · {f.supplier_lead_days} days"
        else:
            fulfilment = "Fulfilment not recorded"

        if row:
            r = row[0]
            parts = [f"{r['standard_days']} days standard" if r["standard_days"] is not None else None, f"{r['express_days']} days express" if r["express_days"] is not None else None]
            delivery = f"{' · '.join(x for x in parts if x) or 'Estimate recorded'} to {r['city']}"
        elif place and f.in_stock:
            delivery = f"No delivery estimate recorded to {place}"
        else:
            delivery = "Estimate not recorded"

        primary = sups[0] if sups else None
        if not primary:
            supplier_label = "Not recorded"
        elif f.in_stock or primary.lead_time_days is None:
            supplier_label = primary.name  # a lead time does not apply to stock that is already on the shelf
        else:
            supplier_label = f"{primary.name} · lead time {primary.lead_time_days} days"

        can_order = (f.fitment_status or "").upper() == "CONFIRMED" and f.part_status == "VERIFIED" and f.orderable is True and f.price is not None
        action = "add_to_cart" if can_order else "identify" if f.part_status != "VERIFIED" else "unavailable"
        note = None
        if can_order and not f.in_stock:
            note = f"Backorder: supplied after the supplier lead time ({f.supplier_lead_days} days)" if f.supplier_lead_days is not None else "Backorder: the supplier lead time is not recorded"
        return Candidate(part=p, recommended=recommended, availability_label=_avail(f.availability), fitment_status=f.fitment_status, fitment_label=fitment_label,
                         inventory=inventory, stock_locations=stock, fulfilment=fulfilment, delivery=delivery, supplier_label=supplier_label, suppliers=sups,
                         price_basis="ex VAT" if f.price is not None else None, order_action=action, order_note=note,
                         supplier=f.supplier, supplier_lead_days=f.supplier_lead_days, fulfilment_days=f.fulfilment_days,
                         within_budget=(f.price is not None and f.price <= budget) if budget is not None else None,
                         tradeoffs=[] if recommended else tradeoffs(f, best), can_add_to_cart=can_order)

    @staticmethod
    def _decision(best: Facts, ranked: list[Facts], machine: str, i: Interpretation) -> DecisionView:
        """The rules the choice was made by, in words a buyer uses. Mirrors ranking.decide exactly."""
        req = [f"Confirmed fit for the {machine}", "Verified part"]
        if i.budget_max is not None:
            req.append(f"Within your {eur(i.budget_max)} budget")
        if i.availability == "require":
            req.append("In stock now")
        if i.preference == "cheapest":
            pri = ["Lowest price", "Availability"]
        elif i.preference == "fastest":
            pri = ["In-stock availability", "Fastest recorded fulfilment", "Price"]
        else:
            pri = ["Availability", "Price"]
        if i.availability == "prefer" and i.preference != "fastest":
            pri = ["In-stock availability", *[x for x in pri if x != "In-stock availability"]]
        because = ["it is confirmed compatible"]
        if best.in_stock:
            because.append("it is currently in stock")
        prices = [f.price for f in ranked if f.price is not None]
        if len(ranked) > 1 and best.price is not None and best.price == min(prices):
            because.append("it has the lowest price of the valid options")
        summary = f"{best.part_number} ranked first because " + (", ".join(because[:-1]) + " and " + because[-1] if len(because) > 1 else because[0]) + "."
        return DecisionView(requirements=req, priorities=pri, summary=summary)

    @staticmethod
    def _why(best: Facts, alts: list[Facts], c: Candidate, machine: str, i: Interpretation) -> list[WhyItem]:
        """Reasons, each one a graph fact, connected to the user's preference and compared with the alternatives."""
        out = [WhyItem(title="Confirmed compatibility", detail=f"Fits the {machine} (catalogue fitment).")]
        if best.in_stock:
            out.append(WhyItem(title="In stock", detail=f"{c.inventory} in connected inventory."))
        elif best.supplier_lead_days is not None:
            out.append(WhyItem(title="Availability", detail=f"{_avail(best.availability)}; supplied after a {best.supplier_lead_days}-day supplier lead time."))
        if alts:
            worse = [a for a in alts if AVAILABILITY_RANK.get(a.availability or "", 3) > AVAILABILITY_RANK.get(best.availability or "", 3)]
            if worse:
                states = sorted({{"BACKORDER": "on backorder", "LIMITED": "in limited stock"}.get(a.availability or "", "without recorded availability") for a in worse})
                out.append(WhyItem(title="Better availability", detail=f"{'The alternative is' if len(alts) == 1 else 'Alternatives are'} {' or '.join(states)}: " + ", ".join(a.part_number for a in worse) + "."))
            cheaper = [a for a in alts if a.price is not None and best.price is not None and a.price < best.price]
            dearer = [a for a in alts if a.price is not None and best.price is not None and a.price > best.price]
            if best.price is not None and dearer and not cheaper:
                out.append(WhyItem(title="Lower price", detail=f"{eur(best.price)} compared with " + " and ".join(f"{eur(a.price)} ({a.part_number})" for a in dearer) + "."))  # type: ignore[arg-type]
            elif best.price is not None and cheaper:
                out.append(WhyItem(title="Price", detail=f"{eur(best.price)}. " + " and ".join(f"{a.part_number} costs less ({eur(a.price)})" for a in cheaper) + " but ranks lower on your priorities."))  # type: ignore[arg-type]
        if i.budget_max is not None and best.price is not None:
            out.append(WhyItem(title="Within your budget", detail=f"{eur(best.price)} against your {eur(i.budget_max)} budget."))
        if c.delivery and not c.delivery.startswith(("Estimate not", "No delivery")):
            out.append(WhyItem(title="Delivery", detail=f"{c.delivery}, {c.fulfilment.lower()}."))
        preference = {
            "cheapest": "You asked for the cheapest option, so the lowest valid price came first.",
            "fastest": "You asked for the fastest option, so parts in stock and the shortest recorded fulfilment came before price.",
        }.get(i.preference)
        if preference is None:
            preference = "You preferred an in-stock option, so availability was prioritised before price." if i.availability == "prefer" else                          "You asked for a part that is in stock now, so only stocked parts were considered; then availability, then price." if i.availability == "require" else                          "No priority was stated, so the default applies: availability first, then price."
        out.append(WhyItem(title="Your priority", detail=preference))
        return out

    @staticmethod
    def _how_we_know(p: PartSummary, c: Candidate, has_delivery: bool) -> list[ProvenanceRow]:
        """Where each kind of fact comes from, kept out of the commercial fields so they stay clean."""
        def kind(status: str | None, real: str, demo: str) -> str:
            return demo if status == "SYNTHETIC_DEMO" else real if status else "Source not stated"
        rows = [ProvenanceRow(label="Fitment", value=f"Noordveld catalogue · {c.fitment_label.lower()}"),
                ProvenanceRow(label="Part status", value=kind(p.availability.data_status if p.availability else None, "Catalogue status", "Demo catalogue status")),
                ProvenanceRow(label="Price", value=kind(p.price.data_status if p.price else None, "Recorded list price, ex VAT", "Recorded demo list price, ex VAT")),
                ProvenanceRow(label="Inventory", value=kind(p.availability.data_status if p.availability else None, "Recorded warehouse stock", "Synthetic demo inventory")),
                ProvenanceRow(label="Supplier", value="Synthetic demo supplier relationship" if c.suppliers else "No supplier relationship recorded")]
        if has_delivery:
            rows.append(ProvenanceRow(label="Delivery", value="Demo delivery estimate"))
        rows.append(ProvenanceRow(label="Ranking", value="Deterministic comparison of graph facts; the language model only read your request"))
        return rows

    # ── graph reads ──────────────────────────────────────────────────────────────────────────────
    def _facts(self, p: PartSummary, machine: str, place: str | None) -> Facts:
        fitment = next((f.fitment_status for f in p.fitment if f.model_code == machine), None)
        suppliers = self._intel.suppliers(p.part_id)
        primary = next((s for s in suppliers if s.get("is_primary")), suppliers[0] if suppliers else None)
        units = p.availability.total_available if p.availability else None
        delivery_days, delivery_from = None, None
        if place:
            rows = self._g.read(q.DELIVERY, part_id=p.part_id, city=place.strip().lower())
            if rows:
                delivery_days, delivery_from = rows[0]["standard_days"], rows[0]["warehouse"]
        return Facts(part_id=p.part_id, part_number=p.part_number, name=p.name, fitment_status=fitment,
                     part_status=p.availability.part_status if p.availability else None, orderable=p.availability.orderable if p.availability else None,
                     price=p.price.amount if p.price else None, availability=p.availability.state if p.availability else None, units=units,
                     supplier=primary["name"] if primary else None, supplier_lead_days=primary.get("lead_time_days") if primary else None,
                     delivery_days=delivery_days, delivery_from=delivery_from)

    def _search(self, part_type: str, machine: str | None) -> list[PartSummary]:
        filler = {"new", "replacement", "spare", "replace", "a", "an", "the", "another", "some"}
        words = [w for w in part_type.split() if w.lower() not in filler] or part_type.split()
        part_type = " ".join(words)
        # the words as given, then made singular; never a looser search ("water pump" must not become "pump")
        attempts = [part_type, " ".join(w[:-1] if w.lower().endswith("s") and len(w) > 3 else w for w in words)]
        for t in dict.fromkeys(a for a in attempts if a):
            _, ids = self._parts.search(text=t, category=None, machine=machine, availability=None, orderable=None, sort="relevance", offset=0, limit=60)
            if ids:
                return [to_summary(r) for r in self._parts.summaries(ids)]
        return []

    def _machine_options(self, part_type: str | None) -> list[Option]:
        if part_type:
            fits = sorted({f.model_code for p in self._search(part_type, None) for f in p.fitment})
            if fits:
                return [Option(label=m, refine=f"for my {m}") for m in fits[:15]]
        return [Option(label=f"{r['machine']['model_code']} · {r['machine']['machine_type']}", refine=f"for my {r['machine']['model_code']}") for r in self._intel.machines()]

    def _part_options(self, machine: str | None) -> list[Option]:
        _, ids = self._parts.search(text="", category=None, machine=machine, availability=None, orderable=True, sort="relevance", offset=0, limit=60)
        subs = Counter(p.subcategory for p in (to_summary(r) for r in self._parts.summaries(ids)) if p.subcategory)
        return [Option(label=s, refine=s.lower()) for s, _ in subs.most_common(8)]

    def _evidence(self, best: Facts, part: PartSummary, machine: str, place: str | None, i: Interpretation, d: Decision,
                  ranked: list[Facts]) -> tuple[list[EvidenceItem], Delivery | None]:
        stock = [w for w in self._intel.warehouses(best.part_id) if (w["available"] or 0) > 0]
        suppliers = self._intel.suppliers(best.part_id)
        demo = part.availability.data_status if part.availability else None
        items = [
            EvidenceItem(key="fit", ok=best.fitment_status == "CONFIRMED", label=f"Fits the {machine}", data_class="SOURCE_DERIVED",
                         detail=f"Catalogue fitment · {(best.fitment_status or 'status not stated').lower()}"),
            EvidenceItem(key="verified", ok=best.part_status == "VERIFIED", label="Verified part", detail=f"Status: {status_label(best.part_status)} (demo catalogue status)", data_class=demo),
        ]
        if best.price is not None:
            label = f"Price {eur(best.price)} — within your {eur(i.budget_max)} budget" if i.budget_max is not None else f"Price {eur(best.price)}"
            items.append(EvidenceItem(key="budget", ok=True, label=label, detail="Recorded list price, excluding VAT (demo price)", data_class=part.price.data_status if part.price else None))
        items.append(EvidenceItem(key="availability", ok=best.in_stock, label=_avail(best.availability), detail="The same availability the Parts Store shows (demo data)", data_class=demo))
        items.append(EvidenceItem(key="inventory", ok=bool(stock), label="Connected inventory" if stock else "No stock recorded",
                                  detail=(f"{sum(w['available'] or 0 for w in stock)} units across {_plural(len(stock), 'warehouse')}: " + ", ".join(f"{w['name']} ({w['available']})" for w in stock)) if stock
                                  else "No warehouse holds recorded stock", data_class=stock[0]["data_status"] if stock else None))
        items.append(EvidenceItem(key="supplier", ok=bool(suppliers), label=f"Supplier: {best.supplier}" if best.supplier else "No supplier relationship",
                                  detail=(", ".join(s["name"] for s in suppliers) + (f" · lead time {best.supplier_lead_days} days" if best.supplier_lead_days is not None else "")) if suppliers
                                  else "None recorded, so none is claimed", data_class=suppliers[0]["data_status"] if suppliers else None))
        delivery = None
        if place:
            rows = self._g.read(q.DELIVERY, part_id=best.part_id, city=place.strip().lower())
            if rows:
                r = rows[0]
                delivery = Delivery(city=r["city"], warehouse=r["warehouse"], warehouse_city=r["warehouse_city"], standard_days=r["standard_days"], express_days=r["express_days"])
                items.append(EvidenceItem(key="delivery", ok=True, label=f"Delivery to {r['city']}", data_class=r["data_status"],
                                          detail=f"From {r['warehouse']}: {r['standard_days']} days standard, {r['express_days']} days express (demo estimate)"))
            else:
                items.append(EvidenceItem(key="delivery", ok=False, label=f"Delivery to {place}", detail="No delivery estimate recorded for that place"))
        if len(ranked) > 1:
            what = {"cheapest": "Lowest recorded price", "fastest": "Fastest recorded fulfilment"}.get(i.preference, "Best availability, then price")
            items.append(EvidenceItem(key="ranking", ok=True, label=f"{what} of {_plural(len(ranked), 'valid option')}", detail=f"Ranked on {d.basis}"))
        return items, delivery
