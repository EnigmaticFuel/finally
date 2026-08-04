"""Watchlist business logic. See planning/TEAM.md interface 3.

The watchlist lives in two places that must stay in step: the database row the
user sees, and the market source that produces its prices. Every mutation here
updates both.
"""

from __future__ import annotations

from app.db import add_watchlist_ticker, get_position, get_watchlist, remove_watchlist_ticker
from app.market import normalize_ticker
from app.state import get_cache, get_source


class WatchlistError(Exception):
    """A watchlist rule violation. The message is shown to the user verbatim."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def validate_ticker(raw: str) -> str:
    """Normalize a symbol, raising WatchlistError(400) if it is malformed."""
    try:
        return normalize_ticker(raw)
    except ValueError as exc:
        raise WatchlistError(str(exc), 400) from exc


async def add_ticker(ticker: str) -> None:
    """Add a symbol to the watchlist and start its price feed.

    Already-watched symbols are a no-op, not an error: adding a ticker twice is
    a harmless request and the end state is what the user asked for.
    """
    symbol = validate_ticker(ticker)
    if add_watchlist_ticker(symbol):
        await get_source().add_ticker(symbol)


async def remove_ticker(ticker: str) -> None:
    """Remove a symbol from the watchlist and stop its price feed.

    Refuses while a position is held, which is what keeps the invariant that
    every position has a live feed (PLAN.md section 7).
    """
    symbol = validate_ticker(ticker)

    if get_position(symbol):
        raise WatchlistError(
            f"Cannot remove {symbol} from the watchlist while you hold a position in it", 409
        )
    if not remove_watchlist_ticker(symbol):
        raise WatchlistError(f"{symbol} is not on the watchlist", 404)

    await get_source().remove_ticker(symbol)


def build_watchlist() -> list[dict]:
    """Every watched ticker with its live price and sparkline history."""
    return [build_entry(ticker) for ticker in get_watchlist()]


def build_entry(ticker: str) -> dict:
    """One watchlist row: price, session baseline and ~60 points, oldest first."""
    cache = get_cache()
    update = cache.get(ticker)
    return {
        "ticker": ticker,
        "price": update.price if update else None,
        "open_price": update.open_price if update else None,
        "change_from_open_percent": update.change_from_open_percent if update else 0.0,
        "history": cache.get_history(ticker),
    }
