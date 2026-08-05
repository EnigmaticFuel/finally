# Phase 1: Foundation & Spine - Research

**Researched:** 2026-08-05
**Domain:** FastAPI app assembly, SQLite concurrency, uv lockfile discipline, repo hygiene
**Confidence:** HIGH

## Summary

This phase is unusually well-specified: `01-CONTEXT.md` locks 22 implementation decisions, so research effort went into *verifying the assumptions those decisions rest on* rather than exploring alternatives. Every load-bearing claim below was confirmed by executing code against the real installed packages in this repo, not recalled from training data.

Three findings change what the planner must do. First, **`app.frontend()` behaves better than PLAN.md §11 assumes** — API routes take precedence over the SPA fallback regardless of registration order, so the "mount order hazard" is structurally gone; but `directory` is keyword-only and resolves against the **process CWD**, which is a new and sharper hazard that will break the moment uvicorn is launched from a different directory. Second, **the httpx-backed SSE integration test in D-21 cannot be written the way D-21 implies** — both `TestClient.stream()` and `httpx.ASGITransport` hang forever on an infinite SSE stream on this project's pinned versions; a real uvicorn server in a background thread is the pattern that works, and it was verified end-to-end. Third, and most consequential: **the tracked `db/finally.db` already contains all six tables populated with a prior session** — $6,200.01 cash, 12 watchlist tickers, 4 positions, 46 trades, 26 chat messages. A fresh clone therefore never exercises CORE-04's lazy seed and never shows the $10,000 / 10-ticker first-launch experience that PLAN.md §2 promises.

The rest is confirmation: the WAL + `busy_timeout` + `BEGIN IMMEDIATE` design in D-03/D-04/D-05 was stress-tested to 360 concurrent writes with zero errors; the dependency bump in SETUP-01/SETUP-02 resolves and installs cleanly with all chat dependencies importing; and the 154-test baseline holds — except for one pre-existing flaky test that fails ~30% of the time independently of anything this phase does.

**Primary recommendation:** Follow CONTEXT.md's decisions as written — they are sound and verified. Add four things the decisions do not cover: an absolute `directory=` path for `app.frontend()`, a uvicorn-in-thread SSE test instead of an ASGITransport one, a resolution for the pre-populated tracked database, and `.gitignore` entries for the WAL sidecar files that D-03 will start producing.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| App assembly / DI wiring | API / Backend (`app/main.py`) | — | `create_app()` owns object graph construction; nothing else may build a `PriceCache` |
| Live price production | Backend background task | — | Frozen `app/market/` source writes into `PriceCache`; lifespan owns only start/stop |
| SSE fan-out | API / Backend (`app/market/stream.py`) | Browser (`EventSource`) | Frozen module; this phase only mounts it |
| Persistence + schema | Database / Storage (`app/db/`) | — | Volume-mounted SQLite file; lazy init on first connection |
| Query surface | Database / Storage (`app/db/queries.py`) | — | Plain `def` functions; services in Phase 3 compose them |
| Event-loop protection | API / Backend (`app/db/connection.py`) | — | Single `asyncio.to_thread` offload point (CORE-10) |
| Money/quantity rounding | Database / Storage (`app/db/money.py`) | — | Write-boundary only (D-18); derived values stay full-precision |
| Static frontend fallback | Frontend Server (FastAPI `app.frontend()`) | CDN / Static (none) | Single origin, single port; no CORS by construction |
| Health reporting | API / Backend (`app/api/health.py`) | — | Reads cache + source name; no DB dependency |

## Project Constraints (from CLAUDE.md)

These are directives, not preferences. Plans that contradict them are wrong.

| Directive | Source | Applies to this phase as |
|-----------|--------|-------------------------|
| No defensive programming; no speculative `try/except` | global + project | `writing()` rolls back on exception and re-raises; no swallowing |
| No overengineering | global | No `pydantic-settings`, no `aiosqlite`, no ORM (D-01, D-13) |
| Short modules and functions | project | `main.py`, `connection.py`, `queries.py`, `money.py`, `schema.sql`, `seed.py`, `health.py` each single-purpose |
| **No emojis** anywhere in code, logs, docstrings, comments | global + project | Applies to every log line and the placeholder `index.html` |
| Docstrings carry the "why"; inline comments rare | project | Module docstrings on all new modules |
| `uv run` / `uv add`; never bare `python` / `pip` | global | `uv add`, `uv sync --frozen`, `uv run --extra dev pytest` |
| Use latest library APIs | global | `app.frontend()` over `StaticFiles`; `lifespan` over `@app.on_event` |
| `from __future__ import annotations` first import in every module | project | Every new `.py` file |
| Full type hints on every signature incl. private helpers | project | Including test fixtures |
| ruff `["E","F","I","N","W"]`, line-length 100, target py312 | project | `uv run --extra dev ruff check app/ tests/` |
| `%s`-style lazy log formatting, never f-strings in log calls | project | `logger.info("Database initialized at %s", path)` |
| Module-level constants `SCREAMING_SNAKE_CASE` | project | `DEFAULT_TICKERS`, `STARTING_CASH`, `BUSY_TIMEOUT_MS`, `QUANTITY_EPSILON` |
| Test files mirror module 1:1 | project | `app/db/queries.py` → `tests/db/test_queries.py` |
| Identify root cause before fixing | global | Directly relevant to the `database is locked` diagnosis instruction |
| Use Context7 for library docs | global (`rules/context7.md`) | Context7 MCP was **unavailable this session** — see Open Questions |

**Project skill:** `.claude/skills/cerebras/SKILL.md` governs LLM call construction. Not exercised in Phase 1 beyond making `litellm` a real locked dependency (SETUP-01).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Async database strategy**

- **D-01:** SQLite access uses the stdlib `sqlite3` module, offloaded from the event loop with `asyncio.to_thread`. No `aiosqlite` dependency. This matches the pattern already in the codebase — `backend/app/market/massive_client.py` runs its blocking REST calls through `asyncio.to_thread` — and `aiosqlite` runs a thread per connection internally anyway, so it buys syntax rather than concurrency. — **Reversibility:** costly — undoing it rewrites every query signature and the call sites in the Phase 3 services and Phase 6 chat router that are built against them.

- **D-02:** Query functions in `app/db/queries.py` are plain `def` functions taking a connection as their first argument. The `asyncio.to_thread` offload lives in exactly one helper in `app/db/connection.py`, applied at the call site. Query functions are therefore directly callable in pytest with no event loop. — **Reversibility:** costly — this is the signature contract Phase 3's `services/trading.execute_trade()` and `services/watchlist.add/remove()` are written against, and the roadmap records those signatures as a contract.

**Connection and transaction model**

- **D-03:** One connection per operation, opened by a context manager that sets WAL and `busy_timeout` on open and closes on exit. Not a shared long-lived connection behind a lock — that would serialize every read behind every write and discard the concurrency WAL was enabled to provide. It also sidesteps `sqlite3`'s `check_same_thread`, since `asyncio.to_thread` hands work to arbitrary executor threads. — **Reversibility:** costly — the test fixtures and every query call site assume it.

- **D-04:** `busy_timeout = 5000` ms. Long enough to absorb snapshot-versus-trade contention, short enough that a genuine locking problem surfaces as a visible error rather than a request that appears to hang. This is deliberate given the accepted OneDrive / Windows bind-mount risk: the roadmap instructs agents to *diagnose* `database is locked` if it appears, and a short timeout is what makes it visible.

- **D-05:** The `BEGIN IMMEDIATE` helper covers writes only — a `writing()` context manager that begins immediately, commits on success and rolls back on exception. Reads use plain autocommit connections; under WAL a reader already sees a consistent snapshot without an explicit transaction.

- **D-06:** Routers obtain the connection through a FastAPI dependency, sourced from the DB path held on `app.state`. No module-level connection singleton — the same rule CORE-07 applies to `PriceCache`. Tests override this one dependency. — **Reversibility:** costly — Phase 3's portfolio and watchlist routers and their route tests are built on this seam.

**Schema and lazy initialization**

- **D-07:** The schema is a single `backend/app/db/schema.sql` executed with `connection.executescript()`. PLAN.md section 4 describes `app/db/` as holding "schema SQL definitions", and a single SQL file reads next to PLAN.md section 7 for a student inspecting the project. Hatchling's wheel target already packages everything under `app/`, so the `.sql` file ships.

- **D-08:** Lazy init is triggered from the connection helper: an idempotent `ensure_initialized(path)` guarded by a flag and a lock so it runs once per path. This covers every caller — request handlers and, later, the Phase 3 snapshot background task — with no way for a new call site to forget it. Explicitly not lifespan startup, which would be eager and read against CORE-04.

- **D-09:** `CREATE TABLE IF NOT EXISTS` always; seeding is gated on a single fresh-database check — does `users_profile` have a row? If not, seed the profile, the ten watchlist tickers and the first portfolio snapshot in one transaction. If it does, touch nothing. Consequence, deliberately chosen: a user who removes all ten tickers does **not** get them back on restart.

- **D-10:** The ten default watchlist tickers are named explicitly in the db seed module, not derived from `app.market.seed_prices.SEED_PRICES`. The default watchlist is user data; `SEED_PRICES` is simulator tuning that also feeds the Massive path. Adding a ticker there for simulator realism must not silently change what every new user sees on first launch.

**Runtime boundaries**

- **D-11:** A placeholder `backend/static/index.html` is committed, stating that the backend is running. The static fallback is therefore real from day one, the "`/api/*` must not be shadowed" assertion in success criterion 1 has something to test against, and Phase 7's Docker build drops the Next.js export into the same directory. No runtime directory-creation branch — the directory is committed, so it always exists.

- **D-12:** The SQLite path resolves from a `FINALLY_DB_PATH` environment variable, defaulting to the repo-root `db/finally.db` by walking up from the package. Docker sets it explicitly to `/app/db/finally.db`. Pure derivation was rejected because it lands on `backend/db/` locally but `/app/db` in the container, silently diverging from the tracked, bind-mounted repo-root `db/`. — **Reversibility:** costly — Phase 2's Dockerfile, start scripts and `.env.example` all depend on the variable name.

- **D-13:** Configuration lives in one small `app/config.py` that calls `load_dotenv` on the project-root `.env` at import and exposes the values as constants. Plain `os.getenv`, no `pydantic-settings` dependency for four strings. This matches the existing style — `app/market/factory.py` already reads `MASSIVE_API_KEY` directly from the environment.

- **D-14:** `GET /api/health` lives in `app/api/health.py` as a `create_health_router(cache)` factory, mirroring the `create_stream_router(cache)` convention the market module established. It needs the cache injected anyway for `tickers_cached` and `newest_price_age_seconds`. This establishes the `app/api/` package that Phase 3 extends with `portfolio.py` and `watchlist.py`.

**Money and quantity rounding**

- **D-15:** Stored precision: cash 2dp, share quantity 4dp, `avg_cost` 4dp. Quantity at 4dp is fixed by PLAN.md section 8. `avg_cost` keeps 4dp because it is a derived ratio rather than a price the user pays — rounding it to cents accumulates visible drift in unrealized P&L across repeated partial buys. — **Reversibility:** one-way — these are stored column values, so changing the precision after data exists requires rewriting existing rows, and `db/finally.db` is tracked in git, so a stale database persists into every clone.

- **D-16:** The zero-comparison epsilon is `1e-6` — two orders of magnitude below the 4dp quantity precision and far above float noise at these magnitudes. A remainder under `1e-6` after a full sell is arithmetic residue, never a real holding.

- **D-17:** `round_money()`, `round_quantity()` and `is_zero()` live in `app/db/money.py`. Phase 3's manual trade path and Phase 6's LLM-driven trade path both route through the same functions, which is the point of the service seam the roadmap records.

- **D-18:** Rounding applies at the write boundary only. Derived values — `market_value`, `unrealized_pnl`, `total_value` — are returned at full float precision and formatted by the client. This matches CORE-06's wording, and the frontend recomputes those figures from the SSE stream on every frame anyway, so server-side rounding would not be authoritative and would visibly disagree with the client's.

**Testing**

- **D-19:** The test database is a real file per test via pytest's `tmp_path`. Not `:memory:` — it cannot exercise WAL, `busy_timeout` or genuine lock contention, which is the specific risk this phase carries, and with connection-per-operation each `:memory:` connection would get its own empty database.

- **D-20:** Phase 1 writes a real concurrency test for success criterion 3: drive the snapshot-write and trade-write query functions from concurrent threads against a tmp-file database and assert no `OperationalError`. Nothing in the codebase currently drives this code concurrently. The realistic collision between the 30s task and `execute_trade` belongs to Phase 3; this proves the query layer holds.

- **D-21:** The httpx-backed SSE integration test lands in this phase. `.planning/codebase/CONCERNS.md` records SSE as the module's weakest coverage (~31%) and names the reason precisely — there was no `main.py` to mount the router into. This phase creates it. The test asserts the stream opens and carries both a price frame and a heartbeat, covering CORE-03 directly.

- **D-22:** Tests point the app at the throwaway database by overriding the FastAPI DB dependency in a conftest fixture built around `create_app()`. Not by monkeypatching `FINALLY_DB_PATH`, which would depend on import-time ordering in `config.py` and is fragile across test sessions. Phase 3's route tests reuse this fixture verbatim.

### Claude's Discretion

The user selected the recommended option in every question, so no area was explicitly delegated. Left to the planner and executor: internal module decomposition beyond the file names fixed above, the exact wording of docstrings and log messages, and the mechanics of the SETUP-03 `.gitattributes` renormalization.

### Deferred Ideas (OUT OF SCOPE)

- **30-second portfolio snapshot background task** — Phase 3 (PORT-*). Its query function lands here; the task that calls it does not.
- **Reset Portfolio (PORT-14)** — Phase 3. It will want to reuse the seed logic written here, so shape the seed helper so a reset can call it rather than duplicating the $10,000 constant.
- **Realistic snapshot-task-versus-`execute_trade` collision test** — Phase 3, once both real callers exist. D-20 proves the query layer only.
- **Relaxing the exact `massive==2.2.0` pin** — tech debt recorded in `.planning/codebase/CONCERNS.md`; touching it would modify the frozen market module's dependency contract for no Phase 1 benefit.
- **`PriceCache.version` read outside the lock** — tech debt in the frozen module. Do not touch.

### Non-negotiable process constraints (from CONTEXT.md `<specifics>` and PROJECT.md)

- No plan, task or success criterion may propose relocating the repo out of OneDrive, changing the `db/` bind-mount source, or untracking `db/finally.db`. If `database is locked` appears, **diagnose it in place**.
- `backend/app/market/` is frozen. Consumed only through `PriceCache`, `wait_for_price`, `create_market_data_source`, `create_stream_router(cache)`, `TICKER_PATTERN`, `normalize_ticker`.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SETUP-01 | `litellm`, `pydantic`, `python-dotenv` declared and in `uv.lock`; `uv sync --frozen` yields importable chat deps | **Verified end-to-end.** Full resolve + clean `uv sync --frozen` + import of all four succeeded (`litellm 1.95.0`, `openai 2.53.0`, `pydantic 2.12.5`, `python-dotenv 1.2.1`). See *Dependency Resolution* and *Pitfall 6* (a `MAX_PATH` red herring). `httpx` must be added too — see *Gap A* |
| SETUP-02 | FastAPI floor raised to `>=0.141.1` for `app.frontend()` | **Verified.** 0.141.1 is the current latest; `app.frontend()` exists there and not in the installed 0.128.7. `massive==2.2.0` imposes no FastAPI/pydantic constraint, so the bump is unobstructed. Exact signature in *Code Examples* |
| SETUP-03 | `.gitattributes` enforcing LF for `.sh`/`Dockerfile`, CRLF for `.ps1`, repo renormalized | **Verified absent** (`git ls-files` shows no `.gitattributes`). Exact directives + `git add --renormalize .` in *Code Examples*. Add a `-text` rule for `db/*.db` — see *Gap D* |
| SETUP-04 | `.env.example` committed documenting the three env vars | **Verified absent.** Must also document `FINALLY_DB_PATH` (D-12) — see *Gap C* |
| SETUP-05 | Stale `__pycache__` under `backend/{app,tests}/{api,db,llm,services}` removed | **Verified present**: 12 `__pycache__` dirs; `app/{api,db,llm,services}` contain *nothing but* `__pycache__`. Already gitignored (`.gitignore:2`), so this is a disk deletion, not an untrack |
| SETUP-06 | The 154 existing market-data tests still pass | **Verified 154 pass** on current deps and **153 pass / 1 fails** on FastAPI 0.141.1 — but the failure is a *pre-existing flake* (3/10 failures on the unmodified current environment). See *Pitfall 1* — this criterion needs restating |
| CORE-01 | `create_app()` constructs `PriceCache` + source before router registration | **Verified working** against the real frozen module. Skeleton in *Code Examples* |
| CORE-02 | Market task starts/stops with lifespan, not deprecated startup events | **Verified working**; `asynccontextmanager` lifespan drove `source.start()`/`stop()` cleanly |
| CORE-03 | SSE router mounted; `GET /api/stream/prices` streams from the running app | **Verified streaming** `200 text/event-stream` with `retry: 1000` + a price frame, via uvicorn-in-thread. **The naive test approach hangs** — see *Pitfall 2* |
| CORE-04 | DB created and seeded lazily — 6 tables, $10k profile, 10 tickers, 1 snapshot | Pattern verified. **Blocked from being observable on a fresh clone** by the pre-populated tracked DB — see *Pitfall 3*, the single most important finding |
| CORE-05 | WAL + busy timeout + `BEGIN IMMEDIATE` so snapshot and trade cannot collide | **Verified under stress**: 360/360 concurrent writes, 0 `OperationalError`. See *Code Examples* and *Pitfall 4* (`isolation_level=None` is mandatory) |
| CORE-06 | Money/quantities rounded at write boundary, compared with epsilon | Design confirmed sound; `float` + 4dp round + `1e-6` epsilon is safe at these magnitudes. See *Don't Hand-Roll* |
| CORE-07 | Shared `PriceCache` reachable by DI without a module-level singleton | Verified via `app.state` + `Depends`. See *Code Examples* |
| CORE-08 | `GET /api/health` returns the four-key payload | **Verified working** against a live cache; `newest_timestamp()` and `source_name` exist and supply two of the four keys |
| CORE-09 | Static frontend served same-origin without shadowing `/api/*` | **Verified in both registration orders** — precedence is order-independent. But `directory` is CWD-relative: *Pitfall 5* |
| CORE-10 | DB access never blocks the event loop | `asyncio.to_thread` at one seam (D-01/D-02). See *Code Examples* |
| TEST-01 | Backend tests cover DB init, seeding, and money/quantity rounding | Test matrix in *Validation Architecture*; `tmp_path` + dependency-override fixture per D-19/D-22 |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | `>=0.141.1` | App assembly, routers, DI, SPA serving | `app.frontend()` (0.138.0+) is the first-class SPA answer; 0.141.1 is current latest `[VERIFIED: PyPI JSON API + local install]` |
| `uvicorn[standard]` | `>=0.32.0` (resolves 0.40.0) | ASGI server | Already declared; unchanged this phase |
| `sqlite3` | stdlib (Python 3.12+) | All persistence | D-01: no `aiosqlite`. Stdlib is sufficient and matches house `asyncio.to_thread` style |
| `pydantic` | `>=2.10.0` (resolves 2.12.5) | Request/response models, LLM structured output | Already a transitive FastAPI dep; SETUP-01 makes it explicit because Phase 6 imports it directly |
| `python-dotenv` | `>=1.0.0` (resolves 1.2.1) | `load_dotenv` on project-root `.env` (D-13) | Already transitively required by `litellm`; SETUP-01 makes it direct |
| `litellm` | `>=1.95.0` | LLM gateway (Phase 6) | Declared now so `uv sync --frozen` in Docker produces an importable chat endpoint (SETUP-01) |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | `>=0.28.0` (resolves 0.28.1) | HTTP client for the SSE integration test | **Dev extra.** Required by D-21 and currently undeclared — see *Gap A* |
| `pytest` / `pytest-asyncio` / `pytest-cov` / `ruff` | as declared | Test + lint | Unchanged |
| `numpy`, `massive`, `rich` | as declared | Frozen market module | Do not touch |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `app.frontend()` | `app.mount("/", StaticFiles(html=True))` after routers | Rejected by SETUP-02 `[CORR]`. Verified inferior: `StaticFiles` requires correct ordering and hand-rolled SPA fallback; `app.frontend()` is order-independent and Accept-aware |
| stdlib `sqlite3` + `to_thread` | `aiosqlite` | Rejected by D-01. `aiosqlite` runs a thread per connection internally — syntax, not concurrency |
| `os.getenv` + `python-dotenv` | `pydantic-settings` | Rejected by D-13. Four strings do not earn a dependency |
| `TestClient` / `ASGITransport` for SSE | uvicorn in a background thread | **Not a preference — the first two provably hang.** See *Pitfall 2* |
| `float` + epsilon | `Decimal` / integer cents | Rejected by D-15/D-16 (one-way: columns are `REAL`). Safe here — see *Don't Hand-Roll* |

**Installation:**

```bash
cd backend
uv add "fastapi>=0.141.1" "litellm>=1.95.0" "pydantic>=2.10.0" "python-dotenv>=1.0.0"
uv add --optional dev "httpx>=0.28.0"
uv sync --frozen --extra dev
uv run --extra dev pytest -q
```

**Verified resolution outcome** — a clean `uv sync --frozen` from the regenerated lock produced:
`fastapi 0.141.1`, `starlette 0.52.1`, `pydantic 2.12.5`, `litellm 1.95.0`, `openai 2.53.0`, `httpx 0.28.1`, `uvicorn 0.40.0`, and all of `litellm, fastapi, pydantic, dotenv, httpx` imported successfully. `[VERIFIED: uv lock + uv sync --frozen + import probe, this session]`

**Cost note:** `litellm` pulls a large transitive tree — `openai`, `tiktoken`, `tokenizers`, `aiohttp`, `jinja2`, `typer`, `huggingface-hub` (21 packages added). Harmless here, but Phase 2/7 should expect a materially larger image layer. `[VERIFIED: uv sync output, this session]`

## Package Legitimacy Audit

| Package | Registry | Latest release | Downloads signal | Source Repo | Verdict | Disposition |
|---------|----------|----------------|------------------|-------------|---------|-------------|
| `fastapi` | PyPI | 0.141.1 | unavailable | github.com/fastapi/fastapi | OK-equivalent | Approved |
| `litellm` | PyPI | 2026-08-02 | unavailable | litellm.ai | SUS (`too-new`, `unknown-downloads`) | Approved — see note |
| `pydantic` | PyPI | 2026-05-06 | unavailable | github.com/pydantic/pydantic | SUS (`unknown-downloads`) | Approved |
| `python-dotenv` | PyPI | 2026-03-01 | unavailable | github.com/theskumar/python-dotenv | SUS (`unknown-downloads`) | Approved |
| `httpx` | PyPI | 2024-12-06 | unavailable | github.com/encode/httpx | SUS (`unknown-downloads`) | Approved |
| `uvicorn` | PyPI | — | unavailable | github.com/encode/uvicorn | OK-equivalent | Approved |

**Interpretation — read before acting on the verdicts.** The seam returned `weeklyDownloads: null` for *every* package including `httpx` and `fastapi`, so the downloads signal was simply unavailable in this environment and the `unknown-downloads` reason carries no information. The `too-new` flag on `litellm` reflects its *most recent release date* (2026-08-02), not the age of the package — `litellm` is a mature, widely-used project already vendored in this repo's venv. None of these are candidate slopsquats: all six are named directly in PLAN.md / REQUIREMENTS.md or are pre-existing declared dependencies, and all resolve, install and import.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged requiring a human checkpoint:** none — the `SUS` verdicts are artifacts of a missing downloads feed, not risk signals. The planner should **not** insert `checkpoint:human-verify` tasks for these.

## Architecture Patterns

### System Architecture Diagram

```text
                    HTTP :8000  (single origin, single port)
                          │
                          ▼
      ┌───────────────────────────────────────────────┐
      │              create_app()                     │
      │                                               │
      │  1. cache  = PriceCache()          ◄── MUST be first
      │  2. source = create_market_data_source(cache)  │
      │  3. app.state.price_cache / db_path            │
      │  4. include_router(health(cache))              │
      │  5. include_router(stream(cache))              │
      │  6. app.frontend("/", directory=ABS_STATIC)    │
      └───────────────────────────────────────────────┘
            │                │                │
            │                │                └──── unmatched path?
            │                │                       ├─ Accept: text/html ─► index.html 200
            │                │                       └─ otherwise ────────► 404 JSON
            │                │
            │                ▼
            │        GET /api/stream/prices
            │        _generate_events(cache)
            │        ├─ "retry: 1000"
            │        ├─ data:{...} when cache.version moves  (~500ms poll)
            │        └─ ": ping" every 15s
            │                ▲
            │                │ reads
            ▼                │
     GET /api/health         │
     ├─ market_source ───────┤
     ├─ tickers_cached ──────┤
     └─ newest_price_age ────┤
                             │
                    ┌────────┴─────────┐
                    │    PriceCache    │ ◄── in-memory, thread-safe, versioned
                    └────────▲─────────┘
                             │ writes ~500ms
                    ┌────────┴──────────────────┐
                    │  MarketDataSource          │  started/stopped by LIFESPAN
                    │  (Simulator | Massive)     │  ── FROZEN MODULE ──
                    └────────────────────────────┘

   ── persistence path (independent of the price path) ──

     request handler
        │  Depends(get_db_path)  ◄── from app.state (no module singleton)
        ▼
     await run_db(query_fn, ...)          app/db/connection.py
        │  asyncio.to_thread   ◄── the ONE event-loop offload seam (CORE-10)
        ▼
     ensure_initialized(path)  ── once per path (flag + lock)
        │   └─ executescript(schema.sql)  → 6 tables  CREATE TABLE IF NOT EXISTS
        │   └─ users_profile empty? ─ yes ─► seed: profile $10k, 10 tickers, 1 snapshot
        │                            └ no ─► touch nothing
        ▼
     connect(path): PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000
        ├─ read  ► autocommit connection (WAL snapshot is already consistent)
        └─ write ► writing(): BEGIN IMMEDIATE → COMMIT / ROLLBACK
        ▼
     db/finally.db  (+ -wal, -shm sidecars)   ── bind-mounted volume
```

### Recommended Project Structure

```text
backend/
├── app/
│   ├── main.py           # create_app(), lifespan
│   ├── config.py         # load_dotenv + constants (D-13)
│   ├── api/
│   │   ├── __init__.py
│   │   └── health.py     # create_health_router(cache)  (D-14)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py # connect(), writing(), run_db(), ensure_initialized()
│   │   ├── schema.sql    # six tables (D-07)
│   │   ├── seed.py       # DEFAULT_TICKERS, STARTING_CASH, seed_fresh()  (D-09/D-10)
│   │   ├── queries.py    # every plain-def query function (D-02)
│   │   └── money.py      # round_money/round_quantity/is_zero (D-17)
│   └── market/           # FROZEN — do not modify
├── static/
│   └── index.html        # committed placeholder (D-11)
└── tests/
    ├── conftest.py       # app fixture + DB dependency override (D-22)
    ├── api/test_health.py
    ├── db/{test_connection,test_queries,test_money,test_seed,test_concurrency}.py
    └── market/           # existing 154 tests — do not modify
```

Note `app/{api,db,llm,services}` and `tests/{api,db,llm,services}` already exist on disk but contain **only stale `__pycache__`** — no `__init__.py`, no sources. SETUP-05 clears them; this phase then adds real `__init__.py` files to `app/api` and `app/db`. `[VERIFIED: filesystem listing, this session]`

### Pattern 1: Cache-before-router assembly (CORE-01)

**What:** `PriceCache` and the market source are constructed in the `create_app()` body, *before* any `include_router()` call and before lifespan runs.
**When to use:** Always, in this project. It is not stylistic — `create_stream_router(cache)` and `create_health_router(cache)` take the cache as a constructor argument, and router registration happens at import/app-build time, strictly before lifespan startup.
**Why it cannot be deferred to lifespan:** lifespan runs on the first ASGI `startup` event, long after `include_router()` has already needed the object.

### Pattern 2: Router factories over module-level routers

**What:** `create_health_router(cache)` builds and returns an `APIRouter` rather than decorating a module-level one.
**Why:** The frozen module established it (`create_stream_router`, `stream.py:22-27`), and its docstring gives the reason verbatim: *"The router is created inside the factory, not at module level, so calling this twice (an app plus a test app) does not register the route twice."* `[VERIFIED: backend/app/market/stream.py:22-27]`

### Pattern 3: One offload seam (CORE-10, D-02)

**What:** Query functions are plain `def`. Exactly one helper in `connection.py` wraps them in `asyncio.to_thread`. Routers `await run_db(fn, ...)`.
**Why:** Tests call query functions synchronously with no event loop; the event loop is never blocked; and there is one place to audit for CORE-10 compliance. Mirrors `massive_client.py`'s existing use of `asyncio.to_thread`.

### Pattern 4: Read/write transaction split (D-05)

**What:** Reads use a plain autocommit connection. Writes go through `writing()` → `BEGIN IMMEDIATE` → `COMMIT`/`ROLLBACK`.
**Why:** `BEGIN IMMEDIATE` acquires the write lock up front, so two concurrent read-modify-write sequences cannot both read, both compute, and both write. Under WAL a reader already sees a consistent snapshot, so wrapping reads adds contention for nothing.

### Anti-Patterns to Avoid

- **Constructing `PriceCache` inside lifespan** — breaks router registration (Pattern 1). The single most likely way to get this phase's assembly wrong.
- **A module-level connection or cache singleton** — forbidden by CORE-07 and D-06; also makes the D-22 test override impossible.
- **Setting PRAGMAs once at init** — `journal_mode` persists in the DB file, but `busy_timeout` is **per-connection** and must be reapplied on every open. `[CITED: sqlite.org forum — "The PRAGMA affects only the connection it is used in"]`
- **Wrapping reads in `BEGIN IMMEDIATE`** — serializes readers behind writers, discarding WAL's benefit.
- **`app.frontend(..., directory="static")` with a relative path** — resolves against process CWD, not the module. See *Pitfall 5*.
- **Rounding derived values server-side** — contradicts D-18 and will visibly disagree with the client's own recomputation.
- **Touching `backend/app/market/`** — frozen.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SPA fallback + API coexistence | Catch-all `@app.get("/{path:path}")` route, or ordered `StaticFiles` + custom 404 handler | `app.frontend(path, directory=..., fallback="index.html")` | FastAPI owns the Accept-header negotiation, method filtering and route precedence. Verified correct in both registration orders |
| Wait for a first price tick | A polling loop in the trade path | `app.market.wait_for_price(cache, ticker, timeout=2.0)` | Already built and exported; implements PLAN.md §8's 2s/200ms rule exactly (`cache.py:145-158`) |
| Ticker validation | A second regex | `app.market.normalize_ticker` / `TICKER_PATTERN` | One shared rule (`tickers.py:7-22`); a second one would drift from the LLM path |
| SSE framing / heartbeats | A new generator | `create_stream_router(cache)` | Frozen, complete, includes `retry: 1000` and 15s `: ping` |
| Price change semantics | Computing `change_from_open` in a query | `PriceUpdate` properties | Cache derives `previous_price`/`open_price` on write (`cache.py:38-67`) |
| DB lock retry logic | A `while True` retry-on-`OperationalError` wrapper | `PRAGMA busy_timeout=5000` | SQLite's own busy handler backs off internally; a manual retry loop defeats D-04's diagnostic intent and is defensive programming |
| Line-ending normalization | A checkout script or editorconfig-only approach | `.gitattributes` + `git add --renormalize .` | Git enforces it repo-wide regardless of each dev's `core.autocrlf` |
| Money precision | A `Decimal` layer or integer-cents refactor | `round(x, 2)` / `round(x, 4)` + `abs(x) < 1e-6` | Columns are `REAL` (one-way per D-15). At $10k scale, float64 has ~11 significant digits of headroom past the cent — the epsilon comparison closes the only real gap |

**Key insight:** This phase's value is *assembly*, not invention. The frozen market module already solves price waiting, validation, SSE framing and change semantics; FastAPI 0.141.1 solves SPA fallback; SQLite solves lock contention. Nearly every hand-rolled component a naive plan would add here already exists upstream — and three of them (`wait_for_price`, `normalize_ticker`, `busy_timeout`) are the exact things an executor is most tempted to rewrite.

## Runtime State Inventory

Phase 1 is greenfield *code*, but it lands on a repo with pre-existing runtime state. This inventory is what a grep audit would miss.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| **Stored data** | **`db/finally.db` is tracked in git and fully populated**: 6 tables, `users_profile.cash_balance = 6200.01`, 12 watchlist tickers (`AAPL, AMZN, GOOGL, JPM, META, MSFT, NFLX, NVDA, SPY, SRP, TSLA, V`), 4 positions (TSLA 1.0 @ 249.32, V 1.0 @ 279.78, SPY 6.0 @ 266.745, NVDA 2.0 @ 837.92), 46 trades, 26 chat messages, 85 snapshots. `journal_mode` already `wal` | **Decision required** — see *Pitfall 3*. Untracking is forbidden; resetting the committed contents is not |
| **Live service config** | None. No n8n, Datadog, Tailscale, or externally-hosted config. Market data is in-process | None — verified by reading PLAN.md §3 and `app/market/factory.py` |
| **OS-registered state** | None. No Task Scheduler entries, no pm2, no systemd. The app runs only under `uvicorn` / Docker | None — verified; no `Dockerfile` or `scripts/` exist yet (Phase 2 owns them) |
| **Secrets/env vars** | `.env` exists at project root and is gitignored (`.gitignore:138`). `MASSIVE_API_KEY` is the only var any code reads today (`factory.py:24`). `OPENROUTER_API_KEY`, `LLM_MOCK` are spec-only. `FINALLY_DB_PATH` is **new in this phase** (D-12) | Add `FINALLY_DB_PATH` to `.env.example` (SETUP-04 as written omits it) — *Gap C* |
| **Build artifacts** | 12 stale `__pycache__` dirs; `app/{api,db,llm,services}` contain nothing else. `backend/.venv` currently runs **Python 3.14.6** while `requires-python = ">=3.12"` and Docker targets 3.12. Also `backend/.pytest_cache`, `backend/.ruff_cache`, `backend/.uv-cache` | Delete stale `__pycache__` (SETUP-05). Consider pinning `.python-version` — *Gap B* |
| **Filesystem sidecars** | WAL mode will create `db/finally.db-wal` and `db/finally.db-shm`. `.gitignore` covers `db.sqlite3-journal` but **not** these. `git check-ignore` confirms both are **not ignored** | Add ignore rules — *Gap D*. PROJECT.md notes OneDrive syncs these sidecars |

## Common Pitfalls

### Pitfall 1: SETUP-06's "154 tests pass" is not reliably achievable — one test is already flaky

**What goes wrong:** `tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval` fails intermittently. A phase-completion gate worded as "all 154 pass" will fail for reasons unrelated to this phase's work, and an executor will waste time hunting a regression that does not exist.

**Why it happens:** The test starts a simulator at `update_interval=0.01`, sleeps `0.05`, and asserts `cache.version > initial_version + 2` — i.e. it expects ≥3 ticks in 50ms. Windows' default timer granularity (~15.6ms) makes this marginal, and any load pushes it under.

**Evidence:** `[VERIFIED: 10 consecutive runs on the unmodified current environment, FastAPI 0.128.7 — 7 passed, 3 failed]`. It also failed once under FastAPI 0.141.1, which is why the scratch suite read `1 failed, 153 passed`. **The FastAPI bump did not cause it.**

**How to avoid:** Do not let the planner treat a single red `test_custom_update_interval` as a dependency-bump regression. Options, in preference order: (a) restate SETUP-06 as "no *new* failures; the known flake is tolerated", (b) re-run the suite to confirm the failure is not reproducible, (c) fix the test's timing tolerance. Note (c) touches `backend/tests/market/`, which is *not* literally inside the frozen `backend/app/market/` — but it is adjacent to the freeze and should be a user decision, not an executor's.

**Warning signs:** A suite result of `1 failed, 153 passed` naming only this test.

### Pitfall 2: The SSE integration test hangs if written the obvious way (affects D-21)

**What goes wrong:** D-21 calls for an "httpx-backed SSE integration test". Written with either `TestClient.stream()` or `httpx.AsyncClient(transport=ASGITransport(app))`, the test **hangs forever** against `/api/stream/prices` — it never even receives response headers, so no timeout inside the read loop can rescue it. A CI run blocks until the job timeout.

**Why it happens:** Both in-process transports buffer the response body to completion before returning. `_generate_events` never completes — it is an infinite loop by design (`stream.py:77-95`), exiting only on client disconnect. There is no body-completion event to wait for.

**Evidence:** `[VERIFIED: both probed this session]` — `ASGITransport` hung with no output before the status line (killed at 90s); `TestClient.stream()` reached "TestClient constructed" and hung at stream-open (killed at 60s). Both on this project's pinned `starlette 0.52.1` / `httpx 0.28.1`.

**How to avoid:** Run a real `uvicorn.Server` on an ephemeral port in a daemon thread and use a real `httpx` client. Verified working, full skeleton in *Code Examples*. Assert the heartbeat separately by driving `_generate_events` with small `interval`/`heartbeat` values — a real 15-second wait does not belong in a unit suite.

**Warning signs:** A test that "passes locally" only because someone interrupted it; a CI job timing out with no failure message.

### Pitfall 3: A fresh clone cannot exercise CORE-04, and does not show the $10,000 first launch

**What goes wrong:** Success criterion 2 says *"On a machine with no database file, the first request creates and seeds it."* On a fresh clone there **is** a database file — `db/finally.db` is tracked and ships with 6 populated tables. D-09's seed gate ("does `users_profile` have a row?") finds one row and correctly seeds nothing. The user's first launch shows **$6,200.01 cash, 12 tickers, 4 positions and 26 chat messages from a prior session** — not PLAN.md §2's promised $10,000 and 10 tickers. TEST-06 ("a fresh start shows the default watchlist, $10,000 balance") would fail in Phase 7 for this reason alone.

**Why it happens:** PROJECT.md records "`db/finally.db` stays tracked in git" as a user-accepted risk, and notes PLAN.md §4's claim that the file is gitignored is factually wrong. The accepted risk was framed as *binary diffs and branch-switch overwrites* — the "fresh clone inherits someone's portfolio" consequence does not appear to have been surfaced when the risk was accepted.

**Evidence:** `[VERIFIED: sqlite3 inspection of the tracked file + git ls-files, this session]`.

**How to avoid — the constraint is narrower than it looks.** CONTEXT.md forbids *untracking* the file; it does not forbid *changing its contents*. Options for the planner to put to the user:
1. **Commit a freshly-seeded database** — replace the tracked file with one containing only the six empty tables plus the standard seed ($10,000, the 10 default tickers, 1 snapshot). Preserves tracking, restores the intended first-launch experience, and is a one-time write.
2. **Commit an empty/absent-schema file** so lazy init genuinely runs on first request — the truest reading of CORE-04, but leaves a 0-byte tracked artifact.
3. **Accept and restate** success criterion 2 as testable only against a `tmp_path` database (which D-19/D-22 already ensure), and separately accept that the demo starts mid-session.

Option 1 is the recommendation: it satisfies CORE-04's *observable intent*, keeps every accepted risk intact, and unblocks TEST-06. **This needs user confirmation — it is a product-visible decision, not an implementation detail.**

**Warning signs:** Header shows a cash figure that is not $10,000 on first launch; watchlist contains `SPY`/`SRP`.

### Pitfall 4: `sqlite3`'s default `isolation_level` silently breaks `BEGIN IMMEDIATE`

**What goes wrong:** `sqlite3.connect(path)` defaults to `isolation_level = ''` — legacy implicit-transaction mode, where the driver opens transactions for you. Issuing an explicit `BEGIN IMMEDIATE` on such a connection conflicts with the driver's own management and raises `OperationalError: cannot start a transaction within a transaction` once a statement has already opened one.

**Why it happens:** It is the stdlib's pre-PEP-249 legacy default and is easy to miss because trivial single-statement tests still pass.

**Evidence:** `[VERIFIED: repr(sqlite3.connect(":memory:").isolation_level) == '' this session]`; the working probe used `isolation_level=None`.

**How to avoid:** Always `sqlite3.connect(path, isolation_level=None)` (autocommit), then drive `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` explicitly in the `writing()` helper. On Python 3.12+ the modern `autocommit=False` attribute also exists, but `isolation_level=None` is the simpler, well-understood spelling and is what was verified.

**Warning signs:** `cannot start a transaction within a transaction`, or writes that appear to commit without `COMMIT`.

### Pitfall 5: `app.frontend(directory=...)` resolves against the process CWD

**What goes wrong:** `app.frontend("/", directory="static")` works when uvicorn is launched from `backend/` and raises `RuntimeError: Frontend directory 'static' does not exist` when launched from the repo root, from Docker's `WORKDIR`, or from a pytest run rooted elsewhere. Because `check_dir` defaults to `"auto"`, this raises **at app-creation time**, so every test in the suite errors at import, not just the frontend one.

**Why it happens:** The path is resolved relative to the current working directory, not to the module defining it.

**Evidence:** `[VERIFIED: probe this session]` — from CWD `…/scratchpad` with the script at `…/scratchpad/fe/probe.py`, `directory="static"` resolved to `…/scratchpad/static` (the CWD), not `…/scratchpad/fe/static` (the module dir). Error text: `RuntimeError: Frontend directory 'static' does not exist. Resolved absolute path: '…\scratchpad\static'`.

**How to avoid:** Always pass an absolute path derived from the module:
```python
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"   # backend/static
app.frontend("/", directory=STATIC_DIR, fallback="index.html")
```
D-11's committed `backend/static/index.html` then guarantees the directory exists in every environment. This also matters for Phase 2's Dockerfile.

**Warning signs:** Every test errors during collection with a `RuntimeError` about a frontend directory; the app runs from one shell and not another.

### Pitfall 6: `uv sync` hardlink failure on OneDrive, and a `MAX_PATH` red herring

**What goes wrong (a):** `uv sync` fails with `failed to hardlink file … The cloud operation cannot be performed on a file with incompatible hardlinks. (os error 396)`, leaving a **half-installed venv**. Because `uv sync` afterwards only installs *missing* packages, the broken partial install is not repaired by re-running it.

**How to avoid (a):** `export UV_LINK_MODE=copy` (or `uv sync --link-mode=copy`). If a venv is already half-installed, delete `.venv` and re-sync — a plain re-run will not fix it. `[VERIFIED: reproduced and fixed this session]`

**What goes wrong (b) — the red herring:** After the failed hardlink sync, `import litellm` raised `ModuleNotFoundError: No module named 'openai.types.responses.response_function_shell_call_output_content_param'`, which looks exactly like a `litellm`/`openai` version incompatibility and would tempt an executor to start pinning `openai`. **It is not.** The `openai` package ships module filenames long enough that the *absolute* path exceeded Windows' 260-char `MAX_PATH` at the deep scratch location used for testing; the file existed (both installs had 221 files in that directory) but Python's import machinery could not open it.

**Evidence:** `[VERIFIED: this session]` — the failing path measured 264 chars; the real project path measures **173 chars** and imports fine. A clean re-resolve at a short path imported `litellm 1.95.0` + `openai 2.53.0` + `fastapi 0.141.1` successfully.

**How to avoid (b):** Do not pin `openai`. The project's real path has ~87 chars of `MAX_PATH` headroom, and Docker (Linux) has no such limit. Only relevant if someone clones into a much deeper directory — worth one line in the README, not a code change.

**Warning signs:** `os error 396`; a `ModuleNotFoundError` naming an unusually long `openai.types.responses.*` module.

### Pitfall 7: Unmatched `/api/*` paths return the SPA to browsers (by design, but surprising)

**What goes wrong:** After `app.frontend()` is registered, navigating a browser to a mistyped `/api/portfolioo` returns **200 with `index.html`**, not a 404. During Phase 3-6 development this makes a typo'd or not-yet-implemented route look like a working page.

**Why it is nonetheless correct:** The fallback is Accept-header gated. Verified behavior `[VERIFIED: probe this session]`:

| Request | Result |
|---------|--------|
| `GET /api/nope` + `Accept: text/html` | `200 text/html` (SPA) |
| `GET /api/nope` + `Accept: text/html,application/xhtml+xml` | `200 text/html` (SPA) |
| `GET /api/nope` + `Accept: application/json` | `404 application/json` |
| `GET /api/nope` + `Accept: */*` | `404 application/json` |
| `POST /api/nope` (any Accept) | `404` |

Because `fetch()` sends `Accept: */*` by default, the frontend's own API calls correctly receive JSON 404s. Only manual browser navigation sees the SPA.

**How to avoid confusion:** Probe API routes with `curl -H 'Accept: application/json'` (or plain `curl`, which sends `*/*`), never the browser address bar. Worth a line in the health-check test.

## Code Examples

### `app.frontend()` — exact verified signature

```python
# Source: inspect.signature(fastapi.FastAPI.frontend) on installed fastapi 0.141.1
# [VERIFIED: local introspection, this session]
frontend(
    self,
    path: str,                                                  # positional
    *,                                                          # everything below is KEYWORD-ONLY
    directory: str | os.PathLike[str],
    fallback: Optional[Literal['auto', 'index.html', '404.html']] = 'auto',
    check_dir: Union[bool, Literal['auto']] = 'auto',
) -> None
```

`check_dir` semantics, quoted verbatim from the installed package's own `Doc()` annotation:

> "Check that the frontend directory exists when the app is created. When set to `"auto"`, skip the check with a warning when `FASTAPI_ENV` is `"development"`, and check it otherwise. The `fastapi dev` command sets `FASTAPI_ENV` to `"development"` if it is not already set."

`[VERIFIED: fastapi 0.141.1 introspection, this session]`

### `create_app()` skeleton — the assembly this phase exists to produce

This was **executed end-to-end** against the real frozen market module; `/api/health` returned a correct payload and `/api/stream/prices` streamed. `[VERIFIED: probe this session]`

```python
"""FastAPI application assembly."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI

from app.market import PriceCache, create_market_data_source, create_stream_router
from app.api.health import create_health_router

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

**Ordering note:** the `app.frontend()` call is placed last to match PLAN.md §11's rule, but this is *belt-and-braces*, not load-bearing. Verified: `/api/health` returned `200 {"status":"ok"}` with `app.frontend()` registered **before** `include_router()` as well. FastAPI checks path operations first regardless. `[VERIFIED: both orderings probed this session]` The genuinely load-bearing ordering is cache-before-router (steps 1-2), which is a Python argument-evaluation constraint, not a routing one.

### `/api/health` payload (CORE-08)

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

Both `PriceCache.newest_timestamp()` and `MarketDataSource.source_name` exist for exactly this purpose. Quoting the frozen source: `newest_timestamp()` — *"Timestamp of the most recently written price, for /api/health."* `[VERIFIED: backend/app/market/cache.py:112-117]`; `source_name` — *"Short identifier for logs and /api/health: 'simulator' or 'massive'."* `[VERIFIED: backend/app/market/interface.py:22-25]`

### SQLite connection + write transaction (CORE-05, D-03/D-04/D-05)

```python
"""Connection management: WAL, busy timeout, and the write-transaction seam."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

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


async def run_db(path: Path, fn: Callable[..., Any], *args: Any) -> Any:
    """The single event-loop offload seam (CORE-10, D-02)."""
    def _call() -> Any:
        ensure_initialized(path)
        with connect(path) as conn:
            return fn(conn, *args)
    return await asyncio.to_thread(_call)
```

**Stress-test result** `[VERIFIED: probe this session]` — 6 writer threads × 60 `BEGIN IMMEDIATE` read-modify-write operations, concurrent with 6 reader threads, against a real file database:

```
journal_mode: wal          busy_timeout: 5000
committed writes: 360 (expected 360)
final value: 360.0
OperationalErrors: 0
```

The final value equalling the write count proves no lost updates — `BEGIN IMMEDIATE` genuinely serialized the read-modify-write sequences rather than merely avoiding errors. This is the evidence for success criterion 3.

### SSE integration test — the pattern that works (D-21, CORE-03)

```python
"""SSE integration test via a real uvicorn server on an ephemeral port."""

from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from app.market import PriceCache, create_stream_router


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def sse_server() -> ...:
    cache = PriceCache()
    app = FastAPI()
    app.include_router(create_stream_router(cache))
    cache.update("AAPL", 190.50)          # seed directly; no simulator needed

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield port
    server.should_exit = True
    thread.join(timeout=10)


def test_stream_opens_and_carries_a_price_frame(sse_server: int) -> None:
    frames: list[str] = []
    url = f"http://127.0.0.1:{sse_server}/api/stream/prices"
    with httpx.stream("GET", url, timeout=10) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.strip():
                frames.append(line)
            if len(frames) >= 2:
                break
    assert frames[0] == "retry: 1000"
    assert any(f.startswith("data: ") and "AAPL" in f for f in frames)
```

Verified live output `[VERIFIED: probe this session]`:

```
STAGE 2: stream open -> 200 text/event-stream; charset=utf-8
   FRAME: retry: 1000
   FRAME: data: {"AAPL": {"ticker": "AAPL", "price": 190.5, "previous_price": 190.5, "open_price": 190.5, ...
STAGE 4: server stopped - PATTERN WORKS
```

**Heartbeat assertion** — drive the generator directly rather than waiting 15 real seconds. `_generate_events` accepts `interval` and `heartbeat` keyword arguments for exactly this (`stream.py:55-60`):

```python
async def test_heartbeat_is_emitted() -> None:
    class FakeRequest:
        client = None
        async def is_disconnected(self) -> bool:
            return False

    cache = PriceCache()
    cache.update("AAPL", 190.50)
    frames: list[str] = []
    gen = _generate_events(cache, FakeRequest(), interval=0.01, heartbeat=0.05)
    async for frame in gen:
        frames.append(frame)
        if len(frames) >= 3:
            break
    await gen.aclose()
    assert any(f.startswith(": ping") for f in frames)
```

Verified output: `['retry: 1000\n\n', 'data: {"AAPL": {"ticker": "AAP', ': ping\n\n']` → heartbeat seen. `[VERIFIED: probe this session]`

### `.gitattributes` (SETUP-03)

```gitattributes
* text=auto

*.sh        text eol=lf
Dockerfile  text eol=lf
*.dockerfile text eol=lf
*.ps1       text eol=crlf
*.bat       text eol=crlf
*.cmd       text eol=crlf

*.db  -text
*.png -text
```

Then, from a clean working tree:

```bash
git add --renormalize .
git status                 # shows what will be normalized
git commit -m "chore: normalize line endings"
```

Semantics, quoted from the official documentation `[CITED: git-scm.com/docs/gitattributes]`:

> "This attribute marks a path to use a specific line-ending style in the working tree when it is checked out. It has effect only if `text` or `text=auto` is set (see above), but **specifying `eol` automatically sets `text` if `text` was left unspecified**."

> `text eol=lf` — "This setting uses the same line endings in the working directory as in the index when the file is checked out."
> `text eol=crlf` — "This setting converts the file's line endings in the working directory to CRLF when the file is checked out."
> `-text` — "Unsetting the `text` attribute on a path tells Git not to attempt any end-of-line conversion upon checkin or checkout."

The `*.db -text` rule matters here specifically: `db/finally.db` is a tracked binary, and a bare `* text=auto` invites Git to inspect and potentially mangle it. This is a correctness fix, not decoration.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `app.mount("/", StaticFiles(html=True))` after all routers | `app.frontend(path, directory=..., fallback="index.html")` | FastAPI 0.138.0 (2026-06-20) | Removes the mount-order hazard entirely; adds Accept-aware SPA fallback. This is what SETUP-02 `[CORR]` buys |
| `@app.on_event("startup")` / `("shutdown")` | `lifespan=` async context manager | FastAPI 0.93 / deprecated since 0.109 | CORE-02 names this explicitly; the old form emits `DeprecationWarning` |
| `sqlite3.connect(..., isolation_level=None)` | still valid; `autocommit=False` attribute added | Python 3.12 (PEP 249 alignment) | Either works; `isolation_level=None` is the verified, simpler spelling |
| `journal_mode=DELETE` (SQLite default) | `journal_mode=WAL` | SQLite 3.7 (long-standing) | Readers no longer block writers — the premise of CORE-05 |

**Deprecated/outdated — do not use:**
- `@app.on_event(...)` — replaced by `lifespan`.
- Hand-rolled SPA catch-all routes — replaced by `app.frontend()`.
- `starlette.testclient.TestClient` **for streaming endpoints** — not deprecated generally, but unusable here (*Pitfall 2*). Note starlette 0.52.1 also emits `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead` — a signal that this compatibility path is being retired. `[VERIFIED: observed this session]`

## Gaps in the Requirements as Written

Four items the phase needs that no requirement currently names. Each is small; each blocks or degrades a stated criterion.

| # | Gap | Why it matters | Suggested handling |
|---|-----|----------------|--------------------|
| **A** | `httpx` is not a declared dev dependency | D-21's SSE test cannot run from a clean `uv sync --frozen --extra dev`. It currently imports only because `litellm` pulls it transitively — invisible and fragile. SETUP-01 does not mention it | Add `httpx>=0.28.0` to `[project.optional-dependencies].dev`. CONTEXT.md already flagged this under "Dependency gap found during scouting" |
| **B** | No `.python-version`; dev venv runs **Python 3.14.6**, Docker targets **3.12** | Two-runtime divergence. Already visible: `tests/conftest.py:11` triggers `DeprecationWarning: 'asyncio.DefaultEventLoopPolicy' is deprecated` ×154 on 3.14. A 3.12-only or 3.14-only behavior difference would surface first in Docker | Commit `backend/.python-version` containing `3.12` for parity with `DOCK-01`. Low cost, removes a whole class of "works locally, fails in the container" |
| **C** | SETUP-04 lists only `OPENROUTER_API_KEY`, `MASSIVE_API_KEY`, `LLM_MOCK` | D-12 introduces `FINALLY_DB_PATH`, and Phase 2's Dockerfile and start scripts depend on that exact name. An undocumented env var is how Phase 2 gets it wrong | Document `FINALLY_DB_PATH` in `.env.example` with its default and the Docker value `/app/db/finally.db` |
| **D** | WAL sidecars are not gitignored | D-03 enables WAL, which creates `db/finally.db-wal` and `db/finally.db-shm`. `git check-ignore` confirms **neither is ignored**; `.gitignore` only covers the unrelated `db.sqlite3-journal`. They would be committed on the next `git add .`, and PROJECT.md notes OneDrive independently syncs them | Add `db/*.db-wal` and `db/*.db-shm` to `.gitignore`. This does **not** untrack `finally.db` and so does not violate the accepted-risk constraint |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Committing a freshly-seeded `db/finally.db` is acceptable to the user (Pitfall 3, option 1) | Common Pitfalls | Product-visible. If unacceptable, first launch keeps showing $6,200.01 / 12 tickers and TEST-06 fails in Phase 7 |
| A2 | `test_custom_update_interval` may be treated as a tolerated known flake rather than a blocking regression | Pitfall 1 | SETUP-06 gate fails ~30% of runs for an unrelated reason; executor burns time hunting a phantom regression |
| A3 | Adding `db/*.db-wal` / `db/*.db-shm` to `.gitignore` does not violate "do not untrack `db/finally.db`" | Gap D | If read strictly, the sidecars get committed and OneDrive-synced, which is itself a corruption vector |
| A4 | Pinning `.python-version` to 3.12 is desirable | Gap B | Dev/prod runtime divergence persists; 3.14-only deprecations keep surfacing in local runs |
| A5 | `tests/market/` is not covered by the `backend/app/market/` freeze | Pitfall 1 | If it is frozen, option (c) for the flake is off the table and only restating SETUP-06 remains |
| A6 | The six-table DDL in the tracked database reflects the intended schema | Runtime State Inventory | It matches PLAN.md §7 on the two tables inspected (`users_profile` keyed on `id`; `positions` with `user_id` + `UNIQUE(user_id, ticker)`), but the other four were not read column-by-column. Write `schema.sql` from PLAN.md §7, not by dumping the existing file |

## Open Questions

1. **What should the tracked `db/finally.db` contain on `main`?**
   - What we know: it is tracked, 94 KB, six populated tables, $6,200.01 cash, 12 tickers, 4 positions, 26 chat messages. Untracking is explicitly forbidden. Tests use `tmp_path`, so the *test* suite is unaffected.
   - What's unclear: whether the user, when accepting the tracked-db risk, understood that a fresh clone inherits a used portfolio rather than the $10,000 first-launch state.
   - Recommendation: surface it in `/gsd-discuss-phase` or as a `checkpoint:human-verify` task. Default to option 1 (commit a freshly-seeded database) — it satisfies CORE-04's intent, preserves every accepted risk, and unblocks TEST-06.

2. **Is SETUP-06's "154 tests pass" a hard gate?**
   - What we know: 154/154 pass on current deps; the same suite yields 153/154 on FastAPI 0.141.1; and the one failure reproduces 3-in-10 on the **unmodified** environment. The bump is not the cause.
   - Recommendation: restate as "no new failures relative to the pre-phase baseline." Decide separately, with the user, whether the flake may be fixed given its proximity to the frozen module.

3. **Context7 was unavailable this session.**
   - What we know: the project's global `rules/context7.md` mandates Context7 for library docs; the MCP tool was not registered in this environment (`mcp__context7__resolve-library-id` → "No such tool available").
   - Mitigation applied: rather than fall back to web results alone, every load-bearing API claim was verified by **executing against the installed packages** — `inspect.signature`, live route probes, a real streaming server, and a threaded SQLite stress test. That is a stronger source than documentation for behavioral questions.
   - Residual risk: low for this phase. Phase 6 (LiteLLM structured outputs, already flagged "Unverified" in STATE.md) should re-attempt Context7 or spike the live path.

4. **Does `create_market_data_source()` belong in `create_app()` or behind a factory override for tests?**
   - What we know: it reads `MASSIVE_API_KEY` from the environment at call time (`factory.py:24`). A developer with that key set would have their test suite hit the real Massive API.
   - Recommendation: the D-22 conftest fixture should construct the app with the simulator explicitly, or clear `MASSIVE_API_KEY` for the test session. Cheap to do now; confusing to debug later.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Backend runtime | ✓ | 3.14.6 in `backend/.venv`; `requires-python >=3.12` | Pin `.python-version` to 3.12 (Gap B) |
| `uv` | All dependency work | ✓ | working (`uv lock`, `uv sync --frozen` both verified) | — |
| `git` | SETUP-03 renormalization | ✓ | working | — |
| SQLite | Persistence | ✓ | stdlib `sqlite3`, WAL verified working | — |
| FastAPI 0.141.1 | SETUP-02 / CORE-09 | ✓ | resolves + installs + `app.frontend()` present | — |
| `litellm` 1.95.0 | SETUP-01 | ✓ | resolves + imports | — |
| `httpx` | D-21 SSE test | ✓ present, ✗ **undeclared** | 0.28.1 (transitive) | Declare in dev extra (Gap A) |
| Node / npm | Frontend | ✗ | — | Not needed this phase; `backend/static/index.html` is a hand-written placeholder (D-11) |
| Docker | Container run | ✗ not checked | — | Phase 2 owns this; out of scope here |

**Missing dependencies with no fallback:** none — nothing blocks this phase.
**Missing dependencies with fallback:** `httpx` must be *declared* (it is installed); Node is not required until Phase 4.

**Environment-specific hazards confirmed this session:**
- `UV_LINK_MODE=copy` is required for `uv sync` to succeed against this OneDrive-backed tree (Pitfall 6a).
- Windows `MAX_PATH` leaves ~87 chars of headroom at the current project location (Pitfall 6b).

## Validation Architecture

`workflow.nyquist_validation` is `true` in `.planning/config.json`, so this section applies. `[VERIFIED: .planning/config.json]`

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 (`asyncio_mode = "auto"`) |
| Config file | `backend/pyproject.toml` → `[tool.pytest.ini_options]`, `testpaths = ["tests"]` |
| Quick run command | `cd backend && uv run --extra dev pytest -q tests/db tests/api` |
| Full suite command | `cd backend && uv run --extra dev pytest -q` |
| Lint command | `cd backend && uv run --extra dev ruff check app/ tests/` |
| Current baseline | **154 passed in 2.41s** `[VERIFIED: this session]` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CORE-01 | `create_app()` builds cache before routers; app constructs | unit | `pytest tests/test_main.py::test_create_app_builds -x` | ❌ Wave 0 |
| CORE-02 | Lifespan starts and stops the market source | integration | `pytest tests/test_main.py::test_lifespan_starts_and_stops_source -x` | ❌ Wave 0 |
| CORE-03 | SSE stream opens, carries a price frame and a heartbeat | integration | `pytest tests/market/test_stream_integration.py -x` | ❌ Wave 0 (uvicorn-in-thread — Pitfall 2) |
| CORE-04 | Fresh DB creates 6 tables; seeds $10k, 10 tickers, 1 snapshot | unit | `pytest tests/db/test_seed.py -x` | ❌ Wave 0 (`tmp_path`, D-19) |
| CORE-04 | Re-init on a populated DB seeds nothing (idempotent) | unit | `pytest tests/db/test_seed.py::test_seed_is_idempotent -x` | ❌ Wave 0 |
| CORE-05 | Concurrent snapshot + trade writes raise no `OperationalError` | integration | `pytest tests/db/test_concurrency.py -x` | ❌ Wave 0 (D-20; threads + `tmp_path`) |
| CORE-05 | Connection sets WAL and `busy_timeout` on every open | unit | `pytest tests/db/test_connection.py -x` | ❌ Wave 0 |
| CORE-06 | Rounding at 2dp/4dp; `is_zero` epsilon; full sell leaves no residue | unit | `pytest tests/db/test_money.py -x` | ❌ Wave 0 |
| CORE-07 | `PriceCache` reachable via DI; no module-level singleton | unit | `pytest tests/test_main.py::test_cache_via_dependency -x` | ❌ Wave 0 |
| CORE-08 | `/api/health` returns the four keys with correct types | unit | `pytest tests/api/test_health.py -x` | ❌ Wave 0 |
| CORE-09 | `/api/*` not shadowed; `/` serves index; unmatched JSON → 404 | integration | `pytest tests/test_main.py::test_api_not_shadowed -x` | ❌ Wave 0 (assert both Accept headers — Pitfall 7) |
| CORE-10 | Query functions run off the event loop | unit | `pytest tests/db/test_connection.py::test_run_db_offloads -x` | ❌ Wave 0 |
| TEST-01 | DB init + seeding + rounding covered | unit | `pytest tests/db -q` | ❌ Wave 0 |
| SETUP-01 | Chat deps import from a frozen sync | smoke | `uv run --frozen python -c "import litellm, pydantic, dotenv"` | ❌ Wave 0 |
| SETUP-06 | No new failures vs. the 154-test baseline | regression | `uv run --extra dev pytest -q` | ✅ exists (see Pitfall 1) |
| SETUP-03 | Line endings normalized | manual | `git ls-files --eol scripts/ Dockerfile` | n/a — inspection |

### Sampling Rate

- **Per task commit:** `uv run --extra dev pytest -q tests/db tests/api` (fast; the DB layer is where the risk is)
- **Per wave merge:** `uv run --extra dev pytest -q` + `uv run --extra dev ruff check app/ tests/`
- **Phase gate:** full suite green (modulo the known flake, Pitfall 1) before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/conftest.py` — extend with the `create_app()` + DB-dependency-override fixture (D-22); clear `MASSIVE_API_KEY` for the session (Open Question 4)
- [ ] `tests/db/__init__.py`, `tests/api/__init__.py` — packages currently hold only stale `__pycache__`
- [ ] `tests/db/test_connection.py` — WAL, busy_timeout, `writing()` rollback, `run_db` offload
- [ ] `tests/db/test_seed.py` — fresh seed + idempotency (CORE-04)
- [ ] `tests/db/test_queries.py` — every query function
- [ ] `tests/db/test_money.py` — rounding + epsilon (CORE-06/TEST-01)
- [ ] `tests/db/test_concurrency.py` — D-20 threaded contention
- [ ] `tests/api/test_health.py` — CORE-08
- [ ] `tests/test_main.py` — assembly, lifespan, DI, `/api/*` precedence
- [ ] `tests/market/test_stream_integration.py` — CORE-03 (**uvicorn-in-thread**, not `TestClient`)
- [ ] Dev dependency: `uv add --optional dev "httpx>=0.28.0"` (Gap A)

## Security Domain

`security_enforcement` is not set to `false`, so this section applies. Scope is narrow: no authentication exists by design, and the app binds to localhost for a single local operator.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No login by design (PLAN.md §2). `user_id` columns exist to allow it later without migration |
| V3 Session Management | no | No sessions; no cookies |
| V4 Access Control | no | Single hardcoded `user_id = "default"`; no multi-tenancy to enforce |
| V5 Input Validation | **yes** | `normalize_ticker` (`^[A-Z]{1,5}$`) for tickers; pydantic models for request bodies; parameterized SQL for every query |
| V6 Cryptography | no | No secrets stored, hashed, or transmitted by this phase |
| V7 Error Handling & Logging | **yes** | FastAPI's default `{"detail": ...}` envelope; never log `OPENROUTER_API_KEY` / `MASSIVE_API_KEY` values |
| V12 Files & Resources | **yes** | `app.frontend()` serves a fixed directory; path traversal is handled by FastAPI/Starlette, not by hand-rolled path joining |
| V14 Configuration | **yes** | `.env` gitignored; `.env.example` carries names and placeholders only, never real keys |

### Known Threat Patterns for FastAPI + SQLite

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via ticker or quantity | Tampering | Parameterized queries (`?` placeholders) everywhere — never f-string SQL. `executescript()` is used **only** for the static `schema.sql`, never with user input |
| Path traversal via static serving | Information Disclosure | Use `app.frontend()` with a fixed absolute directory; do not build a custom file-serving route |
| Secret leakage into git | Information Disclosure | `.env` gitignored (`.gitignore:138`); `.env.example` holds placeholders. Verify `.env` is absent from `git ls-files` after SETUP-04 |
| Secret leakage into logs | Information Disclosure | Log the *presence* of a key, never its value — e.g. `logger.info("Market data source: %s", name)` as `factory.py` already does |
| DB corruption via concurrent writers | Tampering / DoS | WAL + `busy_timeout` + `BEGIN IMMEDIATE` (CORE-05, verified). Note PROJECT.md's standing warning that a Windows Docker bind mount is a documented `database is locked` generator |
| WAL sidecars committed / cloud-synced | Tampering | Gap D — gitignore `db/*.db-wal` and `db/*.db-shm` |
| Unbounded SSE connections | DoS | Out of scope: single local user, single uvicorn worker (DOCK-06). Noted in CONCERNS.md as a multi-user concern only |

No new attack surface of consequence is introduced by this phase: no auth, no network egress beyond the optional Massive API already present, and no user-supplied file paths.

## Sources

### Primary (HIGH confidence — verified by execution against installed packages this session)

- `inspect.signature(fastapi.FastAPI.frontend)` on fastapi 0.141.1 — exact signature, keyword-only `directory`, `fallback` Literal, `check_dir` semantics and embedded `Doc()` text
- Live route-precedence probes (both registration orders × 4 paths × 4 Accept headers) — CORE-09 behavior, Pitfall 7 table
- Live `create_app()` probe against the real frozen market module — CORE-01, CORE-02, CORE-08
- uvicorn-in-thread SSE probe vs. `TestClient` / `ASGITransport` probes — CORE-03, Pitfall 2
- Threaded SQLite stress probe (6 writers × 60 ops + 6 readers) — CORE-05, Pitfall 4
- `uv lock` + clean `uv sync --frozen` + import probe — SETUP-01, SETUP-02, Pitfall 6
- `pytest -q` baseline (154 passed) and 10× flake measurement — SETUP-06, Pitfall 1
- `sqlite3` inspection of tracked `db/finally.db`; `git ls-files`, `git check-ignore` — Pitfall 3, Gaps C/D
- Repository sources read directly: `backend/app/market/{cache,stream,factory,interface,tickers,__init__}.py`, `backend/pyproject.toml`, `backend/tests/conftest.py`, `.planning/{REQUIREMENTS,STATE,PROJECT}.md`, `.planning/codebase/CONCERNS.md`, `.planning/config.json`, `.gitignore`

### Secondary (MEDIUM confidence — official documentation)

- `fastapi.tiangolo.com/tutorial/frontend/` — `app.frontend()` parameters, fallback modes, API precedence statement
- `git-scm.com/docs/gitattributes` — `text` / `eol` / `-text` semantics and `git add --renormalize .`
- `pypi.org/pypi/fastapi/json` — 0.141.1 is the current latest release

### Tertiary (LOW confidence — web search, used only for orientation and cross-checked above)

- `deepwiki.com/fastapi/fastapi/3.9-frontend-serving` — corroborated the 0.138.0 introduction and precedence claim; superseded by direct probing
- SQLite forum / community posts on WAL + `busy_timeout` — motivated the stress test; the test, not the posts, is the evidence
- Community `.gitattributes` best-practice posts — superseded by the official git-scm documentation

**Context7 MCP was unavailable this session** (`mcp__context7__resolve-library-id` not registered), so the project's `rules/context7.md` preference could not be honored. Compensated by direct execution against installed packages, which is a stronger source for behavioral claims than documentation. See Open Question 3.

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — every version resolved, installed and imported in a clean environment this session
- Architecture / app assembly: **HIGH** — the `create_app()` shape was executed against the real frozen module, not merely reasoned about
- SQLite concurrency: **HIGH** — stress-tested; 360/360 writes with zero errors and no lost updates
- Pitfalls: **HIGH** — all seven reproduced directly; Pitfall 6b was diagnosed to root cause rather than reported as observed
- Repo hygiene (SETUP-03/04/05): **HIGH** — current state confirmed by `git ls-files`, `git check-ignore`, filesystem listing
- Tracked-database impact (Pitfall 3): **HIGH** on the facts, **needs user input** on the remedy
- Security domain: **MEDIUM** — correctly scoped to a no-auth local app; low surface, low stakes

**Research date:** 2026-08-05
**Valid until:** 2026-09-04 (30 days). FastAPI's `frontend()` API is new (0.138.0, June 2026) and still evolving — re-verify the signature if the floor is ever raised past 0.141.x.
