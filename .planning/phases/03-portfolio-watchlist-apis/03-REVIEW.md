---
phase: 03-portfolio-watchlist-apis
reviewed: 2026-08-13T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - backend/app/api/__init__.py
  - backend/app/api/errors.py
  - backend/app/api/models.py
  - backend/app/api/portfolio.py
  - backend/app/api/watchlist.py
  - backend/app/main.py
  - backend/app/services/__init__.py
  - backend/app/services/errors.py
  - backend/app/services/portfolio.py
  - backend/app/services/snapshots.py
  - backend/app/services/trading.py
  - backend/app/services/watchlist.py
findings:
  critical: 3
  warning: 4
  info: 5
  total: 12
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-08-13
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

The service seam is well-shaped and the transaction discipline is real: `_apply_trade`,
`_apply_reset`, `_add_row`, `_remove_checked` and `_record_if_changed` each open exactly one
`writing()` block, all validation raises the taxonomy rather than an `HTTPException`, every
ticker goes through `normalize_ticker`, every SQL value is bound, and the mount order in
`create_app()` is correct (routers at `main.py:71-74`, `app.frontend()` at `main.py:75`). The
money precision rule is followed — `round_money` appears only inside the sufficiency comparison
and the snapshot skip comparison, never on a stored or returned derived value.

Three defects break stated invariants, and they compound with each other:

1. The market source is started from a hardcoded ten-ticker constant rather than from the
   persisted watchlist, so any ticker the user adds silently loses its price feed on restart.
2. `execute_trade` never registers a symbol with the market source, so "trading a ticker not on
   the watchlist adds it to the watchlist" cannot actually fill — the PORT-07 test that claims to
   prove it only passes because the fixture pre-loads the cache by hand.
3. A transient `database is locked` — proven reachable below — permanently kills the snapshot
   recorder and then makes `source.stop()` unreachable on shutdown.

Findings 1 and 2 together mean a symbol outside `DEFAULT_TICKERS` is a second-class citizen for
its whole life: it can be watched but not priced after restart, and it can be priced only if it
was added through `POST /api/watchlist` in this same process.

## Critical Issues

### CR-01: User-added watchlist tickers lose their price feed on every restart

**File:** `backend/app/main.py:55`

**Issue:** The lifespan starts the market source from `DEFAULT_TICKERS`:

```python
await source.start(list(DEFAULT_TICKERS))
```

The watchlist is durable database state in a bind-mounted SQLite file; `DEFAULT_TICKERS` is a
compile-time constant in `app/db/seed.py`. `source.add_ticker` is called from exactly one place in
the whole application (`app/services/watchlist.py:117`, grep-confirmed), and that only runs on a
live `POST /api/watchlist`. Nothing reads the watchlist rows at boot.

Failure scenario, entirely within normal use:

1. User adds PYPL via `POST /api/watchlist` — row written, simulator registers it, prices flow.
2. User buys 10 PYPL — position written.
3. Container restarts (the bind mount is the whole point of `db/`).
4. `source.start([AAPL...NFLX])`. PYPL is on the watchlist and in `positions`, but is not in the
   simulator and never will be.

Consequences after step 4, all permanent:
- `GET /api/watchlist` returns PYPL with `price`, `open_price`, `change_from_open_percent` null
  and `history: []` forever — the D-15 null branch used as a permanent state rather than a
  transient one.
- `GET /api/portfolio` reports the PYPL position with null `current_price`/`market_value` and
  **excludes it from `total_value`** (`app/services/portfolio.py:56-68,83`), so the user's reported
  net worth silently drops by the value of that holding.
- The position cannot be sold: `execute_trade` calls `wait_for_price` (`trading.py:103`), which
  polls a cache nothing will ever write, so every sell returns 400 after a 2s wait. The user is
  stuck holding an unsellable, unvalued position.
- Removing PYPL from the watchlist to clean up is refused with 409 (`watchlist.py:159`), because a
  position is held. There is no exit from this state through the API.

This also falsifies the rationale documented at `app/services/watchlist.py:108-113`, which states
that "the source is started from it on every boot, so a failed registration self-heals on the next
start". That property is asserted in a docstring and not implemented anywhere.

**Fix:** start the source from the union of the persisted watchlist and the seed constant, so the
docstring's claim becomes true:

```python
# app/main.py
from app.db.connection import run_db
from app.db.queries import get_watchlist

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    rows = await run_db(app.state.db_path, get_watchlist)
    tickers = [row["ticker"] for row in rows] or list(DEFAULT_TICKERS)
    await source.start(tickers)
    ...
```

`run_db` calls `ensure_initialized`, so a first launch seeds the ten defaults and this reads them
back; the `or` branch is only reached if a user has emptied the watchlist entirely.

---

### CR-02: Trading a ticker that is not on the watchlist can never fill

**File:** `backend/app/services/trading.py:103` (and `backend/app/api/portfolio.py:48`)

**Issue:** PLAN.md section 8 states: *"Trading a ticker that is not on the watchlist adds it to the
watchlist as part of the trade. This holds the invariant that every position has a live price
feed."* The implementation adds the **database row** (`trading.py:144`) but never registers the
symbol with the **market source**, and the price wait runs *before* the transaction:

```python
fill_price = await wait_for_price(cache, ticker, timeout=PRICE_WAIT_SECONDS)   # line 103
...
filled = await run_db(db_path, _apply_trade, ...)                              # line 106
```

`wait_for_price` (`app/market/cache.py:145-158`) only polls the cache; it does not create a feed.
A symbol that has never been registered with the source has no cache entry and never will get one,
so the wait always exhausts its 2 seconds and raises `ValueError` -> 400 *"No price available for
PYPL yet, please try again"*. Retrying gives the identical result forever. `_apply_trade` — and
therefore the `add_watchlist_ticker` call that is supposed to satisfy PORT-07 — is never reached.

The auto-add path is only reachable in one narrow case: a ticker that was registered with the
source earlier in this same process and then removed from the watchlist (D-08 deliberately leaves
the feed running). For the case the requirement is actually about — a fresh symbol — the endpoint
400s.

**Why the green test does not cover this.** `tests/services/test_trading.py:34-37`:

```python
@pytest.fixture
def cache() -> PriceCache:
    price_cache = PriceCache()
    price_cache.update(UNWATCHED, FILL_PRICE)   # PYPL, hand-injected
    return price_cache
```

The fixture performs by hand the exact step production is missing. `03-01-SUMMARY.md:212-217`
claims PORT-07 is "proven in behavior rather than assumed" — it is proven against an arranged
cache, not against a running market source. No API-level or lifespan-level test buys an unwatched
symbol end to end.

**Fix:** make the trade register the feed before waiting on it. This collides with the locked seam
signature in `03-SEAM-CONTRACT.md`, which omits `source` from `execute_trade` — the collision
should be raised with the developer rather than worked around, because the contract as written
makes the requirement unimplementable inside the seam. Two options:

```python
# Option A - amend the seam (preferred; keeps one rule for both callers, incl. Phase 6)
async def execute_trade(
    db_path: Path, cache: PriceCache, source: MarketDataSource,
    ticker: str, side: str, quantity: float,
) -> TradeResult:
    ticker = normalize_ticker(ticker)
    ...
    await source.add_ticker(ticker)          # idempotent; seeds the cache for the simulator
    fill_price = await wait_for_price(cache, ticker, timeout=PRICE_WAIT_SECONDS)
```

```python
# Option B - keep the seam, move the registration into both call sites
# app/api/portfolio.py and, in Phase 6, the LLM path:
await watchlist_service.add(db_path, source, body.ticker)
result = await execute_trade(db_path, price_cache, body.ticker, body.side, body.quantity)
```

Option B duplicates the rule at every call site, which is exactly what the seam exists to prevent,
and it commits the watchlist row before the trade is validated — so a rejected trade would leave a
watchlist row behind, breaking `test_rejected_buy_rolls_the_whole_unit_back`. Option A is the one
that keeps both invariants.

Whichever is chosen, add a test that drives a real `SimulatorDataSource` (or the app lifespan)
rather than a hand-seeded `PriceCache`.

---

### CR-03: A transient lock permanently stops the snapshot recorder and skips `source.stop()`

**File:** `backend/app/main.py:56-63`, `backend/app/services/snapshots.py:96-99`

**Issue:** `snapshot_loop` catches nothing, by design, and the lifespan catches only
`CancelledError`:

```python
task = asyncio.create_task(snapshot_loop(app.state.db_path, cache), name="snapshot-loop")
yield
task.cancel()
try:
    await task
except asyncio.CancelledError:
    pass
await source.stop()
```

If `record_snapshot` raises anything other than `CancelledError`, two things happen:

1. **The recorder dies silently and permanently.** The task ends, no handler logs it, `/api/health`
   does not report it, and no snapshot is written for the remaining life of the process. The P&L
   chart flatlines from that moment, which renders as an idle portfolio rather than a broken
   recorder — precisely the failure mode the module docstring at `snapshots.py:15-18` says it is
   avoiding.
2. **Shutdown breaks.** `task.cancel()` on an already-finished task is a no-op, `await task`
   re-raises the stored exception out of the `except CancelledError` block, and `await
   source.stop()` at line 63 never runs. The market source's `simulator-loop` task is left running
   and lifespan shutdown fails.

This is reachable, not theoretical. `sqlite3.OperationalError('database is locked')` propagates
straight out of `run_db` when `BEGIN IMMEDIATE` cannot acquire the write lock within
`BUSY_TIMEOUT_MS`. Measured on this machine:

```
BEGIN IMMEDIATE FAILED: database is locked after 5.516s   # busy_timeout=5000, one competing writer
```

Phase 3 is what makes this matter: before this phase there was no unconditional background writer.
The 30s loop now contends with every `execute_trade`, every `reset_portfolio` and every
`POST /api/watchlist`, which is consistent with the intermittent
`tests/db/test_concurrency.py::TestMixedWrites` failure noted in the phase brief. The loop dying
is a strictly worse outcome than the flaky test.

**Fix:** make shutdown exception-safe and make the loop's death observable. This is not defensive
programming — it is closing a resource-leak path and an unobservable-failure path:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await source.start(tickers)
    task = asyncio.create_task(snapshot_loop(app.state.db_path, cache), name="snapshot-loop")
    task.add_done_callback(_log_if_failed)
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await source.stop()


def _log_if_failed(task: asyncio.Task[None]) -> None:
    """Surface a snapshot loop that died, so a flat chart is not mistaken for an idle one."""
    if not task.cancelled() and task.exception() is not None:
        logger.error("Snapshot loop stopped: %s", task.exception())
```

Separately, consider whether a transient lock should end the loop at all: the loop runs again in
30 seconds, so skipping one tick is the honest recovery. If that is wanted, catch
`sqlite3.OperationalError` in `snapshot_loop` only (not in `record_snapshot`, which tests call
directly) and log at `warning`.

## Warnings

### WR-01: The blanket `ValueError` handler turns server bugs into 400s and leaks internals

**File:** `backend/app/api/errors.py:40`

**Issue:**

```python
app.add_exception_handler(ValueError, lambda request, exc: _detail(exc, 400))
```

The docstring justifies this row by `normalize_ticker` and `wait_for_price` raising plain
`ValueError`. But it catches *every* `ValueError` raised anywhere in a request, and echoes
`str(exc)` to the client as a user-facing message. Two consequences:

- **Server defects are reported as client errors.** Any `ValueError` from a genuine bug —
  bad `float()` conversion, a malformed value from the database, an arithmetic helper — returns
  400 with an internal message instead of 500. The frontend shows "your input was invalid", the
  user retries the same valid input, and nothing in the logs or status codes indicates a server
  fault.
- **Pydantic validation errors leak.** `pydantic_core.ValidationError` subclasses `ValueError`.
  `PortfolioResponse(**payload)` (`api/portfolio.py:71,108`) and `HistoryResponse(...)`
  (`api/portfolio.py:91`) are constructed *inside* the handler, before FastAPI's own response
  validation, so a shape mismatch produces a 400 whose `detail` is the full pydantic dump — model
  class name, field paths, the offending input values, and a `https://errors.pydantic.dev/...`
  URL. That is not a message written to be shown to the user verbatim, which is the stated
  contract for this envelope.

**Fix:** convert the two known plain-`ValueError` sources into the taxonomy at the seam and drop
the blanket row, so `ValueError` means "bug" again:

```python
# app/services/trading.py
try:
    ticker = normalize_ticker(ticker)
    ...
    fill_price = await wait_for_price(cache, ticker, timeout=PRICE_WAIT_SECONDS)
except ValueError as exc:
    raise TradeError(str(exc)) from exc
```

Apply the same at `watchlist.add`/`watchlist.remove` around `normalize_ticker`, then delete
`api/errors.py:40`. The user-facing messages are unchanged and the status codes are unchanged;
what changes is that an unexpected `ValueError` becomes a 500 with a traceback in the log, which is
what it is.

---

### WR-02: `POST /api/portfolio/reset` is cross-site forgeable

**File:** `backend/app/api/portfolio.py:93-108`

**Issue:** The route takes no body, no header and no token. The application has no auth, no CORS
configuration and no origin check. Any page the user visits while the container is running can
therefore wipe their portfolio:

```html
<form action="http://localhost:8000/api/portfolio/reset" method="POST"><script>...submit()</script></form>
```

A cross-origin form POST is a "simple request": no preflight fires, the browser sends it, and the
side effect lands. The attacker cannot read the response, but does not need to. `GET` is correctly
rejected (`test_a_get_does_not_reset_anything`), which closes prefetch and navigation — the exact
vectors the route docstring at lines 99-102 reasons about — but not this one.

`POST /api/portfolio/trade` and `POST /api/watchlist` are not exposed the same way: they require a
JSON body, and a form-encoded or `text/plain` body fails model validation.

Impact is bounded — simulated money, single local operator, and `trades` survives so the state is
reconstructible (D-10) — which is why this is a Warning and not a Critical. It is still a
destructive unauthenticated endpoint reachable from any tab.

**Fix:** require something a cross-origin form cannot send. The cheapest option that costs the UI
one line is a required JSON body, which forces `Content-Type: application/json` and therefore a
preflight:

```python
class ResetRequest(BaseModel):
    """POST /api/portfolio/reset body. Required so the route is not form-forgeable."""

    confirm: bool


@router.post("/portfolio/reset", response_model=PortfolioResponse)
async def reset(body: ResetRequest, db_path: Annotated[Path, Depends(get_db_path)]) -> ...:
```

This does not contradict D-13 (no *confirmation UX* in the API); it is transport hardening, and the
Phase 4 UI supplies the field without asking the user anything.

---

### WR-03: The trade-time snapshot does not use the price the trade filled at

**File:** `backend/app/services/trading.py:103-104`

**Issue:** The module docstring (lines 12-16) states the snapshot value "agree[s] with the fill
price the user was just quoted". It does not:

```python
fill_price = await wait_for_price(cache, ticker, timeout=PRICE_WAIT_SECONDS)   # read 1
prices = {symbol: update.price for symbol, update in cache.get_all().items()}  # read 2
```

Two independent reads of a cache the simulator rewrites every ~500ms. `prices[ticker]` can already
differ from `fill_price` by the time line 104 runs — and `wait_for_price` sleeps in 200ms
increments, so on a ticker that had no price yet the gap is larger. `_apply_trade` then values the
whole portfolio with `prices` (line 177), so the snapshot the P&L chart shows for this trade is
computed against a price the trade did not execute at.

The discrepancy is small in dollars but the invariant is stated and not held, and the next author
will trust the docstring.

**Fix:** overlay the fill on the price map so the traded ticker is valued at the price actually
paid:

```python
fill_price = await wait_for_price(cache, ticker, timeout=PRICE_WAIT_SECONDS)
prices = {symbol: update.price for symbol, update in cache.get_all().items()}
prices[ticker] = fill_price
```

---

### WR-04: `reset_portfolio` reports a hardcoded body instead of the state it wrote

**File:** `backend/app/services/portfolio.py:178-179`

**Issue:**

```python
await run_db(db_path, _apply_reset)
return {"cash_balance": STARTING_CASH, "total_value": STARTING_CASH, "positions": []}
```

The response is asserted rather than read. It is correct today only because `_apply_reset` happens
to write exactly `STARTING_CASH` and delete exactly every row. Any future change to the reset
transaction — a partial reset, a fee, a retained position — makes the endpoint lie without any test
failing, because every reset test asserts against the same constant. D-11 specifies the endpoint
returns "the same body as `GET /api/portfolio`"; this returns a body that resembles it.

It is also observably wrong under concurrency: a trade that commits between the reset transaction
and the return produces a response claiming zero positions when a position exists.

**Fix:** read back through the one shared path, so there is one definition of what the portfolio
response is:

```python
async def reset_portfolio(db_path: Path, cache: PriceCache) -> dict[str, object]:
    await run_db(db_path, _apply_reset)
    return await get_portfolio(db_path, cache)
```

The route already has `price_cache` in scope (`api/portfolio.py:29`). If adding the `cache`
parameter is unwanted, at minimum read cash and positions back from the database rather than
restating them.

## Info

### IN-01: Two package modules are missing `from __future__ import annotations`

**File:** `backend/app/services/__init__.py:36`, `backend/app/api/__init__.py:10`

**Issue:** Both files begin their imports without it. The convention in `.claude/CLAUDE.md` and
`03-CONTEXT.md` is unqualified: "`from __future__ import annotations` as the first import in every
module". Every other module in the phase complies. Harmless today (neither file has annotations),
but the rule exists so nobody has to check.

**Fix:** add the line above the relative imports in both files.

---

### IN-02: `TradeResponse.cash_balance` is the pre-storage value, not the stored one

**File:** `backend/app/services/trading.py:114`, `backend/app/services/trading.py:175`

**Issue:** `update_cash_balance` stores `round_money(new_cash)`, but `TradeResult.cash_balance`
carries the unrounded `new_cash`. A buy of 3 @ 190.52 yields `9428.439999999999` in the trade
response and `9428.44` in the database, so `POST /api/portfolio/trade` and the `GET /api/portfolio`
that immediately follows it disagree in the last digits. `cash_balance` is a stored value, not a
derived one, so the "derived figures stay full precision" rule does not apply to it. No
user-visible difference at 2dp formatting, and the drift does not accumulate because each trade
re-reads stored cash.

**Fix:** return `round_money(new_cash)` from `_apply_trade`, or read the balance back inside the
transaction after the write.

---

### IN-03: The cash sufficiency check permits a sub-half-cent overdraft

**File:** `backend/app/services/trading.py:154`

**Issue:** `if round_money(cost) > round_money(cash)` compares at cents while `new_cash = cash -
cost` subtracts at full precision. A cost exceeding cash by less than half a cent passes and
produces a negative `new_cash`, which `update_cash_balance` then stores as `-0.0`. JSON serializes
that as `-0.0`, so a client can render `$-0.00`. The no-margin invariant holds in substance —
the escape is bounded at 0.005 — but the negative-zero balance is reachable.

**Fix:** compare at full precision on the value that is actually stored, e.g. `if
round_money(cash - cost) < 0:`, which keeps one rounding rule and cannot produce a negative
stored balance.

---

### IN-04: The insufficient-shares message can emit scientific notation

**File:** `backend/app/services/trading.py:168`

**Issue:** `f"Insufficient shares: need {quantity:g} {ticker}, have {held:g}"`. The `g` format
switches to exponent form below 1e-4, so a fractional-share holding produces *"have 1e-05 AAPL"* in
a message the taxonomy contract says is shown to the user verbatim.

**Fix:** use a fixed 4dp format matching the stored precision and strip trailing zeros, e.g.
`f"{quantity:.4f}".rstrip('0').rstrip('.')`.

---

### IN-05: `unrealized_pnl_percent` divides by an unguarded cost basis

**File:** `backend/app/services/portfolio.py:80`

**Issue:** `(market_value - cost_basis) / cost_basis * 100` with `cost_basis = quantity *
avg_cost`. `avg_cost` is stored through `round_quantity` (4dp), so a position whose average cost
rounds to `0.0` makes this raise `ZeroDivisionError` — a 500 on `GET /api/portfolio`, on
`POST /api/portfolio/trade` (the snapshot at `trading.py:177` uses the same function) and on the
snapshot loop, until the position is removed.

Currently unreachable: `PriceCache` rounds prices to 2dp and both the seeded and the synthesized
simulator prices are well above a cent, so `fill_price` and therefore `avg_cost` cannot round to
zero. Recorded because the reachability depends entirely on the frozen market module's price floor,
which nothing in this phase pins, and because the blast radius is the whole portfolio read rather
than the one position.

**Fix:** if a price floor is not going to be asserted somewhere, report `None` for
`unrealized_pnl_percent` when `cost_basis` is zero — consistent with the existing null rule for
unpriced positions rather than a new special case.

---

_Reviewed: 2026-08-13_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
