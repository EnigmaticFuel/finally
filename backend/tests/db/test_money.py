"""Tests for the money and quantity rounding rules."""

from app.db.money import (
    MONEY_PLACES,
    QUANTITY_EPSILON,
    QUANTITY_PLACES,
    is_zero,
    round_money,
    round_quantity,
)


class TestPrecisionConstants:
    """The stored precisions are a one-way decision and are pinned here."""

    def test_precisions(self) -> None:
        """Cash stores 2 places, quantities 4, epsilon two orders below."""
        assert MONEY_PLACES == 2
        assert QUANTITY_PLACES == 4
        assert QUANTITY_EPSILON == 1e-6


class TestRoundMoney:
    """Cash amounts round to cents at the write boundary."""

    def test_rounds_ordinary_values(self) -> None:
        """Ordinary cash amounts round to two places."""
        assert round_money(1905.199) == 1905.2
        assert round_money(8234.504) == 8234.5
        assert round_money(-42.126) == -42.13

    def test_boundary_and_one_step_either_side(self) -> None:
        """A value already at 2dp is unchanged; a step either side moves."""
        assert round_money(10.25) == 10.25
        assert round_money(10.2549) == 10.25
        assert round_money(10.2551) == 10.26

    def test_tie_breaking_is_asserted_not_assumed(self) -> None:
        """round() is half-to-even on exact binary ties; 1.005 is not one.

        0.125 is exactly representable, so it is a genuine tie and resolves to
        the even last digit. 1.005 and 2.675 are stored slightly below their
        decimal value, so their binary representation decides instead.
        """
        assert round_money(0.125) == 0.12
        assert round_money(1.005) == 1.0
        assert round_money(2.675) == 2.67


class TestRoundQuantity:
    """Share quantities round to four places at the write boundary."""

    def test_rounds_ordinary_values(self) -> None:
        """Fractional-share quantities round to four places."""
        assert round_quantity(1.23456) == 1.2346
        assert round_quantity(0.12345) == 0.1235
        assert round_quantity(10.0) == 10.0

    def test_boundary_and_one_step_either_side(self) -> None:
        """A value already at 4dp is unchanged; a step either side moves."""
        assert round_quantity(0.0001) == 0.0001
        assert round_quantity(0.00009) == 0.0001
        assert round_quantity(0.000149) == 0.0001

    def test_tie_breaking_is_asserted_not_assumed(self) -> None:
        """The 4dp tie boundary resolves by the stored binary value."""
        assert round_quantity(0.00005) == 0.0001
        assert round_quantity(0.00015) == 0.0001
        assert round_quantity(0.00025) == 0.0003


class TestIsZero:
    """The epsilon boundary and one step either side."""

    def test_below_epsilon_is_zero(self) -> None:
        """A remainder an order of magnitude under the epsilon is no holding."""
        assert is_zero(1e-7) is True
        assert is_zero(0.0) is True

    def test_negative_residue_is_zero(self) -> None:
        """Residue is signless: a small negative remainder is also no holding."""
        assert is_zero(-1e-7) is True

    def test_at_and_above_epsilon_is_not_zero(self) -> None:
        """The comparison is strict, so the epsilon itself is a real holding."""
        assert is_zero(1e-6) is False
        assert is_zero(1.1e-6) is False

    def test_smallest_storable_quantity_is_not_zero(self) -> None:
        """The epsilon can never swallow a quantity the schema can store."""
        assert is_zero(round_quantity(0.0001)) is False


class TestFullSellLeavesNoResidue:
    """Selling an entire position provably leaves no fractional-share row."""

    def test_exact_full_sell(self) -> None:
        """Subtracting a stored quantity from itself leaves nothing."""
        held = round_quantity(12.3456)
        assert is_zero(held - held)

    def test_full_sell_after_partial_buys(self) -> None:
        """Accumulated float error after partial buys is residue, not shares."""
        accumulated = 0.1 + 0.2
        held = round_quantity(accumulated)
        remaining = accumulated - held
        assert remaining != 0.0
        assert is_zero(remaining)
