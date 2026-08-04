"""Fixtures for the service tests: a tmp database and a fake market source."""

import pytest

from app import state
from app.db import init_db
from app.market import PriceCache
from tests.services.fakes import FakeSource

SEED_PRICES = {
    "AAPL": 190.0,
    "GOOGL": 175.0,
    "MSFT": 420.0,
    "AMZN": 185.0,
    "TSLA": 250.0,
    "NVDA": 120.0,
    "META": 500.0,
    "JPM": 200.0,
    "V": 280.0,
    "NFLX": 650.0,
}


@pytest.fixture
def db(tmp_path, monkeypatch):
    """An initialized, seeded database in tmp_path."""
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "finally.db"))
    init_db()


@pytest.fixture
def cache():
    return PriceCache()


@pytest.fixture
async def market(db, cache):
    """Install a fake source priced at the seed defaults and return it."""
    source = FakeSource(cache, dict(SEED_PRICES))
    await source.start(list(SEED_PRICES))
    state.set_market(cache, source)
    yield source
    state.clear_market()
