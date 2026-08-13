"""Portfolio valuation - one pure rule, four callers.

value_portfolio does no I/O: no cache, no connection, no await. That is what
lets the trade transaction call it from inside an executor thread while it holds
the write lock, and what makes it unit-testable with literal dicts. GET
/api/portfolio, the trade-time snapshot, the 30-second snapshot task and reset
all share this one arithmetic.

Derived figures come back unrounded. money.py forbids rounding a derived value
and deliberately exposes no helper for it: the client recomputes these from the
SSE price stream on every frame, so a server-side rounding would not be
authoritative and would visibly disagree with the client's own arithmetic.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.db import (
    STARTING_CASH,
    delete_position,
    get_positions,
    get_profile,
    get_snapshots,
    insert_snapshot,
    run_db,
    update_cash_balance,
    writing,
)
from app.market import PriceCache

# --- Valuation ---


def value_portfolio(
    cash: float,
    positions: list[sqlite3.Row],
    prices: dict[str, float],
) -> tuple[list[dict[str, object]], float]:
    """Per-position figures and the portfolio total.

    A position whose ticker has no price reports nulls and is excluded from the
    total, so the client renders a dash rather than a fabricated number. Zero is
    a real price a client will happily multiply; absent is not.
    """
    rows: list[dict[str, object]] = []
    total = cash

    for position in positions:
        ticker = position["ticker"]
        quantity = position["quantity"]
        avg_cost = position["avg_cost"]
        price = prices.get(ticker)

        if price is None:
            rows.append(
                {
                    "ticker": ticker,
                    "quantity": quantity,
                    "avg_cost": avg_cost,
                    "current_price": None,
                    "market_value": None,
                    "unrealized_pnl": None,
                    "unrealized_pnl_percent": None,
                }
            )
            continue

        market_value = quantity * price
        cost_basis = quantity * avg_cost
        rows.append(
            {
                "ticker": ticker,
                "quantity": quantity,
                "avg_cost": avg_cost,
                "current_price": price,
                "market_value": market_value,
                "unrealized_pnl": market_value - cost_basis,
                "unrealized_pnl_percent": (market_value - cost_basis) / cost_basis * 100,
            }
        )
        total += market_value

    return rows, total


# --- Reading ---


def _read_portfolio(conn: sqlite3.Connection) -> tuple[float, list[sqlite3.Row]]:
    """Cash balance and position rows, from one connection.

    Both reads share a connection so cash and positions come from a single WAL
    snapshot rather than two, which is what makes the total arithmetic over one
    consistent view. No writing() wrapper: a WAL reader already sees a consistent
    snapshot, so wrapping a read would serialize readers behind writers for
    nothing.
    """
    return get_profile(conn)["cash_balance"], get_positions(conn)


async def get_portfolio(db_path: Path, cache: PriceCache) -> dict[str, object]:
    """Cash, live-valued positions and the total, in PortfolioResponse's shape.

    The prices mapping is built here rather than inside the executor thread, so
    the database work never depends on state that moves every 500ms. The
    valuation itself runs over at most a handful of rows, so calling the one
    shared pure rule on the event loop costs nothing and keeps the thread
    function trivial.
    """
    cash, rows = await run_db(db_path, _read_portfolio)
    prices = {ticker: update.price for ticker, update in cache.get_all().items()}
    positions, total = value_portfolio(cash, rows, prices)
    return {"cash_balance": cash, "total_value": total, "positions": positions}


async def get_history(
    db_path: Path,
    limit: int = 500,
    since: str | None = None,
) -> list[dict[str, object]]:
    """Portfolio value snapshots, newest first, in SnapshotOut's shape.

    recorded_at is passed through byte-for-byte as stored. The SQL compares
    `since` as a plain string against the same format, so a second timestamp
    format introduced here would not sort against the stored one and would
    silently drop boundary rows. The rows arrive ordered; they are not re-sorted.
    """
    rows = await run_db(db_path, get_snapshots, limit, since)
    return [
        {"total_value": row["total_value"], "recorded_at": row["recorded_at"]} for row in rows
    ]


# --- Reset ---


def _apply_reset(conn: sqlite3.Connection) -> None:
    """Clear the portfolio and restore the starting cash, as one transaction.

    One BEGIN IMMEDIATE covers everything below, so a concurrent trade cannot
    land between the clearing and the cash write and leave a holding behind with
    restored cash. Any raise inside rolls the whole unit back, which is why no
    compensating undo code belongs here.

    There is no bulk-delete query and app/db/ is frozen for this phase, so
    composing the existing per-ticker delete inside a loop is the intended shape,
    not a missing query function.

    The recorded value is STARTING_CASH because nothing is held by then, and
    value_portfolio(STARTING_CASH, [], prices) returns exactly STARTING_CASH for
    any prices mapping - the one valuation rule is satisfied here rather than
    bypassed, which is also why this path takes no cache: an unused collaborator
    argument would be a lie about the dependency.

    Nothing outside the positions table and the profile cash balance is touched.
    The watchlist, the append-only trades log and chat_messages survive: a user
    who resets a portfolio has not asked to lose the tickers they curated or the
    audit trail of what they did, and a reset is not a sale, so no trade row is
    written.
    """
    with writing(conn):
        for position in get_positions(conn):
            delete_position(conn, position["ticker"])
        update_cash_balance(conn, STARTING_CASH)
        insert_snapshot(conn, STARTING_CASH)


async def reset_portfolio(db_path: Path) -> dict[str, object]:
    """Return the portfolio to its starting state and report the result.

    The body is the same three keys get_portfolio returns, so the client's
    post-action refetch rule needs no special case. The snapshot is always
    written: the unchanged-value skip is the 30-second task's rule alone, so a
    second consecutive reset correctly appends a second row at the same value.
    """
    await run_db(db_path, _apply_reset)
    return {"cash_balance": STARTING_CASH, "total_value": STARTING_CASH, "positions": []}
