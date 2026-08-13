"""Portfolio routes: trading against the simulated $10,000 account."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from app.db import get_db_path
from app.market import PriceCache
from app.services import execute_trade

from .models import TradeRequest, TradeResponse


def create_portfolio_router(price_cache: PriceCache) -> APIRouter:
    """Build the /api/portfolio router bound to a specific cache.

    The router is created inside the factory, not at module level, so calling
    this twice (an app plus a test app) does not register the routes twice.
    """
    router = APIRouter(prefix="/api", tags=["portfolio"])

    @router.post("/portfolio/trade", response_model=TradeResponse)
    async def post_trade(
        body: TradeRequest,
        db_path: Annotated[Path, Depends(get_db_path)],
    ) -> TradeResponse:
        """Execute a market order and return the fill.

        The handler catches nothing. Validation and business rules live behind
        execute_trade, and the app-level exception handlers own the translation
        into 400/404/409, so this route is only wiring.
        """
        result = await execute_trade(
            db_path, price_cache, body.ticker, body.side, body.quantity
        )
        return TradeResponse(
            ticker=result.ticker,
            side=result.side,
            quantity=result.quantity,
            fill_price=result.fill_price,
            total_cost=result.total_cost,
            cash_balance=result.cash_balance,
            executed_at=result.executed_at,
        )

    return router
