"""Portfolio valuation: cash plus positions marked to the cache."""

import pytest

from app.db import upsert_position
from app.services.portfolio import build_portfolio
from app.services.trading import execute_trade

pytestmark = pytest.mark.usefixtures("market")


def test_a_fresh_portfolio_is_all_cash():
    portfolio = build_portfolio()

    assert portfolio["cash_balance"] == 10000.0
    assert portfolio["total_value"] == 10000.0
    assert portfolio["positions"] == []


async def test_a_position_is_priced_at_the_market(market):
    await execute_trade("AAPL", "buy", 10)
    market.set_price("AAPL", 200.0)

    position = build_portfolio()["positions"][0]

    assert position["ticker"] == "AAPL"
    assert position["quantity"] == 10.0
    assert position["avg_cost"] == 190.0
    assert position["current_price"] == 200.0
    assert position["market_value"] == 2000.0
    assert position["unrealized_pnl"] == 100.0
    assert position["unrealized_pnl_percent"] == pytest.approx(5.2632, abs=1e-4)


async def test_a_loss_is_negative(market):
    await execute_trade("AAPL", "buy", 10)
    market.set_price("AAPL", 180.0)

    position = build_portfolio()["positions"][0]

    assert position["unrealized_pnl"] == -100.0
    assert position["unrealized_pnl_percent"] == pytest.approx(-5.2632, abs=1e-4)


async def test_total_value_is_cash_plus_market_value(market):
    await execute_trade("AAPL", "buy", 10)
    market.set_price("AAPL", 200.0)

    portfolio = build_portfolio()

    assert portfolio["cash_balance"] == 8100.0
    assert portfolio["total_value"] == 10100.0


async def test_a_market_price_buy_leaves_total_value_unchanged():
    before = build_portfolio()["total_value"]
    await execute_trade("AAPL", "buy", 10)

    assert build_portfolio()["total_value"] == before


async def test_positions_are_ordered_by_ticker():
    await execute_trade("TSLA", "buy", 1)
    await execute_trade("AAPL", "buy", 1)

    assert [p["ticker"] for p in build_portfolio()["positions"]] == ["AAPL", "TSLA"]


def test_an_unpriced_position_is_valued_at_cost():
    """A position must never vanish because its first tick has not landed."""
    upsert_position("PYPL", 10.0, 70.0)

    position = build_portfolio()["positions"][0]

    assert position["ticker"] == "PYPL"
    assert position["current_price"] == 70.0
    assert position["market_value"] == 700.0
    assert position["unrealized_pnl"] == 0.0
    assert build_portfolio()["total_value"] == 10700.0
