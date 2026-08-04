<!-- refreshed: 2026-08-04 -->
# Architecture

**Analysis Date:** 2026-08-04

## Build Status

Only the market data subsystem is implemented in code today: `backend/app/market/` plus its tests in `backend/tests/market/`. Everything else described below for the rest of the platform — portfolio API, watchlist API, database layer, LLM/chat integration, frontend, Docker — is **planned, not built**. `.pyc` files in `backend/app/__pycache__/`, `backend/app/api/__pycache__/`, `backend/app/db/__pycache__/`, `backend/app/llm/__pycache__/`, and `backend/app/services/__pycache__/` are leftover bytecode from source that no longer exists on disk (the corresponding `.py` files are absent), so treat those directory names as a strong hint of the intended shape, not as evidence the code exists. `frontend/` exists only as an empty directory. There is no `Dockerfile`, no `docker-compose.yml`, and `scripts/` and `test/specs/` are empty (aside from `test/node_modules` from an `npm install`).

This document describes the actual architecture of the built portion (market data) in detail, and the planned architecture of the rest (from `planning/PLAN.md`) marked explicitly as planned.

## System Overview (Built: Market Data Subsystem)

```text
┌─────────────────────────────────────────────────────────────┐
│              MarketDataSource (ABC)                         │
│              `backend/app/market/interface.py`               │
├──────────────────────────┬───────────────────────────────────┤
│   SimulatorDataSource     │   MassiveDataSource                │
│  `simulator.py` (GBM)     │  `massive_client.py` (Polygon.io)  │
│  default, no API key      │  used when MASSIVE_API_KEY is set  │
└─────────────┬─────────────┴───────────────┬───────────────────┘
              │                              │
              ▼                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   PriceCache (thread-safe)                   │
│                  `backend/app/market/cache.py`                │
│         holds latest/previous PriceUpdate per ticker,         │
│         a monotonic version counter for change detection      │
└───────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              SSE stream router (FastAPI)                      │
│              `backend/app/market/stream.py`                    │
│              GET /api/stream/prices                            │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| `PriceUpdate` | Immutable snapshot of a single ticker's price state | `backend/app/market/models.py` |
| `MarketDataSource` (ABC) | Contract for any price provider: `start/stop/add_ticker/remove_ticker/get_tickers` | `backend/app/market/interface.py` |
| `PriceCache` | Thread-safe in-memory store; single point of truth read by SSE and (planned) portfolio valuation | `backend/app/market/cache.py` |
| `SimulatorDataSource` / `GBMSimulator` | Default price generator using correlated Geometric Brownian Motion | `backend/app/market/simulator.py` |
| `MassiveDataSource` | REST-polling client against Polygon.io via the `massive` package | `backend/app/market/massive_client.py` |
| `create_market_data_source` | Factory selecting simulator vs. Massive based on `MASSIVE_API_KEY` | `backend/app/market/factory.py` |
| `create_stream_router` | Builds the FastAPI SSE router bound to a given cache instance | `backend/app/market/stream.py` |
| Seed data / correlation params | Realistic seed prices, per-ticker drift/volatility, sector correlation groups; synthesizes params for unknown tickers | `backend/app/market/seed_prices.py` |
| Ticker validation | Shared `TICKER_PATTERN` regex and `normalize_ticker()` used by both manual and (planned) LLM trade/watchlist paths | `backend/app/market/tickers.py` |

## Pattern Overview

**Overall:** Strategy pattern for market data sourcing, with a single shared mutable cache decoupling producers (simulator or Massive poller) from consumers (SSE stream, and later portfolio valuation/trade execution).

**Key Characteristics:**
- Both data sources implement the same `MarketDataSource` ABC; no downstream code branches on which source is active
- `PriceCache` is the only coupling point — producers write, consumers read, no direct producer→consumer reference
- Version counter (`PriceCache.version`) enables cheap change detection in the SSE loop rather than diffing payloads
- Fully async at the boundary (`start`/`stop`/`add_ticker`/`remove_ticker` are coroutines); `get_tickers()` is deliberately synchronous since it's called from request handlers

## Layers (Built)

**Data generation layer:**
- Purpose: produce realistic price ticks
- Location: `backend/app/market/simulator.py`, `backend/app/market/massive_client.py`
- Contains: GBM math with Cholesky-correlated sector moves, random shock events; REST polling and response parsing for Massive
- Depends on: `seed_prices.py` for initial parameters, `models.py` for `PriceUpdate`
- Used by: writes into `PriceCache`

**Cache layer:**
- Purpose: single source of truth for "current price"
- Location: `backend/app/market/cache.py`
- Contains: thread-safe dict of ticker → `PriceUpdate`, version counter
- Depends on: `models.py`
- Used by: `stream.py` (SSE), and will be used by the planned portfolio/trade services

**Transport layer:**
- Purpose: push price updates to the browser
- Location: `backend/app/market/stream.py`
- Contains: SSE generator emitting one event with all tickers per change, 15s heartbeat comment frames
- Depends on: `PriceCache`
- Used by: the (planned) FastAPI app's route registration

## Data Flow

### Primary Price Path (Built)

1. `create_market_data_source(cache)` selects `SimulatorDataSource` or `MassiveDataSource` based on `MASSIVE_API_KEY` (`backend/app/market/factory.py`)
2. `source.start(tickers)` seeds ~60 points of GBM history per ticker and begins a background task producing ticks roughly every 500ms (`backend/app/market/simulator.py`)
3. Each tick calls `PriceCache.update(ticker, price)`, which stores a new `PriceUpdate` and increments `PriceCache.version` (`backend/app/market/cache.py`)
4. `_generate_events()` in the SSE router polls `price_cache.version` every 500ms; on change it serializes `price_cache.get_all()` into one JSON event keyed by ticker (`backend/app/market/stream.py:55-98`)
5. A heartbeat comment frame (`: ping`) is emitted every 15s regardless of price activity (`backend/app/market/stream.py:90-93`)

**State Management:**
- All state lives in the single in-process `PriceCache` instance; no persistence, no cross-process sharing. This is explicitly designed to support a future multi-user scenario without changing the data layer (per `planning/PLAN.md` section 6).

## Key Abstractions (Built)

**`MarketDataSource` (ABC):**
- Purpose: represents any price provider (simulated or real) behind one interface
- Examples: `SimulatorDataSource`, `MassiveDataSource` (both in `backend/app/market/`)
- Pattern: Strategy — swap implementation via `create_market_data_source()`, no other code branches on source type

**`PriceUpdate` (frozen dataclass):**
- Purpose: immutable snapshot of one ticker's price at one moment
- Location: `backend/app/market/models.py`
- Pattern: value object; carries `ticker`, `price`, `previous_price`, `timestamp`, and computed `change`/`change_percent`/`direction`, plus `to_dict()` for SSE serialization

## Entry Points (Built)

**SSE stream router:**
- Location: `backend/app/market/stream.py` — `create_stream_router(price_cache)` returns a FastAPI `APIRouter`
- Triggers: mounted into a FastAPI app (the app itself does not yet exist in code) at `GET /api/stream/prices`
- Responsibilities: long-lived SSE connection, emits price diffs plus heartbeats, exits cleanly on client disconnect

**Demo entry point:**
- Location: `backend/market_data_demo.py`
- Triggers: `uv run market_data_demo.py`
- Responsibilities: standalone Rich-terminal dashboard exercising the simulator directly, not part of the served app

## Planned Architecture (Not Yet Built)

The following is the intended shape per `planning/PLAN.md`, evidenced partly by stale `__pycache__` directory names (`app/api/`, `app/db/`, `app/llm/`, `app/services/`) whose `.py` sources are currently absent:

```text
┌─────────────────────────────────────────────────────────────┐
│  FastAPI app (single process, port 8000)         [PLANNED]   │
│  `backend/app/main.py`                                        │
├──────────────┬──────────────┬──────────────┬─────────────────┤
│  api/         │  services/    │  db/          │  llm/            │
│  routers      │  business     │  schema +     │  LiteLLM/        │
│  (portfolio,  │  logic        │  lazy init +  │  OpenRouter via  │
│  watchlist,   │  (portfolio,  │  repository   │  Cerebras,       │
│  chat,        │  trading,     │               │  structured      │
│  health)      │  watchlist,   │               │  outputs, mock   │
│               │  snapshots)   │               │  mode            │
└──────┬────────┴──────┬────────┴──────┬────────┴────────┬────────┘
       │                │               │                 │
       ▼                ▼               ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│  SQLite (`db/finally.db`), reads live prices from market.cache │
└─────────────────────────────────────────────────────────────┘
       ▲
       │ serves static export as fallback route
┌─────────────────────────────────────────────────────────────┐
│  frontend/ — Next.js static export        [PLANNED, empty dir]│
└─────────────────────────────────────────────────────────────┘
```

**Planned layers** (directory names only exist as stale `.pyc` artifacts today):
- `backend/app/api/` — FastAPI routers: `portfolio.py`, `watchlist.py`, `chat.py`, `health.py`
- `backend/app/services/` — business logic: `portfolio.py`, `trading.py`, `watchlist.py`, `snapshots.py`
- `backend/app/db/` — `connection.py`, `init.py` (lazy schema creation + seeding), `repository.py`
- `backend/app/llm/` — `client.py` (LiteLLM/OpenRouter/Cerebras), `mock.py` (LLM_MOCK), `prompt.py`, `schema.py` (structured output schema)
- `backend/app/main.py` — FastAPI app assembly; must register all `/api/*` routers before mounting static files (mount-order hazard called out explicitly in `planning/PLAN.md` section 11)
- `frontend/` — Next.js TypeScript static export (`output: 'export'`), consuming `/api/*` and `/api/stream/prices`
- `Dockerfile`, `docker-compose.yml`, `scripts/start_*`, `scripts/stop_*` — containerization, not present
- `test/specs/` — Playwright E2E specs run on the host, directory exists but is empty

**Build order** (per `planning/PLAN.md` section 13, steps 2-8 not started):
1. ~~Session baseline in market module~~ — status unclear; `PriceCache`/`PriceUpdate` in the current code do not expose `open_price` / `change_from_open_percent` fields called for by the spec (see CONCERNS.md)
2. Database and portfolio API
3. Watchlist API
4. Frontend shell
5. Charts
6. Chat
7. Docker and start/stop scripts
8. E2E tests

## Architectural Constraints (Built Portion)

- **Threading:** `PriceCache` is documented as thread-safe (used from an asyncio background task and from synchronous request handlers); the simulator's tick loop runs as an asyncio task, not a separate OS thread
- **Global state:** none at import time — `PriceCache` and each `MarketDataSource` implementation are instantiated explicitly by the caller (see `backend/app/market/__init__.py` docstring for the intended lifecycle: `cache = PriceCache(); source = create_market_data_source(cache)`), not module-level singletons
- **Circular imports:** none observed; `market/` submodules import only `models.py`, `interface.py`, `cache.py`, `tickers.py`, `seed_prices.py` in a strict one-directional graph
- **No app assembly exists yet:** there is no `backend/app/main.py`, so the market module's router is not currently mounted anywhere; it must be wired into a FastAPI app with `/api/*` routers registered before any static-file mount

## Anti-Patterns

None observed in the built market module — it is small, tested (per `planning/MARKET_DATA_SUMMARY.md`: 73 tests, 84% coverage), and its code review issues (lazy imports, missing public accessor, unused constants) were already resolved. See CONCERNS.md for the one specification gap (missing session-baseline fields) that is a known next step, not an anti-pattern in the existing code.

## Error Handling (Built Portion)

**Strategy:** the SSE generator handles `asyncio.CancelledError` explicitly to log and re-raise on disconnect (`backend/app/market/stream.py:96-98`); no other explicit error handling is visible in the market module — ticker validation errors are expected to surface at the `tickers.py` normalization boundary rather than deep in the simulator.

## Cross-Cutting Concerns (Built Portion)

**Logging:** standard library `logging` module, used in `stream.py` for connect/disconnect/cancel events (`logger = logging.getLogger(__name__)`)
**Validation:** ticker symbols validated once via `TICKER_PATTERN`/`normalize_ticker()` in `backend/app/market/tickers.py`, intended to be shared by manual and LLM-driven trade/watchlist paths per `planning/PLAN.md`
**Authentication:** none — single-user app by design (`user_id` defaults to `"default"` everywhere per the plan, not yet implemented in code)

---

*Architecture analysis: 2026-08-04*
