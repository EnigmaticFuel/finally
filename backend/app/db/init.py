"""Lazy database initialization and default seed data.

init_db() runs on every startup. It creates the file, applies the schema and
inserts the defaults only where they are missing, so an existing database with
real trades in it is left untouched.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .connection import get_connection
from .repository import DEFAULT_USER_ID, new_id, utc_now

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

INITIAL_CASH = 10000.0

DEFAULT_TICKERS = [
    "AAPL",
    "GOOGL",
    "MSFT",
    "AMZN",
    "TSLA",
    "NVDA",
    "META",
    "JPM",
    "V",
    "NFLX",
]


def init_db() -> None:
    """Create the schema and seed defaults if absent. Idempotent."""
    with get_connection() as conn:
        conn.executescript(SCHEMA_PATH.read_text())
        _seed(conn)


def _seed(conn: sqlite3.Connection) -> None:
    """Insert the default profile, watchlist and opening snapshot if missing."""
    now = utc_now()

    conn.execute(
        "INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        (DEFAULT_USER_ID, INITIAL_CASH, now),
    )

    conn.executemany(
        "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        [(new_id(), DEFAULT_USER_ID, ticker, now) for ticker in DEFAULT_TICKERS],
    )

    # One opening point so the P&L chart is never empty on first launch.
    existing = conn.execute(
        "SELECT 1 FROM portfolio_snapshots WHERE user_id = ? LIMIT 1", (DEFAULT_USER_ID,)
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)"
            " VALUES (?, ?, ?, ?)",
            (new_id(), DEFAULT_USER_ID, INITIAL_CASH, now),
        )
