"""Intent execution. One function per intent: run the intent's fixed queries, shape the rows, record the evidence.

The summary written here is deterministic. It is the answer when no language model is available, and the reference a
model-written summary is checked against.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import quote

from app.graph.repositories.intelligence import IntelligenceRepository
from app.graph.repositories.parts import PartRepository
from app.intelligence.models import Intent, Kind, Outcome, Resolved
from app.intelligence.provenance import LABELS, data_class
from app.schemas.intelligence import Action, Evidence, Fact, FactGroup, ResultItem
from app.services.part_status import status_label
from app.services.parts import to_summary

INTELLIGENCE_ROUTE = "/parts-intelligence"
NOT_ESTABLISHED = "Not established"


@dataclass
class Context:
    question: str
    text: str
    limit: int
    repo: IntelligenceRepository
    parts: PartRepository
    entities: dict[Kind, Resolved] = field(default_factory=dict)
    extra: dict = field(default_factory=dict)  # intent-specific inputs prepared by the service (path ends, place)

    def need(self, kind: Kind) -> Resolved:
        return self.entities[kind]


def humanize(value: str | None) -> str | None:
    if not value:
        return None
    text = value.replace("_", " ").lower()
    return text[0].upper() + text[1:]


def place(city: str | None, country: str | None) -> str | None:
    return ", ".join(x for x in (city, country) if x) or None


def yes_no(value: bool | None) -> str | None:
    return None if value is None else ("Yes" if value else "No")


def ev(entity: str, kind: str, rel: str, target: str, target_kind: str, status: str | None) -> Evidence:
    return Evidence(entity=entity, entity_kind=kind, relationship=rel, target=target, target_kind=target_kind, data_class=data_class(status))


def investigate_action(part_number: str) -> Action:
    return Action(kind="investigate", label=f"Investigate {part_number}", href=f"{INTELLIGENCE_ROUTE}?part={quote(part_number)}")


def part_item(row: dict, *, relationship: str | None = None, facts: list[Fact] | None = None, groups: list[FactGroup] | None = None) -> ResultItem:
    return ResultItem(
        kind="part", key=row["part_id"], title=row["part_number"], subtitle=row["name"], part_number=row["part_number"], relationship=relationship,
        data_class=data_class(row.get("data_status")), facts=facts or [Fact(label="Category", value=row.get("category"))], groups=groups or [],
    )


def _count(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


# ── part → … ────────────────────────────────────────────────────────────────────────────────────
def part_to_machine(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    rows = c.repo.fitment(part.id)
    results = [
        ResultItem(
            kind="machine", key=r["machine_id"], title=r["model_code"], subtitle=r["name"], relationship="FITS", data_class=data_class(r["data_status"]),
            facts=[Fact(label="Machine type", value=r["machine_type"]), Fact(label="Family", value=r["family"]), Fact(label="Fitment", value=humanize(r["fitment_status"])),
                   *([Fact(label="Condition", value=r["condition_note"])] if r["condition_note"] else [])],
        )
        for r in rows
    ]
    evidence = [ev(part.label, "PART", "FITS", r["model_code"], "MACHINE", r["data_status"]) for r in rows]
    summary = (
        f"{part.label} is associated with {_count(len(rows), 'machine')} in the current graph: {', '.join(r['model_code'] for r in rows[:8])}."
        if rows else f"No fitment is recorded for {part.label} in the graph."
    )
    machine = c.entities.get(Kind.MACHINE)
    if machine is not None and machine.tier < 2:  # "does X fit Y?" with Y named exactly: answer for that pair only
        keep = [i for i, r in enumerate(rows) if r["machine_id"] == machine.id]
        results, evidence = [results[i] for i in keep], [evidence[i] for i in keep]
        if keep:
            r = rows[keep[0]]
            summary = f"Yes: {part.label} is recorded as fitting {machine.label} (fitment: {(humanize(r['fitment_status']) or 'status not stated').lower()})."
        else:
            others = f" It is recorded for {', '.join(r['model_code'] for r in rows[:8])}." if rows else ""
            summary = f"No fitment between {part.label} and {machine.label} is recorded in the graph, so it is not established that it fits.{others}"
        return Outcome(summary, results, evidence, ["Part", "FITS", "Machine"], len(results), actions=[investigate_action(part.label)])
    return Outcome(summary, results, evidence, ["Part", "FITS", "Machine"], len(rows), actions=[investigate_action(part.label)])


def machine_to_part(c: Context) -> Outcome:
    machine = c.need(Kind.MACHINE)
    category = c.entities.get(Kind.CATEGORY)
    total, rows = c.repo.machine_parts(machine.id, category.label if category else None, c.limit)
    results = [
        part_item(r, relationship="FITS", facts=[Fact(label="Category", value=r["category"]), Fact(label="Fitment", value=humanize(r["fitment_status"])),
                                                 *([Fact(label="Condition", value=r["condition_note"])] if r["condition_note"] else [])])
        for r in rows
    ]
    evidence = [ev(r["part_number"], "PART", "FITS", machine.label, "MACHINE", r["data_status"]) for r in rows]
    scope = f" in {category.label}" if category else ""
    summary = f"{machine.label} is associated with {_count(total, 'part')}{scope} in the current graph." if total else f"No parts are recorded as fitting {machine.label}{scope} in the graph."
    return Outcome(summary, results, evidence, ["Part", "FITS", "Machine"], total)


def part_to_category(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    row = c.repo.category(part.id)
    if not row.get("category"):
        return Outcome(f"No category is recorded for {part.label}.", path=["Part", "IN_CATEGORY", "Category"], actions=[investigate_action(part.label)])
    item = ResultItem(kind="category", key=row["category_id"] or row["category"], title=row["category"], subtitle="Category", relationship="IN_CATEGORY",
                      data_class=data_class(row["data_status"]), facts=[Fact(label="Subcategory", value=row["subcategory"])])
    sub = f" ({row['subcategory']})" if row["subcategory"] else ""
    return Outcome(f"{part.label} is in the {row['category']} category{sub}.", [item], [ev(part.label, "PART", "IN_CATEGORY", row["category"], "CATEGORY", row["data_status"])],
                   ["Part", "IN_CATEGORY", "Category"], 1, actions=[investigate_action(part.label)])


def part_to_assembly(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    rows = c.repo.assemblies(part.id)
    results = [
        ResultItem(
            kind="assembly", key=r["assembly_id"], title=r["name"] or r["assembly_id"], subtitle="Assembly", relationship="PART_OF", data_class=data_class(r["data_status"]),
            facts=[Fact(label="Quantity in assembly", value=None if r["quantity"] is None else str(r["quantity"])), Fact(label="BOM status", value=humanize(r["bom_status"])),
                   Fact(label="Components", value=str(r["component_count"])), Fact(label="Identified by part", value=r["identified_by"])],
            groups=[FactGroup(label="Other components", values=[f"{x['part_number']} · {x['name']}" for x in r["components"][:6]])] if r["components"] else [],
        )
        for r in rows
    ]
    evidence = [ev(part.label, "PART", "PART_OF", r["name"] or r["assembly_id"], "ASSEMBLY", r["data_status"]) for r in rows]
    summary = (f"{part.label} is part of {_count(len(rows), 'assembly', 'assemblies')}: {', '.join(r['name'] or r['assembly_id'] for r in rows)}."
               if rows else f"No assembly relationship is recorded for {part.label} in the graph.")
    return Outcome(summary, results, evidence, ["Part", "PART_OF", "Assembly"], len(rows), actions=[investigate_action(part.label)])


def assembly_to_part(c: Context) -> Outcome:
    assembly = c.need(Kind.ASSEMBLY)
    core = c.repo.assembly_core(assembly.id)
    total, rows = c.repo.assembly_parts(assembly.id, c.limit)
    results = [part_item(r, relationship="PART_OF", facts=[Fact(label="Category", value=r["category"]), Fact(label="Quantity in assembly", value=None if r["quantity"] is None else str(r["quantity"]))]) for r in rows]
    evidence = [ev(r["part_number"], "PART", "PART_OF", assembly.label, "ASSEMBLY", r["data_status"]) for r in rows]
    bom = humanize(core["assembly"]["bom_status"]) if core else None
    note = f" (BOM status: {bom})" if bom else ""
    summary = f"{assembly.label} has {_count(total, 'part')} connected in the graph{note}." if total else f"No parts are connected to {assembly.label} in the graph."
    return Outcome(summary, results, evidence, ["Part", "PART_OF", "Assembly"], total)


_RELATION_LABEL = {
    "CO_ORDERED_WITH": "Often ordered together",
    "RELATED_COMPONENT": "Related component",
    "SAME_NAME_GROUP_AS": "Shares a part name",
}


def part_to_part(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    rows = c.repo.related(part.id)
    results = [
        part_item({**r, "data_status": r["data_status"]}, relationship=r["relation"],
                  facts=[Fact(label="Relationship", value=_RELATION_LABEL.get(r["relation"], humanize(r["relation"]))), Fact(label="Category", value=r["category"]),
                         Fact(label="Interchangeability", value=NOT_ESTABLISHED if r["interchangeability_status"] in (None, "UNKNOWN") else humanize(r["interchangeability_status"]))])
        for r in rows
    ]
    evidence = [ev(part.label, "PART", r["relation"], r["part_number"], "PART", r["data_status"]) for r in rows]
    stated = any(r["interchangeability_status"] not in (None, "UNKNOWN") for r in rows)
    warnings = []
    if any(w in c.question.lower() for w in ("alternative", "replace", "interchang", "equivalent", "substitut")):
        warnings.append("The graph does not establish alternatives, replacements or interchangeability. Only the explicit relationships below are shown.")
    summary = (f"{part.label} is linked to {_count(len(rows), 'part')} by explicit graph relationships."
               + ("" if stated else " None of these links states that the parts are interchangeable.") if rows
               else f"No related-part relationships are recorded for {part.label} in the graph.")
    other = c.extra.get("other_part")
    if other is not None:  # "is X interchangeable with Y?": answer about that pair only, from the stored links
        rows = [r for r in rows if r["part_number"] == other.label]
        results = [i for i in results if i.title == other.label]
        evidence = [e for e in evidence if e.target == other.label]
        if rows:
            kinds = ", ".join(sorted({_RELATION_LABEL.get(r["relation"], humanize(r["relation"])) or r["relation"] for r in rows})).lower()
            summary = f"{part.label} and {other.label} are linked in the graph ({kinds}). That link does not establish that they are interchangeable."
        else:
            summary = f"No graph relationship links {part.label} and {other.label}, so the graph does not establish that they are interchangeable, alternatives or replacements."
        warnings = ["The graph does not establish alternatives, replacements or interchangeability. Only the explicit relationships below are shown."]
    return Outcome(summary, results, evidence, ["Part", "RELATED_COMPONENT | CO_ORDERED_WITH | SAME_NAME_GROUP_AS", "Part"], len(rows), warnings, [investigate_action(part.label)])


def part_to_supplier(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    rows = c.repo.suppliers(part.id)
    results = [
        ResultItem(
            kind="supplier", key=r["supplier_id"], title=r["name"] or r["supplier_id"], subtitle=place(r["city"], r["country_code"]), relationship="SUPPLIED_BY",
            data_class=data_class(r["data_status"]),
            facts=[Fact(label="Primary supplier", value=yes_no(r["is_primary"])), Fact(label="Lead time", value=None if r["lead_time_days"] is None else f"{r['lead_time_days']} days"),
                   Fact(label="Supplier part number", value=r["supplier_part_number"])],
            groups=[FactGroup(label="Supplies categories", values=r["categories"])] if r["categories"] else [],
        )
        for r in rows
    ]
    evidence = [ev(part.label, "PART", "SUPPLIED_BY", r["name"] or r["supplier_id"], "SUPPLIER", r["data_status"]) for r in rows]
    primary = [r["name"] or r["supplier_id"] for r in rows if r["is_primary"]]
    primary_note = (f" Primary supplier: {', '.join(primary)}." if primary else " None of them is marked as the primary supplier in the graph.") if rows else ""
    summary = (f"{_count(len(rows), 'supplier')} {'is' if len(rows) == 1 else 'are'} connected to {part.label} through SUPPLIED_BY.{primary_note}"
               if rows else f"No supplier relationship is recorded for {part.label} in the graph.")
    return Outcome(summary, results, evidence, ["Part", "SUPPLIED_BY", "Supplier"], len(rows), actions=[investigate_action(part.label)])


def _dealer_item(r: dict) -> ResultItem:
    return ResultItem(
        kind="dealer", key=r["dealer_id"], title=r["name"] or r["dealer_id"], subtitle=place(r["city"], r["country_code"]), relationship="STOCKED_BY", data_class=data_class(r["data_status"]),
        facts=[Fact(label="Units recorded", value=None if r["available"] is None else str(r["available"])), Fact(label="Stocking status", value=humanize(r["stocking_status"])),
               Fact(label="Collection", value=yes_no(r["pickup_allowed"]))],
    )


def part_to_dealer(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    rows = c.repo.dealers(part.id)
    evidence = [ev(part.label, "PART", "STOCKED_BY", r["name"] or r["dealer_id"], "DEALER", r["data_status"]) for r in rows]
    summary = (f"{_count(len(rows), 'dealer')} {'stocks' if len(rows) == 1 else 'stock'} {part.label} according to the graph."
               if rows else f"No dealer stocking relationship is recorded for {part.label} in the graph.")
    return Outcome(summary, [_dealer_item(r) for r in rows], evidence, ["Part", "STOCKED_BY", "Dealer"], len(rows), actions=[investigate_action(part.label)])


def _warehouse_item(r: dict) -> ResultItem:
    return ResultItem(
        kind="warehouse", key=r["warehouse_id"], title=r["name"] or r["warehouse_id"], subtitle=place(r["city"], r["country_code"]), relationship="AVAILABLE_AT",
        data_class=data_class(r["data_status"]),
        facts=[Fact(label="Units recorded", value=None if r["available"] is None else str(r["available"])), Fact(label="Stock status", value=humanize(r["stock_status"]))],
    )


def _holding(rows: list[dict]) -> tuple[list[dict], int]:
    """Records that hold the part (a recorded quantity above zero, or no quantity stated) and how many are recorded at zero. Unknown is not zero."""
    have = [r for r in rows if r["available"] is None or r["available"] > 0]
    return have, len(rows) - len(have)


def _zero_note(zero: int, noun: str) -> str:
    return f" {_count(zero, noun)} {'is' if zero == 1 else 'are'} recorded with no units available." if zero else ""


def part_to_location(c: Context) -> Outcome:
    """Where the part is available: the warehouses and dealers that hold it. Suppliers are a different question; nothing else is returned."""
    part = c.need(Kind.PART)
    wh, dl = _holding(c.repo.warehouses(part.id)), _holding(c.repo.dealers(part.id))
    results = [_warehouse_item(r) for r in wh[0]] + [_dealer_item(r) for r in dl[0]]
    evidence = [ev(part.label, "PART", "AVAILABLE_AT", r["name"] or r["warehouse_id"], "WAREHOUSE", r["data_status"]) for r in wh[0]] + [
        ev(part.label, "PART", "STOCKED_BY", r["name"] or r["dealer_id"], "DEALER", r["data_status"]) for r in dl[0]]
    if not results:
        return Outcome(f"No warehouse or dealer is recorded as holding {part.label} in the graph, so its availability is not established.", path=["Part", "AVAILABLE_AT | STOCKED_BY", "Warehouse | Dealer"],
                       actions=[investigate_action(part.label)])
    summary = f"{part.label} is available at {_count(len(wh[0]), 'warehouse')} and {_count(len(dl[0]), 'dealer')}.{_zero_note(wh[1], 'warehouse')}"
    warnings = ["Cities and countries are the values stated on each record. Sharing a city or country does not imply a business relationship."]
    return Outcome(summary, results, evidence, ["Part", "AVAILABLE_AT | STOCKED_BY", "Warehouse | Dealer"], len(results), warnings, [investigate_action(part.label)])


def part_to_warehouse(c: Context) -> Outcome:
    """Which warehouses hold the part: warehouse records only (no dealers, no suppliers)."""
    part = c.need(Kind.PART)
    rows = c.repo.warehouses(part.id)
    have, zero = _holding(rows)
    results = [_warehouse_item(r) for r in have]
    evidence = [ev(part.label, "PART", "AVAILABLE_AT", r["name"] or r["warehouse_id"], "WAREHOUSE", r["data_status"]) for r in have]
    if not rows:
        return Outcome(f"No warehouse stock record is connected to {part.label}, so which warehouses hold it is not established.", path=["Part", "AVAILABLE_AT", "Warehouse"],
                       actions=[investigate_action(part.label)])
    units = [r["available"] for r in have if r["available"] is not None]
    total = f", {sum(units)} units in all" if units else ""
    summary = (f"{part.label} is held at {_count(len(have), 'warehouse')}{total}.{_zero_note(zero, 'other warehouse')}" if have
               else f"{part.label} has stock records at {_count(len(rows), 'warehouse')}, none with units available.")
    warnings = ["Stock figures are demonstration data, not live inventory."] if any(i.data_class == "SYNTHETIC_DEMO" for i in results) else []
    return Outcome(summary, results, evidence, ["Part", "AVAILABLE_AT", "Warehouse"], len(results), warnings, [investigate_action(part.label)])


def warehouse_stock(c: Context) -> Outcome:
    """What one named warehouse holds. Starts from the warehouse and follows only its own AVAILABLE_AT records."""
    wh = c.need(Kind.WAREHOUSE)
    d = c.repo.warehouse_stock(wh.id, c.limit)
    rows = d["rows"]
    results = [part_item(r, relationship="AVAILABLE_AT", facts=[Fact(label="Units recorded", value=None if r["available"] is None else str(r["available"])),
                                                              Fact(label="Stock status", value=humanize(r["stock_status"])), Fact(label="Category", value=r["category"])]) for r in rows]
    evidence = [ev(r["part_number"], "PART", "AVAILABLE_AT", wh.label, "WAREHOUSE", r["data_status"]) for r in rows]
    if not d["recorded"]:
        return Outcome(f"No stock record is connected to {wh.label} in the graph, so what it holds is not established.", path=["Part", "AVAILABLE_AT", "Warehouse"])
    extras = "".join([f"; {d['out_of_stock']} recorded as out of stock" if d["out_of_stock"] else "", f"; {d['not_stated']} without a stated quantity" if d["not_stated"] else ""])
    summary = f"{wh.label} has {_count(d['in_stock'], 'part')} in stock out of {d['recorded']} with a stock record{extras}."
    warnings = ["Stock figures are demonstration data, not live inventory."] if any(i.data_class == "SYNTHETIC_DEMO" for i in results) else []
    return Outcome(summary, results, evidence, ["Part", "AVAILABLE_AT", "Warehouse"], d["in_stock"], warnings)


def part_to_inventory(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    wh, dl = c.repo.warehouses(part.id), c.repo.dealers(part.id)
    if not wh and not dl:
        return Outcome(f"No stock records are connected to {part.label}, so its availability is unknown. This is not the same as zero.", path=["Part", "AVAILABLE_AT", "Warehouse"],
                       warnings=["Inventory is not connected for this part."], actions=[investigate_action(part.label)])
    known = [r["available"] for r in wh if r["available"] is not None]
    results = [_warehouse_item(r) for r in wh] + [_dealer_item(r) for r in dl]
    evidence = [ev(part.label, "PART", "AVAILABLE_AT", r["name"] or r["warehouse_id"], "WAREHOUSE", r["data_status"]) for r in wh] + [
        ev(part.label, "PART", "STOCKED_BY", r["name"] or r["dealer_id"], "DEALER", r["data_status"]) for r in dl]
    total = f"{sum(known)} units recorded across {_count(len(wh), 'warehouse')}" if known else f"stock recorded at {_count(len(wh), 'warehouse')} without quantities"
    demo = any(i.data_class == "SYNTHETIC_DEMO" for i in results)
    warnings = ["Stock figures are demonstration data, not live inventory."] if demo else []
    return Outcome(f"{part.label}: {total}, and {_count(len(dl), 'dealer')} with a stocking record.", results, evidence, ["Part", "AVAILABLE_AT | STOCKED_BY", "Warehouse | Dealer"], len(results), warnings, [investigate_action(part.label)])


def part_to_compliance(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    rows = c.repo.compliance(part.id)
    results = [
        ResultItem(
            kind="compliance", key=r["compliance_id"], title=r["requirement"] or r["compliance_id"], subtitle=r["standard"], relationship="HAS_COMPLIANCE", data_class=data_class(r["data_status"]),
            facts=[Fact(label="Certification", value=r["certification"]), Fact(label="Certificate status", value=humanize(r["certificate_status"])), Fact(label="Valid until", value=r["valid_until"])],
            groups=[FactGroup(label="Covers categories", values=r["covers"])] if r["covers"] else [],
        )
        for r in rows
    ]
    evidence = [ev(part.label, "PART", "HAS_COMPLIANCE", r["requirement"] or r["compliance_id"], "COMPLIANCE", r["data_status"]) for r in rows]
    demo = sum(1 for i in results if i.data_class == "SYNTHETIC_DEMO")
    warnings = ["These compliance assignments are demonstration data, not real certifications."] if demo else []
    if not rows:
        summary = f"No compliance requirement is connected to {part.label} in the graph, so compliance and certification are not established in the current graph."
    else:
        base = f"{part.label} has {_count(len(rows), 'compliance requirement')} connected in the graph."
        if demo == len(rows):
            summary = f"{base} Compliance information is recorded for this part, but the record is SYNTHETIC_DEMO and does not establish real-world certification."
        elif demo:
            summary = f"{base} {demo} of them {'is' if demo == 1 else 'are'} SYNTHETIC_DEMO and do not establish real-world certification; the others carry the certificate status shown."
        else:
            summary = f"{base} The certificate status is shown as recorded on each requirement."
    return Outcome(summary, results, evidence, ["Part", "HAS_COMPLIANCE", "ComplianceRequirement"], len(rows), warnings, [investigate_action(part.label)])


def part_provenance(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    core = c.repo.part_core(part.label)
    rels = c.repo.relationships(part.id)
    p = core["part"] if core else {}
    profile = (core or {}).get("profile") or {}
    status_code = profile.get("part_status")
    classes: dict[str, int] = {}
    for r in rels:
        classes[r["data_status"]] = classes.get(r["data_status"], 0) + r["n"]
    status_class = data_class(profile.get("data_status")) if profile else "NOT_CONNECTED"
    results = [
        ResultItem(kind="metric", key="record", title="Part record", subtitle=part.label, data_class=data_class(p.get("data_status")), facts=[
            Fact(label="Data class", value=LABELS[data_class(p.get("data_status"))]), Fact(label="Source", value=p.get("source_name")), Fact(label="Source file", value=p.get("source_file")),
            Fact(label="Source record", value=p.get("source_record_id")), Fact(label="Confidence", value=humanize(p.get("confidence"))),
            Fact(label="Authoritative", value=yes_no(p.get("authoritative_flag"))), Fact(label="Last updated", value=p.get("last_updated"))]),
        ResultItem(kind="metric", key="status", title=status_label(status_code), subtitle="Catalogue status", data_class=status_class, facts=[
            Fact(label="Reason", value=profile.get("status_reason")), Fact(label="Orderable online", value=yes_no(profile.get("orderable"))),
            Fact(label="Status data class", value=LABELS[status_class])]),
        *[ResultItem(kind="metric", key=f"rels-{k}", title=f"{n} relationships", subtitle=LABELS[data_class(k)], data_class=data_class(k), facts=[Fact(label="Data class", value=LABELS[data_class(k)])])
          for k, n in sorted(classes.items())],
    ]
    evidence = [ev(part.label, "PART", "RECORD", p.get("source_name") or "source not stated", "SOURCE", p.get("data_status")),
                ev(part.label, "PART", "PROFILES_PART (status)", status_label(status_code), "STATUS", profile.get("data_status"))]
    evidence += [ev(part.label, "PART", r["relationship"], f"{r['n']} × {r['other_label']}", r["other_label"].upper(), r["data_status"]) for r in rels]
    mix = ", ".join(f"{n} {LABELS[data_class(k)].lower()}" for k, n in sorted(classes.items()))
    demo = " (from demo data)" if status_class == "SYNTHETIC_DEMO" else ""
    summary = (f"{part.label} catalogue status: {status_label(status_code)}{demo}. The part record is {LABELS[data_class(p.get('data_status'))].lower()}; "
               f"its {sum(classes.values())} connected relationships are: {mix}.")
    return Outcome(summary, results, evidence, ["Part", "any relationship"], len(results), actions=[investigate_action(part.label)])


def part_graph(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    rels = c.repo.relationships(part.id)
    results = [ResultItem(kind="path", key=f"{r['relationship']}-{r['other_label']}-{r['data_status']}", title=r["relationship"], subtitle=r["other_label"], relationship=r["relationship"],
                          data_class=data_class(r["data_status"]), facts=[Fact(label="Connected entities", value=str(r["n"])), Fact(label="Data class", value=LABELS[data_class(r["data_status"])])]) for r in rels]
    evidence = [ev(part.label, "PART", r["relationship"], f"{r['n']} × {r['other_label']}", r["other_label"].upper(), r["data_status"]) for r in rels]
    return Outcome(f"{part.label} has {sum(r['n'] for r in rels)} direct relationships across {_count(len(rels), 'type')}.", results, evidence, ["Part", "any relationship", "any"], len(results),
                   actions=[investigate_action(part.label)])


def machine_graph(c: Context) -> Outcome:
    machine = c.need(Kind.MACHINE)
    core = c.repo.machine_core(machine.id)
    if core is None:
        return Outcome(f"{machine.label} could not be loaded from the graph.")
    m = core["machine"]
    item = ResultItem(
        kind="machine", key=m["machine_id"], title=m["model_code"], subtitle=m["name"], data_class=data_class(m["data_status"]),
        facts=[Fact(label="Machine type", value=m["machine_type"]), Fact(label="Family", value=core["family"]), Fact(label="Business unit", value=core["business_unit"]),
               Fact(label="Plant", value=core["plant"]), Fact(label="Connected parts", value=str(core["part_count"])), Fact(label="Service plans", value=str(core["service_plans"])),
               Fact(label="Specifications", value=str(core["specifications"])),
               *([Fact(label="Application (demo data)", value=core["profile"]["application"]), Fact(label="Lifecycle (demo data)", value=humanize(core["profile"]["lifecycle_status"])),
                  Fact(label="Introduced (demo data)", value=str(core["profile"]["introduction_year"]))] if core.get("profile") else [])],
        groups=[FactGroup(label="Dealers serving this machine family", values=core["dealers_serving_family"])] if core["dealers_serving_family"] else [],
    )
    ds = m["data_status"]
    evidence = [e for e in [
        ev(m["model_code"], "MACHINE", "MEMBER_OF_FAMILY", core["family"], "FAMILY", ds) if core["family"] else None,
        ev(m["model_code"], "MACHINE", "BRANDED_AS", core["business_unit"], "BUSINESS_UNIT", ds) if core["business_unit"] else None,
        ev(m["model_code"], "MACHINE", "MANUFACTURED_AT", core["plant"], "PLANT", ds) if core["plant"] else None,
        ev(m["model_code"], "MACHINE", "FITS (incoming)", f"{core['part_count']} parts", "PART", "SOURCE_DERIVED"),
        ev(m["model_code"], "MACHINE", "FOR_MACHINE (incoming)", f"{core['service_plans']} service plans", "SERVICE_PLAN", "SYNTHETIC_DEMO") if core["service_plans"] else None,
    ] if e is not None]
    return Outcome(f"{m['model_code']} is a {m['machine_type'] or 'machine'} with {_count(core['part_count'], 'part')} connected in the graph.", [item], evidence, ["Machine", "any relationship", "any"], 1,
                   actions=[Action(kind="ask", label=f"Parts that fit {m['model_code']}", question=f"Which parts fit {m['model_code']}?")])


def machine_list(c: Context) -> Outcome:
    place, brand = c.extra.get("place"), c.extra.get("brand")
    rows = c.repo.machines(place, brand)
    results = [
        ResultItem(kind="machine", key=r["machine"]["machine_id"], title=r["machine"]["model_code"], subtitle=r["machine"]["name"], data_class=data_class(r["machine"]["data_status"]),
                   facts=[Fact(label="Machine type", value=r["machine"]["machine_type"]), Fact(label="Family", value=r["family"]), Fact(label="Brand", value=r["brand"]), Fact(label="Plant", value=r["plant"]),
                          Fact(label="Connected parts", value=str(r["part_count"]))])
        for r in rows[: c.limit]
    ]
    evidence = [ev(r["machine"]["model_code"], "MACHINE", "FITS (incoming)", f"{r['part_count']} parts", "PART", "SOURCE_DERIVED") for r in rows[: c.limit]]
    where = "".join([f" from the {brand.title()} brand" if brand else "", f" with plant or origin matching '{place}'" if place else ""])
    if not rows:
        summary = f"No machines are recorded in the graph{where}."
    elif place is None and brand is None:
        summary = f"The catalogue holds {_count(len(rows), 'machine')}. Ask which parts fit any of them."
    else:
        summary = f"{_count(len(rows), 'machine')} recorded{where}."
    return Outcome(summary, results, evidence, ["Machine"], len(rows))


AVAILABILITY_LABEL = {"IN_STOCK": "In stock", "LIMITED": "Limited", "BACKORDER": "Backorder"}


def shared_parts(c: Context) -> Outcome:
    machine = c.entities.get(Kind.MACHINE)
    total, rows = c.repo.shared_parts(machine.label if machine else None, c.limit)
    results = [part_item(r, relationship="FITS", facts=[Fact(label="Category", value=r["category"]), Fact(label="Machines", value=str(len(r["machines"])))],
                         groups=[FactGroup(label="Fits", values=r["machines"])]) for r in rows]
    evidence = [ev(r["part_number"], "PART", "FITS", m, "MACHINE", r["data_status"]) for r in rows for m in r["machines"]]
    scope = f", including {machine.label}" if machine else ""
    summary = f"{_count(total, 'part')} {'is' if total == 1 else 'are'} recorded as fitting more than one machine{scope}." if total else f"No part is recorded as fitting more than one machine{scope}."
    warnings = ["Fitting the same machines does not make parts interchangeable; each fitment is a separate catalogue record."]
    return Outcome(summary, results, evidence, ["Part", "FITS", "Machine"], total, warnings)


def part_to_service_plan(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    rows = c.repo.part_service_plans(part.id)
    results = [ResultItem(kind="service_plan", key=r["plan"]["service_plan_id"], title=r["plan"]["name"] or r["plan"]["service_plan_id"], subtitle=r["plan"]["service_plan_id"],
                          relationship="REQUIRES_PART", data_class=data_class(r["link_status"]),
                          facts=[Fact(label="For machine", value=r["machine"]), Fact(label="Quantity", value=str(r["quantity"]) if r["quantity"] is not None else None),
                                 Fact(label="Interval", value=f"{r['plan']['interval_hours']} hours (demo interval)" if r["plan"].get("interval_hours") else None)]) for r in rows]
    evidence = [ev(r["plan"]["service_plan_id"], "SERVICE_PLAN", "REQUIRES_PART", part.label, "PART", r["link_status"]) for r in rows]
    evidence += [ev(r["plan"]["service_plan_id"], "SERVICE_PLAN", "FOR_MACHINE", r["machine"], "MACHINE", r["plan"]["data_status"]) for r in rows if r["machine"]]
    summary = f"{_count(len(rows), 'service plan')} {'requires' if len(rows) == 1 else 'require'} {part.label}." if rows else f"No service plan is recorded as requiring {part.label} in the graph."
    warnings = ["Service plans and their intervals are demonstration data, not maintenance instructions."] if rows else []
    return Outcome(summary, results, evidence, ["ServicePlan", "REQUIRES_PART", "Part"], len(rows), warnings, actions=[investigate_action(part.label)])


def part_to_orders(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    rows = c.repo.part_orders(part.id)
    results = []
    for r in rows:
        o = r["order"]
        shipped = ", ".join(humanize(s) or "" for s in r["shipments"]) or "No shipment recorded"
        results.append(ResultItem(kind="order", key=o["order_id"], title=o["order_id"], subtitle=f"Order status: {humanize(o['order_status'])}", relationship="CONTAINS_LINE",
                                  data_class=data_class(o["data_status"]),
                                  facts=[Fact(label="Order date", value=o.get("order_date")), Fact(label="Quantity", value=str(r["quantity"])),
                                         Fact(label="Allocation", value=humanize(r["allocation"])), Fact(label="Shipments", value=shipped)]))
    evidence = [ev(r["order"]["order_id"], "ORDER", "CONTAINS_LINE / REFERENCES_PART", part.label, "PART", r["link_status"]) for r in rows]
    summary = f"{part.label} appears in {_count(len(rows), 'demo order')}." if rows else f"No order containing {part.label} is recorded in the graph."
    warnings = ["Demo orders: orders and shipments are synthetic demonstration data, not live orders. Customer and address details are not shown."] if rows else []
    actions = [Action(kind="ask", label=f"Status of {rows[0]['order']['order_id']}", question=f"Where is order {rows[0]['order']['order_id']}?")] if rows else []
    return Outcome(summary, results, evidence, ["Order", "CONTAINS_LINE", "OrderLine", "REFERENCES_PART", "Part"], len(rows), warnings, actions=actions)


def low_stock_parts(c: Context) -> Outcome:
    total, rows = c.repo.low_stock_parts(c.limit)
    results = [part_item(r, relationship="AVAILABLE_AT", facts=[Fact(label="Availability", value=AVAILABILITY_LABEL.get(r["state"], humanize(r["state"]))),
                                                              Fact(label="Warehouse units recorded", value=str(r["units"])), Fact(label="Warehouses", value=str(r["warehouses"]))])
               for r in rows]
    evidence = [ev(r["part_number"], "PART", "availability_state", AVAILABILITY_LABEL.get(r["state"], r["state"]), "AVAILABILITY", r["data_status"]) for r in rows]
    backorder = sum(1 for r in rows if r["state"] == "BACKORDER")
    summary = (f"{_count(total, 'part')} {'is' if total == 1 else 'are'} Limited or on Backorder in the catalogue ({backorder} on Backorder)." if total
               else "No part is Limited or on Backorder in the catalogue.")
    return Outcome(summary, results, evidence, ["PartCatalogProfile", "PROFILES_PART", "Part", "AVAILABLE_AT", "Warehouse"], total,
                   ["Stock and availability are demonstration data, not live inventory."])


def _listing_outcome(core_label: str, relationship: str, kind: str, total: int, rows: list[dict], summary: str, facts: Callable[[dict], list[Fact]]) -> Outcome:
    results = [part_item(r, relationship=relationship, facts=facts(r)) for r in rows]
    evidence = [ev(r["part_number"], "PART", relationship, core_label, kind, r["data_status"]) for r in rows]
    return Outcome(summary, results, evidence, ["Part", relationship, kind.title()], total)


def supplier_graph(c: Context) -> Outcome:
    supplier = c.need(Kind.SUPPLIER)
    core = c.repo.supplier_core(supplier.id)
    total, rows = c.repo.supplier_parts(supplier.id, c.limit)
    where = place(core["supplier"]["city"], core["supplier"]["country_code"]) if core else None
    cats = f" It is connected to the categories {', '.join(core['categories'])}." if core and core["categories"] else ""
    return _listing_outcome(supplier.label, "SUPPLIED_BY", "SUPPLIER", total, rows, f"{supplier.label}{f' ({where})' if where else ''} is connected to {_count(total, 'part')} through SUPPLIED_BY.{cats}",
                            lambda r: [Fact(label="Category", value=r["category"]), Fact(label="Primary supplier", value=yes_no(r["is_primary"])), Fact(label="Lead time", value=None if r["lead_time_days"] is None else f"{r['lead_time_days']} days")])


def dealer_graph(c: Context) -> Outcome:
    dealer = c.need(Kind.DEALER)
    core = c.repo.dealer_core(dealer.id)
    total, rows = c.repo.dealer_parts(dealer.id, c.limit)
    where = place(core["dealer"]["city"], core["dealer"]["country_code"]) if core else None
    fam = f" It serves the machine families {', '.join(core['families'])}." if core and core["families"] else ""
    return _listing_outcome(dealer.label, "STOCKED_BY", "DEALER", total, rows, f"{dealer.label}{f' ({where})' if where else ''} has a stocking record for {_count(total, 'part')}.{fam}",
                            lambda r: [Fact(label="Category", value=r["category"]), Fact(label="Units recorded", value=None if r["available"] is None else str(r["available"])), Fact(label="Stocking status", value=humanize(r["stocking_status"]))])


_GAPS = (
    ("without_fitment", "Parts with no machine fitment"),
    ("without_supplier", "Parts with no supplier"),
    ("without_warehouse_stock", "Parts with no warehouse stock record"),
    ("without_dealer_stock", "Parts with no dealer stocking record"),
    ("without_compliance", "Parts with no compliance requirement"),
    ("without_assembly", "Parts not in any assembly"),
    ("without_legacy_reference", "Parts with no legacy reference"),
    ("needing_identification", "Parts that need machine identification"),
)

# what a part can be connected to, and how it reads when it is not
_PART_GAPS = (
    ("machines", "FITS", "machine fitment"),
    ("suppliers", "SUPPLIED_BY", "supplier"),
    ("warehouses", "AVAILABLE_AT", "warehouse stock record"),
    ("dealers", "STOCKED_BY", "dealer stocking record"),
    ("compliance", "HAS_COMPLIANCE", "compliance requirement"),
    ("assemblies", "PART_OF", "assembly"),
    ("related_parts", "RELATED_COMPONENT | CO_ORDERED_WITH | SAME_NAME_GROUP_AS", "related part"),
    ("legacy_references", "HAS_LEGACY_REFERENCE", "legacy reference"),
    ("specifications", "HAS_SPECIFICATION", "specification"),
    ("prices", "PRICES_PART", "price"),
)


def _part_gaps(c: Context, part: Resolved) -> Outcome:
    counts = c.repo.counts(part.id)
    core = c.repo.part_core(part.label) or {}
    p = core.get("part") or {}
    missing = [(k, rel, label) for k, rel, label in _PART_GAPS if not counts.get(k)]
    fields = [label for key, label in (("brand", "manufacturer"), ("spec_note_source", "description"), ("origin_plant", "plant of origin")) if not p.get(key)]
    results = [ResultItem(kind="metric", key=k, title="Not connected", subtitle=f"No {label}", relationship=rel, data_class="NOT_CONNECTED", facts=[Fact(label="Relationship", value=rel)])
               for k, rel, label in missing]
    results += [ResultItem(kind="metric", key=f"field-{f}", title="Not recorded", subtitle=f"No {f}", data_class="NOT_CONNECTED", facts=[Fact(label="Field", value=f)]) for f in fields]
    evidence = [ev(part.label, "PART", rel, f"{counts.get(k, 0)} connected", "COUNT", "DERIVED") for k, rel, _ in _PART_GAPS]
    if core.get("identification"):
        results.append(ResultItem(kind="metric", key="identification", title="Identification needed", subtitle="Machine variant or serial range not confirmed", data_class="SYNTHETIC_DEMO",
                                  facts=[Fact(label="Machines", value=", ".join(sorted({i["model_code"] for i in core["identification"] if i.get("model_code")})) or None)]))
    gaps = [label for _, _, label in missing] + fields
    summary = (f"For {part.label}, the graph has no: {', '.join(gaps)}. Missing means not connected, not that the fact is false."
               if gaps else f"Every relationship Parts Intelligence checks is connected for {part.label}.")
    return Outcome(summary, results, evidence, ["Part", "relationship counts"], len(results), actions=[investigate_action(part.label)])


def data_quality(c: Context) -> Outcome:
    part = c.entities.get(Kind.PART)
    if part is not None:
        return _part_gaps(c, part)
    d = c.repo.data_quality()
    results = [ResultItem(kind="metric", key=k, title=str(d[k]), subtitle=label, data_class="DERIVED", facts=[Fact(label="Of parts", value=str(d["parts"]))]) for k, label in _GAPS]
    evidence = [ev(f"{d['parts']} parts", "PART", label, str(d[k]), "COUNT", "DERIVED") for k, label in _GAPS]
    biggest = max(_GAPS, key=lambda g: d[g[0]])
    return Outcome(f"Across {d['parts']} parts, the largest relationship gap is: {biggest[1].lower()} ({d[biggest[0]]}). A missing relationship means the data is not connected, not that the fact is false.",
                   results, evidence, ["counts"], len(results))


def part_search(c: Context) -> Outcome:
    machine, category = c.entities.get(Kind.MACHINE), c.entities.get(Kind.CATEGORY)
    text = c.text.strip()
    if category and text.lower() in category.label.lower():
        text = ""
    total, ids = c.parts.search(text=text, category=category.label if category else None, machine=machine.label if machine else None, availability=None, orderable=None, sort="relevance", offset=0, limit=c.limit)
    rows = [to_summary(r) for r in c.parts.summaries(ids)]
    key = text.lower().replace("-", "").replace(" ", "")

    def reason(p) -> str:
        if key and key == p.part_number.lower().replace("-", ""):
            return "Part number match"
        if text and text.lower() in p.name.lower():
            return "Name match"
        return "Matched on category, legacy reference, alias or machine" if text else "Matches the selected filters"

    results = [
        ResultItem(kind="part", key=p.part_id, title=p.part_number, subtitle=p.name, part_number=p.part_number, data_class="SOURCE_DERIVED",
                   facts=[Fact(label="Match", value=reason(p)), Fact(label="Category", value=p.category),
                          Fact(label="Status", value=status_label(p.availability.part_status if p.availability else None))],
                   groups=[FactGroup(label="Compatible machines", values=[f.model_code for f in p.fitment][:6])] if p.fitment else [])
        for p in rows
    ]
    evidence = [ev(p.part_number, "PART", "IN_CATEGORY", p.category or "no category", "CATEGORY", "SOURCE_DERIVED") for p in rows]
    evidence += [ev(p.part_number, "PART", "FITS", f.model_code, "MACHINE", "SOURCE_DERIVED") for p in rows for f in p.fitment if machine and f.model_code == machine.label]
    scope = " ".join(x for x in [f"for {machine.label}" if machine else "", f"in {category.label}" if category else ""] if x)
    if total == 1 and rows:
        summary = f"{rows[0].part_number} is the {rows[0].name.lower()} in the {rows[0].category or 'uncategorised'} category."
    else:
        summary = f"{_count(total, 'part')} match{'es' if total == 1 else ''}{(' ' + scope) if scope else ''}." if total else "No parts match this search."
    return Outcome(summary, results, evidence, ["Part"], total, actions=[investigate_action(rows[0].part_number)] if total == 1 and rows else [])


# ── paths, orders, places ──────────────────────────────────────────────────────────────────────────
_ID_PROPS = {Kind.PART: ("Part", "part_id"), Kind.MACHINE: ("Machine", "machine_id"), Kind.SUPPLIER: ("Supplier", "supplier_id"), Kind.DEALER: ("Dealer", "dealer_id"),
             Kind.ASSEMBLY: ("Assembly", "assembly_id"), Kind.CATEGORY: ("Category", "category_id"), Kind.ORDER: ("Order", "order_id"), Kind.WAREHOUSE: ("Warehouse", "warehouse_id")}
_DIRECT_MEANING = {"SUPPLIED_BY", "FITS", "STOCKED_BY", "PART_OF", "AVAILABLE_AT", "HAS_COMPLIANCE", "CO_ORDERED_WITH", "RELATED_COMPONENT", "SAME_NAME_GROUP_AS", "IN_CATEGORY"}


def _path_item(n: int, row: dict) -> tuple[ResultItem, list[Evidence]]:
    nodes, rels = row["nodes"], row["rels"]
    steps = [f"{r['source']} —{r['type']}→ {r['target']}" for r in rels]
    classes = {data_class(r["ds"]) for r in rels}
    item = ResultItem(kind="path", key=f"path-{n}", title=f"{nodes[0]['key']} → {nodes[-1]['key']}", subtitle=f"{len(rels)} step{'s' if len(rels) != 1 else ''}",
                      relationship=" / ".join(r["type"] for r in rels), data_class="SYNTHETIC_DEMO" if "SYNTHETIC_DEMO" in classes else (classes.pop() if len(classes) == 1 else "UNKNOWN"),
                      facts=[Fact(label="Through", value=" → ".join(f"{x['label']} {x['key']}" for x in nodes))], groups=[FactGroup(label="Stored relationships", values=steps)])
    evidence = [ev(r["source"], "", r["type"], r["target"], "", r["ds"]) for r in rels]
    return item, evidence


def entity_path(c: Context) -> Outcome:
    source, target = c.extra["path"]
    a = (*_ID_PROPS[source.kind], source.id)
    if isinstance(target, str):  # a kind: the nearest few
        rows = c.repo.path_to_kind(a, target)
        name = f"any {target.lower()}"
    else:
        rows = c.repo.path_between(a, (*_ID_PROPS[target.kind], target.id))
        name = target.label
    path = ["(a)", "business relationships, at most 4 steps", "(b)"]
    if not rows:
        return Outcome(f"No connection between {source.label} and {name} within 4 steps of stored business relationships.", path=path,
                       warnings=["Not connected does not mean the two are unrelated in reality; the graph holds no such link."])
    results, evidence = [], []
    for n, row in enumerate(rows):
        item, evs = _path_item(n, row)
        results.append(item)
        evidence += evs
    first = rows[0]["rels"]
    if len(first) == 1:
        summary = f"{source.label} is connected to {rows[0]['nodes'][-1]['key']} directly through {first[0]['type']}."
    else:
        summary = f"{source.label} reaches {rows[0]['nodes'][-1]['key']} in {len(first)} steps: {' → '.join(r['type'] for r in first)}."
    warnings = []
    if any(len(r["rels"]) > 1 for r in rows):
        warnings.append("A path through a shared warehouse, category, related part or machine family shows how the records connect; it is not a business relationship between the two ends.")
    return Outcome(summary, results, evidence, path, len(results), warnings)


def order_status(c: Context) -> Outcome:
    order = c.need(Kind.ORDER)
    row = c.repo.order_status(order.id)
    if row is None:
        return Outcome(f"Order {order.label} could not be loaded.")
    o = row["order"]
    lines = sorted(row["lines"], key=lambda l: l["line_no"] or 0)
    results = [ResultItem(kind="order", key=o["order_id"], title=o["order_id"], subtitle=f"Order status: {humanize(o['order_status'])}", relationship="CONTAINS_LINE",
                          data_class=data_class(o["data_status"]),
                          facts=[Fact(label="Order date", value=o.get("order_date")), Fact(label="Shipping method", value=humanize(o.get("shipping_method"))), Fact(label="Channel", value=humanize(o.get("channel")))],
                          groups=[FactGroup(label="Parts", values=[f"{l['part_number']} · {l['name']} × {l['quantity']} ({humanize(l['allocation_status']) or 'allocation not stated'})" for l in lines])])]
    evidence = [ev(o["order_id"], "ORDER", "CONTAINS_LINE", l["part_number"], "PART", l["data_status"]) for l in lines]
    latest_text = []
    for s in sorted(row["shipments"], key=lambda s: s["shipment_id"]):
        events = sorted(s["events"], key=lambda e: e.get("event_seq") or 0)
        last = events[-1] if events else None
        latest = f"{humanize(last['event_status'])}, {last.get('event_location') or 'location not stated'}, {last.get('event_date') or 'date not stated'}" if last else None
        results.append(ResultItem(kind="shipment", key=s["shipment_id"], title=s["shipment_id"], subtitle=f"Shipment status: {humanize(s['status'])}", relationship="HAS_SHIPMENT",
                                  data_class=data_class(s["data_status"]),
                                  facts=[Fact(label="Tracking reference", value=s.get("tracking_ref")), Fact(label="Carrier", value=s.get("carrier")), Fact(label="Latest event", value=latest)]))
        evidence.append(ev(o["order_id"], "ORDER", "HAS_SHIPMENT", s["shipment_id"], "SHIPMENT", s["data_status"]))
        if last:
            latest_text.append(f"{s['shipment_id']}: {humanize(last['event_status']).lower()}")
    ship = f" Shipments: {'; '.join(latest_text)}." if latest_text else " No shipment is recorded."
    summary = f"Demo order {o['order_id']} is {humanize(o['order_status']).lower()}, with {_count(len(lines), 'part line')}.{ship}"
    warnings = ["Demo order: orders, shipments and tracking events are synthetic demonstration data, not live order or carrier data. Customer and address details are not shown."]
    return Outcome(summary, results, evidence, ["Order", "CONTAINS_LINE / HAS_SHIPMENT", "OrderLine / Shipment"], len(results), warnings)


_GEO_NOUN = {"DEALER": ("dealer", "dealers"), "SUPPLIER": ("supplier", "suppliers"), "WAREHOUSE": ("warehouse", "warehouses")}


def geo_location(c: Context) -> Outcome:
    kind, city, cc, mode, place_name = c.extra["geo"]
    one, many = _GEO_NOUN[kind]
    rows = c.repo.located(kind, city, cc if city is None else None)
    basis = f"Same city as {place_name}" if city else f"Located in {place_name}"
    warnings = ["Location is the city and country stated on each record. The graph stores no coordinates, so no distances are calculated, "
                "and being in the same place does not make anyone a supplier or dealer of a part."]
    if city and not rows and mode == "near":  # nothing in that city: the same country is the closest stated basis
        rows = c.repo.located(kind, None, cc)
        basis = f"Same country as {place_name} (no {one} is recorded in {place_name}; distance not calculated)"
    results = [ResultItem(kind="dealer" if kind == "DEALER" else "supplier" if kind == "SUPPLIER" else "warehouse", key=r["id"], title=r["name"] or r["id"], subtitle=place(r["city"], r["cc"]),
                          data_class=data_class(r["ds"]), facts=[Fact(label="City", value=r["city"]), Fact(label="Country", value=r["cc"]), Fact(label="Distance basis", value=basis)])
               for r in rows[: c.limit]]
    evidence = [ev(r["name"] or r["id"], kind, "LOCATED (stated city)", place(r["city"], r["cc"]) or "not stated", "PLACE", r["ds"]) for r in rows[: c.limit]]
    where = f"in {place_name}" if mode == "in" or (city and basis.startswith("Same city")) else f"near {place_name}"
    summary = (f"{_count(len(rows), one, many)} {'is' if len(rows) == 1 else 'are'} recorded {where}. Basis: {basis.lower()}; no distances are calculated."
               if rows else f"No {one} is recorded {where}.")
    return Outcome(summary, results, evidence, [kind.title(), "city / country_code"], len(rows), warnings)


HANDLERS: dict[Intent, Callable[[Context], Outcome]] = {
    Intent.PART_SEARCH: part_search, Intent.PART_TO_MACHINE: part_to_machine, Intent.MACHINE_TO_PART: machine_to_part, Intent.PART_TO_CATEGORY: part_to_category,
    Intent.PART_TO_ASSEMBLY: part_to_assembly, Intent.ASSEMBLY_TO_PART: assembly_to_part, Intent.PART_TO_PART: part_to_part, Intent.PART_TO_SUPPLIER: part_to_supplier,
    Intent.PART_TO_DEALER: part_to_dealer, Intent.PART_TO_LOCATION: part_to_location, Intent.PART_TO_WAREHOUSE: part_to_warehouse, Intent.WAREHOUSE_STOCK: warehouse_stock, Intent.PART_TO_INVENTORY: part_to_inventory, Intent.PART_TO_COMPLIANCE: part_to_compliance,
    Intent.PART_PROVENANCE: part_provenance, Intent.PART_GRAPH: part_graph, Intent.MACHINE_GRAPH: machine_graph, Intent.MACHINE_LIST: machine_list, Intent.SHARED_PARTS: shared_parts,
    Intent.PART_TO_SERVICE_PLAN: part_to_service_plan, Intent.PART_TO_ORDERS: part_to_orders, Intent.LOW_STOCK_PARTS: low_stock_parts, Intent.SUPPLIER_GRAPH: supplier_graph,
    Intent.DEALER_GRAPH: dealer_graph, Intent.DATA_QUALITY: data_quality, Intent.ENTITY_PATH: entity_path, Intent.ORDER_STATUS: order_status,
    Intent.GEO_LOCATION: geo_location,
}
