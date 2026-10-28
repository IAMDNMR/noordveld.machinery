"""Spark's guided order journey. Every turn is validated against the graph; an order is created only by the explicit confirm turn, through the same
checkout.place() the Parts Store uses (same permission, same stock reservation, same idempotency)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.app_access import require_app
from app.api.dependencies import CheckoutSvc, Parts, get_orders_repository, require
from app.api.routes.orders import _call
from app.api.routes.profile import Store
from app.api.routes.spark import get_spark_llm
from app.api.routes.spark_voice import limit_spark
from app.llm import LLMClient
from app.schemas.spark_order import OrderTurn
from app.services.order_journey import OrderJourney
from app.services.orders import OrdersRepository, User

router = APIRouter(prefix="/spark", tags=["spark"], dependencies=[Depends(require_app("parts_store")), Depends(limit_spark)])
Buyer = Annotated[User, Depends(require("orders.place"))]


def get_journey(checkout: CheckoutSvc, parts: Parts, repo: Annotated[OrdersRepository, Depends(get_orders_repository)],
                llm: Annotated[LLMClient | None, Depends(get_spark_llm)], user: Buyer, store: Store) -> OrderJourney:
    saved = store.get(user.id)  # present only when the user consented to store a profile
    return OrderJourney(checkout, repo, parts, llm, profile=saved["profile"] if saved else None)


@router.post("/order")
def order_turn(body: OrderTurn, user: Buyer, journey: Annotated[OrderJourney, Depends(get_journey)]) -> dict:
    return _call(journey.turn, user, body)
