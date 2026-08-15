---
phase: 03-portfolio-watchlist-apis
plan: 07
subsystem: api
tags: [fastapi, asyncio, lifespan, teardown, logging, pytest]

# Dependency graph
requires:
  - phase: 03-05
    provides: the lifespan-owned snapshot task and its cancel-then-stop teardown
  - phase: 03-06
    provides: startup_tickers, which the lifespan now boots the feed from
provides:
  - Exception-safe lifespan teardown - cancel, gather, stop the source, all from one finally block
  - _log_if_failed done-callback reporting a dead snapshot recorder at error level when it dies
  - Regression tests for the failure-path teardown and its quiet-shutdown control
affects: [docker, e2e-tests, chat, frontend-shell]

actuals:
  tokens: 3400
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Background-task reclaim runs from a finally block, so teardown completes on every exit path"
    - "asyncio.gather(task, return_exceptions=True) to reclaim a task without re-raising, paired with a done-callback that already reported the failure"
    - "add_done_callback reporting, so a background failure surfaces when it happens rather than at shutdown"

key-files:
  created: []
  modified:
    - backend/app/main.py
    - backend/tests/test_main.py

key-decisions:
  - "Reclaim with asyncio.gather(..., return_exceptions=True) rather than a try/except around await task: it returns the cancellation or the stored failure as a value, so control always reaches await source.stop()"
  - "The failure is reported by a done-callback at the moment the task dies, not at shutdown - that is when an operator can still act on it"
  - "task.cancelled() is tested before task.exception() because exception() re-raises on a cancelled task; that ordering is what keeps an ordinary shutdown silent"
  - "source.stop() is called unconditionally from finally, which is contract-honoring rather than defensive: MarketDataSource.stop() is documented idempotent"
  - "A source.stop() that itself raises is deliberately not defended - it is the last statement of teardown with nothing left to reclaim behind it"
  - "The ERROR assertions filter caplog.records by record.name == 'app.main' rather than reading the list whole, so an unrelated record from the simulator or the database cannot fail a test that is not about it"

patterns-established:
  - "Fix the behavior, then the docstring: the lifespan docstring correction was a separate task ordered after the fix, never before"
  - "Gap-closure tests are written red first and the red output is recorded, so a test that was green before the fix cannot pass as proof"

requirements-completed: [PORT-12]

coverage:
  - id: D1
    description: "A snapshot task that died of a non-CancelledError exception no longer blocks teardown: source.stop() runs, no simulator-loop survives the lifespan, and leaving the context raises nothing"
    requirement: PORT-12
    verification:
      - kind: integration
        ref: "backend/tests/test_main.py#test_lifespan_stops_the_source_when_the_snapshot_task_died"
        status: pass
    human_judgment: false
  - id: D2
    description: "A dead recorder is reported at error level with the real exception text, emitted the instant the task fails rather than at shutdown"
    requirement: PORT-12
    verification:
      - kind: integration
        ref: "backend/tests/test_main.py#test_lifespan_stops_the_source_when_the_snapshot_task_died"
        status: pass
    human_judgment: false
  - id: D3
    description: "An ordinary shutdown stays silent - a cancelled task is not a failed one - so the new error report means something when it appears"
    requirement: PORT-12
    verification:
      - kind: integration
        ref: "backend/tests/test_main.py#test_a_clean_shutdown_logs_no_snapshot_failure"
        status: pass
    human_judgment: false
  - id: D4
    description: "Teardown ordering preserved (D-17): the snapshot task is reclaimed before the source is stopped, and the static mount stays last so the API is not shadowed"
    verification:
      - kind: integration
        ref: "backend/tests/test_main.py#test_lifespan_starts_and_stops_source"
        status: pass
      - kind: e2e
        ref: "backend/tests/test_main.py#test_api_not_shadowed"
        status: pass
    human_judgment: false
  - id: D5
    description: "The lifespan docstring's 'nothing outlives the app' guarantee is a true statement about the code beneath it, and names the finally block as the mechanism"
    verification: []
    human_judgment: true
    rationale: "Whether prose accurately describes the code it sits above is a reading judgment, not something a test can assert"

# Metrics
duration: 14min
completed: 2026-08-15
status: complete
---

# Phase 03 Plan 07: Exception-Safe Lifespan Teardown Summary

**A snapshot recorder that dies can no longer strand the market source: the reclaim sequence runs from a `finally` block, and a `_log_if_failed` done-callback reports the death at error level the moment it happens.**

## Performance

- **Duration:** 14 min
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Closed G-03 / CR-03: `task.cancel()` was a no-op on an already-failed task, `await task` re-raised the stored exception straight past the `except asyncio.CancelledError`, and `await source.stop()` never executed — the market source and its `simulator-loop` outlived the app that owned it.
- Teardown now runs from a single `finally` block: `task.cancel()`, `await asyncio.gather(task, return_exceptions=True)`, `await source.stop()`. D-17's ordering is unchanged — the recorder is reclaimed before its price producer goes away.
- The failure got **louder, not quieter**: `_log_if_failed`, wired with `add_done_callback`, logs `"Snapshot loop stopped: %s"` at error level the instant the task finishes — seconds or hours before shutdown, which is when an operator can still act. Previously the death had no channel at all: no request failed, no status code changed, and the P&L chart simply flatlined, which reads as an idle portfolio rather than a broken writer.
- `backend/app/services/snapshots.py` is byte-identical. PORT-12's raise-don't-swallow behavior inside the loop is untouched; no retry, no tolerance band, no log-level downgrade, and no broad catch anywhere on the teardown path.

## Task Commits

1. **Task 1: Teardown that completes whatever killed the recorder (tracer, TDD)** — `b9dcaca` (fix)
2. **Task 2: Make the lifespan docstring true** — `899fdb9` (docs)

### RED-before-GREEN, recorded verbatim

Required by the plan's verification block. Before any edit to `backend/app/main.py`:

```
app\main.py:60: in lifespan
    await task
app\services\snapshots.py:98: in snapshot_loop
    if await record_snapshot(db_path, cache):
>       raise RuntimeError(SNAPSHOT_FAILURE)
E       RuntimeError: snapshot recorder failed

FAILED tests/test_main.py::test_lifespan_stops_the_source_when_the_snapshot_task_died
1 failed in 2.95s
```

The `RuntimeError` escaped the lifespan context manager at `main.py:60` before a single assertion was reached — exactly the failure shape the plan predicted. After the fix, all 9 tests in the file pass.

## Files Created/Modified

- `backend/app/main.py` — `import logging`, module `logger`, the `_log_if_failed` done-callback, the `try`/`finally` teardown, and the corrected lifespan docstring
- `backend/tests/test_main.py` — `SNAPSHOT_FAILURE`, `_failing_record_snapshot`, `test_lifespan_stops_the_source_when_the_snapshot_task_died`, `test_a_clean_shutdown_logs_no_snapshot_failure`

## Decisions Made

- **`asyncio.gather(task, return_exceptions=True)` rather than a wider `try/except` around `await task`.** It returns the cancellation or the stored failure as a value instead of re-raising, so control always reaches `await source.stop()`. This is not a swallow: `_log_if_failed` already reported the failure the instant the task finished.
- **`task.cancelled()` is tested before `task.exception()`** — `exception()` re-raises on a cancelled task. That short-circuit is precisely what keeps every ordinary shutdown silent and is what the second test pins.
- **`source.stop()` is called unconditionally.** `MarketDataSource.stop()` is documented idempotent (`app/market/interface.py:37`), so an unconditional call from `finally` is contract-honoring rather than defensive. Making it conditional on how the task ended would be G-03 restated.
- **Test patches target `app.services.snapshots`, not `app.main`.** `main.py` imports only `snapshot_loop`, and the loop body resolves `record_snapshot` and `SNAPSHOT_INTERVAL_SECONDS` through its own module globals every iteration — so the *real* loop runs and really dies, rather than being replaced by a stand-in that never exercises the production arrangement.
- **Death-detection is by polling, not a fixed sleep.** The test polls `_running_task_names()` in 20ms steps up to ~2s and asserts no elapsed duration against any threshold. A sleep tuned to the 0.01s patched interval would be a second timing flake on this platform, and the phase already carries one it agreed not to chase.

## Deviations from Plan

None — plan executed exactly as written. No deviation rules fired.

## Issues Encountered

- **A `git commit` printed `error: failed to delete '.../worktrees/agent-a2cec2f87c340bda2': Permission denied`.** This is a stale-worktree prune attempt against a **sibling wave-2 agent's** metadata directory, blocked by a Windows/OneDrive file lock. It is not this plan's worktree and did not affect the commit, which landed normally (`899fdb9`, 1 file changed). Reported rather than reconciled, per the plan's instruction about sibling-owned changes.
- **The known timer flake behaved exactly as documented.** `tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval` passed on the first full-suite run (359 passed, 0 failed) and failed on the second (358 passed, 1 failed) with no intervening change other than a docstring edit — which cannot affect a simulator timer. It is owned by the frozen market module and was not chased.

## Verification Results

| Gate | Result |
|---|---|
| `uv run --extra dev pytest tests/test_main.py -q` | 9 passed |
| `uv run --extra dev pytest -q` (run 1) | **359 passed, 0 failed** |
| `uv run --extra dev pytest -q` (run 2) | 358 passed, 1 failed — known `test_custom_update_interval` timer flake only |
| `uv run --extra dev ruff check app/ tests/` | All checks passed |
| Frozen paths (`services/`, `db/`, `market/`, `api/`, `pyproject.toml`, `uv.lock`, `db/finally.db`) | No output — untouched |
| `git diff --name-only <base> HEAD` | `backend/app/main.py`, `backend/tests/test_main.py` only |

### Prohibition checks (all mechanically verified)

| Check | Required | Actual |
|---|---|---|
| `def _log_if_failed` | 1 | 1 |
| `task.add_done_callback(_log_if_failed)` | 1 | 1 |
| `asyncio.gather(task, return_exceptions=True)` | 1 | 1 |
| `^\s+finally:$` | 1 | 1 |
| `await source.stop()` | 1 | 1 (last statement of the `finally`) |
| `asyncio.create_task(` | 1 | 1 (one owner) |
| `task.cancel()` | 1 | 1 (one reclaim site) |
| `logger.error(` | 1 | 1 |
| `except Exception` | 0 | 0 |
| `sqlite3` | 0 | 0 |
| `logging.getLogger(__name__)` | 1 | 1 |
| `app.include_router(` | 4 | 4, with `app.frontend(` last before `return app` |

## Known Stubs

None. No placeholder values, no unwired data paths, no skipped tests introduced.

## Threat Flags

None. This plan adds no endpoint, no auth path, no file access and no schema change; it edits control flow inside one existing closure and adds one private module-level function.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- The lifespan now holds its "nothing outlives the app" guarantee on the failure path as well as the normal one, so the Docker phase can rely on a clean container shutdown and the E2E suite can restart the app between scenarios without leaking a `simulator-loop` per run.
- `_log_if_failed` gives the recorder a diagnostic channel it previously lacked. If the P&L chart ever flatlines in a demo, the error log now distinguishes a broken writer from an idle portfolio.
- Nothing is blocked. Siblings 03-08 and 03-09 executed concurrently in their own worktrees against disjoint file sets; this plan touched neither.

## Self-Check: PASSED

- `backend/app/main.py` — FOUND (modified)
- `backend/tests/test_main.py` — FOUND (modified)
- `.planning/phases/03-portfolio-watchlist-apis/03-07-SUMMARY.md` — FOUND
- Commit `b9dcaca` (Task 1) — FOUND
- Commit `899fdb9` (Task 2) — FOUND
- Commit `40c441e` (SUMMARY) — FOUND
- Working tree clean apart from `.claude/settings.local.json`, which was already modified before this plan started and is not owned by it

---
*Phase: 03-portfolio-watchlist-apis*
*Completed: 2026-08-15*
