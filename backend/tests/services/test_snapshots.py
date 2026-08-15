"""Tests for the background portfolio value recorder.

Every database here is a real file under tmp_path. :memory: would give each
connection its own empty database and could not exercise the schema the way the
app does.

No test waits for the real interval and none patches it. The loop body is
callable on its own, so the write rules are proven directly, and the loop itself
is proven only for the one thing it adds: that it sleeps before it writes.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from app.db.connection import connect
from app.db.money import round_money
from app.db.queries import (
    get_positions,
    get_profile,
    get_snapshots,
    update_cash_balance,
    upsert_position,
)
from app.db.seed import STARTING_CASH, apply_schema, seed_fresh
from app.market import PriceCache
from app.services.snapshots import (
    SNAPSHOT_INTERVAL_SECONDS,
    record_snapshot,
    snapshot_loop,
)
from app.services.trading import execute_trade
from tests.services.conftest import RecordingSource

TICKER = "AAPL"
PRECISE_QUANTITY = 1.2345
PRECISE_PRICE = 190.57
COLLISION_PRICE = 100.0
COLLISION_ROUNDS = 5


@pytest.fixture
def seeded_db(db_path: Path) -> Path:
    """A real file database carrying the standard first-launch seed.

    The seed writes one snapshot at STARTING_CASH, so every test here starts with
    exactly one row and a baseline to compare against.
    """
    with connect(db_path) as conn:
        apply_schema(conn)
        seed_fresh(conn)
    return db_path


def _snapshots(db: Path) -> list[sqlite3.Row]:
    """Every snapshot row, newest first."""
    with connect(db) as conn:
        return get_snapshots(conn)


def _cash(db: Path) -> float:
    with connect(db) as conn:
        return get_profile(conn)["cash_balance"]


def _priced_cache(ticker: str = TICKER, price: float = COLLISION_PRICE) -> PriceCache:
    """A bare cache holding one price.

    The simulator no-ops before start(), so a test that wanted prices from a real
    source would prove nothing. Seeding the cache directly is the house pattern.
    """
    cache = PriceCache()
    cache.update(ticker, price)
    return cache


class TestRecordSnapshot:
    """One transaction, one skip rule, and what each of them writes."""

    async def test_an_unchanged_total_records_nothing(self, seeded_db: Path) -> None:
        """A freshly seeded all-cash portfolio matches its seed row, so it skips."""
        written = await record_snapshot(seeded_db, PriceCache())

        assert written is False
        assert len(_snapshots(seeded_db)) == 1

    async def test_a_moved_balance_records_the_new_total(self, seeded_db: Path) -> None:
        """A cash balance one cent away from the last snapshot writes one row."""
        moved = STARTING_CASH - 0.01
        with connect(seeded_db) as conn:
            update_cash_balance(conn, moved)

        written = await record_snapshot(seeded_db, PriceCache())

        rows = _snapshots(seeded_db)
        assert written is True
        assert len(rows) == 2
        assert rows[0]["total_value"] == moved

    async def test_a_second_call_with_nothing_changed_skips(self, seeded_db: Path) -> None:
        """Two calls over one change leave one new row, not two."""
        with connect(seeded_db) as conn:
            update_cash_balance(conn, STARTING_CASH - 0.01)

        first = await record_snapshot(seeded_db, PriceCache())
        second = await record_snapshot(seeded_db, PriceCache())

        assert (first, second) == (True, False)
        assert len(_snapshots(seeded_db)) == 2

    async def test_a_sub_cent_move_skips_and_a_full_cent_writes(self, seeded_db: Path) -> None:
        """The skip fires on the touching case and separates on the adjacent one.

        Both totals are built from a fractional holding rather than a cash write,
        because update_cash_balance rounds to cents and could not express a
        difference below one.
        """
        cache = _priced_cache(TICKER, 20.0)
        with connect(seeded_db) as conn:
            upsert_position(conn, TICKER, 0.0001, 20.0)

        skipped = await record_snapshot(seeded_db, cache)

        with connect(seeded_db) as conn:
            upsert_position(conn, TICKER, 0.0005, 20.0)
        wrote = await record_snapshot(seeded_db, cache)

        assert (skipped, wrote) == (False, True)
        assert len(_snapshots(seeded_db)) == 2

    async def test_an_empty_table_records_rather_than_skipping(self, seeded_db: Path) -> None:
        """With nothing to compare against, the honest answer is to record."""
        with connect(seeded_db) as conn:
            conn.execute("DELETE FROM portfolio_snapshots")

        written = await record_snapshot(seeded_db, PriceCache())

        rows = _snapshots(seeded_db)
        assert written is True
        assert len(rows) == 1
        assert rows[0]["total_value"] == STARTING_CASH

    async def test_a_portfolio_with_no_positions_values_as_cash_alone(
        self, seeded_db: Path
    ) -> None:
        """No holdings is not a failure: the total is exactly the cash balance."""
        with connect(seeded_db) as conn:
            update_cash_balance(conn, 8234.50)
            assert get_positions(conn) == []

        await record_snapshot(seeded_db, PriceCache())

        assert _snapshots(seeded_db)[0]["total_value"] == 8234.50

    async def test_a_priceless_position_contributes_nothing(self, seeded_db: Path) -> None:
        """value_portfolio's null rule is inherited, not restated.

        A held ticker the cache has never seen is excluded from the total rather
        than valued at a fabricated price.
        """
        with connect(seeded_db) as conn:
            update_cash_balance(conn, 5000.0)
            upsert_position(conn, TICKER, 10.0, 100.0)

        await record_snapshot(seeded_db, PriceCache())

        assert _snapshots(seeded_db)[0]["total_value"] == 5000.0

    async def test_the_recorded_total_is_not_rounded(self, seeded_db: Path) -> None:
        """The stored value is the raw float, not its cents-rounded form.

        round_money decides the skip and nothing else. The client recomputes this
        figure from the price stream, so a server-side rounding would visibly
        disagree with the client's own arithmetic.
        """
        with connect(seeded_db) as conn:
            upsert_position(conn, TICKER, PRECISE_QUANTITY, 100.0)

        await record_snapshot(seeded_db, _priced_cache(TICKER, PRECISE_PRICE))

        expected = STARTING_CASH + PRECISE_QUANTITY * PRECISE_PRICE
        assert expected != round(expected, 2)
        assert _snapshots(seeded_db)[0]["total_value"] == expected


class TestSnapshotLoop:
    """The loop adds one thing to the recorder: it sleeps before it writes."""

    def test_the_interval_is_thirty_seconds(self) -> None:
        """PLAN.md section 7 fixes the cadence; the constant is where it lives."""
        assert SNAPSHOT_INTERVAL_SECONDS == 30.0

    async def test_the_loop_writes_nothing_before_its_first_interval(
        self, seeded_db: Path
    ) -> None:
        """A task launched and cancelled immediately has recorded nothing.

        This is what makes a short-lived app safe: the write is unreachable
        within a test's lifetime, independently of where db_path points.
        """
        task = asyncio.create_task(snapshot_loop(seeded_db, PriceCache()))
        await asyncio.sleep(0.05)

        assert len(_snapshots(seeded_db)) == 1

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


class TestTradeCollision:
    """The recorder against the other writer of the same rows."""

    async def test_a_concurrent_trade_never_leaves_a_total_never_held(
        self, seeded_db: Path, recording_source: RecordingSource
    ) -> None:
        """Neither writer errors, and no snapshot records a state in between.

        Every buy is one share at one price, so a completed portfolio is worth
        exactly STARTING_CASH however many rounds have run: the cash leaving and
        the position arriving cancel. A snapshot taken between the two halves of
        a trade would therefore show a value one fill away from that, which is
        precisely what the assertion rejects.

        The interleaving is not forced. The assertion holds whether or not the
        two collided on any given run, which is what keeps this from becoming a
        timing-dependent test.
        """
        cache = _priced_cache(TICKER, COLLISION_PRICE)
        with connect(seeded_db) as conn:
            conn.execute("DELETE FROM portfolio_snapshots")

        for _ in range(COLLISION_ROUNDS):
            await asyncio.gather(
                execute_trade(seeded_db, cache, recording_source, TICKER, "buy", 1.0),
                record_snapshot(seeded_db, cache),
            )

        assert _cash(seeded_db) == STARTING_CASH - COLLISION_ROUNDS * COLLISION_PRICE
        totals = {round_money(row["total_value"]) for row in _snapshots(seeded_db)}
        assert totals == {STARTING_CASH}
