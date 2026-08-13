"""Tests for the portfolio read seam and its valuation rule.

Every database here is a real file under tmp_path. :memory: would give each
connection its own empty database and could not exercise the schema the way the
app does.

value_portfolio is covered with genuine sqlite3.Row objects read back through
get_positions rather than hand-built stand-ins, so a column rename in queries.py
fails these tests instead of passing them.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db.connection import connect
from app.db.queries import (
    add_watchlist_ticker,
    get_positions,
    get_profile,
    get_watchlist,
    insert_snapshot,
    insert_trade,
    update_cash_balance,
    upsert_position,
)
from app.db.seed import STARTING_CASH, apply_schema, seed_fresh
from app.market import PriceCache
from app.services.portfolio import (
    get_history,
    get_portfolio,
    reset_portfolio,
    value_portfolio,
)

PRECISE_QUANTITY = 1.2345
PRECISE_PRICE = 190.5678
SPENT_CASH = 1234.56
EXTRA_TICKER = "PYPL"


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A seeded throwaway file database, closed when the test ends."""
    with connect(tmp_path / "finally.db") as connection:
        apply_schema(connection)
        seed_fresh(connection)
        yield connection


@pytest.fixture
def seeded_db(db_path: Path) -> Path:
    """A real file database carrying the standard first-launch seed."""
    with connect(db_path) as connection:
        apply_schema(connection)
        seed_fresh(connection)
    return db_path


@pytest.fixture
def loaded_db(seeded_db: Path) -> Path:
    """A used portfolio: two positions, spent cash, an added ticker, one trade.

    The pre-state is built directly rather than through a trade so these tests
    stay independent of the trade path.
    """
    with connect(seeded_db) as connection:
        upsert_position(connection, "AAPL", 5.0, 100.0)
        upsert_position(connection, "TSLA", 2.0, 250.0)
        update_cash_balance(connection, SPENT_CASH)
        add_watchlist_ticker(connection, EXTRA_TICKER)
        insert_trade(connection, "AAPL", "buy", 5.0, 100.0)
    return seeded_db


TRADE_COUNT = "SELECT COUNT(*) FROM trades"
SNAPSHOT_COUNT = "SELECT COUNT(*) FROM portfolio_snapshots"


def _count(db: Path, sql: str) -> int:
    """Run a counting query against the database.

    trades deliberately has no reader in queries.py, so a test-only count is the
    only way to prove a reset leaves the audit log alone.
    """
    with connect(db) as connection:
        return connection.execute(sql).fetchone()[0]


class TestValuePortfolio:
    """The one valuation rule, over real position rows."""

    def test_no_positions_totals_exactly_the_cash(self, conn: sqlite3.Connection) -> None:
        """An all-cash portfolio is an empty list and a total equal to the cash."""
        positions, total = value_portfolio(STARTING_CASH, get_positions(conn), {"AAPL": 190.5})

        assert positions == []
        assert total == STARTING_CASH

    def test_a_priced_position_reports_its_figures(self, conn: sqlite3.Connection) -> None:
        """Market value, P&L and P&L percent follow from quantity, cost and price."""
        upsert_position(conn, "AAPL", 10.0, 100.0)

        positions, total = value_portfolio(0.0, get_positions(conn), {"AAPL": 110.0})

        assert positions[0]["current_price"] == 110.0
        assert positions[0]["market_value"] == 1100.0
        assert positions[0]["unrealized_pnl"] == 100.0
        assert positions[0]["unrealized_pnl_percent"] == 10.0
        assert total == 1100.0

    def test_a_break_even_position_is_zero_not_null(self, conn: sqlite3.Connection) -> None:
        """A position priced at its avg_cost reports zeros and still counts."""
        upsert_position(conn, "AAPL", 2.0, 100.0)

        positions, total = value_portfolio(500.0, get_positions(conn), {"AAPL": 100.0})

        assert positions[0]["unrealized_pnl"] == 0.0
        assert positions[0]["unrealized_pnl_percent"] == 0.0
        assert total == 700.0

    def test_a_priceless_position_is_null_and_excluded(self, conn: sqlite3.Connection) -> None:
        """No price means four nulls and no contribution to the total.

        Absent must read as absent: a fabricated price is a number the user would
        make money decisions against.
        """
        upsert_position(conn, "AAPL", 10.0, 100.0)

        positions, total = value_portfolio(STARTING_CASH, get_positions(conn), {})

        assert positions[0]["current_price"] is None
        assert positions[0]["market_value"] is None
        assert positions[0]["unrealized_pnl"] is None
        assert positions[0]["unrealized_pnl_percent"] is None
        assert total == STARTING_CASH

    def test_positions_come_back_ticker_ascending(self, conn: sqlite3.Connection) -> None:
        """Insertion order does not survive; get_positions orders by ticker."""
        for ticker in ("TSLA", "AAPL", "MSFT"):
            upsert_position(conn, ticker, 1.0, 100.0)

        positions, _ = value_portfolio(0.0, get_positions(conn), {})

        assert [position["ticker"] for position in positions] == ["AAPL", "MSFT", "TSLA"]

    def test_derived_figures_are_not_rounded(self, conn: sqlite3.Connection) -> None:
        """market_value is the raw product, not the product rounded to cents.

        The client recomputes this from the SSE stream on every frame, so a
        server-side rounding would visibly disagree with the client's arithmetic.
        """
        upsert_position(conn, "AAPL", PRECISE_QUANTITY, 100.0)

        positions, _ = value_portfolio(0.0, get_positions(conn), {"AAPL": PRECISE_PRICE})

        expected = PRECISE_QUANTITY * PRECISE_PRICE
        assert positions[0]["market_value"] == expected
        assert expected != round(expected, 2)


class TestGetPortfolio:
    """The composed read: cash from the profile, positions valued live."""

    async def test_a_fresh_database_is_cash_and_nothing_else(self, seeded_db: Path) -> None:
        """Three keys, the starting cash, no positions, a total equal to the cash."""
        payload = await get_portfolio(seeded_db, PriceCache())

        assert set(payload) == {"cash_balance", "total_value", "positions"}
        assert payload["cash_balance"] == STARTING_CASH
        assert payload["positions"] == []
        assert payload["total_value"] == STARTING_CASH

    async def test_a_held_position_is_valued_from_the_cache(self, seeded_db: Path) -> None:
        """The total is cash plus the live market value of what is held."""
        with connect(seeded_db) as connection:
            upsert_position(connection, "AAPL", 2.0, 100.0)
        cache = PriceCache()
        cache.update("AAPL", 150.0)

        payload = await get_portfolio(seeded_db, cache)

        assert payload["positions"][0]["market_value"] == 300.0
        assert payload["total_value"] == STARTING_CASH + 300.0


class TestGetHistory:
    """Bounded snapshot history for the P&L chart."""

    async def test_snapshots_come_back_newest_first(self, seeded_db: Path) -> None:
        """The seed snapshot plus three more, ordered newest to oldest."""
        with connect(seeded_db) as connection:
            for value in (11000.0, 12000.0, 13000.0):
                insert_snapshot(connection, value)

        rows = await get_history(seeded_db)

        assert set(rows[0]) == {"total_value", "recorded_at"}
        assert [row["total_value"] for row in rows] == [13000.0, 12000.0, 11000.0, STARTING_CASH]

    async def test_limit_keeps_the_newest(self, seeded_db: Path) -> None:
        """A limit of one against four snapshots returns the newest one only."""
        with connect(seeded_db) as connection:
            for value in (11000.0, 12000.0, 13000.0):
                insert_snapshot(connection, value)

        rows = await get_history(seeded_db, limit=1)

        assert len(rows) == 1
        assert rows[0]["total_value"] == 13000.0

    async def test_a_recorded_at_fed_back_as_since_selects_that_row_and_newer(
        self, seeded_db: Path
    ) -> None:
        """The timestamp round-trips verbatim, so no second format is introduced.

        Nothing in the service parses or reformats recorded_at. The SQL compares
        `since` as a plain string, so a differently formatted but equally valid
        ISO 8601 string would not sort against the stored one.
        """
        with connect(seeded_db) as connection:
            for value in (11000.0, 12000.0, 13000.0):
                insert_snapshot(connection, value)
        rows = await get_history(seeded_db)
        boundary = rows[1]["recorded_at"]

        selected = await get_history(seeded_db, since=boundary)

        assert [row["recorded_at"] for row in selected][:2] == [
            rows[0]["recorded_at"],
            rows[1]["recorded_at"],
        ]
        assert all(row["recorded_at"] >= boundary for row in selected)


class TestResetPortfolio:
    """Reset returns the portfolio, and only the portfolio, to the start."""

    async def test_cash_returns_and_every_position_goes(self, loaded_db: Path) -> None:
        """The starting balance is back and nothing is held."""
        await reset_portfolio(loaded_db)

        with connect(loaded_db) as connection:
            assert get_profile(connection)["cash_balance"] == STARTING_CASH
            assert get_positions(connection) == []

    async def test_the_watchlist_survives_untouched(self, loaded_db: Path) -> None:
        """Curated tickers are not the user's portfolio and are not reset.

        This is also what proves the seed helper was not reused: seed_fresh
        writes the ten defaults, which would have dropped the added ticker back
        out of a set comparison only by luck, and would have re-added any the
        user had removed.
        """
        with connect(loaded_db) as connection:
            before = {row["ticker"] for row in get_watchlist(connection)}

        await reset_portfolio(loaded_db)

        with connect(loaded_db) as connection:
            after = {row["ticker"] for row in get_watchlist(connection)}
        assert after == before
        assert EXTRA_TICKER in after

    async def test_the_trades_log_is_not_written_to(self, loaded_db: Path) -> None:
        """A reset is not a sale, so no synthetic row joins the audit log."""
        before = _count(loaded_db, TRADE_COUNT)

        await reset_portfolio(loaded_db)

        assert _count(loaded_db, TRADE_COUNT) == before

    async def test_one_snapshot_records_the_step(self, loaded_db: Path) -> None:
        """History shows the drop immediately rather than a gap for 30 seconds."""
        before = _count(loaded_db, SNAPSHOT_COUNT)

        await reset_portfolio(loaded_db)

        assert _count(loaded_db, SNAPSHOT_COUNT) == before + 1
        assert (await get_history(loaded_db, limit=1))[0]["total_value"] == STARTING_CASH

    async def test_the_payload_is_the_portfolio_shape(self, loaded_db: Path) -> None:
        """The same three keys GET /api/portfolio returns, so a refetch is uniform."""
        payload = await reset_portfolio(loaded_db)

        assert payload == {
            "cash_balance": STARTING_CASH,
            "total_value": STARTING_CASH,
            "positions": [],
        }

    async def test_a_second_reset_is_safe(self, loaded_db: Path) -> None:
        """Resetting twice returns the same body and appends one more snapshot.

        The unchanged-value skip belongs to the 30-second task alone, so a second
        row at the same value is correct here.
        """
        first = await reset_portfolio(loaded_db)
        before = _count(loaded_db, SNAPSHOT_COUNT)

        second = await reset_portfolio(loaded_db)

        assert second == first
        assert _count(loaded_db, SNAPSHOT_COUNT) == before + 1

    async def test_a_failure_part_way_through_commits_nothing(
        self, loaded_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One transaction covers the deletes, the cash write and the snapshot."""

        def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("snapshot write failed")

        monkeypatch.setattr("app.services.portfolio.insert_snapshot", boom)

        with pytest.raises(RuntimeError):
            await reset_portfolio(loaded_db)

        with connect(loaded_db) as connection:
            assert len(get_positions(connection)) == 2
            assert get_profile(connection)["cash_balance"] == SPENT_CASH
