"""GET /api/health - one request that answers "is the stream alive?"."""

import time

import pytest

from app.market import PriceCache
from tests.services.fakes import FakeSource


def test_health_reports_the_running_source(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["market_source"] == "fake"
    assert body["tickers_cached"] == 10


def test_price_age_is_small_on_a_live_cache(client):
    age = client.get("/api/health").json()["newest_price_age_seconds"]

    assert 0 <= age < 5


def test_price_age_grows_when_the_feed_stalls(client):
    """A stalled poller is the failure this endpoint exists to expose."""
    from app import state

    cache = PriceCache()
    cache.update("AAPL", 190.0, timestamp=time.time() - 120)
    state.set_market(cache, FakeSource(cache))

    assert client.get("/api/health").json()["newest_price_age_seconds"] == pytest.approx(120, abs=5)


def test_price_age_is_null_on_an_empty_cache(client):
    from app import state

    cache = PriceCache()
    state.set_market(cache, FakeSource(cache))

    body = client.get("/api/health").json()

    assert body["tickers_cached"] == 0
    assert body["newest_price_age_seconds"] is None


def test_adding_a_ticker_raises_the_cached_count(client):
    client.post("/api/watchlist", json={"ticker": "PYPL"})

    assert client.get("/api/health").json()["tickers_cached"] == 11
