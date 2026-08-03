"""Thread-safe in-memory price cache."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from threading import Lock

from .models import PriceUpdate

HISTORY_POINTS = 60  # Points retained per ticker for sparklines
HISTORY_INTERVAL_SECONDS = 60.0  # Minimum spacing between recorded points


class PriceCache:
    """Latest price, session baseline and recent history for each tracked ticker.

    Writers: exactly one MarketDataSource (simulator or Massive poller).
    Readers: SSE stream, portfolio valuation, trade execution, watchlist.
    """

    def __init__(
        self,
        history_points: int = HISTORY_POINTS,
        history_interval: float = HISTORY_INTERVAL_SECONDS,
    ) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._history: dict[str, deque[float]] = {}
        self._history_at: dict[str, float] = {}
        self._history_points = history_points
        self._history_interval = history_interval
        self._lock = Lock()
        self._version = 0

    # --- Writing ---

    def update(self, ticker: str, price: float, timestamp: float | None = None) -> PriceUpdate:
        """Record a new price. Returns the stored PriceUpdate.

        Derives previous_price and open_price from the entry being replaced, so
        sources stay dumb: they produce a number, the cache supplies the meaning.
        The first update for a ticker pins its session baseline —
        previous_price == open_price == price, direction 'flat', both changes 0.
        """
        with self._lock:
            ts = time.time() if timestamp is None else timestamp
            price = round(price, 2)
            previous = self._prices.get(ticker)

            update = PriceUpdate(
                ticker=ticker,
                price=price,
                previous_price=previous.price if previous else price,
                open_price=previous.open_price if previous else price,
                timestamp=ts,
            )
            self._prices[ticker] = update

            # Version tracks *visible* change. A repeated price refreshes the
            # timestamp (so /api/health still sees a live feed) without waking
            # every SSE client to re-send an identical payload.
            if previous is None or previous.price != price:
                self._version += 1

            self._record_history(ticker, update)
            return update

    def seed_history(
        self, ticker: str, prices: list[float], timestamp: float | None = None
    ) -> None:
        """Install backfilled history for a ticker, replacing anything present.

        Called by a source at startup and when a ticker is added, so sparklines
        are populated on first paint rather than filling in over 30 seconds.
        """
        with self._lock:
            self._history[ticker] = deque(
                (round(p, 2) for p in prices[-self._history_points :]),
                maxlen=self._history_points,
            )
            self._history_at[ticker] = time.time() if timestamp is None else timestamp

    def remove(self, ticker: str) -> None:
        """Forget a ticker entirely — price, baseline and history."""
        with self._lock:
            self._prices.pop(ticker, None)
            self._history.pop(ticker, None)
            self._history_at.pop(ticker, None)

    # --- Reading ---

    def get(self, ticker: str) -> PriceUpdate | None:
        with self._lock:
            return self._prices.get(ticker)

    def get_price(self, ticker: str) -> float | None:
        update = self.get(ticker)
        return update.price if update else None

    def get_all(self) -> dict[str, PriceUpdate]:
        """Shallow copy of every current price. Safe to iterate without the lock."""
        with self._lock:
            return dict(self._prices)

    def get_history(self, ticker: str) -> list[float]:
        """Recent prices, oldest first, up to history_points. Empty if unknown."""
        with self._lock:
            history = self._history.get(ticker)
            return list(history) if history else []

    def newest_timestamp(self) -> float | None:
        """Timestamp of the most recently written price, for /api/health."""
        with self._lock:
            if not self._prices:
                return None
            return max(update.timestamp for update in self._prices.values())

    @property
    def version(self) -> int:
        """Monotonic counter, bumped whenever a price actually changes."""
        return self._version

    def __len__(self) -> int:
        with self._lock:
            return len(self._prices)

    def __contains__(self, ticker: str) -> bool:
        with self._lock:
            return ticker in self._prices

    # --- Internal (callers already hold the lock) ---

    def _record_history(self, ticker: str, update: PriceUpdate) -> None:
        history = self._history.get(ticker)
        if history is None:
            history = self._history[ticker] = deque(maxlen=self._history_points)

        last_at = self._history_at.get(ticker)
        if last_at is None or update.timestamp - last_at >= self._history_interval:
            history.append(update.price)
            self._history_at[ticker] = update.timestamp


async def wait_for_price(cache: PriceCache, ticker: str, timeout: float = 2.0) -> float:
    """Return the current price, waiting up to `timeout` for a first tick.

    Raises ValueError with a user-facing message if no price arrives. Callers
    translate that into a 400 (PLAN.md section 8).
    """
    deadline = time.monotonic() + timeout
    while True:
        price = cache.get_price(ticker)
        if price is not None:
            return price
        if time.monotonic() >= deadline:
            raise ValueError(f"No price available for {ticker} yet, please try again")
        await asyncio.sleep(0.2)
