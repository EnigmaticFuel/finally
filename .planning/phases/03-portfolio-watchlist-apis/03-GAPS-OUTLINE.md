---
phase: 03-portfolio-watchlist-apis
mode: gap_closure
outline_for: plans 03-06 onward
generated: 2026-08-14
fixed_plans: [03-01, 03-02, 03-03, 03-04, 03-05]
findings_total: 12
plans_new: 4
waves: 2
---

# Phase 03 Gap-Closure Plan Outline

Plans 03-01..03-05 are executed, committed and FIXED. This outline covers only the new
gap-closing plans, 03-06 through 03-09.

**Frozen modules:** `backend/app/market/` and `backend/app/db/` appear in no plan's file list.
Both are read from and called into (`run_db`, `get_watchlist`, `MarketDataSource.add_ticker`,
`normalize_ticker`, `wait_for_price`) but never modified.

**Wave rule honored:** every plan in wave 2 has a `Files Modified` set disjoint from every other
wave-2 plan, so 03-07, 03-08 and 03-09 execute in parallel safely. 03-06 runs alone in wave 1
because it is the only plan that may change the `execute_trade` signature and the lifespan's
ticker source, and every wave-2 plan edits a file it touches.

## Plan Table

| Plan ID | Objective | Wave | Depends On | Requirements | Findings Closed | Files Modified |
|---|---|---|---|---|---|---|
| 03-06 | Reconcile the market data source's ticker set with the tickers the user cares about: register a traded symbol with the feed inside `execute_trade` (amended seam), and start the feed from the persisted watchlist at boot. Prove both with production-shaped tests that use no cache pre-seeding. | 1 | [] | PORT-01, PORT-07, PORT-08, WATCH-01, WATCH-03, TEST-02 | G-01, G-02, IN-01 | `backend/app/services/trading.py`, `backend/app/services/watchlist.py`, `backend/app/services/__init__.py`, `backend/app/api/portfolio.py`, `backend/app/api/__init__.py`, `backend/app/main.py`, `backend/tests/services/test_trading.py`, `backend/tests/services/test_watchlist.py`, `backend/tests/services/test_snapshots.py`, `backend/tests/test_main.py`, `backend/tests/test_feed_reconciliation.py` (new) |
| 03-07 | Make lifespan teardown exception-safe so a dead snapshot task cannot leave the market source and its `simulator-loop` running after shutdown — without swallowing, retrying or downgrading the snapshot failure. | 2 | [03-06] | PORT-12 | G-03 | `backend/app/main.py`, `backend/tests/test_main.py` |
| 03-08 | Stop the blanket `ValueError` handler turning server bugs into 400s, and correct four trade-path defects: the snapshot's price, the reported cash balance, the sufficiency comparison, and the share-count message format. | 2 | [03-06] | PORT-02, PORT-04, PORT-05, PORT-10, PORT-11, WATCH-02, TEST-02 | WR-01, WR-03, IN-02, IN-03, IN-04 | `backend/app/services/trading.py`, `backend/app/services/watchlist.py`, `backend/app/api/errors.py`, `backend/tests/services/test_trading.py`, `backend/tests/services/test_watchlist.py`, `backend/tests/api/test_errors.py` (new) |
| 03-09 | Close the cross-site-forgeable reset endpoint, make the reset response report the state it actually wrote, and stop `unrealized_pnl_percent` dividing by an unguarded cost basis. | 2 | [03-06] | PORT-01, PORT-14 | WR-02, WR-04, IN-05 | `backend/app/services/portfolio.py`, `backend/app/api/portfolio.py`, `backend/app/api/models.py`, `backend/tests/services/test_portfolio.py`, `backend/tests/api/test_portfolio.py` |

### Findings coverage checksum

| Finding | Plan |
|---|---|
| G-01 | 03-06 |
| G-02 | 03-06 |
| G-03 | 03-07 |
| WR-01 | 03-08 |
| WR-02 | 03-09 |
| WR-03 | 03-08 |
| WR-04 | 03-09 |
| IN-01 | 03-06 |
| IN-02 | 03-08 |
| IN-03 | 03-08 |
| IN-04 | 03-08 |
| IN-05 | 03-09 |

Twelve findings, twelve rows, each appearing exactly once. No deferrals (D-G02).

### Wave-2 disjointness proof

| File | 03-07 | 03-08 | 03-09 |
|---|---|---|---|
| `backend/app/main.py` | X | | |
| `backend/tests/test_main.py` | X | | |
| `backend/app/services/trading.py` | | X | |
| `backend/app/services/watchlist.py` | | X | |
| `backend/app/api/errors.py` | | X | |
| `backend/tests/services/test_trading.py` | | X | |
| `backend/tests/services/test_watchlist.py` | | X | |
| `backend/tests/api/test_errors.py` | | X | |
| `backend/app/services/portfolio.py` | | | X |
| `backend/app/api/portfolio.py` | | | X |
| `backend/app/api/models.py` | | | X |
| `backend/tests/services/test_portfolio.py` | | | X |
| `backend/tests/api/test_portfolio.py` | | | X |

No file has two marks. 03-06 (wave 1) overlaps all three, which is why it is alone in its wave.

---

## 03-06 — Feed reconciliation: the missing seam, both directions

**Findings:** G-01, G-02, IN-01. **Wave 1, no dependencies.**

Amend `execute_trade` to the shape the developer locked in `03-SEAM-CONTRACT.md`'s Amendment
section — `execute_trade(db_path, cache, source, ticker, side, quantity) -> TradeResult` — and
call `await source.add_ticker(ticker)` after `normalize_ticker`, the side check and
`validate_quantity`, but *before* `wait_for_price` at `trading.py:103`, so a symbol the market
source has never been told about actually gets a feed and can produce a first tick inside
`PRICE_WAIT_SECONDS`. `add_ticker` is documented as a no-op when already tracked
(`app/market/interface.py:40-41`), so the cheap-checks-first ordering that keeps a malformed
quantity from waiting two seconds is preserved and no already-watched ticker pays a cost. Every
call site moves with the signature: `create_portfolio_router(price_cache, source)` in
`api/portfolio.py:29` (mirroring `create_watchlist_router(price_cache, source)` at
`api/watchlist.py:17`), `main.py:72`, roughly 28 `execute_trade(...)` calls in
`tests/services/test_trading.py`, and `tests/services/test_snapshots.py:238`.

The `cache` fixture at `tests/services/test_trading.py:33-38` calls
`price_cache.update(UNWATCHED, FILL_PRICE)` — the exact registration step production omits — and
is what makes `test_buy_fills_and_lands_everywhere` green against an unreachable arrangement.
Retire or rename it so that no test claiming PORT-07 pre-seeds the cache; the pre-seeded fixture
may remain only for tests about arithmetic, never for the auto-add assertion.

For G-02, add `startup_tickers(db_path) -> list[str]` to `app/services/watchlist.py`: read the
persisted rows with `run_db(db_path, get_watchlist)` (calling the frozen query layer, not
modifying it — `run_db` also runs `ensure_initialized`, so a first launch seeds the ten defaults
and reads them straight back) and fall back to `list(DEFAULT_TICKERS)` only when the table is
genuinely empty. `main.py:55` then starts the source from that list instead of
`list(DEFAULT_TICKERS)`. Export the new symbol in `services/__init__.py`'s docstring list and
`__all__`, which the phase verifier checks. Only after the behavior matches, correct the two false
docstrings at `services/watchlist.py:110-113` and `:135-137` that assert "the source is started
from the watchlist rows on every boot" — the D-08 409 rule and the D-09 self-healing rationale
both rest on them.

`tests/test_main.py:111` currently asserts `source.get_tickers() == list(DEFAULT_TICKERS)`;
`get_watchlist` orders ascending by ticker while `DEFAULT_TICKERS` is in seed order, so that
expectation becomes `sorted(DEFAULT_TICKERS)`. Two new tests go in a new file
`backend/tests/test_feed_reconciliation.py`, both driving the real lifespan and the real
`SimulatorDataSource` with zero `price_cache.update(...)` anywhere: (a) trade a ticker the source
has never seen and assert 200 plus the symbol present in `GET /api/watchlist` — today this returns
`400 {"detail": "No price available for PYPL yet, please try again"}` after ~2.08s and the ticker
is absent; (b) restart-shaped — add a ticker, take a position, exit the lifespan, build a second
app against the same `db_path`, and assert the ticker prices and the position values — today
`current_price` is `None`, the holding is excluded from `total_value`, and it is both unsellable
(400) and un-removable (409). IN-01 rides along as a one-line addition of
`from __future__ import annotations` as the first import in `services/__init__.py:36` and
`api/__init__.py:10`, the only two package modules missing it.

## 03-07 — Lifespan teardown survives a dead snapshot task

**Findings:** G-03. **Wave 2, depends on 03-06.**

Per D-G04 the snapshot loop dying loudly is correct and mandated by PORT-12's raise-don't-swallow
prohibition; the only defect is that its corpse blocks the rest of teardown. In `main.py`, wrap the
`yield` so that `task.cancel()`, awaiting the task, and `await source.stop()` all run regardless of
how `snapshot_loop` ended — today `task.cancel()` is a no-op on an already-failed task, `await
task` re-raises a non-`CancelledError` out of the `except asyncio.CancelledError` at lines 58-62,
and line 63 never executes. Do not add a retry, a swallow, or a downgrade of the snapshot failure;
surface it instead (a done-callback logging at `error` level with `%s`-style lazy formatting and no
emojis) so a flat P&L chart is not mistaken for an idle portfolio, and update the lifespan docstring
whose "nothing outlives the app" guarantee is currently false on this path.

The new test lives in `tests/test_main.py`: force the snapshot loop to fail with something other
than `CancelledError` (patching `record_snapshot` to raise, as the verifier's probe did), run the
lifespan to completion, and assert both that `simulator-loop` is no longer in
`asyncio.all_tasks()` names — i.e. `source.stop()` ran — and that the failure was reported rather
than swallowed. Against today's code the lifespan raises `RuntimeError` out of `__aexit__` and
`simulator-loop` is still alive, so the test fails on both assertions.

## 03-08 — Error taxonomy at the seams, and four trade-path corrections

**Findings:** WR-01, WR-03, IN-02, IN-03, IN-04. **Wave 2, depends on 03-06.**

WR-01 is the shaping change: `api/errors.py:40` registers a handler for bare `ValueError`, so every
`ValueError` raised anywhere in a request becomes a 400 echoing `str(exc)` to the user — including
`pydantic_core.ValidationError`, which subclasses `ValueError` and is raised by the
`PortfolioResponse(**payload)` / `HistoryResponse(...)` constructions inside the handlers, leaking
model names, field paths, offending values and an `errors.pydantic.dev` URL into a field the
contract says is shown verbatim. Convert the two known plain-`ValueError` sources into the taxonomy
at the seam — `normalize_ticker` and `wait_for_price` in `trading.py`, and `normalize_ticker` in
`watchlist.add` / `watchlist.remove` — raising `TradeError` (400) with the same message text, then
delete the blanket row. Status codes and user-visible messages are unchanged; what changes is that
an unexpected `ValueError` becomes a 500 with a traceback in the log, which is what it is. This is
translation at a boundary, not speculative defense.

The four narrow corrections all live in `trading.py`. WR-03: `prices` is built from a second,
independent `cache.get_all()` read at line 104, so the trade-time snapshot can value the traded
ticker at a price the trade did not execute at — set `prices[ticker] = fill_price` after the map is
built so the module docstring's claim holds. IN-02: `_apply_trade` returns the unrounded `new_cash`
while `update_cash_balance` stores `round_money(new_cash)`, so `POST /api/portfolio/trade` and the
`GET /api/portfolio` right after it disagree in the last digits — return the rounded, stored value.
IN-03: `if round_money(cost) > round_money(cash)` at line 154 compares at cents while
`new_cash = cash - cost` subtracts at full precision, letting a sub-half-cent overdraft store
`-0.0`; compare on the value actually stored instead. IN-04: `f"{quantity:g}"` / `f"{held:g}"` at
line 168 switches to exponent form below 1e-4, so a fractional holding renders as "have 1e-05
AAPL" in a user-facing message — use fixed 4dp matching the stored precision with trailing zeros
stripped.

New file `backend/tests/api/test_errors.py` asserts a route raising a bare `ValueError` returns 500
rather than 400 (`TestClient(app, raise_server_exceptions=False)`) and that an invalid ticker still
returns 400 with its readable message. Against today's code the first assertion fails: the blanket
handler returns 400. The four corrections each get an assertion in
`tests/services/test_trading.py`, each of which fails today: the snapshot value diverging from
`fill_price` when the cache moves between the two reads; `TradeResult.cash_balance !=` the stored
balance for a fill like 3 @ 190.52; a cost exceeding cash by 0.004 being accepted; and
`1e-05` appearing in the insufficient-shares message.

## 03-09 — Reset hardening and honest valuation

**Findings:** WR-02, WR-04, IN-05. **Wave 2, depends on 03-06.**

WR-02 is a threat-model item, not a cleanup: `POST /api/portfolio/reset` takes no body, no header
and no token, and the app has no auth, no CORS config and no origin check, so a cross-origin HTML
form POST — a "simple request" that fires no preflight — lands the side effect from any tab the
user has open. `GET` is already refused with 405, which closes prefetch and navigation but not this
vector. Add `ResetRequest` with a required `confirm: bool` to `api/models.py` and require it on the
route, which forces `Content-Type: application/json` and therefore a preflight a form cannot send.
This does not contradict D-13 (no confirmation *UX* in the API) — it is transport hardening, and
the Phase 4 UI supplies the field without asking the user anything. Note this is the one place in
these four plans where a Pydantic model is doing work beyond shape declaration; the model still
carries no business rule, so `api/models.py`'s "shape only, no constraints" docstring stays true.

WR-04: `reset_portfolio` at `services/portfolio.py:178-179` asserts its response
(`{"cash_balance": STARTING_CASH, "total_value": STARTING_CASH, "positions": []}`) rather than
reading back what it wrote, and every reset test asserts against the same constant, so any future
change to `_apply_reset` would make the endpoint lie with no test failing. Change the signature to
`reset_portfolio(db_path, cache)` and return `await get_portfolio(db_path, cache)`, so there is one
definition of what a portfolio response is; `api/portfolio.py:107` already has `price_cache` in
scope. Update the `_apply_reset` docstring paragraph that justifies taking no cache, which stops
being true. IN-05: `(market_value - cost_basis) / cost_basis * 100` at `services/portfolio.py:80`
has no zero guard, and the blast radius is the entire `GET /api/portfolio` read plus every snapshot
— return `None` for `unrealized_pnl_percent` when `cost_basis` is zero, reusing the existing null
rule rather than inventing a special case (`PositionOut.unrealized_pnl_percent` is already
`float | None`).

Tests: `tests/api/test_portfolio.py`'s four reset tests gain the required body, plus a new one
asserting a form-encoded `POST /api/portfolio/reset` with no JSON body is rejected (422) and leaves
cash and positions untouched — today it succeeds and wipes the portfolio.
`tests/services/test_portfolio.py`'s reset tests move to the two-argument signature and gain one
asserting the returned body equals a fresh `get_portfolio` read after a concurrent write, plus a
`value_portfolio` case with `avg_cost = 0.0` that today raises `ZeroDivisionError`.

## OUTLINE COMPLETE
