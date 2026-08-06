---
status: testing
phase: 01-foundation-spine
source: [01-VERIFICATION.md]
started: 2026-08-06T20:15:00Z
updated: 2026-08-06T20:15:00Z
---

## Current Test

number: 1
name: Interrupted `uv sync` recovery invariant
expected: |
  The plain re-run does not repair the venv; the delete-and-resync yields a complete
  environment where litellm, pydantic, dotenv, httpx and fastapi all import.
awaiting: user response

## Tests

### 1. Interrupted `uv sync` recovery invariant
expected: Interrupt a `uv sync --frozen --extra dev`, re-run it plainly, then delete `backend/.venv` and re-sync with `UV_LINK_MODE=copy`. The plain re-run does not repair the venv; the delete-and-resync yields a complete environment where litellm, pydantic, dotenv, httpx and fastapi all import.
result: [pending]

### 2. Static-route versus API concurrency
expected: Issue concurrent requests to `/` and `/api/health` against the running app. Static HTML and the four-key health JSON both return intact; neither blocks nor corrupts the other.
result: [pending]

### 3. Disposition on the two flagged test-tier prohibitions
expected: A decision on (a) adding a guard that the `trades` table stays append-only, and (b) whether the `db/finally.db` rewrite gate needs a committed script rather than a one-time procedure. Both are correct in current state but have no automated guard.
result: [pending]

### 4. Acceptance of the two judgment-tier prohibitions
expected: Human accepts the LLM-judge verdicts on CORE-08 (health endpoint never reports healthy while the feed is dead) and SETUP-06 (a genuine regression is never dismissed as the known flake), or requests changes.
result: [pending]

### 5. Correct the flake node ID across planning artifacts
expected: `01-CONTEXT.md` D-24 and `01-VALIDATION.md` name `tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval` instead of the zero-collecting `tests/market/test_simulator.py::test_custom_update_interval`.
result: [pending]

### 6. Refresh 01-VALIDATION.md tracking state
expected: Frontmatter leaves `status: draft` / `nyquist_compliant: false` / `wave_0_complete: false`, and the Per-Task Verification Map stops showing every row as `❌ W0` / `⬜ pending`, now that all eleven referenced test files exist and pass.
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
