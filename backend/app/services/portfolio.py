"""Portfolio valuation. See planning/TEAM.md interface 3.

Positions are priced from the shared cache at the moment of the call. The
client recomputes the same numbers live from the SSE stream (PLAN.md section
10); this is the starting point it works from.
"""

from __future__ import annotations

from app.db import get_cash_balance, get_positions
from app.state import get_cache


def build_portfolio() -> dict:
    """Cash, total value and every position priced at the current market."""
    cache = get_cache()
    cash = get_cash_balance()

    positions = [_price_position(row, cache.get_price(row["ticker"])) for row in get_positions()]
    total = cash + sum(position["market_value"] for position in positions)

    return {
        "cash_balance": round(cash, 2),
        "total_value": round(total, 2),
        "positions": positions,
    }


def _price_position(row: dict, price: float | None) -> dict:
    """Value one holding. A ticker with no tick yet falls back to its cost basis.

    Falling back rather than dropping the row keeps the position visible and
    the portfolio total honest during the sub-second gap after a new ticker is
    added but before its first price arrives.
    """
    if price is None:
        price = row["avg_cost"]

    quantity = row["quantity"]
    avg_cost = row["avg_cost"]
    market_value = quantity * price
    unrealized = market_value - quantity * avg_cost

    return {
        "ticker": row["ticker"],
        "quantity": quantity,
        "avg_cost": avg_cost,
        "current_price": price,
        "market_value": round(market_value, 2),
        "unrealized_pnl": round(unrealized, 2),
        "unrealized_pnl_percent": round((price - avg_cost) / avg_cost * 100, 4),
    }
