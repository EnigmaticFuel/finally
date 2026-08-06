# Phase 1: Foundation & Spine - Pattern Map

**Mapped:** 2026-08-05
**Files analyzed:** 21 (9 source, 1 SQL, 1 HTML, 10 test/config)
**Analogs found:** 17 / 21

The only substantial existing Python in this project is `backend/app/market/` — a finished,
frozen subsystem of nine modules. Every analog below comes from it. Phase 1 must imitate it
stylistically without modifying it.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/main.py` | config / app assembly | request-response | `app/market/factory.py` + `app/market/simulator.py` (lifecycle) | role-match |
| `backend/app/config.py` | config | transform | `app/market/factory.py` (env read) + `app/market/seed_prices.py` (constants) | role-match |
| `backend/app/api/health.py` | route | request-response | `app/market/stream.py` (router factory) | exact |
| `backend/app/api/__init__.py` | package init | — | `app/market/__init__.py` | exact |
| `backend/app/db/connection.py` | service / infra | file-I/O | `app/market/cache.py` (ctx/lock discipline) + `massive_client.py` (`to_thread`) | partial |
| `backend/app/db/schema.sql` | migration | file-I/O | none (see No Analog Found) | none |
| `backend/app/db/init.py` (`ensure_initialized`) | service | file-I/O | `app/market/simulator.py::SimulatorDataSource.start` (idempotent init) | partial |
| `backend/app/db/seed.py` | config / data | batch | `app/market/seed_prices.py` | exact |
| `backend/app/db/queries.py` | model / repository | CRUD | none in-repo (see No Analog Found) | none |
| `backend/app/db/money.py` | utility | transform | `app/market/tickers.py` (one shared rule) + `models.py` (rounding) | exact |
| `backend/app/db/__init__.py` | package init | — | `app/market/__init__.py` | exact |
| `backend/static/index.html` | static asset | — | none | none |
| `backend/tests/conftest.py` | test | — | `backend/tests/conftest.py` (extend in place) | exact |
| `backend/tests/db/test_connection.py` | test | file-I/O | `tests/market/test_cache.py` | role-match |
| `backend/tests/db/test_seed.py` | test | batch | `tests/market/test_cache.py` | role-match |
| `backend/tests/db/test_queries.py` | test | CRUD | `tests/market/test_cache.py` | role-match |
| `backend/tests/db/test_money.py` | test | transform | `tests/market/test_cache.py` | role-match |
| `backend/tests/db/test_concurrency.py` | test | event-driven | none (D-20 is new ground) | none |
| `backend/tests/api/test_health.py` | test | request-response | `tests/market/test_cache.py` | role-match |
| `backend/tests/test_main.py` | test | request-response | `tests/market/test_cache.py` | role-match |
| `backend/tests/market/test_stream_integration.py` | test | streaming | RESEARCH.md Code Examples (uvicorn-in-thread) | spec-only |

---

## Pattern Assignments

### `backend/app/api/health.py` (route, request-response)

**Analog:** `backend/app/market/stream.py` — **exact match. This is the template.**
D-14 says `create_health_router(cache)` mirrors `create_stream_router(cache)`; it is
the same shape with a different body.

**Module header + imports pattern** (`stream.py:1-19`):

```python
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
```

Note the order: one-line module docstring, `from __future__ import annotations`,
stdlib, third-party, local relative import, `logger`, then `SCREAMING_SNAKE_CASE`
module constants.

**Router-factory pattern — copy verbatim in structure** (`stream.py:22-52`):

```python
def create_stream_router(price_cache: PriceCache) -> APIRouter:
    """Build the /api/stream router bound to a specific cache.

    The router is created inside the factory, not at module level, so calling
    this twice (an app plus a test app) does not register the route twice.
    """
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        """SSE endpoint for live price updates.
        ...
        """
        return StreamingResponse(...)

    return router
```

Health equivalent: `router = APIRouter(prefix="/api", tags=["system"])`, one
`@router.get("/health")` handler closing over `cache`, `return router` at the end.
The docstring's stated reason ("calling this twice ... does not register the route
twice") is the house justification — carry the same reasoning into the new docstring.

**Payload source** — both fields already exist in the frozen module, do not compute them by hand:
- `cache.newest_timestamp()` (`cache.py:112-117`) — *"Timestamp of the most recently written price, for /api/health."*
- `source.source_name` (`interface.py:22-25`) — *"Short identifier for logs and /api/health: 'simulator' or 'massive'."*
- `len(cache)` — `PriceCache.__len__` (`cache.py:124-126`)

**Verified payload shape** (RESEARCH.md Code Examples):

```python
@router.get("/health")
async def get_health() -> dict[str, object]:
    newest = cache.newest_timestamp()
    return {
        "status": "ok",
        "market_source": source.source_name,
        "tickers_cached": len(cache),
        "newest_price_age_seconds": None if newest is None else round(time.time() - newest, 3),
    }
```

---

### `backend/app/main.py` (app assembly, request-response)

**Analogs:** `app/market/factory.py` (module shape, env-driven construction) and
`app/market/simulator.py:236-258` (async start/stop lifecycle to be driven by lifespan).

No existing module assembles a FastAPI app — this is the first. Take the *shape* from
`factory.py` and the *lifecycle contract* from `SimulatorDataSource`.

**Factory-function pattern** (`factory.py:1-31`, full file — it is 31 lines and that is
the house scale for a module of this kind):

```python
"""Factory for creating market data sources."""

from __future__ import annotations

import logging
import os

from .cache import PriceCache
from .interface import MarketDataSource
from .massive_client import MassiveDataSource
from .simulator import SimulatorDataSource

logger = logging.getLogger(__name__)


def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """Create the appropriate market data source based on environment variables.

    - MASSIVE_API_KEY set and non-empty → MassiveDataSource (real market data)
    - Otherwise → SimulatorDataSource (GBM simulation)

    Returns an unstarted source. Caller must await source.start(tickers).
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()

    if api_key:
        logger.info("Market data source: Massive API (real data)")
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)
    else:
        logger.info("Market data source: GBM Simulator")
        return SimulatorDataSource(price_cache=price_cache)
```

Note: the env var is read with `os.environ.get(..., "").strip()` and truthiness-tested;
the *presence* of a key is logged, never its value (security: V14 / secret leakage).

**Lifecycle contract main.py's lifespan must honour** (`interface.py:14-19`):

```
Lifecycle:
    source = create_market_data_source(cache)
    await source.start(["AAPL", "GOOGL", ...])   # cache populated on return
    await source.add_ticker("TSLA")
    await source.remove_ticker("GOOGL")
    await source.stop()                          # idempotent
```

`start()` populates the cache before returning (`simulator.py:236-247`), so lifespan
needs no post-start wait. `stop()` is idempotent (`simulator.py:249-257`), so the
lifespan teardown needs no `if` guard — writing one would be defensive programming.

**Lifecycle logging pattern to copy** (`simulator.py:246`, `:257`):

```python
logger.info("Simulator started with %d tickers", len(tickers))
...
logger.info("Simulator stopped")
```

`%s`/`%d` lazy formatting, never f-strings, no emojis.

**`create_app()` skeleton** — verified end-to-end against the real frozen module
(RESEARCH.md Code Examples). The load-bearing constraint is steps 1-2 before step 4:

```python
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"   # absolute — Pitfall 5


def create_app() -> FastAPI:
    """Assemble the application.

    The cache and market source are built here, not in the lifespan handler:
    create_stream_router() and create_health_router() take the cache as an
    argument, and router registration happens before lifespan ever runs.
    """
    cache = PriceCache()                              # 1. CORE-01 ordering constraint
    source = create_market_data_source(cache)         # 2.

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await source.start(DEFAULT_TICKERS)           # CORE-02
        yield
        await source.stop()

    app = FastAPI(title="FinAlly", lifespan=lifespan)
    app.state.price_cache = cache                     # CORE-07: DI, not a module singleton
    app.state.market_source = source
    app.state.db_path = DB_PATH                       # D-06/D-12

    app.include_router(create_health_router(cache))   # CORE-08
    app.include_router(create_stream_router(cache))   # CORE-03
    app.frontend("/", directory=STATIC_DIR, fallback="index.html")   # CORE-09
    return app
```

**Import surface — only these eight names may cross the freeze** (`app/market/__init__.py:21-30`):

```python
__all__ = [
    "MarketDataSource",
    "PriceCache",
    "PriceUpdate",
    "TICKER_PATTERN",
    "create_market_data_source",
    "create_stream_router",
    "normalize_ticker",
    "wait_for_price",
]
```

---

### `backend/app/config.py` (config, transform)

**Analogs:** `app/market/factory.py:24` for env reading, `app/market/seed_prices.py:1-44`
for module-level constants.

D-13: `load_dotenv` on the project-root `.env` at import, then plain `os.getenv` exposed
as constants. No `pydantic-settings`.

**Constants pattern** (`seed_prices.py:1-44`) — module docstring, typed dict/scalar
constants in `SCREAMING_SNAKE_CASE`, each carrying a short `#` comment only where the
value is non-obvious:

```python
"""Seed prices, GBM parameters and correlation groups for the simulator."""

from __future__ import annotations

import hashlib

# Recognisable rather than current. This is a simulation with pretend money.
SEED_PRICES: dict[str, float] = {
    "AAPL": 190.00,
    ...
}

INTRA_TECH_CORR = 0.6  # Tech names move together
INTRA_FINANCE_CORR = 0.5  # Finance names move together
CROSS_GROUP_CORR = 0.3  # Across sectors, TSLA, and synthesised tickers
```

Note the explicit type annotations on container constants (`dict[str, float]`) and bare
floats for scalars. Apply to `DB_PATH`, `OPENROUTER_API_KEY`, `MASSIVE_API_KEY`, `LLM_MOCK`.

**Env-read pattern** (`factory.py:24`):

```python
api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
```

---

### `backend/app/db/money.py` (utility, transform)

**Analogs:** `app/market/tickers.py` (whole file — the "one shared rule, one place"
module) and `app/market/models.py:25-58` (rounding conventions).

**One-shared-rule module pattern** (`tickers.py:1-22`, full file — 22 lines):

```python
"""Ticker symbol validation — one rule, shared by every caller."""

from __future__ import annotations

import re

TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}$")


def normalize_ticker(raw: str) -> str:
    """Uppercase, strip, and validate a ticker symbol.

    Raises ValueError if the symbol is not 1-5 A-Z characters. Callers turn
    that into a 400 with the message shown to the user verbatim.

    This validates shape, not existence: the simulator accepts any well-formed
    symbol and synthesizes parameters for it (see seed_prices.py).
    """
    ticker = raw.strip().upper()
    if not TICKER_PATTERN.match(ticker):
        raise ValueError(f"Invalid ticker symbol: {raw!r}")
    return ticker
```

`money.py` is the same species of module: the docstring names the sharing ("one rule,
shared by every caller" → D-17's "Phase 3's manual trade path and Phase 6's LLM-driven
trade path both route through the same functions"), constants sit above the functions,
each function's docstring states who the callers are and what they do with a failure.

**Rounding + zero-guard pattern** (`models.py:25-35`) — `round(x, n)` at the boundary,
explicit zero check before division, no `Decimal`:

```python
@property
def change(self) -> float:
    """Absolute price change since the previous tick."""
    return round(self.price - self.previous_price, 4)

@property
def change_percent(self) -> float:
    """Percent change since the previous tick. Drives the flash animation only."""
    if self.previous_price == 0:
        return 0.0
    return round((self.price - self.previous_price) / self.previous_price * 100, 4)
```

The cache also rounds on write, not on read (`cache.py:48`): `price = round(price, 2)` —
this is exactly D-18's "rounding applies at the write boundary only".

Constants for `money.py`: `MONEY_PLACES = 2`, `QUANTITY_PLACES = 4`, `QUANTITY_EPSILON = 1e-6`.

---

### `backend/app/db/connection.py` (service/infra, file-I/O)

**Analogs:** `app/market/massive_client.py:118-121` (the `asyncio.to_thread` offload,
which D-01 explicitly cites as precedent) and `app/market/cache.py:36-46` (lock-guarded
resource discipline with `# --- Section ---` dividers).

**The offload pattern this file must generalise** (`massive_client.py:113-121`):

```python
async def _poll_once(self) -> None:
    """Execute one poll cycle. Never raises — the loop must survive every failure."""
    if not self._tickers or not self._client:
        return

    try:
        # The Massive RESTClient is synchronous — run in a thread to
        # avoid blocking the event loop.
        snapshots = await asyncio.to_thread(self._fetch_snapshots)
```

The inline comment explains a specific non-obvious choice at that line — that is the
sanctioned use of `#` in this codebase. `connection.py`'s `run_db` deserves the same
one-line justification.

**Section-divider convention inside a module** (`cache.py:36`, `:91`, `:132`):

```python
    # --- Writing ---
    ...
    # --- Reading ---
    ...
    # --- Internal (callers already hold the lock) ---
```

Also used at module level in `simulator.py:167` (`# --- Internals ---`) and
`massive_client.py:223` (`# --- Diagnostics ---`). `connection.py` naturally splits into
`# --- Connecting ---` / `# --- Transactions ---` / `# --- Offload ---`.

**Verified implementation** (RESEARCH.md Code Examples — stress-tested at 360/360
concurrent writes, 0 `OperationalError`). Note `isolation_level=None` is mandatory
(Pitfall 4) and `busy_timeout` must be reapplied on every open because it is
per-connection:

```python
BUSY_TIMEOUT_MS = 5000        # D-04


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """Open a connection with WAL and a busy timeout, and close it on exit.

    isolation_level=None puts the driver in autocommit mode so the writing()
    helper can drive BEGIN IMMEDIATE explicitly. Both PRAGMAs are applied on
    every open: journal_mode persists in the file, but busy_timeout is
    per-connection and would otherwise silently revert to zero.
    """
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    try:
        yield conn
    finally:
        conn.close()
```

**Error-handling pattern — raise, do not swallow.** The `writing()` helper rolls back
and re-raises. The codebase has exactly one broad `except Exception` that swallows
(`massive_client.py:122`, justified by a comment because the poll loop must survive
network failure); `writing()` is *not* that case:

```python
@contextmanager
def writing(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a write inside BEGIN IMMEDIATE, committing or rolling back."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
```

---

### `backend/app/db/seed.py` (config/data, batch)

**Analog:** `app/market/seed_prices.py` — exact match on module role.

D-10 forbids importing `SEED_PRICES`; `DEFAULT_TICKERS` is declared independently here.
Copy the constants shape (see `config.py` above) plus the docstring habit of explaining
*why* a value was chosen: `seed_prices.py:7` (`# Recognisable rather than current...`)
and `:35-36` (`# Correlation groups. TSLA is deliberately in neither: ...`).

Deferred-idea hook from CONTEXT.md: shape `seed_fresh()` so Phase 3's Reset Portfolio
(PORT-14) can call it rather than duplicating the `$10,000` constant. That means
`STARTING_CASH` and `DEFAULT_TICKERS` are module constants and the seeding body is a
callable function, not inline code inside `ensure_initialized`.

**Idempotent-init precedent** (`simulator.py:116-119`, `:249-251`) — early-return guards
rather than exception handling:

```python
def add_ticker(self, ticker: str) -> None:
    """Add a ticker to the simulation. Rebuilds the correlation matrix."""
    if ticker in self._prices:
        return
```

D-09's seed gate ("does `users_profile` have a row?") is the same idiom.

---

### `backend/app/db/queries.py` (repository, CRUD)

**No in-repo analog** — no SQL exists anywhere in the codebase today. Take the *module
conventions* from `app/market/tickers.py` (docstring stating caller obligations, plain
functions, full type hints) and the SQL rules from RESEARCH.md's Security Domain:

- Parameterized `?` placeholders on every query; never f-string SQL.
- `executescript()` only for the static `schema.sql`, never with user input.
- Plain `def`, connection as first argument (D-02) — so pytest calls them with no event loop.
- Ticker arguments normalized through `app.market.normalize_ticker`, not a second regex.

Signature shape the Phase 3 contract depends on:

```python
def get_positions(conn: sqlite3.Connection, user_id: str = "default") -> list[sqlite3.Row]:
```

---

### `backend/app/db/__init__.py` and `backend/app/api/__init__.py` (package init)

**Analog:** `backend/app/market/__init__.py` — exact match, quoted in full above.

Pattern: module docstring opening with a one-line package summary, then a literal
`Public API:` block listing each exported name with a short description, then the
relative imports, then an alphabetically-sorted `__all__` list. Ruff's `I` rule enforces
the import ordering; `__all__` is sorted with uppercase names first (`TICKER_PATTERN`
before `create_market_data_source`) — that is `sorted()` order, not a style choice.

---

### `backend/tests/db/*.py`, `backend/tests/api/test_health.py`, `backend/tests/test_main.py`

**Analog:** `backend/tests/market/test_cache.py` (and the rest of `tests/market/`).

**Test module pattern** (`test_cache.py:1-27`):

```python
"""Tests for PriceCache."""

import asyncio

import pytest

from app.market.cache import PriceCache, wait_for_price


class TestPriceCache:
    """Unit tests for the PriceCache."""

    def test_update_and_get(self):
        """Test updating and getting a price."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.50)
        assert update.ticker == "AAPL"
        assert update.price == 190.50
        assert cache.get("AAPL") == update

    def test_first_update_is_flat(self):
        """Test that the first update has flat direction."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.50)
        assert update.direction == "flat"
        assert update.previous_price == 190.50
```

Observations the executor must match:
- Tests are grouped in a `Test<Subject>` class with its own docstring.
- One docstring line per test, one behavior per test, few asserts.
- Absolute imports from `app.market.<module>`, not relative.
- **Existing tests carry no `from __future__ import annotations` and no return-type
  annotations.** RESEARCH.md's constraint table says full type hints apply "including
  test fixtures". Resolve toward the stricter rule for *new* test files (annotate
  fixtures and `-> None` on tests) since ruff's rule set does not enforce either way and
  the project convention doc is explicit; do not retrofit `tests/market/`.
- Test file name mirrors the module 1:1: `app/db/queries.py` → `tests/db/test_queries.py`.
- `tests/db/__init__.py` and `tests/api/__init__.py` must be created — those directories
  currently hold only stale `__pycache__` (SETUP-05 clears it).

**Existing `tests/conftest.py` in full** (extend this file, do not replace it):

```python
"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def event_loop_policy():
    """Use the default event loop policy for all async tests."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()
```

D-22 adds a `create_app()` + DB-dependency-override fixture here, plus clearing
`MASSIVE_API_KEY` for the session (RESEARCH.md Open Question 4 — otherwise a developer
with a real key has the suite hit the live Massive API).

---

### `backend/tests/market/test_stream_integration.py` (test, streaming)

**No codebase analog** — `tests/market/test_stream.py` drives `_generate_events`
directly rather than going over HTTP, which is precisely why SSE coverage sits at ~31%.

Use RESEARCH.md's verified uvicorn-in-thread pattern instead. **`TestClient.stream()` and
`httpx.ASGITransport` both hang forever** on this infinite stream (Pitfall 2) — this is
not a preference. The fixture seeds the cache directly (`cache.update("AAPL", 190.50)`),
so no simulator is needed, and the heartbeat is asserted separately by driving
`_generate_events(cache, FakeRequest(), interval=0.01, heartbeat=0.05)` rather than
waiting 15 real seconds — `stream.py:55-60` exposes those keyword arguments for exactly
this purpose.

---

## Shared Patterns

### Module preamble
**Source:** every file in `backend/app/market/`
**Apply to:** all nine new `.py` files

```python
"""One-line statement of what this module is for."""

from __future__ import annotations

import logging
...

logger = logging.getLogger(__name__)

SOME_CONSTANT = 5000  # Brief why, if non-obvious
```

`from __future__ import annotations` is the first import in **every** module without
exception (`cache.py:3`, `models.py:3`, `stream.py:3`, `factory.py:3`, `tickers.py:3`,
`interface.py:3`, `seed_prices.py:3`). Test files are the observed exception.

### Logging
**Source:** `app/market/factory.py:27,30`, `app/market/simulator.py:246,257,262,267`
**Apply to:** `main.py`, `config.py`, `db/connection.py`, `db/seed.py`

```python
logger = logging.getLogger(__name__)          # one per module, module-level
logger.info("Simulator started with %d tickers", len(tickers))
logger.info("Simulator: added ticker %s", ticker)
logger.debug("Shock event on %s: %.1f%% %s", ticker, magnitude * 100, "up" if sign > 0 else "down")
logger.error("Massive poll failed (%s); backing off to %.1fs", exc, ...)
```

`%s`-style lazy formatting only. `logger.info` for lifecycle (start/stop/init/seed),
`logger.debug` for high-frequency internals, `logger.exception` inside an `except` block
when the traceback matters. No emojis, ever. Log the presence of a secret, never its value.

### Error handling
**Source:** `app/market/tickers.py:20-21`, `app/market/cache.py:145-158`
**Apply to:** `db/queries.py`, `db/money.py`, `db/connection.py`

```python
raise ValueError(f"Invalid ticker symbol: {raw!r}")
raise ValueError(f"No price available for {ticker} yet, please try again")
```

Plain `ValueError` with a **user-facing message**; the routers translate it into a 400
and the message is shown verbatim (PLAN.md §8). No custom exception hierarchy exists and
none should be added. No speculative `try/except`. The one broad `except Exception` in
the codebase (`massive_client.py:122`) carries a comment justifying it — match that bar
if a second one is ever needed.

### Do not re-implement — already built and exported
**Source:** `app/market/__init__.py`
**Apply to:** everything in this phase and Phase 3

| Need | Use | Location |
|------|-----|----------|
| Wait up to 2s for a first tick | `wait_for_price(cache, ticker, timeout=2.0)` | `cache.py:145-158` |
| Ticker validation | `normalize_ticker` / `TICKER_PATTERN` | `tickers.py:7-22` |
| SSE framing, `retry: 1000`, 15s heartbeat | `create_stream_router(cache)` | `stream.py:22-52` |
| Price change semantics | `PriceUpdate` properties | `models.py:25-58` |
| Health payload inputs | `cache.newest_timestamp()`, `len(cache)`, `source.source_name` | `cache.py:112`, `:124`; `interface.py:22` |
| DB lock retry | `PRAGMA busy_timeout=5000` — not a retry loop | RESEARCH.md Don't Hand-Roll |

### Lint and formatting gate
**Source:** `backend/pyproject.toml` `[tool.ruff]`
**Apply to:** every new file

`line-length = 100`, `target-version = "py312"`, `select = ["E", "F", "I", "N", "W"]`,
`ignore = ["E501"]`. Run `uv run --extra dev ruff check app/ tests/`. `I` enforces the
import grouping shown above; `N` enforces `snake_case` functions, `PascalCase` classes,
`SCREAMING_SNAKE_CASE` constants. No formatter is configured — match surrounding style
by hand.

---

## No Analog Found

Files with no close match in the codebase (use RESEARCH.md and PLAN.md instead):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `backend/app/db/schema.sql` | migration | file-I/O | No SQL of any kind exists in the repo. Write it from **PLAN.md §7 column-by-column**, not by dumping the tracked `db/finally.db` (RESEARCH.md assumption A6 — only two of its six tables were verified against the spec). `CREATE TABLE IF NOT EXISTS` throughout (D-09). |
| `backend/app/db/queries.py` | repository | CRUD | No data-access layer exists. Conventions above; shapes from PLAN.md §7 and §8. |
| `backend/static/index.html` | static asset | — | No frontend files exist. D-11: a committed placeholder stating the backend is running. **No emojis** (the global rule covers markup too). |
| `backend/tests/db/test_concurrency.py` | test | event-driven | Nothing in the codebase drives code concurrently today. Use RESEARCH.md's stress-probe shape: threads × `BEGIN IMMEDIATE` read-modify-write against a `tmp_path` file DB, asserting both zero `OperationalError` **and** that the final value equals the write count (proving no lost updates, not merely no errors). |
| `backend/tests/market/test_stream_integration.py` | test | streaming | Existing SSE tests never go over HTTP. Uvicorn-in-thread pattern from RESEARCH.md; `TestClient`/`ASGITransport` provably hang. |

Non-code artifacts with no analog and no pattern needed: `.gitattributes`, `.env.example`,
`backend/.python-version`, `.gitignore` edits — all spelled out literally in RESEARCH.md's
Code Examples and Gaps table.

---

## Metadata

**Analog search scope:** `backend/app/market/` (9 modules), `backend/tests/` (conftest +
`tests/market/`), `backend/pyproject.toml`, `backend/CLAUDE.md`
**Files scanned:** 14 read in full or in targeted ranges
**Frozen-module constraint:** every analog listed is read-only. `backend/app/market/` is
consumed through its eight exported names and is not modified by this phase.
**Pattern extraction date:** 2026-08-05
