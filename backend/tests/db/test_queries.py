"""Tests for every query function, against a real seeded file database.

Every database here is a real file under tmp_path. :memory: would give each
connection its own empty database and could not exercise the schema the way the
app does.
"""

import datetime as dt
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db.connection import connect
from app.db.money import round_money, round_quantity
from app.db.queries import (
    delete_position,
    get_latest_snapshot,
    get_position,
    get_positions,
    get_profile,
    get_snapshots,
    insert_snapshot,
    insert_trade,
    update_cash_balance,
    upsert_position,
)
from app.db.seed import STARTING_CASH, apply_schema, seed_fresh


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A seeded throwaway file database, closed when the test ends."""
    with connect(tmp_path / "finally.db") as connection:
        apply_schema(connection)
        seed_fresh(connection)
        yield connection


class TestProfile:
    """The single profile row and its cash balance."""

    def test_get_profile_returns_the_seeded_row(self, conn: sqlite3.Connection) -> None:
        """A seeded database answers with the default user and starting cash."""
        row = get_profile(conn)
        assert row["id"] == "default"
        assert row["cash_balance"] == STARTING_CASH

    def test_update_cash_balance_writes_the_new_value(self, conn: sqlite3.Connection) -> None:
        """The written balance is what the next read returns."""
        update_cash_balance(conn, 8234.50)
        assert get_profile(conn)["cash_balance"] == 8234.50

    def test_update_cash_balance_rounds_to_cents(self, conn: sqlite3.Connection) -> None:
        """A sub-cent balance is stored at 2dp, so the caller need not pre-round."""
        update_cash_balance(conn, 8234.567)
        assert get_profile(conn)["cash_balance"] == round_money(8234.567)


class TestPositions:
    """Upsert, read and delete, with no zero-quantity rows left behind."""

    def test_get_positions_is_empty_on_a_fresh_database(self, conn: sqlite3.Connection) -> None:
        """Seeding creates a watchlist but no holdings."""
        assert get_positions(conn) == []

    def test_get_positions_returns_one_row_after_one_upsert(
        self, conn: sqlite3.Connection
    ) -> None:
        """A single position shows up as a single row."""
        upsert_position(conn, "AAPL", 10.0, 188.60)
        rows = get_positions(conn)
        assert len(rows) == 1
        assert rows[0]["ticker"] == "AAPL"

    def test_get_positions_is_ordered_by_ticker(self, conn: sqlite3.Connection) -> None:
        """The order is specified, not left to SQLite's row order."""
        for ticker in ("TSLA", "AAPL", "MSFT"):
            upsert_position(conn, ticker, 1.0, 100.0)
        assert [row["ticker"] for row in get_positions(conn)] == ["AAPL", "MSFT", "TSLA"]

    def test_get_position_on_an_unheld_ticker_returns_none(
        self, conn: sqlite3.Connection
    ) -> None:
        """A ticker with no holding answers None rather than raising."""
        assert get_position(conn, "AAPL") is None

    def test_upsert_twice_leaves_one_row_with_the_second_values(
        self, conn: sqlite3.Connection
    ) -> None:
        """The UNIQUE constraint turns the second call into an update."""
        upsert_position(conn, "AAPL", 10.0, 188.60)
        upsert_position(conn, "AAPL", 15.0, 190.00)

        rows = get_positions(conn)
        assert len(rows) == 1
        assert rows[0]["quantity"] == 15.0
        assert rows[0]["avg_cost"] == 190.00

    def test_upsert_rounds_quantity_and_avg_cost(self, conn: sqlite3.Connection) -> None:
        """Values carrying a fifth decimal place are stored at 4dp."""
        upsert_position(conn, "AAPL", 1.234567, 188.987654)
        row = get_position(conn, "AAPL")
        assert row["quantity"] == round_quantity(1.234567)
        assert row["avg_cost"] == round_quantity(188.987654)

    def test_delete_position_removes_the_row(self, conn: sqlite3.Connection) -> None:
        """A sold-out position leaves nothing behind, not a zero-quantity row."""
        upsert_position(conn, "AAPL", 10.0, 188.60)
        delete_position(conn, "AAPL")
        assert get_position(conn, "AAPL") is None
        assert get_positions(conn) == []

    def test_lowercase_ticker_is_stored_uppercased(self, conn: sqlite3.Connection) -> None:
        """Normalization happens once, in the shared rule, before the statement."""
        upsert_position(conn, "aapl", 10.0, 188.60)
        assert get_positions(conn)[0]["ticker"] == "AAPL"
        assert get_position(conn, "aapl") is not None

    def test_invalid_ticker_raises(self, conn: sqlite3.Connection) -> None:
        """A malformed symbol is rejected before it reaches SQL."""
        with pytest.raises(ValueError, match="Invalid ticker symbol"):
            upsert_position(conn, "NOT-A-TICKER", 10.0, 188.60)


class TestTrades:
    """The append-only audit log."""

    def test_insert_trade_appends_a_row(self, conn: sqlite3.Connection) -> None:
        """One insert, one row, with the side and ticker as given."""
        insert_trade(conn, "AAPL", "buy", 10.0, 190.52)
        row = conn.execute("SELECT * FROM trades").fetchone()
        assert row["ticker"] == "AAPL"
        assert row["side"] == "buy"
        assert row["quantity"] == 10.0
        assert row["price"] == 190.52

    def test_insert_trade_rounds_at_the_write_boundary(self, conn: sqlite3.Connection) -> None:
        """A 5dp quantity and a 3dp price are stored rounded.

        test_money.py proves round_quantity and round_money behave; this proves
        insert_trade actually routes through them, which is the part a later
        refactor could quietly drop.
        """
        insert_trade(conn, "AAPL", "buy", 1.234567, 190.5249)
        row = conn.execute("SELECT quantity, price FROM trades").fetchone()
        assert row["quantity"] == round_quantity(1.234567)
        assert row["price"] == round_money(190.5249)

    def test_insert_trade_returns_the_stored_timestamp(self, conn: sqlite3.Connection) -> None:
        """The returned executed_at is the one written, not a second one."""
        executed_at = insert_trade(conn, "AAPL", "buy", 10.0, 190.52)
        assert conn.execute("SELECT executed_at FROM trades").fetchone()[0] == executed_at

    def test_trades_accumulate(self, conn: sqlite3.Connection) -> None:
        """Nothing overwrites an earlier trade: the log only ever grows."""
        insert_trade(conn, "AAPL", "buy", 10.0, 190.52)
        insert_trade(conn, "AAPL", "sell", 4.0, 191.00)
        assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 2


class TestSnapshots:
    """Portfolio value over time, newest first."""

    def test_seed_leaves_one_snapshot(self, conn: sqlite3.Connection) -> None:
        """The P&L chart has a data point before the first trade."""
        assert get_latest_snapshot(conn)["total_value"] == STARTING_CASH

    def test_get_latest_snapshot_returns_the_newest(self, conn: sqlite3.Connection) -> None:
        """The most recently written row wins, seed row included."""
        insert_snapshot(conn, 10120.75)
        assert get_latest_snapshot(conn)["total_value"] == 10120.75

    def test_get_snapshots_is_newest_first(self, conn: sqlite3.Connection) -> None:
        """The list reads newest to oldest, whatever the clock resolution."""
        for value in (10100.0, 10200.0, 10300.0):
            insert_snapshot(conn, value)
        values = [row["total_value"] for row in get_snapshots(conn)]
        assert values[:3] == [10300.0, 10200.0, 10100.0]

    def test_get_snapshots_honours_limit(self, conn: sqlite3.Connection) -> None:
        """The limit caps the result at the newest rows."""
        for value in (10100.0, 10200.0, 10300.0):
            insert_snapshot(conn, value)
        rows = get_snapshots(conn, limit=2)
        assert [row["total_value"] for row in rows] == [10300.0, 10200.0]

    def test_since_equal_to_a_row_includes_that_row(self, conn: sqlite3.Connection) -> None:
        """The filter is inclusive at the boundary."""
        insert_snapshot(conn, 10100.0)
        target = get_latest_snapshot(conn)
        ids = [row["id"] for row in get_snapshots(conn, since=target["recorded_at"])]
        assert target["id"] in ids

    def test_since_one_microsecond_later_excludes_that_row(
        self, conn: sqlite3.Connection
    ) -> None:
        """One microsecond past the row's timestamp drops it."""
        insert_snapshot(conn, 10100.0)
        target = get_latest_snapshot(conn)
        just_after = dt.datetime.fromisoformat(target["recorded_at"]) + dt.timedelta(
            microseconds=1
        )
        ids = [row["id"] for row in get_snapshots(conn, since=just_after.isoformat())]
        assert target["id"] not in ids

    def test_no_since_returns_everything(self, conn: sqlite3.Connection) -> None:
        """Without a filter the seed row is still there."""
        insert_snapshot(conn, 10100.0)
        assert len(get_snapshots(conn)) == 2
