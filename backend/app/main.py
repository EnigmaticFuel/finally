"""FastAPI application assembly."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.health import create_health_router
from app.config import DB_PATH
from app.market import PriceCache, create_market_data_source, create_stream_router

# Absolute, because app.frontend() resolves `directory` against the process
# CWD and its check_dir="auto" raises at app-creation time. A relative path
# therefore breaks the whole suite at collection depending on where the
# process was launched from, not just the one test that fetches the page.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Named here for now; plan 01-02 moves the canonical list to app/db/seed.py,
# where the default watchlist belongs as user data.
DEFAULT_TICKERS: list[str] = [
    "AAPL",
    "GOOGL",
    "MSFT",
    "AMZN",
    "TSLA",
    "NVDA",
    "META",
    "JPM",
    "V",
    "NFLX",
]


def create_app() -> FastAPI:
    """Assemble the application.

    The cache and market source are built here rather than in the lifespan
    handler: both router factories take the cache as an argument, and
    include_router() runs long before lifespan ever does, so a cache created
    at startup would arrive too late for the routers that need it.
    """
    cache = PriceCache()
    source = create_market_data_source(cache)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Run the market data source for the lifetime of the app."""
        await source.start(DEFAULT_TICKERS)
        yield
        await source.stop()

    app = FastAPI(title="FinAlly", lifespan=lifespan)
    app.state.price_cache = cache
    app.state.market_source = source
    app.state.db_path = DB_PATH

    app.include_router(create_health_router(cache, source))
    app.include_router(create_stream_router(cache))
    app.frontend("/", directory=STATIC_DIR, fallback="index.html")
    return app
