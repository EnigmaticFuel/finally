"""SQLite connection handling.

This is the only module in the codebase that opens the database file.
The path comes from FINALLY_DB_PATH, defaulting to <repo root>/db/finally.db,
which is the directory Docker bind-mounts.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DB_PATH_ENV = "FINALLY_DB_PATH"

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "db" / "finally.db"


def get_db_path() -> Path:
    """Resolve the database file path, honouring FINALLY_DB_PATH.

    Read on every call rather than cached at import so tests can point the
    whole package at a tmp_path database.
    """
    override = os.getenv(DB_PATH_ENV)
    return Path(override) if override else DEFAULT_DB_PATH


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a connection with row-by-name access, committing on clean exit.

    An exception propagates with the transaction uncommitted, so a failed
    multi-statement write leaves nothing behind.
    """
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
