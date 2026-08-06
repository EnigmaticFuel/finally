"""Connection management: WAL, busy timeout, write transactions and lazy init.

Every path into the database goes through this module, and every one of them
crosses asyncio.to_thread exactly once, in run_db. Query functions stay plain
def taking a connection first, so pytest calls them directly with no event loop
and there is a single place to audit for event-loop compliance.

Initialization is triggered from here rather than from lifespan startup. That is
what makes it lazy, and what makes it impossible for a future call site to
forget: request handlers and Phase 3's snapshot background task both arrive
through the same door.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import Request

from .seed import apply_schema, is_fresh_database, seed_fresh

logger = logging.getLogger(__name__)

BUSY_TIMEOUT_MS = 5000

_initialized: set[Path] = set()
_init_lock = Lock()


# --- Connecting ---


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """Open a connection with WAL and a busy timeout, and close it on exit.

    isolation_level=None is mandatory, not stylistic. The stdlib default of ''
    is legacy implicit-transaction mode, in which an explicit BEGIN IMMEDIATE
    raises "cannot start a transaction within a transaction" once any statement
    has already opened one - and trivial single-statement tests still pass, so
    the defect hides.

    Both PRAGMAs are applied on every open even though journal_mode persists in
    the file, because busy_timeout is per-connection and would otherwise
    silently revert to zero. That is the single easiest line here to "optimize"
    away.

    One connection per operation, not a shared long-lived one behind a lock: a
    shared connection would serialize every read behind every write and discard
    the concurrency WAL exists to provide. It also sidesteps check_same_thread,
    since asyncio.to_thread hands work to arbitrary executor threads.
    """
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    try:
        yield conn
    finally:
        conn.close()


# --- Transactions ---


@contextmanager
def writing(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a write inside BEGIN IMMEDIATE, committing or rolling back.

    BEGIN IMMEDIATE takes the write lock up front, so two concurrent
    read-modify-write sequences cannot both read, both compute and both write.
    Failures roll back and re-raise; nothing is swallowed.

    Reads deliberately do not use this. Under WAL a reader already sees a
    consistent snapshot, so wrapping reads would serialize readers behind
    writers for nothing.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


# --- Initialization ---


def ensure_initialized(path: Path) -> None:
    """Create and seed the database if it has not been initialized yet.

    Idempotent and memoized on the resolved path behind a lock, so it runs once
    per path however many executor threads reach it. Seeding is gated inside the
    same transaction that checks for it, so a database that already holds a
    profile is left completely alone.
    """
    resolved = Path(path).resolve()
    if resolved in _initialized:
        return

    with _init_lock:
        if resolved in _initialized:
            return

        resolved.parent.mkdir(parents=True, exist_ok=True)
        with connect(resolved) as conn:
            apply_schema(conn)
            with writing(conn):
                if is_fresh_database(conn):
                    seed_fresh(conn)

        _initialized.add(resolved)
        logger.info("Database initialized at %s", resolved)


def get_db_path(request: Request) -> Path:
    """FastAPI dependency yielding the database path held on app.state.

    No module-level path or connection singleton - the same rule the price cache
    follows - because tests override exactly this one dependency.
    """
    return request.app.state.db_path


# --- Offload ---


async def run_db(path: Path, fn: Callable[..., Any], *args: Any) -> Any:
    """Run a query function against the database, off the event loop.

    This is the only place database work crosses into a thread. A 5-second busy
    wait therefore blocks an executor thread and never the SSE stream.
    """

    def _call() -> Any:
        ensure_initialized(path)
        with connect(path) as conn:
            return fn(conn, *args)

    # sqlite3 is synchronous - run in a thread to avoid blocking the event loop.
    return await asyncio.to_thread(_call)
