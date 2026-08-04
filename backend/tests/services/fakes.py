"""A market data source that ticks only when a test tells it to.

The real simulator moves prices on a timer, which makes assertions about fill
prices and P&L unreproducible. This one holds whatever price a test sets.
"""

from __future__ import annotations

from app.market import MarketDataSource, PriceCache

DEFAULT_PRICE = 100.0


class FakeSource(MarketDataSource):
    """Tracks tickers and writes one fixed price per ticker into the cache."""

    def __init__(self, cache: PriceCache, prices: dict[str, float] | None = None) -> None:
        self.cache = cache
        self.prices = dict(prices or {})
        self.tickers: list[str] = []
        self.stopped = False

    @property
    def source_name(self) -> str:
        return "fake"

    async def start(self, tickers: list[str]) -> None:
        for ticker in tickers:
            await self.add_ticker(ticker)

    async def stop(self) -> None:
        self.stopped = True

    async def add_ticker(self, ticker: str) -> None:
        if ticker in self.tickers:
            return
        self.tickers.append(ticker)
        price = self.prices.setdefault(ticker, DEFAULT_PRICE)
        self.cache.update(ticker, price)
        self.cache.seed_history(ticker, [price] * 60)

    async def remove_ticker(self, ticker: str) -> None:
        if ticker in self.tickers:
            self.tickers.remove(ticker)
        self.cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self.tickers)

    def set_price(self, ticker: str, price: float) -> None:
        """Move a price mid-test, the way a tick would."""
        self.prices[ticker] = price
        self.cache.update(ticker, price)


class SilentSource(FakeSource):
    """Accepts tickers but never publishes a price, so wait_for_price expires."""

    async def add_ticker(self, ticker: str) -> None:
        if ticker not in self.tickers:
            self.tickers.append(ticker)
