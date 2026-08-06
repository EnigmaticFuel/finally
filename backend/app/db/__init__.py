"""Persistence subsystem for FinAlly: schema, seed data and SQLite access.

Public API:
    BUSY_TIMEOUT_MS     - Milliseconds SQLite waits on a locked database
    DEFAULT_TICKERS     - The ten tickers a new user starts watching
    MONEY_PLACES        - Stored decimal places for cash amounts
    QUANTITY_PLACES     - Stored decimal places for share quantities
    QUANTITY_EPSILON    - Below this, a quantity counts as no holding
    STARTING_CASH       - Cash balance a new user starts with
    apply_schema        - Create every missing table from schema.sql
    connect             - Open a connection with WAL and a busy timeout
    delete_position     - Remove a position row entirely
    ensure_initialized  - Create and seed the database once per path
    get_db_path         - FastAPI dependency yielding the database path
    get_latest_snapshot - The newest portfolio value snapshot
    get_position        - One position row, or None
    get_positions       - Every held position, ordered by ticker
    get_profile         - The user's profile row
    get_snapshots       - Snapshots newest first, with limit and since
    insert_snapshot     - Append one portfolio value snapshot
    insert_trade        - Append one trade to the append-only audit log
    is_fresh_database   - Whether this database has never been seeded
    is_zero             - Whether a quantity is arithmetic residue, not shares
    round_money         - Round a cash amount for storage
    round_quantity      - Round a share quantity for storage
    run_db              - Run a query function off the event loop
    seed_fresh          - Write the first-launch profile, watchlist and snapshot
    update_cash_balance - Write the cash balance, rounded to cents
    upsert_position     - Insert or update the position for one ticker
    writing             - Run a write inside BEGIN IMMEDIATE
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
    delete_position,
    get_latest_snapshot,
    get_position,
    get_positions,
    get_profile,
    get_snapshots,
    insert_snapshot,
    insert_trade,
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
    "apply_schema",
    "connect",
    "delete_position",
    "ensure_initialized",
    "get_db_path",
    "get_latest_snapshot",
    "get_position",
    "get_positions",
    "get_profile",
    "get_snapshots",
    "insert_snapshot",
    "insert_trade",
    "is_fresh_database",
    "is_zero",
    "round_money",
    "round_quantity",
    "run_db",
    "seed_fresh",
    "update_cash_balance",
    "upsert_position",
    "writing",
]
