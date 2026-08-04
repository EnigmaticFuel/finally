"""FastAPI application assembly.

Startup order matters: initialize the database, start the market data source on
the seeded watchlist, then run the periodic snapshot task. The static file mount
is registered last so it cannot shadow the /api routes.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app import state  # noqa: E402
from app.api import chat, health, portfolio, watchlist  # noqa: E402
from app.db import get_watchlist, init_db  # noqa: E402
from app.market import PriceCache, create_market_data_source, create_stream_router  # noqa: E402
from app.services.snapshots import snapshot_task  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

price_cache = PriceCache()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    source = create_market_data_source(price_cache)
    await source.start(get_watchlist())
    state.set_market(price_cache, source)
    logger.info("Market data started: %s", source.source_name)

    async with snapshot_task():
        yield

    await source.stop()
    state.clear_market()


app = FastAPI(title="FinAlly", lifespan=lifespan)

app.include_router(health.router)
app.include_router(portfolio.router)
app.include_router(watchlist.router)
app.include_router(chat.router)
app.include_router(create_stream_router(price_cache))

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
