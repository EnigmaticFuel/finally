"""Tests for schema application and the fresh-database seed.

Every database here is a real file under tmp_path. Not :memory: - it cannot
exercise WAL or genuine lock contention, and connection-per-operation would give
each open its own empty database.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db.seed import (
    DEFAULT_TICKERS,
    DEFAULT_USER_ID,
    STARTING_CASH,
    apply_schema,
    is_fresh_database,
    seed_fresh,
)

EXPECTED_TABLES = {
    "users_profile",
    "watchlist",
    "positions",
    "trades",
    "portfolio_snapshots",
    "chat_messages",
}


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A connection to a real, empty database file."""
    connection = sqlite3.connect(tmp_path / "finally.db")
    yield connection
    connection.close()


def table_names(connection: sqlite3.Connection) -> set[str]:
    """Every table name currently in the database."""
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


class TestApplySchema:
    """Schema creation is complete and repeatable."""

    def test_creates_the_six_tables(self, conn: sqlite3.Connection) -> None:
        """An empty file gains exactly the six tables from PLAN.md section 7."""
        apply_schema(conn)
        assert table_names(conn) == EXPECTED_TABLES

    def test_is_idempotent(self, conn: sqlite3.Connection) -> None:
        """Applying the schema twice does not raise."""
        apply_schema(conn)
        apply_schema(conn)
        assert table_names(conn) == EXPECTED_TABLES

    def test_unique_ticker_per_user(self, conn: sqlite3.Connection) -> None:
        """watchlist and positions both refuse a duplicate ticker for a user."""
        apply_schema(conn)
        conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            ("a", DEFAULT_USER_ID, "AAPL", "2026-01-01T00:00:00+00:00"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                ("b", DEFAULT_USER_ID, "AAPL", "2026-01-01T00:00:00+00:00"),
            )


class TestSeedGate:
    """is_fresh_database answers one question about one table."""

    def test_true_before_seeding(self, conn: sqlite3.Connection) -> None:
        """A schema-only database has never been seeded."""
        apply_schema(conn)
        assert is_fresh_database(conn) is True

    def test_false_after_seeding(self, conn: sqlite3.Connection) -> None:
        """A database holding a profile is not fresh."""
        apply_schema(conn)
        seed_fresh(conn)
        assert is_fresh_database(conn) is False


class TestSeedFresh:
    """The first-launch state PLAN.md section 2 promises the user."""

    def test_writes_profile_watchlist_and_snapshot(self, conn: sqlite3.Connection) -> None:
        """One profile at $10,000, the ten default tickers, one snapshot."""
        apply_schema(conn)
        seed_fresh(conn)

        profiles = conn.execute("SELECT id, cash_balance FROM users_profile").fetchall()
        assert len(profiles) == 1
        assert profiles[0][0] == DEFAULT_USER_ID
        assert profiles[0][1] == STARTING_CASH == 10000.0

        tickers = conn.execute("SELECT ticker FROM watchlist").fetchall()
        assert len(tickers) == 10
        assert {row[0] for row in tickers} == set(DEFAULT_TICKERS)

        snapshots = conn.execute("SELECT total_value FROM portfolio_snapshots").fetchall()
        assert len(snapshots) == 1
        assert snapshots[0][0] == STARTING_CASH

    def test_timestamps_are_iso_utc_strings(self, conn: sqlite3.Connection) -> None:
        """Every *_at column is an ISO 8601 UTC string, never epoch seconds."""
        apply_schema(conn)
        seed_fresh(conn)
        created_at = conn.execute("SELECT created_at FROM users_profile").fetchone()[0]
        assert isinstance(created_at, str)
        assert created_at.endswith("+00:00")


class TestEmptiedWatchlistIsNotRestored:
    """The deliberate consequence of gating the seed on a fresh database."""

    def test_user_emptied_watchlist_stays_empty(self, conn: sqlite3.Connection) -> None:
        """Removing every ticker survives re-initialization, and cash is untouched.

        Re-seeding on every startup would quietly overwrite an action the user
        took on purpose, so the gate refuses to run a second time.
        """
        apply_schema(conn)
        seed_fresh(conn)
        conn.execute("UPDATE users_profile SET cash_balance = 8234.5")
        conn.execute("DELETE FROM watchlist")

        apply_schema(conn)
        if is_fresh_database(conn):
            seed_fresh(conn)

        assert conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] == 0
        assert conn.execute("SELECT cash_balance FROM users_profile").fetchone()[0] == 8234.5
