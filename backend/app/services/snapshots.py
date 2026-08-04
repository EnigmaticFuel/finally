"""Portfolio value snapshots. See planning/TEAM.md interface 3.

Two writers feed the P&L chart: a 30-second background loop, and every trade.
The loop skips a write when the value has not moved, so an idle portfolio does
not accumulate thousands of identical rows overnight.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from app.db import get_latest_snapshot_value, record_snapshot
from app.services.portfolio import build_portfolio

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL_SECONDS = 30.0


def record_now(force: bool = False) -> None:
    """Write a snapshot of the current portfolio value.

    Skips the write when the value is unchanged, unless `force` is set. Trades
    force it: a market-price fill barely moves total value, so an unforced
    write would drop exactly the step the chart is meant to show.
    """
    total_value = build_portfolio()["total_value"]
    if not force and get_latest_snapshot_value() == total_value:
        return
    record_snapshot(total_value)


@asynccontextmanager
async def snapshot_task():
    """Run the 30-second snapshot loop for the lifetime of the app."""
    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def _loop() -> None:
    """Snapshot every 30 seconds until cancelled.

    A failed write is logged and the loop continues: losing one point off the
    P&L chart is not a reason to stop recording for the rest of the session.
    """
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL_SECONDS)
        try:
            record_now()
        except Exception:
            logger.exception("Portfolio snapshot failed")
