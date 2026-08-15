"""The watchlist seam: reading, adding and removing watched tickers.

add and remove are the doors both the HTTP router and, in Phase 6, the LLM path
call, which is why every rule lives here rather than in a route: the ticker
shape, the held-position rejection and the unwatched rejection. Their signatures
are a cross-phase contract; see
.planning/phases/03-portfolio-watchlist-apis/03-SEAM-CONTRACT.md.

The watchlist is database state, not cache state. A ticker the cache has never
seen is still watched, so it comes back with nulls rather than being filtered
out or zeroed: $0.00 is a real price a client will happily render and multiply.

This module composes the query functions and writes no statement text of its
own, so there is one place where a ticker reaches SQLite and it binds
placeholders.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.db.connection import run_db, writing
from app.db.queries import (
    add_watchlist_ticker,
    get_position,
    get_watchlist,
    remove_watchlist_ticker,
)
from app.db.seed import DEFAULT_TICKERS
from app.market import MarketDataSource, PriceCache, normalize_ticker

from .errors import Conflict, NotFound, TradeError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TickerQuote:
    """One watchlist row shaped for the client.

    The three nullable fields move together: all null means the cache has never
    seen this ticker. A flat ticker reports 0.0, never null.
    """

    ticker: str
    price: float | None
    open_price: float | None
    change_from_open_percent: float | None
    history: list[float]


@dataclass(frozen=True, slots=True)
class WatchlistEntry:
    """What the add seam knows: the normalized symbol, and whether a row was new.

    added is what lets Phase 6 say "added PYPL" rather than "PYPL was already on
    your watchlist" without a second query.
    """

    ticker: str
    added: bool


# --- Reading ---


def quote(cache: PriceCache, ticker: str) -> TickerQuote:
    """Render one ticker's live figures, or nulls when it has no price.

    The one place the null rule lives. Every number is passed through untouched:
    PriceCache.update already rounds the stored price and PriceUpdate already
    rounds the percentage, and rounding a derived value again on the way out
    would be a second rule that quietly disagrees with the first.
    """
    update = cache.get(ticker)
    if update is None:
        return TickerQuote(ticker, None, None, None, [])
    return TickerQuote(
        ticker=ticker,
        price=update.price,
        open_price=update.open_price,
        change_from_open_percent=update.change_from_open_percent,
        history=cache.get_history(ticker),
    )


async def read_watchlist(db_path: Path, cache: PriceCache) -> list[TickerQuote]:
    """Every watched ticker with whatever the cache knows about it.

    get_watchlist already orders ascending by ticker, so this imposes no
    ordering of its own and the API answers the same way however the list was
    built up.
    """
    rows = await run_db(db_path, get_watchlist)
    return [quote(cache, row["ticker"]) for row in rows]


# --- Startup ---


async def startup_tickers(db_path: Path) -> list[str]:
    """The tickers the market data source is started from on every boot.

    Reads the frozen query layer and modifies nothing. run_db calls
    ensure_initialized before the read, so a first launch creates the schema,
    seeds the ten defaults and reads them straight back through the same door
    every request uses - there is no second initialization path here.

    The order is get_watchlist's ascending-by-ticker order, not seed order.

    The fallback covers a watchlist the user emptied on purpose. It gives the
    simulator something to produce so the stream and the health probe stay
    meaningful, and it writes no watchlist rows, so the empty watchlist stays
    empty on the next read.
    """
    rows = await run_db(db_path, get_watchlist)
    return [row["ticker"] for row in rows] or list(DEFAULT_TICKERS)


# --- Adding ---


async def add(db_path: Path, source: MarketDataSource, ticker: str) -> WatchlistEntry:
    """Add a ticker to the watchlist and register it with the running feed.

    The database write comes first and the source registration second (D-09).
    The watchlist row is the durable record and startup_tickers starts the source
    from those rows on every boot, so a failed registration self-heals on the
    next start, whereas an orphaned feed would not.

    An already-watched ticker is a success, not an error: add_watchlist_ticker
    no-ops on conflict, and re-registering with the source is a harmless no-op
    that repairs a ticker whose earlier registration failed.

    normalize_ticker is wrapped because it lives in the frozen app/market/ module
    and raises a plain ValueError. Translating that one named call into the
    taxonomy at the seam is what lets a ValueError reaching the router mean a
    defect rather than a bad symbol.
    """
    try:
        symbol = normalize_ticker(ticker)
    except ValueError as exc:
        raise TradeError(str(exc)) from exc
    added = await run_db(db_path, _add_row, symbol)
    await source.add_ticker(symbol)
    logger.info("Watchlist: added ticker %s", symbol)
    return WatchlistEntry(symbol, added)


def _add_row(conn: sqlite3.Connection, ticker: str) -> bool:
    """Write the watchlist row inside one immediate-mode write transaction."""
    with writing(conn):
        return add_watchlist_ticker(conn, ticker)


# --- Removing ---


async def remove(db_path: Path, ticker: str) -> None:
    """Remove a ticker from the watchlist.

    Deliberately does not touch the market source (D-08). The simulator keeps
    producing a price for an unwatched ticker until the process restarts, which
    is harmless: startup_tickers starts the source from the watchlist rows on
    every boot, so the removed ticker is gone from the next run's feed, and the
    client renders from this API rather than from the stream's key set.

    normalize_ticker is wrapped for the same reason it is in add: one frozen call
    raising a plain ValueError, translated into the taxonomy at the seam.
    """
    try:
        symbol = normalize_ticker(ticker)
    except ValueError as exc:
        raise TradeError(str(exc)) from exc
    await run_db(db_path, _remove_checked, symbol)
    logger.info("Watchlist: removed ticker %s", symbol)


def _remove_checked(conn: sqlite3.Connection, ticker: str) -> None:
    """Reject a held ticker, then drop the row, both in one transaction.

    Check and removal share one BEGIN IMMEDIATE (D-08), so a position created
    concurrently cannot slip between them. Both raises happen inside the block,
    which is required rather than incidental: writing() rolls back and re-raises,
    so a rejected removal commits nothing.

    A position row existing at all is the held test. A sell that reaches zero
    drops its row, so no zero-quantity position survives to need an epsilon.

    Held is checked first, so a ticker the user holds answers 409 rather than
    404 even though it is watched.
    """
    with writing(conn):
        if get_position(conn, ticker) is not None:
            raise Conflict(
                f"Cannot remove {ticker} while you hold a position in it."
                f" Sell your {ticker} shares first."
            )
        if not remove_watchlist_ticker(conn, ticker):
            raise NotFound(f"{ticker} is not on your watchlist")
