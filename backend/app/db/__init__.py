"""Persistence subsystem for FinAlly: schema, seed data and SQLite access.

Public API:
    DEFAULT_TICKERS     - The ten tickers a new user starts watching
    MONEY_PLACES        - Stored decimal places for cash amounts
    QUANTITY_PLACES     - Stored decimal places for share quantities
    QUANTITY_EPSILON    - Below this, a quantity counts as no holding
    STARTING_CASH       - Cash balance a new user starts with
    apply_schema        - Create every missing table from schema.sql
    is_fresh_database   - Whether this database has never been seeded
    is_zero             - Whether a quantity is arithmetic residue, not shares
    round_money         - Round a cash amount for storage
    round_quantity      - Round a share quantity for storage
    seed_fresh          - Write the first-launch profile, watchlist and snapshot
"""

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
    "DEFAULT_TICKERS",
    "MONEY_PLACES",
    "QUANTITY_EPSILON",
    "QUANTITY_PLACES",
    "STARTING_CASH",
    "apply_schema",
    "is_fresh_database",
    "is_zero",
    "round_money",
    "round_quantity",
    "seed_fresh",
]
