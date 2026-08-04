"""Trade rules from PLAN.md section 8, exercised through execute_trade."""

import pytest

from app.db import get_cash_balance, get_position, get_snapshots, get_watchlist
from app.services.trading import TradeError, execute_trade
from tests.services.fakes import SilentSource

pytestmark = pytest.mark.usefixtures("market")


# --- the happy path ---------------------------------------------------------


async def test_buy_returns_the_server_fill():
    result = await execute_trade("AAPL", "buy", 10)

    assert result["ticker"] == "AAPL"
    assert result["side"] == "buy"
    assert result["quantity"] == 10
    assert result["fill_price"] == 190.0
    assert result["total_cost"] == 1900.0
    assert result["cash_balance"] == 8100.0
    assert result["executed_at"].endswith("Z")


async def test_buy_creates_the_position_and_debits_cash():
    await execute_trade("AAPL", "buy", 10)

    assert get_position("AAPL") == {
        "ticker": "AAPL",
        "quantity": 10.0,
        "avg_cost": 190.0,
        "updated_at": get_position("AAPL")["updated_at"],
    }
    assert get_cash_balance() == 8100.0


async def test_sell_credits_cash_and_reduces_the_position(market):
    await execute_trade("AAPL", "buy", 10)
    market.set_price("AAPL", 200.0)

    result = await execute_trade("AAPL", "sell", 4)

    assert result["fill_price"] == 200.0
    assert result["total_cost"] == 800.0
    assert get_position("AAPL")["quantity"] == 6.0
    assert get_cash_balance() == 8900.0


async def test_ticker_is_normalized():
    result = await execute_trade("  aapl  ", "buy", 1)
    assert result["ticker"] == "AAPL"


async def test_side_is_case_insensitive():
    result = await execute_trade("AAPL", "BUY", 1)
    assert result["side"] == "buy"


async def test_fractional_quantities_are_supported():
    result = await execute_trade("AAPL", "buy", 0.5)
    assert result["quantity"] == 0.5
    assert result["total_cost"] == 95.0


# --- cost basis -------------------------------------------------------------


async def test_buy_averages_the_cost_basis(market):
    await execute_trade("AAPL", "buy", 10)
    market.set_price("AAPL", 210.0)
    await execute_trade("AAPL", "buy", 10)

    position = get_position("AAPL")
    assert position["quantity"] == 20.0
    assert position["avg_cost"] == 200.0


async def test_uneven_buys_weight_the_average(market):
    await execute_trade("AAPL", "buy", 3)  # 3 @ 190
    market.set_price("AAPL", 200.0)
    await execute_trade("AAPL", "buy", 1)  # 1 @ 200

    assert get_position("AAPL")["avg_cost"] == 192.5


async def test_sell_leaves_the_cost_basis_alone(market):
    await execute_trade("AAPL", "buy", 10)
    market.set_price("AAPL", 300.0)
    await execute_trade("AAPL", "sell", 5)

    assert get_position("AAPL")["avg_cost"] == 190.0


async def test_selling_everything_deletes_the_position():
    await execute_trade("AAPL", "buy", 10)
    await execute_trade("AAPL", "sell", 10)

    assert get_position("AAPL") is None


async def test_selling_everything_in_fractions_deletes_the_position():
    await execute_trade("AAPL", "buy", 0.3)
    await execute_trade("AAPL", "sell", 0.1)
    await execute_trade("AAPL", "sell", 0.2)

    assert get_position("AAPL") is None


# --- no margin, no shorting -------------------------------------------------


async def test_buy_beyond_cash_is_rejected():
    with pytest.raises(TradeError) as exc:
        await execute_trade("AAPL", "buy", 100)

    assert str(exc.value) == "Insufficient cash: need $19000.00, have $10000.00"


async def test_a_rejected_buy_changes_nothing():
    with pytest.raises(TradeError):
        await execute_trade("AAPL", "buy", 100)

    assert get_cash_balance() == 10000.0
    assert get_position("AAPL") is None


async def test_selling_more_than_held_is_rejected():
    await execute_trade("AAPL", "buy", 5)

    with pytest.raises(TradeError) as exc:
        await execute_trade("AAPL", "sell", 6)

    assert str(exc.value) == "Insufficient shares: need 6, have 5 AAPL"


async def test_selling_an_unheld_ticker_is_rejected():
    with pytest.raises(TradeError) as exc:
        await execute_trade("AAPL", "sell", 1)

    assert str(exc.value) == "Insufficient shares: need 1, have 0 AAPL"


async def test_a_failed_sell_does_not_touch_the_watchlist():
    with pytest.raises(TradeError):
        await execute_trade("PYPL", "sell", 1)

    assert "PYPL" not in get_watchlist()


# --- quantity validation ----------------------------------------------------


@pytest.mark.parametrize("quantity", [0, -1, -0.5, 0.00001])
async def test_non_positive_quantities_are_rejected(quantity):
    with pytest.raises(TradeError, match="greater than zero"):
        await execute_trade("AAPL", "buy", quantity)


@pytest.mark.parametrize("quantity", [float("nan"), float("inf"), float("-inf")])
async def test_non_finite_quantities_are_rejected(quantity):
    with pytest.raises(TradeError, match="finite number"):
        await execute_trade("AAPL", "buy", quantity)


async def test_quantity_is_rounded_to_four_decimals():
    result = await execute_trade("AAPL", "buy", 1.234567)
    assert result["quantity"] == 1.2346


# --- symbol and side validation ---------------------------------------------


@pytest.mark.parametrize("ticker", ["", "TOOLONG", "AA PL", "12345", "AAPL!"])
async def test_malformed_tickers_are_rejected(ticker):
    with pytest.raises(TradeError, match="Invalid ticker symbol"):
        await execute_trade(ticker, "buy", 1)


async def test_unknown_side_is_rejected():
    with pytest.raises(TradeError, match="Invalid side"):
        await execute_trade("AAPL", "short", 1)


# --- watchlist and price feed invariants ------------------------------------


async def test_buying_an_unwatched_ticker_adds_it(market):
    await execute_trade("PYPL", "buy", 1)

    assert "PYPL" in get_watchlist()
    assert "PYPL" in market.get_tickers()


async def test_buying_a_watched_ticker_does_not_duplicate_it():
    await execute_trade("AAPL", "buy", 1)

    assert get_watchlist().count("AAPL") == 1


async def test_a_ticker_that_never_prices_is_rejected(cache):
    from app import state

    state.set_market(cache, SilentSource(cache))

    with pytest.raises(TradeError, match="No price available"):
        await execute_trade("PYPL", "buy", 1)


# --- persistence ------------------------------------------------------------


async def test_every_trade_writes_a_snapshot():
    before = len(get_snapshots())
    await execute_trade("AAPL", "buy", 1)

    assert len(get_snapshots()) == before + 1


async def test_a_market_price_trade_still_snapshots():
    """Total value barely moves on a fill, but the chart must show the step."""
    await execute_trade("AAPL", "buy", 1)
    before = get_snapshots()[0]["total_value"]

    await execute_trade("AAPL", "buy", 1)
    snapshots = get_snapshots()

    assert snapshots[0]["total_value"] == before
    assert len(snapshots) == 3  # seed plus two trades
