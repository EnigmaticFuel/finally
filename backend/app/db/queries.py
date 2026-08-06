"""Every SQL statement in the project, in one module.

Each function is a plain def taking the connection first and a user_id last,
so pytest calls it directly with no event loop and app code reaches it through
the single run_db offload seam in connection.py. Nothing here opens or closes a
connection, and nothing here decides whether a write needs a transaction: the
caller wraps writes in writing() when it wants BEGIN IMMEDIATE.

Every value is bound with a question-mark placeholder. No statement in this
module is assembled by interpolating a value into the SQL text, not for a
ticker, not for a limit, not for a user id.

Ticker arguments pass through app.market.normalize_ticker rather than a second
regex, so the manual trade path and Phase 6's LLM path cannot drift apart on
what counts as a valid symbol.

Rounding happens here, at the write boundary, not in the callers: a quantity
goes in through round_quantity and a cash amount through round_money. Derived
figures are deliberately not rounded - see money.py.

These functions return sqlite3.Row objects; shaping them into response models
belongs to the services that call them.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import uuid

from app.market import normalize_ticker

from .money import round_money, round_quantity
from .seed import DEFAULT_USER_ID

# --- Profile ---


def get_profile(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> sqlite3.Row | None:
    """The user's profile row, or None on a database that was never seeded."""
    return conn.execute(
        "SELECT id, cash_balance, created_at FROM users_profile WHERE id = ?",
        (user_id,),
    ).fetchone()


def update_cash_balance(
    conn: sqlite3.Connection, new_balance: float, user_id: str = DEFAULT_USER_ID
) -> None:
    """Write the cash balance, rounded to cents.

    The rounding is applied here rather than by the caller so that every path
    that moves cash - a manual trade, an LLM-driven trade, a future reset -
    stores the same number of decimal places without having to remember to.
    """
    conn.execute(
        "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
        (round_money(new_balance), user_id),
    )


# --- Positions ---


def get_positions(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> list[sqlite3.Row]:
    """Every held position, ordered by ticker.

    The order is specified rather than left to SQLite's row order so the
    positions table renders the same way on every request.
    """
    return conn.execute(
        "SELECT id, user_id, ticker, quantity, avg_cost, updated_at FROM positions"
        " WHERE user_id = ? ORDER BY ticker",
        (user_id,),
    ).fetchall()


def get_position(
    conn: sqlite3.Connection, ticker: str, user_id: str = DEFAULT_USER_ID
) -> sqlite3.Row | None:
    """One position row, or None when the ticker is not held."""
    return conn.execute(
        "SELECT id, user_id, ticker, quantity, avg_cost, updated_at FROM positions"
        " WHERE user_id = ? AND ticker = ?",
        (user_id, normalize_ticker(ticker)),
    ).fetchone()


def upsert_position(
    conn: sqlite3.Connection,
    ticker: str,
    quantity: float,
    avg_cost: float,
    user_id: str = DEFAULT_USER_ID,
) -> None:
    """Insert or update the position for one ticker.

    Driven by the UNIQUE (user_id, ticker) constraint rather than a
    read-then-branch, so the whole decision is one atomic statement under the
    write lock. avg_cost keeps 4 decimal places because it is a derived ratio,
    not a price the user paid - see money.py.
    """
    conn.execute(
        "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (user_id, ticker) DO UPDATE SET"
        " quantity = excluded.quantity,"
        " avg_cost = excluded.avg_cost,"
        " updated_at = excluded.updated_at",
        (
            str(uuid.uuid4()),
            user_id,
            normalize_ticker(ticker),
            round_quantity(quantity),
            round_quantity(avg_cost),
            _utc_now(),
        ),
    )


def delete_position(
    conn: sqlite3.Connection, ticker: str, user_id: str = DEFAULT_USER_ID
) -> None:
    """Remove a position entirely.

    A sell that takes quantity to zero deletes the row rather than storing a
    zero: there are no zero-quantity positions, which is what lets every reader
    treat the presence of a row as the presence of a holding.
    """
    conn.execute(
        "DELETE FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, normalize_ticker(ticker)),
    )


# --- Trades ---


def insert_trade(
    conn: sqlite3.Connection,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    user_id: str = DEFAULT_USER_ID,
) -> str:
    """Append one trade to the audit log and return its executed_at timestamp.

    The trades table is append-only. It has no reader and no UI panel; it exists
    so trade history survives and so realized P&L stays derivable if a panel is
    ever added. This is therefore the only function in this module that touches
    it - nothing here may edit or erase a trade row.

    The stored executed_at is returned so the trade response reports the
    timestamp that was actually written rather than a second one generated by
    the caller.
    """
    executed_at = _utc_now()
    conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            user_id,
            normalize_ticker(ticker),
            side,
            round_quantity(quantity),
            round_money(price),
            executed_at,
        ),
    )
    return executed_at


# --- Snapshots ---


def insert_snapshot(
    conn: sqlite3.Connection, total_value: float, user_id: str = DEFAULT_USER_ID
) -> None:
    """Append one portfolio value snapshot.

    total_value is stored at full float precision: it is a derived figure the
    client recomputes from the price stream on every frame, so a server-side
    rounding would visibly disagree with the client's own arithmetic.
    """
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)"
        " VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, total_value, _utc_now()),
    )


def get_latest_snapshot(
    conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID
) -> sqlite3.Row | None:
    """The newest snapshot, or None if none has been recorded.

    The background snapshot task compares against this to skip writing a row
    identical to the last one, which keeps an idle portfolio from accumulating
    duplicates.
    """
    return conn.execute(
        "SELECT id, total_value, recorded_at FROM portfolio_snapshots"
        " WHERE user_id = ? ORDER BY recorded_at DESC, rowid DESC LIMIT 1",
        (user_id,),
    ).fetchone()


def get_snapshots(
    conn: sqlite3.Connection,
    limit: int = 500,
    since: str | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> list[sqlite3.Row]:
    """Snapshots newest first, optionally only those at or after `since`.

    `since` is an ISO 8601 UTC string, the same format recorded_at stores, so
    the comparison is a plain string comparison on a sortable format. It is
    bound as a parameter and tested for NULL inside the statement rather than
    branching into a second SQL string.
    """
    return conn.execute(
        "SELECT id, total_value, recorded_at FROM portfolio_snapshots"
        " WHERE user_id = ? AND (? IS NULL OR recorded_at >= ?)"
        " ORDER BY recorded_at DESC, rowid DESC LIMIT ?",
        (user_id, since, since, limit),
    ).fetchall()


# --- Watchlist ---


def get_watchlist(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> list[sqlite3.Row]:
    """Every watched ticker, ordered by ticker.

    Ordering here rather than at insertion time means the API returns the same
    order however the list was built up.
    """
    return conn.execute(
        "SELECT id, user_id, ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY ticker",
        (user_id,),
    ).fetchall()


def add_watchlist_ticker(
    conn: sqlite3.Connection, ticker: str, user_id: str = DEFAULT_USER_ID
) -> bool:
    """Add a ticker to the watchlist, returning whether a row was added.

    Already present is a no-op rather than an error, handled by the UNIQUE
    (user_id, ticker) constraint so a concurrent duplicate cannot raise either.

    This function is why the whole query surface lands in Phase 1: the trade
    path calls it so that trading an unwatched ticker adds it to the watchlist,
    which is what holds the invariant that every position has a live price feed.
    """
    cursor = conn.execute(
        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT (user_id, ticker) DO NOTHING",
        (str(uuid.uuid4()), user_id, normalize_ticker(ticker), _utc_now()),
    )
    return cursor.rowcount == 1


def remove_watchlist_ticker(
    conn: sqlite3.Connection, ticker: str, user_id: str = DEFAULT_USER_ID
) -> bool:
    """Remove a ticker from the watchlist, returning whether a row was removed.

    False means the ticker was not watched, which the caller turns into a 404.
    Refusing to remove a ticker the user holds a position in is a business rule
    and lives at the service seam where the 409 is raised, not here.
    """
    cursor = conn.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, normalize_ticker(ticker)),
    )
    return cursor.rowcount == 1


def is_ticker_watched(
    conn: sqlite3.Connection, ticker: str, user_id: str = DEFAULT_USER_ID
) -> bool:
    """Whether a ticker is currently on the watchlist."""
    row = conn.execute(
        "SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, normalize_ticker(ticker)),
    ).fetchone()
    return row is not None


# --- Chat ---


def insert_chat_message(
    conn: sqlite3.Connection,
    role: str,
    content: str,
    actions: str | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> None:
    """Append one chat message.

    actions holds a JSON string for an assistant message that executed trades or
    watchlist changes, and None - stored as SQL NULL - for a user message.
    Serializing it is the caller's job, so this module never imports json.
    """
    conn.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, role, content, actions, _utc_now()),
    )


def get_chat_messages(
    conn: sqlite3.Connection, limit: int = 100, user_id: str = DEFAULT_USER_ID
) -> list[sqlite3.Row]:
    """The most recent messages, returned oldest first.

    The limit keeps the newest messages while the result reads oldest first,
    which is the order the chat panel repopulates in after a reload. Hence the
    subquery: newest-first to apply the limit, then flipped back.
    """
    return conn.execute(
        "SELECT id, role, content, actions, created_at FROM ("
        "  SELECT id, role, content, actions, created_at, rowid FROM chat_messages"
        "  WHERE user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?"
        ") ORDER BY created_at ASC, rowid ASC",
        (user_id, limit),
    ).fetchall()


# --- Internal ---


def _utc_now() -> str:
    """Current time as an ISO 8601 UTC string, the format every *_at column uses."""
    return dt.datetime.now(dt.UTC).isoformat()
