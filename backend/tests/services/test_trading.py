"""Tests for the trade execution seam."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db.connection import connect
from app.db.queries import get_position, get_snapshots
from app.db.seed import DEFAULT_TICKERS, STARTING_CASH, apply_schema, seed_fresh
from app.market import PriceCache
from app.services import TradeError, execute_trade
from app.services.trading import validate_quantity

FILL_PRICE = 100.0
QUANTITY = 3.0
UNWATCHED = "PYPL"


@pytest.fixture
def seeded_db(db_path: Path) -> Path:
    """A real file database carrying the standard first-launch seed."""
    with connect(db_path) as conn:
        apply_schema(conn)
        seed_fresh(conn)
    return db_path


@pytest.fixture
def cache() -> PriceCache:
    """A cache holding one price, so no test waits on a live feed."""
    price_cache = PriceCache()
    price_cache.update(UNWATCHED, FILL_PRICE)
    return price_cache


def _rows(db: Path, sql: str, *args: object) -> list[sqlite3.Row]:
    with connect(db) as conn:
        return conn.execute(sql, args).fetchall()


def _position(db: Path, ticker: str) -> sqlite3.Row | None:
    with connect(db) as conn:
        return get_position(conn, ticker)


def _snapshots(db: Path) -> list[sqlite3.Row]:
    with connect(db) as conn:
        return get_snapshots(conn)


def _cash(db: Path) -> float:
    return _rows(db, "SELECT cash_balance FROM users_profile")[0]["cash_balance"]


async def test_buy_fills_and_lands_everywhere(seeded_db: Path, cache: PriceCache) -> None:
    """One buy debits cash, creates the position, watches the ticker, snapshots.

    All four in one assertion block deliberately: they happen inside a single
    transaction, so proving them separately would not prove they are atomic.
    """
    before = len(_rows(seeded_db, "SELECT id FROM portfolio_snapshots"))

    result = await execute_trade(seeded_db, cache, UNWATCHED, "buy", QUANTITY)

    assert result.fill_price == FILL_PRICE
    assert result.cash_balance == STARTING_CASH - FILL_PRICE * QUANTITY

    position = _rows(seeded_db, "SELECT quantity, avg_cost FROM positions WHERE ticker = ?", UNWATCHED)
    assert len(position) == 1
    assert position[0]["quantity"] == QUANTITY
    assert position[0]["avg_cost"] == FILL_PRICE

    watched = _rows(seeded_db, "SELECT ticker FROM watchlist WHERE ticker = ?", UNWATCHED)
    assert len(watched) == 1, "a traded ticker joins the watchlist (PORT-07)"

    after = len(_rows(seeded_db, "SELECT id FROM portfolio_snapshots"))
    assert after == before + 1, "every trade writes exactly one snapshot (PORT-11)"


async def test_stored_cash_matches_the_reported_balance(
    seeded_db: Path, cache: PriceCache
) -> None:
    """The balance in the response is the balance in the database."""
    result = await execute_trade(seeded_db, cache, UNWATCHED, "buy", QUANTITY)

    stored = _rows(seeded_db, "SELECT cash_balance FROM users_profile")[0]["cash_balance"]
    assert stored == pytest.approx(result.cash_balance)


async def test_rejected_buy_rolls_the_whole_unit_back(
    seeded_db: Path, cache: PriceCache
) -> None:
    """A trade the cash cannot cover leaves no watchlist row, no cash change, no snapshot.

    The watchlist row is the sharp end: add_watchlist_ticker runs before the cash
    guard, so only the rollback keeps a rejected trade from leaving an orphan.
    """
    snapshots_before = len(_rows(seeded_db, "SELECT id FROM portfolio_snapshots"))
    unaffordable = STARTING_CASH / FILL_PRICE + 1

    with pytest.raises(TradeError, match="Insufficient cash"):
        await execute_trade(seeded_db, cache, UNWATCHED, "buy", unaffordable)

    assert _rows(seeded_db, "SELECT ticker FROM watchlist WHERE ticker = ?", UNWATCHED) == []
    assert _rows(seeded_db, "SELECT ticker FROM positions") == []
    assert _rows(seeded_db, "SELECT cash_balance FROM users_profile")[0][0] == STARTING_CASH
    assert len(_rows(seeded_db, "SELECT id FROM portfolio_snapshots")) == snapshots_before


class TestSell:
    """Settlement and refusal on the sell side (PORT-03, PORT-05, PORT-09).

    Every holding is established by executing a real buy first, so each sell
    test also re-exercises the seam it depends on rather than a hand-written row.
    """

    async def test_partial_sell_credits_cash_and_leaves_avg_cost_alone(
        self, seeded_db: Path, cache: PriceCache
    ) -> None:
        """A partial sell adds the proceeds to cash and does not touch the cost basis."""
        await execute_trade(seeded_db, cache, UNWATCHED, "buy", 10.0)
        cash_after_buy = _cash(seeded_db)
        avg_cost_before = _position(seeded_db, UNWATCHED)["avg_cost"]

        result = await execute_trade(seeded_db, cache, UNWATCHED, "sell", 4.0)

        assert result.total_cost == FILL_PRICE * 4.0
        assert result.cash_balance == pytest.approx(cash_after_buy + FILL_PRICE * 4.0)
        assert _cash(seeded_db) == pytest.approx(cash_after_buy + FILL_PRICE * 4.0)

        position = _position(seeded_db, UNWATCHED)
        assert position["quantity"] == pytest.approx(6.0)
        assert position["avg_cost"] == avg_cost_before

    async def test_full_sell_deletes_the_position_row(
        self, seeded_db: Path, cache: PriceCache
    ) -> None:
        """Selling the entire holding removes the row rather than storing a zero."""
        await execute_trade(seeded_db, cache, UNWATCHED, "buy", 10.0)

        await execute_trade(seeded_db, cache, UNWATCHED, "sell", 10.0)

        assert _position(seeded_db, UNWATCHED) is None

    async def test_full_sell_snapshot_values_the_portfolio_as_cash_alone(
        self, seeded_db: Path, cache: PriceCache
    ) -> None:
        """The snapshot the closing sell writes sees no position, because it is gone."""
        await execute_trade(seeded_db, cache, UNWATCHED, "buy", 10.0)

        result = await execute_trade(seeded_db, cache, UNWATCHED, "sell", 10.0)

        assert _snapshots(seeded_db)[0]["total_value"] == pytest.approx(result.cash_balance)

    async def test_oversell_is_refused_and_the_database_is_unmoved(
        self, seeded_db: Path, cache: PriceCache
    ) -> None:
        """One 4dp step beyond the holding is refused with nothing written."""
        await execute_trade(seeded_db, cache, UNWATCHED, "buy", 10.0)
        cash_before = _cash(seeded_db)
        snapshots_before = len(_snapshots(seeded_db))
        trades_before = len(_rows(seeded_db, "SELECT id FROM trades"))

        with pytest.raises(TradeError, match="Insufficient shares"):
            await execute_trade(seeded_db, cache, UNWATCHED, "sell", 10.0001)

        assert _cash(seeded_db) == cash_before
        assert _position(seeded_db, UNWATCHED)["quantity"] == pytest.approx(10.0)
        assert len(_snapshots(seeded_db)) == snapshots_before
        assert len(_rows(seeded_db, "SELECT id FROM trades")) == trades_before

    async def test_oversell_message_names_both_share_figures(
        self, seeded_db: Path, cache: PriceCache
    ) -> None:
        """The refusal states shares needed and shares held, without trailing zeros."""
        await execute_trade(seeded_db, cache, UNWATCHED, "buy", 10.0)

        with pytest.raises(TradeError, match=r"need 11 PYPL, have 10\b"):
            await execute_trade(seeded_db, cache, UNWATCHED, "sell", 11.0)

    async def test_selling_an_unheld_ticker_reports_zero_held(
        self, seeded_db: Path, cache: PriceCache
    ) -> None:
        """A ticker with no positions row counts as zero shares, not as a missing thing."""
        with pytest.raises(TradeError, match=r"Insufficient shares.*have 0\b"):
            await execute_trade(seeded_db, cache, UNWATCHED, "sell", 1.0)

    async def test_selling_exactly_the_holding_succeeds(
        self, seeded_db: Path, cache: PriceCache
    ) -> None:
        """The boundary is a fill, not a refusal."""
        await execute_trade(seeded_db, cache, UNWATCHED, "buy", 2.5)

        result = await execute_trade(seeded_db, cache, UNWATCHED, "sell", 2.5)

        assert result.total_cost == FILL_PRICE * 2.5
        assert _position(seeded_db, UNWATCHED) is None

    async def test_selling_one_step_short_leaves_a_dust_row(
        self, seeded_db: Path, cache: PriceCache
    ) -> None:
        """One 4dp step less than held leaves a real 0.0001-share holding behind."""
        await execute_trade(seeded_db, cache, UNWATCHED, "buy", 10.0)

        await execute_trade(seeded_db, cache, UNWATCHED, "sell", 9.9999)

        assert _position(seeded_db, UNWATCHED)["quantity"] == pytest.approx(0.0001)

    async def test_repeated_fractional_sells_delete_the_row_at_zero(
        self, seeded_db: Path, cache: PriceCache
    ) -> None:
        """Float residue from fractional sells is residue, not a holding."""
        await execute_trade(seeded_db, cache, UNWATCHED, "buy", 0.6)

        for quantity in (0.3, 0.1, 0.2):
            await execute_trade(seeded_db, cache, UNWATCHED, "sell", quantity)

        assert _position(seeded_db, UNWATCHED) is None


FINITENESS = "must be a finite number"
POSITIVITY = "must be greater than zero"
PRECISION = "at most 4 decimal places"


class TestQuantityValidation:
    """Every quantity failure mode, each proven by its own branch's wording (PORT-06).

    TradeError subclasses ValueError, so asserting on the exception type alone
    would discriminate nothing: three cases written that way would all pass with
    two of the three branches dead. Every case matches on its own message.
    """

    def test_accepts_the_smallest_quantity_at_four_places(self) -> None:
        """0.0001 is exactly representable at 4dp and comes back unchanged."""
        assert validate_quantity(0.0001) == 0.0001

    @pytest.mark.parametrize(
        ("quantity", "wording"),
        [
            (float("inf"), FINITENESS),
            (float("-inf"), FINITENESS),
            (float("nan"), FINITENESS),
            (0, POSITIVITY),
            (-1, POSITIVITY),
            (-0.5, POSITIVITY),
            (0.00001, PRECISION),
            (1e-9, PRECISION),
        ],
    )
    def test_rejects_the_quantity_naming_its_own_branch(
        self, quantity: float, wording: str
    ) -> None:
        """Each rejected quantity raises with the wording of the rule it broke."""
        with pytest.raises(TradeError, match=wording):
            validate_quantity(quantity)

    def test_non_finite_quantity_reports_finiteness_not_precision(self) -> None:
        """inf and nan share one wording, and it is not the precision wording.

        round(float('inf'), 4) returns inf rather than raising, so a precision
        check placed first would silently accept an infinite quantity and let it
        reach the cash arithmetic. The check order is the entire mitigation, and
        these two branches must not be provable by one another.
        """
        with pytest.raises(TradeError) as infinite:
            validate_quantity(float("inf"))
        with pytest.raises(TradeError) as not_a_number:
            validate_quantity(float("nan"))
        with pytest.raises(TradeError) as too_precise:
            validate_quantity(1e-9)

        assert FINITENESS in str(infinite.value)
        assert FINITENESS in str(not_a_number.value)
        assert PRECISION in str(too_precise.value)
        assert FINITENESS not in str(too_precise.value)


class TestInsufficientCash:
    """Both sides of the cash boundary, and what a refusal leaves behind (PORT-04)."""

    async def test_buy_for_exactly_the_whole_balance_fills(
        self, seeded_db: Path, cache: PriceCache
    ) -> None:
        """The boundary is a fill, not a rejection."""
        result = await execute_trade(
            seeded_db, cache, UNWATCHED, "buy", STARTING_CASH / FILL_PRICE
        )

        assert result.cash_balance == pytest.approx(0.0)

    async def test_buy_for_one_cent_more_than_the_balance_is_refused(
        self, seeded_db: Path, cache: PriceCache
    ) -> None:
        """A cent past the balance raises, naming both figures at two decimal places."""
        one_cent_over = (STARTING_CASH + 0.01) / FILL_PRICE

        with pytest.raises(TradeError) as refusal:
            await execute_trade(seeded_db, cache, UNWATCHED, "buy", one_cent_over)

        message = str(refusal.value)
        assert f"need ${STARTING_CASH + 0.01:.2f}" in message
        assert f"have ${STARTING_CASH:.2f}" in message
        assert f"{STARTING_CASH:,.2f}" not in message, (
            "the client renders this verbatim, so the figures carry no thousands separator"
        )

    async def test_refused_buy_leaves_the_ticker_off_the_watchlist(
        self, seeded_db: Path, cache: PriceCache
    ) -> None:
        """add_watchlist_ticker ran first inside the transaction; the rollback undid it."""
        assert UNWATCHED not in DEFAULT_TICKERS

        with pytest.raises(TradeError, match="Insufficient cash"):
            await execute_trade(seeded_db, cache, UNWATCHED, "buy", STARTING_CASH)

        assert _rows(seeded_db, "SELECT ticker FROM watchlist WHERE ticker = ?", UNWATCHED) == []

    async def test_every_buy_against_a_spent_balance_is_refused(
        self, seeded_db: Path, cache: PriceCache
    ) -> None:
        """A zero balance reads as zero at two decimal places, not as an absent figure.

        The balance is spent down through a real trade rather than by editing the
        profile row, because the point is that the guard reads live cash from
        inside the transaction.
        """
        await execute_trade(seeded_db, cache, UNWATCHED, "buy", STARTING_CASH / FILL_PRICE)

        with pytest.raises(TradeError) as refusal:
            await execute_trade(seeded_db, cache, UNWATCHED, "buy", 1.0)

        assert "have $0.00" in str(refusal.value)

    async def test_a_portfolio_with_no_positions_refuses_cleanly(
        self, seeded_db: Path, cache: PriceCache
    ) -> None:
        """An unaffordable first trade rejects on cash, not on an absent position row."""
        assert _rows(seeded_db, "SELECT ticker FROM positions") == []

        with pytest.raises(TradeError, match="Insufficient cash"):
            await execute_trade(seeded_db, cache, UNWATCHED, "buy", STARTING_CASH)
