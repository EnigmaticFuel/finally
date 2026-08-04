"""GET, POST /api/watchlist and DELETE /api/watchlist/{ticker}."""

import pytest

from app.db import DEFAULT_TICKERS


def test_list_returns_the_seeded_tickers(client):
    response = client.get("/api/watchlist")

    assert response.status_code == 200
    assert [t["ticker"] for t in response.json()["tickers"]] == DEFAULT_TICKERS


def test_list_entry_shape(client):
    entry = client.get("/api/watchlist").json()["tickers"][0]

    assert entry["ticker"] == "AAPL"
    assert entry["price"] == 190.0
    assert entry["open_price"] == 190.0
    assert entry["change_from_open_percent"] == 0.0
    assert len(entry["history"]) == 60


def test_history_seeds_the_sparkline(client, market):
    """The first paint must not wait 30 seconds for a line to appear."""
    market.cache.seed_history("AAPL", [188.0, 189.0, 190.0])

    entry = client.get("/api/watchlist").json()["tickers"][0]

    assert entry["history"] == [188.0, 189.0, 190.0]


def test_add_returns_the_new_entry(client):
    response = client.post("/api/watchlist", json={"ticker": "PYPL"})

    assert response.status_code == 200
    assert response.json()["ticker"] == "PYPL"
    assert response.json()["price"] == 100.0


def test_add_appends_to_the_list(client, market):
    client.post("/api/watchlist", json={"ticker": "PYPL"})

    assert [t["ticker"] for t in client.get("/api/watchlist").json()["tickers"]] == [
        *DEFAULT_TICKERS,
        "PYPL",
    ]
    assert "PYPL" in market.get_tickers()


def test_add_normalizes_the_symbol(client):
    assert client.post("/api/watchlist", json={"ticker": "pypl"}).json()["ticker"] == "PYPL"


def test_adding_an_existing_ticker_is_not_an_error(client):
    response = client.post("/api/watchlist", json={"ticker": "AAPL"})

    assert response.status_code == 200
    assert len(client.get("/api/watchlist").json()["tickers"]) == len(DEFAULT_TICKERS)


@pytest.mark.parametrize("ticker", ["", "TOOLONG", "PY PL", "1234"])
def test_adding_a_malformed_symbol_is_400(client, ticker):
    response = client.post("/api/watchlist", json={"ticker": ticker})

    assert response.status_code == 400
    assert "Invalid ticker symbol" in response.json()["detail"]


def test_add_without_a_ticker_is_422(client):
    assert client.post("/api/watchlist", json={}).status_code == 422


def test_delete_removes_the_ticker(client, market):
    response = client.delete("/api/watchlist/AAPL")

    assert response.status_code == 200
    assert response.json() == {"ticker": "AAPL"}
    assert "AAPL" not in [t["ticker"] for t in client.get("/api/watchlist").json()["tickers"]]
    assert "AAPL" not in market.get_tickers()


def test_delete_is_case_insensitive(client):
    assert client.delete("/api/watchlist/aapl").status_code == 200


def test_deleting_an_unwatched_ticker_is_404(client):
    response = client.delete("/api/watchlist/PYPL")

    assert response.status_code == 404
    assert response.json() == {"detail": "PYPL is not on the watchlist"}


def test_deleting_a_malformed_symbol_is_400(client):
    response = client.delete("/api/watchlist/TOOLONG")

    assert response.status_code == 400
    assert "Invalid ticker symbol" in response.json()["detail"]


def test_deleting_a_held_ticker_is_409(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})

    response = client.delete("/api/watchlist/AAPL")

    assert response.status_code == 409
    assert "position" in response.json()["detail"]
    assert "AAPL" in [t["ticker"] for t in client.get("/api/watchlist").json()["tickers"]]


def test_deleting_after_selling_out_succeeds(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "sell"})

    assert client.delete("/api/watchlist/AAPL").status_code == 200
