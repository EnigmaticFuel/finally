"""Watchlist routes: read, add and remove the tickers the user watches."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from app.db import get_db_path
from app.market import MarketDataSource, PriceCache
from app.services.watchlist import TickerQuote, add, quote, read_watchlist, remove

from .models import WatchlistAddRequest, WatchlistResponse, WatchlistTickerOut


def create_watchlist_router(price_cache: PriceCache, source: MarketDataSource) -> APIRouter:
    """Build the /api/watchlist router bound to a specific cache and source.

    The router is created inside the factory, not at module level, so calling
    this twice (an app plus a test app) does not register the routes twice.

    The handlers catch nothing and validate nothing: app/services/watchlist.py
    owns every rule and the app-level exception handlers own the translation
    into 400/404/409, so these are only wiring.
    """
    router = APIRouter(prefix="/api", tags=["watchlist"])

    @router.get("/watchlist", response_model=WatchlistResponse)
    async def get_watchlist(
        db_path: Annotated[Path, Depends(get_db_path)],
    ) -> dict[str, object]:
        """Every watched ticker with its live price and sparkline history."""
        return {"tickers": await read_watchlist(db_path, price_cache)}

    @router.post("/watchlist", response_model=WatchlistTickerOut)
    async def post_watchlist(
        body: WatchlistAddRequest,
        db_path: Annotated[Path, Depends(get_db_path)],
    ) -> TickerQuote:
        """Add a ticker and answer with the row the client should render.

        The raw body value goes to the service unvalidated. The service
        normalizes it and the returned quote is keyed on the normalized symbol,
        so a lowercase request answers with the uppercase form.
        """
        entry = await add(db_path, source, body.ticker)
        return quote(price_cache, entry.ticker)

    @router.delete("/watchlist/{ticker}", status_code=204, response_model=None)
    async def delete_watchlist(
        ticker: str,
        db_path: Annotated[Path, Depends(get_db_path)],
    ) -> None:
        """Remove a ticker. 409 if a position is held in it, 404 if unwatched.

        response_model=None is explicit so the None return is not turned into a
        serialized body alongside the 204.
        """
        await remove(db_path, ticker)

    return router
