"""Schema application and first-launch seed data.

DEFAULT_TICKERS is named here rather than imported from
app.market.seed_prices.SEED_PRICES. The default watchlist is user data;
SEED_PRICES is simulator tuning that also feeds the Massive path. Adding a
ticker there for simulator realism must not silently change what every new user
sees on first launch, so the two lists are deliberately independent even though
they currently hold the same ten symbols.

Seeding is gated on a single question, asked by is_fresh_database: does
users_profile hold a row? A database that already has one is left completely
alone. The consequence is deliberate - a user who removes every ticker from
their watchlist keeps an empty watchlist across restarts, because re-seeding on
every startup would quietly overwrite an action they took on purpose.

seed_fresh takes a connection and does only the writing, with the
fresh-or-not decision left to the caller. That separation is why
is_fresh_database is a distinct function: Phase 3's Reset Portfolio can call
seed_fresh directly rather than duplicating the starting cash constant.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import uuid
from pathlib import Path

from .money import round_money

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

DEFAULT_USER_ID = "default"
STARTING_CASH = 10000.0

DEFAULT_TICKERS: tuple[str, ...] = (
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
)


def apply_schema(conn: sqlite3.Connection) -> None:
    """Create every table that is missing. A no-op on an initialized database."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def is_fresh_database(conn: sqlite3.Connection) -> bool:
    """Whether this database has never been seeded.

    One question, one row count. A partially populated database - schema
    present, profile present, watchlist emptied by the user - is a legitimate
    user state, not corruption, and answers False.
    """
    row = conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()
    return row[0] == 0


def seed_fresh(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> None:
    """Write the first-launch state: one profile, ten tickers, one snapshot.

    The snapshot is written at seed time so the P&L chart has a data point on
    first paint rather than an empty panel until the first trade.
    """
    now = _utc_now()
    cash = round_money(STARTING_CASH)

    conn.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        (user_id, cash, now),
    )
    conn.executemany(
        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        [(str(uuid.uuid4()), user_id, ticker, now) for ticker in DEFAULT_TICKERS],
    )
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)"
        " VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, cash, now),
    )


def _utc_now() -> str:
    """Current time as an ISO 8601 UTC string, the format every *_at column uses."""
    return dt.datetime.now(dt.UTC).isoformat()
