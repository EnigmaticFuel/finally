"""The LLM_MOCK contract from PLAN.md section 9.

The E2E suite asserts against this behavior, so these tests pin the trigger
order, the ticker defaults and the exact analysis string.
"""

import pytest

from app.db import set_cash_balance, upsert_position
from app.llm.mock import extract_ticker, mock_response


@pytest.mark.parametrize(
    "message, ticker",
    [
        ("buy", "AAPL"),
        ("buy some shares", "AAPL"),
        ("buy 10 NVDA", "NVDA"),
        ("please buy 3 shares of TSLA today", "TSLA"),
    ],
)
def test_buy_produces_a_buy_trade(market, message, ticker):
    response = mock_response(message)
    assert len(response.trades) == 1
    assert response.trades[0].side == "buy"
    assert response.trades[0].ticker == ticker
    assert response.trades[0].quantity == 1
    assert response.watchlist_changes == []


@pytest.mark.parametrize(
    "message, ticker",
    [
        ("sell", "AAPL"),
        ("sell my GOOGL", "GOOGL"),
    ],
)
def test_sell_produces_a_sell_trade(market, message, ticker):
    response = mock_response(message)
    assert len(response.trades) == 1
    assert response.trades[0].side == "sell"
    assert response.trades[0].ticker == ticker
    assert response.trades[0].quantity == 1


@pytest.mark.parametrize(
    "message, ticker",
    [
        ("watch something", "PYPL"),
        ("add", "PYPL"),
        ("please watch PYPL", "PYPL"),
        ("add SHOP to my list", "SHOP"),
    ],
)
def test_watch_or_add_produces_an_add_change(market, message, ticker):
    response = mock_response(message)
    assert response.trades == []
    assert len(response.watchlist_changes) == 1
    assert response.watchlist_changes[0].action == "add"
    assert response.watchlist_changes[0].ticker == ticker


@pytest.mark.parametrize(
    "message, ticker",
    [
        ("remove it", "PYPL"),
        ("remove META", "META"),
    ],
)
def test_remove_produces_a_remove_change(market, message, ticker):
    response = mock_response(message)
    assert response.trades == []
    assert len(response.watchlist_changes) == 1
    assert response.watchlist_changes[0].action == "remove"
    assert response.watchlist_changes[0].ticker == ticker


def test_buy_wins_over_sell(market):
    """The table is checked in order, so an ambiguous message resolves to buy."""
    response = mock_response("should I buy or sell NVDA")
    assert response.trades[0].side == "buy"


def test_sell_wins_over_watchlist_keywords(market):
    response = mock_response("sell TSLA and remove it from my watchlist")
    assert response.trades[0].side == "sell"
    assert response.watchlist_changes == []


def test_add_wins_over_remove(market):
    response = mock_response("add JPM and remove V")
    assert response.watchlist_changes[0].action == "add"
    assert response.watchlist_changes[0].ticker == "JPM"


def test_the_word_watchlist_triggers_add(market):
    """'watch' is checked before 'remove', so 'remove X from the watchlist' adds.

    A quirk of the keyword table in PLAN.md section 9, pinned here so nobody
    quietly reorders the checks.
    """
    assert mock_response("remove META from the watchlist").watchlist_changes[0].action == "add"


def test_keywords_are_matched_case_insensitively(market):
    assert mock_response("BUY").trades[0].side == "buy"


def test_fallback_analysis_on_a_fresh_portfolio(market):
    response = mock_response("how am I doing?")
    assert response.message == "You are holding 0 positions worth $0.00 with $10000.00 in cash."
    assert response.trades == []
    assert response.watchlist_changes == []


def test_fallback_analysis_echoes_live_numbers(market):
    upsert_position("AAPL", 10, 180.0)
    set_cash_balance(8200.0)

    response = mock_response("what is my exposure")

    assert response.message == "You are holding 1 positions worth $1900.00 with $8200.00 in cash."


def test_extract_ticker_takes_the_first_uppercase_token():
    assert extract_ticker("swap NVDA for AMD", "AAPL") == "NVDA"


def test_extract_ticker_ignores_lowercase_and_long_tokens():
    assert extract_ticker("buy aapl and GOOGLE stock", "AAPL") == "AAPL"


def test_extract_ticker_falls_back_to_the_default():
    assert extract_ticker("nothing here", "PYPL") == "PYPL"
