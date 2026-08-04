"""Watchlist endpoints. Shapes are fixed by PLAN.md section 8.

WatchlistError already carries the status code the rule deserves, so the
translation to HTTP is one line for all three of 400, 404 and 409.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.watchlist import (
    WatchlistError,
    add_ticker,
    build_entry,
    build_watchlist,
    remove_ticker,
    validate_ticker,
)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistRequest(BaseModel):
    ticker: str


@router.get("")
def read_watchlist() -> dict:
    """Every watched ticker with its price and ~60 points of sparkline history."""
    return {"tickers": build_watchlist()}


@router.post("")
async def post_watchlist(request: WatchlistRequest) -> dict:
    """Add a ticker and return its row in the same shape as the list endpoint."""
    try:
        symbol = validate_ticker(request.ticker)
        await add_ticker(symbol)
    except WatchlistError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_entry(symbol)


@router.delete("/{ticker}")
async def delete_watchlist(ticker: str) -> dict:
    """Remove a ticker. Rejected with 409 while a position is held in it."""
    try:
        await remove_ticker(ticker)
    except WatchlistError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"ticker": ticker.strip().upper()}
