---
phase: 03-portfolio-watchlist-apis
plan: 06
subsystem: api
tags: [fastapi, sqlite, market-data, lifespan, pytest, tdd]

requires:
  - phase: 03-portfolio-watchlist-apis
    provides: execute_trade seam, watchlist add/remove seams, the assembled FastAPI app and its lifespan
  - phase: 02-market-data-session-baseline
    provides: MarketDataSource, SimulatorDataSource, PriceCache, wait_for_price
provides:
  - execute_trade(db_path, cache, source, ticker, side, quantity) - the amended cross-phase seam
  - startup_tickers(db_path) - the persisted watchlist the feed is started from on every boot
  - create_portfolio_router(price_cache, source) - the router factory now holding the feed
  - tests/test_feed_reconciliation.py - production-shaped proofs driving the real lifespan and real simulator
affects: [06-chat-llm, 04-frontend-shell, phase-03-verification]

actuals:
  tokens: 20402
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Both writers that can introduce a symbol (execute_trade, watchlist.add) hold the feed they register it with"
    - "Registration sits between cheap validation and the price wait, never before validation"
    - "The market feed is started from persisted state, not from a parallel constant"
    - "A test that hand-writes the price cannot prove a registration behavior - production-shaped tests drive the real lifespan"

key-files:
  created:
    - backend/tests/test_feed_reconciliation.py
  modified:
    - backend/app/services/trading.py
    - backend/app/services/watchlist.py
    - backend/app/services/__init__.py
    - backend/app/api/portfolio.py
    - backend/app/api/__init__.py
    - backend/app/main.py
    - backend/tests/services/test_trading.py
    - backend/tests/services/test_watchlist.py
    - backend/tests/services/test_snapshots.py
    - backend/tests/test_main.py

key-decisions:
  - "execute_trade gained source in third position, exactly as 03-SEAM-CONTRACT.md's Amendment specifies - no variant, no keyword-only marker"
  - "Registration is deliberately not rolled back when the transaction rejects the trade; the next boot repairs the orphan because the feed now starts from the watchlist rows"
  - "The emptied-watchlist fallback feeds the simulator but writes no rows, so a deliberately emptied watchlist stays empty"
  - "The cache-pre-seeding fixture was renamed priced_cache and its docstring forbids its use for the auto-add claim"

patterns-established:
  - "Production-shaped proof: real lifespan via TestClient context manager, real SimulatorDataSource, zero hand-written prices"
  - "A restart is a second create_app() against the same db_path; ensure_initialized memoizes per path so the database is reused, not re-seeded"

requirements-completed: [PORT-01, PORT-07, PORT-08, WATCH-01, WATCH-03, TEST-02]

coverage:
  - id: D1
    description: "Trading a ticker the market data source has never been told about fills at a real server-side price and joins the watchlist"
    requirement: "PORT-07"
    verification:
      - kind: integration
        ref: "backend/tests/test_feed_reconciliation.py#test_trading_an_unregistered_ticker_fills_and_joins_the_watchlist"
        status: pass
      - kind: unit
        ref: "backend/tests/services/test_trading.py#test_buy_fills_and_lands_everywhere"
        status: pass
    human_judgment: false
  - id: D2
    description: "The traded symbol is registered with the feed after cheap validation and before the two-second price wait, so a malformed quantity reaches neither"
    requirement: "PORT-08"
    verification:
      - kind: unit
        ref: "backend/tests/services/test_trading.py#test_a_bad_quantity_is_reported_before_the_price_wait"
        status: pass
      - kind: unit
        ref: "backend/tests/services/test_trading.py#test_a_ticker_that_never_prices_raises_after_the_wait"
        status: pass
    human_judgment: false
  - id: D3
    description: "A ticker the user added in an earlier run still prices after a restart: it values, it sells, and once closed it removes"
    requirement: "PORT-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_feed_reconciliation.py#test_a_user_added_ticker_still_prices_after_a_restart"
        status: pass
    human_judgment: false
  - id: D4
    description: "startup_tickers reads the persisted watchlist through the frozen query layer and writes nothing; an emptied watchlist stays empty"
    requirement: "WATCH-01"
    verification:
      - kind: unit
        ref: "backend/tests/services/test_watchlist.py#TestStartupTickers"
        status: pass
      - kind: integration
        ref: "backend/tests/test_main.py#test_lifespan_starts_and_stops_source"
        status: pass
    human_judgment: false
  - id: D5
    description: "execute_trade's signature matches the amended contract at every call site in app/ and tests/"
    requirement: "WATCH-03"
    verification:
      - kind: other
        ref: "uv run --extra dev python -c \"import inspect; from app.services.trading import execute_trade; print(list(inspect.signature(execute_trade).parameters))\" -> ['db_path', 'cache', 'source', 'ticker', 'side', 'quantity']"
        status: pass
      - kind: unit
        ref: "backend/tests/ (full suite) - 357 passed"
        status: pass
    human_judgment: false
  - id: D6
    description: "No test asserting the auto-add-on-trade path hand-writes a price into the cache"
    requirement: "TEST-02"
    verification:
      - kind: other
        ref: "grep -c '\\.update(' backend/tests/test_feed_reconciliation.py -> 0"
        status: pass
    human_judgment: false

duration: 34min
completed: 2026-08-15
status: complete
---

# Phase 3 Plan 06: Feed Reconciliation Summary

**The market feed and the user's tickers now reconcile in both directions: a trade registers its symbol with the running feed before waiting on a price, and the lifespan starts the feed from the persisted watchlist instead of a hardcoded constant.**

## Performance

- **Duration:** 34 min
- **Tasks:** 3
- **Files modified:** 10 modified, 1 created

## Accomplishments

- **G-01 closed.** `execute_trade` gained `source: MarketDataSource` in third position and calls `await source.add_ticker(ticker)` between `validate_quantity` and `wait_for_price`. Trading a symbol the feed has never heard of now fills at a real server-side price and joins the watchlist — the behavior PORT-07 and ROADMAP SC2 name, previously unreachable through the assembled app because the two-second wait had no producer to wait on.
- **G-02 closed.** The lifespan starts the source from `await startup_tickers(app.state.db_path)`. A ticker the user added in an earlier run now prices after a restart, so its position values, is counted in `total_value`, sells with 200, and removes with 204 — instead of the stranded holding (null price, excluded from the total, unsellable 400, unremovable 409) that the planner measured.
- **The fixture that masked G-01 is demoted.** `backend/tests/services/test_trading.py`'s bare `cache` fixture is now `priced_cache`, and its docstring states what it must never again back. `test_buy_fills_and_lands_everywhere` no longer claims the unwatched-ticker requirement; it claims the atomicity it actually proves.
- **The PORT-07 and G-02 proofs are production-shaped.** `backend/tests/test_feed_reconciliation.py` drives the assembled app's real lifespan through `TestClient` as a context manager with the real `SimulatorDataSource`, and writes no price of its own — `grep -c '\.update(' ` over that file returns 0.
- **Two docstrings became true statements about the code.** `app/services/watchlist.py`'s `add` and `remove` both asserted the source is started from the watchlist rows on every boot. That was false when written; the behavior was fixed first, then the prose was corrected to name `startup_tickers` as the mechanism.
- **IN-01 closed.** `from __future__ import annotations` added to `app/services/__init__.py` and `app/api/__init__.py`, the only two package modules in the tree missing it.

## Task Commits

1. **Task 1 (tracer): Register the traded symbol with the feed** - `500b80b` (feat)
2. **Task 2 (TDD RED): Failing tests for booting the feed from the persisted watchlist** - `5dc84d0` (test)
3. **Task 2 (TDD GREEN): Start the feed from the persisted watchlist** - `3415907` (feat)
4. **Task 3: The future-annotations import and the regression gate** - `3aa5098` (style)

No REFACTOR commit — the GREEN implementation is two statements and needed no cleanup.

## Files Created/Modified

- `backend/app/services/trading.py` - `execute_trade` amended to the contract shape; one new `await source.add_ticker(ticker)` between validation and the price wait; module and function docstrings state registration's position and reason
- `backend/app/services/watchlist.py` - new `startup_tickers(db_path)` in a `# --- Startup ---` section; the two false docstrings in `add` and `remove` corrected
- `backend/app/services/__init__.py` - `startup_tickers` exported in all three places; future-annotations import added
- `backend/app/api/portfolio.py` - `create_portfolio_router(price_cache, source)`, source passed through to `execute_trade`
- `backend/app/api/__init__.py` - future-annotations import added
- `backend/app/main.py` - lifespan starts the source from `startup_tickers`; seed-constant import removed; portfolio router registration gained the source
- `backend/tests/test_feed_reconciliation.py` - **new**; the two production-shaped proofs
- `backend/tests/services/test_trading.py` - 30 call sites swept to the new signature; `cache` fixture renamed `priced_cache`; two ordering assertions added
- `backend/tests/services/test_watchlist.py` - `TestStartupTickers`, four behaviors
- `backend/tests/services/test_snapshots.py` - one call site swept
- `backend/tests/test_main.py` - lifespan assertion moved from seed order to ascending order; two docstrings corrected

## Decisions Made

- **Registration is not rolled back on a rejected trade.** `add_watchlist_ticker` inside `_apply_trade` still rolls back, so a refused trade leaves no watchlist row; the source keeps producing a price for the refused symbol. That is the same harmless condition D-08 already accepts for a removed ticker, and Task 2 makes it self-healing — the next boot starts the feed from the watchlist rows, so the orphan disappears. No compensating logic was added.
- **The recording fake stays the collaborator for arithmetic tests.** A real started `SimulatorDataSource` would overwrite `FILL_PRICE = 100.0` mid-assertion. The fake registers nothing into the cache, so every figure in `test_trading.py` holds exactly — which is precisely why a real source is the right collaborator in the new reconciliation module and the wrong one there.
- **The restart test introduces its ticker through `POST /api/watchlist`, not by trading it.** That route already registered its ticker before this plan, so the test discriminates the boot-from-watchlist gap alone and cannot pass or fail for the registration-on-trade reason.
- **No elapsed-duration assertions anywhere.** The simulator moves every 500ms and this repo already carries one timer-granularity flake on Windows.

## Deviations from Plan

### Deviations

**1. [Rule 3 - Blocking] `uv` hardlinking fails in the OneDrive-hosted worktree**

- **Found during:** Task 1 (first test run)
- **Issue:** `uv run` failed to create the worktree's `.venv`: `failed to hardlink file ... The cloud operation cannot be performed on a file with incompatible hardlinks. (os error 396)`. This is the OneDrive hazard already recorded as a standing accepted risk for this repo, surfacing at venv creation rather than at SQLite.
- **Fix:** Every command in this plan was run with `UV_LINK_MODE=copy` prefixed. No file in the repository was changed.
- **Verification:** All test and lint commands completed normally afterward.
- **Committed in:** N/A — environment-only, no repository change

**2. [Rule 1 - Wrong check] The plan's `__all__` ordering criterion uses the wrong sort key**

- **Found during:** Task 2
- **Issue:** The acceptance criterion `s.__all__ == sorted(s.__all__, key=str.lower)` prints `False`. It also printed `False` on the untouched baseline: `app/services/__init__.py` has always been ASCII-sorted (uppercase names first — `Conflict`, `NotFound`, `SNAPSHOT_INTERVAL_SECONDS`, ... then `add`, `execute_trade`, ...), which is the isort convention the file follows. A case-insensitive sort would put `add` before `Conflict`. The criterion described a convention the file has never used.
- **Fix:** `startup_tickers` was inserted between `snapshot_loop` and `validate_quantity` exactly as the plan's prose instructed, preserving the file's real convention. Verified with the correct key: `s.__all__ == sorted(s.__all__)` prints `True`. The plan's criterion was not "satisfied" by reordering the whole list, which would have been a cosmetic churn contradicting the file's existing style.
- **Files modified:** `backend/app/services/__init__.py`
- **Verification:** `python -c "import app.services as s; print(s.__all__ == sorted(s.__all__))"` -> `True`
- **Committed in:** `3415907`

**3. [Rule 1 - Conflicting criteria] `startup_tickers` appears three times in `main.py`, not twice**

- **Found during:** Task 2
- **Issue:** One acceptance criterion required `startup_tickers` to appear in `main.py` exactly twice (import, lifespan call). Another instruction in the same task required the lifespan docstring to name `startup_tickers` as the mechanism the tickers are read through. The two cannot both hold.
- **Fix:** The docstring instruction was followed — it is the substantive one, and naming the mechanism is what makes the docstring checkable. The count is 3: import (line 19), docstring (line 44), lifespan call (line 55). Both load-bearing occurrences the criterion cared about are present.
- **Files modified:** `backend/app/main.py`
- **Verification:** Manual inspection; both required occurrences confirmed present
- **Committed in:** `3415907`

---

**Total deviations:** 3 (1 blocking environment workaround, 2 mis-specified acceptance criteria)
**Impact on plan:** None on behavior. Every behavioral requirement in the plan was implemented as written. The two criterion deviations are documentation defects in the plan, not code changes; both are recorded here so the verifier does not re-derive them.

## Issues Encountered

- **The `.venv` did not exist in the worktree** and had to be created by the first `uv run`, which is what surfaced the OneDrive hardlink failure above. Resolved with `UV_LINK_MODE=copy`.

## Verification Evidence

- `uv run --extra dev pytest -q` -> **357 passed**, 0 failed (baseline was 351; none reduced). The known `test_custom_update_interval` Windows timer flake passed on this run, so no tolerated failure was exercised.
- `uv run --extra dev ruff check app/ tests/` -> All checks passed
- `inspect.signature(execute_trade)` -> `['db_path', 'cache', 'source', 'ticker', 'side', 'quantity']` — matches `03-SEAM-CONTRACT.md`'s Amendment verbatim
- `grep -c "\.update(" backend/tests/test_feed_reconciliation.py` -> `0`
- `grep -c "execute_trade(" backend/tests/services/test_trading.py` -> `30`
- `grep -c "def priced_cache" backend/tests/services/test_trading.py` -> `1`; `grep -c "def cache"` -> `0`
- `grep -c "from app.db.seed import" backend/app/main.py` -> `0`; no `INSERT INTO` / `DELETE FROM` / `UPDATE ` in `main.py`
- `git diff --name-only cc6c900 HEAD` lists **no path** under `backend/app/market/` or `backend/app/db/` — both frozen modules untouched
- `git status --porcelain db/finally.db` -> empty; the suite wrote nothing to the tracked database
- No change to `backend/app/services/portfolio.py`, `backend/app/api/models.py`, `backend/app/api/errors.py`, `backend/tests/api/test_portfolio.py`, `backend/pyproject.toml` or `backend/uv.lock` — those belong to plans 03-08 and 03-09

## Known Stubs

None. No placeholder values, no skipped tests, no unrun `<verify>` blocks.

## Threat Flags

None. The plan's `<threat_model>` covers every surface this plan touched (T-03-56 through T-03-59); no new endpoint, auth path, file access pattern or schema change was introduced beyond those already registered.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The amended `execute_trade` signature is final and matches `03-SEAM-CONTRACT.md`. Phase 6's LLM path can be planned and built against it directly.
- The feed-to-watchlist reconciliation now holds in both directions, so the phase goal — "the user's positions and watched tickers are real and live-valued" — is reachable through the assembled app rather than only through fixtures.
- No blockers. The `UV_LINK_MODE=copy` workaround is environmental and applies to any agent running in a OneDrive-hosted worktree.

## Self-Check: PASSED

- Files claimed created/modified: all present on disk
- Commits claimed: `500b80b`, `5dc84d0`, `3415907`, `3aa5098` all present in `git log`
- Working tree clean apart from `.claude/settings.local.json`, which was already modified before this plan started and is not this plan's to commit

---
*Phase: 03-portfolio-watchlist-apis*
*Completed: 2026-08-15*
