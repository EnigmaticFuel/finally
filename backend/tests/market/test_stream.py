"""Tests for the SSE streaming generator."""

import json

import pytest

from app.market.cache import PriceCache
from app.market.stream import _generate_events, create_stream_router


class _StubRequest:
    """Minimal stand-in for a FastAPI Request, driving disconnect after N checks."""

    client = None

    def __init__(self, disconnect_after: int):
        self._calls = 0
        self._limit = disconnect_after

    async def is_disconnected(self) -> bool:
        self._calls += 1
        return self._calls > self._limit


@pytest.mark.asyncio
class TestGenerateEvents:
    """Unit tests for _generate_events, driven directly without an ASGI server."""

    async def test_opens_with_retry_directive(self):
        cache = PriceCache()
        frames = [f async for f in _generate_events(cache, _StubRequest(0), interval=0.0)]
        assert frames[0] == "retry: 1000\n\n"

    async def test_no_event_when_the_version_is_unchanged(self):
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        frames = [f async for f in _generate_events(cache, _StubRequest(3), interval=0.0)]
        data_frames = [f for f in frames if f.startswith("data:")]
        assert len(data_frames) == 1  # one payload, then silence

    async def test_no_event_emitted_when_cache_is_empty(self):
        cache = PriceCache()
        frames = [f async for f in _generate_events(cache, _StubRequest(3), interval=0.0)]
        data_frames = [f for f in frames if f.startswith("data:")]
        assert data_frames == []

    async def test_heartbeat_arrives_in_a_quiet_market(self):
        cache = PriceCache()
        frames = [
            f
            async for f in _generate_events(cache, _StubRequest(3), interval=0.0, heartbeat=0.0)
        ]
        assert ": ping\n\n" in frames

    async def test_no_heartbeat_before_its_interval(self):
        cache = PriceCache()
        frames = [
            f
            async for f in _generate_events(
                cache, _StubRequest(3), interval=0.0, heartbeat=3600.0
            )
        ]
        assert ": ping\n\n" not in frames

    async def test_payload_is_keyed_by_ticker_and_carries_the_baseline(self):
        cache = PriceCache()
        cache.update("AAPL", 189.20)
        cache.update("AAPL", 190.50)
        frames = [f async for f in _generate_events(cache, _StubRequest(1), interval=0.0)]
        data_frames = [f for f in frames if f.startswith("data:")]
        payload = json.loads(data_frames[0].removeprefix("data: "))
        assert payload["AAPL"]["open_price"] == 189.20
        assert payload["AAPL"]["change_from_open_percent"] == pytest.approx(0.687, abs=1e-3)

    async def test_multiple_tickers_share_one_event(self):
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.update("GOOGL", 175.00)
        frames = [f async for f in _generate_events(cache, _StubRequest(1), interval=0.0)]
        data_frames = [f for f in frames if f.startswith("data:")]
        assert len(data_frames) == 1
        payload = json.loads(data_frames[0].removeprefix("data: "))
        assert set(payload.keys()) == {"AAPL", "GOOGL"}

    async def test_stops_when_client_disconnects_immediately(self):
        cache = PriceCache()
        frames = [f async for f in _generate_events(cache, _StubRequest(0), interval=0.0)]
        # Only the retry directive; the loop exits before ever reading the cache.
        assert frames == ["retry: 1000\n\n"]


class TestCreateStreamRouter:
    """The router factory must not double-register routes when called twice."""

    def test_creates_independent_routers(self):
        cache = PriceCache()
        router_a = create_stream_router(cache)
        router_b = create_stream_router(cache)
        assert router_a is not router_b
        paths_a = {route.path for route in router_a.routes}
        paths_b = {route.path for route in router_b.routes}
        assert paths_a == paths_b == {"/api/stream/prices"}
