"""Fixtures for the service-layer tests.

Lives here rather than in the root conftest so Phase 1's fixtures stay untouched.
"""

from __future__ import annotations

import pytest

from app.market import MarketDataSource


class RecordingSource(MarketDataSource):
    """A MarketDataSource that records calls instead of producing prices.

    SimulatorDataSource.add_ticker returns immediately when the source has not
    been started, so a real unstarted source would let a registration test pass
    while proving nothing was registered. This records the call instead.

    fail_on_add makes D-09's ordering rule testable: the watchlist row must
    survive a source that refuses the ticker.
    """

    def __init__(self, fail_on_add: bool = False) -> None:
        self.added: list[str] = []
        self.removed: list[str] = []
        self.started: list[str] = []
        self.fail_on_add = fail_on_add

    @property
    def source_name(self) -> str:
        return "recording"

    async def start(self, tickers: list[str]) -> None:
        self.started = list(tickers)

    async def stop(self) -> None:
        pass

    async def add_ticker(self, ticker: str) -> None:
        if self.fail_on_add:
            raise RuntimeError(f"Recording source refused {ticker}")
        self.added.append(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self.removed.append(ticker)

    def get_tickers(self) -> list[str]:
        return list(self.added)


@pytest.fixture
def recording_source() -> RecordingSource:
    """A fresh source that accepts every ticker."""
    return RecordingSource()


@pytest.fixture
def failing_source() -> RecordingSource:
    """A source that raises on add_ticker, for the D-09 ordering test."""
    return RecordingSource(fail_on_add=True)
