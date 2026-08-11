# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""SQLite WAL over the Docker bind mount, stressed deliberately and in place.

Run with:  uv run --script scripts/wal_stress.py [--db PATH]
Inside the container:  python /stress/wal_stress.py

Phase 1's concurrency suite proved the lost-update standard against a database
on the host filesystem. The bind mount is the layer it never touched, and
SQLite's own documentation warns that WAL depends on shared memory and does not
work over a network filesystem - which is the shape a Docker Desktop bind mount
of a Windows path presents as. Driving contention here means a locked database
is diagnosed as an infrastructure fact now, rather than being discovered under
Phase 3's trade logic where it would look like a trade bug.

The scratch database is deliberate. Writing to db/finally.db would produce a
binary diff on a tracked file that holds the user's portfolio baseline; a
scratch database on the same mount and the same filesystem measures the same
thing at no cost. Plain sqlite3 is used rather than app.db.connection for the
same kind of reason: the point is to observe the mount's pragma behaviour
directly, and connection.py is the code whose blind spot this script covers.
"""

from __future__ import annotations

import argparse
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = "/app/db/wal_stress.db"
WRITER_THREADS = 6
WRITES_PER_THREAD = 40
INCREMENT = 1
STARTING_VALUE = 0
BUSY_TIMEOUT_MS = 5000


def _connect(path: Path) -> sqlite3.Connection:
    """Open a connection in the same mode the application uses.

    isolation_level=None so an explicit BEGIN IMMEDIATE is legal, and the same
    5000 ms busy timeout, so a timeout here means what it would mean in
    production rather than something this script invented.
    """
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return conn


def _remove_scratch_database(path: Path) -> None:
    """Delete the scratch database and its WAL sidecars so the run starts fresh."""
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def assert_journal_mode_is_wal(path: Path) -> str:
    """Set WAL and read back the mode the database actually ended up in.

    This runs before any contention is driven, because it is the assertion that
    separates "WAL is on" from "we asked for WAL". PRAGMA journal_mode=WAL
    returns the resulting mode, and returns the original mode when the change
    could not be applied - so a silent downgrade to delete raises nothing and
    logs nothing. backend/app/db/connection.py executes this pragma and
    discards the returned row, which makes a downgrade invisible to the
    application today.
    """
    conn = _connect(path)
    try:
        mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    finally:
        conn.close()
    if mode != "wal":
        raise RuntimeError(f"journal mode read back as {mode!r}, not 'wal'")
    return mode


def create_counter_table(path: Path) -> None:
    """Create the single-row counter table every writer increments.

    The table name, the column name and the row id are contract rather than
    implementation detail: a second container re-reads
    `select value from counter where id = 1` to prove the write crossed the
    bind mount and survived a destroy-and-recreate.
    """
    conn = _connect(path)
    try:
        conn.execute("CREATE TABLE counter (id INTEGER PRIMARY KEY, value INTEGER)")
        conn.execute("INSERT INTO counter (id, value) VALUES (1, ?)", (STARTING_VALUE,))
    finally:
        conn.close()


def _run(targets: list[threading.Thread]) -> None:
    """Start every thread and wait for all of them."""
    for thread in targets:
        thread.start()
    for thread in targets:
        thread.join()


def run_writers(
    path: Path,
    threads: int = WRITER_THREADS,
    writes: int = WRITES_PER_THREAD,
) -> tuple[list[int], list[BaseException]]:
    """Drive N-way contention: read-modify-write inside BEGIN IMMEDIATE.

    Calibrated to the research probe's six writers times forty increments, so a
    regression against the recorded 240/240 measurement is legible rather than
    merely different.
    """
    commits: list[int] = []
    errors: list[BaseException] = []

    def writer() -> None:
        for _ in range(writes):
            conn = _connect(path)
            try:
                conn.execute("BEGIN IMMEDIATE")
                value = conn.execute("SELECT value FROM counter WHERE id = 1").fetchone()[0]
                conn.execute("UPDATE counter SET value = ? WHERE id = 1", (value + INCREMENT,))
                conn.execute("COMMIT")
                commits.append(1)
            except BaseException as exc:
                errors.append(exc)
            finally:
                conn.close()

    _run([threading.Thread(target=writer) for _ in range(threads)])
    return commits, errors


def assert_no_lost_updates(
    path: Path,
    commits: list[int],
    errors: list[BaseException],
    expected_commits: int,
) -> tuple[int, int, str]:
    """Assert the final stored value, then the file's integrity.

    Quoting the analog, backend/tests/db/test_concurrency.py: the load-bearing
    assertion is not "no errors". A design that silently loses updates raises
    nothing; what catches it is the final stored value equalling the starting
    value plus the increment times the committed write count.
    """
    if errors:
        raise RuntimeError(f"{len(errors)} writer failures, first: {errors[0]}")
    if len(commits) != expected_commits:
        raise RuntimeError(f"committed {len(commits)} writes, expected {expected_commits}")

    expected = STARTING_VALUE + INCREMENT * len(commits)
    conn = _connect(path)
    try:
        actual = conn.execute("SELECT value FROM counter WHERE id = 1").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()

    if actual != expected:
        raise RuntimeError(f"lost updates: stored {actual}, expected {expected}")
    if integrity != "ok":
        raise RuntimeError(f"integrity_check returned {integrity!r}")
    return expected, actual, integrity


def classify_failure(message: str) -> str:
    """Name the documented failure signature a message matches.

    Three of the four signatures are mount-layer facts and the fourth is
    application-layer contention that has nothing to do with the mount. Naming
    which one fired is what separates diagnosis from guessing, and it is the
    only thing that should happen before any remedy is considered.
    """
    lowered = message.lower()
    if "journal mode" in lowered:
        return "mount layer, the filesystem refused WAL and shared memory is unavailable"
    if "disk i/o error" in lowered or "shm" in lowered:
        return "mount layer, the -shm mmap failed"
    if "unable to open database file" in lowered:
        return "mount layer, the directory is not writable or the path does not reach the mount"
    if "database is locked" in lowered:
        return "application layer, lock contention outlived the busy timeout, not a mount problem"
    return "unclassified, none of the four documented signatures matched"


def main() -> int:
    """Run the three phases in order and print one pinned result line.

    The result line is space-separated key=value pairs because the wave gate
    greps it: the database path is printed too, so a gate looking for a bare
    mode token would match the path and pass without the pragma ever having
    returned the right mode.
    """
    parser = argparse.ArgumentParser(description="Stress SQLite WAL over the db/ bind mount.")
    parser.add_argument("--db", default=DB_PATH, help=f"scratch database path (default {DB_PATH})")
    parser.add_argument("--threads", type=int, default=WRITER_THREADS, help="writer threads")
    parser.add_argument("--writes", type=int, default=WRITES_PER_THREAD, help="writes per thread")
    args = parser.parse_args()

    path = Path(args.db)
    print(f"database={path}")
    _remove_scratch_database(path)

    started = time.perf_counter()
    try:
        mode = assert_journal_mode_is_wal(path)
        create_counter_table(path)
        commits, errors = run_writers(path, args.threads, args.writes)
        expected, actual, integrity = assert_no_lost_updates(
            path, commits, errors, args.threads * args.writes
        )
    except Exception as exc:
        print(f"FAILED {exc}")
        print(f"signature={classify_failure(str(exc))}")
        return 1
    elapsed = time.perf_counter() - started

    print(
        f"journal_mode={mode} commits={len(commits)} expected={expected} "
        f"actual={actual} errors={len(errors)} integrity_check={integrity} "
        f"elapsed={elapsed:.2f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
