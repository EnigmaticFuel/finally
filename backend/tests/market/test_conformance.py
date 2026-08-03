"""Conformance suite: the lifecycle contract must hold for every MarketDataSource.

Anything only one implementation passes is a leak in the abstraction that
downstream code (SSE, portfolio valuation, trade execution) would otherwise
have to special-case.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.market.cache import PriceCache
from app.market.massive_client import MassiveDataSource
from app.market.simulator import SimulatorDataSource


def _snapshot(ticker: str, price: float) -> MagicMock:
    snap = MagicMock()
    snap.ticker = ticker
    snap.last_trade = MagicMock(price=price, timestamp=1605195918306274000)
    snap.min = None
    snap.day = None
    return snap


@pytest.fixture(params=["simulator", "massive"])
def source_and_cache(request):
    cache = PriceCache()
    if request.param == "simulator":
        yield SimulatorDataSource(cache, update_interval=0.05), cache
    else:
        source = MassiveDataSource(
            "test-key", cache, poll_interval=60.0, backfill_history=False
        )
        with (
            patch.object(
                source,
                "_fetch_snapshots",
                return_value=[_snapshot("AAPL", 190.50), _snapshot("GOOGL", 175.25)],
            ),
            patch.object(source, "_log_market_status", new=AsyncMock()),
            patch("app.market.massive_client.RESTClient"),
        ):
            yield source, cache


@pytest.mark.asyncio
class TestSourceConformance:
    async def test_source_name_is_a_short_identifier(self, source_and_cache):
        source, _ = source_and_cache
        assert source.source_name in {"simulator", "massive"}

    async def test_start_populates_cache_before_returning(self, source_and_cache):
        source, cache = source_and_cache
        await source.start(["AAPL", "GOOGL"])
        assert cache.get_price("AAPL") is not None
        assert cache.get_price("GOOGL") is not None
        await source.stop()

    async def test_stop_is_idempotent(self, source_and_cache):
        source, _cache = source_and_cache
        await source.start(["AAPL"])
        await source.stop()
        await source.stop()  # must not raise

    async def test_remove_ticker_clears_the_cache(self, source_and_cache):
        source, cache = source_and_cache
        await source.start(["AAPL", "GOOGL"])
        await source.remove_ticker("AAPL")
        assert "AAPL" not in cache
        assert "AAPL" not in source.get_tickers()
        await source.stop()

    async def test_get_tickers_reflects_start(self, source_and_cache):
        source, _cache = source_and_cache
        await source.start(["AAPL", "GOOGL"])
        assert set(source.get_tickers()) == {"AAPL", "GOOGL"}
        await source.stop()

    async def test_empty_start_is_not_an_error(self, source_and_cache):
        source, cache = source_and_cache
        await source.start([])
        assert len(cache) == 0
        assert source.get_tickers() == []
        await source.stop()
