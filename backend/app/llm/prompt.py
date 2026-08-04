"""Prompt assembly: system instructions, live portfolio context, history.

The model sees the same numbers the user sees, so its analysis is grounded in
the current session rather than in whatever the conversation happened to say.
"""

from __future__ import annotations

from app.db import get_chat_messages, get_watchlist
from app.services.portfolio import build_portfolio
from app.state import get_cache

HISTORY_LIMIT = 20

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant embedded in a simulated trading workstation.

Your job:
- Analyze the user's portfolio composition, risk concentration and profit and loss.
- Suggest trades and explain your reasoning with the numbers you were given.
- Execute trades when the user asks for them or agrees to a suggestion.
- Manage the watchlist proactively when it helps the user.

How to answer:
- Be concise and data driven. Reference the actual figures in the portfolio context.
- Put the trades you want executed in the trades list and watchlist edits in the
  watchlist_changes list. They are executed automatically, so only include an action
  when you intend it to happen. Never claim an action you did not put in a list.
- Tickers are 1 to 5 uppercase letters. Quantities are positive numbers.
- Buying requires sufficient cash and selling requires sufficient shares. There is no
  shorting and no margin.
- Always respond with valid JSON matching the required schema. All three fields are
  required: use empty lists when there is nothing to execute."""


def build_messages(user_message: str) -> list[dict]:
    """The full message list for the model: system, context, history, new message."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": portfolio_context()},
        *history_messages(user_message),
        {"role": "user", "content": user_message},
    ]


def history_messages(user_message: str) -> list[dict]:
    """Recent conversation turns, oldest first.

    The chat endpoint persists the user's message before generating a reply, so
    the newest stored row is usually this same message. Drop it here and let
    build_messages append it once.
    """
    history = get_chat_messages(limit=HISTORY_LIMIT)
    if history and history[-1]["role"] == "user" and history[-1]["content"] == user_message:
        history = history[:-1]
    return [{"role": message["role"], "content": message["content"]} for message in history]


def portfolio_context() -> str:
    """Cash, positions with P&L, watchlist with live prices, and total value."""
    portfolio = build_portfolio()
    lines = [
        "Current portfolio (live figures, all amounts in USD):",
        f"Cash balance: {portfolio['cash_balance']:.2f}",
        f"Total portfolio value: {portfolio['total_value']:.2f}",
        _positions_block(portfolio["positions"]),
        _watchlist_block(),
    ]
    return "\n".join(lines)


def _positions_block(positions: list[dict]) -> str:
    if not positions:
        return "Positions: none"
    rows = [
        f"  {p['ticker']}: quantity {p['quantity']:g}, avg cost {p['avg_cost']:.2f}, "
        f"price {p['current_price']:.2f}, market value {p['market_value']:.2f}, "
        f"unrealized P&L {p['unrealized_pnl']:.2f} ({p['unrealized_pnl_percent']:.2f}%)"
        for p in positions
    ]
    return "\n".join(["Positions:", *rows])


def _watchlist_block() -> str:
    cache = get_cache()
    rows = []
    for ticker in get_watchlist():
        update = cache.get(ticker)
        if update is None:
            rows.append(f"  {ticker}: no price yet")
        else:
            rows.append(
                f"  {ticker}: price {update.price:.2f}, "
                f"change since open {update.change_from_open_percent:.2f}%"
            )
    if not rows:
        return "Watchlist: empty"
    return "\n".join(["Watchlist:", *rows])
