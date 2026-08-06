---
phase: 01-foundation-spine
verified: 2026-08-06T20:15:00Z
status: human_needed
score: 57/63 must-haves verified
behavior_unverified: 2
overrides_applied: 0
deferred:
  - truth: "The lazy database initialization is triggered by an HTTP request (`the first request creates and seeds it`)"
    addressed_in: "Phase 3"
    evidence: "Phase 3 success criterion 1: 'A user can read their portfolio — cash, total value, and every position with quantity, avg cost, current price, market value and unrealized P&L — and can buy or sell at the server's price'. Phase 1's roadmap scope note assigns query functions to Phase 1 and routers to Phase 3; `run_db` (the only caller of `ensure_initialized`) therefore has no app-side consumer until Phase 3's routers land."
behavior_unverified_items:
  - truth: "An interrupted `uv sync` leaves a partially installed venv that a plain re-run does not repair; deleting `backend/.venv` and re-syncing with `UV_LINK_MODE=copy` restores a complete, importable environment"
    test: "Interrupt a `uv sync --frozen --extra dev` mid-install, re-run it plainly and confirm it does NOT repair, then delete `backend/.venv` and re-sync with `UV_LINK_MODE=copy`"
    expected: "The plain re-run leaves the environment still broken; the delete-and-resync produces an environment where `uv run --frozen python -c \"import litellm, pydantic, dotenv, httpx, fastapi\"` succeeds"
    why_human: "The end state is proven (the frozen import smoke passes today), but the failure-and-recovery transition can only be exercised by destroying the working venv. Verification spot-checks are forbidden from mutating state, so the asserted recovery invariant is present-in-narrative but unexercised."
  - truth: "Concurrent requests to `/` and to `/api/*` are served independently under the `app.frontend()` registration; neither blocks nor corrupts the other"
    test: "With the app running, hold a request to `/` open (or issue `/` and `/api/health` concurrently under load) and confirm both complete with correct, uncorrupted bodies"
    expected: "`/` returns the static HTML and `/api/health` returns its four-key JSON, concurrently, with neither blocking nor truncating the other"
    why_human: "Declared `verification: backstop` in 01-01-PLAN.md, so it abstains absent explicit evidence. The nearest test (`test_concurrent_health_and_stream`) proves `/api/*` against `/api/*` under a held-open SSE stream, not `/` against `/api/*`. No test exercises the static-route-versus-API concurrency this truth names."
flagged_prohibitions:
  - requirement_id: TEST-01
    plan: "01-03"
    verification: test
    statement: "MUST NOT allow trade history to be edited or erased."
    disposition: unverified
    flagged: true
    evidence: "Current state is correct: an exhaustive grep over `backend/app/` finds zero `UPDATE trades` / `DELETE FROM trades` statements, and `queries.py` is documented and structured as the sole SQL module, with `insert_trade` its only writer. But no test asserts the absence, so nothing would catch a future query function that mutates the audit log. Test-tier prohibition with no wired enforcement — fail closed."
  - requirement_id: CORE-04
    plan: "01-05"
    verification: test
    statement: "MUST NOT destroy a developer's live local database without confirmation — the rewrite must refuse to proceed when the working copy differs from HEAD."
    disposition: unverified
    flagged: true
    evidence: "The plan's only modified file is `db/finally.db`; no gating script or check was committed. The git-status precondition was a procedural step the executor performed and recorded in 01-05-SUMMARY.md, leaving no artifact in the codebase to verify or to protect the next rewrite. Test-tier prohibition with no wired enforcement — fail closed."
  - requirement_id: CORE-08
    plan: "01-01"
    verification: judgment
    statement: "MUST NOT report a healthy status while the price feed is dead."
    disposition: llm_judge_satisfied_non_authoritative
    flagged: true
    evidence: "NON-AUTHORITATIVE LLM-judge verdict: satisfied. `create_health_router` computes `newest_price_age_seconds` from `price_cache.newest_timestamp()` at request time, returns `None` before any price exists rather than a fake zero, and `tests/api/test_health.py` pins both the None case and the non-negative-float case. Nothing is hardcoded green. Human review recommended — unverified-prohibition."
  - requirement_id: SETUP-06
    plan: "01-05"
    verification: judgment
    statement: "MUST NOT dismiss a genuine regression as the known flake."
    disposition: llm_judge_satisfied_non_authoritative
    flagged: true
    evidence: "NON-AUTHORITATIVE LLM-judge verdict: satisfied. The executor corrected the node ID, re-ran the test in isolation, and recorded a measured signature (timing-sensitive, not load-sensitive). The final suite is 243 passed / 0 failed, so no failure was tolerated at all. Caveat: 01-05-PLAN.md, 01-CONTEXT.md D-24 and 01-VALIDATION.md all name `tests/market/test_simulator.py::test_custom_update_interval`, a node ID that collects zero tests — the planning artifacts encode an unusable gate target. Human review recommended — unverified-prohibition."
human_verification:
  - test: "Interrupt a `uv sync --frozen --extra dev`, re-run it plainly, then delete `backend/.venv` and re-sync with `UV_LINK_MODE=copy`"
    expected: "The plain re-run does not repair the venv; the delete-and-resync yields a complete environment where litellm, pydantic, dotenv, httpx and fastapi all import"
    why_human: "Only exercisable by destroying the working venv — a state mutation verification may not perform"
  - test: "Issue concurrent requests to `/` and `/api/health` against the running app and confirm both complete correctly"
    expected: "Static HTML and the four-key health JSON both return intact; neither blocks nor corrupts the other"
    why_human: "Declared `verification: backstop`; no test covers static-route-versus-API concurrency"
  - test: "Decide whether the two flagged test-tier prohibitions need wired enforcement in this milestone"
    expected: "A decision on (a) adding a guard that the `trades` table stays append-only, and (b) whether the `db/finally.db` rewrite gate needs a committed script rather than a one-time procedure"
    why_human: "Both are correct in current state but have no automated guard; fail-closed policy requires an explicit human disposition"
  - test: "Confirm the two judgment-tier prohibitions (CORE-08 health honesty, SETUP-06 flake discipline) are accepted"
    expected: "Human accepts the LLM-judge verdicts, or requests changes"
    why_human: "Judgment-tier prohibitions are never silently passed by an autonomous verifier"
  - test: "Correct the flake node ID recorded across the planning artifacts"
    expected: "01-CONTEXT.md D-24 and 01-VALIDATION.md name `tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval` instead of the zero-collecting `tests/market/test_simulator.py::test_custom_update_interval`"
    why_human: "Documentation correction in decision records the verifier should not silently rewrite"
  - test: "Refresh 01-VALIDATION.md tracking state"
    expected: "Frontmatter leaves `status: draft` / `nyquist_compliant: false` / `wave_0_complete: false`, and the Per-Task Verification Map stops showing every row as `❌ W0` / `⬜ pending`, now that all referenced test files exist and pass"
    why_human: "Stale planning artifact; updating it is a planning decision, not a code fix"
---

# Phase 1: Foundation & Spine Verification Report

**Phase Goal:** The backend runs as one assembled FastAPI app with a lazily seeded database and a reachable live price stream
**Verified:** 2026-08-06T20:15:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

The goal is achieved. The app assembles in one `create_app()` factory, the price stream is reachable over real HTTP, and the database layer creates and seeds itself lazily with the exact first-launch state the specification promises. All five ROADMAP success criteria are verified against the codebase and against live command output, not against SUMMARY claims. What holds the phase short of a clean `passed` is not a defect in the built code: it is two truths whose runtime behavior no test exercises, and four prohibitions that fail closed for want of a wired guard.

### Observable Truths — ROADMAP Success Criteria

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | The assembled app streams live prices at `GET /api/stream/prices` for all ten default tickers with heartbeats, answers `GET /api/health` with market source, tickers cached and newest price age, and lets `/api/*` routes take precedence over the static frontend fallback | ✓ VERIFIED | `app/main.py` registers `create_health_router` and `create_stream_router` **before** `app.frontend()`. `tests/test_main.py::test_spine_end_to_end` drives a real uvicorn server: health 200 with exactly the four keys, stream 200 `text/event-stream` opening with `retry: 1000` followed by a `data:` frame, `/` 200 `text/html`. `test_api_not_shadowed` proves `/api/nope` returns 404 JSON for `Accept: application/json` and `*/*`. Heartbeat proven by `tests/market/test_stream_integration.py::TestHeartbeat::test_heartbeat_is_emitted` (asserts a frame starting `: ping`). Ten tickers proven by `test_lifespan_starts_and_stops_source` asserting `source.get_tickers() == list(DEFAULT_TICKERS)`. Corroborated by live HTTP: `{"status":"ok","market_source":"simulator","tickers_cached":10,...}` |
| 2 | On a machine with no database file, the first request creates and seeds it — six tables, one profile with $10,000 cash, ten watchlist tickers, and one portfolio snapshot | ✓ VERIFIED (creation + seed); trigger deferred | `tests/db/test_connection.py::TestEnsureInitialized::test_creates_and_seeds_a_missing_file` and `test_creates_a_missing_parent_directory` prove creation from nothing; `test_running_twice_seeds_once` proves idempotency. `tests/db/test_seed.py::TestApplySchema::test_creates_the_six_tables` and `TestSeedFresh::test_writes_profile_watchlist_and_snapshot` prove the exact shape. `ensure_initialized` is wired into `run_db`, and `get_db_path` reads `app.state.db_path` set by `create_app()`. **The `first request` half is not reachable in Phase 1** — see Deferred Items |
| 3 | A snapshot write and a trade write running at the same time never produce `database is locked`, and selling an entire position leaves no residual fractional shares | ✓ VERIFIED | `tests/db/test_concurrency.py::TestMixedWrites::test_snapshots_and_trades_written_concurrently` runs 3 snapshot threads against 3 trade threads, 20 writes each, on a real `tmp_path` file DB, asserting `errors == []` and exact final row counts. `TestLostUpdates` additionally asserts `final == STARTING_CASH + INCREMENT * len(commits)` — proving `BEGIN IMMEDIATE` serialized the read-modify-writes rather than merely avoiding errors. `TestBusyTimeout` proves the blocked writer *waits* (elapsed >= HOLD_SECONDS/2) rather than failing. Residual shares: `is_zero` epsilon 1e-6 in `app/db/money.py`, `TestFullSellLeavesNoResidue::{test_exact_full_sell, test_full_sell_after_partial_buys}`, and `delete_position` issuing a real `DELETE` (`test_delete_position_removes_the_row`) |
| 4 | `uv sync --frozen` from the committed lockfile produces an environment where the chat dependencies import cleanly and all 154 existing market-data tests still pass | ✓ VERIFIED | `uv run --frozen python -c "import litellm, pydantic, dotenv, httpx, fastapi"` → `imports ok 0.141.1`. `uv.lock` carries `fastapi 0.141.1`, `litellm`, `pydantic`, `python-dotenv`, `httpx`. `pytest --collect-only -q tests/market` → **157 collected** = the 154 pre-existing plus exactly the 3 new tests in `test_stream_integration.py`; full collection 243. Full suite 243 passed / 0 failed; `backend/app/market/` byte-identical across the phase |
| 5 | A fresh clone carries `.env.example` and a `.gitattributes` that keeps `.sh`/`Dockerfile` at LF and `.ps1` at CRLF, and no stale `__pycache__` trees remain under `backend/` | ✓ VERIFIED | `git check-attr text eol` resolves: `scripts/start_mac.sh → eol: lf`, `scripts/start_windows.ps1 → eol: crlf`, `Dockerfile → eol: lf`, `db/finally.db → text: unset`. `.env.example` tracked, documenting all four variables with placeholders only. `git ls-files \| grep -c __pycache__` → **0**; `.gitignore:2` ignores `__pycache__/`; the stale `app/{llm,services}` and `tests/{llm,services}` cache trees are gone (those directories are now empty) |

**ROADMAP score: 5/5 verified.**

### Observable Truths — Plan Must-Haves (roll-up)

| Plan | Truths | Verified | Not verified | Notes |
|------|--------|----------|--------------|-------|
| 01-01 | 16 | 14 | 1 behavior-unverified, 1 backstop-abstain | Assembly, lifespan, DI, route precedence and the SSE spine are all behaviorally proven over real HTTP |
| 01-02 | 14 | 14 | — | Rounding boundaries, tie-breaking, epsilon, WAL/busy_timeout re-application, `writing()` rollback-and-reraise, `run_db` offload and seed idempotency each have a named test |
| 01-03 | 11 | 11 | — | All 16 query functions exist as plain `def`s; every value is `?`-bound (whole file read); `insert_trade` is the sole writer of `trades`; `main.py` starts the source from `app.db.seed.DEFAULT_TICKERS` |
| 01-04 | 8 | 8 | — | Line-ending policy, `.env.example`, WAL sidecar ignores, `db/finally.db` still tracked, zero tracked bytecode |
| 01-05 | 9 | 5 | 4 uncertain | Seeded artifact and the green suite are verified; the four gate-*property* truths left no committed artifact |
| **Total** | **58** | **52** | **6** | |

**Combined score: 57/63 truths verified (5 ROADMAP + 52 plan), 2 behavior-unverified, 4 uncertain.**

Detail on the six non-verified items:

| Truth | Plan | Status | Reason |
|-------|------|--------|--------|
| Interrupted `uv sync` recovery via `UV_LINK_MODE=copy` | 01-01 | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | End state proven; the failure-and-recovery transition needs the venv destroyed to exercise |
| Concurrent `/` vs `/api/*` served independently | 01-01 | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED (backstop abstain) | Declared `verification: backstop`; no test covers static-vs-API concurrency |
| A baseline equal to the pre-phase failure set passes; one extra failing node fails it | 01-05 | ? UNCERTAIN | The regression gate left no committed artifact (`files_modified: db/finally.db` only) |
| An empty pre-phase failure set means any failure is a new failure | 01-05 | ? UNCERTAIN | Same — procedural, no artifact |
| The comparison is set-based over node IDs and order-independent | 01-05 | ? UNCERTAIN | Same — procedural, no artifact |
| The known flake is re-run in isolation before being tolerated | 01-05 | ? UNCERTAIN | Procedural; documented in SUMMARY and corroborated, but nothing in the repo enforces it. Moot for this run: 0 failures were tolerated |

None of the six is a FAILURE, and none blocks the phase goal. The four uncertain items describe properties of a one-off comparison procedure whose *outcome* — 243 passed, 0 failed, market module untouched — is independently verified.

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | The lazy init being triggered *by an HTTP request* (SC2's "the first request creates and seeds it") | Phase 3 | `run_db` — the only caller of `ensure_initialized` — has zero call sites in `backend/app/`; its only callers are tests. No Phase 1 route touches the database (`/api/health` reads the price cache; the SSE stream reads the cache). Phase 3 SC1 requires reading the portfolio over HTTP, which is the first request-side consumer. The ROADMAP's Phase 1 scope note assigns query functions here and routers to Phase 3 — this is by design, not an omission. The seam is fully wired and proven: `app.state.db_path` is set in `create_app()`, `get_db_path` reads it, and `tests/conftest.py` overrides exactly that dependency |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/main.py` | `create_app()` factory, lifespan handler, absolute STATIC_DIR | ✓ VERIFIED | 56 lines. Cache and source built in the factory body (lines 31-32) before both `include_router()` calls (52-53); `app.frontend()` last (54). `asynccontextmanager` lifespan, no `@app.on_event`. `STATIC_DIR` absolute via `Path(__file__).resolve()` |
| `backend/app/config.py` | `load_dotenv` on project-root `.env` plus DB_PATH, OPENROUTER_API_KEY, MASSIVE_API_KEY, LLM_MOCK | ✓ VERIFIED | `PROJECT_ROOT` walked from `parents[2]`, not CWD. `FINALLY_DB_PATH` honored with the repo-root `db/finally.db` default. `LLM_MOCK` exposed as bool |
| `backend/app/api/health.py` | `create_health_router(cache, source)` factory | ✓ VERIFIED | Router built inside the factory (no module-level route registration). Exactly four keys returned; age is `None` until a price exists |
| `backend/static/index.html` | Committed placeholder | ✓ VERIFIED | Tracked, 1672 bytes, real dark-theme HTML with the project palette — not an empty stub |
| `backend/pyproject.toml` | `fastapi>=0.141.1` floor plus litellm, pydantic, python-dotenv, httpx dev extra | ✓ VERIFIED | All five declared; lock resolves fastapi 0.141.1 |
| `backend/app/db/money.py` | round_money, round_quantity, is_zero, constants | ✓ VERIFIED | 2dp / 4dp / 1e-6. Exposes no derived-value rounding helper — the prohibition against it holds by inspection of the whole module |
| `backend/app/db/schema.sql` | Six-table DDL, `CREATE TABLE IF NOT EXISTS` throughout | ✓ VERIFIED | All six tables present, every one `IF NOT EXISTS`, `user_id` default `'default'` on all five non-profile tables, UNIQUE constraints on watchlist and positions |
| `backend/app/db/seed.py` | DEFAULT_TICKERS, STARTING_CASH, apply_schema, is_fresh_database, seed_fresh | ✓ VERIFIED | All five exported; ten tickers; `10000.0`; seed writes profile + 10 tickers + 1 snapshot |
| `backend/app/db/connection.py` | connect, writing, run_db, ensure_initialized, get_db_path | ✓ VERIFIED | `isolation_level=None`, both PRAGMAs on every open, memoized init behind a `Lock`, single `asyncio.to_thread` seam |
| `backend/app/db/queries.py` | 16-function query surface | ✓ VERIFIED | All 16 exported names present as plain `def`s taking `sqlite3.Connection` first; every value `?`-bound |
| `backend/tests/test_main.py` | Spine, lifespan, DI and route-precedence assertions | ✓ VERIFIED | 6 tests, uvicorn-in-thread, all passing |
| `backend/tests/market/test_stream_integration.py` | Uvicorn-in-thread SSE test and heartbeat assertion | ✓ VERIFIED | 3 tests including two-client independence and the `: ping` assertion |
| `backend/tests/db/{test_money,test_seed,test_connection,test_queries,test_concurrency}.py` | DB layer coverage | ✓ VERIFIED | 76 tests across the five files, all passing |
| `.gitattributes` | Line-ending policy plus binary exclusions | ✓ VERIFIED | `text=auto` baseline with `*.db -text` / `*.png -text` in the same file and same commit |
| `.env.example` | Template documenting all four variables | ✓ VERIFIED | Four variables, placeholders only, no credential |
| `.gitignore` | WAL sidecar ignore rules | ✓ VERIFIED | `db/*.db-wal` and `db/*.db-shm` (lines 213-214), scoped so `db/finally.db` stays tracked |
| `db/finally.db` | Freshly seeded tracked database | ✓ VERIFIED | Queried directly: six tables, cash `10000.0`, ten tickers matching DEFAULT_TICKERS, 1 snapshot, 0 positions / 0 trades / 0 chat messages. Still tracked; no WAL sidecars on disk |

No artifact is MISSING, STUB, ORPHANED or HOLLOW.

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app/main.py` | `app/market/stream.py` | `include_router(create_stream_router(cache))` | ✓ WIRED | Line 53, with the cache from line 31; `/api/stream/prices` present in `app.openapi()["paths"]` and reachable over HTTP |
| `app/main.py` | `app/api/health.py` | `include_router(create_health_router(cache, source))` | ✓ WIRED | Line 52, same cache object; `test_cache_via_dependency` proves the router reads the very cache on `app.state` |
| `app/main.py` | `backend/static/index.html` | `app.frontend("/", directory=STATIC_DIR, fallback="index.html")` | ✓ WIRED | Line 54, registered last; `/` returns 200 `text/html` |
| `app/main.py` | `app/config.py` | `app.state.db_path = DB_PATH` | ✓ WIRED | Line 50; consumed by `get_db_path`, and overridden by `conftest.py` — the DI seam is exercised |
| `app/db/connection.py` | `app/db/seed.py` | `ensure_initialized` → `apply_schema` then gated `seed_fresh` | ✓ WIRED | Lines 116-119, seed gated inside the same `writing()` transaction as `is_fresh_database` |
| `app/db/seed.py` | `app/db/schema.sql` | `apply_schema` reads and `executescript`s the packaged SQL | ✓ WIRED | Line 52 |
| `app/db/queries.py` | `app/market/tickers.py` | `normalize_ticker` on every ticker argument | ✓ WIRED | Applied in all 7 ticker-taking functions; `test_lowercase_ticker_is_stored_uppercased` and `test_invalid_ticker_raises` prove it |
| `app/main.py` | `app/db/seed.py` | lifespan starts the source from `DEFAULT_TICKERS` | ✓ WIRED | Line 13 import, line 43 use; asserted by `test_lifespan_starts_and_stops_source` |
| `tests/db/test_concurrency.py` | `app/db/connection.py` | threads drive `writing()` against one `tmp_path` file DB | ✓ WIRED | Real file DB, real threads, real contention |
| `.env.example` | `app/config.py` | documents the exact names config reads incl. `FINALLY_DB_PATH` | ✓ WIRED | All four names match `config.py` exactly |
| `.gitignore` | `app/db/connection.py` | ignores the sidecars `PRAGMA journal_mode=WAL` creates | ✓ WIRED | Scoped rules, `db/finally.db` unaffected |
| `db/finally.db` | `app/db/seed.py` | generated by `apply_schema` + `seed_fresh` | ✓ WIRED | Content-equivalence verified by direct query; the committed artifact matches exactly what the lazy-init path produces |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `app/api/health.py` | `newest`, `len(price_cache)` | `PriceCache.newest_timestamp()` / `__len__`, live cache written by the simulator task | Yes — live HTTP showed `tickers_cached: 10`, `newest_price_age_seconds: 0.263` | ✓ FLOWING |
| `app/market/stream.py` (mounted) | SSE frames | `PriceCache` version-change detection | Yes — frames carry `open_price` and `change_from_open_percent` per ticker | ✓ FLOWING |
| `app/db/queries.py` | rows | real SQLite statements against a real file DB | Yes — no static returns; every function issues SQL and returns its result | ✓ FLOWING |
| `db/finally.db` | seeded rows | `seed_fresh` | Yes — 10000.0 cash, 10 tickers, 1 snapshot read back from the committed file | ✓ FLOWING |
| `backend/static/index.html` | static markup | n/a — deliberate placeholder | n/a (Phase 4 replaces it with the Next.js export) | ✓ N/A |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Chat dependencies import from the frozen lockfile | `uv run --frozen python -c "import litellm, pydantic, dotenv, httpx, fastapi; print(...)"` | `imports ok 0.141.1` | ✓ PASS |
| Market-data test count is 154 pre-existing + the 3 new SSE tests | `uv run --extra dev pytest --collect-only -q tests/market` | `157 tests collected` | ✓ PASS |
| Whole suite collects | `uv run --extra dev pytest --collect-only -q` | `243 tests collected` | ✓ PASS |
| Phase-owned tests pass (assembly, health, DB, SSE integration) | `uv run --extra dev pytest -q tests/db tests/api tests/test_main.py tests/market/test_stream_integration.py` | `89 passed, 2 warnings in 6.46s` | ✓ PASS |
| Lint clean | `uv run --extra dev ruff check app/ tests/` | `All checks passed!` | ✓ PASS |
| Committed database carries the fresh seed | direct `sqlite3` query of `db/finally.db` | 6 tables; cash 10000.0; 10 tickers; snapshots 1; positions/trades/chat 0 | ✓ PASS |
| Line-ending policy resolves correctly | `git check-attr text eol -- scripts/start_mac.sh scripts/start_windows.ps1 Dockerfile db/finally.db` | `lf`, `crlf`, `lf`, `text: unset` | ✓ PASS |
| Renormalization did not rewrite the tracked binary | `git show --stat 54c861c` / `git show --numstat 54c861c -- db/finally.db` | Commit touched `.gitattributes` only (24 insertions); `db/finally.db` untouched | ✓ PASS |
| No tracked bytecode | `git ls-files \| grep -c __pycache__` | `0` | ✓ PASS |
| Python pinned to the Docker target | `cat backend/.python-version` / `uv run python -V` | `3.12` / `3.12.13` | ✓ PASS |

The full suite was not re-run — the orchestrator's `243 passed, 0 failed` is relied upon, and collection counts plus the 89-test phase-owned run were used as independent corroboration.

### Probe Execution

No probes are declared by any plan and no `scripts/*/tests/probe-*.sh` exists in the repository. **Step 7c: SKIPPED (no probes declared or discoverable).**

### Requirements Coverage

Union of `requirements:` across the five plans = SETUP-01…06, CORE-01…10, TEST-01 — exactly the 17 IDs ROADMAP.md maps to Phase 1. **Zero orphaned requirements.**

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SETUP-01 | 01-01 | litellm, pydantic, python-dotenv declared and locked | ✓ SATISFIED | Declared in `pyproject.toml`; present in `uv.lock`; frozen import smoke passes |
| SETUP-02 | 01-01 | FastAPI floor raised to `>=0.141.1` for `app.frontend()` | ✓ SATISFIED | `fastapi>=0.141.1` declared, lock resolves 0.141.1, `app.frontend()` in use at `main.py:54` |
| SETUP-03 | 01-04 | `.gitattributes` LF for `.sh`/Dockerfile, CRLF for `.ps1`, repo renormalized | ✓ SATISFIED | `git check-attr` output above; renormalization commit staged no content change |
| SETUP-04 | 01-04 | `.env.example` documenting the three named variables | ✓ SATISFIED | All three plus `FINALLY_DB_PATH` (D-26), placeholders only |
| SETUP-05 | 01-04 | Stale `__pycache__` under `app/{api,db,llm,services}` and `tests/{api,db,llm,services}` removed | ✓ SATISFIED | The four `llm`/`services` directories are empty of caches; zero bytecode tracked. Caches under `app/{api,db}` are live regenerated artifacts for modules that now exist, not stale trees |
| SETUP-06 | 01-05 | The 154 market-data tests still pass after dependency changes | ✓ SATISFIED | 157 collected in `tests/market` (154 + 3 new); full suite 243 passed / 0 failed; market module byte-identical |
| CORE-01 | 01-01 | `create_app()` builds PriceCache and source before router registration | ✓ SATISFIED | `main.py:31-32` before `:52-53`; `test_create_app_builds_cache_before_routers` |
| CORE-02 | 01-01 | Market task starts/stops with lifespan, not a startup event | ✓ SATISFIED | `asynccontextmanager` lifespan; `test_lifespan_starts_and_stops_source` asserts the `simulator-loop` task appears on enter and is gone on exit. No `@app.on_event` anywhere |
| CORE-03 | 01-01 | SSE router mounted; `/api/stream/prices` streams from the running app | ✓ SATISFIED | `test_spine_end_to_end` and `test_stream_integration.py` over real uvicorn; live HTTP confirmed |
| CORE-04 | 01-02, 01-03, 01-05 | Lazy create + seed: six tables, $10k profile, ten tickers, one snapshot | ✓ SATISFIED | `TestEnsureInitialized`, `TestApplySchema`, `TestSeedFresh`, `TestSeedGate`; committed `db/finally.db` matches. Request-triggered invocation deferred to Phase 3 (see Deferred Items) |
| CORE-05 | 01-02, 01-03 | WAL, busy timeout, `BEGIN IMMEDIATE` so snapshot and trade cannot collide | ✓ SATISFIED | `connect()` applies both PRAGMAs on every open (`test_busy_timeout_reapplied_on_every_open`); `test_concurrency.py` proves zero `OperationalError` and zero lost updates under 6-way contention |
| CORE-06 | 01-02 | Round at the write boundary, compare with epsilon, no residual shares | ✓ SATISFIED | `money.py` + `TestFullSellLeavesNoResidue` + `test_insert_trade_rounds_at_the_write_boundary` |
| CORE-07 | 01-01 | Shared `PriceCache` reachable by DI without a module-level singleton | ✓ SATISFIED | `app.state.price_cache`; `test_cache_via_dependency` also asserts `create_app().state.price_cache is not app.state.price_cache` — no singleton |
| CORE-08 | 01-01 | `/api/health` returns the four-key payload | ✓ SATISFIED | Exactly four keys asserted in both `test_health.py::test_payload_is_exactly_four_keys` and `test_main.py`; `test_payload_never_names_an_api_key` guards the leak case |
| CORE-09 | 01-01 | Static frontend served same-origin without shadowing `/api/*` | ✓ SATISFIED | `test_api_not_shadowed` over real HTTP for `application/json`, `*/*` and `text/html` |
| CORE-10 | 01-02, 01-03 | DB access never blocks the event loop | ✓ SATISFIED | Single `asyncio.to_thread` seam in `run_db`; `test_run_db_offloads` asserts the query runs on a different thread than the caller |
| TEST-01 | 01-02, 01-03 | Tests cover DB init, seeding, and the rounding rules | ✓ SATISFIED | 76 tests across `tests/db/`; init, seed gate, idempotency, rounding boundaries and tie-breaking all covered |

### Prohibitions

| # | Requirement | Tier | Statement (abbrev.) | Disposition |
|---|-------------|------|---------------------|-------------|
| 1 | CORE-08 (01-01) | judgment | Must not report healthy while the feed is dead | ⚠️ FLAGGED — non-authoritative LLM-judge: satisfied. Human review recommended |
| 2 | CORE-04 (01-02) | test | Must not silently restore a deliberately emptied watchlist | ✓ VERIFIED — `test_seed.py::TestEmptiedWatchlistIsNotRestored::test_user_emptied_watchlist_stays_empty` wires real enforcement |
| 3 | TEST-01 (01-03) | test | Must not allow trade history to be edited or erased | ⚠️ FLAGGED — correct today (grep over `app/` finds zero `UPDATE`/`DELETE` on `trades`), but no test guards it. Fail closed |
| 4 | SETUP-03 (01-04) | test | Renormalization must not rewrite the tracked binary DB | ✓ VERIFIED — `*.db -text` shipped in the *same commit* as `* text=auto` (54c861c touched only `.gitattributes`), and `db/finally.db` came through byte-identical |
| 5 | SETUP-04 (01-04) | test | Must not commit a real credential in `.env.example` | ✓ VERIFIED — full file read: one placeholder string, three empty/false values, no credential |
| 6 | CORE-04 (01-05) | test | Rewrite must refuse when the working copy differs from HEAD | ⚠️ FLAGGED — procedural only; no gating artifact committed. Fail closed |
| 7 | SETUP-06 (01-05) | judgment | Must not dismiss a genuine regression as the known flake | ⚠️ FLAGGED — non-authoritative LLM-judge: satisfied (0 failures were tolerated). Human review recommended |

Four flagged prohibitions. Per the fail-closed policy none is counted green, and each is carried into human verification.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | None found |

A scan of every file this phase created or modified (`app/main.py`, `app/config.py`, `app/api/`, `app/db/`, `tests/test_main.py`, `tests/api/`, `tests/db/`, `tests/market/test_stream_integration.py`, `static/`) found **zero** `TBD`/`FIXME`/`XXX` debt markers, zero `TODO`/`HACK`/`PLACEHOLDER` comments, and no empty-implementation or console-log-only patterns. `ruff check app/ tests/` reports `All checks passed!`. The one "placeholder" in the phase — `backend/static/index.html` — is a deliberate, user-decided artifact (D-11) with real content, existing so the `/api/*`-must-not-be-shadowed assertion is testable from day one.

### Context Decisions (D-01 … D-28)

All 28 decisions from 01-CONTEXT.md were checked against the code. All 28 are honored. Spot-notes on the ones easiest to have drifted:

- **D-04** `busy_timeout = 5000` — `BUSY_TIMEOUT_MS = 5000`, reapplied on every open
- **D-10** default tickers named in the db seed module, not imported from `SEED_PRICES` — confirmed; `seed.py`'s docstring states the reason
- **D-15** cash 2dp, quantity 4dp, `avg_cost` 4dp — `upsert_position` passes `avg_cost` through `round_quantity`, not `round_money`
- **D-19** real `tmp_path` file DBs, never `:memory:` — confirmed across all five db test files
- **D-22** DB path arrives via `dependency_overrides[get_db_path]`, not by monkeypatching the env var — confirmed in `conftest.py`
- **D-25** `httpx>=0.28.0` in the dev extra — confirmed
- **D-28** `backend/.python-version` committed as `3.12` — confirmed, and the venv now runs 3.12.13 (was 3.14.6 pre-phase)

### Planning-Artifact Defects (non-blocking)

These do not affect the built code but should not be lost:

1. **Wrong flake node ID recorded in three places.** `01-05-PLAN.md`, `01-CONTEXT.md` (D-24) and `01-VALIDATION.md` all name `tests/market/test_simulator.py::test_custom_update_interval`. That node ID collects zero tests. The real one is `tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval`. The executor caught and corrected this at execution time, so the gate itself was sound — but the decision records still encode an unusable target for anyone who reads them next.
2. **`01-VALIDATION.md` is stale.** Frontmatter still reads `status: draft`, `nyquist_compliant: false`, `wave_0_complete: false`, and every row of the Per-Task Verification Map still shows `❌ W0` / `⬜ pending` — despite all eleven referenced test files now existing and passing.
3. **`01-05-SUMMARY.md` omits the `## Self-Check:` line** the other four summaries carry, using richer frontmatter (four `verification: status: pass` entries) instead. Formatting inconsistency, not a missing verification.

### Human Verification Required

#### 1. Interrupted `uv sync` recovery

**Test:** Interrupt a `uv sync --frozen --extra dev` mid-install, re-run it plainly, then delete `backend/.venv` and re-sync with `UV_LINK_MODE=copy`.
**Expected:** The plain re-run does not repair the partially installed venv; the delete-and-resync produces an environment where litellm, pydantic, dotenv, httpx and fastapi all import.
**Why human:** The end state is already proven, but exercising the recovery invariant requires destroying the working venv — a state mutation verification may not perform.

#### 2. Concurrent `/` and `/api/*`

**Test:** With the app running, issue concurrent requests to `/` and `/api/health`.
**Expected:** Static HTML and the four-key health JSON both return intact; neither blocks nor corrupts the other.
**Why human:** Declared `verification: backstop`, so it abstains without explicit evidence. The nearest test covers `/api/*` against `/api/*` under a held-open SSE stream, not `/` against `/api/*`.

#### 3. Disposition of the two flagged test-tier prohibitions

**Test:** Decide whether (a) the `trades` append-only rule and (b) the `db/finally.db` rewrite gate need wired enforcement in this milestone.
**Expected:** Either a guard is added (a test asserting no query function mutates `trades`; a committed precondition check for the DB rewrite), or the deviation is explicitly accepted.
**Why human:** Both are correct in current state but have no automated guard. Fail-closed policy requires an explicit human disposition rather than a silent pass.

#### 4. Acceptance of the two judgment-tier prohibitions

**Test:** Review the LLM-judge verdicts on CORE-08 (health honesty) and SETUP-06 (flake discipline).
**Expected:** Accepted, or changes requested.
**Why human:** Judgment-tier prohibitions are never silently passed by an autonomous verifier.

#### 5. Correct the flake node ID in the decision records

**Test:** Update `01-CONTEXT.md` D-24 and `01-VALIDATION.md` to name `tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval`.
**Expected:** No planning artifact points at a node ID that collects zero tests.
**Why human:** A documentation correction to decision records the verifier should not silently rewrite.

#### 6. Refresh `01-VALIDATION.md` tracking state

**Test:** Update the frontmatter and the Per-Task Verification Map.
**Expected:** `wave_0_complete: true`, rows reflecting the eleven test files that now exist and pass.
**Why human:** Planning-artifact maintenance, not a code fix.

### Gaps Summary

**No gaps.** No must-have failed, no artifact is missing or stubbed, no key link is unwired, and no blocking anti-pattern exists. All five ROADMAP success criteria are verified against real command output and real file contents, and all 17 requirement IDs are satisfied with none orphaned.

The phase does not reach `passed` for two reasons, neither of which is a defect in the delivered code:

1. **Two truths assert runtime behavior no test exercises.** The interrupted-`uv sync` recovery invariant cannot be re-verified without destroying the environment, and the `/`-versus-`/api/*` concurrency truth is explicitly declared `backstop`, which abstains absent evidence. Both are present and wired; neither is behaviorally proven.
2. **Four prohibitions fail closed.** Two test-tier prohibitions (trades append-only, and the DB-rewrite git-status gate) are correct in current state but have no wired guard, and two judgment-tier prohibitions require human acceptance by policy. None may be silently absorbed into a green verdict.

One item is **deferred, not missing**: SC2's "the first request creates and seeds it" clause. The creation-and-seeding behavior is fully proven; what does not exist yet is a request handler that touches the database, because the ROADMAP assigns routers to Phase 3. The seam is complete and exercised — `run_db` calls `ensure_initialized`, `app.state.db_path` is set by `create_app()`, and `conftest.py` already overrides `get_db_path`, proving the DI path works end to end. Phase 3's first portfolio read will light it up with no further wiring.

A note on scrutiny applied: the SUMMARY files were read only for their claims, and every claim scored above was re-derived from the code, from git, from live command output, or from a direct query of the committed database. The two most load-bearing claims — that the SSE spine works over real HTTP and that concurrent writes lose nothing — were checked against the assertions inside the tests themselves rather than against a passing count, because a concurrency test that asserts only "no exception raised" would pass while proving nothing. Both assert final stored values, not merely absence of errors.

---

_Verified: 2026-08-06T20:15:00Z_
_Verifier: Claude (gsd-verifier)_
