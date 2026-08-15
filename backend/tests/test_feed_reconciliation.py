"""Reconciliation between the market data feed and the tickers the user cares about.

Every test in this module drives the assembled app's real lifespan and the real
SimulatorDataSource, and no test here introduces a price of its own. That rule is
the whole point of the module. A test that writes the price itself performs the
production step under test - registering the symbol with the running feed - and
so reports green whether or not production does it, which is exactly how the
missing registration seam stayed invisible behind a green suite.

Prices therefore come from the simulator or not at all. No exact price and no
elapsed duration is asserted: the simulator moves every 500ms and this repo
already carries one timer-granularity flake on Windows.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.connection import get_db_path
from app.db.seed import DEFAULT_TICKERS
from app.main import create_app

UNWATCHED = "PYPL"


def _app_for(path: Path) -> FastAPI:
    """A fresh app pointed at one database, built the way the root fixture builds one.

    Built here rather than taken from the root app fixture because the restart
    test needs two apps against the same path, which a single fixture cannot give.
    """
    application = create_app()
    application.dependency_overrides[get_db_path] = lambda: path
    application.state.db_path = path
    return application


def test_trading_an_unregistered_ticker_fills_and_joins_the_watchlist(db_path: Path) -> None:
    """A symbol the feed has never been told about trades, and lands on the watchlist.

    The production-shaped proof of PORT-07 and ROADMAP SC2: real lifespan, real
    simulator, no hand-written price. Before the registration seam existed this
    failed as 400 {"detail": "No price available for PYPL yet, please try again"}
    after roughly 2.06 seconds, with the symbol absent from the watchlist
    entirely - the two-second wait had no producer to wait on.
    """
    assert UNWATCHED not in DEFAULT_TICKERS

    app = _app_for(db_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/portfolio/trade",
            json={"ticker": UNWATCHED, "side": "buy", "quantity": 1},
        )
        assert response.status_code == 200, response.text

        filled = response.json()
        assert filled["ticker"] == UNWATCHED
        assert filled["fill_price"] > 0

        assert UNWATCHED in app.state.market_source.get_tickers()

        watched = client.get("/api/watchlist").json()["tickers"]
        entry = next(row for row in watched if row["ticker"] == UNWATCHED)
        assert entry["price"] is not None

        portfolio = client.get("/api/portfolio").json()
        position = next(row for row in portfolio["positions"] if row["ticker"] == UNWATCHED)
        assert position["current_price"] is not None


def test_a_user_added_ticker_still_prices_after_a_restart(db_path: Path) -> None:
    """A ticker added in one run values, sells and removes in the next.

    The symbol is introduced through POST /api/watchlist rather than by trading
    it directly, deliberately: that route registered its ticker with the feed
    before this plan, so this test discriminates the boot-from-watchlist gap
    alone and cannot pass or fail for the registration-on-trade reason.

    Before the lifespan read the persisted watchlist, the second app tracked only
    the ten defaults and the holding was stranded: GET /api/watchlist reported
    the symbol with a null price, GET /api/portfolio reported it with a null
    current_price and market_value and left it out of a total_value of 9662.91,
    the sell returned 400 "No price available for PYPL yet, please try again",
    and the delete returned 409 - refusing to strand the very position that could
    not be sold.
    """
    assert UNWATCHED not in DEFAULT_TICKERS

    first = _app_for(db_path)
    with TestClient(first) as client:
        assert client.post("/api/watchlist", json={"ticker": UNWATCHED}).status_code == 200
        bought = client.post(
            "/api/portfolio/trade",
            json={"ticker": UNWATCHED, "side": "buy", "quantity": 1},
        )
        assert bought.status_code == 200, bought.text

    second = _app_for(db_path)
    with TestClient(second) as client:
        watched = client.get("/api/watchlist").json()["tickers"]
        entry = next(row for row in watched if row["ticker"] == UNWATCHED)
        assert entry["price"] is not None

        portfolio = client.get("/api/portfolio").json()
        position = next(row for row in portfolio["positions"] if row["ticker"] == UNWATCHED)
        assert position["current_price"] is not None
        assert position["market_value"] is not None
        assert portfolio["total_value"] > portfolio["cash_balance"]

        sold = client.post(
            "/api/portfolio/trade",
            json={"ticker": UNWATCHED, "side": "sell", "quantity": 1},
        )
        assert sold.status_code == 200, sold.text

        assert client.delete(f"/api/watchlist/{UNWATCHED}").status_code == 204
