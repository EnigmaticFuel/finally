"""Tests for PriceUpdate dataclass."""

import pytest

from app.market.models import PriceUpdate


class TestPriceUpdate:
    """Unit tests for the PriceUpdate model."""

    def test_price_update_creation(self):
        """Test basic PriceUpdate creation."""
        update = PriceUpdate(
            ticker="AAPL",
            price=190.50,
            previous_price=190.00,
            open_price=189.00,
            timestamp=1234567890.0,
        )
        assert update.ticker == "AAPL"
        assert update.price == 190.50
        assert update.previous_price == 190.00
        assert update.open_price == 189.00
        assert update.timestamp == 1234567890.0

    def test_change_calculation(self):
        """Test price change calculation."""
        update = PriceUpdate(
            ticker="AAPL", price=190.50, previous_price=190.00, open_price=190.00
        )
        assert update.change == 0.50

    def test_change_negative(self):
        """Test negative price change."""
        update = PriceUpdate(
            ticker="AAPL", price=189.50, previous_price=190.00, open_price=190.00
        )
        assert update.change == -0.50

    def test_change_percent_up(self):
        """Test percentage change calculation (up)."""
        update = PriceUpdate(
            ticker="AAPL", price=190.00, previous_price=100.00, open_price=100.00
        )
        assert update.change_percent == 90.0

    def test_change_percent_down(self):
        """Test percentage change calculation (down)."""
        update = PriceUpdate(
            ticker="AAPL", price=100.00, previous_price=200.00, open_price=200.00
        )
        assert update.change_percent == -50.0

    def test_change_percent_zero_previous(self):
        """Test percentage change with zero previous price."""
        update = PriceUpdate(ticker="AAPL", price=100.00, previous_price=0.00, open_price=0.00)
        assert update.change_percent == 0.0

    def test_direction_up(self):
        """Test direction calculation (up)."""
        update = PriceUpdate(
            ticker="AAPL", price=191.00, previous_price=190.00, open_price=190.00
        )
        assert update.direction == "up"

    def test_direction_down(self):
        """Test direction calculation (down)."""
        update = PriceUpdate(
            ticker="AAPL", price=189.00, previous_price=190.00, open_price=190.00
        )
        assert update.direction == "down"

    def test_direction_flat(self):
        """Test direction calculation (flat)."""
        update = PriceUpdate(
            ticker="AAPL", price=190.00, previous_price=190.00, open_price=190.00
        )
        assert update.direction == "flat"

    def test_change_from_open_up(self):
        """Test change_from_open reflects the session baseline, not the previous tick."""
        update = PriceUpdate(
            ticker="AAPL", price=192.00, previous_price=191.50, open_price=190.00
        )
        assert update.change_from_open == 2.00

    def test_change_from_open_percent(self):
        """Test change_from_open_percent uses the open price as the denominator."""
        update = PriceUpdate(
            ticker="AAPL", price=190.687, previous_price=190.60, open_price=189.20
        )
        assert update.change_from_open_percent == pytest.approx(0.7855, abs=1e-3)

    def test_change_from_open_percent_zero_open(self):
        """Test change_from_open_percent guards against division by zero."""
        update = PriceUpdate(ticker="AAPL", price=100.00, previous_price=100.00, open_price=0.00)
        assert update.change_from_open_percent == 0.0

    def test_change_from_open_percent_differs_from_change_percent(self):
        """The two 'change' numbers measure different things and can disagree."""
        # Ticked down from the previous price, but still up on the session.
        update = PriceUpdate(
            ticker="AAPL", price=190.00, previous_price=191.00, open_price=185.00
        )
        assert update.change_percent < 0
        assert update.change_from_open_percent > 0

    def test_to_dict(self):
        """Test serialization to dictionary."""
        update = PriceUpdate(
            ticker="AAPL",
            price=190.50,
            previous_price=190.00,
            open_price=189.20,
            timestamp=1234567890.0,
        )
        result = update.to_dict()

        assert result["ticker"] == "AAPL"
        assert result["price"] == 190.50
        assert result["previous_price"] == 190.00
        assert result["open_price"] == 189.20
        assert result["timestamp"] == 1234567890.0
        assert result["change"] == 0.50
        assert result["change_percent"] == 0.2632  # (0.50 / 190.00) * 100
        assert result["change_from_open_percent"] == pytest.approx(0.6871, abs=1e-3)
        assert result["direction"] == "up"

    def test_immutability(self):
        """Test that PriceUpdate is immutable."""
        update = PriceUpdate(
            ticker="AAPL",
            price=190.50,
            previous_price=190.00,
            open_price=190.00,
            timestamp=1234567890.0,
        )

        with pytest.raises(AttributeError):
            update.price = 200.00  # Should raise error
