"""Path resolution and connection configuration."""

import sqlite3

from app.db.connection import DEFAULT_DB_PATH, get_connection, get_db_path


def test_default_path_is_repo_root_db_file(monkeypatch):
    monkeypatch.delenv("FINALLY_DB_PATH", raising=False)
    path = get_db_path()
    assert path == DEFAULT_DB_PATH
    assert path.name == "finally.db"
    assert path.parent.name == "db"


def test_default_path_sits_beside_the_backend_directory(monkeypatch):
    monkeypatch.delenv("FINALLY_DB_PATH", raising=False)
    assert (get_db_path().parent.parent / "backend").is_dir()


def test_env_override_wins(tmp_path, monkeypatch):
    target = tmp_path / "custom.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(target))
    assert get_db_path() == target


def test_env_is_read_per_call(tmp_path, monkeypatch):
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "one.db"))
    first = get_db_path()
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "two.db"))
    assert get_db_path() != first


def test_missing_parent_directory_is_created(tmp_path, monkeypatch):
    target = tmp_path / "nested" / "deeper" / "finally.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(target))
    with get_connection():
        pass
    assert target.parent.is_dir()


def test_rows_are_accessible_by_name(db):
    with get_connection() as conn:
        row = conn.execute("SELECT cash_balance FROM users_profile").fetchone()
    assert isinstance(row, sqlite3.Row)
    assert row["cash_balance"] == 10000.0


def test_journal_mode_is_wal(db):
    with get_connection() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


def test_clean_exit_commits(db):
    with get_connection() as conn:
        conn.execute("UPDATE users_profile SET cash_balance = 42.0")

    with get_connection() as conn:
        assert conn.execute("SELECT cash_balance FROM users_profile").fetchone()[0] == 42.0


def test_exception_leaves_the_write_uncommitted(db):
    try:
        with get_connection() as conn:
            conn.execute("UPDATE users_profile SET cash_balance = 42.0")
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    with get_connection() as conn:
        assert conn.execute("SELECT cash_balance FROM users_profile").fetchone()[0] == 10000.0
