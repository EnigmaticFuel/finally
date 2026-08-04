"""Process-wide market data singletons.

One PriceCache and one MarketDataSource exist per process, installed at startup
by the lifespan handler in main.py. Request handlers and services read prices
through get_cache(); tests install fakes with set_market().
"""

from __future__ import annotations

from app.market import MarketDataSource, PriceCache

_cache: PriceCache | None = None
_source: MarketDataSource | None = None


def set_market(cache: PriceCache, source: MarketDataSource) -> None:
    """Install the process singletons. Called by the lifespan handler and by tests."""
    global _cache, _source
    _cache = cache
    _source = source


def clear_market() -> None:
    """Drop the singletons. Called on shutdown and by test teardown."""
    global _cache, _source
    _cache = None
    _source = None


def get_cache() -> PriceCache:
    if _cache is None:
        raise RuntimeError("Market data not started")
    return _cache


def get_source() -> MarketDataSource:
    if _source is None:
        raise RuntimeError("Market data not started")
    return _source
