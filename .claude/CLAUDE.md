<!-- GSD:project-start source:PROJECT.md -->

## Project

**FinAlly — AI Trading Workstation**

FinAlly (Finance Ally) is a single-container AI-powered trading workstation: live streaming market prices, a simulated $10,000 portfolio the user can trade, rich data visualization, and an LLM chat copilot that can analyze positions and execute trades on the user's behalf. It looks and feels like a modern Bloomberg terminal with an AI assistant docked beside it.

It is the capstone project for an agentic AI coding course — built entirely by orchestrated coding agents to demonstrate that AI agents can produce a production-quality full-stack application. The user is a single local operator running one Docker command and opening `http://localhost:8000`. No login, no signup, no real money.

**Core Value:** **The whole loop works as one experience: watch → trade → visualize → chat.** No single component is the point; the project is pointless unless a user can watch prices stream, place a trade, see the portfolio react, and ask the AI to do it for them — all in one continuous session.

### Constraints

- **Tech stack**: FastAPI + Python 3.12 (uv), Next.js + TypeScript static export, SQLite, Recharts, Tailwind — fixed by PLAN.md; chosen for single-container simplicity and teaching value
- **Architecture**: One container, one port (8000), one origin — no CORS, no service orchestration, no docker-compose in production
- **Transport**: SSE only for live data — one-way push is all that's needed and it works everywhere
- **LLM**: LiteLLM → OpenRouter → `openrouter/openai/gpt-oss-120b` with Cerebras inference, via the `cerebras` skill; structured outputs for trade parsing
- **Degradation**: A missing `OPENROUTER_API_KEY` must never fail startup — `/api/chat` returns a normal-shaped response explaining the key is absent, and every other feature works
- **Mount order**: `StaticFiles` must mount after every `/api/*` router — mounting first shadows the API and 404s every endpoint while the UI appears fine
- **Timestamps**: SSE carries Unix epoch seconds (float); every REST payload and every `*_at` DB column is an ISO 8601 UTC string. The two never mix in one payload
- **Code style**: No overengineering, no defensive programming, short modules and functions, no emojis in code or log output, docstrings over inline comments — per the project's global instructions
- **Reproducibility**: `npm ci` and `uv sync --frozen --no-dev` build from lockfiles; that is the reason the lockfiles exist

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python 3.12+ **[BUILT]** — `backend/app/market/` (market data subsystem: cache, simulator, Massive client, SSE stream). Declared via `requires-python = ">=3.12"` in `backend/pyproject.toml`.
- TypeScript **[SPEC ONLY]** — `planning/PLAN.md` specifies a Next.js/TypeScript frontend; `frontend/` is currently an empty directory with no `package.json`, no source files.
- None detected yet (no shell/SQL migration scripts present — `backend/app/db/` is empty).

## Runtime

- Python 3.12 (backend), managed via `uv`. A `.venv` exists at `backend/.venv` (interpreter `pyvenv.cfg` present), created by `uv sync`.
- Node.js — **[SPEC ONLY]** for the frontend (PLAN.md specifies Node 22 in the Docker build stage); no Node project exists yet at the repo's `frontend/` path.
- A separate Node project already exists at `test/` (Playwright), with its own `node_modules` — this is the E2E test harness, not the frontend app.
- `uv` (Python) — `backend/pyproject.toml` + `backend/uv.lock` (lockfile present, committed).
- npm — **[SPEC ONLY]** for `frontend/` (not yet present). `test/` (Playwright) has its own npm-managed `node_modules` but no visible `package.json` was found in the immediate `test/` directory during this scan (dependencies present, manifest not confirmed).

## Frameworks

- FastAPI `>=0.115.0` **[BUILT — dependency declared, no app wired up yet]** — declared in `backend/pyproject.toml`; used directly inside `backend/app/market/stream.py` to build an `APIRouter` for SSE (`create_stream_router`). No top-level FastAPI `app` instance / `main.py` exists yet — the market module only exposes a router factory for something else to mount.
- uvicorn `[standard]>=0.32.0` **[BUILT — declared, unused until an app exists]** — ASGI server dependency declared but no run script/entrypoint yet.
- Next.js **[SPEC ONLY]** — PLAN.md specifies a static-export Next.js frontend (`output: 'export'`); not present in code.
- pytest `>=8.3.0` + `pytest-asyncio >=0.24.0` + `pytest-cov >=5.0.0` **[BUILT]** — `backend/pyproject.toml` (`[project.optional-dependencies].dev`), configured in `[tool.pytest.ini_options]` (asyncio_mode = "auto", testpaths = ["tests"]). Tests exist under `backend/tests/market/` (and empty `backend/tests/{api,db,llm,services}/` directories awaiting future code), plus `backend/tests/conftest.py`.
- Playwright — **[BUILT as tooling, SPEC ONLY as tests]** — `test/` has `node_modules` including `playwright`, `@playwright/test`, `playwright-core` installed, and a `playwright-report/` from a prior run, but `test/specs/` contains no spec files yet.
- React Testing Library — **[SPEC ONLY]** (PLAN.md section 12 mentions it for frontend unit tests; no frontend project exists).
- ruff `>=0.7.0` **[BUILT]** — linter, configured in `backend/pyproject.toml` (`[tool.ruff]`: line-length 100, target py312, `select = ["E","F","I","N","W"]`, `ignore = ["E501"]`). Cache present at `backend/.ruff_cache/`.
- hatchling — build backend for the `finally-backend` Python package (`[build-system]` in `backend/pyproject.toml`).

## Key Dependencies

- `fastapi>=0.115.0` — HTTP framework, used for the SSE router today.
- `uvicorn[standard]>=0.32.0` — ASGI server.
- `numpy>=2.0.0` — used in `backend/app/market/simulator.py` for the correlated GBM math (Cholesky factorization for correlated ticker moves).
- `massive==2.2.0` — official client SDK for the Massive (Polygon.io) market data API; used in `backend/app/market/massive_client.py` (`from massive import RESTClient`, `from massive.rest.models import SnapshotMarketType`).
- `rich>=13.0.0` — used by `backend/market_data_demo.py` for a live terminal dashboard demo of the simulated price feed.
- `litellm` is present under `backend/.venv/Lib/site-packages/litellm/` but is **absent from both `backend/pyproject.toml` and `backend/uv.lock`**. This means the LLM integration PLAN.md specifies (LiteLLM → OpenRouter with Cerebras inference) has not yet been added as a real project dependency — the package appears to be a stray/pre-installed artifact in the virtualenv, not a reproducible lockfile entry. Whoever builds `backend/app/llm/` must run `uv add litellm` (or equivalent) to make this dependency real and reproducible.
- No OpenRouter SDK, no `openai` package, no structured-output library declared.
- SQLite via Python's stdlib `sqlite3` or an ORM — `backend/app/db/` is an empty directory; no schema SQL, no ORM (SQLAlchemy/etc.) declared in `pyproject.toml`.
- Docker — no `Dockerfile` or `docker-compose.yml` present at repo root despite being specified in PLAN.md section 11.

## Configuration

- `.env` exists at the project root (confirmed present, git-ignored via `.gitignore:138`). Contents not read (forbidden file — secrets). No `.env.example` file was found in this scan despite PLAN.md section 5 specifying one should be committed.
- Per PLAN.md, expected variables: `OPENROUTER_API_KEY`, `MASSIVE_API_KEY`, `LLM_MOCK`. Only `MASSIVE_API_KEY` is actually consumed by code today, in `backend/app/market/factory.py`:
- `backend/pyproject.toml` — Python project manifest, dependency groups, ruff/pytest/coverage config.
- `backend/uv.lock` — Python dependency lockfile (committed).
- No frontend build config (`next.config.js`, `tsconfig.json`, `tailwind.config.*`) exists yet.

## Platform Requirements

- Python >=3.12, `uv` package manager (per user's global CLAUDE.md: always `uv run`/`uv add`, never bare `python`/`pip`).
- Windows 11 dev environment (per environment info), Git Bash shell.
- Node.js for the future frontend and for the already-set-up Playwright E2E harness in `test/`.
- **[SPEC ONLY]** Single Docker container, multi-stage build (Node 22 → Python 3.12 slim), exposing port 8000, FastAPI serving both `/api/*` and the static Next.js export. None of this exists in code yet — no `Dockerfile`.

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Mandatory Rules (from CLAUDE.md — not optional)

- **No defensive programming.** Do not wrap code in speculative `try/except` "just in case."
- **No emojis** — never in code, print statements, log messages, docstrings, or comments.
- **Short modules, short functions.** Every file in `app/market/` is under 200 lines and does
- **Docstrings over inline comments.** Every module, class, and public function has a
- **Identify root cause before fixing.** Applies to future debugging work in this codebase, not
- **Use `uv`, never bare `python`/`pip`.** `uv run pytest`, `uv add <package>`,
- **Use latest library APIs** — the codebase already does this (see below).

## Naming Patterns

- One module per responsibility, `lowercase_with_underscores.py`: `cache.py`, `models.py`,
- Test files mirror the module they test 1:1: `app/market/cache.py` → `tests/market/test_cache.py`.
- A conformance suite that must pass for *every* implementation of an interface gets its own file
- PascalCase. Concrete implementations are named `<Thing><Role>`: `SimulatorDataSource`,
- `snake_case` throughout. Private/internal methods and module-level helpers prefixed with a
- Boolean-returning or predicate-style helpers read as questions where natural
- `dataclass(frozen=True, slots=True)` for immutable value objects (`PriceUpdate` in
- Abstract base classes via `abc.ABC` + `@abstractmethod` for anything with multiple
- Module-level constants in `SCREAMING_SNAKE_CASE`: `HISTORY_POINTS`, `TRADING_SECONDS_PER_YEAR`,

## Code Style

- `ruff` is the only configured tool (`backend/pyproject.toml`), rule set `["E", "F", "I", "N", "W"]`
- `line-length = 100`, `target-version = "py312"`.
- Run: `uv run --extra dev ruff check app/ tests/`. No `black`/`ruff format` config present —
- `from __future__ import annotations` is the first import in every module — always add it to new
- Full type hints on every function signature, including private helpers and test fixtures where
- `numpy` used with modern vectorized calls (`np.random.standard_normal`, matrix `@` multiply) —
- `asyncio.create_task(..., name="simulator-loop")` — tasks are named for observability.

## Import Organization

## Error Handling

- **Raise, don't swallow.** Validation failures raise plain `ValueError` with a **user-facing
- **One broad `except Exception` exists, and it is justified in a comment.** In
- **Degrade rather than crash on unreachable-but-possible failure**, with a `logger.error` and an
- Idempotent lifecycle methods (`stop()`) tolerate being called when already stopped/never

## Logging

- Standard library `logging`, one `logger = logging.getLogger(__name__)` per module.
- **No emojis, ever**, in log messages.
- `logger.info` for lifecycle events (start/stop/add/remove ticker, client connect/disconnect).
- `logger.debug` for high-frequency internal events (simulator shock events).
- `logger.exception` (not `logger.error`) when inside an `except` block, so the traceback is
- `logger.error` for a defended-against-but-unreachable condition — see
- Use `%s`-style lazy formatting, not f-strings, in log calls: `logger.info("Simulator started

## Comments

- **Docstrings carry the "why," not inline comments.** Module docstrings state the module's
- Inline `#` comments are rare and reserved for explaining a specific non-obvious choice at that

## Function Design

- **Size:** functions stay small and single-purpose; the largest function in the market module
- **Pure vs. I/O separated deliberately.** `GBMSimulator` (in `simulator.py`) is explicitly "pure
- **Parameters:** keyword defaults for tunables that tests need to override (`update_interval`,
- **Return values:** prefer returning plain dicts/dataclasses over mutating passed-in state where

## Module Design

- **Explicit `__all__` in the package `__init__.py`**, with a docstring "Public API" list that
- **Interface + factory pattern for swappable implementations.** `MarketDataSource` (ABC) +
- **Router factories, not module-level routers.** `create_stream_router(price_cache)` builds and
- **One shared validation rule, one place.** Ticker validation lives in exactly one function

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## Build Status

## System Overview (Built: Market Data Subsystem)

```text

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

- Both data sources implement the same `MarketDataSource` ABC; no downstream code branches on which source is active
- `PriceCache` is the only coupling point — producers write, consumers read, no direct producer→consumer reference
- Version counter (`PriceCache.version`) enables cheap change detection in the SSE loop rather than diffing payloads
- Fully async at the boundary (`start`/`stop`/`add_ticker`/`remove_ticker` are coroutines); `get_tickers()` is deliberately synchronous since it's called from request handlers

## Layers (Built)

- Purpose: produce realistic price ticks
- Location: `backend/app/market/simulator.py`, `backend/app/market/massive_client.py`
- Contains: GBM math with Cholesky-correlated sector moves, random shock events; REST polling and response parsing for Massive
- Depends on: `seed_prices.py` for initial parameters, `models.py` for `PriceUpdate`
- Used by: writes into `PriceCache`
- Purpose: single source of truth for "current price"
- Location: `backend/app/market/cache.py`
- Contains: thread-safe dict of ticker → `PriceUpdate`, version counter
- Depends on: `models.py`
- Used by: `stream.py` (SSE), and will be used by the planned portfolio/trade services
- Purpose: push price updates to the browser
- Location: `backend/app/market/stream.py`
- Contains: SSE generator emitting one event with all tickers per change, 15s heartbeat comment frames
- Depends on: `PriceCache`
- Used by: the (planned) FastAPI app's route registration

## Data Flow

### Primary Price Path (Built)

- All state lives in the single in-process `PriceCache` instance; no persistence, no cross-process sharing. This is explicitly designed to support a future multi-user scenario without changing the data layer (per `planning/PLAN.md` section 6).

## Key Abstractions (Built)

- Purpose: represents any price provider (simulated or real) behind one interface
- Examples: `SimulatorDataSource`, `MassiveDataSource` (both in `backend/app/market/`)
- Pattern: Strategy — swap implementation via `create_market_data_source()`, no other code branches on source type
- Purpose: immutable snapshot of one ticker's price at one moment
- Location: `backend/app/market/models.py`
- Pattern: value object; carries `ticker`, `price`, `previous_price`, `timestamp`, and computed `change`/`change_percent`/`direction`, plus `to_dict()` for SSE serialization

## Entry Points (Built)

- Location: `backend/app/market/stream.py` — `create_stream_router(price_cache)` returns a FastAPI `APIRouter`
- Triggers: mounted into a FastAPI app (the app itself does not yet exist in code) at `GET /api/stream/prices`
- Responsibilities: long-lived SSE connection, emits price diffs plus heartbeats, exits cleanly on client disconnect
- Location: `backend/market_data_demo.py`
- Triggers: `uv run market_data_demo.py`
- Responsibilities: standalone Rich-terminal dashboard exercising the simulator directly, not part of the served app

## Planned Architecture (Not Yet Built)

```text

```

- `backend/app/api/` — FastAPI routers: `portfolio.py`, `watchlist.py`, `chat.py`, `health.py`
- `backend/app/services/` — business logic: `portfolio.py`, `trading.py`, `watchlist.py`, `snapshots.py`
- `backend/app/db/` — `connection.py`, `init.py` (lazy schema creation + seeding), `repository.py`
- `backend/app/llm/` — `client.py` (LiteLLM/OpenRouter/Cerebras), `mock.py` (LLM_MOCK), `prompt.py`, `schema.py` (structured output schema)
- `backend/app/main.py` — FastAPI app assembly; must register all `/api/*` routers before mounting static files (mount-order hazard called out explicitly in `planning/PLAN.md` section 11)
- `frontend/` — Next.js TypeScript static export (`output: 'export'`), consuming `/api/*` and `/api/stream/prices`
- `Dockerfile`, `docker-compose.yml`, `scripts/start_*`, `scripts/stop_*` — containerization, not present
- `test/specs/` — Playwright E2E specs run on the host, directory exists but is empty

## Architectural Constraints (Built Portion)

- **Threading:** `PriceCache` is documented as thread-safe (used from an asyncio background task and from synchronous request handlers); the simulator's tick loop runs as an asyncio task, not a separate OS thread
- **Global state:** none at import time — `PriceCache` and each `MarketDataSource` implementation are instantiated explicitly by the caller (see `backend/app/market/__init__.py` docstring for the intended lifecycle: `cache = PriceCache(); source = create_market_data_source(cache)`), not module-level singletons
- **Circular imports:** none observed; `market/` submodules import only `models.py`, `interface.py`, `cache.py`, `tickers.py`, `seed_prices.py` in a strict one-directional graph
- **No app assembly exists yet:** there is no `backend/app/main.py`, so the market module's router is not currently mounted anywhere; it must be wired into a FastAPI app with `/api/*` routers registered before any static-file mount

## Anti-Patterns

## Error Handling (Built Portion)

## Cross-Cutting Concerns (Built Portion)

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

| Skill | Description | Path |
|-------|-------------|------|
| cerebras-inference | Use this to write code to call an LLM using LiteLLM and OpenRouter with the Cerebras inference provider | `.claude/skills/cerebras/SKILL.md` |
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
