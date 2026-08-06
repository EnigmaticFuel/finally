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
    ensure_initialized  - Create and seed the database once per path
    get_db_path         - FastAPI dependency yielding the database path
    is_fresh_database   - Whether this database has never been seeded
    is_zero             - Whether a quantity is arithmetic residue, not shares
    round_money         - Round a cash amount for storage
    round_quantity      - Round a share quantity for storage
    run_db              - Run a query function off the event loop
    seed_fresh          - Write the first-launch profile, watchlist and snapshot
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
    "ensure_initialized",
    "get_db_path",
    "is_fresh_database",
    "is_zero",
    "round_money",
    "round_quantity",
    "run_db",
    "seed_fresh",
    "writing",
]
