---
phase: 03-portfolio-watchlist-apis
verified: 2026-08-15T15:20:00Z
status: human_needed
score: 115/115 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 69/72
  gaps_closed:
    - "G-01 / PORT-07 - trading a ticker the market data source has never been told about now fills and joins the watchlist"
    - "G-02 - the lifespan starts the feed from the persisted watchlist, so a user-added ticker keeps its price across a restart"
    - "G-03 - the lifespan reclaims the market source from a finally block, so a dead snapshot task no longer blocks teardown"
  gaps_remaining: []
  regressions: []
  additionally_closed:
    - "WR-01 - no exception handler broader than the three-class service taxonomy; the pydantic-leak residual flagged by executor 03-08 is now closed at the REAL site (see P3a/P3b)"
    - "WR-02 - POST /api/portfolio/reset requires a JSON body and refuses form-encoded, bodyless and text/plain"
    - "WR-03 - the trade-time snapshot values the traded ticker at that trade's own fill_price"
    - "WR-04 - reset_portfolio reads its response back through get_portfolio instead of asserting a constant"
    - "IN-01..IN-05 - future annotations, stored-precision cash balance, sub-half-cent overdraft, fixed-decimal share counts, zero-cost-basis null percent"
gaps: []
deferred: []
findings:
  - id: W-01
    severity: warning
    statement: >
      REQUIREMENTS.md traceability for phase 3 is entirely unwritten, not partially
      unwritten. All 21 phase-3 requirement IDs (PORT-01..PORT-14, WATCH-01..WATCH-06,
      TEST-02) are still checkbox `[ ]` in the requirements list and `Pending` in the
      traceability table. `git log -- .planning/REQUIREMENTS.md` shows the file has not
      been touched since `57da869` (phase 2). No phase-3 requirement was ever marked and
      then lost to a merge; none was ever marked. The phase-1/phase-2 convention is
      `[x]` plus `Complete`.
    correct_state: >
      All 21 IDs are satisfied by the codebase (evidence per-ID in the Requirements
      Coverage table below) and should be `[x]` / `Complete`. This is a bookkeeping
      omission, not a code defect - it does not block the phase goal.
    action: "Orchestrator or a docs commit should mark all 21 IDs complete in both places."
  - id: W-02
    severity: warning
    statement: >
      `tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval`
      failed on this verifier's run (`assert 2 > (1 + 2)`). It is a non-deterministic
      Windows timer assertion in the frozen market module.
    correct_state: >
      NOT a phase-3 regression. `git diff --name-only 9867eb8..HEAD -- backend/app/market
      backend/tests/market` is empty, so neither the code nor the test changed this phase.
      It is a real pre-existing defect in a frozen module and should be recorded as such
      rather than absorbed into phase 3.
    action: "Record against the market module; do not attribute to phase 3."
  - id: I-01
    severity: info
    statement: >
      A trade rejected by a business rule (not by cheap validation) leaves an orphaned
      registration on the market source: `source.add_ticker` runs before the transaction,
      so an insufficient-cash refusal for an unwatched symbol registers it with the feed
      while rolling back the watchlist row. Probe-confirmed: ORCL orphaned in source True,
      on watchlist False, cash unchanged, and absent from the source after a restart.
    correct_state: >
      This is the documented and intended behavior - it is the same shape as D-08's
      accepted asymmetry on remove, it is not user-visible (the watchlist API is database
      state, not cache state), and it self-heals at the next boot precisely because
      startup_tickers now starts the feed from the persisted rows. It is 03-06's second
      backstop truth, and it is VERIFIED rather than merely asserted.
  - id: I-02
    severity: info
    statement: >
      `POST /api/portfolio/reset` now requires `{"confirm": true}` as application/json.
      A bare POST is 422. This is the only visible API contract change from the gap plans.
    action: "Carry into Phase 4's frontend work (already flagged by executor 03-09)."
flagged_prohibitions: 13
prohibitions_note: >
  31 prohibitions across the nine plans. The 18 test-tier prohibitions introduced by the
  four gap plans (03-06..03-09) were each executed mechanically by this verifier and all
  18 pass - see the Prohibitions section. The 13 judgment-tier prohibitions (11 from plans
  03-01..03-05, 2 from 03-06) are soft-gated: this is an autonomous run, so the verdicts
  recorded are NON-AUTHORITATIVE LLM-judge findings, each flagged
  `unverified-prohibition - human review recommended`. None is a silent pass.
human_verification:
  - test: >
      Run the container with the simulator streaming, hold at least one position, and watch
      GET /api/portfolio (or the header total) across several SSE frames.
    expected: >
      total_value and each position's unrealized_pnl move with the live price, and
      cash + sum(quantity * live price) reconciles on every frame.
    why_human: >
      The suite drives a fixed fake PriceCache. This verifier's probe did observe real
      simulator prices (fill 457.77, a later tick at 457.79) and a total_value that
      reconciled exactly, so single-frame live valuation IS verified; what remains human is
      sustained drift over many frames against a running container. Carried from 03-03
      SUMMARY (D6, human_judgment: true).
  - test: >
      Confirm the narrow reading of PORT-14's "starting state": reset restores $10,000 cash
      and clears positions while deliberately preserving the watchlist and the append-only
      trades log.
    expected: "The developer agrees a reset should not discard curated tickers or the audit trail (CONTEXT D-10)."
    why_human: "PORT-14 is [NEW] with no PLAN.md text; D-10..D-13 are its whole specification. Product intent, not a code property. Carried from 03-03 SUMMARY (D7)."
  - test: "Review the 13 judgment-tier prohibitions in the Prohibitions section and confirm each verdict."
    expected: "Each prohibition is genuinely honored, or is recorded as an accepted deviation."
    why_human: "Judgment-tier prohibitions are a soft gate under autonomous verification; the verdicts recorded are non-authoritative by design."
  - test: "Confirm W-01 above and mark all 21 phase-3 requirement IDs complete in .planning/REQUIREMENTS.md."
    expected: "All 21 IDs read `[x]` in the requirements list and `Complete` in the traceability table, matching the phase-1/phase-2 convention."
    why_human: "A ledger write is a decision about phase closure, not a code property. The verifier does not edit REQUIREMENTS.md."
accepted_risks:
  - id: T-03-55
    statement: "portfolio_snapshots grows unbounded on a long-running container - roughly 2880 rows/day for a held portfolio."
    disposition: accept
    note: "Reads are bounded by the ?limit= cap of 5000 (probe-confirmed 422 above it), so this degrades storage, not any response. Re-confirmed on this run."
  - id: 03-07-backstop
    statement: >
      A source.stop() that itself raises is deliberately not defended, and reclaiming a
      snapshot task whose database call is in flight can block for up to the 5s SQLite busy
      timeout because asyncio.to_thread is not interruptible.
    disposition: accept
    note: "Recorded by plan 03-07 as an accepted non-defense rather than a behavior to assert. Confirmed as a real property of app/main.py lines 84-87 by reading. Forcing it in a test would introduce a second timing flake this phase cannot afford."
---

# Phase 3: Portfolio & Watchlist APIs Verification Report

**Phase Goal:** The user's cash, positions and watched tickers are real, live-valued, and rule-enforced
**Verified:** 2026-08-15T15:20:00Z
**Status:** human_needed
**Re-verification:** Yes - after four gap-closure plans (03-06, 03-07, 03-08, 03-09)
**Mode:** Standard (ROADMAP `mode: null`; MVP-mode section dormant)

## Headline

**All three blocking gaps are closed, and they are closed in production, not in a fixture.**
The auto-add-on-trade path that could never fill now fills in 0.02 seconds where it previously
400'd after 2.08 seconds. The boot path reads the persisted watchlist. The lifespan reclaims the
market source from a `finally` block. Every closure was confirmed by a verifier-written probe
that drives `create_app()` through a real `TestClient` lifespan against a real
`SimulatorDataSource` and **writes nothing to `PriceCache`** - the constraint this phase's own
history made binding.

The one residual explicitly flagged by executor 03-08 as unasserted - the pydantic leak at the
REAL site, `PortfolioResponse(**payload)` in `api/portfolio.py` - **is now closed and proven**
(probe P3a/P3b).

**Two findings are recorded, neither blocking:** the phase-3 requirements ledger was never
written (W-01, and it is all 21 IDs, not the two the handoff expected), and the market module
carries a pre-existing Windows timer flake that is not phase 3's (W-02).

## Method, and how the recorded anti-patterns were avoided

This phase has a documented history of a wrong VERIFIED verdict on PORT-07, caused by a probe
that hand-injected a price into the cache the same way `tests/services/test_trading.py`'s `cache`
fixture does. Two structural rules were applied:

1. **This verifier's probe writes nothing to `PriceCache`.** It calls `create_app()`, enters the
   real lifespan through `TestClient`, and lets the real `SimulatorDataSource` be the only price
   producer. `grep` on the probe source confirms no `.update(` call. Every price in the evidence
   below came from the simulator.
2. **The probe uses a different symbol from the phase's own test.** `tests/test_feed_reconciliation.py`
   uses `PYPL`; this probe uses `IBM`, so no coupling to a symbol the implementation might have
   been tuned around.

`backend/tests/test_feed_reconciliation.py` was independently audited rather than assumed:
`grep -c '\.update(' backend/tests/test_feed_reconciliation.py` outputs **0**, both tests build
their app via `create_app()` and drive it with `TestClient`, and neither asserts an exact price or
an elapsed duration. It genuinely is the production-shaped proof it claims to be.

Commands run from `backend/` with `UV_LINK_MODE=copy` (OneDrive hardlink constraint):

| Command | Result |
|---|---|
| `uv run --extra dev pytest -q` (full suite, run once) | **387 passed, 1 failed** in 25.16s - the failure is W-02's pre-existing frozen-module flake |
| `uv run --extra dev pytest -q -k "<four named tests>"` | 5 passed, 383 deselected |
| `uv run --extra dev ruff check app/ tests/` | All checks passed |
| verifier probe (40 checks, production-shaped) | **40/40 passed** |
| orphan self-heal probe | confirmed |

**Scope integrity:** `git diff --name-only 9867eb8..HEAD -- backend/app/db backend/app/market
backend/tests/market backend/tests/db` is **empty**. The frozen Phase 1 query layer and the frozen
market module were not modified by any of the nine plans, including the four gap plans.

## Goal Achievement

### Observable Truths - ROADMAP Success Criteria (the contract)

| # | Success Criterion | Status | Evidence |
|---|---|---|---|
| SC1 | Read portfolio; buy/sell at the server's price returning the actual `fill_price`, even on a ticker added moments earlier whose first tick is waited on up to 2s | VERIFIED | Probe P1c: `POST /api/portfolio/trade {IBM, buy, 2}` on a symbol the feed had never heard of returned **200 in 0.02s** with `fill_price: 457.77`, `total_cost: 915.54`, `cash_balance: 9084.46`. P1h/P1i: position reports non-null `current_price` and `total_value` (10000.0) = cash + qty x live price exactly. Registration now precedes the wait (`trading.py:141` before `:144`), so PORT-08's 2s window is a wait on a registered symbol rather than a guaranteed expiry |
| SC2 | Every trade rule holds and is tested: no buying past cash, no selling shares not held, no bad quantities, zero-position disappears, trading an unwatched ticker adds it | VERIFIED | P1l `Insufficient cash: need $18999810.00, have $9084.46`; P1m/P1n `Insufficient shares: need 1 AAPL, have 0` (fixed decimal, no exponent form); P1j quantity 0 -> 400; P2e sell-to-zero removed the row entirely; P1f/P1g IBM joined the watchlist **with a live price**. P1k confirms cheap validation still precedes registration - a refused trade registers nothing |
| SC3 | Read watchlist with live price, open price, change from open and ~60 sparkline points; add a ticker that immediately prices; 400 / 404 / 409 rules | VERIFIED | Watchlist probe: 10 tickers, keys exactly `{ticker, price, open_price, change_from_open_percent, history}`, `history` length **60**. `POST /api/watchlist {pypl}` -> 200, normalized to `PYPL`, price 337.09 and 60 history points immediately. P1t invalid symbol 400, P1s unknown removal 404, P1r held ticker 409 |
| SC4 | Value history accumulates - one snapshot per trade plus one every 30s when the value changed - retrievable with `?limit=` and `?since=` | VERIFIED | P1o: 2 snapshots after 1 trade (seed + trade). P1p `?limit=1` returns exactly 1. P1q `?limit=99999` -> 422. Interval and skip logic covered by `test_the_interval_is_thirty_seconds`, `test_an_unchanged_total_records_nothing`, `test_a_sub_cent_move_skips_and_a_full_cent_writes`. `?since` covered at both service and route level |
| SC5 | Reset to the starting state: $10,000 cash and no positions | VERIFIED | P2k/P2l: `{"confirm": true}` as JSON -> 200 with `{cash_balance: 10000.0, total_value: 10000.0, positions: []}`, read back through `get_portfolio` rather than asserted |

### Observable Truths - the three previously-failed gaps

| # | Truth | Status | Evidence |
|---|---|---|---|
| G-01 | Trading a ticker the market data source has never been told about fills and joins the watchlist (PORT-07, SC2) | **VERIFIED (was FAILED)** | `app/services/trading.py:141` `await source.add_ticker(ticker)` sits between `validate_quantity` and `wait_for_price`. Probe P1b confirms the cache did not know IBM beforehand; P1c fills in 0.02s (previously 400 after 2.08s); P1e IBM present in `source.get_tickers()`; P1f/P1g on the watchlist with a live price. `execute_trade`'s signature is `(db_path, cache, source, ticker, side, quantity)`, matching 03-SEAM-CONTRACT.md's Amendment **verbatim** (P0, via `inspect.signature`) |
| G-02 | A user-added ticker keeps its feed across a restart; every position has a live price feed | **VERIFIED (was FAILED)** | `app/main.py:79` `await source.start(await startup_tickers(app.state.db_path))`. P1a: boot tickers == the seeded watchlist rows, not a second constant. P2a: after a full restart against the same database, source tickers are the 10 defaults **plus IBM**. P2b/P2c: non-null price, `current_price` and `market_value`. P2d: the restart-surviving position **sells** (200). P2f: removable once closed (204). The two `watchlist.py` docstrings that previously asserted false behavior are now true statements about `startup_tickers` |
| G-03 | The lifespan owns both background tasks and reclaims both, so nothing outlives the app | **VERIFIED (was PARTIAL)** | `app/main.py:82-87` - `try/yield/finally`, and `await source.stop()` is inside the `finally` with no conditional above it. Probe P4: with `record_snapshot` patched to raise and the interval at 0.01s, the recorder died, **leaving the lifespan raised nothing** (P4a) and **no `simulator-loop` task survived** (P4b). The death is still reported loudly - the probe's stderr carries `Snapshot loop stopped: probe: snapshot recorder died` from `_log_if_failed`, so PORT-12's raise-don't-swallow is intact and only the blocked teardown was fixed |

### Observable Truths - gap-plan must-haves (43 new)

| Plan | Truths | Status | Evidence |
|---|---|---|---|
| 03-06 | 12 truths + 2 backstop | 14/14 VERIFIED | Signature (P0), registration ordering (`trading.py:139-144`, P1k), first-launch feed from seeded rows (P1a), restart survival (P2a-P2f), `startup_tickers` reads only (`grep 'INSERT INTO\|DELETE FROM\|UPDATE ' app/main.py` = 0; `test_an_emptied_watchlist_stays_empty` asserts `read_watchlist == []` after the fallback fires), no cache writes in the reconciliation test (grep = 0), `from __future__ import annotations` present in both `__init__.py` files. **Backstop 1** (emptied watchlist boots from the defaults writing no rows) - explicit evidence at `tests/services/test_watchlist.py:294-295`. **Backstop 2** (orphaned registration self-heals) - probe-confirmed: ORCL orphaned True / on watchlist False / absent from source after restart |
| 03-07 | 8 truths + 1 backstop | 8/8 VERIFIED, 1 accepted-risk | Teardown on the failure path (P4a-P4c); order unchanged (`main.py:85-87` cancel, gather, then stop); loud report (`grep -c 'logger.error(' app/main.py` = 1, observed firing); quiet normal path (`test_lifespan_starts_and_stops_source` passes); `snapshots.py` untouched by this plan; docstring true (read and confirmed); static mount last (`app.frontend(...)` is the final statement before `return app`, after four `include_router` calls; `test_api_not_shadowed` passes over real HTTP); suite green + ruff clean **with exactly the one named flake**, which is this truth's own stated allowance. The backstop is an accepted non-defense, recorded under accepted_risks |
| 03-08 | 12 truths | 12/12 VERIFIED | Messages and status codes unchanged (P1l/P1t carry `Insufficient cash` and the invalid-ticker 400); `ValueError not in app.exception_handlers` is **False** while all three taxonomy classes are True; **the flagged residual is closed** (P3a/P3b); snapshot valued at `fill_price` via the `prices[ticker] = fill_price` overlay (`trading.py:148`) with `grep -c 'in cache.get_all().items()'` = 1, so no second cache read was added; `cash_balance` computed once at storage precision (`trading.py:210,226`); sub-half-cent overdraft closed by comparing raw cost against raw cash before rounding (`trading.py:208`); `_format_shares` fixed decimal (P1m has no `e-`); derived figures unrounded (`test_the_fill_after_the_wait_is_the_cache_float_untouched` passes); zero shares renders `have 0` (P1n) |
| 03-09 | 8 truths | 8/8 VERIFIED | P2g/P2h/P2i: form-encoded, bodyless and text/plain all **422**; P2j: refused resets left cash exactly as it was; P2k/P2l: JSON body -> 200 with the same three-key shape as GET; `reset_portfolio(db_path, cache)` returns `await get_portfolio(...)` (`services/portfolio.py:192`) with `grep -c 'return {'` = 1; `grep -c 'body\.confirm'` = 0 so the handler never branches on the value; P5a zero cost basis -> null percent while `current_price`, `market_value`, `unrealized_pnl` stay real and the position still counts toward total; P5b break-even reports `0.0` not null; `ResetRequest` carries no constraint helper, validator or default |

### Observable Truths - regression check on the 69 previously-passing must-haves

| Check | Status | Evidence |
|---|---|---|
| Full suite | PASS | 387 passed; the single failure is the frozen-module flake (W-02) |
| ruff | PASS | All checks passed |
| Frozen modules | PASS | `app/db` and `app/market` diffs empty across the whole phase |
| Seam contract honored | PASS | `execute_trade` matches the amended signature verbatim; `watchlist.add(db_path, source, ticker)` and `remove(db_path, ticker)` unchanged; no FastAPI object crosses the seam |
| Full API surface | PASS | The 40-check probe exercises every phase-3 route and every rejection path end-to-end through the assembled app |

**Score:** 115/115 must-haves verified (72 original + 43 from the four gap plans). 0 behavior-unverified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `backend/app/services/trading.py` | `execute_trade` at the amended contract shape, registering before the price wait | VERIFIED | 237 lines. `source: MarketDataSource` present; `await source.add_ticker(ticker)` at line 141 between validation and the wait; imported and called by `api/portfolio.py:58` |
| `backend/app/services/watchlist.py` | `startup_tickers` - the persisted watchlist read the lifespan starts from | VERIFIED | 203 lines. `async def startup_tickers` at line 104, reads through `run_db(db_path, get_watchlist)`, falls back to `DEFAULT_TICKERS`, writes nothing. Imported and awaited at `main.py:79` |
| `backend/app/main.py` | Lifespan starting from the persisted watchlist; exception-safe teardown; `_log_if_failed` | VERIFIED | 100 lines. `startup_tickers` at :79, `try/finally` at :82-87, `_log_if_failed` at :31. Mount order correct: four `include_router` calls then `app.frontend(...)` last |
| `backend/app/api/portfolio.py` | `create_portfolio_router(price_cache, source)`; reset requiring `ResetRequest` | VERIFIED | 126 lines. Factory holds the source and passes it third to `execute_trade`; `body: ResetRequest` at :105; `reset_portfolio(db_path, price_cache)` at :123 |
| `backend/app/api/errors.py` | Handler table reduced to the three taxonomy classes | VERIFIED | 41 lines, three `add_exception_handler` calls, no `ValueError` row - mechanically confirmed |
| `backend/app/api/models.py` | `ResetRequest`, shape-only | VERIFIED | `class ResetRequest(BaseModel): confirm: bool` - no constraint, no validator, no default |
| `backend/app/services/portfolio.py` | `reset_portfolio(db_path, cache)` reading back; zero-cost-basis null | VERIFIED | 192 lines. `return await get_portfolio(...)`; `None if cost_basis == 0 else ...` at :86 |
| `backend/tests/test_feed_reconciliation.py` | Two production-shaped proofs | VERIFIED | 120 lines, real `create_app()` + `TestClient` + real simulator, **zero `.update(` calls**, no exact price or duration asserted. Independently audited, not assumed |
| `backend/tests/test_main.py` | Failure-path teardown proof and its quiet control | VERIFIED | 252 lines, `test_lifespan_stops_the_source_when_the_snapshot_task_died` present and passing |

### Key Link Verification

| From | To | Via | Status |
|---|---|---|---|
| `app/services/trading.py` | `app/market/interface.py` | `await source.add_ticker(ticker)` after validation, before `wait_for_price` | WIRED - line 141, ordering confirmed by probe P1k and P1c |
| `app/api/portfolio.py` | `app/services/trading.py` | handler passes the router's source as `execute_trade`'s third argument | WIRED - line 58-60, positional, matches the contract |
| `app/main.py` | `app/services/watchlist.py` | `await source.start(await startup_tickers(app.state.db_path))` | WIRED - line 79, probe P1a/P2a confirm the source's ticker set follows the database |
| `app/services/watchlist.py` | `app/db/connection.py` | `await run_db(db_path, get_watchlist)` - frozen layer called, not modified | WIRED - line 119, frozen diff empty |
| `app/main.py` | `app/market/interface.py` | `await source.stop()` from a `finally` block | WIRED - line 87, inside the sole `finally`, no conditional above it |
| `app/api/portfolio.py` | `app/services/portfolio.py` | route hands its cache to `reset_portfolio`, body is a read of real state | WIRED - line 123 |
| `app/api/errors.py` | `app/services/errors.py` | one handler per taxonomy class, none broader | WIRED - three registrations, `ValueError` absent |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `GET /api/portfolio` | `positions`, `total_value` | `run_db -> _read_portfolio` + `cache.get_all()` | Yes - probe returned real simulator prices and a total that reconciled to cash + qty x price | FLOWING |
| `GET /api/watchlist` | `tickers[].price`, `.history` | `get_watchlist` rows joined against `PriceCache` + `get_history` | Yes - 10 rows, 60 history points each, non-null prices from the simulator | FLOWING |
| `GET /api/portfolio/history` | `snapshots` | `get_snapshots(limit, since)` | Yes - seed row plus per-trade rows, `?limit=` and `?since=` both honored | FLOWING |
| `POST /api/portfolio/trade` | `fill_price` | `wait_for_price` on a now-registered symbol | Yes - 457.77 from the simulator, not a fixture | FLOWING |
| `POST /api/portfolio/reset` | response body | `get_portfolio` read-back | Yes - not a constant; a retained position would surface here | FLOWING |
| market source ticker set | `startup_tickers()` | `get_watchlist` rows | Yes - probe showed the set following the database across a restart | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Unregistered ticker trades (PORT-07) | probe: `POST /api/portfolio/trade {IBM, buy, 2}` on a fresh app, no cache writes | 200 in 0.02s, fill 457.77 | PASS |
| Restart keeps the feed (G-02) | probe: second `create_app()` on the same DB | IBM in source tickers; position values; sells 200; removes 204 | PASS |
| Teardown survives a dead recorder (G-03) | probe: patch `record_snapshot` to raise, drive `lifespan_context` | no exception on exit; no `simulator-loop` task remains | PASS |
| Pydantic failure at the REAL site (WR-01 residual) | probe: force `PortfolioResponse(**payload)` to fail | **500**, body `Internal Server Error`, no model name / field path / offending value / `errors.pydantic.dev` | PASS |
| Reset not form-forgeable (WR-02) | probe: form-encoded, bodyless, text/plain | 422 / 422 / 422, cash unchanged | PASS |
| Zero cost basis (IN-05) | probe: `value_portfolio` with `avg_cost=0.0` | percent None, other figures real, counted in total | PASS |
| Named test - derived figures unrounded | `pytest -k test_the_fill_after_the_wait_is_the_cache_float_untouched` | passed | PASS |
| Named test - static mount not shadowing | `pytest -k test_api_not_shadowed` | passed | PASS |
| Named test - failure-path teardown | `pytest -k test_lifespan_stops_the_source_when_the_snapshot_task_died` | passed | PASS |
| Named tests - feed reconciliation | `pytest -k feed_reconciliation` | 2 passed | PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` exists for this phase and no plan declares one. Phase 2's
`scripts/smoke_check.py` requires a running container and is out of scope here. All probe evidence
above is from verifier-written, production-shaped Python probes run in this verifier's own process.

### Prohibitions

**Test-tier (18) - all executed mechanically by this verifier, all pass:**

| Plan | Check | Result |
|---|---|---|
| 03-06 | `grep -c '\.update(' tests/test_feed_reconciliation.py` = 0 | 0 - PASS |
| 03-06 | zero-quantity trade leaves the source's added list empty | P1k - PASS |
| 03-06 | no diff under `app/market/` or `app/db/` | empty - PASS |
| 03-06 | `grep -c 'INSERT INTO\|DELETE FROM\|UPDATE ' app/main.py` = 0; emptied watchlist stays empty | 0; asserted at `test_watchlist.py:295` - PASS |
| 03-07 | `grep -c 'except Exception' app/main.py` = 0 | 0 - PASS |
| 03-07 | `grep -c 'sqlite3' app/main.py` = 0 | 0 - PASS |
| 03-07 | `grep -c 'logger.error(' app/main.py` = 1 | 1 - PASS |
| 03-07 | `git status --porcelain -- app/services/` empty (loop untouched) | clean - PASS |
| 03-07 | `grep -c 'await source.stop()' app/main.py` = 1, inside the one `finally`, unconditional | 1; `finally:` count 1 - PASS |
| 03-07 | `grep -c 'asyncio.create_task(' app/main.py` = 1 and `task.cancel()` = 1 | 1 / 1 - PASS |
| 03-08 | `ValueError in app.exception_handlers` is False; the three taxonomy classes True | False / True x3 - PASS |
| 03-08 | `Invalid ticker symbol` and `No price available for` still arrive in a 400 | P1t and the wait test - PASS |
| 03-08 | `grep -c 'except ValueError as exc'` = 2 in `trading.py` and 2 in `watchlist.py` | 2 / 2 - PASS |
| 03-08 | `test_the_fill_after_the_wait_is_the_cache_float_untouched` still passes | passed - PASS |
| 03-08 | `grep -c 'in cache.get_all().items()' app/services/trading.py` = 1 | 1 - PASS |
| 03-09 | form-encoded reset -> 422 and cash unchanged | P2g / P2j - PASS |
| 03-09 | `grep -c 'body\.confirm' app/api/portfolio.py` = 0 | 0 - PASS |
| 03-09 | `grep -v '^#' app/services/portfolio.py \| grep -c 'return {'` = 1 | 1 - PASS |
| 03-09 | zero-cost-basis percent is None, other figures real, still counted | P5a - PASS |
| 03-09 | no diff under `app/market/` or `app/db/` | empty - PASS |

**Judgment-tier (13) - NON-AUTHORITATIVE, flagged `unverified-prohibition - human review recommended`:**
11 carried from plans 03-01..03-05 (verdicts unchanged from the previous report; the code they
constrain is either unmodified or was modified in the direction the prohibition requires), plus 2
from 03-06: "MUST NOT reduce the auto-add rule to a partial version" (LLM-judge verdict: honored -
the fix is in the seam every caller shares, and the probe proves it through the assembled app, not
only in a test) and "MUST NOT correct the false docstrings before the behavior matches" (LLM-judge
verdict: honored - `git log` shows `b9dcaca fix(03-07)` landing behavior before `899fdb9 docs(03-07)`
made the docstring true, and the same ordering holds for `watchlist.py` in 03-06). Both remain
soft-gated and route to human review.

### Requirements Coverage

All 21 declared IDs are accounted for. No orphans: `grep "Phase 3" REQUIREMENTS.md` returns exactly
these 21 and no more.

| Requirement | Description | Status | Evidence |
|---|---|---|---|
| PORT-01 | Retrieve portfolio - cash, total, per-position figures | SATISFIED | P1h/P1i/P2c; `value_portfolio` + `get_portfolio`; nulls for unpriced holdings |
| PORT-02 | Buy at server price, cash decreases by the fill | SATISFIED | P1c: cash 10000.00 -> 9084.46 = 2 x 457.77; balance at storage precision |
| PORT-03 | Sell held shares, cash increases | SATISFIED | P2d: sell 2 IBM at 457.79, cash 10000.04 |
| PORT-04 | Buy past cash -> 400 naming need and have | SATISFIED | P1l; sub-half-cent boundary closed by raw comparison |
| PORT-05 | Sell past holdings -> 400, no shorting | SATISFIED | P1m/P1n, fixed decimal, `have 0` for no position |
| PORT-06 | Bad quantity -> 400 | SATISFIED | P1j; `validate_quantity` with `isfinite` first; runs before registration |
| PORT-07 | Trading an unwatched ticker adds it | **SATISFIED (was the failed one)** | P1c-P1g on a genuinely unregistered symbol with no cache writes |
| PORT-08 | Just-added ticker waited on up to 2s | SATISFIED | `wait_for_price(timeout=PRICE_WAIT_SECONDS=2.0)` now downstream of registration; `TestPriceWait` suite |
| PORT-09 | Sell to zero deletes the row | SATISFIED | P2e; `delete_position` under `is_zero` |
| PORT-10 | Response reports the server `fill_price` | SATISFIED | P1c/P2d; derived figures unrounded |
| PORT-11 | Every trade writes a snapshot immediately | SATISFIED | P1o; `insert_snapshot` inside `_apply_trade`, valued at the fill price |
| PORT-12 | 30s background snapshot, skipping unchanged | SATISFIED | `SNAPSHOT_INTERVAL_SECONDS = 30.0`; skip logic tested; loop dies loudly and no longer blocks teardown |
| PORT-13 | History with `?limit=` and `?since=` | SATISFIED | P1p/P1q; `since` covered at service and route level |
| PORT-14 | Reset to $10,000 and no positions | SATISFIED | P2k/P2l; scope of "starting state" is human item 2 |
| WATCH-01 | Watchlist with price, open, change from open, ~60 history points | SATISFIED | probe: all five keys, history length exactly 60 |
| WATCH-02 | Add validated by `^[A-Z]{1,5}$` after uppercasing | SATISFIED | `pypl` -> `PYPL` 200; `toolongsym` -> 400 |
| WATCH-03 | Adding registers with the live source so it produces prices | SATISFIED | `PYPL` priced 337.09 with 60 backfilled points on the add response; survives restart (P2a) |
| WATCH-04 | Remove a ticker held no position in | SATISFIED | P2f -> 204 |
| WATCH-05 | Removing a held ticker -> 409, readable message | SATISFIED | P1r; message names the ticker and the remedy |
| WATCH-06 | Removing an unwatched ticker -> 404 | SATISFIED | P1s |
| TEST-02 | Backend tests cover execution and every rejection path | SATISFIED | `tests/services/test_trading.py` 639 lines; insufficient cash, insufficient shares, invalid quantity, zero-position deletion all covered; plus the production-shaped `test_feed_reconciliation.py` |

**Ledger state (W-01):** all 21 read `[ ]` / `Pending` in REQUIREMENTS.md. The evidence above says
all 21 should read `[x]` / `Complete`. The file has not been edited since phase 2, so this is not a
lost merge - it is an unwritten ledger. The verifier does not edit REQUIREMENTS.md; human item 4.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| - | - | none | - | `grep` for `TODO\|FIXME\|XXX\|TBD\|HACK\|PLACEHOLDER\|not yet implemented\|coming soon` across every phase-3 file returns nothing. No stub returns, no empty handlers, no hardcoded empty data reaching a response |

### Human Verification Required

#### 1. Live drift against a running container

**Test:** Run the container with the simulator streaming, hold at least one position, and watch
`GET /api/portfolio` (or the header total) across several SSE frames.
**Expected:** `total_value` and each position's `unrealized_pnl` move with the live price, and
`cash + sum(quantity x live price)` reconciles on every frame.
**Why human:** The suite drives a fixed fake `PriceCache`. This verifier's probe did observe real
simulator prices and an exactly-reconciling total, so single-frame live valuation is verified;
sustained drift over many frames against a real container is not. Carried from 03-03 (D6).

#### 2. PORT-14's "starting state" scope

**Test:** Confirm that reset restoring $10,000 and clearing positions while preserving the
watchlist and the append-only trades log is the intended reading.
**Expected:** The developer agrees a reset should not discard curated tickers or the audit trail.
**Why human:** PORT-14 is `[NEW]`; D-10..D-13 are its whole specification. Product intent.

#### 3. The 13 judgment-tier prohibition verdicts

**Test:** Review the Prohibitions section and confirm each judgment-tier verdict.
**Expected:** Each is genuinely honored, or recorded as an accepted deviation.
**Why human:** Non-authoritative by design under autonomous verification.

#### 4. Write the phase-3 requirements ledger (W-01)

**Test:** Mark all 21 phase-3 IDs `[x]` in the requirements list and `Complete` in the traceability
table of `.planning/REQUIREMENTS.md`.
**Expected:** Phase 3 matches the phase-1/phase-2 convention.
**Why human:** A ledger write is a phase-closure decision, not a code property.

### Gaps Summary

**None.** All three gaps from the previous verification are closed, and closed in production rather
than in a fixture - each confirmed by a probe that drives the assembled app through its real
lifespan with the real simulator and writes nothing to the price cache. The four warning-level and
five info-level findings from `03-REVIEW.md` are closed as well, including the pydantic-leak
residual that executor 03-08 explicitly flagged as unasserted, which this verifier proved at the
real handler site.

Two non-blocking findings are recorded rather than absorbed: the phase-3 requirements ledger was
never written (W-01 - and it is all 21 IDs, not the two the handoff anticipated), and the market
module's `test_custom_update_interval` is a genuine pre-existing Windows timer defect that phase 3
did not cause and must not be credited with.

The phase goal - **the user's cash, positions and watched tickers are real, live-valued, and
rule-enforced** - is achieved.

---

_Verified: 2026-08-15T15:20:00Z_
_Verifier: Claude (gsd-verifier)_
