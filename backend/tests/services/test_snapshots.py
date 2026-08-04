"""The snapshot writer and its 30-second background loop."""

import asyncio

import pytest

from app.db import get_snapshots
from app.services import snapshots
from app.services.snapshots import record_now, snapshot_task
from app.services.trading import execute_trade

pytestmark = pytest.mark.usefixtures("market")


def test_an_unchanged_value_is_skipped():
    before = len(get_snapshots())
    record_now()
    record_now()

    assert len(get_snapshots()) == before


def test_a_price_move_with_no_position_is_skipped(market):
    """Prices move constantly; with no holdings the total value does not."""
    market.set_price("AAPL", 200.0)
    record_now()

    assert len(get_snapshots()) == 1


async def test_a_moved_position_is_written(market):
    await execute_trade("AAPL", "buy", 10)
    before = len(get_snapshots())

    market.set_price("AAPL", 200.0)
    record_now()

    assert len(get_snapshots()) == before + 1
    assert get_snapshots()[0]["total_value"] == 10100.0


def test_force_writes_an_unchanged_value():
    before = len(get_snapshots())
    record_now(force=True)

    assert len(get_snapshots()) == before + 1


def test_snapshots_carry_an_iso_timestamp():
    record_now(force=True)
    assert get_snapshots()[0]["recorded_at"].endswith("Z")


async def test_the_loop_records_on_each_interval(market, monkeypatch):
    monkeypatch.setattr(snapshots, "SNAPSHOT_INTERVAL_SECONDS", 0.01)
    market.set_price("AAPL", 200.0)
    await execute_trade("AAPL", "buy", 10)
    before = len(get_snapshots())

    async with snapshot_task():
        market.set_price("AAPL", 300.0)
        await asyncio.sleep(0.05)

    assert len(get_snapshots()) > before


async def test_the_loop_survives_a_failing_write(monkeypatch):
    """One bad write must not silence the chart for the rest of the session."""
    monkeypatch.setattr(snapshots, "SNAPSHOT_INTERVAL_SECONDS", 0.01)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database is locked")

    monkeypatch.setattr(snapshots, "record_now", flaky)

    async with snapshot_task():
        await asyncio.sleep(0.05)

    assert len(calls) > 1


async def test_the_loop_stops_cleanly_on_shutdown(monkeypatch):
    monkeypatch.setattr(snapshots, "SNAPSHOT_INTERVAL_SECONDS", 0.01)

    async with snapshot_task():
        await asyncio.sleep(0.02)

    after = len(get_snapshots())
    await asyncio.sleep(0.05)
    assert len(get_snapshots()) == after
