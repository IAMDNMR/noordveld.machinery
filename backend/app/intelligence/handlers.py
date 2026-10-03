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
    summary = (f"{_count(len(rows), 'supplier')} {'is' if len(rows) == 1 else 'are'} connected to {part.label} through SUPPLIED_BY."
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
        kind="stock", key=r["warehouse_id"], title=r["name"] or r["warehouse_id"], subtitle=place(r["city"], r["country_code"]), relationship="AVAILABLE_AT",
        data_class=data_class(r["data_status"]),
        facts=[Fact(label="Units recorded", value=None if r["available"] is None else str(r["available"])), Fact(label="Stock status", value=humanize(r["stock_status"]))],
    )


def part_to_location(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    wh, dl, sp = c.repo.warehouses(part.id), c.repo.dealers(part.id), c.repo.suppliers(part.id)
    results = [_warehouse_item(r) for r in wh] + [_dealer_item(r) for r in dl] + [
        ResultItem(kind="supplier", key=r["supplier_id"], title=r["name"] or r["supplier_id"], subtitle=place(r["city"], r["country_code"]), relationship="SUPPLIED_BY",
                   data_class=data_class(r["data_status"]), facts=[Fact(label="Role", value="Supplier")])
        for r in sp
    ]
    evidence = (
        [ev(part.label, "PART", "AVAILABLE_AT", r["name"] or r["warehouse_id"], "WAREHOUSE", r["data_status"]) for r in wh]
        + [ev(part.label, "PART", "STOCKED_BY", r["name"] or r["dealer_id"], "DEALER", r["data_status"]) for r in dl]
        + [ev(part.label, "PART", "SUPPLIED_BY", r["name"] or r["supplier_id"], "SUPPLIER", r["data_status"]) for r in sp]
    )
    if not results:
        return Outcome(f"No warehouse, dealer or supplier location is connected to {part.label} in the graph.", path=["Part", "AVAILABLE_AT | STOCKED_BY | SUPPLIED_BY", "Location"], actions=[investigate_action(part.label)])
    summary = f"{part.label} is connected to {_count(len(wh), 'warehouse')}, {_count(len(dl), 'dealer')} and {_count(len(sp), 'supplier')}."
    warnings = ["Cities and countries are the values stated on each record. Sharing a city or country does not imply a business relationship."]
    return Outcome(summary, results, evidence, ["Part", "AVAILABLE_AT | STOCKED_BY | SUPPLIED_BY", "Warehouse | Dealer | Supplier"], len(results), warnings, [investigate_action(part.label)])


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
    warnings = ["These compliance assignments are demonstration data, not real certifications."] if any(i.data_class == "SYNTHETIC_DEMO" for i in results) else []
    summary = f"{part.label} has {_count(len(rows), 'compliance requirement')} connected in the graph." if rows else f"No compliance requirement is connected to {part.label} in the graph."
    return Outcome(summary, results, evidence, ["Part", "HAS_COMPLIANCE", "ComplianceRequirement"], len(rows), warnings, [investigate_action(part.label)])


def part_provenance(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    core = c.repo.part_core(part.label)
    rels = c.repo.relationships(part.id)
    p = core["part"] if core else {}
    classes: dict[str, int] = {}
    for r in rels:
        classes[r["data_status"]] = classes.get(r["data_status"], 0) + r["n"]
    results = [
        ResultItem(kind="metric", key="record", title="Part record", subtitle=part.label, data_class=data_class(p.get("data_status")), facts=[
            Fact(label="Data class", value=humanize(p.get("data_status"))), Fact(label="Source", value=p.get("source_name")), Fact(label="Source file", value=p.get("source_file")),
            Fact(label="Source record", value=p.get("source_record_id")), Fact(label="Confidence", value=humanize(p.get("confidence"))),
            Fact(label="Authoritative", value=yes_no(p.get("authoritative_flag")))]),
        *[ResultItem(kind="metric", key=f"rels-{k}", title=f"{n} relationships", subtitle=humanize(k), data_class=data_class(k), facts=[Fact(label="Data class", value=humanize(k))]) for k, n in sorted(classes.items())],
    ]
    mix = ", ".join(f"{n} {LABELS[data_class(k)].lower()}" for k, n in sorted(classes.items()))
    return Outcome(f"The {part.label} record is {LABELS[data_class(p.get('data_status'))].lower()}. Its {sum(classes.values())} connected relationships are: {mix}.", results, [],
                   ["Part", "any relationship"], len(results), actions=[investigate_action(part.label)])


def part_graph(c: Context) -> Outcome:
    part = c.need(Kind.PART)
    rels = c.repo.relationships(part.id)
    results = [ResultItem(kind="path", key=f"{r['relationship']}-{r['other_label']}-{r['data_status']}", title=r["relationship"], subtitle=r["other_label"], relationship=r["relationship"],
                          data_class=data_class(r["data_status"]), facts=[Fact(label="Connected entities", value=str(r["n"])), Fact(label="Data class", value=humanize(r["data_status"]))]) for r in rels]
    return Outcome(f"{part.label} has {sum(r['n'] for r in rels)} direct relationships across {_count(len(rels), 'type')}.", results, [], ["Part", "any relationship", "any"], len(results), actions=[investigate_action(part.label)])


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
               Fact(label="Specifications", value=str(core["specifications"]))],
        groups=[FactGroup(label="Dealers serving this machine family", values=core["dealers_serving_family"])] if core["dealers_serving_family"] else [],
    )
    return Outcome(f"{m['model_code']} is a {m['machine_type'] or 'machine'} with {_count(core['part_count'], 'part')} connected in the graph.", [item], [], ["Machine", "any relationship", "any"], 1,
                   actions=[Action(kind="ask", label=f"Parts that fit {m['model_code']}", question=f"Which parts fit {m['model_code']}?")])


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
    out = _listing_outcome(supplier.label, "SUPPLIED_BY", "SUPPLIER", total, rows, f"{supplier.label}{f' ({where})' if where else ''} is connected to {_count(total, 'part')} through SUPPLIED_BY.{cats}",
                           lambda r: [Fact(label="Category", value=r["category"]), Fact(label="Primary supplier", value=yes_no(r["is_primary"])), Fact(label="Lead time", value=None if r["lead_time_days"] is None else f"{r['lead_time_days']} days")])
    return out


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


def data_quality(c: Context) -> Outcome:
    d = c.repo.data_quality()
    results = [ResultItem(kind="metric", key=k, title=str(d[k]), subtitle=label, data_class="DERIVED", facts=[Fact(label="Of parts", value=str(d["parts"]))]) for k, label in _GAPS]
    biggest = max(_GAPS, key=lambda g: d[g[0]])
    return Outcome(f"Across {d['parts']} parts, the largest relationship gap is: {biggest[1].lower()} ({d[biggest[0]]}). A missing relationship means the data is not connected, not that the fact is false.",
                   results, [], ["counts"], len(results))


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
                   facts=[Fact(label="Match", value=reason(p)), Fact(label="Category", value=p.category)],
                   groups=[FactGroup(label="Compatible machines", values=[f.model_code for f in p.fitment][:6])] if p.fitment else [])
        for p in rows
    ]
    scope = " ".join(x for x in [f"for {machine.label}" if machine else "", f"in {category.label}" if category else ""] if x)
    summary = f"{_count(total, 'part')} match{'es' if total == 1 else ''}{(' ' + scope) if scope else ''}." if total else "No parts match this search."
    return Outcome(summary, results, [], ["Part"], total)


HANDLERS: dict[Intent, Callable[[Context], Outcome]] = {
    Intent.PART_SEARCH: part_search, Intent.PART_TO_MACHINE: part_to_machine, Intent.MACHINE_TO_PART: machine_to_part, Intent.PART_TO_CATEGORY: part_to_category,
    Intent.PART_TO_ASSEMBLY: part_to_assembly, Intent.ASSEMBLY_TO_PART: assembly_to_part, Intent.PART_TO_PART: part_to_part, Intent.PART_TO_SUPPLIER: part_to_supplier,
    Intent.PART_TO_DEALER: part_to_dealer, Intent.PART_TO_LOCATION: part_to_location, Intent.PART_TO_INVENTORY: part_to_inventory, Intent.PART_TO_COMPLIANCE: part_to_compliance,
    Intent.PART_PROVENANCE: part_provenance, Intent.PART_GRAPH: part_graph, Intent.MACHINE_GRAPH: machine_graph, Intent.SUPPLIER_GRAPH: supplier_graph,
    Intent.DEALER_GRAPH: dealer_graph, Intent.DATA_QUALITY: data_quality,
}
