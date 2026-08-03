"""Abstract interface for market data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod


class MarketDataSource(ABC):
    """Contract for market data providers.

    Implementations push prices into a shared PriceCache on their own schedule.
    Downstream code never asks a source for a price — it reads the cache.

    Lifecycle:
        source = create_market_data_source(cache)
        await source.start(["AAPL", "GOOGL", ...])   # cache populated on return
        await source.add_ticker("TSLA")
        await source.remove_ticker("GOOGL")
        await source.stop()                          # idempotent
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Short identifier for logs and /api/health: 'simulator' or 'massive'."""

    @abstractmethod
    async def start(self, tickers: list[str]) -> None:
        """Begin producing prices for `tickers`.

        Must populate the cache (prices and seeded history) before returning, so
        the first HTTP request never sees an empty cache. Called exactly once.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Stop the background task. Idempotent, and never writes afterwards."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Track a ticker. No-op if already tracked. Seeds price and history."""

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Stop tracking a ticker and remove it from the cache. No-op if absent."""

    @abstractmethod
    def get_tickers(self) -> list[str]:
        """Currently tracked tickers. Synchronous — called from request handlers."""
