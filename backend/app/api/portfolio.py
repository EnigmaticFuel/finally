"""Portfolio routes: trading against the simulated $10,000 account."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.db import get_db_path
from app.market import MarketDataSource, PriceCache
from app.services import execute_trade
from app.services.portfolio import get_history, get_portfolio, reset_portfolio

from .models import HistoryResponse, PortfolioResponse, TradeRequest, TradeResponse

HISTORY_DEFAULT_LIMIT = 500
HISTORY_MAX_LIMIT = 5000

SINCE_DESCRIPTION = (
    "Return only snapshots at or after this timestamp. It must be in the same"
    " format recorded_at comes back in - the practical instruction is to echo a"
    " recorded_at value straight back. The comparison is a plain string"
    " comparison, so a differently formatted but equally valid ISO 8601 string"
    " does not sort against the stored one."
)


def create_portfolio_router(price_cache: PriceCache, source: MarketDataSource) -> APIRouter:
    """Build the /api/portfolio router bound to a specific cache and source.

    The router is created inside the factory, not at module level, so calling
    this twice (an app plus a test app) does not register the routes twice.

    The source is held for the same reason create_watchlist_router holds one: a
    trade can introduce a symbol the feed has never been told about, and it must
    be registered before anything waits on a price for it.
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
            db_path, price_cache, source, body.ticker, body.side, body.quantity
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

    @router.get("/portfolio", response_model=PortfolioResponse)
    async def read_portfolio(
        db_path: Annotated[Path, Depends(get_db_path)],
    ) -> PortfolioResponse:
        """Report cash, live-valued positions and the total.

        A held ticker with no cached price reports nulls and is left out of
        total_value, so the client renders a dash rather than a wrong number.
        """
        payload = await get_portfolio(db_path, price_cache)
        return PortfolioResponse(**payload)

    @router.get("/portfolio/history", response_model=HistoryResponse)
    async def read_history(
        db_path: Annotated[Path, Depends(get_db_path)],
        limit: Annotated[int, Query(ge=1, le=HISTORY_MAX_LIMIT)] = HISTORY_DEFAULT_LIMIT,
        since: Annotated[str | None, Query(description=SINCE_DESCRIPTION)] = None,
    ) -> HistoryResponse:
        """Portfolio value snapshots, newest first, for the P&L chart.

        `since` must be in the same format recorded_at comes back in: echo a
        recorded_at value straight back. The comparison is a plain string
        comparison, so a differently formatted but equally valid ISO 8601 string
        would not sort against the stored one and would drop boundary rows.

        The bounds are transport validation with exactly one caller, so they
        return FastAPI's 422 rather than a service-layer 400, and cap the row
        count before any query runs.
        """
        snapshots = await get_history(db_path, limit, since)
        return HistoryResponse(snapshots=snapshots)

    @router.post("/portfolio/reset", response_model=PortfolioResponse)
    async def reset(
        db_path: Annotated[Path, Depends(get_db_path)],
    ) -> PortfolioResponse:
        """Return cash to the starting balance and clear every position.

        POST only, with no body and no confirmation token. Being reachable by
        navigation, link prefetch or a crawler is the failure mode that matters
        for a destructive endpoint; the confirmation step belongs to the UI,
        where the user actually clicks.

        The watchlist and the append-only trades log survive, so what was cleared
        stays reconstructible.
        """
        payload = await reset_portfolio(db_path)
        return PortfolioResponse(**payload)

    return router
