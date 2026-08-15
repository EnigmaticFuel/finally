"""Tests for the assembled FastAPI application."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.connection import connect, ensure_initialized
from app.db.queries import get_snapshots
from app.db.seed import DEFAULT_TICKERS
from app.main import create_app
from app.market import PriceCache

STARTUP_TIMEOUT = 15.0
HEALTH_KEYS = {"status", "market_source", "tickers_cached", "newest_price_age_seconds"}


def _free_port() -> int:
    """Bind port 0 so the OS picks an unused port, then release it."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _running_task_names() -> set[str]:
    """Names of the asyncio tasks still running, for lifecycle assertions."""
    return {task.get_name() for task in asyncio.all_tasks()}


@pytest.fixture
def live_app(app: FastAPI) -> Iterator[str]:
    """Serve the app from a real uvicorn server, yielding its base URL.

    A real server rather than TestClient or httpx.ASGITransport: both buffer
    the response body to completion before returning, and the SSE generator
    never completes, so both hang before even the headers arrive.
    """
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
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
    assert set(health.json()) == HEALTH_KEYS

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


def test_create_app_builds_cache_before_routers(app: FastAPI) -> None:
    """Both routers were registered against a cache that already existed.

    Paths come from the OpenAPI schema rather than app.routes: since FastAPI
    0.141 include_router() appends an _IncludedRouter wrapper instead of
    flattening its routes, so app.routes no longer lists them directly.
    """
    assert isinstance(app.state.price_cache, PriceCache)
    paths = set(app.openapi()["paths"])
    assert "/api/health" in paths
    assert "/api/stream/prices" in paths


async def test_lifespan_starts_and_stops_source(app: FastAPI) -> None:
    """Lifespan owns both background tasks: started on enter, gone on exit.

    The expected tickers are sorted rather than in seed order, and that is the
    point: the feed is started from the persisted watchlist rows, and
    get_watchlist orders ascending by ticker. Seed order is no longer what the
    source holds, which is itself the proof that the streamed set and the
    watchlist the user sees come from one place and cannot diverge.
    """
    source = app.state.market_source
    assert source.get_tickers() == []

    async with app.router.lifespan_context(app):
        assert source.get_tickers() == sorted(DEFAULT_TICKERS)
        assert "simulator-loop" in _running_task_names()
        assert "snapshot-loop" in _running_task_names()

    assert "simulator-loop" not in _running_task_names()
    assert "snapshot-loop" not in _running_task_names()
    assert app.state.market_source is source


async def test_lifespan_records_no_snapshot_on_a_short_life(
    app: FastAPI, db_path: Path
) -> None:
    """An app that lives for milliseconds writes nothing: the loop sleeps first.

    ensure_initialized is belt-and-braces rather than required setup: the
    lifespan now reads the watchlist through startup_tickers, and run_db seeds on
    first touch, so the database exists either way. The assertion of exactly one
    snapshot row holds under both, which is the thing being pinned - the sleeping
    snapshot task adds nothing of its own.
    """
    ensure_initialized(db_path)

    async with app.router.lifespan_context(app):
        pass

    with connect(db_path) as conn:
        assert len(get_snapshots(conn)) == 1


def test_cache_via_dependency(app: FastAPI) -> None:
    """The routers read the cache exposed on app.state, and no singleton exists."""
    app.state.price_cache.update("AAPL", 190.50)
    payload = TestClient(app).get("/api/health").json()
    assert payload["tickers_cached"] == 1

    assert create_app().state.price_cache is not app.state.price_cache


def test_api_not_shadowed(live_app: str) -> None:
    """API routes win over the SPA fallback for every JSON client."""
    health = httpx.get(f"{live_app}/api/health", timeout=10)
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    explicit_json = httpx.get(
        f"{live_app}/api/nope", headers={"Accept": "application/json"}, timeout=10
    )
    assert explicit_json.status_code == 404
    assert explicit_json.headers["content-type"].startswith("application/json")

    any_accept = httpx.get(f"{live_app}/api/nope", headers={"Accept": "*/*"}, timeout=10)
    assert any_accept.status_code == 404
    assert any_accept.headers["content-type"].startswith("application/json")

    # Correct behavior, not a defect: the fallback is Accept-gated, and fetch()
    # sends */*, so the frontend's own calls always land in the JSON rows above.
    browser_navigation = httpx.get(
        f"{live_app}/api/nope", headers={"Accept": "text/html"}, timeout=10
    )
    assert browser_navigation.status_code == 200
    assert browser_navigation.headers["content-type"].startswith("text/html")


def test_concurrent_health_and_stream(live_app: str) -> None:
    """A held-open SSE stream stalls neither health nor route precedence."""
    with httpx.stream("GET", f"{live_app}/api/stream/prices", timeout=10) as stream:
        assert stream.status_code == 200
        assert next(stream.iter_lines()) == "retry: 1000"

        health = httpx.get(f"{live_app}/api/health", timeout=10)
        assert health.status_code == 200
        assert set(health.json()) == HEALTH_KEYS

        missing = httpx.get(
            f"{live_app}/api/nope", headers={"Accept": "application/json"}, timeout=10
        )
        assert missing.status_code == 404
        assert missing.headers["content-type"].startswith("application/json")
