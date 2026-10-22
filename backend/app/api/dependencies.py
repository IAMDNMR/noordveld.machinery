"""FastAPI dependencies: one GraphClient per process, services built per request."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.agent.service import AgentService
from app.core.config import get_settings
from app.graph.client import GraphClient
from app.graph.repositories.catalogue import CatalogueRepository
from app.graph.repositories.parts import PartRepository
from app.graph.repositories.intelligence import IntelligenceRepository
from app.intelligence.service import IntelligenceService
from app.intelligence.workspace import Entities, Overview, PartWorkspace
from app.llm import LLMClient, create_llm
from app.services.cart import CartService
from app.services.catalogue import CatalogueService
from app.services.parts import PartService
from app.services.site import SiteService


@lru_cache
def get_graph() -> GraphClient:
    return GraphClient(get_settings())


@lru_cache
def get_llm() -> LLMClient | None:
    return create_llm(get_settings())


Graph = Annotated[GraphClient, Depends(get_graph)]


def get_part_service(graph: Graph) -> PartService:
    return PartService(PartRepository(graph))


def get_catalogue_service(graph: Graph) -> CatalogueService:
    return CatalogueService(CatalogueRepository(graph))


def get_cart_service(graph: Graph) -> CartService:
    return CartService(PartRepository(graph))


Parts = Annotated[PartService, Depends(get_part_service)]
Catalogue = Annotated[CatalogueService, Depends(get_catalogue_service)]
Cart = Annotated[CartService, Depends(get_cart_service)]


def get_question_service(
    graph: Graph, llm: Annotated[LLMClient | None, Depends(get_llm)]
) -> IntelligenceService:
    return IntelligenceService(IntelligenceRepository(graph), PartRepository(graph), llm)


def get_workspace(graph: Graph) -> PartWorkspace:
    return PartWorkspace(IntelligenceRepository(graph))


def get_overview(graph: Graph) -> Overview:
    return Overview(IntelligenceRepository(graph))


Questions = Annotated[IntelligenceService, Depends(get_question_service)]
Workspaces = Annotated[PartWorkspace, Depends(get_workspace)]
Overviews = Annotated[Overview, Depends(get_overview)]


def get_agent(graph: Graph, llm: Annotated[LLMClient | None, Depends(get_llm)]) -> AgentService:
    return AgentService(graph, llm)


Agents = Annotated[AgentService, Depends(get_agent)]


def get_site(graph: Graph) -> SiteService:
    return SiteService(graph)


Sites = Annotated[SiteService, Depends(get_site)]


def get_entities(graph: Graph) -> Entities:
    return Entities(IntelligenceRepository(graph))


EntityDetails = Annotated[Entities, Depends(get_entities)]


# ── accounts and the order workflow ───────────────────────────────────────────────────────────────
from fastapi import Cookie, HTTPException, Request  # noqa: E402

from app.core.session import COOKIE, verify  # noqa: E402
from app.services.checkout import CheckoutService  # noqa: E402
from app.services.orders import GraphOrdersRepository, OrdersRepository, OrdersService, User  # noqa: E402


def get_orders_repository(graph: Graph) -> OrdersRepository:
    return GraphOrdersRepository(graph)


def get_orders(repo: Annotated[OrdersRepository, Depends(get_orders_repository)]) -> OrdersService:
    return OrdersService(repo)


OrdersSvc = Annotated[OrdersService, Depends(get_orders)]


def get_checkout(
    repo: Annotated[OrdersRepository, Depends(get_orders_repository)], orders: OrdersSvc
) -> CheckoutService:
    return CheckoutService(repo, orders)


CheckoutSvc = Annotated[CheckoutService, Depends(get_checkout)]


def current_user(
    orders: OrdersSvc,
    request: Request,
    nv_session: Annotated[str | None, Cookie(alias=COOKIE)] = None,
    nv_studio_session: Annotated[str | None, Cookie(alias="nv_studio_session")] = None,
) -> User:
    """The signed-in user, resolved on the backend from the signed cookie and the user record. Never from a role the browser sends."""
    studio_only = request.url.path.startswith("/api/v1/studio-session")
    studio_route = request.url.path.startswith(
        ("/api/v1/design-studio", "/api/v1/domain-knowledge")
    ) or (request.url.path == "/api/v1/workspace" and request.query_params.get("studio") == "1")
    use_studio = studio_only or (studio_route and nv_studio_session is not None)
    token = nv_studio_session if use_studio else nv_session
    secret = ("studio:" if use_studio else "") + get_settings().session_secret
    user_id = verify(token, secret)
    user = None
    # The local demo account is already resolved by studio-session/demo. Reuse
    # that server-owned record briefly so each Studio request need not contact
    # the commerce graph. Deployed and commerce sessions always resolve normally.
    from app.core.demo_access import local_demo_request
    from app.design_studio.preview_identity import cached, remember

    local_studio = use_studio and local_demo_request(request)
    if local_studio:
        user = cached(user_id) if user_id else None
    if user is None:
        user = orders.user(user_id)
        if user is not None and local_studio:
            remember(user)
    if user is None:
        raise HTTPException(
            status_code=401, detail={"code": "not_signed_in", "message": "Sign in to continue."}
        )
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require(permission: str):
    """A route guard: 403 unless the signed-in user's role has `permission`."""

    def guard(user: CurrentUser) -> User:
        if not user.can(permission):
            raise HTTPException(
                status_code=403,
                detail={"code": "forbidden", "message": "Your role does not allow this."},
            )
        return user

    return guard
