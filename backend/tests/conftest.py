"""Pytest configuration and fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI

from app.db.connection import get_db_path
from app.main import create_app


@pytest.fixture
def event_loop_policy():
    """Use the default event loop policy for all async tests."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session", autouse=True)
def _no_massive_api_key() -> Iterator[None]:
    """Keep the whole suite off the live Massive API.

    create_market_data_source() reads MASSIVE_API_KEY at call time, so a
    developer holding a real key would otherwise have every app fixture start
    polling the real service.
    """
    previous = os.environ.pop("MASSIVE_API_KEY", None)
    yield
    if previous is not None:
        os.environ["MASSIVE_API_KEY"] = previous


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A throwaway database path, one per test."""
    return tmp_path / "finally.db"


@pytest.fixture
def app(db_path: Path) -> FastAPI:
    """An app pointed at a throwaway database.

    The path arrives by overriding the one dependency every route reads it
    through, rather than by monkeypatching FINALLY_DB_PATH, which would depend
    on import-time ordering in config.py.

    Lifespan has not run yet, so the cache is empty and the market source is
    unstarted. Tests needing a live feed drive the lifespan themselves or serve
    the app from uvicorn.
    """
    application = create_app()
    application.dependency_overrides[get_db_path] = lambda: db_path
    return application
