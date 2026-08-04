"""Trade execution. See planning/TEAM.md interface 3.

This is the only path a trade takes. The manual endpoint and the LLM both call
execute_trade, so the rules in PLAN.md section 8 cannot drift between them.
"""

from __future__ import annotations

import math

from app.db import (
    delete_position,
    get_cash_balance,
    get_position,
    record_trade,
    set_cash_balance,
    upsert_position,
)
from app.market import normalize_ticker, wait_for_price
from app.services.snapshots import record_now
from app.services.watchlist import add_ticker
from app.state import get_cache

QUANTITY_DECIMALS = 4
SIDES = ("buy", "sell")


class TradeError(Exception):
    """A trade rule violation. The message is shown to the user verbatim."""


async def execute_trade(ticker: str, side: str, quantity: float) -> dict:
    """Validate, fill at the server price, persist, snapshot.

    Adds the ticker to the watchlist and the market source first if it is not
    already tracked, so every position is guaranteed a live price feed.
    """
    symbol = _validate_ticker(ticker)
    side = _validate_side(side)
    quantity = _validate_quantity(quantity)

    # Everything that does not depend on the price is settled first, so a
    # doomed trade neither waits on a tick nor leaves a watchlist entry behind.
    if side == "buy":
        await add_ticker(symbol)
    else:
        _require_shares(symbol, quantity)

    fill_price = await _fill_price(symbol)

    if side == "buy":
        total_cost = _apply_buy(symbol, quantity, fill_price)
    else:
        total_cost = _apply_sell(symbol, quantity, fill_price)

    trade = record_trade(symbol, side, quantity, fill_price)
    record_now(force=True)

    return {
        "ticker": symbol,
        "side": side,
        "quantity": quantity,
        "fill_price": fill_price,
        "total_cost": total_cost,
        "cash_balance": get_cash_balance(),
        "executed_at": trade["executed_at"],
    }


# --- validation -------------------------------------------------------------


def _validate_ticker(raw: str) -> str:
    try:
        return normalize_ticker(raw)
    except ValueError as exc:
        raise TradeError(str(exc)) from exc


def _validate_side(raw: str) -> str:
    side = raw.strip().lower()
    if side not in SIDES:
        raise TradeError(f"Invalid side: {raw!r}. Use 'buy' or 'sell'")
    return side


def _validate_quantity(raw: float) -> float:
    """Quantity must be finite and positive; more than 4dp is rounded away."""
    if not math.isfinite(raw):
        raise TradeError(f"Quantity must be a finite number, got {raw}")

    quantity = round(raw, QUANTITY_DECIMALS)
    if quantity <= 0:
        raise TradeError(f"Quantity must be greater than zero, got {_number(raw)}")
    return quantity


async def _fill_price(symbol: str) -> float:
    """The server's price, waiting up to 2s for a just-added ticker's first tick."""
    try:
        return await wait_for_price(get_cache(), symbol)
    except ValueError as exc:
        raise TradeError(str(exc)) from exc


# --- the two sides ----------------------------------------------------------


def _apply_buy(symbol: str, quantity: float, price: float) -> float:
    """Debit cash and raise the position, averaging the cost basis."""
    total_cost = round(quantity * price, 2)
    cash = get_cash_balance()
    if total_cost > cash:
        raise TradeError(f"Insufficient cash: need ${total_cost:.2f}, have ${cash:.2f}")

    position = get_position(symbol)
    if position:
        held, avg_cost = position["quantity"], position["avg_cost"]
        new_quantity = round(held + quantity, QUANTITY_DECIMALS)
        new_avg_cost = round((held * avg_cost + quantity * price) / new_quantity, 4)
    else:
        new_quantity, new_avg_cost = quantity, price

    upsert_position(symbol, new_quantity, new_avg_cost)
    set_cash_balance(round(cash - total_cost, 2))
    return total_cost


def _require_shares(symbol: str, quantity: float) -> None:
    """Reject a sell of more than is held. There is no shorting."""
    position = get_position(symbol)
    held = position["quantity"] if position else 0.0
    if quantity > held:
        raise TradeError(
            f"Insufficient shares: need {_number(quantity)}, have {_number(held)} {symbol}"
        )


def _apply_sell(symbol: str, quantity: float, price: float) -> float:
    """Credit cash and reduce the position, deleting it when it reaches zero.

    avg_cost is left alone — the remaining shares kept the basis they were
    bought at, and realized P&L is deliberately not tracked (PLAN.md section 7).
    """
    position = get_position(symbol)
    held = position["quantity"]
    remaining = round(held - quantity, QUANTITY_DECIMALS)
    if remaining == 0:
        delete_position(symbol)
    else:
        upsert_position(symbol, remaining, position["avg_cost"])

    proceeds = round(quantity * price, 2)
    set_cash_balance(round(get_cash_balance() + proceeds, 2))
    return proceeds


def _number(value: float) -> str:
    """Format a share count without trailing zeros: 10, 0.5, 1.2345."""
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"
