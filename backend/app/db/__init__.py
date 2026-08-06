"""Persistence subsystem for FinAlly: schema, seed data and SQLite access.

Public API:
    MONEY_PLACES        - Stored decimal places for cash amounts
    QUANTITY_PLACES     - Stored decimal places for share quantities
    QUANTITY_EPSILON    - Below this, a quantity counts as no holding
    is_zero             - Whether a quantity is arithmetic residue, not shares
    round_money         - Round a cash amount for storage
    round_quantity      - Round a share quantity for storage
"""

from .money import (
    MONEY_PLACES,
    QUANTITY_EPSILON,
    QUANTITY_PLACES,
    is_zero,
    round_money,
    round_quantity,
)

__all__ = [
    "MONEY_PLACES",
    "QUANTITY_EPSILON",
    "QUANTITY_PLACES",
    "is_zero",
    "round_money",
    "round_quantity",
]
