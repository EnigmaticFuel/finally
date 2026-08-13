"""Portfolio valuation - one pure rule, four callers.

value_portfolio does no I/O: no cache, no connection, no await. That is what
lets the trade transaction call it from inside an executor thread while it holds
the write lock, and what makes it unit-testable with literal dicts. GET
/api/portfolio, the trade-time snapshot, the 30-second snapshot task and reset
all share this one arithmetic.

Derived figures come back unrounded. money.py forbids rounding a derived value
and deliberately exposes no helper for it: the client recomputes these from the
SSE price stream on every frame, so a server-side rounding would not be
authoritative and would visibly disagree with the client's own arithmetic.
"""

from __future__ import annotations

import sqlite3


def value_portfolio(
    cash: float,
    positions: list[sqlite3.Row],
    prices: dict[str, float],
) -> tuple[list[dict[str, object]], float]:
    """Per-position figures and the portfolio total.

    A position whose ticker has no price reports nulls and is excluded from the
    total, so the client renders a dash rather than a fabricated number. Zero is
    a real price a client will happily multiply; absent is not.
    """
    rows: list[dict[str, object]] = []
    total = cash

    for position in positions:
        ticker = position["ticker"]
        quantity = position["quantity"]
        avg_cost = position["avg_cost"]
        price = prices.get(ticker)

        if price is None:
            rows.append(
                {
                    "ticker": ticker,
                    "quantity": quantity,
                    "avg_cost": avg_cost,
                    "current_price": None,
                    "market_value": None,
                    "unrealized_pnl": None,
                    "unrealized_pnl_percent": None,
                }
            )
            continue

        market_value = quantity * price
        cost_basis = quantity * avg_cost
        rows.append(
            {
                "ticker": ticker,
                "quantity": quantity,
                "avg_cost": avg_cost,
                "current_price": price,
                "market_value": market_value,
                "unrealized_pnl": market_value - cost_basis,
                "unrealized_pnl_percent": (market_value - cost_basis) / cost_basis * 100,
            }
        )
        total += market_value

    return rows, total
