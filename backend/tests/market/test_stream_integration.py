"""SSE integration tests driving the stream over real HTTP."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from app.market import PriceCache, create_stream_router
from app.market.stream import _generate_events

STARTUP_TIMEOUT = 15.0


def _free_port() -> int:
    """Bind port 0 so the OS picks an unused port, then release it."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _next_data_frame(lines: Iterator[str]) -> str:
    """Advance a line iterator to the next data frame."""
    for line in lines:
        if line.startswith("data: "):
            return line
    raise AssertionError("stream ended without a data frame")


@pytest.fixture
def sse_server() -> Iterator[tuple[str, PriceCache]]:
    """Serve the SSE router from a real uvicorn server.

    The cache is seeded directly rather than by running a simulator: these
    tests are about the transport, and a hand-seeded cache makes the expected
    frame contents exact. The cache is yielded alongside the URL so a test can
    drive a fresh frame on demand.

    TestClient and httpx.ASGITransport both buffer the response body to
    completion, and this generator never completes, so neither can be used.
    """
    cache = PriceCache()
    cache.update("AAPL", 190.50)

    app = FastAPI()
    app.include_router(create_stream_router(cache))

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + STARTUP_TIMEOUT
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start within %.0fs" % STARTUP_TIMEOUT)
        time.sleep(0.05)

    yield f"http://127.0.0.1:{port}/api/stream/prices", cache

    server.should_exit = True
    thread.join(timeout=10)


class TestStreamOverHttp:
    """The SSE endpoint as a browser actually reaches it."""

    def test_stream_opens_and_carries_a_price_frame(
        self, sse_server: tuple[str, PriceCache]
    ) -> None:
        """The stream opens as event-stream, retries after 1s, and names the ticker."""
        url, _ = sse_server
        with httpx.stream("GET", url, timeout=10) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            lines = response.iter_lines()
            assert next(lines) == "retry: 1000"
            assert "AAPL" in _next_data_frame(lines)

    def test_two_clients_stream_independently(self, sse_server: tuple[str, PriceCache]) -> None:
        """Each client gets its own frames; one disconnecting leaves the other live."""
        url, cache = sse_server
        with httpx.stream("GET", url, timeout=10) as first:
            first_lines = first.iter_lines()
            assert "AAPL" in _next_data_frame(first_lines)

            with httpx.stream("GET", url, timeout=10) as second:
                assert second.status_code == 200
                assert "AAPL" in _next_data_frame(second.iter_lines())

            # The second client is closed here. A new price proves the first
            # is still being served rather than torn down alongside it.
            cache.update("AAPL", 191.25)
            assert "191.25" in _next_data_frame(first_lines)


class TestHeartbeat:
    """The comment frame that keeps a quiet stream legible."""

    async def test_heartbeat_is_emitted(self) -> None:
        """A stream with no price movement still emits a ping."""

        class FakeRequest:
            """Stand-in for Request: never disconnects, has no client."""

            client = None

            async def is_disconnected(self) -> bool:
                return False

        cache = PriceCache()
        cache.update("AAPL", 190.50)

        # Driven directly with a short heartbeat: the real cadence is 15s, and
        # waiting that long does not belong in a unit suite.
        frames: list[str] = []
        events = _generate_events(cache, FakeRequest(), interval=0.01, heartbeat=0.05)
        async for frame in events:
            frames.append(frame)
            if len(frames) >= 3:
                break
        await events.aclose()

        assert any(frame.startswith(": ping") for frame in frames)
