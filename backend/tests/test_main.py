"""Tests for the assembled FastAPI application."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn

from app.main import create_app

STARTUP_TIMEOUT = 15.0


def _free_port() -> int:
    """Bind port 0 so the OS picks an unused port, then release it."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def live_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Serve create_app() from a real uvicorn server, yielding its base URL.

    A real server rather than TestClient or httpx.ASGITransport: both buffer
    the response body to completion before returning, and the SSE generator
    never completes, so both hang before even the headers arrive.

    MASSIVE_API_KEY is cleared so a developer holding a real key does not have
    this test poll the live Massive API.
    """
    monkeypatch.setenv("MASSIVE_API_KEY", "")

    port = _free_port()
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + STARTUP_TIMEOUT
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start within %.0fs" % STARTUP_TIMEOUT)
        time.sleep(0.05)

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10)


def test_spine_end_to_end(live_app: str) -> None:
    """Health, the price stream and the static frontend all answer on one app."""
    health = httpx.get(f"{live_app}/api/health", timeout=10)
    assert health.status_code == 200
    assert set(health.json()) == {
        "status",
        "market_source",
        "tickers_cached",
        "newest_price_age_seconds",
    }

    frames: list[str] = []
    with httpx.stream("GET", f"{live_app}/api/stream/prices", timeout=10) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.strip():
                frames.append(line)
            if len(frames) >= 2:
                break
    assert frames[0] == "retry: 1000"
    assert any(frame.startswith("data: ") for frame in frames)

    index = httpx.get(f"{live_app}/", timeout=10)
    assert index.status_code == 200
    assert index.headers["content-type"].startswith("text/html")
