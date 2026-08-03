"""Massive (Polygon.io) REST client for real market data."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time

from massive import RESTClient
from massive.rest.models import SnapshotMarketType

from .cache import HISTORY_POINTS, PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)

MAX_BACKOFF_MULTIPLIER = 8.0
BACKFILL_LOOKBACK_DAYS = 7


class MassiveDataSource(MarketDataSource):
    """MarketDataSource backed by the Massive REST API.

    Polls /v2/snapshot/locale/us/markets/stocks/tickers for the union of watched
    tickers in one request, then writes each result to the PriceCache.

    Rate limits:
      Basic (free): 5 req/min  -> poll_interval 15.0 (default)
      Paid tiers:   unlimited  -> poll_interval 2.0-5.0
    """

    def __init__(
        self,
        api_key: str,
        price_cache: PriceCache,
        poll_interval: float = 15.0,
        backfill_history: bool = True,
    ) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._backfill_enabled = backfill_history
        self._tickers: list[str] = []
        self._client: RESTClient | None = None
        self._task: asyncio.Task | None = None
        self._backfill_task: asyncio.Task | None = None
        self._backoff = 1.0

    @property
    def source_name(self) -> str:
        return "massive"

    # --- Lifecycle ---

    async def start(self, tickers: list[str]) -> None:
        self._client = RESTClient(api_key=self._api_key)
        self._tickers = [t.upper() for t in tickers]

        await self._log_market_status()
        await self._poll_once()  # Cache has prices before start() returns

        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")
        if self._backfill_enabled:
            self._backfill_task = asyncio.create_task(
                self._backfill_all(list(self._tickers)), name="massive-backfill"
            )
        logger.info(
            "Massive poller started: %d tickers, %.1fs interval",
            len(self._tickers),
            self._interval,
        )

    async def stop(self) -> None:
        for task in (self._task, self._backfill_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._task = None
        self._backfill_task = None
        self._client = None
        logger.info("Massive poller stopped")

    async def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        if ticker in self._tickers:
            return
        self._tickers.append(ticker)
        logger.info("Massive: added ticker %s (will appear on next poll)", ticker)
        if self._backfill_enabled:
            await self._backfill_one(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)
        logger.info("Massive: removed ticker %s", ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    # --- Polling ---

    async def _poll_loop(self) -> None:
        """Poll on interval, widening under sustained failure."""
        while True:
            await asyncio.sleep(self._interval * self._backoff)
            await self._poll_once()

    async def _poll_once(self) -> None:
        """Execute one poll cycle. Never raises — the loop must survive every failure."""
        if not self._tickers or not self._client:
            return

        try:
            # The Massive RESTClient is synchronous — run in a thread to
            # avoid blocking the event loop.
            snapshots = await asyncio.to_thread(self._fetch_snapshots)
        except Exception as exc:
            # 401 bad key, 403 not in plan, 429 rate limited, network, timeout.
            self._backoff = min(self._backoff * 2, MAX_BACKOFF_MULTIPLIER)
            logger.error(
                "Massive poll failed (%s); backing off to %.1fs",
                exc,
                self._interval * self._backoff,
            )
            return

        self._backoff = 1.0
        updated = 0
        for snap in snapshots:
            quote = self._extract_quote(snap)
            if quote is None:
                logger.warning(
                    "No usable price in snapshot for %s", getattr(snap, "ticker", "???")
                )
                continue
            price, timestamp = quote
            self._cache.update(ticker=snap.ticker, price=price, timestamp=timestamp)
            updated += 1

        logger.debug("Massive poll: updated %d/%d tickers", updated, len(self._tickers))

    def _fetch_snapshots(self) -> list:
        """Synchronous SDK call. Runs on a worker thread."""
        assert self._client is not None
        return self._client.get_snapshot_all(
            market_type=SnapshotMarketType.STOCKS,
            tickers=self._tickers,
        )

    @staticmethod
    def _extract_quote(snap) -> tuple[float, float] | None:
        """Best available price and its Unix-seconds timestamp, or None.

        TIMESTAMP UNITS ARE NOT UNIFORM IN THIS API:
            last_trade.timestamp, last_quote.timestamp, snapshot.updated -> NANOseconds
            Agg.timestamp (aggregate bars), min.timestamp               -> MILLIseconds

        Massive's own sample lastTrade.t of 1605195918306274000 is 2020-11-12
        when divided by 1e9, and out of range for any other unit. Dividing by
        1e3 puts every price roughly 50,000 years in the future, silently.
        """
        trade = getattr(snap, "last_trade", None)
        if trade is not None and getattr(trade, "price", None):
            return float(trade.price), float(trade.timestamp) / 1_000_000_000.0

        minute = getattr(snap, "min", None)
        if minute is not None and getattr(minute, "close", None):
            return float(minute.close), float(minute.timestamp) / 1_000.0

        day = getattr(snap, "day", None)
        if day is not None and getattr(day, "close", None):
            return float(day.close), time.time()

        return None

    # --- History backfill ---

    async def _backfill_all(self, tickers: list[str]) -> None:
        """Seed sparkline history, one ticker at a time, spaced to respect the
        rate limit. Off the poll loop: once at startup, once per added ticker.

        On the free tier this shares a 5 req/min budget with the poller, so
        sparklines fill in over the first minutes rather than instantly. That is
        the correct trade — a burst of ten requests at startup earns a 429 and
        no history at all.
        """
        for ticker in tickers:
            await self._backfill_one(ticker)
            await asyncio.sleep(self._interval)

    async def _backfill_one(self, ticker: str) -> None:
        if self._client is None:
            return
        try:
            history = await asyncio.to_thread(self._fetch_history, ticker)
        except Exception as exc:
            logger.warning("History backfill failed for %s: %s", ticker, exc)
            return
        if history:
            self._cache.seed_history(ticker, history)
            logger.debug("Backfilled %d history points for %s", len(history), ticker)

    def _fetch_history(self, ticker: str) -> list[float]:
        """Most recent ~60 one-minute closes. Synchronous; runs on a thread."""
        assert self._client is not None
        today = dt.date.today()
        bars = self._client.get_aggs(
            ticker=ticker,
            multiplier=1,
            timespan="minute",
            from_=(today - dt.timedelta(days=BACKFILL_LOOKBACK_DAYS)).isoformat(),
            to=today.isoformat(),
            limit=HISTORY_POINTS,
            sort="desc",
        )
        return [float(bar.close) for bar in reversed(list(bars))]  # Oldest first

    # --- Diagnostics ---

    async def _log_market_status(self) -> None:
        """Log whether the market is open. 'Prices are not moving' is the most
        likely support question on this path, and this line is the answer."""
        if self._client is None:
            return
        try:
            status = await asyncio.to_thread(self._client.get_market_status)
            logger.info("Massive market status: %s", getattr(status, "market", "unknown"))
        except Exception as exc:
            logger.warning("Could not read market status: %s", exc)
