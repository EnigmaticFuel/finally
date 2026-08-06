---
phase: 01-foundation-spine
plan: 02
subsystem: persistence
tags: [sqlite, wal, schema, seed, rounding, asyncio-to-thread, dependency-injection]
status: complete

requires:
  - "create_app() and app.state.db_path from plan 01-01"
  - "app / db_path pytest fixtures from plan 01-01"
provides:
  - "round_money, round_quantity, is_zero and the precision constants in backend/app/db/money.py"
  - "Six-table schema.sql, CREATE TABLE IF NOT EXISTS throughout"
  - "DEFAULT_TICKERS, STARTING_CASH, apply_schema, is_fresh_database, seed_fresh in backend/app/db/seed.py"
  - "connect, writing, ensure_initialized, get_db_path, run_db in backend/app/db/connection.py"
  - "dependency_overrides[get_db_path] as the test DB seam"
affects:
  - "plan 01-03 (wires main.py at DEFAULT_TICKERS; adds tests/db/test_concurrency.py against connect/writing)"
  - "plan 01-05 (the tracked db/finally.db decision, which this schema defines the shape of)"
  - "phase 3 portfolio and watchlist services (query signatures, run_db, the rounding rules)"
  - "phase 6 chat (chat_messages table; the same trade path through round_quantity)"

tech-stack:
  added: []
  patterns:
    - "Plain def query functions taking sqlite3.Connection first; one asyncio.to_thread seam in run_db"
    - "Connection per operation, PRAGMAs reapplied on every open"
    - "isolation_level=None plus explicit BEGIN IMMEDIATE / COMMIT / ROLLBACK"
    - "Seed gated on a fresh-database row count, never re-run"
    - "Real tmp_path file databases in every test, never :memory:"

key-files:
  created:
    - backend/app/db/__init__.py
    - backend/app/db/money.py
    - backend/app/db/schema.sql
    - backend/app/db/seed.py
    - backend/app/db/connection.py
    - backend/tests/db/__init__.py
    - backend/tests/db/test_money.py
    - backend/tests/db/test_seed.py
    - backend/tests/db/test_connection.py
  modified:
    - backend/tests/conftest.py

decisions:
  - "Tie-breaking documented as observed rather than as half-to-even: only exact binary ties (0.125) round to even, and 1.005 / 0.00005 / 0.00015 are decided by their stored binary value"
  - "seed_fresh takes a connection and a user_id and does only the writing, so Phase 3's Reset Portfolio can call it without duplicating STARTING_CASH"
  - "ensure_initialized memoizes on the resolved path; tests clear the memo to prove durable idempotency rather than memo idempotency"
  - "app.state.db_path left in place in main.py; only the get_db_path dependency is overridden in tests"
  - "DEFAULT_TICKERS deliberately left duplicated in main.py, per this plan's Task 2 instruction that plan 01-03 owns the rewiring"

metrics:
  duration: "~50m"
  completed: 2026-08-06
  tasks: 3
  commits: 3
  files_created: 9
  files_modified: 1

actuals:
  tokens: 7900
  tasks: 3
  commits: 3
---

# Phase 01 Plan 02: SQLite Foundation Summary

The whole persistence layer beneath the assembled app: one rounding rule every trade path will share, the six-table schema, a seed that runs exactly once, and a connection layer that gives writes WAL, a busy timeout and `BEGIN IMMEDIATE` while keeping the event loop free.

## What Was Built

**Rounding (`backend/app/db/money.py`).** `round_money` (2dp), `round_quantity` (4dp) and `is_zero` (epsilon `1e-6`). Three functions, no `Decimal`, no integer-cents layer — the columns are `REAL` and at $10,000 scale float64 has ample headroom past the cent. What the module deliberately does *not* have is any helper that rounds a derived value: `market_value`, `unrealized_pnl` and `total_value` stay at full precision because the frontend recomputes them from the SSE stream on every frame, and a server-side rounding would visibly disagree with the client's own arithmetic. The module docstring records why `avg_cost` keeps 4dp rather than 2, so a later reader does not "tidy" it to `MONEY_PLACES` and reintroduce P&L drift across repeated partial buys.

**Schema (`backend/app/db/schema.sql`).** Six tables transcribed column by column from PLAN.md section 7 — deliberately from the spec, not by dumping the tracked `db/finally.db`, whose contents RESEARCH.md flagged as only partially verified against the spec. `CREATE TABLE IF NOT EXISTS` on every statement, `UNIQUE (user_id, ticker)` on `watchlist` and `positions`, every `user_id` defaulting to `'default'`. No `realized_pnl` column, with the absence and its reasoning written into the file's header comment so it reads as deliberate rather than forgotten.

**Seed (`backend/app/db/seed.py`).** `DEFAULT_TICKERS`, `STARTING_CASH` and three functions. `apply_schema` reads the packaged `schema.sql` relative to `Path(__file__)` and runs it through `executescript` — the only `executescript` call in the codebase, and it never touches a caller-supplied string. `is_fresh_database` asks one question of one table. `seed_fresh` writes the profile, the ten watchlist rows with UUID primary keys and one snapshot at seed time, all through `?` placeholders.

The split between `is_fresh_database` and `seed_fresh` is the load-bearing shape here: the gate decision belongs to the caller, so Phase 3's Reset Portfolio can call `seed_fresh` directly rather than copying the `$10,000` constant into a second place.

**Connection layer (`backend/app/db/connection.py`).** Four sections. `connect()` opens with `isolation_level=None` and reapplies both PRAGMAs on every open. `writing()` runs `BEGIN IMMEDIATE`, commits on normal exit, rolls back and re-raises on failure. `ensure_initialized()` creates the parent directory, applies the schema and seeds inside one transaction, memoized per resolved path behind a `threading.Lock`. `run_db()` is the single `asyncio.to_thread` seam. `get_db_path()` is the FastAPI dependency reading `request.app.state.db_path`.

**Tests.** 33 new tests across three modules, every one against a real file database under `tmp_path`.

## Key Decisions

**The `isolation_level=None` argument is a correctness requirement, not a style choice.** The stdlib default of `''` is legacy implicit-transaction mode, where an explicit `BEGIN IMMEDIATE` raises `cannot start a transaction within a transaction` once any statement has opened one — and trivial single-statement tests still pass, so the defect hides. `test_autocommit_mode` and `test_begin_immediate_does_not_raise` pin both halves.

**`busy_timeout` is proven per-open, not per-file.** `journal_mode` persists in the database file; `busy_timeout` does not. A test that only checks the first connection would pass even if the PRAGMA had been "optimized" into `ensure_initialized`. `test_busy_timeout_reapplied_on_every_open` opens, closes, and opens a second connection to assert it there — that second open is the whole point of the test.

**Idempotency is proven durably, not through the memo.** `ensure_initialized` caches resolved paths, so calling it twice in one process is trivially a no-op and proves nothing about a restart. `test_running_twice_seeds_once` clears the memo between calls, so the second run genuinely re-opens the database, re-applies the schema and re-asks the fresh-database question. That is the property a restarted container actually depends on.

**The emptied-watchlist consequence is asserted, not just documented.** `TestEmptiedWatchlistIsNotRestored` seeds, changes cash, deletes every watchlist row, then re-runs the full schema-and-gate sequence and asserts the watchlist is still empty and cash is unchanged. Re-seeding on every startup would quietly overwrite an action the user took on purpose; this test is the thing that stops a future "helpful" change from doing it.

## Deviations from Plan

### Documentation correction (no code impact)

**1. The plan's stated tie-breaking contract was imprecise, and the code now states it accurately**

- **Found during:** Task 1
- **Issue:** The plan's `must_haves.truths` said `round_quantity(0.00005)` and `round_quantity(0.00015)` "resolve by Python's `round()` half-to-even rule". Probing the real interpreter before writing the assertions showed that is not what happens: neither value is an exact tie in binary, so half-to-even never applies to either. `round(0.00005, 4)` is `0.0001` because the stored double sits slightly *above* the decimal midpoint; `round(0.00015, 4)` is also `0.0001` because its stored double sits slightly *below* — which is the opposite of half-to-even, since `0.0002` is the even-last-digit answer.
- **Root cause (proven, not assumed):** ran the values through `uv run python` before writing a single assertion, rather than asserting the plan's description and discovering the mismatch as a red test.
- **Resolution:** the observed values are asserted exactly as measured, and the docstrings and test names now say what is actually true — `round()` is half-to-even on exact binary ties, and `0.125 -> 0.12` is included as the case where that genuinely fires. No behavior changed; only the description of it.
- **Files:** `backend/app/db/money.py`, `backend/tests/db/test_money.py`
- **Commit:** `3ab80a2`
- **Worth carrying forward:** the tie-breaking contract is now pinned by three asserted values per precision, so Phase 3 cannot drift it silently.

No Rule 1, 2, 3 or 4 deviations. Nothing was auto-fixed, nothing was blocked, no architectural question arose.

## Handoff Note: `DEFAULT_TICKERS` in `main.py`

The orchestrator's wave-1 handoff asked this plan to move `DEFAULT_TICKERS` out of `backend/app/main.py` and update the import site. **This plan's own Task 2 instructs the opposite, with a reason:** *"`app/main.py` currently names the ten tickers locally; leave that alone in this task — plan 01-03's wiring task points `main.py` at `DEFAULT_TICKERS` once `app/db/` is importable without a cycle."*

The plan is the authoritative artifact, so `main.py` was left untouched. Two consequences worth stating plainly:

1. The canonical list now lives in `backend/app/db/seed.py`. The copy in `main.py` is the duplicate, and plan 01-03 removes it.
2. The in-code note in `main.py` still reads "plan 01-02 moves the canonical list" — accurate about the list's destination, stale about which plan rewires the import. Plan 01-03 deletes those lines, which resolves the note as a side effect.

Not filed as a broken window: it is an intentional interim state with a named owner plan inside the same phase, exactly as plan 01-01's two handoffs were. Editing `main.py` here would also have risked a merge collision with another wave-2 worktree.

## Known Stubs

None. Every function in this plan has a real implementation and a test that exercises it.

## Threat Flags

None. The two mitigations this plan owns from the phase threat register are implemented and covered:

| Threat | Mitigation | Evidence |
|--------|-----------|----------|
| T-1-02 (concurrent writers) | WAL and `busy_timeout` on every open; `writing()` takes the write lock up front | `test_pragmas_applied_on_first_open`, `test_busy_timeout_reapplied_on_every_open`, `test_begin_immediate_does_not_raise`. Concurrency stress is plan 01-03's `test_concurrency.py` |
| T-1-04 (SQL construction) | Every insert binds `?`; `executescript` used only for the static packaged `schema.sql` | `seed.py` contains no f-string SQL and no user-supplied string reaches `executescript` |
| T-1-09 (write stalling the SSE stream) | All database work crosses `asyncio.to_thread` in `run_db` | `test_run_db_offloads` |

T-1-10 (path in logs) stays `accept` as registered: `ensure_initialized` logs the local operator's own filesystem path at info level.

## Verification

All checks run from `backend/`.

| Check | Result |
|-------|--------|
| `uv run --extra dev pytest -q` (full suite) | **203 passed**, 0 failed |
| `uv run --extra dev pytest -q tests/db -x` | 33 passed (plan required at least 16) |
| `uv run --extra dev pytest -q tests/db/test_money.py -x` | 13 passed (plan required at least 8) |
| `uv run --extra dev pytest -q tests/db/test_seed.py -x` | 8 passed (plan required at least 6) |
| `uv run --extra dev pytest -q tests/api tests/test_main.py` | 13 passed — the conftest change did not break the spine |
| `uv run --extra dev ruff check app/ tests/` | All checks passed |
| `git status --porcelain backend/app/market/` | empty — frozen module untouched |

**Regression gate (D-24):** plan 01-01 left the suite at 170 passing. It now runs 203 (170 + 33 new) with zero failures. The known flake `tests/market/test_simulator_source.py::test_custom_update_interval` passed on this run and was not touched.

**No in-memory databases:** `grep` over `tests/db/` finds no `:memory:`. Every database is a real file under `tmp_path`, per D-19 — `:memory:` cannot exercise WAL or `busy_timeout`, which is exactly what these tests exist to prove.

## Requirements Satisfied

| ID | Evidence |
|----|----------|
| CORE-04 | `TestEnsureInitialized::test_creates_and_seeds_a_missing_file` — six tables, $10,000 profile, ten tickers, one snapshot on a path with no file. `test_running_twice_seeds_once` and `TestEmptiedWatchlistIsNotRestored` cover the gate's deliberate consequence |
| CORE-05 | `TestConnect` (WAL and busy timeout on every open) and `TestWriting` (BEGIN IMMEDIATE, commit on success, rollback and re-raise on failure) |
| CORE-06 | `tests/db/test_money.py` — 2dp and 4dp boundaries, tie-breaking pinned by assertion, epsilon at `1e-7` / `1e-6` / `1.1e-6` / `-1e-7`, and a full sell provably leaving residue that `is_zero` reports as nothing |
| CORE-10 | `test_run_db_offloads` — the query function's `threading.get_ident()` differs from the calling coroutine's |
| TEST-01 | 33 tests covering initialization, seeding and rounding, all against real file databases |

## Notes for Future Phases

- **Query functions are plain `def` taking the connection first.** Call them directly in tests with no event loop; call them from a route with `await run_db(path, fn, *args)`. Do not add a second offload point — `run_db` is the one place to audit for CORE-10.
- **`run_db` initializes lazily on every call.** A route never needs to call `ensure_initialized` itself, and the 30-second snapshot task in Phase 3 will not either.
- **Do not wrap reads in `writing()`.** Under WAL a reader already sees a consistent snapshot; wrapping reads serializes readers behind writers for nothing.
- **Do not add a retry-on-`OperationalError` loop.** `PRAGMA busy_timeout` is SQLite's own busy handler with internal back-off, and a manual retry would defeat D-04's intent that a genuine locking problem surfaces visibly rather than as a request that appears to hang.
- **The test DB seam is `dependency_overrides[get_db_path]`.** The `app` fixture sets it; Phase 3's route tests reuse it verbatim. `app.state.db_path` still holds the real path and is only read through that dependency.
- **`ensure_initialized` memoizes per resolved path in module state.** A test that wants to re-exercise initialization must `connection._initialized.discard(path.resolve())` — the `db_file` fixture in `tests/db/test_connection.py` does this on teardown so paths do not leak between tests.
- **CRLF warnings on every new file are still expected** — `.gitattributes` is SETUP-03, owned by plan 01-04.

## Self-Check: PASSED

All 9 created files and the 1 modified file exist on disk and are tracked by git. All three task commits (`3ab80a2`, `8d5693c`, `a2a1df1`) are present in `git log`. `backend/app/market/` is unmodified.

**Note on `actuals.tokens`:** 7,900 is chars/4 over the 31,209 characters authored across the nine new files plus the small `conftest.py` edit. Against the plan's estimate of 75,000 the authored work came in an order of magnitude under, matching the pattern plan 01-01 recorded — the estimates appear to be sized for total phase context rather than diff volume.
