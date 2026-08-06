"""Health endpoint reporting whether the price feed is actually alive."""

from __future__ import annotations

import time

from fastapi import APIRouter

from app.market import MarketDataSource, PriceCache


def create_health_router(price_cache: PriceCache, source: MarketDataSource) -> APIRouter:
    """Build the /api/health router bound to a specific cache and source.

    The router is created inside the factory, not at module level, so calling
    this twice (an app plus a test app) does not register the route twice.
    """
    router = APIRouter(prefix="/api", tags=["system"])

    @router.get("/health")
    async def get_health() -> dict[str, object]:
        """Report the market source and how stale the newest cached price is.

        newest_price_age_seconds is the reason this endpoint is worth calling:
        a fixed "ok" reads identically whether the feed is streaming or has
        stopped, so the age is what lets an operator tell the two apart. It is
        None until the first price arrives.

        The payload is these four keys and nothing else. No API key, and no
        derivative of one, belongs in a response this freely readable.
        """
        newest = price_cache.newest_timestamp()
        return {
            "status": "ok",
            "market_source": source.source_name,
            "tickers_cached": len(price_cache),
            "newest_price_age_seconds": None if newest is None else round(time.time() - newest, 3),
        }

    return router
