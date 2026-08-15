"""FastAPI application assembly."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.health import create_health_router
from app.api.portfolio import create_portfolio_router
from app.api.watchlist import create_watchlist_router
from app.config import DB_PATH
from app.market import PriceCache, create_market_data_source, create_stream_router
from app.services.snapshots import snapshot_loop
from app.services.watchlist import startup_tickers

# Absolute, because app.frontend() resolves `directory` against the process
# CWD and its check_dir="auto" raises at app-creation time. A relative path
# therefore breaks the whole suite at collection depending on where the
# process was launched from, not just the one test that fetches the page.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

logger = logging.getLogger(__name__)


def _log_if_failed(task: asyncio.Task[None]) -> None:
    """Report a snapshot task that died, at the moment it dies.

    A recorder that fails silently renders as a flat P&L chart, which reads as an
    idle portfolio rather than a broken writer. Reporting here rather than at
    shutdown is what lets an operator act while the app is still up.

    The cancelled() test comes first and short-circuits, because exception()
    re-raises on a cancelled task. That ordering is what keeps every ordinary
    shutdown silent: a cancelled task is not a failed one.
    """
    if not task.cancelled() and task.exception() is not None:
        logger.error("Snapshot loop stopped: %s", task.exception())


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
        """Run the market data source and the snapshot recorder for the app's life.

        The streamed tickers are the persisted watchlist, read through
        startup_tickers. They are the same rows the API serves, so a ticker the
        user added in an earlier run gets a feed, and there is only one list to
        disagree with itself.

        This lifespan owns both background tasks and cancels both here, so
        nothing outlives the app. The snapshot task stops first because it reads
        prices from the cache the source writes: cancelling it before the source
        leaves no window where a live recorder reads a cache whose producer has
        already gone. The path comes off this app's own state, which is what
        lets a test fixture point the recorder at a throwaway database.
        """
        await source.start(await startup_tickers(app.state.db_path))
        task = asyncio.create_task(snapshot_loop(app.state.db_path, cache), name="snapshot-loop")
        task.add_done_callback(_log_if_failed)
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await source.stop()

    app = FastAPI(title="FinAlly", lifespan=lifespan)
    register_exception_handlers(app)
    app.state.price_cache = cache
    app.state.market_source = source
    app.state.db_path = DB_PATH

    app.include_router(create_health_router(cache, source))
    app.include_router(create_portfolio_router(cache, source))
    app.include_router(create_stream_router(cache))
    app.include_router(create_watchlist_router(cache, source))
    app.frontend("/", directory=STATIC_DIR, fallback="index.html")
    return app
