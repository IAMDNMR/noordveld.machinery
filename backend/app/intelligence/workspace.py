"""The part investigation workspace: one method per tab. Every number is counted in Neo4j or Python, never produced by a model."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.core.exceptions import NotFoundError
from app.graph.repositories.intelligence import IntelligenceRepository
from app.intelligence.handlers import INTELLIGENCE_ROUTE, humanize
from app.intelligence.provenance import LABELS, data_class
from app.schemas.intelligence import (
    Action, AssemblyItem, Component, ComplianceItem, DealerItem, FitmentItem, GraphEdge, GraphNode, GraphView, IdentificationNeed, Insight, InventoryView,
    Kpis, PartOverview, PartStatus, ProvenanceReport, RelatedItem, RelationshipSource, SupplierItem, WarehouseItem,
)

STORE_ROUTE = "/parts-store"
RELATION_LABEL = {"CO_ORDERED_WITH": "Often ordered together", "RELATED_COMPONENT": "Related component", "SAME_NAME_GROUP_AS": "Shares a part name"}
CAPS = {"machines": 15, "assemblies": 10, "suppliers": 10, "dealers": 10, "warehouses": 6, "compliance": 6, "related": 10}


def part_status(profile: dict | None, identification: list[dict]) -> PartStatus:
    if any(i.get("needed") or i.get("reason") for i in identification):
        return PartStatus(code="IDENTIFICATION_REQUIRED", label="Identification required")
    if profile is None:
        return PartStatus(code="UNVERIFIED", label="Unverified")
    if profile.get("part_status") == "VERIFIED":
        return PartStatus(code="VERIFIED", label="Verified")
    return PartStatus(code="OTHER", label=humanize(profile.get("part_status")) or "Unverified")


class PartWorkspace:
    def __init__(self, repo: IntelligenceRepository) -> None:
        self._repo = repo

    def _core(self, key: str) -> dict[str, Any]:
        core = self._repo.part_core(key)
        if core is None:
            raise NotFoundError("Part", key)
        return core

    def overview(self, key: str) -> PartOverview:
        core = self._core(key)
        p, profile, ident = core["part"], core["profile"], core["identification"]
        status = part_status(profile, ident)
        pn = p["part_number"]
        actions: list[Action] = []
        orderable = profile.get("orderable") if profile else None
        if status.code == "VERIFIED" and orderable is True:
            actions.append(Action(kind="parts_store", label="View in Parts Store", href=f"{STORE_ROUTE}/{quote(pn)}"))
        if status.code == "IDENTIFICATION_REQUIRED":
            actions.append(Action(kind="identify", label="Identify part", href=f"{INTELLIGENCE_ROUTE}?part={quote(pn)}&tab=fitment"))
        return PartOverview(
            part_id=p["part_id"], part_number=pn, name=p["name"], description=p.get("spec_note_source"), category=p.get("category"), subcategory=p.get("subcategory"),
            manufacturer=p.get("brand"), origin_plant=p.get("origin_plant"), status=status, data_class=data_class(p.get("data_status")),
            identification=[IdentificationNeed(model_code=i.get("model_code"), reason=i.get("reason"), needed=i.get("needed")) for i in ident if i.get("needed") or i.get("reason")],
            source=p.get("source_name"), last_updated=p.get("last_updated"), orderable=orderable, actions=actions,
        )

    def _id(self, key: str) -> str:
        return self._core(key)["part"]["part_id"]

    def fitment(self, key: str) -> list[FitmentItem]:
        return [FitmentItem(model_code=r["model_code"], name=r["name"], machine_type=r["machine_type"], family=r["family"], fitment_status=humanize(r["fitment_status"]),
                            condition_note=r["condition_note"], data_class=data_class(r["data_status"])) for r in self._repo.fitment(self._id(key))]

    def related(self, key: str) -> list[RelatedItem]:
        return [RelatedItem(part_number=r["part_number"], name=r["name"], category=r["category"], relation=r["relation"], relation_label=RELATION_LABEL.get(r["relation"], humanize(r["relation"]) or ""),
                            interchangeability_status=None if r["interchangeability_status"] in (None, "UNKNOWN") else humanize(r["interchangeability_status"]),
                            data_class=data_class(r["data_status"])) for r in self._repo.related(self._id(key))]

    def assemblies(self, key: str) -> list[AssemblyItem]:
        return [AssemblyItem(assembly_id=r["assembly_id"], name=r["name"], quantity=r["quantity"], bom_status=humanize(r["bom_status"]), identified_by=r["identified_by"], component_count=r["component_count"],
                             components=[Component(**c) for c in r["components"]], data_class=data_class(r["data_status"])) for r in self._repo.assemblies(self._id(key))]

    def suppliers(self, key: str) -> list[SupplierItem]:
        return [SupplierItem(supplier_id=r["supplier_id"], name=r["name"], city=r["city"], country_code=r["country_code"], is_primary=r["is_primary"], lead_time_days=r["lead_time_days"],
                             categories=r["categories"], data_class=data_class(r["data_status"])) for r in self._repo.suppliers(self._id(key))]

    @staticmethod
    def _dealer(r: dict) -> DealerItem:
        return DealerItem(dealer_id=r["dealer_id"], name=r["name"], city=r["city"], country_code=r["country_code"], pickup_allowed=r["pickup_allowed"], stocking_status=humanize(r["stocking_status"]),
                          available=r["available"], data_class=data_class(r["data_status"]))

    def dealers(self, key: str) -> list[DealerItem]:
        return [self._dealer(r) for r in self._repo.dealers(self._id(key))]

    def inventory(self, key: str) -> InventoryView:
        pid = self._id(key)
        wh, dl = self._repo.warehouses(pid), self._repo.dealers(pid)
        if not wh and not dl:
            return InventoryView(state="NOT_CONNECTED", total_available=None, warehouses=[], dealers=[], data_class="NOT_CONNECTED", note="No stock is connected for this part. Availability is unknown, which is not the same as zero.")
        known = [r["available"] for r in wh if r["available"] is not None]
        classes = {data_class(r["data_status"]) for r in [*wh, *dl]}
        demo = "SYNTHETIC_DEMO" in classes
        return InventoryView(
            state="CONNECTED", total_available=sum(known) if known else None,
            warehouses=[WarehouseItem(warehouse_id=r["warehouse_id"], name=r["name"], city=r["city"], country_code=r["country_code"], available=r["available"], stock_status=humanize(r["stock_status"]),
                                      data_class=data_class(r["data_status"])) for r in wh],
            dealers=[self._dealer(r) for r in dl], data_class="SYNTHETIC_DEMO" if demo else (next(iter(classes)) if len(classes) == 1 else "UNKNOWN"),
            note="Stock figures are demonstration data, not live inventory." if demo else None,
        )

    def compliance(self, key: str) -> list[ComplianceItem]:
        return [ComplianceItem(requirement=r["requirement"], standard=r["standard"], certification=r["certification"], certificate_status=humanize(r["certificate_status"]),
                               valid_until=r["valid_until"], covers=r["covers"], data_class=data_class(r["data_status"])) for r in self._repo.compliance(self._id(key))]

    def provenance(self, key: str) -> ProvenanceReport:
        core = self._core(key)
        p, profile = core["part"], core["profile"]
        rels = self._repo.relationships(p["part_id"])
        sources = [RelationshipSource(relationship=r["relationship"], connected_label=r["other_label"], count=r["n"], data_class=data_class(r["data_status"])) for r in rels]
        status = part_status(profile, core["identification"])
        limits: list[str] = []
        if any(s.data_class == "SYNTHETIC_DEMO" for s in sources):
            limits.append("Stock, price, supplier, dealer, assembly and compliance links are demonstration data, not enterprise truth.")
        if not p.get("authoritative_flag"):
            limits.append("This record is not marked authoritative for ordering.")
        if any(s.data_class == "UNKNOWN" for s in sources):
            limits.append("Some relationships do not state where they came from.")
        limits.append("Absent relationships mean the data is not connected, not that the fact is false.")
        return ProvenanceReport(
            classification=data_class(p.get("data_status")), source_name=p.get("source_name"), source_file=p.get("source_file"), source_sheet=p.get("source_sheet"),
            source_record_id=p.get("source_record_id"), confidence=humanize(p.get("confidence")), authoritative=bool(p.get("authoritative_flag")),
            verification=status.label, relationship_sources=sources, limitations=limits, last_updated=p.get("last_updated"),
        )

    def insights(self, key: str) -> list[Insight]:
        pid = self._id(key)
        c = self._repo.counts(pid)
        wh, dl, sp = self._repo.warehouses(pid), self._repo.dealers(pid), self._repo.suppliers(pid)
        countries = {r["country_code"] for r in [*wh, *dl, *sp] if r["country_code"]}
        units = [r["available"] for r in wh if r["available"] is not None]

        def count(k: str, label: str, detail: str) -> Insight:
            return Insight(key=k, label=label, value=c[k], detail=detail, state="present" if c[k] else "gap")

        out = [
            count("machines", "Machines associated", "Machines this part fits (FITS)"),
            count("related_parts", "Related parts", "Linked by explicit relationships; none implies interchangeability"),
            count("assemblies", "Assemblies", "Assemblies containing this part (PART_OF)"),
            count("suppliers", "Supplier relationships", "Suppliers connected through SUPPLIED_BY"),
            count("dealers", "Dealer stocking records", "Dealers connected through STOCKED_BY"),
            count("compliance", "Compliance requirements", "Requirements connected through HAS_COMPLIANCE"),
            Insight(key="connected", label="Connected entities", value=sum(c[k] for k in ("machines", "related_parts", "assemblies", "suppliers", "dealers", "warehouses", "compliance", "legacy_references")),
                    detail="Direct relationships to other entities"),
            Insight(key="countries", label="Countries with a connected location", value=len(countries) if countries else None, detail=", ".join(sorted(countries)) or "No location connected",
                    state="present" if countries else "not_connected"),
            Insight(key="stock_units", label="Warehouse units recorded", value=sum(units) if units else None, detail="Sum of recorded warehouse quantities; unknown when none are recorded",
                    state="present" if units else "not_connected"),
        ]
        gaps = [i.label for i in out if i.state == "gap"]
        if gaps:
            out.append(Insight(key="gaps", label="Data gaps", value=len(gaps), detail=", ".join(gaps), state="gap"))
        return out

    def graph(self, key: str) -> GraphView:
        core = self._core(key)
        p = core["part"]
        view, counts = self._repo.graph_view(p["part_id"]), self._repo.counts(p["part_id"])
        root = f"PART:{p['part_id']}"
        nodes = [GraphNode(id=root, label=p["part_number"], kind="PART", part_number=p["part_number"])]
        edges: list[GraphEdge] = []
        groups = (("machines", "MACHINE", "machines"), ("assemblies", "ASSEMBLY", "assemblies"), ("suppliers", "SUPPLIER", "suppliers"), ("dealers", "DEALER", "dealers"),
                  ("warehouses", "WAREHOUSE", "warehouses"), ("compliance", "COMPLIANCE", "compliance"), ("related", "PART", "related_parts"))
        truncated = False
        for field, kind, count_key in groups:
            items = view.get(field, [])
            truncated = truncated or counts.get(count_key, 0) > CAPS[field]
            for it in items:
                nid = f"{kind}:{it['id']}"
                if not any(n.id == nid for n in nodes):  # a part linked by two relationship types is one node with two edges
                    nodes.append(GraphNode(id=nid, label=it["label"] or it["id"], kind=kind, part_number=it["label"] if kind == "PART" else None))
                edges.append(GraphEdge(source=root, target=nid, type=it["type"], data_class=data_class(it["ds"])))
        if view.get("category"):
            cat = view["category"]
            nodes.append(GraphNode(id=f"CATEGORY:{cat['id']}", label=cat["label"], kind="CATEGORY"))
            edges.append(GraphEdge(source=root, target=f"CATEGORY:{cat['id']}", type="IN_CATEGORY", data_class=data_class(cat["ds"])))
        return GraphView(nodes=nodes, edges=edges, truncated=truncated)


class Overview:
    """Whole-graph figures and suggested questions. Both come from the graph; nothing here names a catalogue entry."""

    def __init__(self, repo: IntelligenceRepository) -> None:
        self._repo = repo

    def kpis(self) -> Kpis:
        k = self._repo.kpis()
        total = k["nodes"] + k["relationships"]
        covered = k["nodes_with_provenance"] + k["relationships_with_provenance"]
        return Kpis(parts=k["parts"], machines=k["machines"], fitments=k["fitments"], suppliers=k["suppliers"], dealers=k["dealers"], assemblies=k["assemblies"], relationships=k["relationships"],
                    nodes=k["nodes"], synthetic_nodes=k["synthetic_nodes"], provenance_coverage_pct=round(100 * covered / total, 1) if total else 0.0)

    def suggestions(self) -> list[dict[str, str]]:
        s = self._repo.suggestion_seeds()
        if not s:
            return []
        part, machine, supplier, dealer, assembly = s["part"], s["machine"], s["supplier"], s["dealer"], s["assembly"]
        return [
            {"category": "Part Discovery", "question": f"Find {part}"},
            {"category": "Machine & Fitment", "question": f"Which parts fit the {machine}?"},
            {"category": "Machine & Fitment", "question": f"Which machines use {part}?"},
            {"category": "Part Relationships", "question": f"Which parts are related to {part}?"},
            {"category": "Supplier Intelligence", "question": f"Which suppliers are connected to {part}?"},
            {"category": "Supplier Intelligence", "question": f"Which parts does {supplier} supply?"},
            {"category": "Dealer Intelligence", "question": f"Which dealers stock {part}?"},
            {"category": "Dealer Intelligence", "question": f"What does {dealer} stock?"},
            {"category": "Assembly Intelligence", "question": f"What assemblies contain {part}?"},
            {"category": "Assembly Intelligence", "question": f"Which parts are in {assembly}?"},
            {"category": "Geographic Intelligence", "question": f"Where is {part} available?"},
            {"category": "Compliance", "question": f"Which compliance requirements apply to {part}?"},
            {"category": "Inventory", "question": f"What is the stock of {part}?"},
            {"category": "Network", "question": f"Show the relationships for {part}."},
            {"category": "Provenance", "question": f"What is the provenance of {part}?"},
            {"category": "Provenance", "question": "Where is the catalogue data incomplete?"},
        ]
