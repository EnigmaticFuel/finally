"""Tests for the portfolio routes."""

from __future__ import annotations

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.seed import STARTING_CASH

TICKER = "AAPL"
SERVER_PRICE = 190.52


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
