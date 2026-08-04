"""Deterministic mock responses for LLM_MOCK=true.

This is a contract, not an implementation detail: the E2E suite asserts against
the keyword table in PLAN.md section 9, so the trigger order and the analysis
string below are part of the spec. Mock actions still run through the real
execution and validation path in app/api/chat.py.
"""

from __future__ import annotations

from app.market import TICKER_PATTERN
from app.services.portfolio import build_portfolio

from .schema import ChatResponse, Trade, WatchlistChange

DEFAULT_TRADE_TICKER = "AAPL"
DEFAULT_WATCHLIST_TICKER = "PYPL"
MOCK_QUANTITY = 1.0


def mock_response(user_message: str) -> ChatResponse:
    """Keyword-triggered reply, checked in the order given by PLAN.md section 9."""
    lowered = user_message.lower()

    if "buy" in lowered:
        return _trade_response(user_message, "buy")
    if "sell" in lowered:
        return _trade_response(user_message, "sell")
    if "watch" in lowered or "add" in lowered:
        return _watchlist_response(user_message, "add")
    if "remove" in lowered:
        return _watchlist_response(user_message, "remove")
    return ChatResponse(message=_analysis(), trades=[], watchlist_changes=[])


def extract_ticker(user_message: str, default: str) -> str:
    """The first ^[A-Z]{1,5}$ token in the message, or `default` if there is none."""
    for token in user_message.split():
        if TICKER_PATTERN.match(token):
            return token
    return default


def _trade_response(user_message: str, side: str) -> ChatResponse:
    ticker = extract_ticker(user_message, DEFAULT_TRADE_TICKER)
    trade = Trade(ticker=ticker, side=side, quantity=MOCK_QUANTITY)
    return ChatResponse(
        message=f"Placing a {side} order for {MOCK_QUANTITY:g} share of {ticker}.",
        trades=[trade],
        watchlist_changes=[],
    )


def _watchlist_response(user_message: str, action: str) -> ChatResponse:
    ticker = extract_ticker(user_message, DEFAULT_WATCHLIST_TICKER)
    change = WatchlistChange(ticker=ticker, action=action)
    preposition = "to" if action == "add" else "from"
    return ChatResponse(
        message=f"Applying {action} for {ticker} {preposition} your watchlist.",
        trades=[],
        watchlist_changes=[change],
    )


def _analysis() -> str:
    """The fallback string, echoing live portfolio numbers."""
    portfolio = build_portfolio()
    positions = portfolio["positions"]
    holdings_value = sum(position["market_value"] for position in positions)
    return (
        f"You are holding {len(positions)} positions worth ${holdings_value:.2f} "
        f"with ${portfolio['cash_balance']:.2f} in cash."
    )
