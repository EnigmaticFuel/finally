"""Tests for the trade execution seam."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db.connection import connect
from app.db.seed import STARTING_CASH, apply_schema, seed_fresh
from app.market import PriceCache
from app.services import TradeError, execute_trade

FILL_PRICE = 100.0
QUANTITY = 3.0
UNWATCHED = "PYPL"


@pytest.fixture
def seeded_db(db_path: Path) -> Path:
    """A real file database carrying the standard first-launch seed."""
    with connect(db_path) as conn:
        apply_schema(conn)
        seed_fresh(conn)
    return db_path


@pytest.fixture
def cache() -> PriceCache:
    """A cache holding one price, so no test waits on a live feed."""
    price_cache = PriceCache()
    price_cache.update(UNWATCHED, FILL_PRICE)
    return price_cache


def _rows(db: Path, sql: str, *args: object) -> list[sqlite3.Row]:
    with connect(db) as conn:
        return conn.execute(sql, args).fetchall()


async def test_buy_fills_and_lands_everywhere(seeded_db: Path, cache: PriceCache) -> None:
    """One buy debits cash, creates the position, watches the ticker, snapshots.

    All four in one assertion block deliberately: they happen inside a single
    transaction, so proving them separately would not prove they are atomic.
    """
    before = len(_rows(seeded_db, "SELECT id FROM portfolio_snapshots"))

    result = await execute_trade(seeded_db, cache, UNWATCHED, "buy", QUANTITY)

    assert result.fill_price == FILL_PRICE
    assert result.cash_balance == STARTING_CASH - FILL_PRICE * QUANTITY

    position = _rows(seeded_db, "SELECT quantity, avg_cost FROM positions WHERE ticker = ?", UNWATCHED)
    assert len(position) == 1
    assert position[0]["quantity"] == QUANTITY
    assert position[0]["avg_cost"] == FILL_PRICE

    watched = _rows(seeded_db, "SELECT ticker FROM watchlist WHERE ticker = ?", UNWATCHED)
    assert len(watched) == 1, "a traded ticker joins the watchlist (PORT-07)"

    after = len(_rows(seeded_db, "SELECT id FROM portfolio_snapshots"))
    assert after == before + 1, "every trade writes exactly one snapshot (PORT-11)"


async def test_stored_cash_matches_the_reported_balance(
    seeded_db: Path, cache: PriceCache
) -> None:
    """The balance in the response is the balance in the database."""
    result = await execute_trade(seeded_db, cache, UNWATCHED, "buy", QUANTITY)

    stored = _rows(seeded_db, "SELECT cash_balance FROM users_profile")[0]["cash_balance"]
    assert stored == pytest.approx(result.cash_balance)


async def test_rejected_buy_rolls_the_whole_unit_back(
    seeded_db: Path, cache: PriceCache
) -> None:
    """A trade the cash cannot cover leaves no watchlist row, no cash change, no snapshot.

    The watchlist row is the sharp end: add_watchlist_ticker runs before the cash
    guard, so only the rollback keeps a rejected trade from leaving an orphan.
    """
    snapshots_before = len(_rows(seeded_db, "SELECT id FROM portfolio_snapshots"))
    unaffordable = STARTING_CASH / FILL_PRICE + 1

    with pytest.raises(TradeError, match="Insufficient cash"):
        await execute_trade(seeded_db, cache, UNWATCHED, "buy", unaffordable)

    assert _rows(seeded_db, "SELECT ticker FROM watchlist WHERE ticker = ?", UNWATCHED) == []
    assert _rows(seeded_db, "SELECT ticker FROM positions") == []
    assert _rows(seeded_db, "SELECT cash_balance FROM users_profile")[0][0] == STARTING_CASH
    assert len(_rows(seeded_db, "SELECT id FROM portfolio_snapshots")) == snapshots_before
