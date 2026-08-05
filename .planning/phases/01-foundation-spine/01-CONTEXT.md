# Phase 1: Foundation & Spine - Context

**Gathered:** 2026-08-05
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase assembles the FastAPI application for the first time and lands the entire SQLite data layer beneath it.

**In scope:** `create_app()` factory, lifespan-managed market data source, the already-built SSE router mounted and reachable, `GET /api/health`, the static frontend fallback, the six-table schema with lazy init and seed data, every SQLite query function later phases call, the money/quantity rounding rules, and the dependency and repo-hygiene work in SETUP-01..06.

**Out of scope:** `/api/portfolio`, `/api/watchlist` and `/api/chat` routers and their services (Phase 3, Phase 6), the 30-second snapshot background task (Phase 3), the Dockerfile and start/stop scripts (Phase 2), any frontend beyond a placeholder `index.html` (Phase 4).

**Frozen:** `backend/app/market/` is consumed through `PriceCache`, `wait_for_price`, `create_market_data_source` and `create_stream_router(cache)` only. No phase modifies it.

</domain>

<decisions>
## Implementation Decisions

### Async database strategy

- **D-01:** SQLite access uses the stdlib `sqlite3` module, offloaded from the event loop with `asyncio.to_thread`. No `aiosqlite` dependency. This matches the pattern already in the codebase — `backend/app/market/massive_client.py` runs its blocking REST calls through `asyncio.to_thread` — and `aiosqlite` runs a thread per connection internally anyway, so it buys syntax rather than concurrency. — **Reversibility:** costly — undoing it rewrites every query signature and the call sites in the Phase 3 services and Phase 6 chat router that are built against them.

- **D-02:** Query functions in `app/db/queries.py` are plain `def` functions taking a connection as their first argument. The `asyncio.to_thread` offload lives in exactly one helper in `app/db/connection.py`, applied at the call site. Query functions are therefore directly callable in pytest with no event loop. — **Reversibility:** costly — this is the signature contract Phase 3's `services/trading.execute_trade()` and `services/watchlist.add/remove()` are written against, and the roadmap records those signatures as a contract.

### Connection and transaction model

- **D-03:** One connection per operation, opened by a context manager that sets WAL and `busy_timeout` on open and closes on exit. Not a shared long-lived connection behind a lock — that would serialize every read behind every write and discard the concurrency WAL was enabled to provide. It also sidesteps `sqlite3`'s `check_same_thread`, since `asyncio.to_thread` hands work to arbitrary executor threads. — **Reversibility:** costly — the test fixtures and every query call site assume it.

- **D-04:** `busy_timeout = 5000` ms. Long enough to absorb snapshot-versus-trade contention, short enough that a genuine locking problem surfaces as a visible error rather than a request that appears to hang. This is deliberate given the accepted OneDrive / Windows bind-mount risk: the roadmap instructs agents to *diagnose* `database is locked` if it appears, and a short timeout is what makes it visible.

- **D-05:** The `BEGIN IMMEDIATE` helper covers writes only — a `writing()` context manager that begins immediately, commits on success and rolls back on exception. Reads use plain autocommit connections; under WAL a reader already sees a consistent snapshot without an explicit transaction.

- **D-06:** Routers obtain the connection through a FastAPI dependency, sourced from the DB path held on `app.state`. No module-level connection singleton — the same rule CORE-07 applies to `PriceCache`. Tests override this one dependency. — **Reversibility:** costly — Phase 3's portfolio and watchlist routers and their route tests are built on this seam.

### Schema and lazy initialization

- **D-07:** The schema is a single `backend/app/db/schema.sql` executed with `connection.executescript()`. PLAN.md section 4 describes `app/db/` as holding "schema SQL definitions", and a single SQL file reads next to PLAN.md section 7 for a student inspecting the project. Hatchling's wheel target already packages everything under `app/`, so the `.sql` file ships.

- **D-08:** Lazy init is triggered from the connection helper: an idempotent `ensure_initialized(path)` guarded by a flag and a lock so it runs once per path. This covers every caller — request handlers and, later, the Phase 3 snapshot background task — with no way for a new call site to forget it. Explicitly not lifespan startup, which would be eager and read against CORE-04.

- **D-09:** `CREATE TABLE IF NOT EXISTS` always; seeding is gated on a single fresh-database check — does `users_profile` have a row? If not, seed the profile, the ten watchlist tickers and the first portfolio snapshot in one transaction. If it does, touch nothing. Consequence, deliberately chosen: a user who removes all ten tickers does **not** get them back on restart.

- **D-10:** The ten default watchlist tickers are named explicitly in the db seed module, not derived from `app.market.seed_prices.SEED_PRICES`. The default watchlist is user data; `SEED_PRICES` is simulator tuning that also feeds the Massive path. Adding a ticker there for simulator realism must not silently change what every new user sees on first launch.

### Runtime boundaries

- **D-11:** A placeholder `backend/static/index.html` is committed, stating that the backend is running. The static fallback is therefore real from day one, the "`/api/*` must not be shadowed" assertion in success criterion 1 has something to test against, and Phase 7's Docker build drops the Next.js export into the same directory. No runtime directory-creation branch — the directory is committed, so it always exists.

- **D-12:** The SQLite path resolves from a `FINALLY_DB_PATH` environment variable, defaulting to the repo-root `db/finally.db` by walking up from the package. Docker sets it explicitly to `/app/db/finally.db`. Pure derivation was rejected because it lands on `backend/db/` locally but `/app/db` in the container, silently diverging from the tracked, bind-mounted repo-root `db/`. — **Reversibility:** costly — Phase 2's Dockerfile, start scripts and `.env.example` all depend on the variable name.

- **D-13:** Configuration lives in one small `app/config.py` that calls `load_dotenv` on the project-root `.env` at import and exposes the values as constants. Plain `os.getenv`, no `pydantic-settings` dependency for four strings. This matches the existing style — `app/market/factory.py` already reads `MASSIVE_API_KEY` directly from the environment.

- **D-14:** `GET /api/health` lives in `app/api/health.py` as a `create_health_router(cache)` factory, mirroring the `create_stream_router(cache)` convention the market module established. It needs the cache injected anyway for `tickers_cached` and `newest_price_age_seconds`. This establishes the `app/api/` package that Phase 3 extends with `portfolio.py` and `watchlist.py`.

### Money and quantity rounding

- **D-15:** Stored precision: cash 2dp, share quantity 4dp, `avg_cost` 4dp. Quantity at 4dp is fixed by PLAN.md section 8. `avg_cost` keeps 4dp because it is a derived ratio rather than a price the user pays — rounding it to cents accumulates visible drift in unrealized P&L across repeated partial buys. — **Reversibility:** one-way — these are stored column values, so changing the precision after data exists requires rewriting existing rows, and `db/finally.db` is tracked in git, so a stale database persists into every clone.

- **D-16:** The zero-comparison epsilon is `1e-6` — two orders of magnitude below the 4dp quantity precision and far above float noise at these magnitudes. A remainder under `1e-6` after a full sell is arithmetic residue, never a real holding.

- **D-17:** `round_money()`, `round_quantity()` and `is_zero()` live in `app/db/money.py`. Phase 3's manual trade path and Phase 6's LLM-driven trade path both route through the same functions, which is the point of the service seam the roadmap records.

- **D-18:** Rounding applies at the write boundary only. Derived values — `market_value`, `unrealized_pnl`, `total_value` — are returned at full float precision and formatted by the client. This matches CORE-06's wording, and the frontend recomputes those figures from the SSE stream on every frame anyway, so server-side rounding would not be authoritative and would visibly disagree with the client's.

### Testing

- **D-19:** The test database is a real file per test via pytest's `tmp_path`. Not `:memory:` — it cannot exercise WAL, `busy_timeout` or genuine lock contention, which is the specific risk this phase carries, and with connection-per-operation each `:memory:` connection would get its own empty database.

- **D-20:** Phase 1 writes a real concurrency test for success criterion 3: drive the snapshot-write and trade-write query functions from concurrent threads against a tmp-file database and assert no `OperationalError`. Nothing in the codebase currently drives this code concurrently. The realistic collision between the 30s task and `execute_trade` belongs to Phase 3; this proves the query layer holds.

- **D-21:** The httpx-backed SSE integration test lands in this phase. `.planning/codebase/CONCERNS.md` records SSE as the module's weakest coverage (~31%) and names the reason precisely — there was no `main.py` to mount the router into. This phase creates it. The test asserts the stream opens and carries both a price frame and a heartbeat, covering CORE-03 directly.

- **D-22:** Tests point the app at the throwaway database by overriding the FastAPI DB dependency in a conftest fixture built around `create_app()`. Not by monkeypatching `FINALLY_DB_PATH`, which would depend on import-time ordering in `config.py` and is fragile across test sessions. Phase 3's route tests reuse this fixture verbatim.

### Claude's Discretion

The user selected the recommended option in every question, so no area was explicitly delegated. Left to the planner and executor: internal module decomposition beyond the file names fixed above, the exact wording of docstrings and log messages, and the mechanics of the SETUP-03 `.gitattributes` renormalization.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product specification (authoritative for behaviour and shapes)
- `planning/PLAN.md` §4 — directory structure, including the `backend/app/db/` and top-level `db/` split
- `planning/PLAN.md` §5 — environment variables; the backend runs from `backend/` but loads `../.env`
- `planning/PLAN.md` §7 — the six-table schema, column-by-column, and the seed data
- `planning/PLAN.md` §8 — API shapes, error envelope, `/api/health` payload, trade rules including the 4dp quantity limit
- `planning/PLAN.md` §11 — the static mount-order hazard: routers before the static mount
- `planning/PLAN.md` §13 — build order; step 1 is complete, this phase is step 2 plus app assembly

### Phase scope and constraints
- `.planning/ROADMAP.md` — Phase 1 goal, the five success criteria, and two load-bearing notes: the `create_app()` ordering constraint and the "every query function lands here" scope note
- `.planning/REQUIREMENTS.md` — SETUP-01..06, CORE-01..10, TEST-01, including the `[CORR]` corrections on CORE-05, CORE-06, CORE-09 and SETUP-02
- `.planning/PROJECT.md` — Key Decisions table; the OneDrive location and tracked `db/finally.db` are accepted risks, not tasks

### Existing code
- `backend/CLAUDE.md` — the market data public API surface as it is meant to be consumed
- `.planning/codebase/CONCERNS.md` — the SSE coverage gap and its stated cause, and the stale `__pycache__` inventory SETUP-05 clears
- `.planning/codebase/CONVENTIONS.md` — code style rules this phase must match
- `backend/app/market/__init__.py` — the exact exported surface: `PriceCache`, `wait_for_price`, `MarketDataSource`, `PriceUpdate`, `create_market_data_source`, `create_stream_router`, `TICKER_PATTERN`, `normalize_ticker`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`app.market.wait_for_price`** — already exported from `cache.py`. Phase 3's "poll the cache for up to 2 seconds for a first tick" rule is prebuilt; do not reimplement it.
- **`app.market.tickers.normalize_ticker` / `TICKER_PATTERN`** — the one shared `^[A-Z]{1,5}$` validation rule. The watchlist query functions landing in this phase must use it rather than defining a second rule.
- **`asyncio.to_thread` offload pattern** — `backend/app/market/massive_client.py` already runs blocking I/O this way. D-01 follows it rather than introducing a second async idiom.
- **Router-factory pattern** — `create_stream_router(price_cache)` in `stream.py` is the house convention. `create_health_router(cache)` (D-14) mirrors it.
- **`app.market.seed_prices.SEED_PRICES`** — holds the same ten tickers, but D-10 deliberately does not import it.

### Established Patterns

- `from __future__ import annotations` as the first import in every module
- Full type hints on every signature, including private helpers
- Docstrings carry the "why"; inline comments are rare
- `ruff` with `["E", "F", "I", "N", "W"]`, line-length 100, target py312
- `%s`-style lazy formatting in log calls, never f-strings; no emojis anywhere
- Module-level constants in `SCREAMING_SNAKE_CASE`
- Test files mirror their module 1:1 — `app/db/queries.py` → `tests/db/test_queries.py`

### Integration Points

- **`create_app()`** must construct `PriceCache` and the market source *before* `include_router(create_stream_router(cache))`, because the router factory takes the cache as an argument and registration happens before lifespan runs. This is the phase's stated ordering constraint.
- **Lifespan** starts and stops the market data source (CORE-02) — the cache itself is constructed earlier, in the factory body.
- **Static mount last**, after every `/api/*` router, via `app.frontend()` per SETUP-02 / CORE-09 `[CORR]`.
- **`backend/pyproject.toml`** gains `litellm`, `pydantic` and `python-dotenv` (SETUP-01) and raises the FastAPI floor to `>=0.141.1` (SETUP-02).

### Dependency gap found during scouting

`httpx` is **not** currently a dev dependency — `[project.optional-dependencies].dev` holds only pytest, pytest-asyncio, pytest-cov and ruff, and the existing `tests/market/test_stream.py` tests `_generate_events` directly rather than over HTTP. D-21's SSE integration test needs `httpx` added to the dev extra, and `uv.lock` regenerated. SETUP-01 as written does not mention it.

### API to verify, not assume

`app.frontend()` (SETUP-02, FastAPI `>=0.141.1`) is newer than the assistant's reliable knowledge. Its exact signature and directory-handling behaviour must be read from the installed package or current FastAPI docs during research — not recalled.

</code_context>

<specifics>
## Specific Ideas

- The short `busy_timeout` (D-04) is a diagnostic choice, not a performance one. If `database is locked` appears, the roadmap and PROJECT.md Key Decisions both say to diagnose it in place. No plan, task or success criterion may propose relocating the repo out of OneDrive, changing the `db/` bind-mount source, or untracking `db/finally.db`.
- The fresh-DB seed gate (D-09) has a user-visible consequence that is intended: an emptied watchlist stays empty across restarts.
- The `avg_cost` precision decision (D-15) is the one genuinely one-way choice in this phase, because a tracked database file carries the old values into every clone.

</specifics>

<deferred>
## Deferred Ideas

- **30-second portfolio snapshot background task** — Phase 3 (PORT-*). Its query function lands here; the task that calls it does not.
- **Reset Portfolio (PORT-14)** — Phase 3. It will want to reuse the seed logic written here, so shape the seed helper so a reset can call it rather than duplicating the $10,000 constant.
- **Realistic snapshot-task-versus-`execute_trade` collision test** — Phase 3, once both real callers exist. D-20 proves the query layer only.
- **Relaxing the exact `massive==2.2.0` pin** — tech debt recorded in `.planning/codebase/CONCERNS.md`; touching it would modify the frozen market module's dependency contract for no Phase 1 benefit.
- **`PriceCache.version` read outside the lock** — tech debt in the frozen module. Do not touch.

</deferred>

---

*Phase: 1-Foundation & Spine*
*Context gathered: 2026-08-05*
