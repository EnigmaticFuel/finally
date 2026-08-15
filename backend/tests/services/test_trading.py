"""Tests for the trade execution seam."""

from __future__ import annotations

import asyncio
import math
import sqlite3
from pathlib import Path

import pytest

from app.db.connection import connect, writing
from app.db.queries import get_position, get_snapshots
from app.db.seed import DEFAULT_TICKERS, STARTING_CASH, apply_schema, seed_fresh
from app.market import PriceCache
from app.services import TradeError, execute_trade
from app.services.trading import _format_shares, validate_quantity
from tests.services.conftest import RecordingSource

FILL_PRICE = 100.0
QUANTITY = 3.0
UNWATCHED = "PYPL"
PRICELESS = "ZZZ"

AWKWARD_PRICE = 190.52
"""A price whose product with a fractional quantity is not already at 2dp.

FILL_PRICE times any whole quantity lands exactly on a stored cent, so the gap
between the raw balance and the stored one is invisible at that price. Every
storage-precision assertion in this module uses this one instead.
"""


class MovingCache(PriceCache):
    """A cache that ticks once, between the two reads execute_trade makes.

    A subclass rather than a monkeypatch because the divergence under test is
    only observable when the second read differs from the first. execute_trade
    reads the cache twice by design - wait_for_price for the fill, get_all for
    the snapshot's price map - and no static fixture can make those two disagree.
    """

    def __init__(self, ticker: str, moved_price: float) -> None:
        super().__init__()
        self._moving_ticker = ticker
        self._moved_price = moved_price

    def get_all(self) -> dict[str, object]:
        """Move the price, then answer. get_price reads get(), so the fill is unaffected."""
        self.update(self._moving_ticker, self._moved_price)
        return super().get_all()


@pytest.fixture
def seeded_db(db_path: Path) -> Path:
    """A real file database carrying the standard first-launch seed."""
    with connect(db_path) as conn:
        apply_schema(conn)
        seed_fresh(conn)
    return db_path


@pytest.fixture
def priced_cache() -> PriceCache:
    """A cache holding one price, so no arithmetic test waits on a live feed.

    It exists only so the figures in this module are exact: FILL_PRICE stays
    100.0 and no simulated tick can clobber it mid-assertion.

    It must never back an assertion about the auto-add-on-trade path. Writing
    the price by hand performs the very registration step production omits, so a
    test resting on this fixture would pass while the behavior was unreachable
    through the assembled app - which is exactly how G-01 stayed invisible behind
    a green suite. That claim belongs to tests/test_feed_reconciliation.py, which
    drives the real lifespan and the real simulator.
    """
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


async def test_buy_fills_and_lands_everywhere(
    seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
) -> None:
    """One buy debits cash, creates the position, watches the ticker, snapshots.

    All four in one assertion block deliberately: they happen inside a single
    transaction, so proving them separately would not prove they are atomic.
    """
    before = len(_rows(seeded_db, "SELECT id FROM portfolio_snapshots"))

    result = await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", QUANTITY)

    assert result.fill_price == FILL_PRICE
    assert result.cash_balance == STARTING_CASH - FILL_PRICE * QUANTITY

    position = _rows(seeded_db, "SELECT quantity, avg_cost FROM positions WHERE ticker = ?", UNWATCHED)
    assert len(position) == 1
    assert position[0]["quantity"] == QUANTITY
    assert position[0]["avg_cost"] == FILL_PRICE

    watched = _rows(seeded_db, "SELECT ticker FROM watchlist WHERE ticker = ?", UNWATCHED)
    assert len(watched) == 1, "the watchlist row lands in the same transaction as the position"

    after = len(_rows(seeded_db, "SELECT id FROM portfolio_snapshots"))
    assert after == before + 1, "every trade writes exactly one snapshot (PORT-11)"


async def test_stored_cash_matches_the_reported_balance(
    seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
) -> None:
    """The balance in the response is the balance in the database."""
    result = await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", QUANTITY)

    stored = _rows(seeded_db, "SELECT cash_balance FROM users_profile")[0]["cash_balance"]
    assert stored == pytest.approx(result.cash_balance)


async def test_the_reported_balance_is_the_stored_balance_to_the_last_digit(
    seeded_db: Path, recording_source: RecordingSource
) -> None:
    """A buy whose raw balance is not already at 2dp still reports the stored figure.

    Not a duplicate of the test above, which cannot fail: pytest.approx at its
    default relative tolerance treats a 0.002 gap on roughly 9981 as equal, so
    it stayed green while the response reported 9980.948 against a stored
    9980.95. A client that renders the response and then refetches /api/portfolio
    would see the balance change with no trade behind it.

    0.1 at 190.52 is the diverging case. Three whole shares at the same price
    gives 9428.44, which is already exactly its own 2dp rounding and would
    likewise prove nothing.
    """
    price_cache = PriceCache()
    price_cache.update(UNWATCHED, AWKWARD_PRICE)

    result = await execute_trade(seeded_db, price_cache, recording_source, UNWATCHED, "buy", 0.1)

    assert result.cash_balance == 9980.95
    assert result.cash_balance == _cash(seeded_db)


async def test_a_sell_also_reports_the_stored_balance_exactly(
    seeded_db: Path, recording_source: RecordingSource
) -> None:
    """The sell branch computes its one cash figure at storage precision too."""
    price_cache = PriceCache()
    price_cache.update(UNWATCHED, AWKWARD_PRICE)
    await execute_trade(seeded_db, price_cache, recording_source, UNWATCHED, "buy", 0.1)

    result = await execute_trade(seeded_db, price_cache, recording_source, UNWATCHED, "sell", 0.1)

    assert result.cash_balance == _cash(seeded_db)


async def test_rejected_buy_rolls_the_whole_unit_back(
    seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
) -> None:
    """A trade the cash cannot cover leaves no watchlist row, no cash change, no snapshot.

    The watchlist row is the sharp end: add_watchlist_ticker runs before the cash
    guard, so only the rollback keeps a rejected trade from leaving an orphan.
    """
    snapshots_before = len(_rows(seeded_db, "SELECT id FROM portfolio_snapshots"))
    unaffordable = STARTING_CASH / FILL_PRICE + 1

    with pytest.raises(TradeError, match="Insufficient cash"):
        await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", unaffordable)

    assert _rows(seeded_db, "SELECT ticker FROM watchlist WHERE ticker = ?", UNWATCHED) == []
    assert _rows(seeded_db, "SELECT ticker FROM positions") == []
    assert _rows(seeded_db, "SELECT cash_balance FROM users_profile")[0][0] == STARTING_CASH
    assert len(_rows(seeded_db, "SELECT id FROM portfolio_snapshots")) == snapshots_before


async def test_the_snapshot_values_the_traded_ticker_at_the_fill_price(
    seeded_db: Path, recording_source: RecordingSource
) -> None:
    """A cache tick between the fill and the snapshot does not move the snapshot.

    portfolio_snapshots is append-only and the P&L chart trusts it, so a row
    valued at a price no trade ever executed at is not correctable later. The
    fill is overlaid onto the price map rather than the two reads being made
    atomic: the cache is rewritten every 500ms by design.
    """
    price_cache = MovingCache(UNWATCHED, moved_price=200.00)
    price_cache.update(UNWATCHED, AWKWARD_PRICE)
    before = len(_snapshots(seeded_db))

    result = await execute_trade(seeded_db, price_cache, recording_source, UNWATCHED, "buy", 2.0)

    assert result.fill_price == AWKWARD_PRICE
    assert len(_snapshots(seeded_db)) == before + 1
    assert _snapshots(seeded_db)[0]["total_value"] == pytest.approx(
        result.cash_balance + 2.0 * result.fill_price
    )


class TestSell:
    """Settlement and refusal on the sell side (PORT-03, PORT-05, PORT-09).

    Every holding is established by executing a real buy first, so each sell
    test also re-exercises the seam it depends on rather than a hand-written row.
    """

    async def test_partial_sell_credits_cash_and_leaves_avg_cost_alone(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """A partial sell adds the proceeds to cash and does not touch the cost basis."""
        await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", 10.0)
        cash_after_buy = _cash(seeded_db)
        avg_cost_before = _position(seeded_db, UNWATCHED)["avg_cost"]

        result = await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "sell", 4.0)

        assert result.total_cost == FILL_PRICE * 4.0
        assert result.cash_balance == pytest.approx(cash_after_buy + FILL_PRICE * 4.0)
        assert _cash(seeded_db) == pytest.approx(cash_after_buy + FILL_PRICE * 4.0)

        position = _position(seeded_db, UNWATCHED)
        assert position["quantity"] == pytest.approx(6.0)
        assert position["avg_cost"] == avg_cost_before

    async def test_full_sell_deletes_the_position_row(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """Selling the entire holding removes the row rather than storing a zero."""
        await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", 10.0)

        await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "sell", 10.0)

        assert _position(seeded_db, UNWATCHED) is None

    async def test_full_sell_snapshot_values_the_portfolio_as_cash_alone(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """The snapshot the closing sell writes sees no position, because it is gone."""
        await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", 10.0)

        result = await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "sell", 10.0)

        assert _snapshots(seeded_db)[0]["total_value"] == pytest.approx(result.cash_balance)

    async def test_oversell_is_refused_and_the_database_is_unmoved(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """One 4dp step beyond the holding is refused with nothing written."""
        await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", 10.0)
        cash_before = _cash(seeded_db)
        snapshots_before = len(_snapshots(seeded_db))
        trades_before = len(_rows(seeded_db, "SELECT id FROM trades"))

        with pytest.raises(TradeError, match="Insufficient shares"):
            await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "sell", 10.0001)

        assert _cash(seeded_db) == cash_before
        assert _position(seeded_db, UNWATCHED)["quantity"] == pytest.approx(10.0)
        assert len(_snapshots(seeded_db)) == snapshots_before
        assert len(_rows(seeded_db, "SELECT id FROM trades")) == trades_before

    async def test_oversell_message_names_both_share_figures(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """The refusal states shares needed and shares held, without trailing zeros."""
        await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", 10.0)

        with pytest.raises(TradeError, match=r"need 11 PYPL, have 10\b"):
            await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "sell", 11.0)

    async def test_selling_an_unheld_ticker_reports_zero_held(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """A ticker with no positions row counts as zero shares, not as a missing thing."""
        with pytest.raises(TradeError, match=r"Insufficient shares.*have 0\b"):
            await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "sell", 1.0)

    async def test_a_dust_holding_is_reported_without_exponent_notation(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """A holding below 4dp reads as 0 shares, never as 1e-05.

        The row is hand-written deliberately. upsert_position rounds through
        round_quantity at 4dp, so a 1e-05 holding is unreachable through the
        normal write path - which is exactly why the g-format's switch to
        exponent notation below 1e-4 survived every existing test. The message is
        shown to the user verbatim, and 1e-05 shares is not a figure anyone can
        act on.
        """
        with connect(seeded_db) as conn:
            with writing(conn):
                conn.execute(
                    "INSERT INTO positions"
                    " (id, user_id, ticker, quantity, avg_cost, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    ("dust-row", "default", UNWATCHED, 1e-05, 100.0, "2026-08-15T00:00:00Z"),
                )

        with pytest.raises(TradeError) as refusal:
            await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "sell", 1.0)

        message = str(refusal.value)
        assert "e-" not in message
        assert "E-" not in message
        assert "have 0" in message

    async def test_selling_exactly_the_holding_succeeds(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """The boundary is a fill, not a refusal."""
        await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", 2.5)

        result = await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "sell", 2.5)

        assert result.total_cost == FILL_PRICE * 2.5
        assert _position(seeded_db, UNWATCHED) is None

    async def test_selling_one_step_short_leaves_a_dust_row(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """One 4dp step less than held leaves a real 0.0001-share holding behind."""
        await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", 10.0)

        await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "sell", 9.9999)

        assert _position(seeded_db, UNWATCHED)["quantity"] == pytest.approx(0.0001)

    async def test_repeated_fractional_sells_delete_the_row_at_zero(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """Float residue from fractional sells is residue, not a holding."""
        await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", 0.6)

        for quantity in (0.3, 0.1, 0.2):
            await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "sell", quantity)

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


class TestFormatShares:
    """Rendering a share count for a message the user reads verbatim (PORT-05)."""

    @pytest.mark.parametrize(
        ("value", "rendered"),
        [
            (11.0, "11"),
            (10.0, "10"),
            (2.5, "2.5"),
            (0.0001, "0.0001"),
            (0.0, "0"),
            (1e-05, "0"),
        ],
    )
    def test_renders_at_stored_precision_without_trailing_zeros(
        self, value: float, rendered: str
    ) -> None:
        """Four places is the stored quantity precision, with the padding stripped."""
        assert _format_shares(value) == rendered

    def test_a_dust_value_never_renders_in_exponent_form(self) -> None:
        """The g presentation type switches to exponents below 1e-4; this must not."""
        assert "e" not in _format_shares(1e-05)


class TestInsufficientCash:
    """Both sides of the cash boundary, and what a refusal leaves behind (PORT-04)."""

    async def test_buy_for_exactly_the_whole_balance_fills(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """The boundary is a fill, not a rejection."""
        result = await execute_trade(
            seeded_db, priced_cache, recording_source, UNWATCHED, "buy", STARTING_CASH / FILL_PRICE
        )

        assert result.cash_balance == pytest.approx(0.0)

    async def test_a_buy_for_exactly_the_balance_stores_positive_zero(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """Spending the balance down to nothing stores 0.0, never -0.0.

        A negative zero serializes as -0.0 and renders as $-0.00, which reads to
        the user as a debt in an account that cannot go negative. Comparing raw
        cost against raw cash before any rounding is what makes it unreachable.
        """
        await execute_trade(
            seeded_db, priced_cache, recording_source, UNWATCHED, "buy", STARTING_CASH / FILL_PRICE
        )

        stored = _cash(seeded_db)
        assert stored == 0.0
        assert math.copysign(1.0, stored) == 1.0

    async def test_a_sub_cent_overdraft_is_refused_and_nothing_lands(
        self, seeded_db: Path, recording_source: RecordingSource
    ) -> None:
        """A cost over the balance by less than half a cent is still an overdraft.

        The old guard compared round_money(cost) against round_money(cash), so
        10000.004 against 10000.0 rounded to 10000.0 against 10000.0 and filled.
        The trade then stored -0.0 and left a position, a watchlist row and a
        snapshot behind it - a reachable breach of the no-margin rule.

        5000.002 is a legal 4dp quantity, so validate_quantity passes it straight
        through and the cash guard is genuinely the thing under test.
        """
        price_cache = PriceCache()
        price_cache.update(UNWATCHED, 2.00)
        snapshots_before = len(_snapshots(seeded_db))

        with pytest.raises(TradeError, match="Insufficient cash"):
            await execute_trade(
                seeded_db, price_cache, recording_source, UNWATCHED, "buy", 5000.002
            )

        assert _cash(seeded_db) == STARTING_CASH
        assert _rows(seeded_db, "SELECT ticker FROM positions") == []
        assert _rows(seeded_db, "SELECT ticker FROM watchlist WHERE ticker = ?", UNWATCHED) == []
        assert len(_snapshots(seeded_db)) == snapshots_before

    async def test_buy_for_one_cent_more_than_the_balance_is_refused(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """A cent past the balance raises, naming both figures at two decimal places."""
        one_cent_over = (STARTING_CASH + 0.01) / FILL_PRICE

        with pytest.raises(TradeError) as refusal:
            await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", one_cent_over)

        message = str(refusal.value)
        assert f"need ${STARTING_CASH + 0.01:.2f}" in message
        assert f"have ${STARTING_CASH:.2f}" in message
        assert f"{STARTING_CASH:,.2f}" not in message, (
            "the client renders this verbatim, so the figures carry no thousands separator"
        )

    async def test_refused_buy_leaves_the_ticker_off_the_watchlist(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """add_watchlist_ticker ran first inside the transaction; the rollback undid it."""
        assert UNWATCHED not in DEFAULT_TICKERS

        with pytest.raises(TradeError, match="Insufficient cash"):
            await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", STARTING_CASH)

        assert _rows(seeded_db, "SELECT ticker FROM watchlist WHERE ticker = ?", UNWATCHED) == []

    async def test_every_buy_against_a_spent_balance_is_refused(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """A zero balance reads as zero at two decimal places, not as an absent figure.

        The balance is spent down through a real trade rather than by editing the
        profile row, because the point is that the guard reads live cash from
        inside the transaction.
        """
        await execute_trade(
            seeded_db, priced_cache, recording_source, UNWATCHED, "buy", STARTING_CASH / FILL_PRICE
        )

        with pytest.raises(TradeError) as refusal:
            await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", 1.0)

        assert "have $0.00" in str(refusal.value)

    async def test_a_portfolio_with_no_positions_refuses_cleanly(
        self, seeded_db: Path, priced_cache: PriceCache, recording_source: RecordingSource
    ) -> None:
        """An unaffordable first trade rejects on cash, not on an absent position row."""
        assert _rows(seeded_db, "SELECT ticker FROM positions") == []

        with pytest.raises(TradeError, match="Insufficient cash"):
            await execute_trade(seeded_db, priced_cache, recording_source, UNWATCHED, "buy", STARTING_CASH)


class TestPriceWait:
    """The trade path routes through wait_for_price and reports it faithfully (PORT-08).

    wait_for_price is tested in the frozen market module; what is proven here is
    that a trade waits on it, fills at exactly what it returned, and lets its
    failure through unchanged. Timings are one-sided and no elapsed duration is
    asserted: this repo already carries one timer-granularity flake on Windows,
    and a second one would buy a boundary nobody can observe.
    """

    async def test_a_price_arriving_during_the_wait_fills(
        self, seeded_db: Path, recording_source: RecordingSource
    ) -> None:
        """A ticker priced 50ms after the call fills at that price, inside the 2s window."""
        price_cache = PriceCache()

        async def seed_later() -> None:
            await asyncio.sleep(0.05)
            price_cache.update(PRICELESS, FILL_PRICE)

        task = asyncio.create_task(seed_later())
        result = await execute_trade(seeded_db, price_cache, recording_source, PRICELESS, "buy", 1.0)

        assert result.fill_price == FILL_PRICE
        await task

    async def test_a_ticker_that_never_prices_raises_after_the_wait(
        self, seeded_db: Path, recording_source: RecordingSource
    ) -> None:
        """The cache's own message, naming the ticker, reaches the caller unchanged.

        wait_for_price raises a plain ValueError, which execute_trade translates
        into TradeError at the seam, so this reaches 400 through the taxonomy's
        own row rather than through a handler on the built-in class. The message
        fragment is what is asserted: TradeError subclasses ValueError, so
        catching the type alone would also pass if the quantity validator had
        fired instead.

        The registration assertion pins the other half: the symbol was offered to
        the feed before the wait began, so the expiry is a source that genuinely
        produces nothing rather than a symbol nobody ever told the feed about.
        """
        with pytest.raises(ValueError, match=f"No price available for {PRICELESS}"):
            await execute_trade(seeded_db, PriceCache(), recording_source, PRICELESS, "buy", 1.0)

        assert recording_source.added == [PRICELESS]

    async def test_the_fill_after_the_wait_is_the_cache_float_untouched(
        self, seeded_db: Path, recording_source: RecordingSource
    ) -> None:
        """The service returns the cache's own float and rounds nothing of its own.

        PriceCache.update normalizes every price to cents as it stores it, so a
        sub-cent price never reaches this seam at all - that rounding belongs to
        the frozen market module, upstream. What is pinned here is that the
        service adds none of its own: fill_price is exactly what wait_for_price
        returned, and total_cost is the raw product, which a round_money applied
        to the returned figure would visibly change.
        """
        price_cache = PriceCache()
        price_cache.update(PRICELESS, 190.123456)
        cached = price_cache.get_price(PRICELESS)

        result = await execute_trade(seeded_db, price_cache, recording_source, PRICELESS, "buy", 0.3333)

        assert result.fill_price == cached
        assert result.total_cost == cached * 0.3333
        assert result.total_cost != round(result.total_cost, 2), "the derived figure stays raw"

    async def test_a_bad_quantity_is_reported_before_the_price_wait(
        self, seeded_db: Path, recording_source: RecordingSource
    ) -> None:
        """Cheap checks run first, so the failure names the quantity, not the price.

        Had the price wait run first, this call would burn the full two-second
        window and then report the wrong reason.

        The empty added list is the ordering guard on registration: a malformed
        quantity must reach neither the market source nor the price wait, so a
        symbol nobody can trade is never handed to the feed.
        """
        with pytest.raises(TradeError) as refusal:
            await execute_trade(seeded_db, PriceCache(), recording_source, PRICELESS, "buy", 0)

        assert POSITIVITY in str(refusal.value)
        assert "No price available" not in str(refusal.value)
        assert recording_source.added == []
