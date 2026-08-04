"""Watchlist rules: the database row and the price feed move together."""

import pytest

from app.db import DEFAULT_TICKERS, get_watchlist
from app.services.trading import execute_trade
from app.services.watchlist import WatchlistError, add_ticker, build_watchlist, remove_ticker

pytestmark = pytest.mark.usefixtures("market")


async def test_add_registers_with_the_database_and_the_source(market):
    await add_ticker("PYPL")

    assert "PYPL" in get_watchlist()
    assert "PYPL" in market.get_tickers()


async def test_add_normalizes_the_symbol():
    await add_ticker(" pypl ")
    assert "PYPL" in get_watchlist()


async def test_adding_twice_is_a_no_op():
    await add_ticker("PYPL")
    await add_ticker("PYPL")

    assert get_watchlist().count("PYPL") == 1


@pytest.mark.parametrize("ticker", ["", "TOOLONG", "PY PL", "123"])
async def test_add_rejects_a_malformed_symbol(ticker):
    with pytest.raises(WatchlistError) as exc:
        await add_ticker(ticker)

    assert exc.value.status_code == 400


async def test_remove_deregisters_from_the_database_and_the_source(market):
    await remove_ticker("AAPL")

    assert "AAPL" not in get_watchlist()
    assert "AAPL" not in market.get_tickers()


async def test_remove_drops_the_cached_price(market):
    await remove_ticker("AAPL")
    assert market.cache.get("AAPL") is None


async def test_removing_an_unwatched_ticker_is_404():
    with pytest.raises(WatchlistError) as exc:
        await remove_ticker("PYPL")

    assert exc.value.status_code == 404
    assert str(exc.value) == "PYPL is not on the watchlist"


async def test_removing_a_held_ticker_is_409():
    await execute_trade("AAPL", "buy", 1)

    with pytest.raises(WatchlistError) as exc:
        await remove_ticker("AAPL")

    assert exc.value.status_code == 409
    assert "position" in str(exc.value)


async def test_a_rejected_removal_leaves_the_feed_running(market):
    await execute_trade("AAPL", "buy", 1)

    with pytest.raises(WatchlistError):
        await remove_ticker("AAPL")

    assert "AAPL" in get_watchlist()
    assert "AAPL" in market.get_tickers()


async def test_removing_a_sold_out_ticker_is_allowed():
    await execute_trade("AAPL", "buy", 1)
    await execute_trade("AAPL", "sell", 1)
    await remove_ticker("AAPL")

    assert "AAPL" not in get_watchlist()


def test_build_watchlist_returns_the_seeded_tickers_in_order():
    assert [entry["ticker"] for entry in build_watchlist()] == DEFAULT_TICKERS


def test_build_watchlist_carries_price_baseline_and_history():
    entry = next(e for e in build_watchlist() if e["ticker"] == "AAPL")

    assert entry["price"] == 190.0
    assert entry["open_price"] == 190.0
    assert entry["change_from_open_percent"] == 0.0
    assert len(entry["history"]) == 60


def test_build_watchlist_reports_the_change_from_open(market):
    market.set_price("AAPL", 209.0)
    entry = next(e for e in build_watchlist() if e["ticker"] == "AAPL")

    assert entry["price"] == 209.0
    assert entry["open_price"] == 190.0
    assert entry["change_from_open_percent"] == 10.0


async def test_an_unpriced_ticker_still_appears(cache):
    from app import state
    from tests.services.fakes import SilentSource

    state.set_market(cache, SilentSource(cache))
    await add_ticker("PYPL")

    entry = next(e for e in build_watchlist() if e["ticker"] == "PYPL")
    assert entry["price"] is None
    assert entry["history"] == []
