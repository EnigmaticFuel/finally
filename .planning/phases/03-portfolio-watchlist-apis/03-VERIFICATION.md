---
phase: 03-portfolio-watchlist-apis
verified: 2026-08-13T22:45:00Z
status: gaps_found
score: 69/72 must-haves verified
behavior_unverified: 0
overrides_applied: 0
flagged_prohibitions: 11
prohibitions_note: >
  All 11 prohibitions across the five plans are verification-tier `judgment`.
  This is an autonomous verification run, so the verdicts recorded below are
  NON-AUTHORITATIVE LLM-judge findings, each flagged
  `unverified-prohibition - human review recommended`. None is a silent pass.
verifier_correction: >
  An earlier draft of this report recorded PORT-07 as VERIFIED. That was WRONG.
  The verifier's own first probe hand-injected PYPL into the price cache -
  reproducing exactly the fixture arrangement that makes the test suite green -
  and so proved nothing about production. A production-shaped probe (real
  lifespan, real simulator, no cache injection) shows the requirement fails.
  Recorded because the failure mode is instructive: a green test and a green
  probe can share the same blind spot.
gaps:
  - truth: "Trading a ticker that is not on the watchlist adds it to the watchlist as part of the trade (PORT-07, ROADMAP SC2)"
    status: failed
    reason: >
      execute_trade awaits wait_for_price BEFORE opening the transaction, and
      add_watchlist_ticker lives INSIDE that transaction. Nothing on the trade
      path ever registers the symbol with the market data source, so a ticker
      the simulator has never been told about never gets a price, the 2s wait
      always expires, and _apply_trade is never reached. The auto-add is
      unreachable for exactly the case the requirement names.
    artifacts:
      - path: "backend/app/services/trading.py"
        issue: "Line 103 `await wait_for_price(...)` precedes line 106 `run_db(db_path, _apply_trade, ...)`; the `add_watchlist_ticker` at line 144 is inside the transaction and therefore downstream of a wait that cannot succeed for an unregistered symbol. `execute_trade` takes no `MarketDataSource`, so it has no way to register one."
      - path: "backend/tests/services/test_trading.py"
        issue: "The `cache` fixture at lines 33-38 calls `price_cache.update(UNWATCHED, FILL_PRICE)`, hand-injecting PYPL. This performs the exact registration step production lacks, so `test_buy_fills_and_lands_everywhere`'s PORT-07 assertion passes against an arrangement production never produces."
    missing:
      - "Register the traded symbol with the market data source before (or as part of) the price wait, so a genuinely new ticker can produce a first tick"
      - "A test that trades an unwatched ticker WITHOUT pre-seeding the cache - driving the real source through the lifespan - so the fixture cannot mask the gap"
      - "Resolve the seam-contract consequence: execute_trade(db_path, cache, ticker, side, quantity) has no `source` parameter, so the fix either changes a signature 03-SEAM-CONTRACT.md locks as one-way, or reaches the source another way"
  - truth: "The user's positions and watched tickers are real and live-valued (phase goal); every position has a live price feed (PLAN.md section 8 invariant)"
    status: failed
    reason: >
      The lifespan starts the market source from the hardcoded DEFAULT_TICKERS
      constant, never from the persisted watchlist. A user-added ticker survives
      a restart in the database but gets no feed. Its position then reports a
      null price, is silently excluded from total_value, cannot be sold
      (wait_for_price 400s) and cannot be removed (409, position held) - a
      stranded holding with no in-app recovery short of a full portfolio reset.
      This also falsifies the D-09 rationale Phase 3 wrote into its own
      docstrings ("the source is started from the watchlist rows on every boot"),
      and removes the premise that makes the 409 held-ticker rule safe.
    artifacts:
      - path: "backend/app/main.py"
        issue: "Line 55 `await source.start(list(DEFAULT_TICKERS))` - the seeded constant, not the persisted watchlist. Nothing reconciles the source's ticker set with the watchlist table at boot."
      - path: "backend/app/services/watchlist.py"
        issue: "Docstrings at lines 110-113 and 135-137 assert 'the source is started from it on every boot' and 'the source is started from the watchlist rows on every boot'. Both are false, and the D-08/D-09 reasoning rests on them."
    missing:
      - "Start the market source from the persisted watchlist rows (union with DEFAULT_TICKERS on a fresh database) rather than the constant alone"
      - "A restart-shaped test: add a ticker, take a position, tear down the lifespan, bring a second app up against the same database, assert the ticker still prices and the position still values"
      - "Correct the two watchlist.py docstrings once the behavior matches them"
  - truth: "The lifespan owns both background tasks and cancels both, so nothing outlives the app (03-05 truth 4)"
    status: partial
    reason: >
      Holds on the normal path. When snapshot_loop dies of anything other than
      CancelledError, `await task` re-raises that exception out of the lifespan,
      so `await source.stop()` is never reached: the market source and its
      simulator-loop task survive shutdown. The loop dying is correct and
      required by PORT-12's raise-don't-swallow prohibition; the defect is only
      that its corpse blocks the rest of the teardown.
    artifacts:
      - path: "backend/app/main.py"
        issue: "Lines 58-63: `task.cancel()` is a no-op on an already-failed task, and the `except asyncio.CancelledError` catches only cancellation, so any other exception propagates before line 63 `await source.stop()`."
    missing:
      - "Ensure source.stop() runs regardless of how the snapshot task ended (e.g. try/finally around the teardown), without swallowing the snapshot failure"
      - "A test that fails the snapshot loop and asserts the market source was still stopped"
deferred: []
human_verification:
  - test: "Run the container with the simulator streaming, hold at least one position, and watch GET /api/portfolio (or the header total) across several SSE frames."
    expected: "total_value and each position's unrealized_pnl move with the live price, and cash + sum(quantity * live price) reconciles on every frame."
    why_human: "The entire test suite drives a fixed fake PriceCache. Drift against a genuinely moving feed is only observable against a running container. Carried from 03-03 SUMMARY (D6, human_judgment: true)."
  - test: "Confirm the narrow reading of PORT-14's 'starting state': reset restores $10,000 cash and clears positions while deliberately preserving the watchlist and the append-only trades log."
    expected: "The developer agrees a reset should not discard curated tickers or the audit trail (CONTEXT D-10)."
    why_human: "PORT-14 is [NEW] with no PLAN.md text; D-10..D-13 are its whole specification. Product intent, not a code property. Carried from 03-03 SUMMARY (D7, human_judgment: true)."
  - test: "Review the 11 judgment-tier prohibitions in the Prohibitions section and confirm each verdict."
    expected: "Each prohibition is genuinely honored, or is recorded as an accepted deviation."
    why_human: "Judgment-tier prohibitions are a soft gate under autonomous verification; the verdicts recorded are non-authoritative by design."
accepted_risks:
  - id: T-03-55
    statement: "portfolio_snapshots grows unbounded on a long-running container - roughly 2880 rows/day for a held portfolio."
    disposition: accept
    note: "Reads are bounded by the ?limit= cap of 5000 (probe-confirmed 422 above it), so this degrades storage, not any response. Confirmed a real property of the code and correctly dispositioned."
---

# Phase 3: Portfolio & Watchlist APIs Verification Report

**Phase Goal:** The user's cash, positions and watched tickers are real, live-valued, and rule-enforced
**Verified:** 2026-08-13T22:45:00Z
**Status:** gaps_found
**Re-verification:** No - initial verification
**Mode:** Standard (ROADMAP `mode: null`; MVP-mode section dormant)

## Headline

Phase 3 is substantially built and of high quality: 69 of 72 must-haves verify against the
codebase, the service seam matches its locked contract exactly, the frozen modules were not
touched, the suite is green and ruff is clean. **Three confirmed gaps block the phase goal**, and
one of them is a requirement-level failure that the test suite reports as passing.

## A note on method, and on a verifier error

Verification was goal-backward and independent of the SUMMARY files. Evidence is code reads,
verifier-written probes driving the real app, and one full suite run in this verifier's own process.

**The first draft of this report recorded PORT-07 as VERIFIED. That was wrong.** The verifier's
initial probe called `app.state.price_cache.update("PYPL", 70.0)` before trading PYPL - reproducing
precisely the fixture arrangement that makes the test suite green - and therefore proved nothing
about production behavior. Re-probing with the real lifespan and no cache injection reversed the
finding. This is recorded rather than quietly fixed because it is the instructive part: a green
test and a green probe shared one blind spot, and only a production-shaped run exposed it.

Commands run (from `backend/`, `UV_LINK_MODE=copy` per the OneDrive constraint):

| Command | Result |
|---|---|
| `uv run --extra dev pytest tests/services tests/api tests/test_main.py -q` | 121 passed in 10.03s |
| `uv run --extra dev pytest -q` (full suite, run once) | **351 passed, 0 failed** in 16.22s |
| `uv run --extra dev ruff check app/ tests/` | All checks passed |

Both flaky tests named in the execution state passed on this run; no flake allowance was applied.

**Scope integrity:** `git diff --name-only 9867eb8..HEAD -- backend/app/db backend/app/market` is
**empty**. The frozen Phase 1 query layer and the frozen market module were not modified, exactly as
`03-CONTEXT.md` requires. `app/main.py` (+23/-2) is the only pre-existing file changed.

## Gaps

### G-01 (BLOCKER) - PORT-07 auto-add is unreachable in production

**Requirement:** PORT-07 / ROADMAP SC2 - "Trading a ticker that is not on the watchlist adds it to
the watchlist as part of the trade."

**Production-shaped probe** (real lifespan, real simulator, cache untouched):

```
seeded watchlist:            [AAPL, AMZN, GOOGL, JPM, META, MSFT, NFLX, NVDA, TSLA, V]
source tickers at boot:      [AAPL, AMZN, GOOGL, JPM, META, MSFT, NFLX, NVDA, TSLA, V]
cache knows PYPL:            False
POST /api/portfolio/trade {PYPL, buy, 1}
  -> 400 {"detail": "No price available for PYPL yet, please try again"}   (took 2.08s)
PYPL on watchlist after trade: False
```

**Root cause, in the code.** `backend/app/services/trading.py`:

- line 103 `fill_price = await wait_for_price(cache, ticker, timeout=PRICE_WAIT_SECONDS)`
- line 106 `filled = await run_db(db_path, _apply_trade, ...)`
- line 144 `add_watchlist_ticker(conn, ticker)` - inside `_apply_trade`

The auto-add sits *downstream* of a wait that can never succeed for a symbol the market source has
never been told about. `execute_trade` receives a `PriceCache` but no `MarketDataSource`, so it has
no mechanism to register one. The 2.08s measured latency is the full `PRICE_WAIT_SECONDS` expiring.

**Why the test is green.** `backend/tests/services/test_trading.py` lines 33-38:

```python
@pytest.fixture
def cache() -> PriceCache:
    """A cache holding one price, so no test waits on a live feed."""
    price_cache = PriceCache()
    price_cache.update(UNWATCHED, FILL_PRICE)   # UNWATCHED = "PYPL"
    return price_cache
```

The fixture performs the registration step production omits. `test_buy_fills_and_lands_everywhere`
then asserts `len(watched) == 1, "a traded ticker joins the watchlist (PORT-07)"` and passes. The
assertion is real; the arrangement is not reachable in production.

**What does still work** (the residual case, probe-confirmed): a ticker that is cached but not
watched - e.g. after `DELETE /api/watchlist/NFLX`, since `remove` deliberately does not deregister
from the source (D-08) - trades successfully and *is* re-added. So `add_watchlist_ticker` is not
dead code; it is simply unreachable for the case the requirement is about.

**Downstream blast radius.** Phase 6 routes LLM trades through this same seam, so "buy me some
PYPL" will 400 after a 2s stall. PLAN.md's invariant "trading a ticker not on the watchlist adds it,
which holds the invariant that every position has a live price feed" does not hold.

### G-02 (BLOCKER) - user-added tickers lose their feed on restart, stranding positions

**Probe** (session 1 adds IBM and buys it; session 2 is a fresh app on the same database):

```
S1 IBM registered with source:  True
S1 IBM priced:                  True
S1 persisted watchlist:         [AAPL, ..., IBM, ...]

-- restart --
CLAIM-2 source tickers after restart:  [AAPL, AMZN, GOOGL, JPM, META, MSFT, NFLX, NVDA, TSLA, V]
CLAIM-2 IBM has a feed after restart:  False
CLAIM-2 IBM position valuation:  {ticker: IBM, quantity: 1.0, avg_cost: 457.75,
                                  current_price: None, market_value: None,
                                  unrealized_pnl: None, unrealized_pnl_percent: None}
CLAIM-2 total_value: 9542.25   cash: 9542.25      <- the holding contributes nothing
CLAIM-2 sell held IBM   -> 400 {"detail": "No price available for IBM yet, please try again"}
CLAIM-2 remove held IBM -> 409 {"detail": "Cannot remove IBM while you hold a position in it..."}
```

The position is **unsellable and un-removable** - a deadlock whose only in-app exit is
`POST /api/portfolio/reset`, which discards the holding entirely.

**Root cause.** `backend/app/main.py:55` `await source.start(list(DEFAULT_TICKERS))` starts the feed
from the hardcoded seed constant, never from the `watchlist` table. Nothing reconciles the two at
boot. `git blame` attributes that line to Phase 1 (`19b4140 feat(01-03)`), where it was harmless
because no user-added tickers and no positions existed yet. **Phase 3 is what made it consequential**
and Phase 3 asserted the opposite in its own docstrings - `services/watchlist.py:110-113` and
`:135-137` both claim "the source is started from the watchlist rows on every boot". D-09's
self-healing rationale and D-08's justification for the 409 rule both rest on that false premise, so
this is in Phase 3's scope to close even though it did not author the line.

**Relationship to the must-haves.** Every literal clause of ROADMAP SC3 passes (add does work
*immediately*, in-session). No numbered plan truth covers the restart case - the must_haves
under-specified relative to the phase goal. It is recorded against the goal itself, which says
positions and watched tickers are "real, live-valued, and rule-enforced".

### G-03 (WARNING) - a failed snapshot loop blocks market-source shutdown

**Probe** (`record_snapshot` patched to raise, interval shortened - probe-local, no code change):

```
CLAIM-3 lifespan RAISED at shutdown: RuntimeError: disk exploded
CLAIM-3 source still running after shutdown (stop() skipped): True
CLAIM-3 source tickers still registered: 10
CLAIM-3 simulator-loop still alive after shutdown: True
```

**Root cause.** `backend/app/main.py:58-63`. `task.cancel()` is a no-op on an already-failed task;
`await task` then re-raises the stored exception, which is not `CancelledError`, so it escapes the
`except` and line 63 `await source.stop()` never runs.

**Correctly scoped:** the loop *dying* is intended and is mandated by PORT-12's own prohibition
("Raise and let the task die"). The defect is narrower - the dead task blocks the rest of teardown,
so `main.py`'s docstring guarantee "This lifespan owns both background tasks and cancels both here,
so nothing outlives the app" is false on that path. This fails 03-05 truth 4 partially, not the
PORT-12 recorder behavior, which verifies cleanly.

## Goal Achievement

### ROADMAP Success Criteria

| # | Success Criterion | Status | Evidence |
|---|---|---|---|
| SC1 | Read portfolio; buy/sell at the server's price returning `fill_price`, waiting up to 2s for a first tick | VERIFIED | Probe: `GET /api/portfolio` returns the 3 keys with all 7 per-position fields. Buy of `aapl` filled at `fill_price == 191.00` (cache value, not client value). A ticker *added moments earlier via POST /api/watchlist* then bought -> 200 at 337.10, so this clause holds. `test_a_price_arriving_during_the_wait_fills` passes |
| SC2 | Every trade rule holds and is tested: no over-buy, no over-sell, no bad quantities, zero position disappears, **unwatched ticker auto-added** | **FAILED** | Five of six clauses verified (over-buy 400, over-sell 400, NaN/Infinity/0/-1/0.00001 each 400, sell-to-zero deletes the row). The auto-add clause **fails in production** - see G-01 |
| SC3 | Read watchlist with live price, open, change from open, ~60 sparkline points; add starts producing prices; 400 / 404 / 409 | VERIFIED | Probe under a live lifespan: 11 rows, exact key set, GOOGL history = 60 points; `ibm` -> `IBM` registered and pricing at 457.72 within 1.2s; `TOOLONG` -> 400, `ZZZ` -> 404, held `PYPL` -> 409 with a verbatim sentence. (Every literal clause passes; the cross-restart defect is recorded as G-02 against the goal) |
| SC4 | History accumulates - one per trade plus one every 30s when value changed - with `?limit=` and `?since=` | VERIFIED | `?limit=3` -> 3 newest-first; echoed `recorded_at` as `?since=` selects that row; 0 -> 422, 5000 -> 200, 5001 -> 422. Per-trade snapshot asserted `+1`. **30s recurrence probed directly**: 8 idle ticks wrote 0 rows, a real change wrote 1, a sub-cent change wrote 0, a cent-level change wrote 1, cancellation stopped all writes |
| SC5 | Reset to starting state: $10,000 and no positions | VERIFIED | Probe: 200 `{10000.0, 10000.0, []}`, persisted on re-read; watchlist 11->11 and trades 3->3 preserved; `GET` -> 405 |

**4 of 5 ROADMAP success criteria verified. SC2 FAILED.**

### Plan Must-Have Truths

All 67 truths across the five PLAN frontmatters were checked. Only the failures and the
behavior-dependent items are expanded here; the remainder verified against code plus probe or a
passing named test.

#### 03-01 (11 truths) - trade seam and transaction

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | `fill_price` is the server's cache price | VERIFIED | Probe returned 191.00 for a request carrying no price |
| 2 | Cash drops by `fill_price * quantity`; position at paid `avg_cost` | VERIFIED | Probe: 10000 -> 8090.0 for 10 @ 191.0 |
| 3 | **Buying an unwatched ticker leaves it watched (PORT-07)** | **FAILED** | **G-01.** Production probe: 400 after 2.08s, PYPL not added. Green test is fixture-arranged |
| 4 | Exactly one snapshot row per trade, same transaction (PORT-11) | VERIFIED | `trading.py:178` inside `writing()`; `after == before + 1` |
| 5 | A buy for exactly the whole balance succeeds | VERIFIED | `trading.py:154` strict `>` on rounded values |
| 6 | Stored values raw; rounding once at the queries.py boundary | VERIFIED | Grep: `round_money` only at `trading.py:154` and `snapshots.py:61` (both comparisons); `round_quantity` only at `:81` (validation) |
| 7 | `fill_price` captured before the transaction, never re-read | VERIFIED | `:103` captures, `:106` passes in; no cache access inside `_apply_trade` |
| 8 | `fill_price`/`total_cost` full precision | VERIFIED | `test_the_fill_after_the_wait_is_the_cache_float_untouched` |
| 9 | Unchanged post-trade total still writes a snapshot | VERIFIED | No comparison exists on the trade path |
| 10 | First trade on a fresh DB writes its snapshot | VERIFIED | Runs against `seed_fresh` |
| 11 | A rejected trade leaves no snapshot, watchlist row or cash change | VERIFIED | `test_rejected_buy_rolls_the_whole_unit_back`; probe confirmed |

#### 03-02 (14 truths) - sell settlement and rejection suite

All 14 VERIFIED. Highlights: sell leaves `avg_cost` untouched (`trading.py:173`); over-sell rolls
back; sell-to-zero deletes the row (probe-confirmed); `math.isfinite` runs before the precision
check (`:77-82`), probe-confirmed for `NaN`, `Infinity` and `1e400`, none of which reach the
precision message; the insufficient-cash message is ASCII, 2dp, no thousands separator
(`need $1910000.00, have $8020.00`). Both `verification: backstop` truths carry explicit evidence -
the two `TestPriceWait` tests for the price-window truth, and an audit of every `pytest.raises` in
`tests/services/` confirming each asserts its own branch's message text (via `match=` or
`str(exc.value)`) for the no-cross-proof truth.

#### 03-03 (14 truths) - portfolio read, history, reset

All 14 VERIFIED. Highlights: the D-14 null rule probe-confirmed by removing NVDA from the cache -
4 nulls returned and `total_value 9600.0 == cash 9100.0 + 500.0`, the priceless holding excluded;
`GET /api/portfolio/reset` -> 405 with OpenAPI showing `post` only; `limit` bounds 422/200/422;
`portfolio.py` imports no `datetime` and calls no rounding helper. The `verification: backstop`
truth about no zero-guard on `cost_basis` is confirmed structurally: `portfolio.py:80` has no guard,
and `avg_cost` is only ever written from `fill_price` arithmetic (`trading.py:163`) or preserved
(`:173`) - satisfied by construction exactly as the truth states.

#### 03-04 (16 truths) - watchlist read/add/remove

All 16 VERIFIED as literally written. Highlights: add registers with a **started** source and prices
within 1.2s without a restart; 60 history points; `AMZN` present with nulls rather than omitted or
zeroed; held-check and delete share one `writing()` block (`:158-165`); a 6-character `NOSUCH` is a
400 from `normalize_ticker` *before* any lookup while a valid-shaped `ZZZ` correctly reaches the
lookup and returns 404. **Caveat on truth 7** (a `source.add_ticker` failure leaves the row in
place, D-09): the row does survive, so the truth passes - but its stated rationale ("the source is
started from it on every boot, so it self-heals on the next start") is false, per G-02.

#### 03-05 (12 truths) - background snapshot recorder

11 of 12 VERIFIED, 1 PARTIAL.

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | `snapshot-loop` task owned by the lifespan appends rows with no request | VERIFIED | `main.py:56`; `test_lifespan_starts_and_stops_source`; probe observed request-free writes |
| 2 | Sleeps before its first write | VERIFIED | `snapshots.py:96-98`; `test_lifespan_records_no_snapshot_on_a_short_life` |
| 3 | Loop body separately callable; no test waits 30s | VERIFIED | Full suite runs in 16.22s |
| 4 | **Created after `source.start()`, cancelled before `source.stop()`; nothing outlives the app** | **PARTIAL** | **G-03.** Correct on the normal path; on a non-`CancelledError` failure `source.stop()` is skipped and `simulator-loop` survives shutdown |
| 5 | Write/skip by `round_money` equality vs the newest snapshot | VERIFIED | `snapshots.py:61`; `queries.py:205` `ORDER BY recorded_at DESC, rowid DESC` |
| 6 | Cents-equal writes nothing; one cent writes | VERIFIED | Probe: idle 0, sub-cent 0, cent-level 1 |
| 7 | Empty table writes; positionless portfolio values as cash | VERIFIED | `latest is None or ...` |
| 8 | *(backstop)* Newest-row baseline; same-microsecond tie unasserted | VERIFIED | `queries.py:205` carries that exact ORDER BY; the tie lives in frozen Phase 1 code |
| 9 | Read-compare-write inside one `writing()` block | VERIFIED | `snapshots.py:57-64`; collision test passes |
| 10 | Test fixture points `app.state.db_path` at the tmp database | VERIFIED | `tests/conftest.py:65` |
| 11 | `__all__` names every published symbol and all import | VERIFIED | Probe: 19 names, 0 unimportable |
| 12 | Whole suite green, ruff clean | VERIFIED | 351 passed; ruff clean - both run by this verifier |

**Score:** 69/72 truths verified (5 ROADMAP SC + 67 plan truths). 3 failed: ROADMAP SC2, 03-01 #3,
03-05 #4. 0 present-but-behavior-unverified.

### Seam Contract Compliance

`03-SEAM-CONTRACT.md` locks three signatures (blocking user decision, option-a). All match exactly:

| Contract | Code | Match |
|---|---|---|
| `execute_trade(db_path, cache, ticker, side, quantity) -> TradeResult` | `trading.py:86-92` | EXACT |
| `add(db_path, source, ticker) -> WatchlistEntry` | `watchlist.py:103` | EXACT |
| `remove(db_path, ticker) -> None` - **no `source` parameter** | `watchlist.py:131` | EXACT - option-a honored, no vestigial `source` |

**Contract tension raised by G-01.** `execute_trade` deliberately takes no `MarketDataSource`, which
is precisely why it cannot register a new ticker. Closing G-01 either changes a signature the
contract calls one-way and reversible only by replanning Phase 6, or finds another route to the
source. This needs a decision, not just a patch.

### Required Artifacts

All 18 declared artifacts exist, are substantive, and are wired. No stubs, no orphans - every
service module is imported by a router and exercised by tests.

| Artifact | Status | Details |
|---|---|---|
| `app/services/errors.py` | VERIFIED | 26 lines; 3 classes, all `ValueError` subclasses, no FastAPI import |
| `app/services/trading.py` | VERIFIED | 180 lines; `execute_trade`, `_apply_trade`, `validate_quantity` (G-01 is a logic gap, not a missing artifact) |
| `app/services/portfolio.py` | VERIFIED | 179 lines; all four functions |
| `app/services/watchlist.py` | VERIFIED | 165 lines; all seams and dataclasses |
| `app/services/snapshots.py` | VERIFIED | 99 lines; constant, loop, `record_snapshot`, `_record_if_changed` |
| `app/services/__init__.py` | VERIFIED | 62 lines; 19 names, all importable |
| `app/api/errors.py` | VERIFIED | 40 lines; four handlers incl. the load-bearing bare-`ValueError` row |
| `app/api/portfolio.py` | VERIFIED | 110 lines; four routes |
| `app/api/watchlist.py` | VERIFIED | 62 lines; three routes |
| `app/api/models.py` | VERIFIED | 104 lines; 9 models, **zero constraints** (D-20 honored) |
| `app/main.py` | VERIFIED | `app.frontend()` at line 75, after all four `include_router` calls |
| `tests/services/conftest.py` | VERIFIED | 61 lines; `RecordingSource` present |
| `tests/services/test_trading.py` | VERIFIED (with G-01 caveat) | 421 lines; the `cache` fixture masks PORT-07 |
| `tests/services/test_portfolio.py` | VERIFIED | 325 lines |
| `tests/services/test_watchlist.py` | VERIFIED | 245 lines |
| `tests/services/test_snapshots.py` | VERIFIED | 244 lines |
| `tests/api/test_portfolio.py` | VERIFIED | 220 lines |
| `tests/api/test_watchlist.py` | VERIFIED | 136 lines |

### Key Link Verification

All 13 declared key links WIRED, confirmed by grep at the named line numbers: routes ->
services (`execute_trade` at `api/portfolio.py:48`, `from app.services.watchlist import` at
`api/watchlist.py:12`), services -> `run_db`/`writing`, `main.py` -> all four routers before
`app.frontend()`, `snapshots.py` -> `value_portfolio` and `round_money`, `watchlist.py` ->
`normalize_ticker` (no second regex found anywhere under `app/services/` or `app/api/`),
`portfolio.py` -> `STARTING_CASH` (never a literal `10000.0`).

**One link that should exist and does not:** `services/trading.py` -> `MarketDataSource`. Its
absence is G-01's mechanism.

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data? | Status |
|---|---|---|---|---|
| `GET /api/portfolio` | positions, total | `get_positions` + `PriceCache.get_all()` | Yes | FLOWING |
| `GET /api/watchlist` | tickers + history | `get_watchlist` + `cache.get`/`get_history` | Yes - 60 real points, live 457.72 | FLOWING |
| `GET /api/portfolio/history` | snapshots | `get_snapshots(conn, limit, since)` | Yes - rows from real trades and the real loop | FLOWING |
| `POST /api/portfolio/trade` | fill | `wait_for_price` + `_apply_trade` | Yes for a fed ticker; **no path at all for an unfed one** | FLOWING (G-01 caveat) |
| `POST /api/portfolio/reset` | portfolio | `_apply_reset` + `STARTING_CASH` | Yes - persisted, re-read | FLOWING |
| Position valuation **after restart** | `current_price` | `PriceCache` never fed for user-added tickers | **No - permanently null** | **DISCONNECTED (G-02)** |

### Behavioral Spot-Checks

| Behavior | Result | Status |
|---|---|---|
| Buy fills at the server price | 200, `fill_price 191.00`, cash 8090.0 | PASS |
| **Auto-add on trade, production-shaped (no cache injection)** | **400 after 2.08s; ticker not added** | **FAIL (G-01)** |
| Auto-add for a cached-but-unwatched ticker (residual path) | 200, re-added | PASS |
| Buy after an explicit `POST /api/watchlist` | 200 at 337.10 | PASS |
| Insufficient cash / shares messages | 400 with concrete figures in both | PASS |
| `NaN` / `Infinity` / `1e400` over the wire | 400 `must be a finite number` for all three | PASS |
| Precision `0.00001` | 400 `at most 4 decimal places` | PASS |
| Sell-to-zero deletes the row | AAPL absent afterwards | PASS |
| Null-price rule (D-14) | 4 nulls, excluded from total | PASS |
| Watchlist add registers with a started source | registered, priced at 457.72 | PASS |
| 400 / 404 / 409 discrimination | `TOOLONG` 400, `ZZZ` 404, held `PYPL` 409 | PASS |
| History bounds and `?since=` echo | 422 / 200 / 422; echo selects correctly | PASS |
| Snapshot loop recurrence, skip, cancel | idle 0, move 1, sub-cent 0, cent 1, clean cancel | PASS |
| Reset preserves watchlist and trades | 11->11, 3->3 | PASS |
| Reset is POST-only | 405 on GET | PASS |
| Route surface / mount order | all 8 `/api/*` routes; `test_api_not_shadowed` passes | PASS |
| `services.__all__` importability | 19 names, 0 unimportable | PASS |
| **Restart: user-added ticker keeps its feed** | **no feed; position null, unsellable, un-removable** | **FAIL (G-02)** |
| **Shutdown after a snapshot-loop failure** | **`source.stop()` skipped; simulator survives** | **FAIL (G-03)** |

### Probe Execution

No `scripts/*/tests/probe-*.sh` exist and no PLAN or SUMMARY declares a shell probe. Step 7c is
**N/A**; the behavioral spot-checks above are the verifier-run evidence in its place.

### Requirements Coverage

All 21 IDs are claimed by a plan; the union of the five `requirements:` fields exactly equals the
ROADMAP list. **No orphaned requirements.**

| Requirement | Plan | Status | Evidence |
|---|---|---|---|
| PORT-01 | 03-03 | SATISFIED | All 7 position fields + 3 top-level keys |
| PORT-02 | 03-01 | SATISFIED | 10000 -> 8090.0 at fill 191.00 |
| PORT-03 | 03-02 | SATISFIED | Sell settlement tests pass |
| PORT-04 | 03-02 | SATISFIED | `need $1910000.00, have $8020.00` |
| PORT-05 | 03-02 | SATISFIED | 400; no negative/zero row reachable |
| PORT-06 | 03-02 | SATISFIED | 0, -1, NaN, Infinity, 1e400, 0.00001 all 400 |
| **PORT-07** | 03-01 | **BLOCKED** | **G-01 - unreachable in production; the passing test is fixture-arranged** |
| PORT-08 | 03-02 | SATISFIED | 2.0s constant; both wait tests pass; wait measured at 2.08s |
| PORT-09 | 03-02 | SATISFIED | Row deleted at zero (probe) |
| PORT-10 | 03-01 | SATISFIED | Probe + route test |
| PORT-11 | 03-01 | SATISFIED | In-transaction `insert_snapshot`; `+1` |
| PORT-12 | 03-05 | SATISFIED | Loop recurrence, skip and cancel probed directly. (G-03 is a teardown defect, not a recorder defect) |
| PORT-13 | 03-03 | SATISFIED | Bounds 422/200/422; echo round-trip |
| PORT-14 | 03-03 | SATISFIED | Starting state restored and persisted. *Narrow-reading confirmation is a human item* |
| WATCH-01 | 03-04 | SATISFIED | 60 points, correct key set |
| WATCH-02 | 03-04 | SATISFIED | `ibm` -> `IBM`; `TOOLONG` -> 400 |
| **WATCH-03** | 03-04 | **SATISFIED in-session / DEGRADED across restart** | Registration works live (probe). G-02: not re-established at boot |
| WATCH-04 | 03-04 | SATISFIED | 204, empty body |
| WATCH-05 | 03-04 | SATISFIED | 409 with a readable sentence |
| WATCH-06 | 03-04 | SATISFIED | Valid-shaped `ZZZ` -> 404 |
| **TEST-02** | 03-02 | **SATISFIED with a reservation** | Every rejection path is covered and each asserts its own message. But the suite's `cache` fixture arranges away PORT-07, so coverage of the *execution* path has a demonstrated blind spot |

### Prohibitions (11 - all judgment-tier, NON-AUTHORITATIVE)

Autonomous run: LLM-judge verdicts, each flagged `unverified-prohibition - human review recommended`.

| # | Req | Prohibition (abbreviated) | Verdict | Basis |
|---|---|---|---|---|
| 1 | PORT-02 | No trade/watchlist rule enforced only at the HTTP boundary | HONORED (flagged) | `api/models.py` has zero constraints; routers hold no validation and no `sqlite3` |
| 2 | PORT-05 | An uncoverable sell must be a refusal - no negative, placeholder or implicit borrow | HONORED (flagged) | `trading.py:167` raises pre-write; only `delete_position` or `upsert_position(remaining>0)` can run |
| 3 | PORT-06 | No second, looser entry point for quantities | HONORED (flagged) | Grep: exactly one call site, `trading.py:101` |
| 4 | PORT-04 | No unactionable rejection message | HONORED (flagged) | Both refusals carry concrete figures |
| 5 | PORT-14 | Reset must not touch anything outside positions + cash | HONORED (flagged) | Probe: watchlist and trades counts unchanged |
| 6 | PORT-14 | Reset unreachable by navigation/prefetch/crawler | HONORED (flagged) | OpenAPI `post` only; GET -> 405 |
| 7 | PORT-01 | No fabricated number for a missing price | HONORED (flagged) | `portfolio.py:56-68` returns nulls and skips the total |
| 8 | WATCH-05 | No watchlist rule enforced only at the HTTP boundary | HONORED (flagged) | All three raises in `services/watchlist.py` |
| 9 | WATCH-05 | Held-check must not read outside the delete's transaction | HONORED (flagged) | One `writing()` block; concurrency test passes |
| 10 | WATCH-01 | Never omit a watched ticker, never substitute a fabricated price | HONORED (flagged) | `AMZN` present with nulls. **Note:** G-02 means a restarted app shows *every* user-added ticker this way - honest, but the honesty is masking a broken feed |
| 11 | PORT-12 | Skip must not widen; loop must not swallow its failure; must not record a total never held | HONORED (flagged) | Exact `round_money` equality, no tolerance band; **zero** `except Exception` anywhere in `app/services/` or `app/api/`; read-compare-write in one `writing()` block. G-03 does not violate this - it is the consequence of correctly obeying it |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `app/main.py` | 62 | bare `pass` | Info | Inside `except asyncio.CancelledError` at teardown - idiomatic, though G-03 shows the surrounding block is too narrow |
| `tests/services/test_trading.py` | 33-38 | Fixture pre-seeds the cache with the "unwatched" ticker | **Blocker** | Arranges away the exact production condition PORT-07 describes; the requirement's assertion passes against an unreachable state |

Scanned every file in the phase diff for `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, `PLACEHOLDER`,
"not yet implemented", "coming soon", empty returns and hardcoded empty collections reaching a
response. **Zero debt markers** - the debt-marker gate does not fire. `ruff` clean.

### Verification of the Two Recorded Executor Deviations

**1. 03-02's unsatisfiable acceptance criterion (rewritten test).** CONFIRMED SOUND.
`app/market/cache.py:46` runs `price = round(price, 2)` inside `PriceCache.update`, upstream of and
frozen relative to this phase, so a sub-cent price provably cannot reach the trade seam and the
criterion as literally written was unsatisfiable. The substitute
(`test_the_fill_after_the_wait_is_the_cache_float_untouched`) pins what the criterion protected:
`fill_price == cached` and `total_cost != round(total_cost, 2)`. A stray `round_money` in the
service would fail both. The substitution narrows nothing this phase owns.

**2. 03-05's accepted risk T-03-55 (unbounded `portfolio_snapshots`).** CONFIRMED REAL AND BOUNDED.
No retention logic exists, so growth is genuine; read exposure is capped by `HISTORY_MAX_LIMIT =
5000` at `api/portfolio.py:18`, enforced as a probe-confirmed 422. Storage-only degradation,
correctly dispositioned `accept`.

### Regression Check Against Prior Phases

- Frozen modules untouched (empty diff for `app/db` and `app/market`).
- Full 351-test suite passes, including all Phase 1 `tests/db/`, `tests/market/` and the Phase 2
  spine tests (`test_spine_end_to_end`, `test_api_not_shadowed`, `test_concurrent_health_and_stream`).
- Phase 2's mount-order guarantee still holds with four routers registered.
- Both known flaky tests passed on this run.
- **No regression introduced.** G-02's root line is inherited from Phase 1, but it became a defect
  only once Phase 3 added user-added tickers and positions.

### Human Verification Required

Deferred until the gaps are closed, but recorded now so they are not lost.

1. **Live-price drift of derived figures** (carried from 03-03, D6). Hold a position against the
   streaming simulator and confirm `total_value` and `unrealized_pnl` move with the feed and
   reconcile as `cash + sum(quantity * live price)`. The suite drives a fixed fake cache, so drift
   is only observable against a running container.
2. **Confirm PORT-14's narrow "starting state" reading** (carried from 03-03, D7). Reset preserving
   the watchlist and the trades audit log is product intent, not a code property. The code
   demonstrably implements the narrow reading.
3. **Review the 11 judgment-tier prohibitions** above; those verdicts are non-authoritative by
   design.

### Gaps Summary

Phase 3 is well-built - clean layering, a faithfully honored seam contract, disciplined precision
rules, genuinely thorough tests, no debt markers, and 69 of 72 must-haves verified. Three gaps
block the goal, and they share one theme: **nothing in the system reconciles the market data
source's ticker set with the tickers the user actually cares about.**

- **G-01** - the trade path can add a watchlist row but can never establish a feed, so PORT-07 and
  ROADMAP SC2 fail for the case they name. The suite reports this as passing because the fixture
  supplies the missing step.
- **G-02** - boot starts the feed from a constant instead of the persisted watchlist, so a restart
  strands user-added positions: null-valued, unsellable, un-removable.
- **G-03** - a dead snapshot task blocks `source.stop()`, so the market source can outlive the app.

G-01 and G-02 are the same missing seam seen from two directions, and they should be planned
together. Doing so requires a decision on `03-SEAM-CONTRACT.md`, since `execute_trade` deliberately
holds no `MarketDataSource`. That is a contract question for the developer, not something to patch
silently.

Recommended: `/gsd-plan-phase --gaps`. The structured gaps are in this file's frontmatter.

---

_Verified: 2026-08-13T22:45:00Z_
_Verifier: Claude (gsd-verifier)_
