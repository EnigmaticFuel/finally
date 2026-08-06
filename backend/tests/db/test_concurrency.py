"""Concurrent writes against one file database: no lock errors, no lost updates.

This is the direct proof of Phase 1 success criterion 3. Every database here is
a real file under tmp_path. An in-memory database cannot exercise WAL,
busy_timeout or genuine lock contention, and under connection-per-operation each
in-memory connection would get its own empty database, so these tests would pass
while proving nothing at all.

The load-bearing assertion is not "no errors". A design that silently loses
updates raises nothing; what catches it is the final stored value equalling the
starting value plus the increment times the committed write count.
"""

import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db.connection import connect, writing
from app.db.queries import get_profile, insert_snapshot, insert_trade, update_cash_balance
from app.db.seed import STARTING_CASH, apply_schema, seed_fresh

WRITER_THREADS = 6
WRITES_PER_THREAD = 20
READER_THREADS = 3
READS_PER_THREAD = 20
INCREMENT = 1.0
HOLD_SECONDS = 0.3


@pytest.fixture
def db_file(tmp_path: Path) -> Iterator[Path]:
    """A seeded file database that the threads share."""
    path = tmp_path / "finally.db"
    with connect(path) as conn:
        apply_schema(conn)
        seed_fresh(conn)
    yield path


def _run(targets: list[threading.Thread]) -> None:
    """Start every thread and wait for all of them."""
    for thread in targets:
        thread.start()
    for thread in targets:
        thread.join()


class TestLostUpdates:
    """Read-modify-write from several threads must serialize, not interleave."""

    def test_concurrent_increments_lose_nothing(self, db_file: Path) -> None:
        """Every committed increment shows up in the final balance."""
        errors: list[BaseException] = []
        commits: list[int] = []

        def writer() -> None:
            for _ in range(WRITES_PER_THREAD):
                try:
                    with connect(db_file) as conn:
                        with writing(conn):
                            balance = get_profile(conn)["cash_balance"]
                            update_cash_balance(conn, balance + INCREMENT)
                    commits.append(1)
                except BaseException as exc:
                    errors.append(exc)

        def reader() -> None:
            for _ in range(READS_PER_THREAD):
                try:
                    with connect(db_file) as conn:
                        assert get_profile(conn) is not None
                except BaseException as exc:
                    errors.append(exc)

        _run(
            [threading.Thread(target=writer) for _ in range(WRITER_THREADS)]
            + [threading.Thread(target=reader) for _ in range(READER_THREADS)]
        )

        assert errors == []
        assert not [exc for exc in errors if isinstance(exc, sqlite3.OperationalError)]
        assert len(commits) == WRITER_THREADS * WRITES_PER_THREAD

        with connect(db_file) as conn:
            final = get_profile(conn)["cash_balance"]
        assert final == STARTING_CASH + INCREMENT * len(commits)


class TestMixedWrites:
    """The snapshot-versus-trade collision, at the query layer."""

    def test_snapshots_and_trades_written_concurrently(self, db_file: Path) -> None:
        """Both append paths complete in full with no lock errors.

        The realistic version - Phase 3's 30-second snapshot task colliding with
        a real execute_trade - belongs to Phase 3, once both callers exist.
        """
        errors: list[BaseException] = []

        def snapshotter() -> None:
            for value in range(WRITES_PER_THREAD):
                try:
                    with connect(db_file) as conn:
                        with writing(conn):
                            insert_snapshot(conn, 10000.0 + value)
                except BaseException as exc:
                    errors.append(exc)

        def trader() -> None:
            for _ in range(WRITES_PER_THREAD):
                try:
                    with connect(db_file) as conn:
                        with writing(conn):
                            insert_trade(conn, "AAPL", "buy", 1.0, 190.52)
                except BaseException as exc:
                    errors.append(exc)

        groups = WRITER_THREADS // 2
        _run(
            [threading.Thread(target=snapshotter) for _ in range(groups)]
            + [threading.Thread(target=trader) for _ in range(groups)]
        )

        assert errors == []
        with connect(db_file) as conn:
            snapshots = conn.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0]
            trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

        # One snapshot already exists from seeding.
        assert snapshots == groups * WRITES_PER_THREAD + 1
        assert trades == groups * WRITES_PER_THREAD


class TestBusyTimeout:
    """The mechanism, not the outcome: the second writer waits, it does not fail."""

    def test_second_writer_waits_for_the_lock(self, db_file: Path) -> None:
        """A write blocked by a held write lock succeeds once the lock releases.

        Failing immediately would also produce a passing row count under a retry
        loop somewhere; the elapsed time is what shows PRAGMA busy_timeout is
        doing the waiting.
        """
        lock_held = threading.Event()
        errors: list[BaseException] = []
        elapsed: list[float] = []

        def holder() -> None:
            with connect(db_file) as conn:
                with writing(conn):
                    insert_snapshot(conn, 10100.0)
                    lock_held.set()
                    time.sleep(HOLD_SECONDS)

        def blocked_writer() -> None:
            lock_held.wait(timeout=5.0)
            started = time.perf_counter()
            try:
                with connect(db_file) as conn:
                    with writing(conn):
                        insert_snapshot(conn, 10200.0)
            except BaseException as exc:
                errors.append(exc)
            elapsed.append(time.perf_counter() - started)

        _run([threading.Thread(target=holder), threading.Thread(target=blocked_writer)])

        assert errors == []
        assert elapsed[0] >= HOLD_SECONDS / 2
        with connect(db_file) as conn:
            assert conn.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0] == 3
