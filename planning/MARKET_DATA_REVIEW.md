# Market Data Backend — Code Review

**Date:** 2026-08-03
**Reviewer:** Claude (automated review, triggered from issue #4)
**Scope:** `backend/app/market/` (9 source files) and `backend/tests/market/` (9 test files)

---

## 1. Test Execution — Could Not Run in This Environment

The issue asked for the test suite to be run as part of this review. **I was unable to do so.** This CI run is triggered directly from an issue with no interactive user attached, and the sandbox requires explicit approval for `uv sync`, `pip install`, and `python -m ...` invocations — approval that has no one to grant in an unattended run. Every attempt (`uv sync --extra dev`, installing `uv` via `curl`/`pip`, even `python3 -m pytest --version`) was rejected with "this command requires approval." Trivial read-only commands (`ls`, `find`, `git status`, `echo`) were not affected.

To let a future run actually execute the suite, add the relevant command prefixes to `--allowedTools` in `.github/workflows/claude.yml`, e.g.:

```yaml
claude_args: '--allowed-tools "Bash(uv:*),Bash(python3:*)"'
```

In lieu of a live run, I read all 9 test modules in full (148 `test_` functions; the 6 conformance tests are parametrized over both implementations, so ~154 executions) and traced each assertion against the corresponding source. The suite's structure and assertions are sound and — taking the issue author's confirmation that all tests pass at face value — I have no reason to doubt that. The reasoning below evaluates test *quality* and *coverage gaps*, not whether they currently pass.

| Module | Test functions | Notes |
|---|---|---|
| `test_models.py` | 15 | `PriceUpdate` properties, immutability, session-baseline math |
| `test_cache.py` | 30 | Update/read/history/baseline/version semantics |
| `test_simulator.py` | 29 | GBM math, correlation, backfill, unknown-ticker synthesis |
| `test_simulator_source.py` | 15 | `SimulatorDataSource` lifecycle (integration-style, real asyncio) |
| `test_massive.py` | 23 | `MassiveDataSource`, fully mocked REST client |
| `test_factory.py` | 7 | Env-var driven source selection |
| `test_stream.py` | 9 | SSE generator driven directly, no ASGI server needed |
| `test_conformance.py` | 6 (×2 params) | Shared lifecycle contract, both implementations |
| `test_tickers.py` | 14 | Ticker validation regex |

---

## 2. Spec Conformance (`planning/PLAN.md` §6)

Section 6 describes the "one remaining change" to the market module: session baseline (`open_price`, `change_from_open_percent`), unknown-ticker synthesis, one-shared ticker-validation rule, and the SSE heartbeat. All are implemented and match the spec closely:

| Requirement | Status | Where |
|---|---|---|
| `open_price` pinned on first tick, survives later updates | ✅ | `cache.py:51-58`, `test_cache.py:117-134` |
| `change_from_open_percent` drives the user-facing "change %" | ✅ | `models.py:54-58` |
| Baseline resets on remove + re-add | ✅ | `cache.py:84-89`, `test_cache.py:136-142` |
| Unknown tickers get deterministic synthesized price/vol | ✅ | `seed_prices.py:47-61`, SHA-256-based, no `random` |
| Ticker validation is one shared rule (`^[A-Z]{1,5}$`) | ✅ | `tickers.py` |
| History backfill (~60 points) on startup and on add | ✅ | `simulator.py:141-165`, `cache.py:69-82` |
| SSE: one event for all tickers, only on version change | ✅ | `stream.py:82-88` |
| SSE heartbeat every 15s regardless of price activity | ✅ | `stream.py:90-93` |
| SSE `retry: 1000` directive on open | ✅ | `stream.py:71` |
| Timestamps are epoch seconds on the wire | ✅ | `models.py:21`, `to_dict()` |
| Massive off-hours flatness is expected, not a bug | ✅ (documented) | `massive_client.py` |

No spec regressions found. This is a genuinely complete implementation of the one item build order step 1 called out as outstanding.

---

## 3. Architecture — Strengths

- Clean strategy pattern: `MarketDataSource` ABC with two conforming implementations, both exercised by a shared `test_conformance.py` suite — the right way to guarantee interchangeability instead of hoping the two stay in sync.
- `PriceCache` as the single point of truth is well-isolated: producers write, consumers (SSE, eventually portfolio valuation) read, no direct coupling. Version counter cleanly decouples "did anything change" from "what changed."
- `PriceUpdate` is `frozen=True, slots=True` — correct choice for a value object handed across threads/tasks.
- GBM math is properly separated from I/O: `GBMSimulator` is pure and synchronous (`simulator.py:31-46`), `SimulatorDataSource` owns the only asyncio task. Tests drive `step()` directly instead of sleeping, which is why `test_simulator.py` can run 10,000 iterations without being slow.
- Numerical edge case handled defensively: a non-positive-definite correlation matrix degrades to independent draws instead of crashing the whole price feed (`simulator.py:191-198`), and it's tested (`test_simulator.py:102-110`).
- The Massive timestamp-unit landmine is called out with a large, specific comment (`massive_client.py:159-166`) rather than a generic "watch out for units" note — this is exactly the kind of thing that bites someone at 2am, and it's pre-empted well, backed by a real sample value in the tests.
- Failure isolation is correct throughout: `_run_loop` (`simulator.py:290-303`) and `_poll_once` (`massive_client.py:113-130`) both catch broadly and log rather than letting the background task die silently, which is the one way a "live" stream can look connected while actually frozen — explicitly called out in the code comments.
- Backfilled sparkline history correctly runs the GBM recurrence *backwards* from the live price (`simulator.py:141-165`) so history and live stream join continuously instead of jumping.

---

## 4. Findings

None of the following are severe; nothing here should block moving to build-order step 2 (database/portfolio API). Ordered roughly by how likely each is to bite the next agent that builds on top of this module.

### 4.1 `MassiveDataSource.add_ticker` doesn't seed a live price (Medium — downstream risk)

`massive_client.py:87-94`:

```python
async def add_ticker(self, ticker: str) -> None:
    ticker = ticker.upper().strip()
    if ticker in self._tickers:
        return
    self._tickers.append(ticker)
    logger.info("Massive: added ticker %s (will appear on next poll)", ticker)
    if self._backfill_enabled:
        await self._backfill_one(ticker)
```

This seeds *history* (if enabled) but never calls `self._cache.update(...)` — the live price only appears after the next scheduled poll, which defaults to **15 seconds** on the free tier. Compare with `SimulatorDataSource._seed()` (`simulator.py:280-288`), which publishes a price synchronously before `add_ticker`/`start` returns.

PLAN.md §8 specifies that a just-added ticker's first trade "polls the cache for up to 2 seconds (every 200ms) waiting for a first tick," and calls that effectively-never-expiring only for the simulator. With Massive as the source, adding a ticker via a trade (§8: "Trading a ticker that is not on the watchlist adds it to the watchlist as part of the trade") will hit the 2-second `wait_for_price` timeout in the common case, well before the next poll fires. This is a real functional gap for anyone testing against live Massive data rather than the simulator (which is the documented default and what E2E tests use, so it won't surface in CI — but it will surface for a student who sets `MASSIVE_API_KEY`).

Not something to fix in the market module in isolation — flagging it now so whoever builds the trade endpoint knows the "wait up to 2s" strategy is simulator-only in practice, and either lives with the failure message ("no price available yet, try again") for Massive users or special-cases an eager single-ticker fetch on add.

### 4.2 Ticker normalization is inconsistent between the two implementations (Low)

`MassiveDataSource.add_ticker`/`remove_ticker` (`massive_client.py:87-100`) do their own ad hoc `ticker.upper().strip()`, while `SimulatorDataSource.add_ticker`/`remove_ticker` (`simulator.py:260-273`) and `GBMSimulator.add_ticker`/`remove_ticker` do no normalization at all — they trust the caller. `MassiveDataSource.start()` (`massive_client.py:58`) also uppercases but doesn't strip.

Both implementations skip the shared `normalize_ticker()` in `tickers.py` entirely, duplicating (and, for Simulator, omitting) logic that already exists once, correctly, elsewhere in the package.

In practice this is likely harmless today because the not-yet-built watchlist/trade routes are expected to call `normalize_ticker()` before reaching either source. But it means the two "interchangeable" implementations are not actually interchangeable if a caller ever passes an unnormalized ticker directly — `SimulatorDataSource.add_ticker("aapl")` and `MassiveDataSource.add_ticker("aapl")` behave differently (the former creates a *new*, lowercase-keyed synthesized ticker distinct from `"AAPL"`; the latter normalizes and merges with any existing `"AAPL"`). Given the interface's own stated goal — "downstream code is source-agnostic" — this is worth tightening: both should call `normalize_ticker` internally rather than relying on callers to have already done so.

### 4.3 `interface.py` docstring overstates the `MassiveDataSource` guarantee (Low)

`interface.py:40-41`:

```python
async def add_ticker(self, ticker: str) -> None:
    """Track a ticker. No-op if already tracked. Seeds price and history."""
```

Per 4.1, this is only true for `SimulatorDataSource`. For `MassiveDataSource` it seeds history (conditionally) but not price. Worth either fixing the implementation to match the contract, or narrowing the docstring to say what's actually guaranteed across both.

### 4.4 Day-close fallback timestamps with wall-clock instead of the bar's actual time (Low)

`massive_client.py:175-177`:

```python
day = getattr(snap, "day", None)
if day is not None and getattr(day, "close", None):
    return float(day.close), time.time()
```

The `last_trade` and `min` fallbacks both return the quote's real timestamp; this one stamps a potentially stale daily-close price with "now." Since `PriceUpdate.timestamp` feeds `/api/health`'s `newest_price_age_seconds` (per PLAN.md §8), a stale day-close snapshot would read as perfectly fresh. Minor — this is the last-resort fallback and only matters when neither trade nor minute data is available — but worth a one-line comment acknowledging the trade-off, or using `day.timestamp` if the SDK exposes one.

### 4.5 No conformance test pins down `add_ticker`'s timing contract (Low, test-coverage)

`test_conformance.py` tests that `start()` populates the cache before returning (`test_conformance.py:55-60`), but there's no equivalent assertion for `add_ticker()`. Given 4.1, an explicit test — even one that simply documents "Massive's add_ticker does not guarantee an immediate price, Simulator's does" — would turn today's silent divergence into a visible, intentional one.

### 4.6 Documentation has drifted from the implemented code (Low)

- `backend/CLAUDE.md` documents `PriceUpdate` as `(ticker, price, previous_price, timestamp, change, direction)` — missing `open_price`, `change_from_open`, `change_from_open_percent`, and doesn't mention `wait_for_price`, `normalize_ticker`/`TICKER_PATTERN`, or the SSE heartbeat/retry behavior at all.
- `planning/MARKET_DATA_SUMMARY.md` has the same gap (line 28's module table) and its "Test Suite" section (73 tests, 6 modules) is stale — there are now 9 modules and 148 test functions.

Neither is a code defect, but both are read by future agents as the ground truth for "what does this module already provide" per `CLAUDE.md`'s own instruction to consult them. Worth a refresh before build-order steps 2–3 (database/portfolio, watchlist API) start, so those agents don't miss `open_price`/`wait_for_price`/`normalize_ticker` and re-derive them.

---

## 5. Test Suite Assessment

The suite is a genuine strength of this codebase, not just a checkbox:

- Tests read like specifications — docstrings state *why*, not just *what* (e.g. `test_zero_timestamp_is_not_discarded`, `test_repeated_price_does_not_bump_version`).
- Good edge-case discipline: zero/negative denominators, empty ticker lists, duplicate add/remove, Cholesky failure, malformed API snapshots, backoff capping and reset, immediate-disconnect SSE clients.
- The conformance suite (`test_conformance.py`) is the right instinct for a strategy-pattern ABC — it's the mechanism that should have caught 4.1/4.2 and currently doesn't (see 4.5).
- `test_simulator.py`'s `test_prices_are_positive` running 10,000 iterations is a reasonable property-style check given GBM prices are mathematically guaranteed positive (`exp()` is always > 0) — not flaky, just thorough.
- Minor observation, not a defect: `test_simulator_source.py` and a few Massive lifecycle tests rely on real `asyncio.sleep()` calls with small durations (0.05–0.3s) rather than fake clocks. This is standard for this kind of integration test and unlikely to flake given the margins used, but is worth keeping an eye on if CI ever runs on noisy/shared runners.

---

## 6. Verdict

The market data subsystem is well-architected and the session-baseline feature that PLAN.md §13 called out as the "one remaining change" is fully and correctly implemented, matching the documented wire contract exactly. I was not able to execute the test suite myself in this sandboxed, unattended run (see §1) — take the "all tests pass" confirmation as the source of truth on green/red status, and the findings above as what a full static read surfaced regardless of pass/fail.

Nothing found here rises above "worth a follow-up," and none of it blocks starting build-order step 2 (database and portfolio API). The one item worth actually fixing before it causes a confusing bug report is **4.1** (Massive's `add_ticker` not seeding a price), since it's the kind of thing that only surfaces once someone sets a real `MASSIVE_API_KEY` and tries to buy a ticker they just added — by which point the market module itself will look "done" and the bug report will land on the portfolio/trade code instead.

**Recommended follow-ups, roughly in priority order:**
1. Decide how `MASSIVE_API_KEY` users should experience adding-then-immediately-trading a new ticker (4.1) — either an eager single-ticker fetch on `add_ticker`, or an explicit, documented UX limitation.
2. Route both implementations' `add_ticker`/`remove_ticker`/`start` through `normalize_ticker()` instead of duplicating (or skipping) normalization (4.2, 4.3).
3. Refresh `backend/CLAUDE.md` and `planning/MARKET_DATA_SUMMARY.md` to reflect the current module surface (4.6).
4. Add a conformance test that pins down the `add_ticker` timing contract, once 4.1 is resolved one way or the other (4.5).
5. Optional/cosmetic: `massive_client.py:177`'s day-close timestamp (4.4).
