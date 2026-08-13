"""The background portfolio value recorder.

This is the only writer in the app that runs because time passed rather than
because a request arrived. That is what gives the P&L chart a continuous line
rather than a scatter of trade events: a portfolio nobody trades still moves
with the market, and without this loop that movement is never recorded.

The whole read-compare-write sits inside one writing() block. This module is the
second writer of the cash and position rows the trade path also touches, so
reading them outside a transaction could pair a pre-trade cash balance with a
post-trade position and append a chart point for a portfolio that never existed.
That is why the reads here are wrapped even though connection.py notes that
reads normally are not: this is not a read, it is a read-modify-write.

Nothing here catches anything. A loop that logged and continued would look alive
while recording nothing, and the gap it left would render as a flat portfolio
rather than a broken recorder.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path

from app.db.connection import run_db, writing
from app.db.money import round_money
from app.db.queries import get_latest_snapshot, get_positions, get_profile, insert_snapshot
from app.market import PriceCache

from .portfolio import value_portfolio

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL_SECONDS = 30.0


# --- Recording ---


def _record_if_changed(conn: sqlite3.Connection, prices: dict[str, float]) -> bool:
    """Append one snapshot unless the cents-rounded total is unchanged.

    "Unchanged" is round_money equality against the newest existing row, reusing
    money.py rather than introducing a second precision rule. The comparison is
    the only place rounding appears: insert_snapshot is handed the raw total,
    because money.py forbids rounding a derived value the client recomputes.

    A missing latest row means write, not skip. There is nothing to compare
    against, so recording is the honest answer, and it removes an entire class of
    "the chart is empty and nothing ever fills it" failure for one is-None test.

    The flag is set inside the block and returned after it, so the transaction
    has exactly one exit and the read-compare-write reads as one bounded unit.
    """
    with writing(conn):
        profile = get_profile(conn)
        total = value_portfolio(profile["cash_balance"], get_positions(conn), prices)[1]
        latest = get_latest_snapshot(conn)
        written = latest is None or round_money(total) != round_money(latest["total_value"])
        if written:
            insert_snapshot(conn, total)
    return written


async def record_snapshot(db_path: Path, cache: PriceCache) -> bool:
    """Record the portfolio's current value, reporting whether a row was added.

    Separately callable rather than inlined into the loop, so every test drives a
    real write without waiting for the interval and without patching it.

    Prices are captured here and passed inward as a plain dict (D-02): the
    executor function never touches PriceCache, which keeps it pure over its
    arguments and testable with literals.
    """
    prices = {ticker: update.price for ticker, update in cache.get_all().items()}
    return await run_db(db_path, _record_if_changed, prices)


# --- The loop ---


async def snapshot_loop(db_path: Path, cache: PriceCache) -> None:
    """Record the portfolio value every SNAPSHOT_INTERVAL_SECONDS, forever.

    The sleep comes first and the write second, which is load-bearing rather than
    stylistic: an app that lives for milliseconds never reaches a write, so a
    test entering and leaving the lifespan cannot append rows to whatever
    database it was pointed at. That is one of two independent mitigations, the
    other being the test fixture's own db_path override.

    Cancellation is how this ends. The lifespan that created the task cancels it,
    and asyncio.CancelledError propagates out untouched.
    """
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL_SECONDS)
        if await record_snapshot(db_path, cache):
            logger.debug("Snapshot recorded for %s", db_path)
