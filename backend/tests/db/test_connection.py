"""Tests for the connection, transaction, initialization and offload layer.

Every database is a real file under tmp_path: :memory: cannot exercise WAL,
busy_timeout or genuine lock contention, which is precisely what these tests
exist to prove.
"""

import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db import connection
from app.db.connection import (
    BUSY_TIMEOUT_MS,
    connect,
    ensure_initialized,
    run_db,
    writing,
)
from app.db.seed import DEFAULT_TICKERS, STARTING_CASH, apply_schema


@pytest.fixture
def db_file(tmp_path: Path) -> Iterator[Path]:
    """A throwaway database path, forgotten by the init memo afterwards."""
    path = tmp_path / "finally.db"
    yield path
    connection._initialized.discard(path.resolve())


class TestConnect:
    """Every open carries WAL and a busy timeout."""

    def test_pragmas_applied_on_first_open(self, db_file: Path) -> None:
        """A new connection reports WAL journalling and the busy timeout."""
        with connect(db_file) as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == BUSY_TIMEOUT_MS

    def test_busy_timeout_reapplied_on_every_open(self, db_file: Path) -> None:
        """A second, separately opened connection also carries the timeout.

        busy_timeout is per-connection, unlike journal_mode which persists in
        the file, so this is what proves the PRAGMA is not set once at init.
        """
        with connect(db_file):
            pass
        with connect(db_file) as conn:
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == BUSY_TIMEOUT_MS
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    def test_autocommit_mode(self, db_file: Path) -> None:
        """isolation_level is None, so the driver opens no implicit transaction."""
        with connect(db_file) as conn:
            assert conn.isolation_level is None

    def test_row_factory(self, db_file: Path) -> None:
        """Rows come back addressable by column name."""
        with connect(db_file) as conn:
            apply_schema(conn)
            row = conn.execute("SELECT 1 AS answer").fetchone()
            assert row["answer"] == 1


class TestWriting:
    """BEGIN IMMEDIATE, then commit or roll back."""

    def test_begin_immediate_does_not_raise(self, db_file: Path) -> None:
        """The explicit transaction is legal on an autocommit connection."""
        with connect(db_file) as conn:
            apply_schema(conn)
            with writing(conn):
                conn.execute("SELECT 1")

    def test_commits_on_normal_exit(self, db_file: Path) -> None:
        """A row written inside the transaction survives the connection."""
        with connect(db_file) as conn:
            apply_schema(conn)
            with writing(conn):
                conn.execute(
                    "INSERT INTO users_profile (id, cash_balance, created_at)"
                    " VALUES ('default', 10000.0, '2026-01-01T00:00:00+00:00')"
                )
        with connect(db_file) as conn:
            assert conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0] == 1

    def test_rolls_back_and_reraises(self, db_file: Path) -> None:
        """A failing body loses its writes and the exception propagates."""
        with connect(db_file) as conn:
            apply_schema(conn)
            with pytest.raises(ValueError, match="deliberate"):
                with writing(conn):
                    conn.execute(
                        "INSERT INTO users_profile (id, cash_balance, created_at)"
                        " VALUES ('default', 10000.0, '2026-01-01T00:00:00+00:00')"
                    )
                    raise ValueError("deliberate")

        with connect(db_file) as conn:
            assert conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0] == 0


class TestEnsureInitialized:
    """Lazy creation, seeded exactly once per path."""

    def test_creates_and_seeds_a_missing_file(self, db_file: Path) -> None:
        """A path with no file gets six tables and the standard seed."""
        assert not db_file.exists()
        ensure_initialized(db_file)

        with connect(db_file) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            assert len(tables) == 6
            assert conn.execute("SELECT cash_balance FROM users_profile").fetchone()[0] == (
                STARTING_CASH
            )
            assert conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] == len(
                DEFAULT_TICKERS
            )
            assert conn.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0] == 1

    def test_creates_a_missing_parent_directory(self, tmp_path: Path) -> None:
        """A path whose directory does not exist yet is still created."""
        nested = tmp_path / "db" / "finally.db"
        ensure_initialized(nested)
        assert nested.exists()
        connection._initialized.discard(nested.resolve())

    def test_running_twice_seeds_once(self, db_file: Path) -> None:
        """A second initialization changes nothing, memo cleared or not."""
        ensure_initialized(db_file)
        connection._initialized.discard(db_file.resolve())
        ensure_initialized(db_file)

        with connect(db_file) as conn:
            assert conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] == len(
                DEFAULT_TICKERS
            )
            assert conn.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0] == 1


def count_watchlist(conn: sqlite3.Connection) -> int:
    """A plain query function: connection first, no event loop needed."""
    return conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]


def current_thread_ident(conn: sqlite3.Connection) -> int:
    """Report which thread the query function actually ran on."""
    return threading.get_ident()


class TestRunDb:
    """The single event-loop offload seam."""

    async def test_returns_the_query_result(self, db_file: Path) -> None:
        """run_db initializes lazily and passes the connection through."""
        assert await run_db(db_file, count_watchlist) == len(DEFAULT_TICKERS)

    async def test_run_db_offloads(self, db_file: Path) -> None:
        """The query function runs on a different thread from the caller."""
        caller = threading.get_ident()
        worker = await run_db(db_file, current_thread_ident)
        assert worker != caller
