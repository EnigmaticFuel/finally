"""Tests for MassiveDataSource (mocked)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.market.cache import PriceCache
from app.market.massive_client import MassiveDataSource

# Massive's own sample lastTrade.t value: 2020-11-12T15:45:18.306274 UTC in nanoseconds.
SAMPLE_TIMESTAMP_NS = 1605195918306274000
SAMPLE_TIMESTAMP_S = 1605195918.306274


def _make_snapshot(ticker: str, price: float, timestamp_ns: int = SAMPLE_TIMESTAMP_NS) -> MagicMock:
    """Create a mock Massive snapshot object with a last_trade quote."""
    snap = MagicMock()
    snap.ticker = ticker
    snap.last_trade = MagicMock()
    snap.last_trade.price = price
    snap.last_trade.timestamp = timestamp_ns
    snap.min = None
    snap.day = None
    return snap


@pytest.mark.asyncio
class TestMassiveDataSource:
    """Unit tests for MassiveDataSource with mocked API."""

    async def test_source_name(self):
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)
        assert source.source_name == "massive"

    async def test_poll_updates_cache(self):
        """Test that polling updates the cache."""
        cache = PriceCache()
        source = MassiveDataSource(
            api_key="test-key",
            price_cache=cache,
            poll_interval=60.0,  # Long interval so the loop doesn't auto-poll
        )
        source._tickers = ["AAPL", "GOOGL"]
        source._client = MagicMock()  # Satisfy the _poll_once guard

        mock_snapshots = [
            _make_snapshot("AAPL", 190.50),
            _make_snapshot("GOOGL", 175.25),
        ]

        with patch.object(source, "_fetch_snapshots", return_value=mock_snapshots):
            await source._poll_once()

        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("GOOGL") == 175.25

    async def test_nanosecond_timestamps_convert_to_seconds(self):
        """last_trade.timestamp is nanoseconds, not milliseconds."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._tickers = ["AAPL"]
        source._client = MagicMock()

        with patch.object(source, "_fetch_snapshots", return_value=[_make_snapshot("AAPL", 190.5)]):
            await source._poll_once()

        assert cache.get("AAPL").timestamp == pytest.approx(SAMPLE_TIMESTAMP_S)

    async def test_malformed_snapshot_skipped(self):
        """Test that malformed snapshots are skipped gracefully."""
        cache = PriceCache()
        source = MassiveDataSource(
            api_key="test-key",
            price_cache=cache,
            poll_interval=60.0,
        )
        source._tickers = ["AAPL", "BAD"]
        source._client = MagicMock()  # Satisfy the _poll_once guard

        good_snap = _make_snapshot("AAPL", 190.50)
        bad_snap = MagicMock()
        bad_snap.ticker = "BAD"
        bad_snap.last_trade = None
        bad_snap.min = None
        bad_snap.day = None

        with patch.object(source, "_fetch_snapshots", return_value=[good_snap, bad_snap]):
            await source._poll_once()

        # Good ticker processed, bad one skipped
        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("BAD") is None

    async def test_falls_back_to_minute_bar_when_no_last_trade(self):
        """Off-hours snapshots may have no last_trade; fall back to the minute bar."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._tickers = ["AAPL"]
        source._client = MagicMock()

        snap = MagicMock()
        snap.ticker = "AAPL"
        snap.last_trade = None
        snap.min = MagicMock(close=188.25, timestamp=1707580800000)  # milliseconds
        snap.day = None

        with patch.object(source, "_fetch_snapshots", return_value=[snap]):
            await source._poll_once()

        assert cache.get_price("AAPL") == 188.25
        assert cache.get("AAPL").timestamp == pytest.approx(1707580800.0)

    async def test_falls_back_to_day_close_when_only_day_available(self):
        """The last-resort fallback uses the daily close and the wall clock."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._tickers = ["AAPL"]
        source._client = MagicMock()

        snap = MagicMock()
        snap.ticker = "AAPL"
        snap.last_trade = None
        snap.min = None
        snap.day = MagicMock(close=187.10)

        with patch.object(source, "_fetch_snapshots", return_value=[snap]):
            await source._poll_once()

        assert cache.get_price("AAPL") == 187.10

    async def test_no_usable_quote_is_skipped(self):
        """A snapshot with no last_trade, min, or day is skipped, not crashed on."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._tickers = ["AAPL"]
        source._client = MagicMock()

        snap = MagicMock()
        snap.ticker = "AAPL"
        snap.last_trade = None
        snap.min = None
        snap.day = None

        with patch.object(source, "_fetch_snapshots", return_value=[snap]):
            await source._poll_once()

        assert cache.get_price("AAPL") is None

    async def test_api_error_does_not_crash(self):
        """Test that API errors don't crash the poller."""
        cache = PriceCache()
        source = MassiveDataSource(
            api_key="test-key",
            price_cache=cache,
            poll_interval=60.0,
        )
        source._tickers = ["AAPL"]
        source._client = MagicMock()  # Satisfy the _poll_once guard

        with patch.object(source, "_fetch_snapshots", side_effect=Exception("network error")):
            await source._poll_once()  # Should not raise

        assert cache.get_price("AAPL") is None  # No update happened

    async def test_poll_failure_backs_off(self):
        """Repeated failures should widen the interval rather than hammer the API."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="k", price_cache=cache, poll_interval=15.0)
        source._tickers = ["AAPL"]
        source._client = MagicMock()

        with patch.object(source, "_fetch_snapshots", side_effect=RuntimeError("429")):
            await source._poll_once()

        assert source._backoff == 2.0
        assert len(cache) == 0

    async def test_backoff_resets_after_a_success(self):
        """A successful poll should undo any prior backoff."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="k", price_cache=cache, poll_interval=15.0)
        source._tickers = ["AAPL"]
        source._client = MagicMock()
        source._backoff = 4.0

        with patch.object(source, "_fetch_snapshots", return_value=[_make_snapshot("AAPL", 190.0)]):
            await source._poll_once()

        assert source._backoff == 1.0

    async def test_backoff_is_capped(self):
        """Backoff must not grow without bound."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="k", price_cache=cache, poll_interval=15.0)
        source._tickers = ["AAPL"]
        source._client = MagicMock()
        source._backoff = 8.0

        with patch.object(source, "_fetch_snapshots", side_effect=RuntimeError("429")):
            await source._poll_once()

        assert source._backoff == 8.0

    async def test_add_ticker(self):
        """Test adding a ticker."""
        cache = PriceCache()
        source = MassiveDataSource(
            api_key="test-key", price_cache=cache, backfill_history=False
        )

        await source.add_ticker("AAPL")
        assert "AAPL" in source.get_tickers()

    async def test_add_ticker_uppercase_normalization(self):
        """Test that tickers are normalized to uppercase."""
        cache = PriceCache()
        source = MassiveDataSource(
            api_key="test-key", price_cache=cache, backfill_history=False
        )

        await source.add_ticker("aapl")
        assert "AAPL" in source.get_tickers()

    async def test_add_ticker_strips_whitespace(self):
        """Test that ticker whitespace is stripped."""
        cache = PriceCache()
        source = MassiveDataSource(
            api_key="test-key", price_cache=cache, backfill_history=False
        )

        await source.add_ticker("  AAPL  ")
        assert "AAPL" in source.get_tickers()

    async def test_add_duplicate_ticker_is_noop(self):
        cache = PriceCache()
        source = MassiveDataSource(
            api_key="test-key", price_cache=cache, backfill_history=False
        )
        await source.add_ticker("AAPL")
        await source.add_ticker("AAPL")
        assert source.get_tickers() == ["AAPL"]

    async def test_remove_ticker(self):
        """Test removing a ticker."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)
        source._tickers = ["AAPL", "GOOGL"]
        cache.update("AAPL", 190.00)

        await source.remove_ticker("AAPL")
        assert "AAPL" not in source.get_tickers()
        assert cache.get("AAPL") is None

    async def test_get_tickers(self):
        """Test getting the list of active tickers."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)
        source._tickers = ["AAPL", "GOOGL"]

        tickers = source.get_tickers()
        assert tickers == ["AAPL", "GOOGL"]

    async def test_empty_tickers_skips_poll(self):
        """Test that polling is skipped when there are no tickers."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)
        source._tickers = []

        # Should not call _fetch_snapshots
        with patch.object(source, "_fetch_snapshots") as mock_fetch:
            await source._poll_once()
            mock_fetch.assert_not_called()

    async def test_stop_is_idempotent(self):
        """Test that stop() can be called multiple times."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)

        await source.stop()
        await source.stop()  # Should not raise

    async def test_stop_cancels_task(self):
        """Test that stop() cancels the polling task."""
        cache = PriceCache()
        source = MassiveDataSource(
            api_key="test-key", price_cache=cache, poll_interval=10.0, backfill_history=False
        )

        with patch("app.market.massive_client.RESTClient"):
            with patch.object(source, "_fetch_snapshots", return_value=[]):
                with patch.object(source, "_log_market_status", new=AsyncMock()):
                    await source.start(["AAPL"])

        # Verify task is running
        assert source._task is not None
        assert not source._task.done()

        # Stop and verify task is cancelled
        await source.stop()
        assert source._task is None

    async def test_start_immediate_poll(self):
        """Test that start() does an immediate poll before starting the loop."""
        cache = PriceCache()
        source = MassiveDataSource(
            api_key="test-key", price_cache=cache, poll_interval=60.0, backfill_history=False
        )

        mock_snapshots = [_make_snapshot("AAPL", 190.50)]

        with patch("app.market.massive_client.RESTClient"):
            with patch.object(source, "_fetch_snapshots", return_value=mock_snapshots):
                with patch.object(source, "_log_market_status", new=AsyncMock()):
                    await source.start(["AAPL"])

        # Cache should have data immediately from the first poll
        assert cache.get_price("AAPL") == 190.50

        await source.stop()

    async def test_start_backfills_history(self):
        """start() kicks off a history backfill task per ticker."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)

        with patch("app.market.massive_client.RESTClient"):
            with patch.object(source, "_fetch_snapshots", return_value=[]):
                with patch.object(source, "_log_market_status", new=AsyncMock()):
                    with patch.object(
                        source, "_fetch_history", return_value=[100.0, 101.0, 102.0]
                    ):
                        await source.start(["AAPL"])
                        await asyncio.sleep(0.05)

        assert cache.get_history("AAPL") == [100.0, 101.0, 102.0]
        await source.stop()

    async def test_backfill_failure_is_swallowed(self):
        """A failed history fetch must not crash the backfill task."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)

        with patch.object(source, "_fetch_history", side_effect=RuntimeError("boom")):
            source._client = MagicMock()
            await source._backfill_one("AAPL")  # Should not raise

        assert cache.get_history("AAPL") == []
