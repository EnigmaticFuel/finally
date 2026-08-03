"""Tests for PriceCache."""

import asyncio

import pytest

from app.market.cache import PriceCache, wait_for_price


class TestPriceCache:
    """Unit tests for the PriceCache."""

    def test_update_and_get(self):
        """Test updating and getting a price."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.50)
        assert update.ticker == "AAPL"
        assert update.price == 190.50
        assert cache.get("AAPL") == update

    def test_first_update_is_flat(self):
        """Test that the first update has flat direction."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.50)
        assert update.direction == "flat"
        assert update.previous_price == 190.50

    def test_direction_up(self):
        """Test price update with upward direction."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        update = cache.update("AAPL", 191.00)
        assert update.direction == "up"
        assert update.change == 1.00

    def test_direction_down(self):
        """Test price update with downward direction."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        update = cache.update("AAPL", 189.00)
        assert update.direction == "down"
        assert update.change == -1.00

    def test_remove(self):
        """Test removing a ticker from cache."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.remove("AAPL")
        assert cache.get("AAPL") is None

    def test_remove_nonexistent(self):
        """Test removing a ticker that doesn't exist."""
        cache = PriceCache()
        cache.remove("AAPL")  # Should not raise

    def test_get_all(self):
        """Test getting all prices."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.update("GOOGL", 175.00)
        all_prices = cache.get_all()
        assert set(all_prices.keys()) == {"AAPL", "GOOGL"}

    def test_version_increments(self):
        """Test that version counter increments on a real price change."""
        cache = PriceCache()
        v0 = cache.version
        cache.update("AAPL", 190.00)
        assert cache.version == v0 + 1
        cache.update("AAPL", 191.00)
        assert cache.version == v0 + 2

    def test_get_price_convenience(self):
        """Test the convenience get_price method."""
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("NOPE") is None

    def test_len(self):
        """Test __len__ method."""
        cache = PriceCache()
        assert len(cache) == 0
        cache.update("AAPL", 190.00)
        assert len(cache) == 1
        cache.update("GOOGL", 175.00)
        assert len(cache) == 2

    def test_contains(self):
        """Test __contains__ method."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        assert "AAPL" in cache
        assert "GOOGL" not in cache

    def test_custom_timestamp(self):
        """Test updating with a custom timestamp."""
        cache = PriceCache()
        custom_ts = 1234567890.0
        update = cache.update("AAPL", 190.50, timestamp=custom_ts)
        assert update.timestamp == custom_ts

    def test_zero_timestamp_is_not_discarded(self):
        """timestamp=0.0 is a legitimate value and must not fall back to time.time()."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.50, timestamp=0.0)
        assert update.timestamp == 0.0

    def test_price_rounding(self):
        """Test that prices are rounded to 2 decimal places."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.12345)
        assert update.price == 190.12

    # --- Session baseline ---

    def test_first_update_pins_the_session_baseline(self):
        """The first update for a ticker sets its open_price."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.00)
        assert update.open_price == 190.00
        assert update.previous_price == 190.00
        assert update.direction == "flat"
        assert update.change_from_open_percent == 0.0

    def test_open_price_survives_later_updates(self):
        """open_price stays pinned to the first price seen, not the latest tick."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.update("AAPL", 191.00)
        update = cache.update("AAPL", 192.00)
        assert update.open_price == 190.00
        assert update.previous_price == 191.00
        assert update.change_from_open_percent == pytest.approx(1.0526, abs=1e-3)

    def test_open_price_resets_after_remove_and_readd(self):
        """A ticker re-added after removal gets a fresh session baseline."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.remove("AAPL")
        update = cache.update("AAPL", 250.00)
        assert update.open_price == 250.00

    def test_repeated_price_does_not_bump_version(self):
        """Emitting the same price twice must not look like a change to SSE."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        version = cache.version
        cache.update("AAPL", 190.00)
        assert cache.version == version
        assert cache.get("AAPL").timestamp > 0

    def test_repeated_price_still_refreshes_timestamp(self):
        """Even with no visible change, the feed should look alive to /api/health."""
        cache = PriceCache()
        cache.update("AAPL", 190.00, timestamp=100.0)
        cache.update("AAPL", 190.00, timestamp=200.0)
        assert cache.get("AAPL").timestamp == 200.0

    # --- History ---

    def test_history_is_bounded_and_ordered(self):
        cache = PriceCache(history_points=5, history_interval=0.0)
        for price in range(100, 110):
            cache.update("AAPL", float(price))
        assert cache.get_history("AAPL") == [105.0, 106.0, 107.0, 108.0, 109.0]

    def test_history_respects_the_minimum_interval(self):
        cache = PriceCache(history_points=10, history_interval=60.0)
        cache.update("AAPL", 100.0, timestamp=0.0)
        cache.update("AAPL", 101.0, timestamp=10.0)  # too soon, not recorded
        cache.update("AAPL", 102.0, timestamp=70.0)  # 70s later, recorded
        assert cache.get_history("AAPL") == [100.0, 102.0]

    def test_get_history_unknown_ticker_is_empty(self):
        cache = PriceCache()
        assert cache.get_history("NOPE") == []

    def test_seed_history_then_remove_clears_everything(self):
        cache = PriceCache()
        cache.seed_history("AAPL", [1.0, 2.0, 3.0])
        cache.update("AAPL", 4.0)
        cache.remove("AAPL")
        assert cache.get("AAPL") is None
        assert cache.get_history("AAPL") == []

    def test_seed_history_replaces_existing_history(self):
        cache = PriceCache(history_interval=0.0)
        cache.update("AAPL", 1.0)
        cache.update("AAPL", 2.0)
        cache.seed_history("AAPL", [10.0, 20.0, 30.0])
        assert cache.get_history("AAPL") == [10.0, 20.0, 30.0]

    def test_seed_history_truncates_to_history_points(self):
        cache = PriceCache(history_points=3)
        cache.seed_history("AAPL", [1.0, 2.0, 3.0, 4.0, 5.0])
        assert cache.get_history("AAPL") == [3.0, 4.0, 5.0]

    # --- Health ---

    def test_newest_timestamp_empty_cache(self):
        cache = PriceCache()
        assert cache.newest_timestamp() is None

    def test_newest_timestamp_reflects_latest_write(self):
        cache = PriceCache()
        cache.update("AAPL", 190.00, timestamp=100.0)
        cache.update("GOOGL", 175.00, timestamp=200.0)
        assert cache.newest_timestamp() == 200.0


@pytest.mark.asyncio
class TestWaitForPrice:
    """Unit tests for the wait_for_price helper."""

    async def test_returns_immediately_when_price_present(self):
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        price = await wait_for_price(cache, "AAPL", timeout=1.0)
        assert price == 190.00

    async def test_waits_for_a_price_that_arrives_late(self):
        cache = PriceCache()

        async def seed_later():
            await asyncio.sleep(0.05)
            cache.update("AAPL", 190.00)

        task = asyncio.create_task(seed_later())
        price = await wait_for_price(cache, "AAPL", timeout=1.0)
        assert price == 190.00
        await task

    async def test_raises_on_timeout(self):
        cache = PriceCache()
        with pytest.raises(ValueError, match="AAPL"):
            await wait_for_price(cache, "AAPL", timeout=0.1)
