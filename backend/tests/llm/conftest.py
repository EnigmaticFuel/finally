"""Fixtures for the LLM tests: a tmp database and a fake market source.

Nothing here reaches the network. The real API is never called: LLM_MOCK drives
the mock path, and the tests that cover the real path stub the completion call.
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app import state
from app.api import chat
from app.db import get_watchlist, init_db
from app.market import MarketDataSource, PriceCache

FAKE_PRICES = {
    "AAPL": 190.0,
    "GOOGL": 175.0,
    "MSFT": 420.0,
    "AMZN": 185.0,
    "TSLA": 250.0,
    "NVDA": 130.0,
    "META": 500.0,
    "JPM": 200.0,
    "V": 280.0,
    "NFLX": 600.0,
    "PYPL": 65.0,
}
DEFAULT_FAKE_PRICE = 100.0


class FakeSource(MarketDataSource):
    """A market source with fixed prices and no background task."""

    def __init__(self, cache: PriceCache) -> None:
        self._cache = cache
        self._tickers: list[str] = []

    @property
    def source_name(self) -> str:
        return "fake"

    async def start(self, tickers: list[str]) -> None:
        for ticker in tickers:
            await self.add_ticker(ticker)

    async def stop(self) -> None:
        self._tickers = []

    async def add_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            return
        self._tickers.append(ticker)
        self._cache.update(ticker, FAKE_PRICES.get(ticker, DEFAULT_FAKE_PRICE))

    async def remove_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            self._tickers.remove(ticker)
            self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)


@pytest.fixture
def db(tmp_path, monkeypatch):
    """An initialized, seeded database in tmp_path."""
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "finally.db"))
    init_db()


@pytest.fixture
async def market(db):
    """Install a fake cache and source priced for the seeded watchlist."""
    cache = PriceCache()
    source = FakeSource(cache)
    await source.start(get_watchlist())
    state.set_market(cache, source)
    yield cache
    state.clear_market()


@pytest.fixture
def mock_llm(monkeypatch):
    """Force the deterministic mock path."""
    monkeypatch.setenv("LLM_MOCK", "true")


@pytest.fixture
def no_key(monkeypatch):
    """Leave the mock off and remove any real key from the environment."""
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


@pytest.fixture
async def client(market, mock_llm):
    """An httpx client bound to the chat router, with the LLM mocked."""
    app = FastAPI()
    app.include_router(chat.router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
