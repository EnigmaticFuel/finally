"""Tests for the watchlist routes: the 200/204/400/404/409 surface.

The app fixture has not run lifespan, so the market source is unstarted and its
add_ticker returns immediately. Prices are therefore given to routes by writing
into app.state.price_cache directly.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.connection import connect, ensure_initialized, writing
from app.db.queries import upsert_position
from app.db.seed import DEFAULT_TICKERS

HELD = "AAPL"
UNWATCHED = "PYPL"
NEVER_WATCHED = "ZZZZ"
PRICE = 190.50


def _hold_position(db_path: Path, ticker: str) -> None:
    """Give the user a position, the way a filled trade would."""
    ensure_initialized(db_path)
    with connect(db_path) as conn:
        with writing(conn):
            upsert_position(conn, ticker, 10.0, PRICE)


def _tickers(client: TestClient) -> list[str]:
    """The symbols currently listed by GET /api/watchlist."""
    return [row["ticker"] for row in client.get("/api/watchlist").json()["tickers"]]


class TestReadWatchlist:
    """GET /api/watchlist."""

    def test_a_fresh_database_lists_the_ten_seeded_tickers(self, app: FastAPI) -> None:
        """The seeded watchlist is what the first request sees."""
        response = TestClient(app).get("/api/watchlist")
        assert response.status_code == 200
        assert response.json()["tickers"] != []
        assert len(response.json()["tickers"]) == len(DEFAULT_TICKERS)

    def test_a_cached_ticker_has_a_price_and_the_rest_are_null(self, app: FastAPI) -> None:
        """A ticker with no price is present with nulls, never omitted or zeroed."""
        app.state.price_cache.update(HELD, PRICE)
        rows = {row["ticker"]: row for row in TestClient(app).get("/api/watchlist").json()["tickers"]}

        assert rows[HELD]["price"] == PRICE
        assert rows[HELD]["change_from_open_percent"] == 0.0
        assert rows["GOOGL"]["price"] is None
        assert rows["GOOGL"]["open_price"] is None
        assert rows["GOOGL"]["change_from_open_percent"] is None
        assert rows["GOOGL"]["history"] == []


class TestAddTicker:
    """POST /api/watchlist."""

    def test_a_lowercase_symbol_answers_with_the_uppercase_form(self, app: FastAPI) -> None:
        """The service normalizes, so the response names the stored symbol."""
        response = TestClient(app).post("/api/watchlist", json={"ticker": UNWATCHED.lower()})
        assert response.status_code == 200
        assert response.json()["ticker"] == UNWATCHED

    def test_an_added_ticker_appears_in_the_next_read(self, app: FastAPI) -> None:
        """The write is durable, not just reflected in the response."""
        client = TestClient(app)
        client.post("/api/watchlist", json={"ticker": UNWATCHED.lower()})
        assert UNWATCHED in _tickers(client)

    def test_an_invalid_symbol_is_a_400_not_a_422(self, app: FastAPI) -> None:
        """The shared ticker rule raises, so the answer comes from the handlers."""
        response = TestClient(app).post("/api/watchlist", json={"ticker": "toolong"})
        assert response.status_code == 400
        assert "Invalid ticker symbol" in response.json()["detail"]


class TestRemoveTicker:
    """DELETE /api/watchlist/{ticker}."""

    def test_removing_a_watched_ticker_returns_204_with_an_empty_body(
        self, app: FastAPI
    ) -> None:
        """204 carries no body, so the route must not serialize its None."""
        response = TestClient(app).delete(f"/api/watchlist/{HELD}")
        assert response.status_code == 204
        assert response.content == b""

    def test_a_removed_ticker_is_gone_from_the_next_read(self, app: FastAPI) -> None:
        """The delete is durable."""
        client = TestClient(app)
        client.delete(f"/api/watchlist/{HELD}")
        assert HELD not in _tickers(client)

    def test_a_lowercase_path_removes_the_uppercase_row(self, app: FastAPI) -> None:
        """Equality is byte equality after strip and uppercase."""
        client = TestClient(app)
        assert client.delete(f"/api/watchlist/{HELD.lower()}").status_code == 204
        assert HELD not in _tickers(client)

    def test_a_second_removal_returns_404(self, app: FastAPI) -> None:
        """Removal is not status-idempotent."""
        client = TestClient(app)
        assert client.delete(f"/api/watchlist/{HELD}").status_code == 204
        assert client.delete(f"/api/watchlist/{HELD}").status_code == 404

    def test_an_unwatched_ticker_returns_404(self, app: FastAPI) -> None:
        """WATCH-06: a well-formed symbol naming no row is a 404."""
        response = TestClient(app).delete(f"/api/watchlist/{NEVER_WATCHED}")
        assert response.status_code == 404
        assert NEVER_WATCHED in response.json()["detail"]

    def test_a_held_ticker_returns_409_and_stays_watched(
        self, app: FastAPI, db_path: Path
    ) -> None:
        """WATCH-05: the 409 names the ticker and the row survives."""
        _hold_position(db_path, HELD)
        client = TestClient(app)

        response = client.delete(f"/api/watchlist/{HELD}")
        assert response.status_code == 409
        assert HELD in response.json()["detail"]
        assert HELD in _tickers(client)


class TestMountOrder:
    """The new router must not disturb the static mount."""

    def test_health_still_answers(self, app: FastAPI) -> None:
        """A shadowed API would 404 here while the page still loaded."""
        assert TestClient(app).get("/api/health").status_code == 200
