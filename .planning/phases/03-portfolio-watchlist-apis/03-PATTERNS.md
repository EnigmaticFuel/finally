# Phase 3: Portfolio & Watchlist APIs - Pattern Map

**Mapped:** 2026-08-12
**Files analyzed:** 17 new/modified files
**Analogs found:** 14 / 17

Every excerpt below is verbatim from the live tree, with file path and line numbers. Where no
analog exists it is stated as such rather than invented.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/services/__init__.py` | package init | — | `backend/app/db/__init__.py` | exact (structural sibling) |
| `backend/app/services/errors.py` | utility (exception taxonomy) | — | **none** — see No Analog Found | none |
| `backend/app/services/portfolio.py` | service | CRUD (read) + pure transform | `backend/app/db/queries.py` (plain-def-over-conn) + `backend/app/market/cache.py` (pure read surface) | partial |
| `backend/app/services/trading.py` | service | read-modify-write in one transaction | `backend/app/db/connection.py::writing` + `queries.py::upsert_position` | partial |
| `backend/app/services/watchlist.py` | service | CRUD + side-effect on the market source | `backend/app/db/queries.py::add_watchlist_ticker` / `remove_watchlist_ticker` | partial |
| `backend/app/services/snapshots.py` | service (background writer) | timer-driven read-modify-write | `backend/app/services/trading.py` (built in this phase by `03-01`/`03-02`) — `03-05` Task 1 copies its shape exactly: module docstring, `# --- Section ---` dividers, plain `def _record_if_changed(conn, ...)` handed to `run_db`, async seam above it | partial |
| `backend/tests/services/conftest.py` | test fixture (fake collaborator) | — | `backend/app/market/interface.py` — the six abstract members `RecordingSource` implements; `03-04` Task 1 specifies the fake against that interface, not against `SimulatorDataSource` | partial |
| `backend/app/api/portfolio.py` | route (router factory) | request-response | `backend/app/api/health.py` | exact |
| `backend/app/api/watchlist.py` | route (router factory) | request-response | `backend/app/api/health.py` | exact |
| `backend/app/api/models.py` | model (Pydantic) | transform | **none** — no Pydantic model exists in the repo yet | none |
| `backend/app/api/errors.py` | middleware (exception handlers) | request-response | **none** — no handler registered today | none |
| `backend/app/api/__init__.py` (edit) | package init | — | itself, lines 1-11 | exact |
| `backend/app/main.py` (edit) | config / app assembly | event-driven (lifespan) | itself, lines 23-55 | exact |
| `backend/tests/services/__init__.py` | test package marker | — | `backend/tests/api/__init__.py` | exact |
| `backend/tests/services/test_*.py` | test (unit) | — | `backend/tests/db/test_queries.py` | exact |
| `backend/tests/api/test_portfolio.py`, `test_watchlist.py` | test (route) | request-response | `backend/tests/api/test_health.py` | exact |
| `backend/tests/conftest.py` (one-line edit, Pitfall 1) | test fixture | — | itself, lines 44-58 | exact |

## Pattern Assignments

### `app/api/portfolio.py` and `app/api/watchlist.py` (route, request-response)

**Analog:** `backend/app/api/health.py` — the only existing router in the project. Copy its shape exactly.

**Whole-file pattern** (`backend/app/api/health.py:1-40`):

```python
"""Health endpoint reporting whether the price feed is actually alive."""

from __future__ import annotations

import time

from fastapi import APIRouter

from app.market import MarketDataSource, PriceCache


def create_health_router(price_cache: PriceCache, source: MarketDataSource) -> APIRouter:
    """Build the /api/health router bound to a specific cache and source.

    The router is created inside the factory, not at module level, so calling
    this twice (an app plus a test app) does not register the route twice.
    """
    router = APIRouter(prefix="/api", tags=["system"])

    @router.get("/health")
    async def get_health() -> dict[str, object]:
        ...

    return router
```

Copy from this: module docstring first, `from __future__ import annotations`, factory taking
collaborators as arguments, `APIRouter(prefix="/api", tags=[...])` built **inside** the factory,
inner `async def` handler with a full return annotation, `return router` last.
`create_portfolio_router(price_cache)` and `create_watchlist_router(price_cache, source)` differ
only in their argument list and `tags=["portfolio"]` / `tags=["watchlist"]`.

**The db_path seam** — `health.py` does not need it, so take it from the dependency itself
(`backend/app/db/connection.py:125-131`):

```python
def get_db_path(request: Request) -> Path:
    """FastAPI dependency yielding the database path held on app.state.

    No module-level path or connection singleton - the same rule the price cache
    follows - because tests override exactly this one dependency.
    """
    return request.app.state.db_path
```

Handlers therefore take `db_path: Annotated[Path, Depends(get_db_path)]`. This is the one seam
`tests/conftest.py:57` overrides; do not read `app.state.db_path` from a request handler directly.

---

### `app/services/trading.py` (service, read-modify-write in one transaction)

**Analog for the transaction:** `backend/app/db/connection.py:73-92`.

```python
@contextmanager
def writing(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a write inside BEGIN IMMEDIATE, committing or rolling back.

    BEGIN IMMEDIATE takes the write lock up front, so two concurrent
    read-modify-write sequences cannot both read, both compute and both write.
    Failures roll back and re-raise; nothing is swallowed.

    Reads deliberately do not use this. Under WAL a reader already sees a
    consistent snapshot, so wrapping reads would serialize readers behind
    writers for nothing.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
```

Raising `TradeError` / `Conflict` inside the `with writing(conn):` block is safe and correct: the
`except Exception` branch rolls back and re-raises. This is what makes D-01 and D-08 work, and why
no compensating "undo" code belongs anywhere in the service.

**Analog for the offload seam:** `backend/app/db/connection.py:137-150`.

```python
async def run_db(path: Path, fn: Callable[..., Any], *args: Any) -> Any:
    """Run a query function against the database, off the event loop.

    This is the only place database work crosses into a thread. A 5-second busy
    wait therefore blocks an executor thread and never the SSE stream.
    """

    def _call() -> Any:
        ensure_initialized(path)
        with connect(path) as conn:
            return fn(conn, *args)

    # sqlite3 is synchronous - run in a thread to avoid blocking the event loop.
    return await asyncio.to_thread(_call)
```

`_apply_trade(conn, ...)` must therefore be a **plain `def` taking the connection first**, matching
every function in `queries.py`, and is invoked as
`await run_db(db_path, _apply_trade, ticker, side, quantity, fill_price, prices)`.

**Analog for the price wait (do not reimplement):** `backend/app/market/cache.py:145-158`.

```python
async def wait_for_price(cache: PriceCache, ticker: str, timeout: float = 2.0) -> float:
    """Return the current price, waiting up to `timeout` for a first tick.

    Raises ValueError with a user-facing message if no price arrives. Callers
    translate that into a 400 (PLAN.md section 8).
    """
    deadline = time.monotonic() + timeout
    while True:
        price = cache.get_price(ticker)
        if price is not None:
            return price
        if time.monotonic() >= deadline:
            raise ValueError(f"No price available for {ticker} yet, please try again")
        await asyncio.sleep(0.2)
```

Note "Callers translate that into a 400" — this is the docstring that makes the bare-`ValueError`
handler in `app/api/errors.py` load-bearing rather than defensive.

**Analog for the write calls** (`backend/app/db/queries.py:89-118`, `139-172`, `246-263`) — call
these; pass **raw** values and let the write boundary round:

```python
def upsert_position(
    conn: sqlite3.Connection,
    ticker: str,
    quantity: float,
    avg_cost: float,
    user_id: str = DEFAULT_USER_ID,
) -> None:
    """Insert or update the position for one ticker.

    Driven by the UNIQUE (user_id, ticker) constraint rather than a
    read-then-branch, so the whole decision is one atomic statement under the
    write lock. avg_cost keeps 4 decimal places because it is a derived ratio,
    not a price the user paid - see money.py.
    """
    conn.execute(
        "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (user_id, ticker) DO UPDATE SET"
        " quantity = excluded.quantity,"
        " avg_cost = excluded.avg_cost,"
        " updated_at = excluded.updated_at",
        (
            str(uuid.uuid4()),
            user_id,
            normalize_ticker(ticker),
            round_quantity(quantity),
            round_quantity(avg_cost),
            _utc_now(),
        ),
    )
```

```python
    executed_at = _utc_now()          # queries.py:158, insert_trade
    ...
    return executed_at                # queries.py:172 — the trade response uses THIS value
```

```python
    cursor = conn.execute(            # queries.py:258-263, add_watchlist_ticker
        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT (user_id, ticker) DO NOTHING",
        (str(uuid.uuid4()), user_id, normalize_ticker(ticker), _utc_now()),
    )
    return cursor.rowcount == 1
```

PORT-07's auto-add is one call to this inside the same `writing()` block.

**Money helpers to use verbatim** (`backend/app/db/money.py:33-65`):

```python
def round_money(value: float) -> float:
    """Round a cash amount to 2 decimal places for storage."""
    return round(value, MONEY_PLACES)


def round_quantity(value: float) -> float:
    """Round a share quantity to 4 decimal places for storage."""
    return round(value, QUANTITY_PLACES)


def is_zero(value: float) -> bool:
    """Whether a share quantity should be treated as no holding at all."""
    return abs(value) < QUANTITY_EPSILON
```

Constants at `money.py:28-30`: `MONEY_PLACES = 2`, `QUANTITY_PLACES = 4`, `QUANTITY_EPSILON = 1e-6`.

The module docstring (`money.py:9-19`) is a binding rule for this phase, not commentary:

> Rounding applies at the write boundary only. Derived figures - market_value, unrealized_pnl,
> total_value - are returned at full float precision and formatted by the client... This module
> therefore exposes no helper that rounds a derived value.

So `value_portfolio` returns unrounded figures, and `round_money` appears in the service only in
the D-16 snapshot-skip comparison and the D-04 cash-sufficiency comparison — never on an output.

---

### `app/services/portfolio.py` (service, CRUD read + pure transform)

**Analog for the read functions:** `backend/app/db/queries.py:65-86` — plain def, conn first,
`user_id` last, returns `sqlite3.Row`.

```python
def get_positions(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> list[sqlite3.Row]:
    """Every held position, ordered by ticker.

    The order is specified rather than left to SQLite's row order so the
    positions table renders the same way on every request.
    """
    return conn.execute(
        "SELECT id, user_id, ticker, quantity, avg_cost, updated_at FROM positions"
        " WHERE user_id = ? ORDER BY ticker",
        (user_id,),
    ).fetchall()
```

Row column sets the service must key off (verbatim from the SELECT lists):
profile `id, cash_balance, created_at`; position `id, user_id, ticker, quantity, avg_cost,
updated_at`; snapshot `id, total_value, recorded_at`; watchlist `id, user_id, ticker, added_at`.

**Analog for the pure-function-with-a-lock-free-read-surface style:**
`backend/app/market/cache.py:101-110`.

```python
    def get_all(self) -> dict[str, PriceUpdate]:
        """Shallow copy of every current price. Safe to iterate without the lock."""
        with self._lock:
            return dict(self._prices)

    def get_history(self, ticker: str) -> list[float]:
        """Recent prices, oldest first, up to history_points. Empty if unknown."""
        with self._lock:
            history = self._history.get(ticker)
            return list(history) if history else []
```

`value_portfolio(cash, positions, prices)` is the same species: no I/O, callable from the executor
thread, unit-testable with literals. The prices dict is built on the async side as
`{t: u.price for t, u in cache.get_all().items()}` and handed in (D-02).

**Reset (`reset_portfolio`)** — no bulk-delete analog exists; see No Analog Found. The per-ticker
loop composes `get_positions` (above) with `delete_position` (`queries.py:121-133`) inside one
`writing()` block, and reads `STARTING_CASH` from `app.db.seed` (`seed.py:34`) rather than
restating `10000.0`.

---

### `app/services/watchlist.py` (service, CRUD + market-source side effect)

**Analog for the delete-and-report-rowcount pattern:** `backend/app/db/queries.py:266-279`.

```python
def remove_watchlist_ticker(
    conn: sqlite3.Connection, ticker: str, user_id: str = DEFAULT_USER_ID
) -> bool:
    """Remove a ticker from the watchlist, returning whether a row was removed.

    False means the ticker was not watched, which the caller turns into a 404.
    Refusing to remove a ticker the user holds a position in is a business rule
    and lives at the service seam where the 409 is raised, not here.
    """
    cursor = conn.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, normalize_ticker(ticker)),
    )
    return cursor.rowcount == 1
```

This docstring is the specification for `_remove_checked`: `False` → `NotFound` (404); held
position → `Conflict` (409), raised inside the same `writing()` block (D-08).

**Analog for the source side effect (D-09):** `backend/app/market/simulator.py:260-273`.

```python
    async def add_ticker(self, ticker: str) -> None:
        if self._sim is None:
            return
        if ticker in self._sim.get_tickers():
            return
        self._sim.add_ticker(ticker)
        self._seed(ticker)
        logger.info("Simulator: added ticker %s", ticker)
```

The `if self._sim is None: return` line is Pitfall 4 in the source: before `start()`, `add_ticker`
is a silent no-op, so route tests must seed the cache directly rather than assert a price appears.
Note also the `%s` lazy log formatting — copy that style in the services.

---

### `app/services/snapshots.py` (service, timer-driven read-modify-write)

**Analog:** `backend/app/services/trading.py`, built earlier in this same phase by `03-01` and
completed by `03-02`. There is no pre-existing background writer in the repo, so the analog is the
other read-modify-write service rather than anything in the live tree at planning time.

`_record_if_changed(conn, prices)` is the same species as `_apply_trade(conn, ...)`: a plain `def`
taking the connection first, handed to `run_db`, with the whole read-compare-write inside one
`with writing(conn):` block (the `connection.py:73-92` excerpt above). It reuses `value_portfolio`
from `app/services/portfolio.py` rather than restating the valuation arithmetic (D-18), and
`round_money` (`money.py:33`, quoted above) appears only in the unchanged-skip comparison, never on
the value handed to `insert_snapshot`.

The loop itself follows the market module's task conventions: `asyncio.create_task(...,
name="snapshot-loop")` mirroring `simulator.py:247`, the cancel block copied verbatim from
`SimulatorDataSource.stop` (`simulator.py:250-258`, quoted below), and `%s` lazy log formatting.

---

### `tests/services/conftest.py` (test fixture, fake collaborator)

**Analog:** `backend/app/market/interface.py` — `RecordingSource` is written against the
`MarketDataSource` ABC and implements all six abstract members, rather than subclassing or
monkeypatching `SimulatorDataSource`. That is deliberate: `SimulatorDataSource.add_ticker` returns
immediately before `start()` (the `if self._sim is None: return` line quoted in the watchlist
section, Pitfall 4), so a real unstarted source makes a passing registration test prove nothing.

Fixture style follows `backend/tests/conftest.py:38-58` (quoted below): a plain `@pytest.fixture`
returning a fresh instance, docstring stating what it is for. It lives under `tests/services/`
rather than in the root conftest so Phase 1's fixtures stay untouched (D-22).

---

### `app/main.py` (config / app assembly, event-driven)

**Analog:** itself, `backend/app/main.py:23-55`. Three additions, nothing else.

```python
def create_app() -> FastAPI:
    """Assemble the application. ..."""
    cache = PriceCache()
    source = create_market_data_source(cache)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Run the market data source for the lifetime of the app. ..."""
        await source.start(list(DEFAULT_TICKERS))
        yield
        await source.stop()

    app = FastAPI(title="FinAlly", lifespan=lifespan)
    app.state.price_cache = cache
    app.state.market_source = source
    app.state.db_path = DB_PATH

    app.include_router(create_health_router(cache, source))
    app.include_router(create_stream_router(cache))
    app.frontend("/", directory=STATIC_DIR, fallback="index.html")
    return app
```

- New `include_router` calls go **between line 53 and line 54**. `app.frontend(...)` stays last
  (C-17; guarded by `tests/test_main.py`).
- `register_exception_handlers(app)` goes after the `FastAPI(...)` construction.
- The `snapshot-loop` task is created after `await source.start(...)`, cancelled before
  `await source.stop()`.

**Task cancel pattern to copy verbatim** (`backend/app/market/simulator.py:250-258`):

```python
    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Simulator stopped")
```

Task naming convention: `asyncio.create_task(self._run_loop(), name="simulator-loop")`
(`simulator.py:247`) → `name="snapshot-loop"`. `tests/test_main.py:109` asserts
`"simulator-loop" in _running_task_names()`; the snapshot-loop test mirrors that assertion.

---

### `app/services/__init__.py` and the `app/api/__init__.py` edit (package init)

**Analog:** `backend/app/db/__init__.py:1-37` and `81-115` — a "Public API" docstring listing every
export with a one-line description, then explicit re-imports, then an alphabetically sorted
`__all__`.

```python
"""Persistence subsystem for FinAlly: schema, seed data and SQLite access.

Public API:
    BUSY_TIMEOUT_MS     - Milliseconds SQLite waits on a locked database
    ...
    writing                - Run a write inside BEGIN IMMEDIATE
"""

from .connection import (
    BUSY_TIMEOUT_MS,
    connect,
    ...
)

__all__ = [
    "BUSY_TIMEOUT_MS",
    ...
]
```

The `app/api/__init__.py` edit extends the existing file (`backend/app/api/__init__.py:1-11`) in
the same shape:

```python
"""HTTP routers for the FinAlly API.

Public API:
    create_health_router - FastAPI router factory for GET /api/health
"""

from .health import create_health_router

__all__ = [
    "create_health_router",
]
```

Note `app/api/__init__.py` has **no** `from __future__ import annotations` — package `__init__`
files here are docstring + imports + `__all__` only. Match that.

---

### `tests/api/test_portfolio.py`, `tests/api/test_watchlist.py` (test, request-response)

**Analog:** `backend/tests/api/test_health.py:1-52`.

```python
"""Tests for the health endpoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

HEALTH_KEYS = {"status", "market_source", "tickers_cached", "newest_price_age_seconds"}


class TestHealthEndpoint:
    """Unit tests for GET /api/health."""

    def test_payload_is_exactly_four_keys(self, app: FastAPI) -> None:
        """The health payload is a fixed four-key surface."""
        response = TestClient(app).get("/api/health")
        assert response.status_code == 200
        assert set(response.json()) == HEALTH_KEYS

    def test_price_age_is_a_non_negative_float_once_a_price_exists(self, app: FastAPI) -> None:
        """A cached price turns the age into a real measurement."""
        app.state.price_cache.update("AAPL", 190.50)
        payload = TestClient(app).get("/api/health").json()
        ...
```

Copy: one `class TestX` per endpoint, one behavior per test, a docstring on every test stating the
behavior, `app: FastAPI` fixture, `TestClient(app)` constructed inline, and
`app.state.price_cache.update("AAPL", 190.50)` (line 42) as the way to give a route a price without
running lifespan — this is exactly the Pitfall 4 workaround.

**Fixtures to reuse verbatim** (`backend/tests/conftest.py:38-58`):

```python
@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A throwaway database path, one per test."""
    return tmp_path / "finally.db"


@pytest.fixture
def app(db_path: Path) -> FastAPI:
    """An app pointed at a throwaway database.

    The path arrives by overriding the one dependency every route reads it
    through, rather than by monkeypatching FINALLY_DB_PATH, which would depend
    on import-time ordering in config.py.

    Lifespan has not run yet, so the cache is empty and the market source is
    unstarted. Tests needing a live feed drive the lifespan themselves or serve
    the app from uvicorn.
    """
    application = create_app()
    application.dependency_overrides[get_db_path] = lambda: db_path
    return application
```

Pitfall 1's one-line addition goes immediately after line 57:
`application.state.db_path = db_path`.

---

### `tests/services/test_*.py` (test, unit)

**Analog:** `backend/tests/db/test_queries.py:1-64`.

```python
"""Tests for every query function, against a real seeded file database.

Every database here is a real file under tmp_path. :memory: would give each
connection its own empty database and could not exercise the schema the way the
app does.
"""

import datetime as dt
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db.connection import connect
from app.db.money import round_money, round_quantity
from app.db.queries import (
    add_watchlist_ticker,
    ...
)
from app.db.seed import DEFAULT_TICKERS, STARTING_CASH, apply_schema, seed_fresh


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A seeded throwaway file database, closed when the test ends."""
    with connect(tmp_path / "finally.db") as connection:
        apply_schema(connection)
        seed_fresh(connection)
        yield connection


class TestProfile:
    """The single profile row and its cash balance."""

    def test_get_profile_returns_the_seeded_row(self, conn: sqlite3.Connection) -> None:
        """A seeded database answers with the default user and starting cash."""
        row = get_profile(conn)
        assert row["id"] == "default"
        assert row["cash_balance"] == STARTING_CASH
```

Copy: the local `conn` fixture for tests that exercise a composed `def _apply_x(conn, ...)`
directly (no event loop needed), real file databases under `tmp_path` never `:memory:`, grouping
classes named after the unit, and asserting against `STARTING_CASH` / `round_money(...)` rather
than literals. `tests/services/__init__.py` copies `tests/api/__init__.py` (bare package marker).

## Shared Patterns

### Module preamble (applies to every new `.py` file under `app/`)

**Source:** `backend/app/db/connection.py:1-29`, `backend/app/api/health.py:1-9`

```python
"""One-line summary of what this module owns.

The why: the constraint or decision that makes this module's shape non-obvious.
"""

from __future__ import annotations

import logging
...

logger = logging.getLogger(__name__)
```

`from __future__ import annotations` is the first import in every module under `app/` (C-9).
Package `__init__.py` files are the sole exception.

### Section comments inside a module

**Source:** `backend/app/db/queries.py:36`, `62`, `136`, `175`, `231`, `293` and
`backend/app/db/connection.py:37`, `70`, `95`, `134`

```python
# --- Profile ---
# --- Positions ---
# --- Transactions ---
```

Long modules use `# --- Section ---` dividers. `services/trading.py` and `services/portfolio.py`
should use them (validation / transaction / public seam).

### Logging

**Source:** `backend/app/market/simulator.py:248`, `267`, `273`; `backend/app/db/connection.py:122`

```python
logger.info("Simulator started with %d tickers", len(tickers))
logger.info("Simulator: added ticker %s", ticker)
logger.info("Database initialized at %s", resolved)
```

`%s`/`%d` lazy formatting, never f-strings, never emojis (C-8, C-12). One
`logger = logging.getLogger(__name__)` per module.

### Ticker validation — one rule, already applied at the query boundary

**Source:** `backend/app/market/tickers.py:7-22`, applied at `queries.py:31, 85, 113, 165, 261, 277, 288`
**Apply to:** every service that takes a ticker

`normalize_ticker(raw)` raises `ValueError(f"Invalid ticker symbol: {raw!r}")`. `queries.py`
already routes every ticker argument through it, so a service must not add a second regex — but a
service that wants the 400 *before* touching the database calls `normalize_ticker` itself first.

### Error taxonomy is `ValueError`-rooted, and `writing()` handles the rollback

**Source:** `backend/app/db/connection.py:85-92`, `backend/app/market/cache.py:148-149`,
`backend/app/db/queries.py:271`
**Apply to:** `services/errors.py`, all three services, `api/errors.py`

Three existing docstrings already assume this phase's design: `wait_for_price` says "Callers
translate that into a 400", `remove_watchlist_ticker` says "False means the ticker was not
watched, which the caller turns into a 404" and "the 409... lives at the service seam". Services
raise; only the app-level handlers translate; no service imports `HTTPException` (C-13, D-06/D-07).

## No Analog Found

Files and behaviors with no close match in the codebase. The planner should use RESEARCH.md's
patterns and code examples instead.

| File / behavior | Role | Data Flow | Reason |
|-----------------|------|-----------|--------|
| `app/services/errors.py` | utility (exception classes) | — | No custom exception class exists anywhere in `app/`. Everything raises bare `ValueError` today (`tickers.py:21`, `cache.py:157`). Use RESEARCH.md D-06 / Pattern 3. |
| `app/api/errors.py` | middleware | request-response | No `add_exception_handler` call exists in the repo; `main.py` registers none. Use RESEARCH.md Pattern 3 verbatim, including the load-bearing bare-`ValueError` row. |
| `app/api/models.py` | model | transform | **No Pydantic model exists anywhere in the project.** `health.py` returns a plain `dict[str, object]`, and `PriceUpdate` is a frozen dataclass, not a `BaseModel`. Follow RESEARCH.md D-19/D-20: shape only, no `gt=0`, nullable fields as `float \| None`. |
| Bulk position delete for PORT-14 reset | service | CRUD (delete) | **No `delete_all_positions` query exists and `queries.py` is frozen** (RESEARCH.md Open Question 1). Compose `get_positions` + `delete_position` in a loop inside one `writing()` block. Do not add a query function. |
| `since` timestamp normalization for `/api/portfolio/history` | route | request-response | **No analog and deliberately none to be written** (RESEARCH.md Pitfall 5). `_utc_now()` emits `+00:00`; PLAN.md's examples use `Z`; the two do not sort compatibly. Document the format in the route docstring; do not normalize in the service. |
| `app/services/` and `tests/services/` package layout | package init | — | Both directories exist and are **completely empty — no `__init__.py`**. Nearest structural siblings: `app/db/__init__.py` and `tests/api/__init__.py`. |

## Metadata

**Analog search scope:** `backend/app/api/`, `backend/app/db/`, `backend/app/market/`,
`backend/app/main.py`, `backend/tests/` (all subpackages)
**Files read this session:** 14
**Pattern extraction date:** 2026-08-12
