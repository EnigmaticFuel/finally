"""Tests for the portfolio routes."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.portfolio import HISTORY_MAX_LIMIT
from app.db.connection import connect
from app.db.queries import update_cash_balance, upsert_position
from app.db.seed import STARTING_CASH

TICKER = "AAPL"
SERVER_PRICE = 190.52
PORTFOLIO_KEYS = {"cash_balance", "total_value", "positions"}


class TestTradeEndpoint:
    """Unit tests for POST /api/portfolio/trade."""

    def test_fill_price_is_the_servers_price(self, app: FastAPI) -> None:
        """The response reports the cached price, whatever the client believed.

        The client's displayed price is advisory: it never reaches the server, so
        there is nothing for the body to echo back except the server's own.
        """
        app.state.price_cache.update(TICKER, SERVER_PRICE)

        response = TestClient(app).post(
            "/api/portfolio/trade",
            json={"ticker": TICKER, "side": "buy", "quantity": 2},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["fill_price"] == SERVER_PRICE
        assert payload["cash_balance"] == STARTING_CASH - SERVER_PRICE * 2

    def test_rejected_trade_is_a_readable_400(self, app: FastAPI) -> None:
        """A trade the seeded cash cannot cover reaches the client as 400 with detail.

        This is the phase's only proof that a TradeError crosses the HTTP boundary
        as PLAN.md section 8's envelope rather than a 500 carrying a Starlette
        traceback body. The message is asserted, not just the status: detail is
        what the client renders verbatim, so a status-only assertion would pass
        against an empty or repr-shaped body.
        """
        app.state.price_cache.update(TICKER, SERVER_PRICE)
        unaffordable = round(STARTING_CASH / SERVER_PRICE, 4) + 1

        response = TestClient(app).post(
            "/api/portfolio/trade",
            json={"ticker": TICKER, "side": "buy", "quantity": unaffordable},
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert re.fullmatch(
            r"Insufficient cash: need \$\d+\.\d{2}, have \$\d+\.\d{2}", detail
        ), detail
        assert f"have ${STARTING_CASH:.2f}" in detail


class TestReadPortfolio:
    """Unit tests for GET /api/portfolio."""

    def test_a_fresh_database_is_cash_and_nothing_else(self, app: FastAPI) -> None:
        """Three keys, the starting cash, no positions, a total equal to the cash."""
        response = TestClient(app).get("/api/portfolio")

        assert response.status_code == 200
        payload = response.json()
        assert set(payload) == PORTFOLIO_KEYS
        assert payload["cash_balance"] == STARTING_CASH
        assert payload["positions"] == []
        assert payload["total_value"] == STARTING_CASH

    def test_a_priced_position_reports_a_market_value(
        self, app: FastAPI, db_path: Path
    ) -> None:
        """A held ticker with a cached price is valued rather than nulled.

        The first request is what creates and seeds the database, so the position
        is written after it rather than before.
        """
        client = TestClient(app)
        client.get("/api/portfolio")
        with connect(db_path) as connection:
            upsert_position(connection, TICKER, 2.0, 100.0)
        app.state.price_cache.update(TICKER, SERVER_PRICE)

        payload = client.get("/api/portfolio").json()

        position = payload["positions"][0]
        assert position["ticker"] == TICKER
        assert position["market_value"] == SERVER_PRICE * 2
        assert payload["total_value"] == STARTING_CASH + SERVER_PRICE * 2


class TestPortfolioHistory:
    """Unit tests for GET /api/portfolio/history."""

    @staticmethod
    def _with_history(client: TestClient) -> list[dict[str, object]]:
        """Build history from this plan's own endpoint, then read it back.

        Reset is used rather than a trade so these tests stay independent of the
        trade path. A fresh database carries only the one seed snapshot.
        """
        client.post("/api/portfolio/reset")
        client.post("/api/portfolio/reset")
        return client.get("/api/portfolio/history").json()["snapshots"]

    def test_snapshots_come_back_newest_first(self, app: FastAPI) -> None:
        """Three snapshots, ordered newest to oldest, each carrying both fields."""
        snapshots = self._with_history(TestClient(app))

        assert len(snapshots) == 3
        assert set(snapshots[0]) == {"total_value", "recorded_at"}
        recorded = [snapshot["recorded_at"] for snapshot in snapshots]
        assert recorded == sorted(recorded, reverse=True)

    def test_limit_keeps_the_newest(self, app: FastAPI) -> None:
        """A limit of one returns exactly one snapshot, the newest."""
        client = TestClient(app)
        snapshots = self._with_history(client)

        limited = client.get("/api/portfolio/history?limit=1").json()["snapshots"]

        assert len(limited) == 1
        assert limited[0]["recorded_at"] == snapshots[0]["recorded_at"]

    def test_limit_zero_is_rejected(self, app: FastAPI) -> None:
        """Zero is a bad request, not an empty history."""
        assert TestClient(app).get("/api/portfolio/history?limit=0").status_code == 422

    def test_limit_above_the_cap_is_rejected(self, app: FastAPI) -> None:
        """The cap bounds the row count before any query runs."""
        response = TestClient(app).get(
            f"/api/portfolio/history?limit={HISTORY_MAX_LIMIT + 1}"
        )
        assert response.status_code == 422

    def test_limit_at_the_cap_is_accepted(self, app: FastAPI) -> None:
        """The cap itself is a legal value."""
        response = TestClient(app).get(f"/api/portfolio/history?limit={HISTORY_MAX_LIMIT}")
        assert response.status_code == 200

    def test_a_recorded_at_echoed_back_as_since_selects_that_row_and_newer(
        self, app: FastAPI
    ) -> None:
        """The timestamp a client received round-trips as a filter unchanged."""
        client = TestClient(app)
        snapshots = self._with_history(client)
        boundary = snapshots[1]["recorded_at"]

        selected = client.get(f"/api/portfolio/history?since={boundary}").json()["snapshots"]

        assert [snapshot["recorded_at"] for snapshot in selected][:2] == [
            snapshots[0]["recorded_at"],
            snapshots[1]["recorded_at"],
        ]
        assert all(snapshot["recorded_at"] >= boundary for snapshot in selected)


class TestResetPortfolioRoute:
    """Unit tests for POST /api/portfolio/reset."""

    @staticmethod
    def _spend(client: TestClient, db_path: Path) -> None:
        """Put the account into a used state, after lazy initialization has run."""
        client.get("/api/portfolio")
        with connect(db_path) as connection:
            upsert_position(connection, TICKER, 2.0, 100.0)
            update_cash_balance(connection, 1234.56)

    def test_reset_returns_the_starting_state(self, app: FastAPI, db_path: Path) -> None:
        """The response body is the portfolio shape at the starting cash."""
        client = TestClient(app)
        self._spend(client, db_path)

        response = client.post("/api/portfolio/reset")

        assert response.status_code == 200
        assert response.json() == {
            "cash_balance": STARTING_CASH,
            "total_value": STARTING_CASH,
            "positions": [],
        }

    def test_a_later_read_confirms_the_state_changed(
        self, app: FastAPI, db_path: Path
    ) -> None:
        """The reset body is not cosmetic; GET /api/portfolio agrees with it."""
        client = TestClient(app)
        self._spend(client, db_path)
        client.post("/api/portfolio/reset")

        payload = client.get("/api/portfolio").json()

        assert payload["cash_balance"] == STARTING_CASH
        assert payload["positions"] == []

    def test_a_cross_origin_form_post_is_refused(self, app: FastAPI, db_path: Path) -> None:
        """A form-encoded POST cannot drive the reset, so no cross-origin page can.

        A cross-origin HTML form POST is a CORS simple request: no preflight
        fires, the browser sends it, and the side effect lands. Requiring a JSON
        body is what makes the request non-simple. The untouched cash and
        position are asserted alongside the status, because a refusal that still
        wiped the account would satisfy a status-only assertion.
        """
        client = TestClient(app)
        self._spend(client, db_path)

        response = client.post("/api/portfolio/reset", data={"confirm": "true"})

        assert response.status_code == 422
        payload = client.get("/api/portfolio").json()
        assert payload["cash_balance"] == 1234.56
        assert len(payload["positions"]) == 1

    def test_a_get_does_not_reset_anything(self, app: FastAPI, db_path: Path) -> None:
        """The destructive path is POST only, so navigation cannot trigger it.

        The cash balance is asserted rather than the status code: the static
        fallback is mounted at the root and may answer an unmatched GET with the
        index page rather than a 405, and the property that matters is that
        nothing was destroyed.
        """
        client = TestClient(app)
        self._spend(client, db_path)

        client.get("/api/portfolio/reset")

        assert client.get("/api/portfolio").json()["cash_balance"] == 1234.56
