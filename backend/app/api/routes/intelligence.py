"""Parts Intelligence endpoints. Handlers parse the request and call a service; nothing else."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import EntityDetails, Overviews, Questions, Workspaces
from app.schemas.intelligence import (
    AssemblyItem, ComplianceItem, DealerItem, EntityDetail, FitmentItem, GraphView, Insight, InventoryView, Kpis, PartOverview, ProvenanceReport, QueryRequest, QueryResponse,
    RelatedItem, SupplierItem,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.post("/query", response_model=QueryResponse)
def ask(request: QueryRequest, service: Questions) -> QueryResponse:
    """Answer a natural-language question from the graph. A model may interpret and word it; it never writes the query."""
    return service.query(request)


@router.get("/suggestions")
def suggestions(service: Overviews) -> list[dict[str, str]]:
    return service.suggestions()


@router.get("/kpis", response_model=Kpis)
def kpis(service: Overviews) -> Kpis:
    return service.kpis()


@router.get("/parts/{key}", response_model=PartOverview)
def overview(key: str, ws: Workspaces) -> PartOverview:
    return ws.overview(key)


@router.get("/parts/{key}/fitment", response_model=list[FitmentItem])
def fitment(key: str, ws: Workspaces) -> list[FitmentItem]:
    return ws.fitment(key)


@router.get("/parts/{key}/relationships", response_model=list[RelatedItem])
def relationships(key: str, ws: Workspaces) -> list[RelatedItem]:
    return ws.related(key)


@router.get("/parts/{key}/assemblies", response_model=list[AssemblyItem])
def assemblies(key: str, ws: Workspaces) -> list[AssemblyItem]:
    return ws.assemblies(key)


@router.get("/parts/{key}/suppliers", response_model=list[SupplierItem])
def suppliers(key: str, ws: Workspaces) -> list[SupplierItem]:
    return ws.suppliers(key)


@router.get("/parts/{key}/dealers", response_model=list[DealerItem])
def dealers(key: str, ws: Workspaces) -> list[DealerItem]:
    return ws.dealers(key)


@router.get("/parts/{key}/inventory", response_model=InventoryView)
def inventory(key: str, ws: Workspaces) -> InventoryView:
    return ws.inventory(key)


@router.get("/parts/{key}/compliance", response_model=list[ComplianceItem])
def compliance(key: str, ws: Workspaces) -> list[ComplianceItem]:
    return ws.compliance(key)


@router.get("/parts/{key}/provenance", response_model=ProvenanceReport)
def provenance(key: str, ws: Workspaces) -> ProvenanceReport:
    return ws.provenance(key)


@router.get("/parts/{key}/insights", response_model=list[Insight])
def insights(key: str, ws: Workspaces) -> list[Insight]:
    return ws.insights(key)


@router.get("/parts/{key}/graph", response_model=GraphView)
def graph(key: str, ws: Workspaces) -> GraphView:
    return ws.graph(key)


@router.get("/entities/{kind}/{entity_id}", response_model=EntityDetail)
def entity(kind: str, entity_id: str, service: EntityDetails) -> EntityDetail:
    """Detail of a graph node that is not a part (machine, supplier, dealer, warehouse, assembly, compliance, category)."""
    return service.detail(kind.upper(), entity_id)
