"""Persistence subsystem for FinAlly: schema, seed data and SQLite access.

Public API:
    BUSY_TIMEOUT_MS     - Milliseconds SQLite waits on a locked database
    DEFAULT_TICKERS     - The ten tickers a new user starts watching
    MONEY_PLACES        - Stored decimal places for cash amounts
    QUANTITY_PLACES     - Stored decimal places for share quantities
    QUANTITY_EPSILON    - Below this, a quantity counts as no holding
    STARTING_CASH       - Cash balance a new user starts with
    add_watchlist_ticker   - Add a ticker to the watchlist, if not already there
    apply_schema           - Create every missing table from schema.sql
    connect                - Open a connection with WAL and a busy timeout
    delete_position        - Remove a position row entirely
    ensure_initialized     - Create and seed the database once per path
    get_chat_messages      - Recent chat messages, oldest first
    get_db_path            - FastAPI dependency yielding the database path
    get_latest_snapshot    - The newest portfolio value snapshot
    get_position           - One position row, or None
    get_positions          - Every held position, ordered by ticker
    get_profile            - The user's profile row
    get_snapshots          - Snapshots newest first, with limit and since
    get_watchlist          - Every watched ticker, ordered by ticker
    insert_chat_message    - Append one chat message
    insert_snapshot        - Append one portfolio value snapshot
    insert_trade           - Append one trade to the append-only audit log
    is_fresh_database      - Whether this database has never been seeded
    is_ticker_watched      - Whether a ticker is on the watchlist
    is_zero                - Whether a quantity is arithmetic residue, not shares
    remove_watchlist_ticker - Remove a ticker from the watchlist
    round_money            - Round a cash amount for storage
    round_quantity         - Round a share quantity for storage
    run_db                 - Run a query function off the event loop
    seed_fresh             - Write the first-launch profile, watchlist and snapshot
    update_cash_balance    - Write the cash balance, rounded to cents
    upsert_position        - Insert or update the position for one ticker
    writing                - Run a write inside BEGIN IMMEDIATE
"""

from .connection import (
    BUSY_TIMEOUT_MS,
    connect,
    ensure_initialized,
    get_db_path,
    run_db,
    writing,
)
from .money import (
    MONEY_PLACES,
    QUANTITY_EPSILON,
    QUANTITY_PLACES,
    is_zero,
    round_money,
    round_quantity,
)
from .queries import (
    add_watchlist_ticker,
    delete_position,
    get_chat_messages,
    get_latest_snapshot,
    get_position,
    get_positions,
    get_profile,
    get_snapshots,
    get_watchlist,
    insert_chat_message,
    insert_snapshot,
    insert_trade,
    is_ticker_watched,
    remove_watchlist_ticker,
    update_cash_balance,
    upsert_position,
)
from .seed import (
    DEFAULT_TICKERS,
    STARTING_CASH,
    apply_schema,
    is_fresh_database,
    seed_fresh,
)

__all__ = [
    "BUSY_TIMEOUT_MS",
    "DEFAULT_TICKERS",
    "MONEY_PLACES",
    "QUANTITY_EPSILON",
    "QUANTITY_PLACES",
    "STARTING_CASH",
    "add_watchlist_ticker",
    "apply_schema",
    "connect",
    "delete_position",
    "ensure_initialized",
    "get_chat_messages",
    "get_db_path",
    "get_latest_snapshot",
    "get_position",
    "get_positions",
    "get_profile",
    "get_snapshots",
    "get_watchlist",
    "insert_chat_message",
    "insert_snapshot",
    "insert_trade",
    "is_fresh_database",
    "is_ticker_watched",
    "is_zero",
    "remove_watchlist_ticker",
    "round_money",
    "round_quantity",
    "run_db",
    "seed_fresh",
    "update_cash_balance",
    "upsert_position",
    "writing",
]
