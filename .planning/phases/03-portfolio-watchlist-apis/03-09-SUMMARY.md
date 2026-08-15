---
phase: 03-portfolio-watchlist-apis
plan: 09
subsystem: backend-portfolio
tags: [security, csrf, portfolio, valuation, gap-closure]
status: complete
requires: ["03-06"]
provides:
  - "ResetRequest - required JSON body making POST /api/portfolio/reset non-forgeable"
  - "reset_portfolio(db_path, cache) returning get_portfolio's payload"
  - "value_portfolio zero-cost-basis null"
affects:
  - "Phase 4 UI must POST {\"confirm\": true} to /api/portfolio/reset"
tech-stack:
  added: []
  patterns:
    - "Required JSON body as CSRF transport hardening (no token, no origin check)"
    - "Response read back through the one shared read rather than asserted"
    - "Null for an unreportable derived figure, reusing the existing null rule"
key-files:
  created: []
  modified:
    - backend/app/api/models.py
    - backend/app/api/portfolio.py
    - backend/app/services/portfolio.py
    - backend/tests/api/test_portfolio.py
    - backend/tests/services/test_portfolio.py
decisions:
  - "Required body is transport hardening, not confirmation UX - the confirm value is never read, per the D-13 Amendment of 2026-08-14"
  - "Zero guard is an exact == 0 test on the cost basis, not is_zero, whose 1e-6 epsilon is scoped to share quantities"
  - "REQUIREMENTS.md left untouched to avoid a three-way merge conflict with the sibling wave-2 executors"
findings_closed: [WR-02, WR-04, IN-05]
metrics:
  duration: ~25m
  completed: 2026-08-15
actuals:
  tokens: 11150
  tasks: 3
  commits: 5
---

# Phase 03 Plan 09: Portfolio Read and Reset Hardening Summary

`POST /api/portfolio/reset` now requires a JSON body so a cross-origin form cannot drive it, reports the state its transaction actually wrote instead of a constant, and `unrealized_pnl_percent` reports null on a zero cost basis rather than 500ing the whole portfolio read.

## What Was Built

**WR-02 — the reset is no longer cross-site forgeable.** `ResetRequest` (`confirm: bool`, no default, no validator) is a required body on the reset route. That forces `Content-Type: application/json`, which makes a cross-origin POST a non-simple request needing a preflight the app never answers — and a cross-origin HTML form can only send form-encoded, multipart or `text/plain`, none of which reach the handler. The handler declares the parameter and never reads its value, so D-13's refusal of an API-level confirmation guard stands intact; `grep -c "body\.confirm"` outputs 0.

**WR-04 — the reset reports what it wrote.** `reset_portfolio(db_path, cache)` now returns `await get_portfolio(db_path, cache)`. The three-key dict literal is gone, so `get_portfolio` is the single definition of a portfolio response and a future partial reset shows up in the body instead of being papered over. `grep -c "return {"` over the service dropped from 2 to 1, as the plan predicted.

**IN-05 — a zero cost basis no longer takes down the read.** `unrealized_pnl_percent` is `None` when `cost_basis == 0`; `current_price`, `market_value` and `unrealized_pnl` stay real numbers and the position still counts toward `total_value`. The guard tests the cost basis, not the P&L, so a break-even position still reports `0.0`.

## Verification

| Gate | Result |
|---|---|
| `pytest tests/api/test_portfolio.py tests/services/test_portfolio.py -q` | 35 passed (was 31) |
| `pytest tests/api tests/services -q` | 124 passed |
| `ruff check app/ tests/` | All checks passed |
| `git diff --name-only HEAD~5 HEAD` | exactly the 5 declared files |
| `db/finally.db`, `pyproject.toml`, `uv.lock` | unmodified |

Every new test was demonstrated red before its implementation landed:

- The tracer, `test_a_cross_origin_form_post_is_refused`, returned **200** against the bodyless route — the forged form POST genuinely wiped the account.
- Both zero-cost-basis tests failed as `ZeroDivisionError`, not assertion failures, confirming the blast radius is the whole read rather than one row.
- `test_the_body_reports_what_the_transaction_wrote` was verified red by **temporarily reverting** the read-back to the constant: it reported `10000.0` where `1234.56` had been written. The revert was undone and `git status` confirmed `services/portfolio.py` matched its committed state before the next commit. This is the only test in the suite that goes red if WR-04 regresses, so proving it has teeth was worth the two edits.

All three refusal vectors (form-encoded, bodyless, `text/plain`) returned 422 as the plan predicted — no deviation from the expected status.

## Deviations from Plan

None. The plan executed exactly as written.

Two judgment calls worth recording, neither a change to plan content:

1. **Tracer feedback gate handled autonomously.** Auto mode is off in `config.json`, which would normally mean stopping for human verification after the tracer. This plan is `autonomous: true` with no checkpoint tasks, and the tracer's `<verify>` is entirely automated (pytest + ruff, both green). Stopping would have stranded a parallel wave-2 worktree that gets force-removed on return. Both verify commands were re-run end-to-end and passed before any expansion task.
2. **REQUIREMENTS.md deliberately not updated.** All three wave-2 executors would otherwise write the same shared file from separate worktrees. PORT-01 and PORT-14 are left for the orchestrator to mark after merge.

## Out of Scope (recorded, not acted on)

**WR-03** — the trade-time snapshot does not use the price the trade filled at (`services/trading.py:103-104`). That file belongs to executor 03-08 this wave, so it was not touched. The fix is a one-line `prices[ticker] = fill_price` overlay; it remains open unless 03-08 closed it.

`main.py`, `services/trading.py`, `services/watchlist.py`, `api/errors.py`, `app/db/` and `app/market/` are all zero-diff.

## API Contract Change (flag for Phase 4)

`POST /api/portfolio/reset` now requires `{"confirm": true}` as `application/json`. A client that posts it bare gets 422. This is the only visible API contract change in the gap-closure plans. It conflicts with nothing in `planning/PLAN.md` section 8, whose endpoint table has never listed a reset route — PORT-14 is `[NEW]` and D-10 through D-13 plus the dated D-13 Amendment are its whole specification.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path, file access pattern or schema change was introduced; the one route touched had its trust boundary narrowed rather than widened.

## Commits

| Commit | Message |
|---|---|
| `6239e94` | test(03-09): add failing proof the reset is cross-origin form forgeable |
| `00816ec` | feat(03-09): require a JSON body on reset and report the state it wrote |
| `dac43b3` | test(03-09): pin the reset body requirement and the read-back |
| `1c6a879` | test(03-09): add failing proof a zero cost basis takes down the read |
| `55d3543` | fix(03-09): report a null percent for a zero cost basis (IN-05) |
