# Architecture Research

**Domain:** Single-container full-stack real-time trading workstation — FastAPI + SQLite + SSE + static Next.js export + LLM tool-executing chat
**Researched:** 2026-08-05
**Confidence:** MEDIUM (see [Confidence & Sources](#sources) — API signatures come from first-party FastAPI/Starlette docs cross-checked against PyPI release data; frontend guidance is community consensus)

---

## Headline Finding

**The mount-ordering hazard that PLAN.md section 11 warns about no longer needs a workaround.** FastAPI **0.141.0** (released 2026-07-29) added `app.frontend()`, a first-class SPA-serving primitive. Its documented semantics: *"Path operations take precedence over frontend files. FastAPI checks path operations first; frontend files are only served if no regular route matches. Frontend can be called at any point in your code."*

That converts PLAN.md's most dangerous ordering constraint from a discipline problem into a non-issue. The project currently pins `fastapi>=0.115.0`; `uv sync` will already resolve to 0.141.x. **Recommendation: use `app.frontend()`, bump the floor to `fastapi>=0.141.1`, and record the deviation from PLAN.md section 11.** The `StaticFiles(html=True)` fallback is documented below for the case where the team prefers to stay on the spec's literal wording.

> 0.141.1 (same day) specifically fixed background-task and dependency-header support in `frontend()` — pin `>=0.141.1`, not `>=0.141.0`.

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser (single origin, http://localhost:8000)                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  Next.js static export — one page, all client components        │  │
│  │  ┌───────────┐  ┌────────────────────────────────────────────┐  │  │
│  │  │ EventSource│─▶│  priceStore (module scope, non-React)     │  │  │
│  │  │  (1 conn)  │  │  ticker → {price, open, direction, ...}   │  │  │
│  │  └───────────┘  └───────┬────────────────────────────────────┘  │  │
│  │                          │ useSyncExternalStore + primitive     │  │
│  │                          │ selectors (per-ticker, per-field)    │  │
│  │  ┌──────────┬──────────┬─┴────────┬──────────┬──────────────┐  │  │
│  │  │Watchlist │  Chart   │ Heatmap  │Positions │  Header/P&L  │  │  │
│  │  └──────────┴──────────┴──────────┴──────────┴──────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────────────┐  │  │
│  │  │ appStore: cash, positions[], watchlist[], chat[], selected│  │  │
│  │  │  refetched ONLY on: mount, manual trade, chat w/ actions  │  │  │
│  │  └──────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────┘  │
└───────────────┬──────────────────────────────────┬───────────────────┘
                │ GET /api/stream/prices (SSE)      │ REST /api/*
                ▼                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FastAPI app — one process, one port 8000        `backend/app/main.py`│
│                                                                       │
│  lifespan ──▶ init_db() ──▶ read watchlist ──▶ source.start(tickers)  │
│           └─▶ snapshot_task (30s)                                     │
│                                                                       │
│  ┌─────────────────────────── routers ──────────────────────────────┐ │
│  │ stream (FROZEN) │ portfolio │ watchlist │ chat │ health          │ │
│  └────────┬──────────────┬──────────┬─────────┬────────────────────┘ │
│           │              │          │         │                       │
│           │        ┌─────┴──────────┴─────────┴────┐                  │
│           │        │  trading.execute_trade()      │  ← only real     │
│           │        │  watchlist.add/remove()       │    "service"     │
│           │        └─────┬──────────────────┬──────┘    layer         │
│           │              │                  │                         │
│  ┌────────┴──────────────┴──┐    ┌──────────┴───────────────────────┐ │
│  │  app/market/  [FROZEN]   │    │  app/db/  connection + queries   │ │
│  │  PriceCache ◀── source   │    │  sqlite3, WAL, busy_timeout      │ │
│  │  (in-memory, thread-safe)│    └──────────┬───────────────────────┘ │
│  └──────────────────────────┘               │                         │
│                                              ▼                        │
│  app.frontend("/", directory="static")   db/finally.db (bind mount)   │
│  ▲ fallback only — never shadows /api/*                               │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Status |
|-----------|----------------|--------|
| `app/market/` | Price generation, `PriceCache`, SSE router | **FROZEN — do not modify** |
| `app/main.py` | App factory: creates cache + source, wires lifespan, includes routers, calls `app.frontend()` | To build |
| `app/deps.py` | `Annotated` DI providers reading `request.app.state` | To build |
| `app/db/connection.py` | `connect()` context manager — WAL, `busy_timeout`, `check_same_thread=False`, row factory | To build |
| `app/db/schema.sql` + `init.py` | Lazy schema creation + seed (profile, 10 tickers, 1 snapshot) | To build |
| `app/db/queries.py` | Plain functions `(conn, ...) -> rows`. No ORM, no repository class | To build |
| `app/services/trading.py` | `execute_trade()` — the one piece of logic with two callers (manual + LLM) | To build |
| `app/services/watchlist.py` | `add_ticker()` / `remove_ticker()` — DB write + market source call, two callers | To build |
| `app/snapshots.py` | 30s background task; skips unchanged totals | To build |
| `app/api/{portfolio,watchlist,chat,health}.py` | Thin routers: validate → call service or query → shape response | To build |
| `app/llm/` | LiteLLM client, mock, prompt, structured-output schema | To build |
| `frontend/` | Next.js static export → `out/`, copied to `backend/static/` in Docker | To build |

---

## Q1 — FastAPI App Assembly

### The ordering problem, stated precisely

There are **two** independent construction-order facts, and PLAN.md only names one:

1. **Route vs. static fallback.** Solved by `app.frontend()` — path operations always win. (With `StaticFiles`, the mount at `/` is itself a route registered in order, so it *does* shadow anything registered after it.)
2. **Cache must exist before the app.** `create_stream_router(price_cache)` is a *factory taking the cache as an argument*, so the cache must be constructed **before** `include_router()` — which is before the app ever starts, and therefore **before lifespan runs**. This is the constraint that actually shapes `main.py`. Lifespan cannot be where the cache is born.

### Concrete `main.py`

```python
"""FastAPI application assembly."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api import chat, health, portfolio, watchlist
from app.db.init import init_db
from app.db.queries import list_watchlist_tickers
from app.db.connection import connect
from app.market import PriceCache, create_market_data_source, create_stream_router
from app.snapshots import snapshot_loop

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    """Build the application. One call site in prod, one per test module."""

    # 1. Shared state is created HERE, not in lifespan, because
    #    create_stream_router() needs the cache at include_router() time.
    price_cache = PriceCache()
    market_source = create_market_data_source(price_cache)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup. Blocking here is fine - nothing is being served yet.
        init_db()
        with connect() as conn:
            tickers = list_watchlist_tickers(conn)

        await market_source.start(tickers)
        snapshot = asyncio.create_task(snapshot_loop(price_cache))
        logger.info("Started: source=%s tickers=%d", market_source.source_name, len(tickers))

        yield

        # Shutdown, reverse order.
        snapshot.cancel()
        await asyncio.gather(snapshot, return_exceptions=True)
        await market_source.stop()

    app = FastAPI(title="FinAlly", lifespan=lifespan)

    # 2. Reachable from any handler via app/deps.py.
    app.state.price_cache = price_cache
    app.state.market_source = market_source

    # 3. Routers. Order among themselves is irrelevant - the paths are disjoint.
    app.include_router(create_stream_router(price_cache))   # FROZEN module
    app.include_router(portfolio.router)
    app.include_router(watchlist.router)
    app.include_router(chat.router)
    app.include_router(health.router)

    # 4. Frontend. Path operations take precedence, so this is a pure fallback.
    #    check_dir=False: the static dir only exists after the Docker build stage.
    app.frontend("/", directory=str(STATIC_DIR), fallback="index.html", check_dir=False)

    return app


app = create_app()
```

**Why a factory, not module-level `app = FastAPI()`:** tests get a fresh cache, a fresh source, and a fresh temp DB per module. It also mirrors the existing `create_stream_router` / `create_market_data_source` convention, so the codebase has one shape rather than two.

**Why `snapshot_loop` uses `asyncio.create_task` rather than a `BackgroundTasks`:** `BackgroundTasks` is per-request and dies with the response. A 30-second forever-loop is a lifespan-scoped task. Cancel it explicitly on shutdown and `gather(..., return_exceptions=True)` so the expected `CancelledError` does not surface as a shutdown error.

### If you must stay on `StaticFiles` (PLAN.md literal reading)

```python
from fastapi.staticfiles import StaticFiles
# ... every include_router() call FIRST ...
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
```

This works only because `mount()` is the **last** route registered. It is exactly the fragility PLAN.md warns about: any future `include_router()` appended below the mount silently 404s. If this path is taken, add a test that asserts `GET /api/health` returns 200 against the fully assembled app — it is the cheapest possible guard and it fails loudly the day someone reorders the file.

---

## Q2 — Injecting the Shared `PriceCache`

Four candidate patterns exist. Recommendation and rationale:

| Pattern | Verdict | Why |
|---------|---------|-----|
| Module-level singleton (`cache = PriceCache()` at import) | **Reject** | Directly contradicts the market module's documented design ("no global state at import time"). Breaks test isolation — every test module shares one cache. |
| Factory closure (`create_stream_router(cache)`) | **Keep where it exists** | Already used by the frozen SSE router. Correct, but forces every router into a `create_*_router()` function, which is ceremony for four thin routers. |
| Starlette lifespan `yield {"price_cache": cache}` → `request.state["price_cache"]` | **Reject** | Untyped dict access at every call site, shallow-copied per request, and — decisively — the cache must exist *before* lifespan runs (see Q1). |
| **`app.state` + a one-line `Depends` provider** | **Recommend** | Typed, overridable in tests, zero import-time state, one obvious place to look. |

### Concrete `app/deps.py`

```python
"""Dependency providers for shared application state."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import Depends, Request

from app.db.connection import connect
from app.market import MarketDataSource, PriceCache


def get_price_cache(request: Request) -> PriceCache:
    """The single PriceCache created in create_app()."""
    return request.app.state.price_cache


def get_market_source(request: Request) -> MarketDataSource:
    """The single MarketDataSource created in create_app()."""
    return request.app.state.market_source


def get_db():
    """A short-lived SQLite connection, committed or rolled back per request."""
    with connect() as conn:
        yield conn


Cache = Annotated[PriceCache, Depends(get_price_cache)]
Source = Annotated[MarketDataSource, Depends(get_market_source)]
Db = Annotated[sqlite3.Connection, Depends(get_db)]
```

Usage stays a single word per parameter:

```python
@router.get("/api/portfolio")
def get_portfolio(cache: Cache, db: Db) -> PortfolioResponse:
    ...
```

**Test override — the payoff:**

```python
app = create_app()
app.dependency_overrides[get_price_cache] = lambda: fixture_cache
```

Note `get_price_cache` is declared `def`, not `async def`. It performs no IO; FastAPI will run it in the threadpool, which for an attribute read is free either way. Declaring it `def` keeps it callable directly from sync test code.

**On the mixed convention:** the SSE router keeps closure injection (it is frozen), the new routers use `Depends`. Both read the same object. Document the reason once in `deps.py` rather than modifying tested code for cosmetic uniformity.

---

## Q3 — How Many Layers?

**Recommendation: two layers plus one narrow service seam. Not four.**

The rule that decides it: **a service module earns its existence only when two independent callers need identical logic.** Applied to this system, exactly two pieces qualify:

| Logic | Callers | Verdict |
|-------|---------|---------|
| Execute a trade | `POST /api/portfolio/trade`, `POST /api/chat` auto-execution | **Service.** Duplicating server-side fill price + cash check + auto-add-to-watchlist + snapshot write in two routers guarantees they drift. |
| Add / remove watchlist ticker | `POST/DELETE /api/watchlist`, `POST /api/chat`, and `execute_trade`'s auto-add | **Service.** Three callers. |
| Read portfolio + value it | `GET /api/portfolio` only | Router. ~15 lines. |
| Portfolio history | `GET /api/portfolio/history` only | Router. A `SELECT` and a shape. |
| Health | `GET /api/health` only | Router. |
| Snapshot loop | Its own task | Standalone module. |

So:

```
backend/app/
├── main.py                 # create_app(): cache, source, lifespan, routers, frontend
├── deps.py                 # Cache / Source / Db  Annotated providers
├── snapshots.py            # 30s lifespan task
├── market/                 # FROZEN
├── db/
│   ├── connection.py       # connect() -> contextmanager, WAL + busy_timeout
│   ├── schema.sql          # six CREATE TABLE IF NOT EXISTS
│   ├── init.py             # init_db(): apply schema, seed if empty
│   └── queries.py          # plain functions: (conn, ...) -> rows. No classes.
├── services/
│   ├── trading.py          # execute_trade()  <- two callers
│   └── watchlist.py        # add_ticker() / remove_ticker()  <- three callers
├── api/
│   ├── portfolio.py        # router; valuation inline
│   ├── watchlist.py        # router
│   ├── chat.py             # router
│   └── health.py           # router
└── llm/
    ├── client.py           # LiteLLM -> OpenRouter -> Cerebras
    ├── mock.py             # LLM_MOCK keyword contract
    ├── prompt.py           # system prompt + portfolio context builder
    └── schema.py           # structured output model
```

### Explicitly rejected as overengineering

- **A `Repository` class over SQLite.** `queries.py` with free functions taking a `sqlite3.Connection` is the same thing minus a constructor and an interface. The stale `__pycache__` hints at `repository.py`; do not resurrect it.
- **A separate `services/portfolio.py`.** Valuation is `cash + Σ(qty × cache.get_price(t))`. It has one caller. Putting it behind a module boundary adds a file and an import to save nothing.
- **Pydantic model files split from routers.** Response models live next to the router that returns them until there are two returners.
- **An ORM.** Six tables, no relations traversed, no migrations (lazy `CREATE TABLE IF NOT EXISTS`). SQLAlchemy would be more code than the schema.

**Layer dependency direction (enforce it):** `api/` → `services/` → `db/`, and anyone may read `market/`. Nothing in `db/` or `services/` imports from `api/`. `market/` imports nothing outside itself.

---

## Q4 — Blocking-IO Discipline

### The hazard is real, and it is specifically SQLite lock waits

A `sqlite3` read completes in microseconds; blocking the event loop for that is harmless. The danger is different: with `busy_timeout` set (and it **must** be set — omitting it is the single most common SQLite concurrency mistake, turning contention into an immediate `database is locked` error), a write that collides with the snapshot task's write **blocks for up to the timeout — seconds**. If that call sits directly inside an `async def`, it freezes the event loop, and therefore **every open SSE stream**, for the full duration. The connection dot goes yellow for every browser tab because one trade hit a lock.

### The rule

> **Default every endpoint to `def`. Use `async def` only when the body must `await` something. In those, route SQLite through `run_in_threadpool`.**

FastAPI's own guidance backs the default: *"When you declare a path operation function with normal `def` instead of `async def`, it is run in an external threadpool that is then awaited, instead of being called directly (as it would block the server)."* and *"If you just don't know, use normal `def`."*

### Endpoint-by-endpoint

| Endpoint | `def` / `async def` | Reason |
|----------|--------------------|--------|
| `GET /api/stream/prices` | `async def` | **FROZEN and correct.** A long-lived `def` streaming endpoint would occupy one of the ~40 AnyIO threadpool threads *permanently* — 40 browser tabs and the server deadlocks. |
| `GET /api/portfolio` | `def` | SQLite read + in-memory cache reads. Threadpool. |
| `GET /api/portfolio/history` | `def` | SQLite read only. |
| `POST /api/portfolio/trade` | **`async def`** | Must `await wait_for_price(cache, ticker, 2.0)` and `await source.add_ticker(...)`. Wrap the DB transaction in `run_in_threadpool`. |
| `GET /api/watchlist` | `def` | SQLite read + `cache.get_history()`. |
| `POST /api/watchlist` | **`async def`** | Must `await source.add_ticker(...)`. |
| `DELETE /api/watchlist/{ticker}` | **`async def`** | Must `await source.remove_ticker(...)`. |
| `GET /api/chat` | `def` | SQLite read only. |
| `POST /api/chat` | **`async def`** | Must `await litellm.acompletion(...)`, then `await` the trade service. |
| `GET /api/health` | `def` | Pure in-memory reads; `def` keeps it consistent and costs nothing. |

### The one wrapper

```python
"""app/services/trading.py"""
from starlette.concurrency import run_in_threadpool

from app.db.connection import connect
from app.market import PriceCache, wait_for_price


async def execute_trade(cache: PriceCache, source, ticker: str, side: str, quantity: float) -> dict:
    """Validate, fill at the server price, persist, snapshot. One code path."""
    fill_price = await wait_for_price(cache, ticker, timeout=2.0)  # raises ValueError -> 400
    await ensure_watchlisted(source, ticker)                       # invariant I1
    return await run_in_threadpool(_persist_trade, ticker, side, quantity, fill_price, cache)


def _persist_trade(ticker, side, quantity, fill_price, cache) -> dict:
    """Synchronous, transactional. Runs off the event loop."""
    with connect() as conn:            # BEGIN ... COMMIT / ROLLBACK
        ...                            # cash check, position upsert/delete, trades row
        write_snapshot(conn, total_value(conn, cache))
    return {...}
```

`starlette.concurrency.run_in_threadpool` is preferred over `asyncio.to_thread` here because it uses the same AnyIO threadpool (and its limiter) that FastAPI already uses for `def` endpoints — one pool to size, one pool to reason about. `asyncio.to_thread` spawns into a separate default executor.

### `connection.py`

```python
"""app/db/connection.py"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parents[3] / "db" / "finally.db"


@contextmanager
def connect():
    """A per-operation connection. Commits on success, rolls back on error."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")     # readers never block the writer
    conn.execute("PRAGMA busy_timeout=5000")    # wait for a lock, do not error
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

**Connection per operation, never shared across threads.** WAL gives one writer + many concurrent readers, which is exactly this workload: the snapshot task writes every 30s, trades write occasionally, everything else reads. `check_same_thread=False` is required because the threadpool hands work to arbitrary threads. Do not build a connection pool — SQLite connections are cheap and pooling adds a lifecycle to get wrong.

**The snapshot task must also use the threadpool**, or it blocks the loop for its whole write:

```python
async def snapshot_loop(cache: PriceCache, interval: float = 30.0) -> None:
    while True:
        await asyncio.sleep(interval)
        await run_in_threadpool(write_snapshot_if_changed, cache)
```

---

## Q5 — Data Flow, Traced

### (a) Page load

```
Browser GET /                → app.frontend() fallback → index.html + _next/* assets
  │
  ├─ GET /api/watchlist      → def handler → db.list_watchlist(conn)
  │                                        → cache.get(t) for price/open_price
  │                                        → cache.get_history(t) for ~60 sparkline points
  │                                          [DB: which tickers.  CACHE: all price data.]
  │
  ├─ GET /api/portfolio      → def handler → db.list_positions(conn), db.get_cash(conn)
  │                                        → cache.get_price(t) per position
  │                                          [DB: qty + avg_cost + cash.  CACHE: current price.]
  │
  ├─ GET /api/portfolio/history → def handler → db.list_snapshots(conn, limit, since)
  │                                          [DB only.]
  │
  ├─ GET /api/chat           → def handler → db.list_messages(conn, limit)
  │                                          [DB only.]
  │
  └─ EventSource /api/stream/prices  → FROZEN async generator
                                      → polls cache.version every 500ms
                                      → on change: cache.get_all() → one JSON event
                                      → ": ping" every 15s
                                        [CACHE only. Never touches the DB.]
```

**The split that matters:** the DB owns *what the user owns and watches*; the cache owns *what things are worth right now*. No endpoint reads a price from the DB, and nothing writes a price to it. The only place they meet is valuation.

### (b) Manual trade

```
TradeBar → POST /api/portfolio/trade {ticker, quantity, side}
   │
   ▼  api/portfolio.py  (async def)
   normalize_ticker(ticker)                      [market/tickers.py - shared rule]
   validate quantity > 0, finite, <= 4dp         → 400
   │
   ▼  services/trading.execute_trade()
   await wait_for_price(cache, ticker, 2.0)      [CACHE, may await up to 2s] → 400 on timeout
   await ensure_watchlisted(source, ticker)      [DB insert-or-ignore + await source.add_ticker]
   │                                              ^ holds invariant I1
   ▼  run_in_threadpool(_persist_trade)          [off the event loop]
      BEGIN
        buy : cash >= qty*fill  else 400 ; upsert position, recompute avg_cost
        sell: held >= qty       else 400 ; decrement, DELETE row if it hits 0
        INSERT trades (audit log, no reader)
        INSERT portfolio_snapshots (immediate, so the P&L chart shows the step)
      COMMIT
   │
   ▼  200 {ticker, side, quantity, fill_price, total_cost, cash_balance, executed_at}
   │
   ▼  Frontend: show fill_price, then REFETCH /api/portfolio + /api/watchlist
      (watchlist too, because the trade may have auto-added the ticker)
```

### (c) LLM-driven trade via chat

```
ChatPanel → POST /api/chat {message}
   │
   ▼  api/chat.py (async def)
   if not OPENROUTER_API_KEY:
        return 200 {message: "no API key configured", trades: [], watchlist_changes: []}
        ^ never raises, never fails startup
   │
   ▼  run_in_threadpool: db.list_messages(conn, limit)   [DB - conversation history]
      cache.get_all() + db positions/cash                [CACHE + DB - portfolio context]
   ▼  llm/prompt.build(system, portfolio_context, history, user_message)
   │
   ▼  LLM_MOCK=true ? llm/mock.respond(message)          [pure, keyword-triggered]
                    : await litellm.acompletion(...)     [NETWORK - the reason this is async]
   ▼  parse structured output → {message, trades[], watchlist_changes[]}
   │
   ▼  for each trade:            await services.trading.execute_trade(...)
      for each watchlist change: await services.watchlist.add/remove(...)
        ^^ IDENTICAL code path to the manual routes. Same validation, same fill rule,
           same auto-add, same 409. A failure is caught and its message is appended
           to the response actions rather than raising.
   │
   ▼  run_in_threadpool: INSERT chat_messages (user row, then assistant row w/ actions JSON)
   │
   ▼  200 {message, trades, watchlist_changes}
   │
   ▼  Frontend: append messages; if trades or watchlist_changes non-empty
                → REFETCH /api/portfolio + /api/watchlist
```

**The load-bearing property:** the chat router is a *caller* of the same services the REST routers call. It is not a parallel implementation. If `execute_trade` is the only function that can move cash, then manual and AI trades cannot diverge — and the E2E suite testing mock-mode chat is genuinely exercising trade logic, as PLAN.md section 9 asserts.

### (d) Watchlist add

```
Watchlist "+" → POST /api/watchlist {ticker}
   │
   ▼  api/watchlist.py (async def)
   normalize_ticker → ^[A-Z]{1,5}$ else 400
   │
   ▼  services/watchlist.add_ticker()
   run_in_threadpool: INSERT INTO watchlist ... ON CONFLICT DO NOTHING   [DB]
   await source.add_ticker(ticker)                                       [MARKET SOURCE]
        └─ synthesizes seed price + volatility from a hash of the symbol
        └─ seeds ~60 history points into the cache  → sparkline populated immediately
        └─ first cache.update() pins open_price     → change % starts at 0.00%, not garbage
   │
   ▼  201 → frontend refetches /api/watchlist (to get history + open_price)
   ▼  within ~500ms the next SSE frame includes the new ticker; no extra plumbing
```

**DELETE** is the mirror, with one extra gate: `SELECT 1 FROM positions WHERE ticker=?` → **409** if held. Then `DELETE FROM watchlist`, then `await source.remove_ticker()` (which also calls `cache.remove()`). Order matters: check the position *before* touching the source, so a rejected delete leaves the feed untouched.

---

## Q6 — Client-Side Derived State: Assessment

**Verdict: correct design, and the right one here.** A portfolio SSE channel would duplicate the price channel's data (positions change ~never; prices change constantly) and introduce two clocks to keep in sync. Computing on the client is strictly simpler *provided the invariants below hold* — and each one has a concrete failure mode if it does not.

### Invariants that must hold

| # | Invariant | Enforced by | If it breaks |
|---|-----------|-------------|--------------|
| **I1** | Every ticker with a position is on the watchlist, therefore in the cache, therefore in every SSE frame | Trade auto-adds to watchlist; `DELETE /api/watchlist/{t}` returns 409 when held | Client has a position with no live price. **Silently under-values the portfolio** — the worst failure mode because nothing errors. |
| **I2** | `cash_balance` and `positions[]` come from the **same** `/api/portfolio` response | Store them as one atomic object; never merge a new cash into old positions | Total is wrong by the trade amount until the next refetch. Two in-flight refetches can land out of order. |
| **I3** | Refetch after *every* server-side mutation the client did not compute itself | Manual trade response; chat response with non-empty `trades`/`watchlist_changes` | Positions silently stale. Note: an LLM trade that **fails** validation returns empty arrays — but the error path may still have partially applied earlier trades in the same batch. **Refetch whenever any action was attempted, not only when it succeeded.** |
| **I4** | Server valuation (`portfolio_snapshots`) and client valuation use the **same** formula | Single documented formula: `cash + Σ(qty × price)` | The P&L chart's historical line and its live endpoint disagree — a visible kink at "now". |

### Failure modes and mitigations

1. **Missing price for a held ticker.** Even with I1, there is a window: a ticker added seconds ago may have a position before its first tick. **Mitigation: value at `avg_cost` when no live price exists, never at 0 and never by dropping the row.** Degrades to "flat", which is honest.
2. **Frozen-but-plausible display.** If the SSE connection drops, prices stop updating but the numbers still look live and correct. The connection dot is the *only* signal, which makes it load-bearing UI, not decoration. Implement it exactly as PLAN.md section 2 specifies (observable `EventSource.readyState` + a 30s silence timer fed by heartbeats *and* price events).
3. **Refetch/frame race.** A trade completes, the SSE frame arrives, then the `/api/portfolio` refetch resolves. Between frame and refetch the total is computed from stale positions. This is **self-healing** — the next frame (≤500ms) recomputes against the refetched positions. Do not add a lock; do avoid rendering a "settling" intermediate as a flash.
4. **Header total vs. `total_value` in the API response.** The response carries a server-computed `total_value` from a different instant. **Never render both.** Use the API's `total_value` only as a sanity check in tests; the header always shows the client computation.
5. **Fractional-share float drift.** `qty × price` over many trades accumulates float error. At $10k with 4dp quantities this is invisible, but round only at display time, never in the accumulator.

---

## Q7 — Frontend Component Architecture

### Sizing the problem honestly

The instinct is to fear a re-render storm. The actual load is milder than it looks: **one SSE event every ~500ms carrying all tickers**, not one event per ticker. That is **2 store writes per second**, not 20. Re-rendering a 10-row table twice a second is nothing.

The real risk is not frequency — it is **object identity**. Every frame produces a brand-new `PriceUpdate` object for every ticker, so any selector returning an object re-renders unconditionally. React compares snapshots with `Object.is`; a fresh object always fails that check. Hence the single most important rule below.

### Recommended shape

```
frontend/
├── app/
│   ├── layout.tsx
│   └── page.tsx                # 'use client'; composes panels. One route.
├── lib/
│   ├── priceStore.ts           # EventSource + store. MODULE SCOPE, zero React.
│   ├── appStore.ts             # zustand: cash, positions, watchlist, chat, selectedTicker
│   ├── api.ts                  # typed fetch wrappers + the one refetch() helper
│   └── valuation.ts            # THE formula. Imported by header, table, heatmap, chart.
└── components/
    ├── Header.tsx  ConnectionDot.tsx  Watchlist.tsx  Sparkline.tsx
    ├── MainChart.tsx  Heatmap.tsx  PnlChart.tsx  PositionsTable.tsx
    ├── TradeBar.tsx  ChatPanel.tsx
```

### Where the EventSource lives

**Module scope in `priceStore.ts`, created lazily on first subscribe — not inside a component.**

React 19 StrictMode double-invokes effects in dev, so an EventSource created in a `useEffect` opens two connections, and a naive cleanup closes the surviving one. Owning the connection outside React sidesteps the whole class of bug and means panels can mount and unmount freely without touching the transport.

```ts
// lib/priceStore.ts  — no React imports
type Price = { price: number; openPct: number; direction: 'up' | 'down' | 'flat' };

let prices: Record<string, Price> = {};
let source: EventSource | null = null;
let status: 'connecting' | 'open' | 'closed' = 'closed';
const listeners = new Set<() => void>();

const emit = () => listeners.forEach((l) => l());

function connect() {
  source = new EventSource('/api/stream/prices');
  source.onopen = () => { status = 'open'; emit(); };
  source.onerror = () => {
    status = source?.readyState === EventSource.CLOSED ? 'closed' : 'connecting';
    emit();                       // EventSource retries on its own (server sends retry: 1000)
  };
  source.onmessage = (e) => {
    const frame = JSON.parse(e.data);
    const next: Record<string, Price> = {};
    for (const t in frame) {
      next[t] = {
        price: frame[t].price,
        openPct: frame[t].change_from_open_percent,
        direction: frame[t].direction,
      };
    }
    prices = next;                // whole-object swap; selectors pull primitives out
    emit();
  };
}

export function subscribe(listener: () => void) {
  listeners.add(listener);
  if (!source) connect();
  return () => { listeners.delete(listener); };   // keep the connection open
}

export const getPrices = () => prices;
export const getStatus = () => status;
```

### How panels subscribe without storms

```ts
// lib/usePrice.ts
import { useSyncExternalStore } from 'react';
import { subscribe, getPrices } from './priceStore';

/** Subscribe to ONE primitive. Object.is on a number => no render when unchanged. */
export function usePrice(ticker: string): number | undefined {
  return useSyncExternalStore(
    subscribe,
    () => getPrices()[ticker]?.price,     // primitive, NOT the object
    () => undefined,                      // SSR/static-export snapshot
  );
}
```

**The four rules that make this work:**

1. **Select primitives, never objects.** `getPrices()[t]?.price` returns a `number`; `getPrices()[t]` returns a fresh object every frame and defeats the comparison entirely. This is the documented #1 `useSyncExternalStore` performance bug.
2. **`subscribe` must be a stable module-level reference.** React tears down and re-establishes the subscription whenever the `subscribe` identity changes. Defining it in `priceStore.ts` guarantees stability.
3. **Provide `getServerSnapshot`** (the third argument). A static export prerenders at build time; without it, hydration throws.
4. **Push the subscription to the leaf.** `<PriceCell ticker="AAPL" />` subscribes; `<Watchlist />` does not. Then a tick in NVDA re-renders one `<td>`, not the table.

### State library recommendation

**Zustand for application state; hand-rolled store for prices.** Rationale:

- The price store is ~40 lines and needs no library — and putting a 2Hz firehose through a general store adds an indirection for nothing.
- Application state (cash, positions, watchlist, chat, `selectedTicker`) is classic shared state read by six panels and written by three actions. Prop-drilling it is worse; Context re-renders every consumer on every change. Zustand is `useSyncExternalStore` with selectors, ~1KB, and gives per-field subscription for free (use `useShallow` for array/object slices).
- **Do not use React Context for either.** Context propagates to all consumers regardless of what they read — the exact bottleneck this architecture must avoid.
- Do not add TanStack Query. There are four GET endpoints, refetch is explicitly event-driven (not cache-invalidation-driven), and there is no polling. It would add a caching model to fight against the spec's one refetch rule.

### Charts and flashes — the two real cost centers

- **Disable Recharts animation everywhere on live data:** `isAnimationActive={false}` **and** `animationDuration={0}`. Setting only `isAnimationActive={false}` still leaves dots rendering after a ~1500ms default delay — a known Recharts behavior that reads as lag on a live chart.
- **Throttle chart inputs to ~1Hz.** The watchlist price cells should update at full 2Hz (that is the drama), but re-laying out a 60-point line chart, a treemap, and 10 sparklines twice a second is wasted work. Buffer chart data in the store and expose a coarser selector.
- **Memoize chart subtrees** with `React.memo` and pass stable, `useMemo`'d data arrays. A new array literal each render forces a full Recharts re-layout.
- **Price flash via CSS, not React timers.** Ten per-cell `setTimeout`s firing twice a second is avoidable churn. Apply a class derived from `direction` and let a CSS `transition`/`animation` fade it; restart the animation by keying on the tick timestamp.

---

## Q8 — Build Order

### Assessment of PLAN.md section 13

The proposed order (DB+portfolio → watchlist → shell → charts → chat → Docker → E2E) is sound in its dependency logic. Two changes are worth making:

**Change 1 — Split a "spine" phase off the front.** PLAN.md folds app assembly into "database and portfolio API." But `main.py` is what makes the *already-built* SSE router reachable for the first time, and it is a prerequisite for literally every other step including the frontend. Isolating it makes step 2 and step 3 genuinely parallel instead of nominally so, and it delivers something verifiable in an afternoon: `/api/health` responds and prices stream in a browser.

**Change 2 — Move Docker forward.** This is the strongest recommendation here. Docker at step 7 means the single-origin static-serving path — the highest-risk integration in the system, and the one PLAN.md itself flags as "the most common way this architecture breaks" — is exercised for the first time *after* all the code exists. A walking-skeleton Dockerfile serving a placeholder `index.html` alongside a live `/api/health` proves the whole shape in one small phase, and every later phase inherits a working container instead of discovering one.

### Recommended sequence

| # | Phase | Depends on | Parallel with |
|---|-------|------------|---------------|
| **0** | **Housekeeping** — delete stale `__pycache__` under `app/{api,db,llm,services}`; `uv add litellm`; bump `fastapi>=0.141.1`; commit `.env.example` | — | — |
| **1** | **Spine** — `main.py` (`create_app`, lifespan, `app.state`), `deps.py`, `db/{connection,schema.sql,init,queries}.py`, mount frozen SSE router, `GET /api/health` | 0 | — |
| **2** | **Walking-skeleton Docker** — multi-stage Dockerfile, placeholder `static/index.html`, bind-mounted `db/`, start/stop scripts. Proves single-origin serving + volume persistence. | 1 | 3, 4 |
| **3** | **Portfolio API** — `services/trading.py`, `GET /api/portfolio`, `POST /api/portfolio/trade`, `GET /api/portfolio/history`, `snapshots.py` | 1 | 2, 4 |
| **4** | **Watchlist API** — `services/watchlist.py`, `GET/POST/DELETE /api/watchlist` | 1 | 2, 3 |
| **5** | **Frontend shell** — Next.js static export, `priceStore`, `appStore`, layout, header + connection dot, watchlist panel with flashes, trade bar, positions table | 1 (+3, 4 to be complete) | — |
| **6** | **Charts** — Recharts main chart, sparklines, treemap heatmap, P&L line | 3, 5 | 7a |
| **7a** | **Chat backend** — `llm/*`, `GET/POST /api/chat`, mock mode, auto-execution | 3, 4 | 6, 7b |
| **7b** | **Chat panel** — collapsible sidebar, history, loading state, inline action confirmations | 5 | 6, 7a |
| **8** | **Harden Docker** — real frontend build stage, `npm ci`, `uv sync --frozen --no-dev` | 2, 6, 7 | — |
| **9** | **E2E** — Playwright on the host against the container | 8 | — |

### What is genuinely independent

- **3 ∥ 4 ∥ 2.** All three depend only on phase 1 and touch disjoint files. This holds **only if all SQLite query functions land in phase 1** — including `add_watchlist_ticker`, which `execute_trade` needs for its auto-add. Put the queries in phase 1 and the two API phases never touch the same file. Skip that and 3 and 4 collide in `queries.py`.
- **7a ∥ 7b.** The chat response shape is fully specified in PLAN.md section 9, so the panel can be built against a fixture while the backend is written.
- **6 ∥ 7a.** Different halves of the stack, no shared files.
- **5 can start after 1.** The shell needs the SSE stream (built) and `/api/health`; it can render against fixture data for portfolio/watchlist and switch to live calls when 3 and 4 land.

### What is *not* independent (common misreads)

- Portfolio API is **not** independent of the watchlist *concept* — `execute_trade` auto-adds. The dependency is on a DB function, which phase 1 provides; it is not a dependency on phase 4's router.
- Charts are **not** independent of the portfolio API — the heatmap needs positions and the P&L chart needs `/api/portfolio/history`.
- E2E is **not** parallelizable with feature work, because PLAN.md specifies it runs against the container, not a dev server.

### Phases likely to need their own deeper research

- **7a (LLM integration)** — structured-output reliability through OpenRouter→Cerebras, and LiteLLM's `response_format` behavior with that provider, are the least-pinned-down part of the system.
- **6 (Charts)** — Recharts `Treemap` API surface and its React 19 compatibility warrant a check before the phase starts.
- **8 (Docker)** — Next.js static export output path and the Node→Python stage copy are mechanical but easy to get subtly wrong.

---

## Anti-Patterns

### 1. Mounting `StaticFiles` at `/` before the routers
**What people do:** `app.mount("/", StaticFiles(...))` near the top of `main.py` because it reads like configuration.
**Why it's wrong:** the mount is a route registered in order. Everything registered after it is unreachable — and the failure is maximally confusing because the UI loads perfectly while every API call 404s.
**Instead:** `app.frontend("/", directory=..., fallback="index.html")`, which is order-independent by design. If staying on `StaticFiles`, mount last *and* add a test asserting `GET /api/health` → 200 on the assembled app.

### 2. A module-level `PriceCache` singleton
**What people do:** `price_cache = PriceCache()` at the top of a module so everything can `import` it.
**Why it's wrong:** contradicts the frozen market module's explicit no-global-state design, and every test module then shares mutable price state.
**Instead:** create it in `create_app()`, park it on `app.state`, reach it through a one-line `Depends` provider.

### 3. Blocking `sqlite3` calls inside `async def`
**What people do:** write the trade transaction directly in the async endpoint because "SQLite is fast."
**Why it's wrong:** it is fast until it waits on a lock, and then `busy_timeout` blocks the event loop for seconds — freezing every SSE stream in every open tab.
**Instead:** `def` endpoints by default; `run_in_threadpool` for DB work inside the few genuinely-async endpoints.

### 4. A long-lived streaming endpoint declared `def`
**What people do:** make the SSE endpoint `def` by reflex after adopting the "default to `def`" rule.
**Why it's wrong:** a `def` endpoint occupies an AnyIO threadpool thread for its entire life. An SSE stream never ends. ~40 tabs exhausts the pool and the whole app stops responding.
**Instead:** streaming endpoints are always `async def`. (The frozen router already is — do not "fix" it.)

### 5. Adding a second SSE channel for portfolio updates
**What people do:** push portfolio state down its own stream so the client does not compute.
**Why it's wrong:** two clocks, duplicated price data, and a whole new class of sync bug — for state that changes a few times per session.
**Instead:** one price channel; derive on the client; refetch on mutation.

### 6. Selecting objects from the price store
**What people do:** `useSyncExternalStore(subscribe, () => getPrices()[ticker])`.
**Why it's wrong:** a new object every frame fails `Object.is` unconditionally, so the selector re-renders every subscriber every frame — the storm the architecture was designed to avoid.
**Instead:** select primitives: `() => getPrices()[ticker]?.price`.

### 7. Leaving Recharts animations on for live data
**What people do:** accept the defaults.
**Why it's wrong:** every update animates from the old value, so a 2Hz feed is permanently mid-transition and reads as lag. `isAnimationActive={false}` alone is insufficient — dots still render on a ~1500ms delay.
**Instead:** `isAnimationActive={false}` **and** `animationDuration={0}`, plus throttled chart inputs.

### 8. Building a repository/UnitOfWork layer over SQLite
**What people do:** create `db/repository.py` with a class per table (the stale `__pycache__` suggests this was once attempted).
**Why it's wrong:** it is `queries.py` with extra constructors, against six tables with no relational traversal and no migration story.
**Instead:** free functions taking a connection.

### 9. Creating the `EventSource` inside a React component
**What people do:** `useEffect(() => { const es = new EventSource(...); return () => es.close(); }, [])`.
**Why it's wrong:** React 19 StrictMode double-invokes effects in dev, opening two connections and closing the wrong one; and the connection's lifetime becomes coupled to a component's.
**Instead:** module scope, lazily connected on first subscribe, never closed on unsubscribe.

---

## Scaling Considerations

This is a single-user local app; conventional user-count scaling is the wrong axis. The dimensions that actually bite:

| Dimension | Realistic range | What breaks first | Fix |
|-----------|-----------------|-------------------|-----|
| Tickers watched | 10 → 50 | SSE payload size (every frame carries all tickers); Massive free tier is 5 calls/min | Payload is fine to ~100. For Massive, batch the poll and lengthen the interval. |
| Open browser tabs | 1 → 10 | One `async` generator per tab polling `cache.version` every 500ms — cheap. `def` streaming would be fatal here (anti-pattern 4). | None needed. |
| `portfolio_snapshots` rows | 2/min → ~2,880/day | `GET /api/portfolio/history` unbounded scan | Already handled: `?limit=` default 500 + skip-unchanged writes. Add an index on `(user_id, recorded_at)`. |
| `chat_messages` rows | tens | LLM context window, not the DB | `?limit=` on history; cap the messages fed into the prompt. |
| Concurrent writers | snapshot task + trades | SQLite write lock | WAL + `busy_timeout=5000` + threadpool. Sufficient by a wide margin. |

**Do not optimize for anything beyond this.** The `user_id` column already buys future multi-user without a migration; that is the entire forward-compatibility budget this project should spend.

---

## Integration Points

### External services

| Service | Integration pattern | Gotchas |
|---------|---------------------|---------|
| Massive / Polygon.io | REST polling inside the frozen `MassiveDataSource` | Off-hours quotes are flat — no flashes, 0% changes. Documented as correct, not a bug. Simulator remains the demo default. |
| OpenRouter (LiteLLM → Cerebras) | `await litellm.acompletion(...)` with structured outputs, inside `async def` chat route | Missing key must degrade to a normal-shaped 200 response, never a startup failure. Verify `response_format` JSON-schema support survives OpenRouter's provider routing to Cerebras — flag for phase-level research. |

### Internal boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| market source ↔ `PriceCache` | Direct write | Frozen. Exactly one writer. |
| `PriceCache` ↔ SSE router | Closure injection via `create_stream_router(cache)` | Frozen. Version-counter polling, not diffing. |
| `PriceCache` ↔ new routers | `Annotated[PriceCache, Depends(get_price_cache)]` reading `app.state` | The one new injection pattern. |
| `api/` ↔ `services/` | Direct function calls | Services exist only for trade + watchlist (two/three callers each). |
| `services/` ↔ `db/` | Free functions taking a `sqlite3.Connection` | No ORM, no repository. |
| chat ↔ trading/watchlist | Same service functions as the REST routers | **Load-bearing.** Guarantees manual and AI paths cannot diverge. |
| backend ↔ frontend | Same origin, `/api/*`; `app.frontend()` fallback for everything else | No CORS by construction. |
| frontend transport ↔ React | Module-scope store + `useSyncExternalStore` primitive selectors | Keeps the connection out of the component lifecycle. |

---

## Sources

**First-party documentation (WebFetch — seam tier LOW for the provider; sources themselves are authoritative and were cross-checked against PyPI release metadata):**
- FastAPI — Lifespan Events: https://fastapi.tiangolo.com/advanced/events/
- FastAPI — Concurrency and async/await: https://fastapi.tiangolo.com/async/
- FastAPI — Static Files: https://fastapi.tiangolo.com/tutorial/static-files/
- FastAPI — Frontend (`app.frontend()` API): https://fastapi.tiangolo.com/tutorial/frontend/
- FastAPI — Release Notes (0.141.0 / 0.141.1, 2026-07-29): https://fastapi.tiangolo.com/release-notes/
- Starlette — Lifespan state: https://www.starlette.io/lifespan/
- PyPI — fastapi latest version 0.141.1 (direct API query)

**Community consensus (WebSearch — seam tier MEDIUM where cross-verified):**
- useSyncExternalStore selector/primitive guidance: [This Week In React](https://thisweekinreact.com/articles/useSyncExternalStore-the-underrated-react-api), [LogRocket](https://blog.logrocket.com/exploring-usesyncexternalstore-react-hook/), [Epic React](https://www.epicreact.dev/use-sync-external-store-demystified-for-practical-react-development-w5ac0)
- Zustand selective subscription / `useShallow`: [pmndrs discussion #1179](https://github.com/pmndrs/zustand/discussions/1179), [Avoid performance issues when using Zustand](https://dev.to/devgrana/avoid-performance-issues-when-using-zustand-12ee)
- SQLite WAL + `busy_timeout` discipline: [SkyPilot — Abusing SQLite to Handle Concurrency](https://blog.skypilot.co/abusing-sqlite-to-handle-concurrency/), [SQLite Concurrent Writes: WAL Mode and Lock Handling](https://adhdecode.com/articles/sqlite/sqlite-concurrent-writes-locking/)
- Recharts live-data performance: [Recharts Performance Optimization guide](https://recharts.github.io/en-US/guide/performance/), [recharts#945 — animation delay with isAnimationActive=false](https://github.com/recharts/recharts/issues/945), [recharts#287 — real-time chart](https://github.com/recharts/recharts/issues/287)
- StaticFiles shadowing API routes: [fastapi discussion #10458](https://github.com/fastapi/fastapi/discussions/10458)

**Direct source reading (HIGH confidence — the code is in this repo):**
- `backend/app/market/{cache,stream,interface,factory,models,__init__}.py`
- `backend/pyproject.toml`, `backend/CLAUDE.md`
- `planning/PLAN.md`, `.planning/PROJECT.md`, `.planning/codebase/ARCHITECTURE.md`

---
*Architecture research for: single-container real-time trading workstation with LLM copilot*
*Researched: 2026-08-05*
