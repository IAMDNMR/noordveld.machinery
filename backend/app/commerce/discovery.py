"""DiscoveryContext: "I need a hydraulic pump for my KFT-600" -> machine, candidate parts, fitment, approved source, availability, price, ranking, recommendation.

Pipeline (each step reads records; none guesses):
  request text -> entity extraction (machine identifier, part identifier, descriptive terms)
  -> candidate retrieval by the canonical discovery vocabulary (name, description, aliases, common_names, technical_terms, symptoms, subcategory)
  -> machine identification (an explicit model identifier or id only: a family, a type word or a near miss ASKS, it never resolves)
  -> fitment, approved-source and availability validation per candidate, every failed check kept as a rejection reason
  -> pricing -> deterministic ranking of the candidates that passed -> recommendation.

A candidate is never recommended unless fitment AND approved source AND availability hold. Rejected candidates are kept with their reasons.
Ranking is a weighted sum of five named components (WEIGHTS below, echoed in every result); the same records always give the same order, ties broken by part id.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.commerce import contract as c
from app.commerce.discovery_reader import DiscoveryReader
from app.lifecycle.rules import APPROVED, VERIFIED

# ── rejection reasons ────────────────────────────────────────────────────────────────────────────
NOT_APPROVED, DEPRECATED, NO_FITMENT, NO_APPROVED_SOURCE, OUT_OF_REGION, NOT_AVAILABLE, AVAILABILITY_UNKNOWN, WEAK_MATCH = (
    "NOT_APPROVED", "DEPRECATED", "NO_FITMENT", "NO_APPROVED_SOURCE", "OUT_OF_REGION", "NOT_AVAILABLE", "AVAILABILITY_UNKNOWN", "LOW_SEMANTIC_MATCH")
RECOMMEND, NO_VALID_RECOMMENDATION, CLARIFY = "RECOMMEND", "NO_VALID_RECOMMENDATION", "REQUIRES_CLARIFICATION"
DEPRECATED_PART_STATUSES = frozenset({"DEPRECATED", "OBSOLETE", "SUPERSEDED", "DISCONTINUED"})

# The ranking policy. Echoed in every result so the agent can show it; it is a rule, not a fact about any part.
WEIGHTS: dict[str, float] = {"fitment_score": 0.30, "semantic_match_score": 0.25, "approval_score": 0.20, "availability_score": 0.20, "regional_score": 0.05}
MAX_CANDIDATES = 25
STOPWORDS = frozenset("""i a an the need needs needed want wants looking look for my me our we to of on in with find get buy order please which what part parts spare spares replacement new fit fits fitting
fitted compatible that this do does you have can is are it and or some any one original genuine oem machine would like show give recommend suitable right correct how much cost price available stock
recorded as at from by be your am if im ive""".split())


def _words(text: str | None) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _flex(identifier: str) -> re.Pattern[str]:
    """'KFT-600' matches kft-600, KFT 600, kft600 and KFT_600; never inside a longer token."""
    groups = re.findall(r"[a-z]+|\d+", identifier.lower())
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-_/]?".join(re.escape(g) for g in groups) + r"(?![a-z0-9])")


def _hit(term: str, words: list[str]) -> bool:
    for w in words:
        if w == term:
            return True
        short, long_ = sorted((w, term), key=len)
        if len(short) >= 4 and long_.startswith(short) and len(short) / len(long_) >= 0.75:  # pump/pumps, hydraulic/hydraulics
            return True
    return False


# ── entity extraction ────────────────────────────────────────────────────────────────────────────
def resolve_machine(text: str, machines: list[dict[str, Any]], *, machine_id: str | None = None, instance_machine_id: str | None = None) -> tuple[dict[str, Any], str]:
    """(machine resolution, text with the machine mention removed). RESOLVED only from an id or an explicit model identifier."""
    by_id = {m["machine_id"]: m for m in machines}
    if machine_id:
        m = by_id.get(machine_id)
        return ({"resolution": "RESOLVED", "via": "machine_id", "machine": m, "options": [], "suggestions": []} if m
                else {"resolution": "NOT_FOUND", "via": "machine_id", "machine": None, "options": [], "suggestions": [], "detail": f"No machine {machine_id}."}), text
    if instance_machine_id:
        m = by_id.get(instance_machine_id)
        return ({"resolution": "RESOLVED", "via": "machine_instance", "machine": m, "options": [], "suggestions": []} if m
                else {"resolution": "NOT_FOUND", "via": "machine_instance", "machine": None, "options": [], "suggestions": [], "detail": "The machine model of this instance is not in the catalogue."}), text
    low = text.lower()
    found = {m["machine_id"]: m for m in machines if _flex(m["model"]).search(low)}
    if len(found) == 1:
        m = next(iter(found.values()))
        return {"resolution": "RESOLVED", "via": "model_identifier", "machine": m, "options": [], "suggestions": []}, _flex(m["model"]).sub(" ", low)
    if len(found) > 1:
        return {"resolution": "AMBIGUOUS", "via": "model_identifier", "machine": None, "options": _opts(found.values()), "suggestions": [], "detail": "More than one machine model is named."}, text
    words = set(_words(low))
    prefixes: dict[str, list[dict[str, Any]]] = {}
    for m in machines:
        prefixes.setdefault((re.match(r"[A-Za-z]+", m["model"]) or re.match(r"", "")).group(0).lower(), []).append(m)  # type: ignore[union-attr]
    family = [m for p, ms in prefixes.items() if p and p in words for m in ms]
    ident = [w for w in re.findall(r"(?<![a-z0-9])[a-z]{1,5}-?\d{2,5}(?![a-z0-9])", low)]
    digits = {re.sub(r"\D", "", i) for i in ident}
    near = [m for m in machines if digits and re.sub(r"\D", "", m["model"].split("-")[-1]) in digits]
    typed = [m for m in machines if words & {w for w in _words(f"{m['machine_type']} {m['name']}") if w not in STOPWORDS and len(w) >= 4 and not w.isdigit()}]
    if family:
        return {"resolution": "AMBIGUOUS", "via": "family", "machine": None, "options": _opts(family), "suggestions": [], "detail": "Only a machine family is named, not one model."}, text
    if ident:
        return {"resolution": "NOT_RESOLVED", "via": "unmatched_identifier", "machine": None, "options": [], "unmatched": sorted(set(ident)), "suggestions": _opts(near),
                "detail": "The machine identifier does not match any model in the catalogue."}, text
    if typed:
        return {"resolution": "AMBIGUOUS", "via": "machine_type_word", "machine": None, "options": _opts(typed), "suggestions": [], "detail": "A kind of machine is named, not one model."}, text
    return {"resolution": "NOT_STATED", "via": None, "machine": None, "options": [], "suggestions": [], "detail": "No machine is named."}, text


def _opts(machines: Any) -> list[dict[str, Any]]:
    return [{"machine_id": m["machine_id"], "model": m["model"], "name": m["name"]} for m in sorted(machines, key=lambda x: x["machine_id"])]


def extract_terms(text: str, parts: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """(descriptive terms, part identifiers found). Identifiers are part numbers and digit-bearing aliases (legacy numbers); they are looked up exactly."""
    low = text.lower()
    found: list[str] = []
    for p in parts:
        for ident in [p["part_number"], *[a for a in p["aliases"] if re.search(r"\d", a)]]:
            m = _flex(ident).search(low)
            if m:
                found.append(p["part_id"])
                low = low[:m.start()] + " " + low[m.end():]
                break
    terms: list[str] = []
    for w in _words(low):
        if w not in STOPWORDS and not w.isdigit() and len(w) > 1 and w not in terms:
            terms.append(w)
    return terms, sorted(set(found))


# ── retrieval ────────────────────────────────────────────────────────────────────────────────────
def semantic_match(part: dict[str, Any], terms: list[str], by_identifier: bool, reader: DiscoveryReader) -> dict[str, Any]:
    """How well the canonical vocabulary of one part covers the descriptive terms. Primary fields: name, technical terms, subcategory, category, part number.
    Secondary: common names, aliases, symptoms, description. Level HIGH = every term in a primary field; MEDIUM = every term, some only secondary; LOW = some terms."""
    if by_identifier and not terms:
        return {"level": "HIGH", "score": 1.0, "matched_terms": [], "unmatched_terms": [], "via": "IDENTIFIER", "fields": ["part_number_or_alias"]}
    primary = _words(" ".join([part["name"], " ".join(part["technical_terms"]), reader.category_name(part.get("subcategory_id")) or "", reader.category_name(part.get("category_id")) or "",
                               part["part_number"]]))
    secondary = _words(" ".join([" ".join(part["common_names"]), " ".join(part["aliases"]), " ".join(part["symptoms"]), part.get("description") or ""]))
    points, matched, fields = 0, [], set()
    for t in terms:
        if _hit(t, primary):
            points += 2
            matched.append(t)
            fields.add("primary")
        elif _hit(t, secondary):
            points += 1
            matched.append(t)
            fields.add("secondary")
    unmatched = [t for t in terms if t not in matched]
    if not terms:
        level = "NONE"
    elif not matched:
        level = "NONE"
    elif unmatched:
        level = "LOW"
    else:
        # every term is covered; primary-only coverage is HIGH, any term resting on secondary vocabulary alone is MEDIUM
        only_secondary = [t for t in matched if not _hit(t, primary)]
        level = "MEDIUM" if only_secondary else "HIGH"
    return {"level": level, "score": round(points / (2 * len(terms)), 4) if terms else 0.0, "matched_terms": matched, "unmatched_terms": unmatched,
            "via": "IDENTIFIER" if by_identifier else ("VOCABULARY_PRIMARY" if level == "HIGH" else "VOCABULARY_SECONDARY"), "fields": sorted(fields)}


# ── validation ───────────────────────────────────────────────────────────────────────────────────
def _within(row: dict[str, Any], today: date) -> bool:
    lo, hi = row.get("valid_from"), row.get("valid_to")
    return (not lo or date.fromisoformat(lo[:10]) <= today) and (not hi or today <= date.fromisoformat(hi[:10]))


def _expired(row: dict[str, Any], today: date) -> bool:
    return bool(row.get("valid_to")) and date.fromisoformat(row["valid_to"][:10]) < today


def validate_fitment(fitments: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """APPROVED only for a fitment record that is approved on both statuses and in force today. DEPRECATED, CONDITIONAL and absent are told apart."""
    good = [f for f in fitments if f["fitment_status"] == APPROVED and f["approval_status"] == APPROVED and _within(f, today)]
    if good:
        return {"state": "APPROVED", "fitment": good[0], "reason": None}
    if not fitments:
        return {"state": "NONE", "fitment": None, "reason": (NO_FITMENT, "No fitment record connects this part to this machine model.")}
    f = fitments[0]
    if "DEPRECATED" in (f["fitment_status"], f["approval_status"]) or _expired(f, today):
        return {"state": "DEPRECATED", "fitment": f, "reason": (DEPRECATED, f"The fitment record is {f['approval_status']} / expired ({f.get('valid_to')}).")}
    return {"state": f["approval_status"], "fitment": f, "reason": (NOT_APPROVED, f"The fitment is {f['approval_status']} ({f.get('fitment_rule') or 'rule not stated'}), not APPROVED.")}


def validate_sources(sources: list[dict[str, Any]], today: date, country: str | None, region: str | None) -> dict[str, Any]:
    """An approved source is APPROVED and in force; if the destination is known, it must also be approved for that country or region (an empty region list means no restriction)."""
    live = [s for s in sources if s["approval_status"] == APPROVED and _within(s, today)]
    if not sources or not live:
        why = "No approved source is recorded for this part." if not sources else "Sources exist but none is APPROVED and in force: " + ", ".join(sorted({s["approval_status"] for s in sources})) + "."
        return {"state": "NONE", "approved": [], "reason": (NO_APPROVED_SOURCE, why)}
    if country or region:
        regional = [s for s in live if not s["approved_regions"] or {r.upper() for r in s["approved_regions"]} & {x.upper() for x in (country, region) if x}]
        if not regional:
            return {"state": "OUT_OF_REGION", "approved": [], "reason": (OUT_OF_REGION, f"No approved source covers {country or region}.")}
        live = regional
    return {"state": "APPROVED", "approved": live, "reason": None}


def validate_availability(rows: list[dict[str, Any]], locations: dict[str, dict[str, Any]], region: str | None) -> dict[str, Any]:
    known = [r for r in rows if r["available_quantity"] is not None]
    in_stock = [r for r in known if r["available_quantity"] > 0]
    unknown = [r for r in rows if r["available_quantity"] is None or r["status"] == "UNKNOWN"]
    total = sum(r["available_quantity"] for r in in_stock)
    if in_stock:
        state = "AVAILABLE"
    elif unknown:
        state = "UNKNOWN"
    else:
        state = "NOT_AVAILABLE"
    in_region = [r for r in in_stock if region and (locations.get(r["location_id"]) or {}).get("region") == region]
    return {"state": state, "total_available": total if in_stock else (None if state == "UNKNOWN" else 0), "low_stock_only": bool(in_stock) and all(r["status"] == "LOW_STOCK" for r in in_stock),
            "in_destination_region": (bool(in_region) if region and state == "AVAILABLE" else None), "warehouses": [{"location_id": r["location_id"], "available_quantity": r["available_quantity"], "status": r["status"]} for r in rows],
            "reason": None if state == "AVAILABLE" else (AVAILABILITY_UNKNOWN, "Stock is recorded as unknown, which is not read as available.") if state == "UNKNOWN"
            else (NOT_AVAILABLE, "No warehouse has stock: " + ", ".join(sorted({r["status"] for r in rows})) + "." if rows else "No inventory record exists for this part.")}


def select_price(prices: list[dict[str, Any]], today: date, region: str | None) -> dict[str, Any]:
    live = [p for p in prices if _within(p, today) and (not p.get("region") or p["region"] == region)]
    if not live:
        return {"state": "NOT_AVAILABLE", "price": None, "alternatives": 0}
    best = sorted(live, key=lambda p: (0 if p.get("region") else 1, p.get("valid_from") or "", p["price_id"]))[0] if len(live) == 1 else \
        sorted(live, key=lambda p: (0 if p.get("region") else 1, -int((p.get("valid_from") or "0000-00-00").replace("-", "")), p["price_id"]))[0]
    return {"state": "AVAILABLE", "price": best, "alternatives": len(live) - 1}


def _status_checks(part: dict[str, Any]) -> tuple[str, str] | None:
    s = part.get("status")
    if s in DEPRECATED_PART_STATUSES:
        return DEPRECATED, f"The part's catalogue status is {s}."
    if s != VERIFIED:
        return NOT_APPROVED, f"The part's catalogue status is {s}, not {VERIFIED}."
    return None


# ── context ──────────────────────────────────────────────────────────────────────────────────────
@dataclass(kw_only=True)
class DiscoveryContext(c.CommerceContext):
    user_request: str
    machine: dict[str, Any]
    candidate_parts: list[dict[str, Any]] = field(default_factory=list)
    fitment_results: list[dict[str, Any]] = field(default_factory=list)
    approved_sources: list[dict[str, Any]] = field(default_factory=list)
    availability: list[dict[str, Any]] = field(default_factory=list)
    pricing: list[dict[str, Any]] = field(default_factory=list)
    recommended_part: dict[str, Any] | None = None
    ranking: list[dict[str, Any]] = field(default_factory=list)
    rejection_reasons: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    scoring: dict[str, Any] = field(default_factory=dict)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    extracted: dict[str, Any] = field(default_factory=dict)
    clarification: dict[str, Any] | None = None


class DiscoveryContextBuilder:
    def __init__(self, reader: DiscoveryReader, as_of: date, generated_at: str) -> None:
        self.r = reader
        self.as_of = as_of
        self.generated_at = generated_at
        self.partial_matches_set_aside = 0

    def build(self, request: str, *, machine_id: str | None = None, instance_machine_id: str | None = None, destination_country: str | None = None,
              customer_country: str | None = None) -> DiscoveryContext:
        r = self.r
        parts = r.parts()
        machine, remaining = resolve_machine(request, r.machines(), machine_id=machine_id, instance_machine_id=instance_machine_id)
        terms, identifiers = extract_terms(remaining, parts)
        country = (destination_country or customer_country or None)
        country = country.upper() if country else None
        region = r.region_of_country(country)
        extracted = {"terms": terms, "part_identifiers": identifiers, "destination_country": country, "destination_region": region, "machine_resolution": machine["resolution"]}
        inputs = {"request": request, "machine_id": machine_id, "instance_machine_id": instance_machine_id, "country": country}

        candidates = self._retrieve(parts, terms, identifiers)
        extracted["partial_matches_set_aside"] = self.partial_matches_set_aside
        truncated = len(candidates) > MAX_CANDIDATES
        candidates = candidates[:MAX_CANDIDATES]

        if not terms and not identifiers:
            return self._clarify(inputs, request, machine, extracted, [], "part_unspecified", "Which part do you need? Describe it (for example 'hydraulic pump') or give its part number.")
        if machine["resolution"] == "NOT_FOUND":
            return self._finish(inputs, request, machine, extracted, candidates, validated=False, truncated=truncated, status=c.NOT_FOUND, decision=NO_VALID_RECOMMENDATION,
                                summary=machine.get("detail") or "The machine is not in the catalogue.", reasons=[machine.get("detail", "")], next_action="Check the machine id or model and ask again.")
        if machine["resolution"] != "RESOLVED":
            return self._clarify(inputs, request, machine, extracted, candidates, "machine_unresolved", "Which machine model do you mean?")
        return self._validate_and_rank(inputs, request, machine, extracted, candidates, truncated, region, country)

    # retrieval: every part whose vocabulary covers at least one term, plus identifier hits
    def _retrieve(self, parts: list[dict[str, Any]], terms: list[str], identifiers: list[str]) -> list[dict[str, Any]]:
        out = []
        for p in parts:
            sm = semantic_match(p, terms, p["part_id"] in identifiers, self.r)
            if sm["level"] != "NONE":
                out.append({"part": p, "semantic": sm})
        # a part that covers every term (HIGH / MEDIUM) is a candidate; partial matches (LOW) only stand in when nothing covers the whole request. The count is reported, not hidden.
        full = [x for x in out if x["semantic"]["level"] in ("HIGH", "MEDIUM")]
        kept = full or out
        self.partial_matches_set_aside = len(out) - len(kept)
        return sorted(kept, key=lambda x: (-x["semantic"]["score"], x["part"]["part_id"]))

    def _validate_and_rank(self, inputs, request, machine, extracted, candidates, truncated, region, country) -> DiscoveryContext:
        r, today = self.r, self.as_of
        mid = machine["machine"]["machine_id"]
        locations = {loc["location_id"]: loc for loc in (r.location(x["location_id"]) for cand in candidates for x in r.inventory(cand["part"]["part_id"])) if loc}
        records: list[dict[str, Any]] = [c.record("Machine", mid, machine["machine"])]
        results = []
        for cand in candidates:
            p = cand["part"]
            pid = p["part_id"]
            fit = validate_fitment(r.fitments(mid, pid), today)
            src = validate_sources(r.approved_sources(pid), today, country, region)
            avail = validate_availability(r.inventory(pid), locations, region)
            price = select_price(r.prices(pid), today, region)
            reasons: list[dict[str, Any]] = []
            status_reason = _status_checks(p)
            if status_reason:
                reasons.append({"code": status_reason[0], "detail": status_reason[1], "source": {"entity": "Part", "id": pid}})
            if fit["reason"]:
                reasons.append({"code": fit["reason"][0], "detail": fit["reason"][1], "source": {"entity": "Fitment", "id": fit["fitment"]["fitment_id"] if fit["fitment"] else None, "machine_id": mid, "part_id": pid}})
            if src["reason"]:
                srcs = r.approved_sources(pid)
                reasons.append({"code": src["reason"][0], "detail": src["reason"][1], "source": {"entity": "ApprovedSource", "id": srcs[0]["approved_source_id"] if srcs else None, "ids": [x["approved_source_id"] for x in srcs],
                                                                                              "part_id": pid, "basis": "RECORDS" if srcs else "ABSENCE_OF_RECORD"}})
            if avail["reason"]:
                inv = r.inventory(pid)
                reasons.append({"code": avail["reason"][0], "detail": avail["reason"][1], "source": {"entity": "Inventory", "id": inv[0]["inventory_id"] if inv else None, "ids": [x["inventory_id"] for x in inv],
                                                                                              "part_id": pid, "basis": "RECORDS" if inv else "ABSENCE_OF_RECORD"}})
            if cand["semantic"]["level"] == "LOW":
                reasons.append({"code": WEAK_MATCH, "detail": "Only " + ", ".join(cand["semantic"]["matched_terms"]) + " of the request is covered; missing " + ", ".join(cand["semantic"]["unmatched_terms"]) + ".",
                                "source": {"entity": "Part", "id": pid}})
            comps = {"fitment_score": 1.0 if fit["state"] == "APPROVED" else 0.0,
                     "approval_score": 1.0 if (not status_reason and src["state"] == "APPROVED") else 0.0,
                     "availability_score": 0.0 if avail["state"] != "AVAILABLE" else (0.5 if avail["low_stock_only"] else 1.0),
                     "semantic_match_score": cand["semantic"]["score"],
                     "regional_score": None if avail["in_destination_region"] is None else (1.0 if avail["in_destination_region"] else 0.0)}
            used = {k: v for k, v in comps.items() if v is not None}
            total = round(sum(WEIGHTS[k] * v for k, v in used.items()) / sum(WEIGHTS[k] for k in used), 4)
            results.append({"part": p, "semantic": cand["semantic"], "fit": fit, "src": src, "avail": avail, "price": price, "reasons": reasons, "components": comps, "total": total})
        return self._assemble(inputs, request, machine, extracted, results, truncated, region, country, records)

    # ── output ───────────────────────────────────────────────────────────────────────────────────
    def _assemble(self, inputs, request, machine, extracted, results, truncated, region, country, records) -> DiscoveryContext:
        r = self.r
        mid = machine["machine"]["machine_id"]
        valid = sorted((x for x in results if not x["reasons"]), key=lambda x: (-x["total"], x["part"]["part_id"]))
        rejected = [x for x in results if x["reasons"]]
        evidence: list[dict[str, Any]] = [c.evidence_item(f"machine {machine['machine']['model']} resolved via {machine['via']}", "Machine", mid, machine["machine"])]
        warnings: list[str] = []
        missing: list[str] = []
        if truncated:
            warnings.append(f"More than {c_max()} parts matched; only the best {c_max()} by vocabulary match were validated.")
        if not (region or country):
            warnings.append("No destination country is known, so regional approval of sources and the regional ranking component were not applied.")
        ranking = []
        for i, x in enumerate(valid, 1):
            ranking.append({"rank": i, "part_id": x["part"]["part_id"], "part_number": x["part"]["part_number"], "total_score": x["total"], "components": x["components"],
                            "explanation": self._explain(x), "outranked_by_top": None if i == 1 else self._compare(valid[0], x)})
        for x in results:
            pid = x["part"]["part_id"]
            records += [c.record("Part", pid, x["part"])]
            if x["fit"]["fitment"]:
                records.append(c.record("Fitment", x["fit"]["fitment"]["fitment_id"], x["fit"]["fitment"]))
            records += [c.record("ApprovedSource", s["approved_source_id"], s) for s in x["src"]["approved"]]
            records += [c.record("Inventory", i["inventory_id"], i) for i in r.inventory(pid)]
            if x["price"]["price"]:
                records.append(c.record("Price", x["price"]["price"]["price_id"], x["price"]["price"]))
        top = valid[0] if valid else None
        path: list[dict[str, Any]] = []
        if top:
            pid, fit, src = top["part"]["part_id"], top["fit"]["fitment"], top["src"]["approved"][0]
            inv = next(i for i in r.inventory(pid) if (i["available_quantity"] or 0) > 0)
            path = [c.path_step(1, "Part", pid, "FITS", top["part"]), c.path_step(2, "Fitment", fit["fitment_id"], "SUPPLIED_BY", fit),
                    c.path_step(3, "ApprovedSource", src["approved_source_id"], "AVAILABLE_AT", src), c.path_step(4, "Inventory", inv["inventory_id"], "PRICES_PART" if top["price"]["price"] else None, inv)]
            if top["price"]["price"]:
                path.append(c.path_step(5, "Price", top["price"]["price"]["price_id"], None, top["price"]["price"]))
            evidence += [c.evidence_item(f"{pid} fitment {fit['approval_status']} for {mid} ({fit['fitment_rule']})", "Fitment", fit["fitment_id"], fit),
                         c.evidence_item(f"{pid} has {len(top['src']['approved'])} approved source(s)", "ApprovedSource", src["approved_source_id"], src),
                         c.evidence_item(f"{pid} available: {top['avail']['total_available']} in stock", "Inventory", inv["inventory_id"], inv)]
            if top["price"]["price"]:
                evidence.append(c.evidence_item(f"{pid} list price {top['price']['price']['unit_price']} {top['price']['price']['currency']}", "Price", top["price"]["price"]["price_id"], top["price"]["price"]))
            else:
                missing.append(f"price:{pid}")
            if top["avail"]["in_destination_region"] is False:
                warnings.append(f"{pid} has stock, but not in the destination region {region}.")
            if top["semantic"]["level"] == "MEDIUM":
                warnings.append(f"{pid} matches the request through secondary vocabulary only ({', '.join(top['semantic']['fields'])}: {', '.join(top['semantic']['matched_terms'])}); check that it is the part meant.")
            if top["price"]["alternatives"]:
                warnings.append(f"{pid} has {top['price']['alternatives']} other valid price record(s); the most specific, most recent one is shown.")
        for x in rejected:
            for rs in x["reasons"]:
                evidence.append(c.evidence_item(f"{x['part']['part_id']} rejected: {rs['code']} - {rs['detail']}", rs["source"]["entity"], rs["source"].get("id") or x["part"]["part_id"]))
        for x in results:
            if x["avail"]["state"] == "UNKNOWN":
                missing.append(f"availability:{x['part']['part_id']}")

        recommended = None
        if top:
            recommended = {"part_id": top["part"]["part_id"], "part_number": top["part"]["part_number"], "name": top["part"]["name"], "total_score": top["total"], "fitment": top["fit"]["state"],
                           "approved_source": True, "availability": top["avail"]["state"], "semantic_match": top["semantic"]["level"], "price": self._price_view(top["price"]), "explanation": ranking[0]["explanation"]}
            decision = c.CommerceDecision(
                status=c.SUCCESS, decision=RECOMMEND, summary=f"{top['part']['name']} ({top['part']['part_number']}) fits {machine['machine']['model']} with an approved source and is available.",
                facts={"part_id": top["part"]["part_id"], "fitment": top["fit"]["state"], "approved_source": True, "availability": top["avail"]["state"] == "AVAILABLE", "semantic_match": top["semantic"]["level"],
                       "unit_price": self._price_view(top["price"]), "valid_candidates": len(valid), "rejected_candidates": len(rejected)},
                reasons=ranking[0]["explanation"]["lines"], missing=missing, warnings=warnings,
                recommended_next_action="Present the recommendation with its evidence; add to cart only after the user confirms.")
        else:
            otherwise_valid = [x for x in rejected if {rs["code"] for rs in x["reasons"]} == {NOT_AVAILABLE}]
            why = sorted({rs["code"] for x in rejected for rs in x["reasons"]})
            decision = c.CommerceDecision(
                status=c.NOT_FOUND, decision=NO_VALID_RECOMMENDATION,
                summary=("No candidate passed fitment, approved-source and availability validation for " + machine["machine"]["model"] + "." if results else "No part in the catalogue matches the request."),
                facts={"valid_candidates": 0, "rejected_candidates": len(rejected), "rejection_codes": why, "fits_but_not_available": [x["part"]["part_id"] for x in otherwise_valid]},
                reasons=[f"{x['part']['part_id']}: " + "; ".join(f"{rs['code']} ({rs['detail']})" for rs in x["reasons"]) for x in rejected], missing=missing, warnings=warnings,
                recommended_next_action=("Tell the user which candidates were rejected and why; offer to look for the same part at another time or a different machine." if results else "Ask the user to describe the part differently."))
        cand_view = [self._candidate_view(x, valid) for x in results]
        return DiscoveryContext(
            **c.meta("DISCOVERY", inputs, self.as_of.isoformat(), self.generated_at, decision, records, evidence, path), user_request=request, machine=self._machine_view(machine), candidate_parts=cand_view,
            fitment_results=[{"part_id": x["part"]["part_id"], "state": x["fit"]["state"], "fitment_id": (x["fit"]["fitment"] or {}).get("fitment_id"), "fitment_rule": (x["fit"]["fitment"] or {}).get("fitment_rule"),
                              "machine_id": mid} for x in results],
            approved_sources=[{"part_id": x["part"]["part_id"], "state": x["src"]["state"], "has_approved_source": x["src"]["state"] == "APPROVED",
                               "sources": [{"approved_source_id": s["approved_source_id"], "source_id": s["source_id"], "source_kind": s["source_kind"], "approved_regions": s["approved_regions"]} for s in x["src"]["approved"]]}
                              for x in results],
            availability=[{"part_id": x["part"]["part_id"], **{k: v for k, v in x["avail"].items() if k != "reason"}} for x in results],
            pricing=[{"part_id": x["part"]["part_id"], **self._price_view(x["price"])} for x in results], recommended_part=recommended, ranking=ranking,
            rejection_reasons={x["part"]["part_id"]: x["reasons"] for x in sorted(rejected, key=lambda y: y["part"]["part_id"])}, scoring={"weights": WEIGHTS, "rule": "weighted mean of the components that apply; ties by part id"},
            provenance=c.dedupe_records(records), extracted=extracted)

    @staticmethod
    def _price_view(price: dict[str, Any]) -> dict[str, Any]:
        p = price["price"]
        return {"state": price["state"], "unit_price": p["unit_price"] if p else None, "currency": p["currency"] if p else None, "price_id": p["price_id"] if p else None, "price_status": p.get("status") if p else None}

    @staticmethod
    def _machine_view(machine: dict[str, Any]) -> dict[str, Any]:
        m = machine["machine"]
        return {"resolution": machine["resolution"], "via": machine["via"], "machine_id": m["machine_id"] if m else None, "model": m["model"] if m else None, "name": m["name"] if m else None,
                "machine_type": m["machine_type"] if m else None, "options": machine["options"], "suggestions": machine["suggestions"], "unmatched_identifiers": machine.get("unmatched", []), "detail": machine.get("detail")}

    @staticmethod
    def _explain(x: dict[str, Any]) -> dict[str, Any]:
        lines = [f"fitment = {x['fit']['state']}", "approved_source = YES", f"availability = {x['avail']['state']}", f"semantic_match = {x['semantic']['level']}"]
        reg = x["components"]["regional_score"]
        if reg is not None:
            lines.append("regional = " + ("IN_DESTINATION_REGION" if reg == 1.0 else "OUTSIDE_DESTINATION_REGION"))
        return {"fitment": x["fit"]["state"], "approved_source": "YES", "availability": x["avail"]["state"], "semantic_match": x["semantic"]["level"], "lines": lines}

    @staticmethod
    def _compare(top: dict[str, Any], other: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"component": k, "top": top["components"][k], "this": other["components"][k]} for k in WEIGHTS if top["components"][k] != other["components"][k]]

    @staticmethod
    def _candidate_view(x: dict[str, Any], valid: list[dict[str, Any]]) -> dict[str, Any]:
        p = x["part"]
        return {"part_id": p["part_id"], "part_number": p["part_number"], "name": p["name"], "catalogue_status": p.get("status"), "semantic_match": x["semantic"], "components": x["components"], "total_score": x["total"],
                "validation": "VALID" if not x["reasons"] else "REJECTED", "rank": valid.index(x) + 1 if x in valid else None, "rejection_codes": [rs["code"] for rs in x["reasons"]]}

    def _clarify(self, inputs, request, machine, extracted, candidates, kind: str, question: str) -> DiscoveryContext:
        records = [c.record("Part", x["part"]["part_id"], x["part"]) for x in candidates]
        options = machine["options"] or machine["suggestions"]
        decision = c.CommerceDecision(
            status=c.REQUIRES_CLARIFICATION, decision=CLARIFY, summary=question, facts={"reason": kind, "machine_resolution": machine["resolution"], "machine_options": machine["options"],
                                                                                    "machine_suggestions": machine["suggestions"], "candidate_part_ids": [x["part"]["part_id"] for x in candidates]},
            reasons=[machine.get("detail") or "The request does not say enough."], missing=["machine" if kind == "machine_unresolved" else "part"], warnings=(["The candidate parts below are NOT validated against any machine."] if candidates else []),
            recommended_next_action="Ask the user: " + question + (" Options: " + ", ".join(o["model"] for o in options) if options else ""))
        view = [{"part_id": x["part"]["part_id"], "part_number": x["part"]["part_number"], "name": x["part"]["name"], "catalogue_status": x["part"].get("status"), "semantic_match": x["semantic"],
                 "validation": "NOT_VALIDATED", "rank": None, "rejection_codes": []} for x in candidates]
        return DiscoveryContext(**c.meta("DISCOVERY", inputs, self.as_of.isoformat(), self.generated_at, decision, records, [], []), user_request=request, machine=self._machine_view(machine),
                                candidate_parts=view, scoring={"weights": WEIGHTS}, provenance=c.dedupe_records(records), extracted=extracted,
                                clarification={"question": question, "kind": kind, "options": options})

    def _finish(self, inputs, request, machine, extracted, candidates, *, validated, truncated, status, decision, summary, reasons, next_action) -> DiscoveryContext:
        d = c.CommerceDecision(status=status, decision=decision, summary=summary, reasons=reasons, facts={"machine_resolution": machine["resolution"]}, missing=["machine"], recommended_next_action=next_action)
        return DiscoveryContext(**c.meta("DISCOVERY", inputs, self.as_of.isoformat(), self.generated_at, d, [], [], []), user_request=request, machine=self._machine_view(machine), scoring={"weights": WEIGHTS},
                                extracted=extracted)


def c_max() -> int:
    return MAX_CANDIDATES
