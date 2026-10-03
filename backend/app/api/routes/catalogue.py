"""Catalogue filter options and cart quote."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import Cart, Catalogue
from app.schemas.cart import Quote, QuoteRequest
from app.schemas.catalogue import CatalogueFilters

router = APIRouter(tags=["catalogue"])


@router.get("/catalogue/filters", response_model=CatalogueFilters)
def get_filters(service: Catalogue) -> CatalogueFilters:
    return service.filters()


@router.post("/cart/quote", response_model=Quote)
def quote_cart(request: QuoteRequest, service: Cart) -> Quote:
    """Price a cart. Read-only: nothing is stored and no order is placed."""
    return service.quote(request)
