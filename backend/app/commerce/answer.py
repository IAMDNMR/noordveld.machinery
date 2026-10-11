"""Compose the agent's answer from the contexts' own decisions, facts and evidence. Deterministic: every sentence below is a template over a value the context returned.

The only language-model step is optional and last: it may reword the LEAD (at most two sentences) from the evidence the sections already show. The reword is accepted only when
app.intelligence.grounding.is_grounded accepts it (every number and identifier is already in the evidence, nothing it claims is absent); otherwise the deterministic lead stays.
Nothing here decides fitment, stock, a shipment's state, a date or warranty eligibility, and nothing here widens what the context's visibility already removed.
"""
from __future__ import annotations

import logging
from typing import Any

from app.commerce import contract as c
from app.intelligence.grounding import is_grounded
from app.llm.base import LLMError

log = logging.getLogger(__name__)

DISCOVERY, LOGISTICS, WARRANTY = "DISCOVERY", "LOGISTICS", "WARRANTY"
TITLES = {DISCOVERY: "Part discovery", LOGISTICS: "Shipment and logistics", WARRANTY: "Warranty and traceability"}
SYNTHETIC_NOTICE = "This is demonstration data: the records are synthetic demo data, not real operational data."
OUT_OF_SCOPE = ("I can find a part for a machine, track a shipment or order, and check warranty and installation history. "
                "Ask about one of those, for example “Find a hydraulic pump for KFT-200” or “Where is SHP-0010?”.")


def _money(price: dict[str, Any] | None) -> str | None:
    if not price or price.get("state") != "AVAILABLE" or price.get("unit_price") is None:
        return None
    status = str(price.get("price_status") or "").lower().replace("_", " ")
    return f"{price['unit_price']:,.2f} {price.get('currency') or ''}".strip() + (f" ({status})" if status else "")


def _days(n: int | float) -> str:
    n = int(n)
    return f"{n} day" if n == 1 else f"{n} days"


# ── discovery ────────────────────────────────────────────────────────────────────────────────────
def discovery_lines(x: dict[str, Any], focus: list[str]) -> list[str]:
    d = x["decision"]
    facts, lines = d.get("facts") or {}, []
    part = x.get("recommended_part") or x.get("compatible_part")
    if x.get("clarification"):
        cl = x["clarification"]
        lines += [f"Needed: {m}" for m in d.get("missing", [])] + [f"Option: {o if isinstance(o, str) else o.get('label') or o.get('model') or o}" for o in (cl.get("options") or [])[:8]]
        return lines
    if part:
        lines.append(f"Part: {part['name']} ({part['part_number']}), {str(part.get('product_match_status') or '').replace('_', ' ').lower()}.")
        lines.append(f"Fitment: {str(part.get('fitment')).lower()} for {(x.get('machine') or {}).get('model') or 'this machine'}; approved source: {'yes' if part.get('approved_source') else 'no'}.")
        avail = next((a for a in x.get("availability", []) if a["part_id"] == part["part_id"]), None)
        if avail:
            qty = f", {avail['total_available']} units recorded" if avail.get("total_available") is not None else ""
            lines.append(f"Availability: {str(avail['state']).replace('_', ' ').lower()}{qty}.")
        price = _money(part.get("price"))
        if price:
            lines.append(f"Price: {price}.")
    for alt in (facts.get("alternatives") or [])[:3]:
        lines.append(f"Alternative: {alt.get('name') or alt.get('part_number') or alt.get('part_id')}.")
    if facts.get("canonical_type_mismatches"):
        lines.append(f"Not recommended: {', '.join(facts['canonical_type_mismatches'])} (matched only through alias text; their canonical product type is different).")
    if "explain" in focus:
        top = (x.get("ranking") or [{}])[0]
        lines += [f"Why: {ln}" for ln in (top.get("explanation") or {}).get("lines", [])]
        if top.get("total_score") is not None:
            lines.append(f"Ranking score {top['total_score']} from {', '.join(f'{k.replace('_score', '')} {v}' for k, v in (top.get('components') or {}).items() if v is not None)}.")
    elif d["decision"] in ("NO_AVAILABLE_RECOMMENDATION", "NO_VALID_RECOMMENDATION") and part:
        for r in (x.get("rejection_reasons") or {}).get(part["part_id"], [])[:2]:
            lines.append(f"Why not: {r['detail']}")
    return lines


# ── logistics ────────────────────────────────────────────────────────────────────────────────────
def logistics_lines(x: dict[str, Any], focus: list[str]) -> list[str]:
    d = x["decision"]
    facts, lines = d.get("facts") or {}, []
    if x.get("clarification"):
        cl = x["clarification"]
        for o in (cl.get("options") or [])[:8]:
            parts = ", ".join(f"{p['part_number']}" for p in o.get("parts", []) if p.get("part_number")) or o.get("part_number") or "part not recorded"
            lines.append(f"Option: shipment {o['shipment_id']} ({str(o.get('status') or '').lower()}), {o.get('line_count', 1)} order line(s): {parts}.")
        return lines
    s = x.get("shipment")
    if not s:
        return [f"Order {x['order']['order_id']}: status {x['order'].get('status')}."] if x.get("order") else []
    lines.append(f"Status: {str(x.get('current_status') or s.get('status')).replace('_', ' ').lower()} (shipment {s['shipment_id']}, recorded as {str(s.get('status')).lower()}).")
    sl = x.get("shipment_lines") or []
    if x.get("shipment_kind") == "MULTI_LINE":
        lines.append(f"This shipment carries {len(sl)} order lines with {len(x.get('parts') or [])} different part(s):")
    elif sl:
        lines.append("This shipment carries one order line:")
    for ln in sl:
        qty = f" × {ln['quantity']}" if ln.get("quantity") is not None else ""
        lines.append(f"  {ln['order_line_id']}: {ln.get('part_number') or 'part not recorded'}{(' ' + ln['name']) if ln.get('name') else ''}{qty}")
    if x.get("order_split"):
        others = [i for i in x.get("order_shipments", []) if i != s["shipment_id"]]
        lines.append(f"Order {s.get('order_id')} was split into {len(x['order_shipments'])} shipments; the others are {', '.join(others)}.")
    prog = x.get("route_progress")
    if prog:
        lines.append(f"Route {x['route']['route_id']} ({x['route'].get('transport_mode')}): {len(x.get('completed_legs') or [])} of {len(x.get('route_legs') or [])} legs completed.")
    eta = x.get("planned_eta") or {}
    if eta.get("planned_eta"):
        when = f", {_days(abs(eta['days_to_eta']))} {'ago' if eta['days_to_eta'] < 0 else 'to go'}" if eta.get("days_to_eta") is not None and not eta.get("delivered") else ""
        lines.append(f"{'Delivered' if eta.get('delivered') else 'Planned ETA'}: {eta.get('actual_eta') or eta['planned_eta']}{when}.")
    loc = x.get("current_location") or {}
    if loc.get("known") and loc.get("location"):
        lines.append(f"Last known place: {loc['location'].get('name')} ({loc.get('as_of')}).")
    elif loc and not loc.get("known"):
        lines.append(f"No live position: {loc.get('description') or 'the last event has no place'}.")
    if "faster" in focus or "why_slow" in focus:
        alts = [a for a in facts.get("alternatives", [])]
        if not x.get("route"):
            lines.append("A faster option cannot be named: the route of this shipment is not determinable from the records.")
        elif alts:
            for a in alts:
                dv = a.get("days_vs_current")
                rel = f"{_days(abs(dv))} {'faster' if dv < 0 else 'slower'}" if dv is not None and dv != 0 else "same time" if dv == 0 else "difference not recorded"
                lines.append(f"Recorded alternative: {a['route_id']} ({a['transport_mode']}), {a.get('planned_transit_days')} days, {a.get('estimated_cost')} {a.get('currency')}, {rel}.")
        else:
            lines.append("No other route is recorded between this shipment's origin and destination.")
    if "why_slow" in focus and x.get("route"):
        rem = x.get("remaining_legs") or []
        lines.append(f"{len(rem)} leg(s) remain" + (": " + ", ".join(f"{leg['transport_mode']} {_days(leg['planned_transit_days'])}" for leg in rem if leg.get("planned_transit_days") is not None) if rem else "") + ".")
    return lines


# ── warranty ─────────────────────────────────────────────────────────────────────────────────────
def warranty_lines(x: dict[str, Any], focus: list[str]) -> list[str]:
    d = x["decision"]
    facts, lines = d.get("facts") or {}, []
    if d["status"] == c.REQUIRES_CLARIFICATION:
        for o in options_of(x)[:8]:
            lines.append("Option: " + ", ".join(f"{k.replace('_', ' ')} {', '.join(v) if isinstance(v, list) else v}" for k, v in o.items() if v))
        return lines
    if facts.get("outcome"):
        lines.append(f"Decision: {facts['outcome'].replace('_', ' ').lower()}" + (f" (judged on {facts['reference_date']})" if facts.get("reference_date") else "") + ".")
    if x.get("coverage_start"):
        lines.append(f"Coverage: {x['coverage_start']} to {x['coverage_end']}.")
    failing = [f for f in x.get("decision_factors", []) if f.get("status") in ("FAIL", "UNKNOWN")]
    for f in failing:
        lines.append(f"{'Not met' if f['status'] == 'FAIL' else 'Unknown'}: {f['label']}. {f.get('detail') or ''}".strip())
    if not failing and x.get("decision_factors"):
        lines.append(f"All {len(x['decision_factors'])} warranty checks passed.")
    inst, dealer = x.get("installation"), x.get("dealer")
    if inst and ({"who_installed", "installed_correctly"} & set(focus) or True):
        by = f" by dealer {dealer['name']} ({str(dealer.get('authorized_status') or 'status not recorded').lower()})" if dealer else ""
        tech = x.get("technician")
        who = f", technician certification {tech['certification']}, {tech.get('specialization')}" if tech and tech.get("certification") else ""
        lines.append(f"Installed on {inst['installation_date']}{by}{who}; installation record {str(inst.get('validation_status') or 'not validated').lower()}"
                     + (f" ({', '.join(inst['validation_issues'])})" if inst.get("validation_issues") else "") + ".")
        if x.get("work_order"):
            lines.append(f"Work order {x['work_order']['work_order_id']} ({x['work_order'].get('service_type')}, {x['work_order'].get('service_date')}).")
        elif inst:
            lines.append("No work order is recorded for this installation.")
    if tech_hidden(x):
        lines.append("The technician's name is not shown to your role.")
    hist = x.get("replacement_history") or []
    lines.append(f"Replacement history: {len(hist)} recorded replacement(s)" + (": " + ", ".join(f"{h['replacement_id']} on {h['replacement_date']}" for h in hist) if hist else "") + ".")
    prior = x.get("prior_claims") or []
    if prior:
        lines.append("Earlier claims: " + ", ".join(f"{p['claim_id']} ({p['status']})" for p in prior) + ".")
    return lines


def options_of(x: dict[str, Any]) -> list[dict[str, Any]]:
    """What the asker may choose from: the context's clarification, else the options its decision lists."""
    return (x.get("clarification") or {}).get("options") or (x.get("decision") or {}).get("facts", {}).get("options") or []


def tech_hidden(x: dict[str, Any]) -> bool:
    return "technician.name" in (x.get("visibility") or {}).get("hidden_fields", [])


COMPOSERS = {DISCOVERY: discovery_lines, LOGISTICS: logistics_lines, WARRANTY: warranty_lines}


# ── the response ─────────────────────────────────────────────────────────────────────────────────
def _section(step: Any, focus: list[str]) -> dict[str, Any]:
    x = step.context
    if x is None:  # a step the agent itself closed (a question, or a journey with nothing to track)
        return {"domain": step.domain, "title": TITLES[step.domain], "status": step.status, "decision": step.decision, "headline": step.summary, "lines": [], "notes": step.resolution}
    return {"domain": step.domain, "title": TITLES[step.domain], "status": step.status, "decision": step.decision, "headline": step.summary,
            "lines": COMPOSERS[step.domain](x, focus), "notes": step.resolution}


def _flatten_evidence(steps: list[Any]) -> list[dict[str, Any]]:
    out = []
    for s in steps:
        for e in (s.context or {}).get("evidence", []):
            out.append({"domain": s.domain, **e})
    return out


def compose(u: Any, steps: list[Any], message: str, llm: Any = None) -> dict[str, Any]:
    sections = [_section(s, u.focus) for s in steps]
    contexts = {s.domain: s.context for s in steps if s.context is not None}
    records = c.dedupe_records([r for ctx in contexts.values() for r in ctx.get("source_records", [])])
    data_status = c.aggregate_data_status(records)
    asked = next((s for s in steps if s.status == c.REQUIRES_CLARIFICATION), None)
    clarification = None
    if asked is not None:
        cl = asked.clarification or (asked.context or {}).get("clarification") or {}
        clarification = {"domain": asked.domain, "question": cl.get("question") or asked.summary, "options": cl.get("options") or options_of(asked.context or {})}
    if u.intent == "UNKNOWN":
        status, lead = "OUT_OF_SCOPE", OUT_OF_SCOPE
    elif u.intent == "CLARIFICATION" and not steps:
        status, lead = c.REQUIRES_CLARIFICATION, "I can help find a part, track a shipment or check warranty. Which do you need, and for which machine, shipment or claim?"
        clarification = {"domain": None, "question": lead, "options": [{"domain": d} for d in ("DISCOVERY", "LOGISTICS", "WARRANTY")]}
    else:
        undecided = {s.status for s in steps} & c.UNDECIDED
        status = c.REQUIRES_CLARIFICATION if clarification else "PARTIAL" if undecided and len(steps) > 1 else "ANSWERED"
        lead = " ".join(s["headline"] for s in sections)
    evidence = _flatten_evidence(steps)
    notice = SYNTHETIC_NOTICE if "SYNTHETIC_DEMO" in {r.get("data_status") for r in records} else None
    text, grounding = lead, {"mode": "TEMPLATE", "validated": True}
    if llm is not None and steps and not clarification:
        text, grounding = _reword(llm, message, u.intent, lead, evidence, sections)
    return {"intent": u.intent, "status": status,
            "answer": {"text": text, "lead": lead, "sections": sections, "synthetic_notice": notice, "grounding": grounding},
            "steps": [{"domain": s.domain, "status": s.status, "decision": s.decision, "summary": s.summary, "resolution": s.resolution} for s in steps],
            "contexts": contexts, "clarification": clarification, "evidence": evidence,
            "evidence_paths": {d: ctx.get("evidence_path", []) for d, ctx in contexts.items()}, "source_records": records, "data_status": data_status,
            "confidence": {d: ctx.get("confidence") for d, ctx in contexts.items()}, "visibility": {d: ctx.get("visibility") for d, ctx in contexts.items()},
            "warnings": sorted({w for ctx in contexts.values() for w in ctx.get("warnings", [])}), "missing": sorted({m for ctx in contexts.values() for m in ctx.get("missing", [])})}


def _reword(llm: Any, message: str, intent: str, lead: str, evidence: list[dict[str, Any]], sections: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """The model may phrase the lead; it is kept only when every number and identifier in it is already in the evidence or the deterministic lead."""
    support = [{"domain": s["domain"], "facts": s["lines"][:12]} for s in sections] + [{"fact": e.get("fact"), "entity": e.get("entity"), "id": e.get("id")} for e in evidence[:12]]
    try:
        candidate = llm.generate_grounded_response(message, intent, support, lead)
    except LLMError as exc:
        log.info("commerce wording unavailable: %s", type(exc).__name__)
        return lead, {"mode": "TEMPLATE", "validated": True, "note": "language model unavailable"}
    if is_grounded(candidate, support, lead, message):
        return candidate, {"mode": "LLM", "validated": True}
    log.info("commerce wording rejected: not grounded in the evidence")
    return lead, {"mode": "TEMPLATE", "validated": True, "note": "model wording rejected (not grounded)"}
