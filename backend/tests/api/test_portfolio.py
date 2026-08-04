"""GET /api/portfolio, POST /api/portfolio/trade, GET /api/portfolio/history."""

import pytest

from app.db import DEFAULT_TICKERS, get_watchlist

# --- GET /api/portfolio -----------------------------------------------------


def test_portfolio_shape_on_a_fresh_account(client):
    response = client.get("/api/portfolio")

    assert response.status_code == 200
    assert response.json() == {
        "cash_balance": 10000.0,
        "total_value": 10000.0,
        "positions": [],
    }


def test_portfolio_position_shape(client, market):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "buy"})
    market.set_price("AAPL", 200.0)

    body = client.get("/api/portfolio").json()

    assert body["cash_balance"] == 8100.0
    assert body["total_value"] == 10100.0
    assert body["positions"] == [
        {
            "ticker": "AAPL",
            "quantity": 10.0,
            "avg_cost": 190.0,
            "current_price": 200.0,
            "market_value": 2000.0,
            "unrealized_pnl": 100.0,
            "unrealized_pnl_percent": pytest.approx(5.2632, abs=1e-4),
        }
    ]


# --- POST /api/portfolio/trade ----------------------------------------------


def test_buy_returns_the_fill(client):
    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "buy"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["side"] == "buy"
    assert body["quantity"] == 10
    assert body["fill_price"] == 190.0
    assert body["total_cost"] == 1900.0
    assert body["cash_balance"] == 8100.0
    assert body["executed_at"].endswith("Z")


def test_the_client_price_is_ignored(client, market):
    """The fill is the server's price, whatever the client thought it saw."""
    market.set_price("AAPL", 195.0)
    response = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "quantity": 1, "side": "buy", "price": 1.0},
    )

    assert response.json()["fill_price"] == 195.0


def test_sell_returns_the_proceeds(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "buy"})
    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "sell"}
    )

    assert response.status_code == 200
    assert response.json()["cash_balance"] == 10000.0
    assert client.get("/api/portfolio").json()["positions"] == []


def test_insufficient_cash_is_400_with_a_readable_message(client):
    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 100, "side": "buy"}
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Insufficient cash: need $19000.00, have $10000.00"}


def test_insufficient_shares_is_400(client):
    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "sell"}
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Insufficient shares: need 1, have 0 AAPL"}


@pytest.mark.parametrize("quantity", [0, -5])
def test_non_positive_quantity_is_400(client, quantity):
    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": quantity, "side": "buy"}
    )

    assert response.status_code == 400
    assert "greater than zero" in response.json()["detail"]


@pytest.mark.parametrize("quantity", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_quantity_is_400(client, quantity):
    response = client.post(
        "/api/portfolio/trade",
        content=f'{{"ticker": "AAPL", "quantity": {quantity}, "side": "buy"}}',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert "finite number" in response.json()["detail"]


def test_malformed_ticker_is_400(client):
    response = client.post(
        "/api/portfolio/trade", json={"ticker": "TOOLONG", "quantity": 1, "side": "buy"}
    )

    assert response.status_code == 400
    assert "Invalid ticker symbol" in response.json()["detail"]


def test_unknown_side_is_400(client):
    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "short"}
    )

    assert response.status_code == 400
    assert "Invalid side" in response.json()["detail"]


def test_a_missing_field_is_422(client):
    response = client.post("/api/portfolio/trade", json={"ticker": "AAPL"})
    assert response.status_code == 422


def test_trading_an_unwatched_ticker_adds_it(client):
    assert "PYPL" not in get_watchlist()

    response = client.post(
        "/api/portfolio/trade", json={"ticker": "PYPL", "quantity": 1, "side": "buy"}
    )

    assert response.status_code == 200
    assert [t["ticker"] for t in client.get("/api/watchlist").json()["tickers"]] == [
        *DEFAULT_TICKERS,
        "PYPL",
    ]


# --- GET /api/portfolio/history ---------------------------------------------


def test_history_starts_with_the_seed_snapshot(client):
    body = client.get("/api/portfolio/history").json()

    assert len(body["snapshots"]) == 1
    assert body["snapshots"][0]["total_value"] == 10000.0
    assert body["snapshots"][0]["recorded_at"].endswith("Z")


def test_history_gains_a_point_per_trade(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "sell"})

    assert len(client.get("/api/portfolio/history").json()["snapshots"]) == 3


def test_history_is_newest_first(client, market):
    market.set_price("AAPL", 100.0)
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
    market.set_price("AAPL", 300.0)
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})

    snapshots = client.get("/api/portfolio/history").json()["snapshots"]

    assert [s["recorded_at"] for s in snapshots] == sorted(
        (s["recorded_at"] for s in snapshots), reverse=True
    )
    assert snapshots[0]["total_value"] == 10200.0


def test_history_honours_limit(client):
    for _ in range(3):
        client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})

    assert len(client.get("/api/portfolio/history?limit=2").json()["snapshots"]) == 2


def test_history_honours_since(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
    cutoff = client.get("/api/portfolio/history").json()["snapshots"][0]["recorded_at"]
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})

    body = client.get("/api/portfolio/history", params={"since": cutoff}).json()

    assert len(body["snapshots"]) == 1
    assert body["snapshots"][0]["recorded_at"] > cutoff


def test_a_zero_limit_is_422(client):
    assert client.get("/api/portfolio/history?limit=0").status_code == 422
