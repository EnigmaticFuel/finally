# Phase 02 - Deferred Items

Out-of-scope discoveries logged during execution. These are NOT fixed by this
phase because they were not caused by it. See the scope boundary rule: only
issues directly caused by the current task's changes are auto-fixed.

## 1. `test_custom_update_interval` is timing-marginal on Windows

- **Found during:** plan 02-02, Task 3 (backend regression gate)
- **Test:** `backend/tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval`
- **Observed:** `1 failed, 242 passed` on two consecutive full-suite runs.
  The same test passes in isolation (`1 passed in 0.22s`).
- **Not caused by this phase:** `git status --porcelain backend/` is empty and
  `git diff --stat` across this plan's commits shows only `scripts/`. The
  backend tree is byte-identical to the one plan 02-01 ran against, where the
  suite reported 243 passed.
- **Root cause:** the test starts the simulator at `update_interval=0.01`,
  sleeps `0.05`s, and asserts `cache.version > initial_version + 2` - at least
  three ticks inside a 50 ms window. Windows' default asyncio timer granularity
  is approximately 15.6 ms, so the window affords roughly 3.2 ticks against an
  assertion that needs 3. The margin is thin enough that ordinary event-loop
  load from the preceding 240 tests pushes it under.
- **Owner:** the market subsystem, not this phase. CONTEXT.md freezes Phase 1
  code for Phase 2 ("no decision here edits Phase 1 code"), so this phase must
  not touch it.
- **Suggested fix when it is picked up:** widen the sleep or assert on elapsed
  time rather than tick count, so the assertion does not encode a platform's
  timer resolution.
