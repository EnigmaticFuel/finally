---
phase: 03-portfolio-watchlist-apis
plan: 05
subsystem: api
tags: [fastapi, asyncio, sqlite, background-task, lifespan, pytest]

requires:
  - phase: 01-foundation-spine
    provides: run_db, writing, get_latest_snapshot, insert_snapshot, round_money, the app fixture
  - phase: 03-portfolio-watchlist-apis
    provides: value_portfolio (03-03), execute_trade (03-02), the watchlist seam (03-04)
provides:
  - A lifespan-owned snapshot-loop task recording portfolio value every 30 seconds
  - record_snapshot, the directly callable loop body, and the _record_if_changed transaction
  - The cents-rounded unchanged-value skip (D-16), reusing money.py
  - A conftest guard keeping any background writer off the git-tracked database
  - The reconciled app.services public surface - 19 names, every one importable
affects: [05-charts, 06-chat-llm]

actuals:
  tokens: 12500
  tasks: 4
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Read-modify-write background writer inside one BEGIN IMMEDIATE, sharing the trade path's lock"
    - "Sleep-first loop ordering as a safety property, not a style choice"
    - "Loop body extracted as a separately callable coroutine so no test waits on the interval"

key-files:
  created:
    - backend/app/services/snapshots.py
    - backend/tests/services/test_snapshots.py
  modified:
    - backend/app/main.py
    - backend/app/services/__init__.py
    - backend/tests/conftest.py
    - backend/tests/test_main.py

key-decisions:
  - "The snapshot recorder wraps its reads in writing() - the one deliberate departure from connection.py's reads-do-not-use-writing note, because this is a read-modify-write on the rows execute_trade also touches"
  - "A None from get_latest_snapshot writes rather than skips: with nothing to compare against, recording is the honest answer"
  - "The trade-collision test uses a constant fill price so a completed portfolio is always worth exactly STARTING_CASH, making any interleaving artifact a visible assertion failure without forcing the interleaving"
  - "app/services/__init__.py exports the 19 names the plan enumerated; trading.py's PRICE_WAIT_SECONDS and VALID_SIDES stay module-local"

patterns-established:
  - "Background writer: async seam captures cache state, plain def executor runs one writing() block over already-fetched arguments"
  - "Interval constants are asserted directly rather than slept through, so no test duration depends on production cadence"

requirements-completed: [PORT-12]

coverage:
  - id: D1
    description: "A running app records portfolio value every 30 seconds with no request involved, via a lifespan-owned asyncio task named snapshot-loop"
    requirement: PORT-12
    verification:
      - kind: unit
        ref: "backend/tests/test_main.py#test_lifespan_starts_and_stops_source"
        status: pass
      - kind: unit
        ref: "backend/tests/services/test_snapshots.py#TestSnapshotLoop::test_the_interval_is_thirty_seconds"
        status: pass
    human_judgment: false
  - id: D2
    description: "The write is skipped when the cents-rounded total is unchanged, and taken when it moved by a cent, when nothing exists to compare against, or when only cash is held"
    requirement: PORT-12
    verification:
      - kind: unit
        ref: "backend/tests/services/test_snapshots.py#TestRecordSnapshot (8 tests: unchanged, moved, repeat, adjacency, empty, cash-only, priceless, precision)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The task is cancelled before source.stop() and does not outlive the lifespan; a short-lived app records nothing because the loop sleeps first"
    requirement: PORT-12
    verification:
      - kind: unit
        ref: "backend/tests/test_main.py#test_lifespan_records_no_snapshot_on_a_short_life"
        status: pass
      - kind: unit
        ref: "backend/tests/services/test_snapshots.py#TestSnapshotLoop::test_the_loop_writes_nothing_before_its_first_interval"
        status: pass
    human_judgment: false
  - id: D4
    description: "A snapshot never records a total the portfolio did not hold, proven against a concurrent execute_trade"
    requirement: PORT-12
    verification:
      - kind: integration
        ref: "backend/tests/services/test_snapshots.py#TestTradeCollision::test_a_concurrent_trade_never_leaves_a_total_never_held"
        status: pass
    human_judgment: false
  - id: D5
    description: "No test writes to the git-tracked db/finally.db; app.services publishes exactly what the phase's five modules define"
    verification:
      - kind: other
        ref: "git status --porcelain -- db/finally.db (no output after full suite)"
        status: pass
      - kind: other
        ref: "uv run --extra dev python -c \"import app.services as s; ...\" -> 19 True True"
        status: pass
    human_judgment: false

duration: 34min
completed: 2026-08-13
status: complete
---

# Phase 3 Plan 05: Background Snapshot Task & Phase Reconciliation Summary

**A lifespan-owned `snapshot-loop` asyncio task records portfolio value every 30 seconds inside one `BEGIN IMMEDIATE`, skipping the write when the cents-rounded total is unchanged — and the phase's services package now publishes the 19 names its five modules actually define.**

## Performance

- **Duration:** ~34 min
- **Tasks:** 4
- **Files modified:** 6 (2 created, 4 modified)
- **Suite at completion:** 351 passed, 0 failed

## Accomplishments

- `backend/app/services/snapshots.py` — `SNAPSHOT_INTERVAL_SECONDS = 30.0`, `snapshot_loop`, the separately callable `record_snapshot`, and the single `_record_if_changed` transaction. The whole read-compare-write sits in one `writing(conn)` block, so `BEGIN IMMEDIATE` takes the write lock before the cash and position reads and the recorder can never pair a pre-trade cash balance with a post-trade position.
- The unchanged-value skip is `round_money(total) != round_money(latest["total_value"])` and nothing else (D-16). `round_money` appears on exactly one line — the comparison — and `insert_snapshot` receives the raw float, as `money.py` requires.
- `main.py`'s lifespan now owns two background tasks. `snapshot-loop` is created beside `source.start()` and cancelled before `source.stop()` (D-17), using the cancel block copied verbatim from `SimulatorDataSource.stop`. No `include_router` call was added or moved; `app.frontend(...)` is still the last statement before `return app`.
- The Phase 1 conftest `app` fixture now sets `application.state.db_path = db_path`, closing the hole a lifespan-owned writer would otherwise open onto the git-tracked `db/finally.db`. The loop's sleep-first ordering is the second, independent mitigation.
- Phase 1's deferred snapshot-versus-`execute_trade` collision test now exists, and both real callers finally drive it.
- `app/services/__init__.py` reconciled in one pass against the code on disk: 19 exports, alphabetically sorted, every one resolving, no private symbol.

## Task Commits

1. **Task 1: The snapshot recorder** — `9186ba7` (feat)
2. **Task 2: Test app fixture state guard** — `ba15341` (test)
3. **Task 3: Lifespan snapshot task** — `3ac65a8` (feat)
4. **Task 4: Services package surface reconcile** — `436bfb5` (docs)

## Files Created/Modified

- `backend/app/services/snapshots.py` — created. The interval constant, the loop, the loop body and the one transaction.
- `backend/tests/services/test_snapshots.py` — created. 11 tests across `TestRecordSnapshot` (8), `TestSnapshotLoop` (2) and `TestTradeCollision` (1).
- `backend/app/main.py` — lifespan only: `import asyncio`, `from app.services.snapshots import snapshot_loop`, the named task, the cancel block, an extended docstring.
- `backend/app/services/__init__.py` — rewritten: `Public API:` docstring block, five grouped imports, 19-name `__all__`.
- `backend/tests/conftest.py` — one line plus a rationale paragraph in the `app` fixture docstring.
- `backend/tests/test_main.py` — two `snapshot-loop` assertions added to the existing lifespan test, plus one new app-level sleep-first test.

## Decisions Made

- **The half-cent adjacency case is driven by a fractional holding, not a cash write.** `update_cash_balance` rounds to cents at the write boundary, so a sub-cent difference cannot be expressed through it at all. The test holds 0.0001 shares at $20.00 (a $0.002 total move, skipped) and then 0.0005 shares (a $0.01 move, written). This is a test-construction consequence of Phase 1's rounding rule, and it is recorded because the obvious alternative silently proves nothing.
- **The collision test uses a constant fill price.** Buying one share at $100 leaves the portfolio worth exactly `STARTING_CASH` after every round: the cash leaving and the position arriving cancel. Any snapshot taken between the two halves of a trade would therefore land one fill away from that value, so `{round_money(total) for every row} == {STARTING_CASH}` is a sharp assertion that does not depend on the interleaving actually occurring. The seed snapshot row is deleted first so the first `record_snapshot` genuinely writes rather than skipping.
- **`PRICE_WAIT_SECONDS` and `VALID_SIDES` are not exported.** Both are public module-level constants in `trading.py`, and the plan's enumerated export set (which the acceptance criteria pin at 19) omits them. They are internal tunables of the trade path rather than a seam any caller needs, so they stay module-local. Recorded because the package docstring rule ("re-export every submodule's public surface") could otherwise read as a miss.

## Deviations from Plan

None — plan executed exactly as written. Every name the plan predicted for `__all__` matched what the wave-2 modules actually define, so the reconcile-against-the-code rule produced no correction.

## Issues Encountered

- **`uv` under OneDrive.** As flagged in the execution brief, every `uv` invocation needed `UV_LINK_MODE=copy` to avoid `os error 396` (incompatible hardlinks on a cloud-backed path). No workaround was added to the repository — this is an environment prefix only.
- **The known Windows timer flake.** `tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval` failed on one of the three full-suite runs (the Task 2 gate) and passed on the other two, including the final one. It is owned by the frozen market module and documented as tolerated (Phase 1 D-24); it was not investigated.
- **`tests/db/test_concurrency.py::TestMixedWrites::test_snapshots_and_trades_written_concurrently` did not regress.** It passed on all three full-suite runs. The conftest guard means the new background writer never reaches a tracked database, and the loop's 30-second first sleep means it never runs during the suite at all.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **PORT-12 is closed**, which completes Phase 3's requirement set. Phase 5's P&L chart now has a source of points that accumulate without user action.
- **`app.services` is the stable surface Phase 6 plans against.** `execute_trade`, `watchlist.add` and `watchlist.remove` are unchanged and match `03-SEAM-CONTRACT.md` exactly.
- **One open question, deliberately accepted rather than mitigated (T-03-55):** `portfolio_snapshots` grows unbounded on a long-running container — a held portfolio under GBM writes a row every 30 seconds, roughly 2880 rows a day. Reads are bounded by `03-03`'s `?limit=` cap of 5000, so this degrades storage rather than any response. Recorded so a future retention decision inherits an open question rather than a silent assumption.
- **Phase-wide gate:** `uv run --extra dev pytest -q` → 351 passed, 0 failed. `uv run --extra dev ruff check app/ tests/` → clean. `git status --porcelain -- db/finally.db` → no output. Every frozen path (`backend/app/db/`, `backend/app/market/`, `backend/app/api/`, `pyproject.toml`, `uv.lock`, the three wave-2 service modules) is untouched.

## Self-Check: PASSED

- `backend/app/services/snapshots.py` — FOUND
- `backend/tests/services/test_snapshots.py` — FOUND
- `backend/app/services/__init__.py` — FOUND (modified)
- `backend/app/main.py` — FOUND (modified)
- `backend/tests/conftest.py` — FOUND (modified)
- `backend/tests/test_main.py` — FOUND (modified)
- Commits `9186ba7`, `ba15341`, `3ac65a8`, `436bfb5` — all present in `git log`

---
*Phase: 03-portfolio-watchlist-apis*
*Completed: 2026-08-13*
