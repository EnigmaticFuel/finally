"""Tests for the health endpoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

HEALTH_KEYS = {"status", "market_source", "tickers_cached", "newest_price_age_seconds"}


class TestHealthEndpoint:
    """Unit tests for GET /api/health."""

    def test_payload_is_exactly_four_keys(self, app: FastAPI) -> None:
        """The health payload is a fixed four-key surface."""
        response = TestClient(app).get("/api/health")
        assert response.status_code == 200
        assert set(response.json()) == HEALTH_KEYS

    def test_status_is_ok(self, app: FastAPI) -> None:
        """status is the fixed string ok."""
        payload = TestClient(app).get("/api/health").json()
        assert payload["status"] == "ok"

    def test_market_source_is_simulator_without_a_key(self, app: FastAPI) -> None:
        """With MASSIVE_API_KEY cleared the factory selects the simulator."""
        payload = TestClient(app).get("/api/health").json()
        assert payload["market_source"] == "simulator"

    def test_tickers_cached_is_an_int(self, app: FastAPI) -> None:
        """tickers_cached counts cache entries, so it is an int."""
        payload = TestClient(app).get("/api/health").json()
        assert isinstance(payload["tickers_cached"], int)

    def test_price_age_is_none_before_any_price(self, app: FastAPI) -> None:
        """An empty cache reports None rather than a fabricated zero."""
        payload = TestClient(app).get("/api/health").json()
        assert payload["newest_price_age_seconds"] is None

    def test_price_age_is_a_non_negative_float_once_a_price_exists(self, app: FastAPI) -> None:
        """A cached price turns the age into a real measurement."""
        app.state.price_cache.update("AAPL", 190.50)
        payload = TestClient(app).get("/api/health").json()
        age = payload["newest_price_age_seconds"]
        assert isinstance(age, float)
        assert age >= 0

    def test_payload_never_names_an_api_key(self, app: FastAPI) -> None:
        """The endpoint is unauthenticated, so no key-shaped field belongs in it."""
        payload = TestClient(app).get("/api/health").json()
        assert not any("key" in name.lower() for name in payload)
