"""Fixtures for the database tests. Every test gets its own tmp_path database."""

import pytest

from app.db import init_db


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Point the db package at an empty tmp_path file, uninitialized."""
    path = tmp_path / "finally.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(path))
    return path


@pytest.fixture
def db(db_path):
    """An initialized, seeded database."""
    init_db()
    return db_path
