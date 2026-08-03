"""SSE streaming endpoint for live price updates."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

logger = logging.getLogger(__name__)

POLL_INTERVAL = 0.5  # How often the generator looks at the cache
HEARTBEAT_INTERVAL = 15.0  # Comment frame cadence, price activity or not


def create_stream_router(price_cache: PriceCache) -> APIRouter:
    """Build the /api/stream router bound to a specific cache.

    The router is created inside the factory, not at module level, so calling
    this twice (an app plus a test app) does not register the route twice.
    """
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        """SSE endpoint for live price updates.

        Streams all tracked ticker prices every ~500ms. The client connects
        with EventSource and receives events in the format:

            data: {"AAPL": {"ticker": "AAPL", "price": 190.50, ...}, ...}

        Includes a retry directive so the browser auto-reconnects on
        disconnection (EventSource built-in behavior).
        """
        return StreamingResponse(
            _generate_events(price_cache, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering if proxied
            },
        )

    return router


async def _generate_events(
    price_cache: PriceCache,
    request: Request,
    interval: float = POLL_INTERVAL,
    heartbeat: float = HEARTBEAT_INTERVAL,
) -> AsyncGenerator[str, None]:
    """Yield SSE frames until the client disconnects.

    Emits one data event carrying every tracked ticker, keyed by symbol, and
    only when the cache version has moved. A heartbeat comment goes out every
    `heartbeat` seconds regardless, so silence is legible to the frontend.
    """
    client = request.client.host if request.client else "unknown"
    logger.info("SSE client connected: %s", client)

    # Tell the client to retry after 1 second if the connection drops
    yield "retry: 1000\n\n"

    last_version = -1
    last_beat = time.monotonic()

    try:
        while True:
            if await request.is_disconnected():
                logger.info("SSE client disconnected: %s", client)
                break

            version = price_cache.version
            if version != last_version:
                last_version = version
                prices = price_cache.get_all()
                if prices:
                    payload = {ticker: update.to_dict() for ticker, update in prices.items()}
                    yield f"data: {json.dumps(payload)}\n\n"

            now = time.monotonic()
            if now - last_beat >= heartbeat:
                yield ": ping\n\n"
                last_beat = now

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled: %s", client)
        raise
