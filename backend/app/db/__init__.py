"""Database layer for FinAlly. See planning/TEAM.md interface 2.

Synchronous sqlite3. Every *_at value returned is an ISO 8601 UTC string;
money and quantities are floats. Nothing outside this package opens the
database file or writes SQL.
"""

from .connection import get_connection, get_db_path
from .init import DEFAULT_TICKERS, INITIAL_CASH, init_db
from .repository import (
    DEFAULT_USER_ID,
    add_chat_message,
    add_watchlist_ticker,
    delete_position,
    get_cash_balance,
    get_chat_messages,
    get_latest_snapshot_value,
    get_position,
    get_positions,
    get_snapshots,
    get_watchlist,
    record_snapshot,
    record_trade,
    remove_watchlist_ticker,
    set_cash_balance,
    upsert_position,
)

__all__ = [
    "DEFAULT_TICKERS",
    "DEFAULT_USER_ID",
    "INITIAL_CASH",
    "add_chat_message",
    "add_watchlist_ticker",
    "delete_position",
    "get_cash_balance",
    "get_chat_messages",
    "get_connection",
    "get_db_path",
    "get_latest_snapshot_value",
    "get_position",
    "get_positions",
    "get_snapshots",
    "get_watchlist",
    "init_db",
    "record_snapshot",
    "record_trade",
    "remove_watchlist_ticker",
    "set_cash_balance",
    "upsert_position",
]
