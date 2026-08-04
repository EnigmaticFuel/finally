# Codebase Structure

**Analysis Date:** 2026-08-04

## Directory Layout

```
finally/
├── backend/                      # uv-managed Python project (FastAPI)
│   ├── app/
│   │   ├── __init__.py
│   │   └── market/                # BUILT — market data subsystem
│   │       ├── __init__.py        # Public API re-exports
│   │       ├── models.py          # PriceUpdate dataclass
│   │       ├── interface.py       # MarketDataSource ABC
│   │       ├── cache.py           # PriceCache, wait_for_price()
│   │       ├── simulator.py       # GBMSimulator, SimulatorDataSource
│   │       ├── massive_client.py  # MassiveDataSource (Polygon.io)
│   │       ├── seed_prices.py     # Seed prices, GBM params, correlation groups
│   │       ├── tickers.py         # TICKER_PATTERN, normalize_ticker()
│   │       ├── factory.py         # create_market_data_source()
│   │       └── stream.py          # create_stream_router() — SSE endpoint
│   ├── tests/
│   │   ├── conftest.py
│   │   └── market/                 # 8 test modules, 73 tests, 84% coverage
│   ├── market_data_demo.py         # Standalone Rich-terminal demo (uv run)
│   ├── pyproject.toml               # uv project config, deps, ruff, pytest config
│   ├── uv.lock
│   └── CLAUDE.md                    # Backend developer guide (market API usage)
│
│   # PLANNED, not present as source (only stale .pyc in __pycache__/):
│   #   app/main.py, app/api/, app/db/, app/llm/, app/services/
│   #   tests/api/, tests/db/, tests/llm/, tests/services/ (test dirs exist
│   #   with __pycache__ but no corresponding .py source files currently)
│
├── frontend/                      # PLANNED — empty directory, no Next.js project yet
│
├── planning/                      # Project-wide docs (shared agent contract)
│   ├── PLAN.md                    # The spec — read in full via CLAUDE.md
│   ├── MARKET_DATA_SUMMARY.md     # Summary of the built market module
│   ├── MARKET_DATA_DESIGN.md
│   ├── MARKET_DATA_REVIEW.md
│   ├── MARKET_INTERFACE.md
│   ├── MARKET_SIMULATOR.md
│   ├── MASSIVE_API.md
│   └── archive/
│
├── .planning/                     # GSD workflow state (codebase maps, etc.)
│   └── codebase/                  # This document and its siblings
│
├── db/                            # Runtime bind-mount target for SQLite
│   └── finally.db                 # Present but no schema code exists yet to populate it meaningfully
│
├── scripts/                       # PLANNED — empty; start/stop scripts not written
│
├── test/                          # PLANNED — Playwright E2E, host-run
│   ├── node_modules/              # npm install has been run
│   ├── playwright-report/
│   ├── test-results/
│   └── specs/                     # Empty — no .spec.ts files yet
│
├── .github/workflows/             # CI config (not analyzed in detail here)
├── CLAUDE.md                       # Project-root Claude instructions, references planning/PLAN.md
├── README.md
├── LICENSE
└── .env                            # Present, gitignored (contents not read — see forbidden_files policy)

# Not present: Dockerfile, docker-compose.yml
```

## Directory Purposes

**`backend/app/market/`:**
- Purpose: everything needed to produce and stream live/simulated ticker prices
- Contains: data models, the source abstraction, two concrete sources, the shared cache, ticker validation, and the SSE router factory
- Key files: `cache.py` (single source of truth for current prices), `factory.py` (chooses simulator vs. Massive), `stream.py` (SSE endpoint)

**`backend/tests/market/`:**
- Purpose: unit and conformance tests for the market subsystem
- Contains: one test module per source file plus `test_conformance.py`, which asserts both `SimulatorDataSource` and `MassiveDataSource` satisfy the same `MarketDataSource` contract

**`planning/`:**
- Purpose: the shared, authoritative specification agents build against
- Contains: `PLAN.md` (full spec, loaded automatically via root `CLAUDE.md`), plus supporting design docs and reviews for the market module already completed

**`db/`:**
- Purpose: runtime location of the SQLite database file, bind-mounted into the Docker container per the plan
- Currently: `finally.db` exists on disk but there is no schema/init code in the repo to have created meaningful tables in it yet — treat its current contents as incidental, not authoritative

**`frontend/`, `scripts/`, `test/specs/`:**
- Purpose (planned): Next.js static-export UI, Docker start/stop scripts, Playwright E2E specs
- Currently: empty or scaffold-only (e.g., `test/node_modules` exists from `npm install` but no specs)

## Key File Locations

**Entry Points:**
- `backend/market_data_demo.py`: standalone demo script, not the served app (run via `uv run market_data_demo.py`)
- `backend/app/main.py`: **planned**, does not exist — this is where the FastAPI app will be assembled and where `/api/*` routers must be registered before any static-file mount (per `planning/PLAN.md` section 11)

**Configuration:**
- `backend/pyproject.toml`: uv project definition, dependencies (`fastapi`, `uvicorn`, `numpy`, `massive`, `rich`), dev deps (`pytest`, `ruff`), pytest and ruff config
- `.env` (project root): environment variables (`OPENROUTER_API_KEY`, `MASSIVE_API_KEY`, `LLM_MOCK`) — existence noted only, contents not inspected

**Core Logic (built):**
- `backend/app/market/cache.py`: `PriceCache` — thread-safe store, `version` counter drives SSE change detection
- `backend/app/market/simulator.py`: `GBMSimulator` — Cholesky-correlated geometric Brownian motion price generation
- `backend/app/market/stream.py`: `create_stream_router()` — the one HTTP-facing piece of the built subsystem

**Testing:**
- `backend/tests/market/`: pytest suite for the market module
- `backend/tests/conftest.py`: shared fixtures
- Run via `uv run --extra dev pytest -v` from `backend/`

## Naming Conventions

**Files:**
- Python: `snake_case.py` throughout `backend/app/market/` and `backend/tests/market/`
- Test files: `test_<module>.py`, mirroring the module they cover (e.g., `simulator.py` → `test_simulator.py`, plus `test_simulator_source.py` for the source-adapter behavior)

**Directories:**
- Backend Python package rooted at `backend/app/`, subpackages by domain (`market/`, and planned `api/`, `db/`, `llm/`, `services/`) rather than by layer-then-domain
- Tests mirror the app package structure one level down: `backend/tests/<subpackage>/`

**Python conventions observed in `backend/app/market/`:**
- Classes: `PascalCase` (`PriceCache`, `PriceUpdate`, `GBMSimulator`, `SimulatorDataSource`, `MassiveDataSource`)
- Functions/methods: `snake_case` (`create_market_data_source`, `normalize_ticker`, `wait_for_price`)
- Constants: `UPPER_SNAKE_CASE` (`TICKER_PATTERN`, `POLL_INTERVAL`, `HEARTBEAT_INTERVAL`)
- Every module has a module-level docstring; public functions/classes have docstrings describing contracts and lifecycle, not just descriptions
- `from __future__ import annotations` used at the top of files with type hints (e.g., `stream.py`, `interface.py`)
- Package `__init__.py` re-exports the public API explicitly via `__all__` (see `backend/app/market/__init__.py`)

## Where to Add New Code

This is the highest-value section of this document since most of the platform is unbuilt. Directions below follow `planning/PLAN.md` sections 4, 7, 8, and 13.

**Database layer (build order step 2):**
- Create `backend/app/db/` with `connection.py` (SQLite connection handling), `init.py` (lazy schema creation + seed data — triggered on first request, not a separate migration step), and `repository.py` or per-table modules
- Schema SQL and seed logic live here per the plan's directory contract (`planning/PLAN.md` section 4)
- Tests go in `backend/tests/db/` (directory already exists with a stale `__pycache__`, confirming this was the intended location before)

**Portfolio API (build order step 2):**
- Router: `backend/app/api/portfolio.py` exposing `GET /api/portfolio`, `POST /api/portfolio/trade`, `GET /api/portfolio/history`
- Business logic: `backend/app/services/portfolio.py` (valuation, P&L), `backend/app/services/trading.py` (trade execution, validation), `backend/app/services/snapshots.py` (30-second snapshot background task)
- These services read live prices from `backend/app/market/cache.py`'s `PriceCache` — do not duplicate price logic

**Watchlist API (build order step 3):**
- Router: `backend/app/api/watchlist.py` exposing `GET/POST /api/watchlist`, `DELETE /api/watchlist/{ticker}`
- Business logic: `backend/app/services/watchlist.py`, wired to the market source's `add_ticker()`/`remove_ticker()` (already present on `MarketDataSource`)
- Reuse `backend/app/market/tickers.py`'s `normalize_ticker()`/`TICKER_PATTERN` for validation — do not write a second ticker-validation regex

**Chat / LLM (build order step 6):**
- `backend/app/llm/client.py`: LiteLLM → OpenRouter call using the `cerebras-inference` skill/provider
- `backend/app/llm/schema.py`: structured output schema (`message`, `trades`, `watchlist_changes`)
- `backend/app/llm/mock.py`: `LLM_MOCK=true` deterministic responses, keyword-triggered per the contract in `planning/PLAN.md` section 9
- `backend/app/llm/prompt.py`: system prompt + portfolio context construction
- Router: `backend/app/api/chat.py` exposing `GET/POST /api/chat`

**App assembly:**
- `backend/app/main.py`: create the FastAPI app, register every `/api/*` router first, then mount `StaticFiles(directory="static", html=True)` at `/` last — mount order is explicitly called out as the most common way this architecture breaks (`planning/PLAN.md` section 11)
- Also the place to instantiate the single `PriceCache` and `MarketDataSource`, start it on app startup, and stop it on shutdown

**Frontend (build order step 4-5):**
- Initialize a Next.js TypeScript project inside `frontend/` with `output: 'export'` in `next.config`
- Internal structure is left to the implementer; only the API contract in `planning/PLAN.md` section 8 and the `/api/stream/prices` SSE contract in section 6 are fixed
- Charts: Recharts for every chart including the treemap heatmap (per plan section 10) — do not introduce a second charting library

**Docker & scripts (build order step 7):**
- `Dockerfile` at repo root: multi-stage (Node 22 → Python 3.12/uv), building the frontend static export first, then `uv sync --frozen --no-dev`, copying frontend output into a `static/` dir served by FastAPI
- `scripts/start_mac.sh`, `scripts/stop_mac.sh`, `scripts/start_windows.ps1`, `scripts/stop_windows.ps1`: currently empty directory, need to be created idempotent per the plan

**E2E tests (build order step 8):**
- `test/specs/*.spec.ts`: Playwright specs run on the host against the started container (`npx playwright test` against `http://localhost:8000`), with `LLM_MOCK=true` for determinism
- `test/` already has `node_modules` and Playwright installed — only spec files are missing

**Utilities:**
- Shared, cross-cutting helpers used by more than one domain (e.g., ticker validation) belong in `backend/app/market/` if price/ticker-related, since that module is already the shared dependency of the rest of the backend; avoid creating a generic `utils/` grab-bag

## Special Directories

**`backend/app/market/`:**
- Purpose: the one finished, tested vertical slice — treat as the reference implementation for docstring style, module layout, and ABC-based source abstraction when building the rest
- Generated: No
- Committed: Yes

**`db/`:**
- Purpose: runtime SQLite file location, bind-mounted in Docker
- Generated: Yes (the `.db` file), directory itself is committed via `.gitkeep` per the plan
- Committed: `finally.db` is intended to be gitignored per `planning/PLAN.md` section 4; directory placeholder is committed

**`backend/.venv/`, `backend/.uv-cache/`, `.uv-cache/`, `backend/.pytest_cache/`, `backend/.ruff_cache/`, `__pycache__/`:**
- Purpose: local tooling caches and virtual environment
- Generated: Yes
- Committed: No — exclude from any codebase analysis or new-file placement decisions

**`test/node_modules/`, `test/playwright-report/`, `test/test-results/`:**
- Purpose: npm-installed Playwright dependencies and prior run artifacts
- Generated: Yes
- Committed: No

---

*Structure analysis: 2026-08-04*
