"""Tests for the watchlist seam: reading, adding and removing.

Every database here is a real file under tmp_path, seeded lazily by run_db the
way production seeds it.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from app.db.connection import run_db, writing
from app.db.queries import upsert_position
from app.db.seed import DEFAULT_TICKERS
from app.market import PriceCache, create_market_data_source
from app.market.cache import HISTORY_INTERVAL_SECONDS, HISTORY_POINTS
from app.services.errors import Conflict, NotFound, TradeError
from app.services.watchlist import add, quote, read_watchlist, remove, startup_tickers

from .conftest import RecordingSource

HELD = "AAPL"
UNWATCHED = "PYPL"
NEVER_WATCHED = "ZZZZ"
PRICE = 190.50


def _hold_position(conn: sqlite3.Connection, ticker: str) -> None:
    """Give the user a position, the way a filled trade would."""
    with writing(conn):
        upsert_position(conn, ticker, 10.0, PRICE)


def _spaced_history(cache: PriceCache, ticker: str, points: int) -> float:
    """Push `points` prices far enough apart that every one is recorded.

    _record_history skips a point closer than HISTORY_INTERVAL_SECONDS to the
    last one, so a tight loop would record exactly one.
    """
    base = 1_000_000.0
    price = 0.0
    for index in range(points):
        price = 100.0 + index
        cache.update(ticker, price, timestamp=base + HISTORY_INTERVAL_SECONDS * index)
    return price


class TestQuote:
    """The one null rule, and the numbers passed through untouched."""

    def test_a_ticker_the_cache_never_saw_is_null_not_zero(self) -> None:
        """No price means null on every numeric field and an empty history."""
        result = quote(PriceCache(), HELD)
        assert result.ticker == HELD
        assert result.price is None
        assert result.open_price is None
        assert result.change_from_open_percent is None
        assert result.history == []

    def test_price_and_open_price_come_from_the_cache(self) -> None:
        """Both numbers are whatever PriceCache holds, not a recomputation."""
        cache = PriceCache()
        cache.update(HELD, PRICE)
        result = quote(cache, HELD)
        assert result.price == cache.get_price(HELD)
        assert result.open_price == cache.get(HELD).open_price

    def test_a_ticker_at_its_open_reports_zero_not_none(self) -> None:
        """A flat ticker is 0.0; null is reserved for having no price at all."""
        cache = PriceCache()
        cache.update(HELD, PRICE)
        result = quote(cache, HELD)
        assert result.change_from_open_percent == 0.0
        assert result.change_from_open_percent is not None

    def test_change_from_open_is_the_price_update_property(self) -> None:
        """The percentage is read from PriceUpdate, so there is no second rule."""
        cache = PriceCache()
        cache.update(HELD, PRICE)
        cache.update(HELD, PRICE * 1.05)
        assert quote(cache, HELD).change_from_open_percent == (
            cache.get(HELD).change_from_open_percent
        )

    def test_history_is_capped_oldest_first(self) -> None:
        """Seventy spaced updates leave at most sixty points, newest last."""
        cache = PriceCache()
        newest = _spaced_history(cache, HELD, HISTORY_POINTS + 10)
        history = quote(cache, HELD).history
        assert len(history) == HISTORY_POINTS
        assert history[-1] == newest
        assert history == sorted(history), "prices rose, so oldest first means ascending"


class TestReadWatchlist:
    """The watchlist is database state, rendered with whatever the cache knows."""

    async def test_returns_the_seeded_tickers_ascending(self, db_path: Path) -> None:
        """Ordering comes from get_watchlist, and UNIQUE makes a tie impossible."""
        rows = await read_watchlist(db_path, PriceCache())
        assert [row.ticker for row in rows] == sorted(DEFAULT_TICKERS)

    async def test_a_watched_ticker_with_no_price_is_present_with_nulls(
        self, db_path: Path
    ) -> None:
        """A priceless ticker is listed, never filtered out and never zeroed."""
        rows = await read_watchlist(db_path, PriceCache())
        assert len(rows) == len(DEFAULT_TICKERS)
        assert all(row.price is None and row.history == [] for row in rows)

    async def test_a_cached_ticker_carries_its_live_price(self, db_path: Path) -> None:
        """Only the ticker the cache knows about gets a number."""
        cache = PriceCache()
        cache.update(HELD, PRICE)
        rows = {row.ticker: row for row in await read_watchlist(db_path, cache)}
        assert rows[HELD].price == PRICE
        assert rows["GOOGL"].price is None

    async def test_an_empty_watchlist_reads_as_an_empty_list(self, db_path: Path) -> None:
        """Removing everything leaves a list, not an error."""
        for ticker in DEFAULT_TICKERS:
            await remove(db_path, ticker)
        assert await read_watchlist(db_path, PriceCache()) == []


class TestAdd:
    """Adding: the shared ticker rule, the durable write, then the feed."""

    async def test_a_lowercase_symbol_is_stored_uppercased(
        self, db_path: Path, recording_source: RecordingSource
    ) -> None:
        """The normalized form is what is stored and what the caller is told."""
        entry = await add(db_path, recording_source, UNWATCHED.lower())
        assert entry.ticker == UNWATCHED
        assert entry.added is True

        rows = await read_watchlist(db_path, PriceCache())
        assert UNWATCHED in [row.ticker for row in rows]

    async def test_adding_registers_the_ticker_with_the_source(
        self, db_path: Path, recording_source: RecordingSource
    ) -> None:
        """WATCH-03: the running feed learns about the ticker."""
        await add(db_path, recording_source, UNWATCHED)
        assert recording_source.added == [UNWATCHED]

    async def test_adding_an_already_watched_ticker_is_not_an_error(
        self, db_path: Path, recording_source: RecordingSource
    ) -> None:
        """added is False, and re-registering repairs an earlier failed one."""
        entry = await add(db_path, recording_source, HELD)
        assert entry.added is False
        assert recording_source.added == [HELD]

    async def test_an_invalid_symbol_never_reaches_the_database_or_the_source(
        self, db_path: Path, recording_source: RecordingSource
    ) -> None:
        """normalize_ticker runs first, so a malformed symbol does no I/O.

        The class is asserted as TradeError rather than ValueError deliberately.
        TradeError subclasses ValueError, so the looser assertion passed both
        before and after the seam translation and discriminated nothing.
        """
        with pytest.raises(TradeError, match="Invalid ticker symbol"):
            await add(db_path, recording_source, "toolong")

        assert recording_source.added == []
        rows = await read_watchlist(db_path, PriceCache())
        assert len(rows) == len(DEFAULT_TICKERS)

    async def test_a_source_failure_leaves_the_watchlist_row_in_place(
        self, db_path: Path, failing_source: RecordingSource
    ) -> None:
        """D-09: the durable write happens first, so registration can fail safely."""
        with pytest.raises(RuntimeError):
            await add(db_path, failing_source, UNWATCHED)

        rows = await read_watchlist(db_path, PriceCache())
        assert UNWATCHED in [row.ticker for row in rows]

    async def test_a_started_simulator_produces_a_price_for_an_added_ticker(
        self, db_path: Path
    ) -> None:
        """The end of WATCH-03: a real source, a real price, no restart."""
        cache = PriceCache()
        source = create_market_data_source(cache)
        await source.start([HELD])
        try:
            await add(db_path, source, UNWATCHED)
            assert cache.get_price(UNWATCHED) is not None
        finally:
            await source.stop()


class TestRemove:
    """Removing: 409 before 404, both inside one transaction."""

    async def test_removing_a_watched_unheld_ticker_deletes_the_row(
        self, db_path: Path
    ) -> None:
        """The plain success path returns None."""
        assert await remove(db_path, HELD) is None

        rows = await read_watchlist(db_path, PriceCache())
        assert HELD not in [row.ticker for row in rows]

    async def test_a_lowercase_symbol_removes_the_uppercase_row(self, db_path: Path) -> None:
        """Equality is byte equality after strip and uppercase."""
        await remove(db_path, HELD.lower())
        rows = await read_watchlist(db_path, PriceCache())
        assert HELD not in [row.ticker for row in rows]

    async def test_removing_a_held_ticker_is_rejected_and_changes_nothing(
        self, db_path: Path
    ) -> None:
        """WATCH-05: the 409 names the ticker and the row survives the rollback."""
        await run_db(db_path, _hold_position, HELD)

        with pytest.raises(Conflict, match=HELD):
            await remove(db_path, HELD)

        rows = await read_watchlist(db_path, PriceCache())
        assert HELD in [row.ticker for row in rows]

    async def test_removing_an_unwatched_ticker_raises_not_found(self, db_path: Path) -> None:
        """WATCH-06: a well-formed symbol naming no row is a 404."""
        with pytest.raises(NotFound, match=NEVER_WATCHED):
            await remove(db_path, NEVER_WATCHED)

    async def test_a_second_removal_raises_not_found(self, db_path: Path) -> None:
        """Removal is not status-idempotent: a row is reported removed once."""
        await remove(db_path, HELD)
        with pytest.raises(NotFound, match=HELD):
            await remove(db_path, HELD)

    async def test_two_concurrent_removals_resolve_to_one_success(self, db_path: Path) -> None:
        """BEGIN IMMEDIATE makes the check-and-delete a single winner."""
        results = await asyncio.gather(
            remove(db_path, HELD), remove(db_path, HELD), return_exceptions=True
        )
        assert sum(result is None for result in results) == 1
        assert sum(isinstance(result, NotFound) for result in results) == 1

    async def test_an_invalid_symbol_is_rejected_before_any_lookup(self, db_path: Path) -> None:
        """A malformed symbol cannot name a row, so it is a 400 not a 404.

        Asserted as TradeError for the same reason as its counterpart on add:
        TradeError subclasses ValueError, so the looser assertion could not tell
        whether the translation at the seam had happened at all.
        """
        with pytest.raises(TradeError, match="Invalid ticker symbol"):
            await remove(db_path, "toolong")


class TestStartupTickers:
    """The persisted watchlist, read the way the lifespan starts the feed from it."""

    async def test_a_fresh_database_returns_the_seeded_tickers_ascending(
        self, db_path: Path
    ) -> None:
        """run_db seeds on first touch, so a first launch reads the ten straight back.

        The expectation is sorted rather than a literal list because get_watchlist
        orders ascending by ticker, which is not the seed order.
        """
        assert await startup_tickers(db_path) == sorted(DEFAULT_TICKERS)

    async def test_a_user_added_ticker_comes_back_with_the_defaults(
        self, db_path: Path, recording_source: RecordingSource
    ) -> None:
        """A ticker added in an earlier run is in the list the next boot starts from."""
        await add(db_path, recording_source, UNWATCHED)

        tickers = await startup_tickers(db_path)

        assert UNWATCHED in tickers
        assert tickers == sorted([*DEFAULT_TICKERS, UNWATCHED])

    async def test_an_emptied_watchlist_falls_back_without_re_seeding(
        self, db_path: Path
    ) -> None:
        """The fallback feeds the simulator; it does not restore the user's rows.

        A user who empties their watchlist keeps it empty across restarts, which
        is why the second assertion matters as much as the first: startup reads
        and never writes.
        """
        for ticker in DEFAULT_TICKERS:
            await remove(db_path, ticker)

        assert await startup_tickers(db_path) == list(DEFAULT_TICKERS)
        assert await read_watchlist(db_path, PriceCache()) == []

    async def test_the_returned_values_are_plain_strings(self, db_path: Path) -> None:
        """The source is handed symbols, not sqlite3.Row objects."""
        assert all(isinstance(ticker, str) for ticker in await startup_tickers(db_path))
