"""Health endpoint. Shape is fixed by PLAN.md section 8.

Enough to answer "is the stream alive?" in one request: which source is
running, how many tickers it has priced, and how stale the newest of them is.
"""

from __future__ import annotations

import time

from fastapi import APIRouter

from app.state import get_cache, get_source

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def read_health() -> dict:
    """Market data liveness. newest_price_age_seconds is null on an empty cache."""
    cache = get_cache()
    newest = cache.newest_timestamp()

    return {
        "status": "ok",
        "market_source": get_source().source_name,
        "tickers_cached": len(cache),
        "newest_price_age_seconds": None if newest is None else round(time.time() - newest, 3),
    }
