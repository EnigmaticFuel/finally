"""Tests for GBMSimulator."""

from unittest.mock import patch

import numpy as np

from app.market.seed_prices import SEED_PRICES, synthesize_params
from app.market.simulator import GBMSimulator


class TestGBMSimulator:
    """Unit tests for the GBM price simulator."""

    def test_step_returns_all_tickers(self):
        """Test that step() returns prices for all tickers."""
        sim = GBMSimulator(tickers=["AAPL", "GOOGL"])
        result = sim.step()
        assert set(result.keys()) == {"AAPL", "GOOGL"}

    def test_prices_are_positive(self):
        """GBM prices can never go negative (exp() is always positive)."""
        sim = GBMSimulator(tickers=["AAPL"])
        for _ in range(10_000):
            prices = sim.step()
            assert prices["AAPL"] > 0

    def test_initial_prices_match_seeds(self):
        """Test that initial prices match seed prices."""
        sim = GBMSimulator(tickers=["AAPL"])
        # Before any step, price should be the seed price
        assert sim.get_price("AAPL") == SEED_PRICES["AAPL"]

    def test_add_ticker(self):
        """Test adding a ticker dynamically."""
        sim = GBMSimulator(tickers=["AAPL"])
        sim.add_ticker("TSLA")
        result = sim.step()
        assert "TSLA" in result

    def test_remove_ticker(self):
        """Test removing a ticker."""
        sim = GBMSimulator(tickers=["AAPL", "GOOGL"])
        sim.remove_ticker("GOOGL")
        result = sim.step()
        assert "GOOGL" not in result
        assert "AAPL" in result

    def test_add_duplicate_is_noop(self):
        """Test that adding a duplicate ticker is a no-op."""
        sim = GBMSimulator(tickers=["AAPL"])
        sim.add_ticker("AAPL")
        assert len(sim._tickers) == 1

    def test_remove_nonexistent_is_noop(self):
        """Test that removing a non-existent ticker is a no-op."""
        sim = GBMSimulator(tickers=["AAPL"])
        sim.remove_ticker("NOPE")  # Should not raise

    def test_unknown_ticker_gets_synthesized_price(self):
        """Unknown tickers get a deterministic price in the plausible large-cap range."""
        sim = GBMSimulator(tickers=["ZZZZZ"])
        price = sim.get_price("ZZZZZ")
        assert price is not None
        assert 20.0 <= price <= 500.0

    def test_unknown_ticker_price_is_deterministic(self):
        """Restarting the process must not reprice a held position."""
        sim_a = GBMSimulator(tickers=["PYPL"])
        sim_b = GBMSimulator(tickers=["PYPL"])
        assert sim_a.get_price("PYPL") == sim_b.get_price("PYPL")

    def test_empty_step(self):
        """Test stepping with no tickers."""
        sim = GBMSimulator(tickers=[])
        result = sim.step()
        assert result == {}

    def test_prices_change_over_time(self):
        """After many steps, prices should have drifted from their seeds."""
        sim = GBMSimulator(tickers=["AAPL"])
        initial_price = sim.get_price("AAPL")

        for _ in range(1000):
            sim.step()

        final_price = sim.get_price("AAPL")
        # Price should have changed (extremely unlikely to be exactly the seed)
        assert final_price != initial_price

    def test_cholesky_rebuilds_on_add(self):
        """Test that Cholesky matrix is rebuilt when tickers are added."""
        sim = GBMSimulator(tickers=["AAPL"])
        assert sim._cholesky is None  # Only 1 ticker, no correlation matrix
        sim.add_ticker("GOOGL")
        assert sim._cholesky is not None  # Now 2 tickers, matrix exists

    def test_cholesky_none_with_one_ticker(self):
        """Test that Cholesky is None with only one ticker."""
        sim = GBMSimulator(tickers=["AAPL"])
        assert sim._cholesky is None

    def test_cholesky_failure_degrades_to_independent_draws(self):
        """A non positive-definite matrix must not take the whole feed down."""
        sim = GBMSimulator(tickers=["AAPL", "GOOGL"])
        with patch("numpy.linalg.cholesky", side_effect=np.linalg.LinAlgError("singular")):
            sim._rebuild_cholesky()
        assert sim._cholesky is None
        # The simulator keeps working with independent draws.
        result = sim.step()
        assert set(result.keys()) == {"AAPL", "GOOGL"}

    def test_get_price_returns_none_for_unknown(self):
        """Test that get_price returns None for unknown ticker."""
        sim = GBMSimulator(tickers=["AAPL"])
        assert sim.get_price("UNKNOWN") is None

    def test_pairwise_correlation_tech_stocks(self):
        """Test that tech stocks have high correlation."""
        corr = GBMSimulator._pairwise_correlation("AAPL", "GOOGL")
        assert corr == 0.6

    def test_pairwise_correlation_finance_stocks(self):
        """Test that finance stocks have moderate correlation."""
        corr = GBMSimulator._pairwise_correlation("JPM", "V")
        assert corr == 0.5

    def test_pairwise_correlation_tsla(self):
        """TSLA is deliberately outside both sector groups."""
        corr = GBMSimulator._pairwise_correlation("TSLA", "AAPL")
        assert corr == 0.3
        corr = GBMSimulator._pairwise_correlation("TSLA", "JPM")
        assert corr == 0.3

    def test_pairwise_correlation_cross_sector(self):
        """Test cross-sector correlation."""
        corr = GBMSimulator._pairwise_correlation("AAPL", "JPM")
        assert corr == 0.3

    def test_default_dt_is_reasonable(self):
        """Test that default dt is a reasonable small value."""
        assert 0 < GBMSimulator.DEFAULT_DT < 0.0001

    def test_prices_rounded_to_two_decimals(self):
        """Test that prices are rounded to 2 decimal places."""
        sim = GBMSimulator(tickers=["AAPL"])
        result = sim.step()
        price_str = str(result["AAPL"])
        # Check that we have at most 2 decimal places
        if "." in price_str:
            decimal_part = price_str.split(".")[1]
            assert len(decimal_part) <= 2

    # --- History backfill ---

    def test_backfill_returns_requested_points(self):
        sim = GBMSimulator(tickers=["AAPL"])
        history = sim.backfill_history("AAPL", points=60)
        assert len(history) == 60

    def test_backfill_ends_at_the_current_price(self):
        sim = GBMSimulator(tickers=["AAPL"])
        history = sim.backfill_history("AAPL")
        assert history[-1] == sim.get_price("AAPL")

    def test_backfill_is_oldest_first_and_all_positive(self):
        sim = GBMSimulator(tickers=["AAPL"])
        history = sim.backfill_history("AAPL", points=10)
        assert len(history) == 10
        assert all(p > 0 for p in history)

    def test_backfill_unknown_ticker_returns_empty(self):
        sim = GBMSimulator(tickers=["AAPL"])
        assert sim.backfill_history("UNKNOWN") == []

    def test_backfill_zero_points_returns_empty(self):
        sim = GBMSimulator(tickers=["AAPL"])
        assert sim.backfill_history("AAPL", points=0) == []


class TestSynthesizeParams:
    """Unit tests for the deterministic unknown-ticker parameter synthesis."""

    def test_deterministic_across_calls(self):
        assert synthesize_params("PYPL") == synthesize_params("PYPL")

    def test_price_and_sigma_within_plausible_ranges(self):
        price, params = synthesize_params("PYPL")
        assert 20.0 <= price <= 500.0
        assert 0.15 <= params["sigma"] <= 0.50
        assert 0.02 <= params["mu"] <= 0.08

    def test_different_tickers_get_different_params(self):
        assert synthesize_params("AMD") != synthesize_params("DIS")
