"""Trade execution - the published seam, and the one transaction behind it.

execute_trade is the only door into a trade. The manual route calls it and
Phase 6's LLM path calls it with the same arguments, so an LLM-supplied quantity
cannot bypass what a manual one is held to. Its signature is a cross-phase
contract; see .planning/phases/03-portfolio-watchlist-apis/03-SEAM-CONTRACT.md.

Validation runs cheap checks, then registration, then price, then balance: a
malformed quantity returns immediately rather than after a two-second wait, the
traded symbol is registered with the running feed once it is known to be worth
trading, and the price wait only ever runs for input that could actually fill
and for a symbol that now has a producer.

The prices used for the trade-time snapshot are captured before the transaction
opens and passed in as a plain dict, so _apply_trade never touches PriceCache.
That keeps the thread function pure, keeps the transaction off state that moves
every 500ms, and makes the snapshot value agree with the fill the user was just
quoted.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.db import (
    add_watchlist_ticker,
    delete_position,
    get_position,
    get_positions,
    get_profile,
    insert_snapshot,
    insert_trade,
    is_zero,
    round_money,
    round_quantity,
    run_db,
    update_cash_balance,
    upsert_position,
    writing,
)
from app.market import MarketDataSource, PriceCache, normalize_ticker, wait_for_price

from .errors import TradeError
from .portfolio import value_portfolio

PRICE_WAIT_SECONDS = 2.0
VALID_SIDES = ("buy", "sell")


@dataclass(frozen=True, slots=True)
class TradeResult:
    """What a filled trade reports back, in PLAN.md section 8's shape.

    fill_price is the server's price, captured before the transaction opened and
    never re-read afterwards. total_cost is the raw product, unrounded: it is a
    derived figure the client recomputes, so rounding it here would disagree with
    the client's own arithmetic.
    """

    ticker: str
    side: str
    quantity: float
    fill_price: float
    total_cost: float
    cash_balance: float
    executed_at: str


def validate_quantity(quantity: float) -> float:
    """Validate a share quantity and return it, raising TradeError otherwise.

    The check order is load-bearing. round(float('inf'), 4) returns inf rather
    than raising, so inf != inf is False and a precision check placed first lets
    an infinite quantity straight through. isfinite must run first.
    """
    if not math.isfinite(quantity):
        raise TradeError(f"Quantity must be a finite number, got {quantity}")
    if quantity <= 0:
        raise TradeError(f"Quantity must be greater than zero, got {quantity}")
    if round_quantity(quantity) != quantity:
        raise TradeError(f"Quantity may have at most 4 decimal places, got {quantity}")
    return quantity


async def execute_trade(
    db_path: Path,
    cache: PriceCache,
    source: MarketDataSource,
    ticker: str,
    side: str,
    quantity: float,
) -> TradeResult:
    """Execute one market order and return the fill.

    The published service seam. No FastAPI object crosses it, so Phase 6 passes
    exactly what the router passes.

    source is the running feed the traded symbol is registered with. The seam is
    symmetric with watchlist.add: both writers that can introduce a new symbol
    hold the feed they must register it with. Registration precedes the price
    wait because an unregistered symbol has no producer, so the wait would always
    expire and trading an unwatched ticker would be unreachable.

    Two calls are wrapped, and both wrap exactly one named call each. This is
    translation at a boundary, not defensive programming: normalize_ticker and
    wait_for_price live in the frozen app/market/ module and raise the plain
    ValueError Phase 1's style used, each with a documented user-facing message.
    Converting them into the taxonomy here is what lets a ValueError reaching the
    router mean a defect rather than a user error. Nothing else is wrapped -
    validate_quantity already raises TradeError, and a wider block would report a
    genuine fault inside the transaction as a 400.
    """
    try:
        ticker = normalize_ticker(ticker)
    except ValueError as exc:
        raise TradeError(str(exc)) from exc
    if side not in VALID_SIDES:
        raise TradeError(f"Side must be 'buy' or 'sell', got {side!r}")
    validate_quantity(quantity)

    await source.add_ticker(ticker)

    try:
        fill_price = await wait_for_price(cache, ticker, timeout=PRICE_WAIT_SECONDS)
    except ValueError as exc:
        raise TradeError(str(exc)) from exc
    prices = {symbol: update.price for symbol, update in cache.get_all().items()}

    filled = await run_db(db_path, _apply_trade, ticker, side, quantity, fill_price, prices)

    return TradeResult(
        ticker=ticker,
        side=side,
        quantity=quantity,
        fill_price=fill_price,
        total_cost=filled["total_cost"],
        cash_balance=filled["cash_balance"],
        executed_at=filled["executed_at"],
    )


def _apply_trade(
    conn: sqlite3.Connection,
    ticker: str,
    side: str,
    quantity: float,
    fill_price: float,
    prices: dict[str, float],
) -> dict[str, object]:
    """The whole trade as one immediate-mode write transaction.

    add_watchlist_ticker runs first so that a trade rejected further down rolls
    the row back with everything else - a rejected trade must leave no watchlist
    row, no cash change and no snapshot.

    Every value handed to a query function is raw. Rounding happens once at the
    queries.py write boundary, and round_money appears here only inside the
    sufficiency comparison, never on a value being stored.

    A sell leaves avg_cost alone: selling part of a holding does not change the
    cost basis per share, and a sell to zero deletes the row so no cost basis
    ever survives with no shares behind it. The remainder is tested with is_zero
    rather than an equality, because repeated fractional sells leave residue far
    below a share that an equality would strand as an unsellable dust holding.
    """
    with writing(conn):
        add_watchlist_ticker(conn, ticker)
        profile = get_profile(conn)
        position = get_position(conn, ticker)

        cash = profile["cash_balance"]
        cost = fill_price * quantity

        held = position["quantity"] if position else 0.0

        if side == "buy":
            if round_money(cost) > round_money(cash):
                raise TradeError(f"Insufficient cash: need ${cost:.2f}, have ${cash:.2f}")
            new_cash = cash - cost
            held_avg = position["avg_cost"] if position else 0.0
            new_quantity = held + quantity
            upsert_position(
                conn,
                ticker,
                new_quantity,
                (held * held_avg + quantity * fill_price) / new_quantity,
            )
        else:
            remaining = held - quantity
            if remaining < 0 and not is_zero(remaining):
                raise TradeError(f"Insufficient shares: need {quantity:g} {ticker}, have {held:g}")
            new_cash = cash + cost
            if is_zero(remaining):
                delete_position(conn, ticker)
            else:
                upsert_position(conn, ticker, remaining, position["avg_cost"])

        update_cash_balance(conn, new_cash)
        executed_at = insert_trade(conn, ticker, side, quantity, fill_price)
        total_value = value_portfolio(new_cash, get_positions(conn), prices)[1]
        insert_snapshot(conn, total_value)

    return {"executed_at": executed_at, "cash_balance": new_cash, "total_cost": cost}
