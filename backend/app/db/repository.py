"""Every query in the project. See planning/TEAM.md interface 2.

All functions take a trailing user_id, all timestamps out are ISO 8601 UTC
strings, all money and quantities are floats.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime

from .connection import get_connection

DEFAULT_USER_ID = "default"


def utc_now() -> str:
    """Current UTC time as an ISO 8601 string with milliseconds."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def new_id() -> str:
    return str(uuid.uuid4())


# --- cash -------------------------------------------------------------------


def get_cash_balance(user_id: str = DEFAULT_USER_ID) -> float:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
        ).fetchone()
    return row["cash_balance"]


def set_cash_balance(balance: float, user_id: str = DEFAULT_USER_ID) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = ?", (balance, user_id)
        )


# --- positions --------------------------------------------------------------


def _position_dict(row: sqlite3.Row) -> dict:
    return {
        "ticker": row["ticker"],
        "quantity": row["quantity"],
        "avg_cost": row["avg_cost"],
        "updated_at": row["updated_at"],
    }


def get_positions(user_id: str = DEFAULT_USER_ID) -> list[dict]:
    """Every open position, ordered by ticker."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ticker, quantity, avg_cost, updated_at FROM positions"
            " WHERE user_id = ? ORDER BY ticker",
            (user_id,),
        ).fetchall()
    return [_position_dict(row) for row in rows]


def get_position(ticker: str, user_id: str = DEFAULT_USER_ID) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT ticker, quantity, avg_cost, updated_at FROM positions"
            " WHERE user_id = ? AND ticker = ?",
            (user_id, ticker),
        ).fetchone()
    return _position_dict(row) if row else None


def upsert_position(
    ticker: str, quantity: float, avg_cost: float, user_id: str = DEFAULT_USER_ID
) -> None:
    """Insert or replace the position for one ticker, stamping updated_at."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (user_id, ticker) DO UPDATE SET"
            " quantity = excluded.quantity,"
            " avg_cost = excluded.avg_cost,"
            " updated_at = excluded.updated_at",
            (new_id(), user_id, ticker, quantity, avg_cost, utc_now()),
        )


def delete_position(ticker: str, user_id: str = DEFAULT_USER_ID) -> None:
    """Remove a position. A sell that reaches zero deletes the row."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker)
        )


# --- watchlist --------------------------------------------------------------


def get_watchlist(user_id: str = DEFAULT_USER_ID) -> list[str]:
    """Watched tickers, oldest addition first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at, rowid",
            (user_id,),
        ).fetchall()
    return [row["ticker"] for row in rows]


def add_watchlist_ticker(ticker: str, user_id: str = DEFAULT_USER_ID) -> bool:
    """Add a ticker. Returns False if it was already there."""
    with get_connection() as conn:
        inserted = conn.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at)"
            " VALUES (?, ?, ?, ?)",
            (new_id(), user_id, ticker, utc_now()),
        ).rowcount
    return inserted == 1


def remove_watchlist_ticker(ticker: str, user_id: str = DEFAULT_USER_ID) -> bool:
    """Remove a ticker. Returns False if it was not there."""
    with get_connection() as conn:
        deleted = conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker)
        ).rowcount
    return deleted == 1


# --- trades -----------------------------------------------------------------


def record_trade(
    ticker: str, side: str, quantity: float, price: float, user_id: str = DEFAULT_USER_ID
) -> dict:
    """Append to the trade audit log and return the recorded row."""
    trade = {
        "id": new_id(),
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "price": price,
        "executed_at": utc_now(),
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                trade["id"],
                user_id,
                ticker,
                side,
                quantity,
                price,
                trade["executed_at"],
            ),
        )
    return trade


# --- portfolio snapshots ----------------------------------------------------


def record_snapshot(total_value: float, user_id: str = DEFAULT_USER_ID) -> dict:
    """Write a portfolio value point for the P&L chart."""
    snapshot = {"total_value": total_value, "recorded_at": utc_now()}
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)"
            " VALUES (?, ?, ?, ?)",
            (new_id(), user_id, total_value, snapshot["recorded_at"]),
        )
    return snapshot


def get_snapshots(
    limit: int = 500, since: str | None = None, user_id: str = DEFAULT_USER_ID
) -> list[dict]:
    """Snapshots newest first. `since` is an ISO string, exclusive."""
    sql = "SELECT total_value, recorded_at FROM portfolio_snapshots WHERE user_id = ?"
    params: list = [user_id]
    if since:
        sql += " AND recorded_at > ?"
        params.append(since)
    sql += " ORDER BY recorded_at DESC, rowid DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [{"total_value": row["total_value"], "recorded_at": row["recorded_at"]} for row in rows]


def get_latest_snapshot_value(user_id: str = DEFAULT_USER_ID) -> float | None:
    """The most recent total value, so the snapshot task can skip a no-op write."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT total_value FROM portfolio_snapshots WHERE user_id = ?"
            " ORDER BY recorded_at DESC, rowid DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    return row["total_value"] if row else None


# --- chat -------------------------------------------------------------------


def get_chat_messages(limit: int = 100, user_id: str = DEFAULT_USER_ID) -> list[dict]:
    """The most recent `limit` messages, returned oldest first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT role, content, actions, created_at FROM chat_messages"
            " WHERE user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()

    messages = [
        {
            "role": row["role"],
            "content": row["content"],
            "actions": json.loads(row["actions"]) if row["actions"] else None,
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    messages.reverse()
    return messages


def add_chat_message(
    role: str, content: str, actions: dict | None = None, user_id: str = DEFAULT_USER_ID
) -> dict:
    """Store one message. `actions` is JSON-encoded on write."""
    message = {
        "role": role,
        "content": content,
        "actions": actions,
        "created_at": utc_now(),
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                new_id(),
                user_id,
                role,
                content,
                json.dumps(actions) if actions is not None else None,
                message["created_at"],
            ),
        )
    return message
