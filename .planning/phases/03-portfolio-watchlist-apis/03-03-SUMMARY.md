---
phase: 03-portfolio-watchlist-apis
plan: 03
subsystem: api
tags: [fastapi, sqlite, pydantic, portfolio, snapshots, pytest]

# Dependency graph
requires:
  - phase: 01-foundation-spine
    provides: "queries.py (get_profile, get_positions, delete_position, update_cash_balance, insert_snapshot, get_snapshots), run_db/writing/connect, STARTING_CASH, conftest db_path and app fixtures"
  - phase: 03-portfolio-watchlist-apis
    provides: "03-01's value_portfolio pure rule, api/models.py response models, create_portfolio_router factory already registered in main.py, app-level exception handlers"
provides:
  - "GET /api/portfolio - cash, live-valued positions and total, with nulls for a priceless holding"
  - "GET /api/portfolio/history - snapshots newest first, bounded by ?limit= and filtered by ?since="
  - "POST /api/portfolio/reset - cash back to STARTING_CASH, positions cleared, one snapshot recording the step"
  - "get_portfolio / get_history / reset_portfolio service functions on the db_path-first seam convention"
affects: [04-frontend-shell, 05-charts, 06-chat]

actuals:
  tokens: 7325
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - "Read-only service functions take the connection first and deliberately skip writing(): a WAL reader already sees a consistent snapshot"
    - "A multi-statement destructive operation composes existing per-row query functions inside one writing() block rather than gaining a new bulk query"
    - "Query-parameter bounds declared with Annotated[int, Query(ge=, le=)] as transport validation (422), distinct from service-owned business rules (400)"

key-files:
  created:
    - backend/tests/services/test_portfolio.py
  modified:
    - backend/app/services/portfolio.py
    - backend/app/api/portfolio.py
    - backend/tests/api/test_portfolio.py

key-decisions:
  - "Reset is composed from get_positions + delete_position in a loop inside one writing() block - app/db/ stayed frozen and no bulk-delete query was added"
  - "reset_portfolio takes no cache argument: after the deletes nothing is held, so value_portfolio(STARTING_CASH, [], prices) is STARTING_CASH for any prices mapping, and an unused collaborator would misstate the dependency"
  - "recorded_at is returned byte-for-byte as stored and accepted back verbatim as ?since=; the service imports no datetime and parses nothing"
  - "The reset route's safety test asserts the cash balance after a GET rather than a 405, because the static fallback mounted at the root answers unmatched GETs"

patterns-established:
  - "Service seam convention held: db_path first, collaborators next, payload last, no FastAPI object crossing"
  - "The prices mapping is built on the async side from cache.get_all() and never read inside the executor thread"
  - "Derived figures (market_value, unrealized_pnl, total_value) are returned unrounded; no rounding helper appears in the service"

requirements-completed: [PORT-01, PORT-13, PORT-14]

coverage:
  - id: D1
    description: "GET /api/portfolio returns exactly cash_balance, total_value and positions, reporting the starting cash and an empty list on a fresh database"
    requirement: PORT-01
    verification:
      - kind: unit
        ref: "backend/tests/api/test_portfolio.py#TestReadPortfolio::test_a_fresh_database_is_cash_and_nothing_else"
        status: pass
      - kind: unit
        ref: "backend/tests/services/test_portfolio.py#TestGetPortfolio::test_a_fresh_database_is_cash_and_nothing_else"
        status: pass
    human_judgment: false
  - id: D2
    description: "A position is valued from the live cache; a position whose ticker has no price reports four nulls and contributes nothing to total_value, and a break-even position reports zeros rather than nulls"
    requirement: PORT-01
    verification:
      - kind: unit
        ref: "backend/tests/services/test_portfolio.py#TestValuePortfolio::test_a_priceless_position_is_null_and_excluded"
        status: pass
      - kind: unit
        ref: "backend/tests/services/test_portfolio.py#TestValuePortfolio::test_a_break_even_position_is_zero_not_null"
        status: pass
      - kind: unit
        ref: "backend/tests/api/test_portfolio.py#TestReadPortfolio::test_a_priced_position_reports_a_market_value"
        status: pass
    human_judgment: false
  - id: D3
    description: "Positions render ticker-ascending and every derived figure comes back at full float precision"
    requirement: PORT-01
    verification:
      - kind: unit
        ref: "backend/tests/services/test_portfolio.py#TestValuePortfolio::test_positions_come_back_ticker_ascending"
        status: pass
      - kind: unit
        ref: "backend/tests/services/test_portfolio.py#TestValuePortfolio::test_derived_figures_are_not_rounded"
        status: pass
    human_judgment: false
  - id: D4
    description: "GET /api/portfolio/history serves snapshots newest first, rejects limit=0 and limit above 5000 with 422, accepts the cap, and selects by an echoed-back recorded_at"
    requirement: PORT-13
    verification:
      - kind: unit
        ref: "backend/tests/api/test_portfolio.py#TestPortfolioHistory (6 tests: ordering, limit=1, limit=0 422, cap+1 422, cap 200, since round-trip)"
        status: pass
      - kind: unit
        ref: "backend/tests/services/test_portfolio.py#TestGetHistory::test_a_recorded_at_fed_back_as_since_selects_that_row_and_newer"
        status: pass
    human_judgment: false
  - id: D5
    description: "POST /api/portfolio/reset restores STARTING_CASH, clears every position, writes exactly one snapshot, and leaves the watchlist and the trades log untouched; a GET to the same path destroys nothing"
    requirement: PORT-14
    verification:
      - kind: unit
        ref: "backend/tests/services/test_portfolio.py#TestResetPortfolio (7 tests incl. watchlist survival, trades count, snapshot step, second reset, rollback)"
        status: pass
      - kind: unit
        ref: "backend/tests/api/test_portfolio.py#TestResetPortfolioRoute::test_a_get_does_not_reset_anything"
        status: pass
    human_judgment: false
  - id: D6
    description: "total_value and each position's unrealized_pnl drift with a live streaming ticker over several minutes rather than sticking"
    requirement: PORT-01
    verification: []
    human_judgment: true
    rationale: "03-VALIDATION.md's one manual-only row for PORT-01. Automated tests drive a fixed fake PriceCache, so drift over a genuinely moving GBM stream is only observable against a running container."
  - id: D7
    description: "The narrow reading of PORT-14's 'starting state' - portfolio only, watchlist and audit trail preserved - is the right one"
    requirement: PORT-14
    verification: []
    human_judgment: true
    rationale: "PORT-14 is [NEW] with no PLAN.md text; D-10 through D-13 are its entire specification and the edge probe could not classify it. A reviewer should confirm the portfolio-only reading against the alternative, full first-launch state."

# Metrics
duration: 19min
completed: 2026-08-13
status: complete
---

# Phase 3 Plan 03: Portfolio Read, History and Reset Summary

**The portfolio became readable and resettable: `GET /api/portfolio` values holdings live against the price cache with nulls for a priceless ticker, `GET /api/portfolio/history` serves snapshots bounded by `?limit=` and `?since=`, and `POST /api/portfolio/reset` clears positions and restores $10,000 in one transaction while leaving the watchlist and the audit log alone.**

## Performance

- **Duration:** 19 min
- **Started:** 2026-08-13T16:22:00Z
- **Completed:** 2026-08-13T16:41:00Z
- **Tasks:** 3
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments

- `get_portfolio` composes one WAL-consistent read of cash and positions with the prices mapping built on the async side, then hands both to 03-01's single `value_portfolio` rule rather than restating the arithmetic.
- `get_history` passes `limit` and `since` straight through to the existing `get_snapshots` query and returns `recorded_at` byte-for-byte, so a timestamp a client received round-trips as a filter unchanged. No composed wrapper function was needed, and none was written.
- `reset_portfolio` runs every position delete, the cash write and the snapshot inside one `BEGIN IMMEDIATE`, composed from existing query functions - `app/db/` stayed frozen and no bulk-delete query was added.
- Three routes joined 03-01's existing router factory with no signature change and no edit to `main.py`; the OpenAPI document now lists exactly `/api/portfolio`, `/api/portfolio/history`, `/api/portfolio/reset` and `/api/portfolio/trade`.
- 29 new tests (18 service, 11 route). The reset suite proves the blast radius directly: watchlist set identical before and after, trades row count identical, snapshot count up by exactly one, and a monkeypatched failure part-way through committing nothing.

## Task Commits

Each task was committed atomically. Tasks 1 and 2 were TDD, so each carries a RED test commit and a GREEN implementation commit:

1. **Task 1: Read the portfolio and its history through the service seam** - `f261d75` (test), `2428875` (feat)
2. **Task 2: Reset the portfolio in one transaction** - `5ef1d9d` (test), `bd44d0e` (feat)
3. **Task 3: Publish the three portfolio routes** - `e995ee2` (feat)

Both RED commits were verified failing before implementation (`ImportError: cannot import name 'get_history'`, then `'reset_portfolio'`).

## Files Created/Modified

- `backend/app/services/portfolio.py` - Added `_read_portfolio`, `get_portfolio`, `get_history`, `_apply_reset`, `reset_portfolio` alongside the untouched `value_portfolio`
- `backend/app/api/portfolio.py` - Added `HISTORY_DEFAULT_LIMIT`, `HISTORY_MAX_LIMIT`, `SINCE_DESCRIPTION` and the three route handlers `read_portfolio`, `read_history`, `reset`
- `backend/tests/services/test_portfolio.py` - New: `TestValuePortfolio`, `TestGetPortfolio`, `TestGetHistory`, `TestResetPortfolio` (18 tests)
- `backend/tests/api/test_portfolio.py` - Appended `TestReadPortfolio`, `TestPortfolioHistory`, `TestResetPortfolioRoute` (11 tests)

## Decisions Made

- **`STARTING_CASH` imported from the `app.db` package re-export** rather than `app.db.seed` directly, matching how the sibling `trading.py` imports every persistence symbol in one block. It resolves to the same `seed.py` constant, so the "never restate 10000.0" rule holds (`grep -c 10000` on the service is 0).
- **The `since` round-trip test asserts a prefix plus a `>= boundary` invariant** rather than an exact row count. `recorded_at` ties break by `rowid` in the SQL ordering, but a `>=` string filter would include every tied row, so an exact-length assertion would be flaky on a fast clock while the prefix assertion proves the same property.
- **A test-only counting helper takes a full SQL string** instead of interpolating a table name, so no dynamic SQL appears anywhere in the plan, not even in a test.
- **New service functions are imported from `app.services.portfolio` directly**, not through the package `__init__`, which 03-05 reconciles in one pass.

## Deviations from Plan

None - plan executed exactly as written. No deviation rule fired: no bugs surfaced, no missing critical functionality was found, and nothing blocked a task.

## Issues Encountered

- **Every `git commit` printed `error: failed to delete '.../worktrees/agent-a3cac8aca70d5c526': Permission denied` on stderr.** This is git's automatic worktree prune touching a *sibling* agent's live worktree (plan 03-02 or 03-04, running in parallel), not this one. Every commit succeeded and produced a hash; the message is noise from concurrent execution and needs no action.
- **`uv` required `UV_LINK_MODE=copy`** for every invocation, as the orchestrator's environment note specified. No workaround was added to the repo.
- **`.claude/settings.local.json` was already modified in the working tree when this agent started** and was deliberately left unstaged - it is not one of this plan's files.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 4's header, positions table, P&L chart and reset button have their three HTTP shapes, and `/docs` documents the `since` format the history route accepts.
- Phase 5's chart can page history through `?since=` against a stable timestamp contract.
- One manual verification remains open (D6): watching `total_value` and `unrealized_pnl` drift against a live container over several minutes. It cannot be automated because the test suite drives a fixed fake cache.
- 03-05 still owns the `app/services/__init__.py` reconciliation; the three new service functions are not yet in the package's public `__all__` by design.

## Self-Check: PASSED

All five claimed files exist on disk and all six claimed commits are present in the branch history
(`f261d75`, `2428875`, `5ef1d9d`, `bd44d0e`, `e995ee2`, `8390678`). `git diff --name-only` against
the plan's base lists exactly the four files in `files_modified`, and `db/finally.db` is unmodified.

---
*Phase: 03-portfolio-watchlist-apis*
*Completed: 2026-08-13*
