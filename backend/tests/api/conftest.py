"""Fixtures for the endpoint tests.

TestClient is used without its context manager on purpose: entering it would
run the real lifespan, which starts the real simulator. These tests install a
fake source instead, so fills and P&L are deterministic.
"""

import pytest
from fastapi.testclient import TestClient

from app import state
from app.db import init_db
from app.main import app
from app.market import PriceCache
from tests.services.conftest import SEED_PRICES
from tests.services.fakes import FakeSource


@pytest.fixture
async def market(tmp_path, monkeypatch):
    """A tmp database plus a fake market source, installed as the singletons."""
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "finally.db"))
    init_db()

    cache = PriceCache()
    source = FakeSource(cache, dict(SEED_PRICES))
    await source.start(list(SEED_PRICES))
    state.set_market(cache, source)
    yield source
    state.clear_market()


@pytest.fixture
def client(market):
    return TestClient(app)
