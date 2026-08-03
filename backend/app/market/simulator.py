"""GBM-based market simulator."""

from __future__ import annotations

import asyncio
import logging
import math
import random

import numpy as np

from .cache import HISTORY_POINTS, PriceCache
from .interface import MarketDataSource
from .seed_prices import (
    CORRELATION_GROUPS,
    CROSS_GROUP_CORR,
    INTRA_FINANCE_CORR,
    INTRA_TECH_CORR,
    params_for,
)

logger = logging.getLogger(__name__)

# 500ms expressed as a fraction of a trading year
# 252 trading days * 6.5 hours/day * 3600 seconds/hour = 5,896,800 seconds
TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600  # 5,896,800
DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR  # ~8.48e-8 for a 500ms tick
HISTORY_STEP_TICKS = 120  # One backfill point per simulated minute


class GBMSimulator:
    """Correlated geometric Brownian motion over a set of tickers.

    Math:
        S(t+dt) = S(t) * exp((mu - sigma^2/2) * dt + sigma * sqrt(dt) * Z)

    Where:
        S(t)   = current price
        mu     = annualized drift (expected return)
        sigma  = annualized volatility
        dt     = time step as a fraction of a trading year
        Z      = correlated standard normal random variable

    Pure and synchronous: holds prices, parameters and the Cholesky factor, and
    knows nothing about the cache, asyncio or FastAPI. Tests drive step()
    directly with a large dt instead of sleeping.
    """

    TRADING_SECONDS_PER_YEAR = TRADING_SECONDS_PER_YEAR
    DEFAULT_DT = DEFAULT_DT

    def __init__(
        self,
        tickers: list[str],
        dt: float = DEFAULT_DT,
        event_probability: float = 0.001,
    ) -> None:
        self._dt = dt
        self._event_prob = event_probability

        # Per-ticker state
        self._tickers: list[str] = []
        self._prices: dict[str, float] = {}
        self._params: dict[str, dict[str, float]] = {}

        # Cholesky decomposition of the correlation matrix (for correlated moves)
        self._cholesky: np.ndarray | None = None

        for ticker in tickers:
            self._add_internal(ticker)
        self._rebuild_cholesky()

    # --- Public API ---

    def step(self) -> dict[str, float]:
        """Advance every ticker one tick. Returns {ticker: rounded price}.

        The hot path: called every 500ms forever. All n normals are drawn in one
        numpy call and correlated with one matrix multiply rather than looping.
        """
        n = len(self._tickers)
        if n == 0:
            return {}

        z = np.random.standard_normal(n)
        if self._cholesky is not None:
            z = self._cholesky @ z

        prices: dict[str, float] = {}
        for i, ticker in enumerate(self._tickers):
            params = self._params[ticker]
            mu, sigma = params["mu"], params["sigma"]

            drift = (mu - 0.5 * sigma**2) * self._dt
            diffusion = sigma * math.sqrt(self._dt) * z[i]
            self._prices[ticker] *= math.exp(drift + diffusion)

            # Random shock: GBM alone is smooth, real markets jump. ~0.1% per
            # tick per ticker is an event every ~50s across ten tickers — often
            # enough to see in a minute, rare enough to stay an event.
            if random.random() < self._event_prob:
                magnitude = random.uniform(0.02, 0.05)
                sign = random.choice([-1, 1])
                self._prices[ticker] *= 1 + magnitude * sign
                logger.debug(
                    "Shock event on %s: %.1f%% %s",
                    ticker,
                    magnitude * 100,
                    "up" if sign > 0 else "down",
                )

            prices[ticker] = round(self._prices[ticker], 2)

        return prices

    def add_ticker(self, ticker: str) -> None:
        """Add a ticker to the simulation. Rebuilds the correlation matrix."""
        if ticker in self._prices:
            return
        self._add_internal(ticker)
        self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker from the simulation. Rebuilds the correlation matrix."""
        if ticker not in self._prices:
            return
        self._tickers.remove(ticker)
        del self._prices[ticker]
        del self._params[ticker]
        self._rebuild_cholesky()

    def get_price(self, ticker: str) -> float | None:
        """Current price for a ticker, or None if not tracked."""
        price = self._prices.get(ticker)
        return round(price, 2) if price is not None else None

    def get_tickers(self) -> list[str]:
        """Return the list of currently tracked tickers."""
        return list(self._tickers)

    def backfill_history(self, ticker: str, points: int = HISTORY_POINTS) -> list[float]:
        """Manufacture plausible prior history ending at the current price.

        Runs the GBM recurrence *backwards* — dividing rather than multiplying —
        so the series ends at the live price and joins the stream continuously.
        The coarser dt gives a per-minute cadence, so 60 points is an hour of
        price action with visible shape rather than 30 seconds of flat line.
        """
        params = self._params.get(ticker)
        if params is None or points < 1:
            return []

        mu, sigma = params["mu"], params["sigma"]
        dt = self._dt * HISTORY_STEP_TICKS
        drift = (mu - 0.5 * sigma**2) * dt
        scale = sigma * math.sqrt(dt)

        price = self._prices[ticker]
        history = [round(price, 2)]
        for z in np.random.standard_normal(points - 1):
            price /= math.exp(drift + scale * z)
            history.append(round(price, 2))

        history.reverse()  # Oldest first, ending at the current price
        return history

    # --- Internals ---

    def _add_internal(self, ticker: str) -> None:
        """Add without rebuilding Cholesky, for batch initialization."""
        if ticker in self._prices:
            return
        price, params = params_for(ticker)
        self._tickers.append(ticker)
        self._prices[ticker] = price
        self._params[ticker] = params

    def _rebuild_cholesky(self) -> None:
        """Refactor the correlation matrix. O(n^3), called only on add/remove."""
        n = len(self._tickers)
        if n <= 1:
            self._cholesky = None
            return

        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                rho = self._pairwise_correlation(self._tickers[i], self._tickers[j])
                corr[i, j] = corr[j, i] = rho

        try:
            self._cholesky = np.linalg.cholesky(corr)
        except np.linalg.LinAlgError:
            # Should be unreachable with the block structure in seed_prices.py.
            # Degrade to independent draws rather than taking the price feed
            # down over a correlation constant.
            logger.error("Correlation matrix not positive definite; using independent draws")
            self._cholesky = None

    @staticmethod
    def _pairwise_correlation(t1: str, t2: str) -> float:
        """Sector-based correlation: tech 0.6, finance 0.5, everything else 0.3."""
        tech = CORRELATION_GROUPS["tech"]
        finance = CORRELATION_GROUPS["finance"]

        if t1 in tech and t2 in tech:
            return INTRA_TECH_CORR
        if t1 in finance and t2 in finance:
            return INTRA_FINANCE_CORR
        return CROSS_GROUP_CORR


class SimulatorDataSource(MarketDataSource):
    """MarketDataSource backed by the GBM simulator.

    Owns one asyncio task that steps the simulation every `update_interval`
    seconds and writes each price to the cache. No maths, no I/O.
    """

    def __init__(
        self,
        price_cache: PriceCache,
        update_interval: float = 0.5,
        event_probability: float = 0.001,
    ) -> None:
        self._cache = price_cache
        self._interval = update_interval
        self._event_prob = event_probability
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    @property
    def source_name(self) -> str:
        return "simulator"

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(
            tickers=tickers,
            event_probability=self._event_prob,
        )
        # Populate the cache *before* the loop starts, so start() returns with
        # prices and sparklines already available and the first HTTP request
        # never sees an empty cache.
        for ticker in tickers:
            self._seed(ticker)

        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")
        logger.info("Simulator started with %d tickers", len(tickers))

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Simulator stopped")

    async def add_ticker(self, ticker: str) -> None:
        if self._sim is None:
            return
        if ticker in self._sim.get_tickers():
            return
        self._sim.add_ticker(ticker)
        self._seed(ticker)
        logger.info("Simulator: added ticker %s", ticker)

    async def remove_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)
        logger.info("Simulator: removed ticker %s", ticker)

    def get_tickers(self) -> list[str]:
        return self._sim.get_tickers() if self._sim else []

    # --- Internals ---

    def _seed(self, ticker: str) -> None:
        """Backfill history then publish the first price. Order matters: the
        history must be in place before the price the sparkline ends at."""
        assert self._sim is not None
        price = self._sim.get_price(ticker)
        if price is None:
            return
        self._cache.seed_history(ticker, self._sim.backfill_history(ticker))
        self._cache.update(ticker=ticker, price=price)

    async def _run_loop(self) -> None:
        """Core loop: step the simulation, write to cache, sleep."""
        while True:
            try:
                if self._sim:
                    prices = self._sim.step()
                    for ticker, price in prices.items():
                        self._cache.update(ticker=ticker, price=price)
            except Exception:
                # A background task that raises dies silently and takes the
                # whole price feed with it, leaving a UI that looks connected
                # and frozen. Log and take the next tick.
                logger.exception("Simulator step failed")
            await asyncio.sleep(self._interval)
