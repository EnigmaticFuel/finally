---
phase: 03
slug: portfolio-watchlist-apis
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-08-15
---

# Phase 03 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

Register origin: **authored at plan time**. All nine plans (`03-01` ... `03-09`) carry a
`<threat_model>` block, so this audit verifies that registered mitigations exist rather
than constructing a register retroactively. ASVS L1, `block_on: high`.

This phase is where untrusted input first reaches money. Phase 1 built the app shell and
Phase 2 containerized it; Phase 3 adds the endpoints that move `cash_balance`, write
`positions`, and hand symbols to the market simulator. The interesting surface is
therefore arithmetic and transaction boundaries rather than infrastructure: a `NaN`
quantity, a TOCTOU double-spend between two buys, a sell that credits cash but loses the
position write, a reset interleaving with a trade, and a background snapshot loop that
can pair pre-trade cash with a post-trade position.

Two structural properties carry most of the register. Every state change runs inside a
single `writing(conn)` = `BEGIN IMMEDIATE` transaction, and every database call goes
through `run_db` -> `asyncio.to_thread`, so no handler blocks the event loop that serves
the SSE stream.

## Threat ID collisions - read before consuming this register

The nine plans were authored in parallel and **six threat IDs are reused for entirely
different threats**: `T-03-56`, `T-03-57`, `T-03-58`, `T-03-59`, `T-03-60` and `T-03-61`
each mean one thing in one plan and something unrelated in another (the 03-05/03-06 and
03-07/03-09 pairs). For example `T-03-60` is "router registered after the static mount"
in 03-07 and "reset driven cross-origin by a form" in 03-09 - both `high`, both
`mitigate`, both real.

Consequently **this register is keyed by (Threat ID, Source Plan), not by Threat ID.**
Any tool that keys on the ID alone will silently drop six rows. The collision is also how
four mitigate-disposition threats initially escaped verification: they were invisible to
an ID-keyed register and had to be audited in a second pass. The IDs are left as the
plans authored them rather than renumbered, so traceability back to each
`<threat_model>` block survives.

`T-03-SC` (supply chain) is the one genuine duplicate - the same threat restated
identically in all nine plans - and is collapsed to a single row.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| browser -> `/api/*` | Untrusted JSON bodies and query strings reach money arithmetic | `ticker`, `side`, `quantity`, `?limit=`, `?since=` |
| service -> SQLite | Untrusted values reach parameterized SQL and `cash_balance` | Ticker strings, quantities, ISO timestamps |
| service -> price cache | The service reads prices; the client never names one | Fill prices, valuation prices |
| request handler -> event loop | A synchronous database call here stalls the SSE stream for every client | All DB work, via `run_db` |
| background snapshot loop -> SQLite | A task writing concurrently with a trade can record an inconsistent total | `portfolio_snapshots` rows |
| app lifespan -> background tasks | A task outliving the app holds a SQLite write lock nobody reclaims | Task handles, DB connections |
| router registration -> static mount | A router registered after `app.frontend(...)` shadows every `/api/*` route | Route table ordering |
| test process -> tracked `db/finally.db` | A misdirected test write lands in a committed binary artifact | Snapshot rows |

---

## Threat Register

| Threat ID | Source Plan | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|-------------|----------|-----------|----------|-------------|------------|--------|
| T-03-01 | 03-01 | Tampering | `ticker` in `TradeRequest` reaching SQL and the market source | medium | mitigate | `normalize_ticker` (`^[A-Z]{1,5}$`) before any use; `queries.py` binds `?` placeholders exclusively and this plan writes zero SQL | closed - summary |
| T-03-02 | 03-01 | Tampering | `quantity` float corrupting `cash_balance` with `NaN` or `Infinity` | high | mitigate | `validate_quantity` runs `math.isfinite` before the positivity and precision checks, in the service, before any arithmetic (proven necessary: `round(inf, 4)` returns `inf`) | closed - summary |
| T-03-03 | 03-01 | Tampering | Two concurrent buys both passing the cash check (TOCTOU double-spend) | high | mitigate | The whole read-modify-write is one composed function inside `writing(conn)` = `BEGIN IMMEDIATE`, with `busy_timeout=5000` absorbing contention | closed - summary |
| T-03-05 | 03-01 | Info disclosure | Error bodies shown to the user verbatim | medium | mitigate | Handlers emit `{"detail": str(exc)}` where `exc` carries a service-authored message; never a repr, never a filesystem path, never a traceback | closed - summary |
| T-03-06 | 03-01 | Elevation of privilege | `user_id` becoming a request-controlled parameter | medium | mitigate | No route, model or service signature accepts `user_id`; every query call takes the `DEFAULT_USER_ID` default | closed - summary |
| T-03-07 | 03-01 | Denial of service | Blocking the event loop and stalling the SSE stream | medium | mitigate | All database work goes through `run_db`'s `asyncio.to_thread`; no synchronous `sqlite3` call is added to a route | closed - summary |
| T-03-08 | 03-01 | Tampering | A rejected trade leaving partial state (cash debited with no position, orphan watchlist row) | high | mitigate | Every write is inside one `writing()` block; raising inside it rolls back and re-raises | closed - summary |
| T-03-02-01 | 03-02 | Elevation of privilege | The sell arm acquiring shares the user does not hold (an implicit short) | high | mitigate | `held` is read via `get_position` inside the same `BEGIN IMMEDIATE` as the write, so there is no read-then-write window; `remaining < 0 and not is_zero(remaining)` raises before any position... | closed - summary |
| T-03-02-02 | 03-02 | Tampering | A negative or dust quantity persisting in `positions` after a sell | high | mitigate | The branch writes only `delete_position` when `is_zero(remaining)` or `upsert_position` with a strictly positive `remaining`; no other write path exists in the arm | closed - summary |
| T-03-02-03 | 03-02 | Tampering | `NaN` or `Infinity` quantity corrupting `cash_balance` on the sell path | high | mitigate | `validate_quantity` runs finiteness first, before positivity and precision, and `execute_trade` calls it before any I/O per D-04 - proven necessary because rounding an infinite float returns... | closed - summary |
| T-03-02-04 | 03-02 | Repudiation | A rejected trade leaving a row in the append-only `trades` audit log | medium | mitigate | Every rejection raises before `insert_trade` and inside `writing()`, whose rollback branch is verified; the audit log records settled trades only, and a test asserts the snapshot and cash co... | closed - summary |
| T-03-02-05 | 03-02 | Information disclosure | Rejection messages shown verbatim leaking internals | medium | mitigate | Messages carry only the ticker, the quantities and the two cash figures at two decimal places - no filesystem path, no exception repr, no traceback; the handlers emit `{"detail": str(exc)}` ... | closed - summary |
| T-03-02-06 | 03-02 | Denial of service | The two-second first-tick wait held open per request | medium | accept | Bounded by `wait_for_price`'s own deadline, and it runs before the transaction opens so it holds no write lock; a single-operator localhost app has no adversarial request volume | closed - accepted |
| T-03-02-07 | 03-02 | Tampering | A partially settled sell - cash credited with the position write lost | high | mitigate | Both writes and the guard sit inside 03-01's single `writing()` block; a raise anywhere inside rolls the whole unit back, and Task 1's acceptance criteria assert the database is unmoved afte... | closed - summary |
| T-03-02-SC | 03-02 | Tampering | Package-manager installs | informational | accept | This plan installs zero packages; `backend/pyproject.toml` and `backend/uv.lock` are not in `files_modified`, so there is no supply-chain surface to audit. Recorded at `informational` rather... | closed - accepted |
| T-03-30 | 03-03 | Denial of service | `?limit=` on `GET /api/portfolio/history` | medium | mitigate | `Annotated[int, Query(ge=1, le=HISTORY_MAX_LIMIT)]` caps the row count at 5000 at the transport layer before any query runs (D-21); `?limit=0` and an over-cap value are 422s, not empty lists | closed - audit |
| T-03-31 | 03-03 | Tampering | `?since=` reaching the snapshot query | medium | mitigate | `get_snapshots` binds `since` as a `?` placeholder twice and this plan writes zero SQL; an unparseable string simply matches nothing rather than altering the statement. No normalization is a... | closed - audit |
| T-03-32 | 03-03 | Tampering | `POST /api/portfolio/reset` as an unauthenticated destructive endpoint | high | mitigate | Declared on POST only, so no navigation, link prefetch or crawler can trigger it, and asserted by a test that a GET to the same path leaves cash unchanged. Its blast radius is bounded to `po... | closed - audit |
| T-03-33 | 03-03 | Repudiation | A reset leaving no trace, so a portfolio appears to have simply lost value | medium | mitigate | The snapshot row is written inside the reset transaction, so `GET /api/portfolio/history` shows the step the moment it happens and the P&L chart renders it as a visible drop rather than a ga... | closed - audit |
| T-03-34 | 03-03 | Tampering | A concurrent trade interleaving with the reset, leaving positions with reset cash or cash with surviving positions | high | mitigate | The whole reset - every `delete_position`, the cash write and the snapshot - is one composed function inside `writing(conn)` = `BEGIN IMMEDIATE`, with `busy_timeout=5000` absorbing contentio... | closed - audit |
| T-03-35 | 03-03 | Information disclosure | A missing price silently becoming a fabricated one in a number the user trades against | medium | mitigate | `value_portfolio` emits nulls and excludes the position from `total_value` (D-14); no fallback to `avg_cost`, to a last-known price, or to zero exists in the code path | closed - audit |
| T-03-36 | 03-03 | Denial of service | Blocking the event loop and stalling the SSE stream | medium | mitigate | Every database access in this plan goes through `run_db`'s `asyncio.to_thread`; no synchronous `sqlite3` call is added to a route, and the router file is gated to contain no `run_db` or `sql... | closed - audit |
| T-03-10 | 03-04 | Tampering | User-supplied ticker in the POST body and the DELETE path reaching SQLite and the market source | medium | mitigate | `normalize_ticker` runs first in both `add` and `remove`, before any I/O; `queries.py` binds placeholders exclusively and this plan writes zero SQL | closed - summary |
| T-03-11 | 03-04 | Tampering | TOCTOU on removal - a trade creating a position between the held check and the delete, breaking the "every position has a live price feed" invariant | high | mitigate | `_remove_checked` performs `get_position` and `remove_watchlist_ticker` inside one `writing(conn)` block, so the whole check-and-delete is one `BEGIN IMMEDIATE` with `busy_timeout=5000` abso... | closed - summary |
| T-03-12 | 03-04 | Denial of service | Registering the watchlist router after the static mount, shadowing every `/api/*` route while the page still loads | high | mitigate | The `include_router` call goes above `app.frontend(...)`, which stays the last statement before `return app`; `tests/test_main.py::test_api_not_shadowed` asserts it over real HTTP and is run... | closed - summary |
| T-03-13 | 03-04 | Denial of service | Unbounded watchlist growth through repeated adds - each new symbol allocates a simulated series that ticks every 500ms and adds 60 history points to e... | medium | accept | Single-operator localhost app with no authentication and fake money; the shared rule caps the namespace at well-formed symbols and there is no remote attacker in the threat model. Recorded r... | closed - accepted |
| T-03-14 | 03-04 | Information disclosure | Rejection messages are rendered to the user verbatim, and the invalid-symbol message echoes the submitted string back | low | accept | The body is `{"detail": str(exc)}` carrying a service-authored message - no path, no repr, no traceback. The echoed value is JSON-encoded on the way out; Phase 4 must render `detail` as text... | closed - accepted |
| T-03-15 | 03-04 | Elevation of privilege | `user_id` becoming a request-controlled parameter through a watchlist route | medium | mitigate | No route, model or service signature in this plan accepts `user_id`; every query call takes the `DEFAULT_USER_ID` default | closed - summary |
| T-03-50 | 03-05 | Tampering | The snapshot loop and `execute_trade` interleaving, recording a total that pairs pre-trade cash with a post-trade position | high | mitigate | The whole read-compare-write - `get_profile`, `get_positions`, `value_portfolio`, `get_latest_snapshot`, `insert_snapshot` - sits inside one `writing(conn)` block, so `BEGIN IMMEDIATE` takes... | closed - audit |
| T-03-51 | 03-05 | Denial of service | The background task outliving the app, or leaking across a reload, holding a SQLite write lock nobody reclaims | high | mitigate | One lifespan creates it and cancels it: `task.cancel()`, `await task`, `except asyncio.CancelledError: pass`, before `await source.stop()` (D-17); `tests/test_main.py` asserts `snapshot-loop... | closed - audit |
| T-03-52 | 03-05 | Tampering | A test run writing snapshot rows into the git-tracked `db/finally.db` | medium | mitigate | Two independent mitigations, both applied: `tests/conftest.py` sets `application.state.db_path = db_path`, and the loop sleeps `SNAPSHOT_INTERVAL_SECONDS` before its first write so no existi... | closed - audit |
| T-03-53 | 03-05 | Repudiation | A recorder that dies or silently records nothing, leaving a gap in history that renders as a flat portfolio rather than a broken feed | medium | mitigate | No `except` anywhere in the module - a failure surfaces as a task exception rather than an infinitely quiet loop; the unchanged skip is narrowed to `round_money` equality against the newest ... | closed - audit |
| T-03-54 | 03-05 | Denial of service | The timer loop blocking the event loop and stalling the SSE stream | medium | mitigate | The wait is `await asyncio.sleep(...)`, never a synchronous sleep, and every database access goes through `run_db`'s `asyncio.to_thread`; no synchronous `sqlite3` call is added to the loop | closed - audit |
| T-03-55 | 03-05 | Denial of service | Unbounded growth of `portfolio_snapshots` on a long-running container - a row every 30 seconds is 2880 rows a day | medium | accept | The D-16 skip removes the idle and all-cash case entirely, which is the realistic single-operator pattern; reads are bounded by `03-03`'s `?limit=` cap of 5000 rows, so growth degrades stora... | closed - accepted |
| T-03-56 | 03-05 | Denial of service | Registering anything after the static mount while editing `main.py`, shadowing every `/api/*` route while the page still loads | high | mitigate | This plan adds no `include_router` call and moves none; `app.frontend(...)` stays the last statement before `return app`, an acceptance criterion pins the `include_router` count as unchanged... | closed - audit |
| T-03-56 | 03-06 | Denial of service | `execute_trade` registering an untrusted symbol with the simulator: each new ticker costs an O(n^3) Cholesky rebuild on add and a per-tick step foreve... | medium | accept | Same posture and same reasoning as T-03-13, which the phase already accepted: single-operator localhost app, no authentication, fake money, no remote attacker in the threat model. Two real l... | closed - accepted |
| T-03-57 | 03-06 | Tampering | Boot handing ticker strings read from SQLite straight to the simulator, without re-validating their shape | low | accept | Watchlist rows can only ever be written through `add_watchlist_ticker`, which calls `normalize_ticker` on the way in (`queries.py:261`), so a row's shape is already enforced at the only writ... | closed - accepted |
| T-03-58 | 03-06 | Denial of service | `startup_tickers` making application startup depend on a database read: a locked or unreadable database now fails startup instead of the first request | medium | mitigate | The read goes through `run_db`, the same door every request already uses, with `busy_timeout=5000` absorbing contention - a database that cannot be read at boot would have failed the first r... | closed - audit |
| T-03-59 | 03-06 | Spoofing | The amended seam being called by Phase 6's LLM path with a source the caller chose, rather than the app's own | low | accept | `execute_trade` takes the source as a collaborator exactly as `watchlist.add` already does (D-09), and the only production caller is the router factory, which is handed `create_app`'s single... | closed - accepted |
| T-03-57 | 03-07 | Denial of service | The market source and its `simulator-loop` surviving lifespan exit after the snapshot task died, per the recorded probe `simulator-loop still alive af... | high | mitigate | `task.cancel()`, `await asyncio.gather(task, return_exceptions=True)` and `await source.stop()` all run from a single `finally` block, so no exception path can skip the reclaim; `stop()` is ... | closed - audit |
| T-03-58 | 03-07 | Repudiation | A recorder that died leaving no trace: no request failed, no status code changed, `/api/health` says nothing, and the P&L chart simply flatlines - whi... | medium | mitigate | `_log_if_failed` is wired with `add_done_callback` and reports at error level with `%s` lazy formatting the instant the task finishes - seconds or hours before shutdown, which is when the op... | closed - audit |
| T-03-59 | 03-07 | Tampering | A "fix" that quiets the failure to make teardown clean - a retry around the task, a tolerance band, a downgrade to warning, or a broad catch - silentl... | medium | mitigate | D-G04 forbids it and three prohibitions pin it mechanically: no broad catch and no database-lock handler in `main.py` (both grep-checked at `0`), exactly one `logger.error(` call, and `backe... | closed - audit |
| T-03-60 | 03-07 | Denial of service | Registering a router after the static mount while editing `main.py`, shadowing every `/api/*` route while the page still loads - the single most conse... | high | mitigate | This plan adds no `include_router` call and moves none; an acceptance criterion pins the count at `4` and `app.frontend(` as the last statement before `return app`; `tests/test_main.py::test... | closed - audit |
| T-03-61 | 03-07 | Denial of service | Shutdown blocking while the reclaim waits on a snapshot task whose `run_db` call is mid-flight: `asyncio.to_thread` is not interruptible, so cancellat... | low | accept | Bounded by SQLite's `busy_timeout=5000`, so the worst case is a roughly five-second shutdown delay, not a hang; identical to the pre-existing behavior of the code being replaced, so this pla... | closed - accepted |
| T-03-40 | 03-08 | Information disclosure | The blanket `ValueError` handler at `api/errors.py:40` echoing `str(exc)` for any `ValueError`, including `pydantic_core.ValidationError`, which leaks... | high | mitigate | Task 1 translates the two known plain-`ValueError` sources into `TradeError` at the service seam and deletes the blanket registration; `tests/api/test_errors.py` asserts a pydantic failure r... | closed - audit |
| T-03-41 | 03-08 | Repudiation | Server defects reported to the client as 400s, so a genuine fault produces no 5xx, no traceback and nothing in the logs to attribute it to - the front... | medium | mitigate | With the blanket row gone an unexpected `ValueError` falls through to Starlette's 500 with the traceback logged; the 500-not-400 assertion in `tests/api/test_errors.py` is the regression gua... | closed - audit |
| T-03-42 | 03-08 | Tampering | The cash sufficiency check comparing rounded cost against rounded cash while the subtraction runs at full precision, letting a sub-half-cent overdraft... | medium | mitigate | Task 2 compares raw `cost` against raw `cash`, which makes the difference provably non-negative before rounding; a test buys 5000.002 shares at 2.00 against the seeded 10000.0 balance and as... | closed - audit |
| T-03-43 | 03-08 | Tampering | The trade-time snapshot valuing the traded ticker at a second, independent cache read rather than at the fill, writing a wrong row into an append-only... | low | mitigate | Task 3 overlays `fill_price` onto the price map before the transaction opens; the `MovingCache` test forces the two reads to disagree and asserts the snapshot follows the fill | closed - audit |
| T-03-44 | 03-08 | Information disclosure | User-facing refusal messages rendering share counts in exponent form, producing text a user cannot act on and which reveals the internal float represe... | low | mitigate | `_format_shares` renders at the stored 4dp precision with trailing zeros stripped; a parametrized unit test and an end-to-end message test both assert no exponent notation | closed - audit |
| T-03-45 | 03-08 | Denial of service | A `TradeError` message echoing a submitted value back to the client (`Invalid ticker symbol: 'toolong'`) as a reflection vector | low | accept | Unchanged by this plan and inherited from 03-04's T-03-14: the body is `{"detail": str(exc)}` carrying a service-authored message with no path, no repr and no traceback, JSON-encoded on the ... | closed - accepted |
| T-03-60 | 03-09 | Spoofing | `POST /api/portfolio/reset` driven cross-origin by a form, a beacon or a `no-cors` fetch (WR-02) | high | mitigate | `ResetRequest` becomes a required JSON body, so the request stops being a CORS "simple request": a form-encoded, bodyless or `text/plain` POST fails model validation with 422 before `_apply_... | closed - audit |
| T-03-61 | 03-09 | Tampering | The other two state-changing POST routes, `/api/portfolio/trade` and `/api/watchlist` | low | accept | Both already require a JSON body (`TradeRequest`, `WatchlistAddRequest`), so a form-encoded or `text/plain` POST fails their model validation today. No change is made here and none is needed... | closed - accepted |
| T-03-62 | 03-09 | Repudiation | A reset reporting state it did not write, so a user cannot tell from the response what actually happened (WR-04) | medium | mitigate | `reset_portfolio` returns `await get_portfolio(db_path, cache)`, so a transaction that leaves cash or a position behind is visible in the body. Pinned by a test that substitutes a partial tr... | closed - audit |
| T-03-63 | 03-09 | Denial of service | `ZeroDivisionError` on a zero cost basis taking down `GET /api/portfolio`, the trade-time snapshot and the 30-second snapshot loop until the position ... | medium | mitigate | `value_portfolio` reports `unrealized_pnl_percent` as `None` when the cost basis is exactly zero, so the read returns instead of 500ing. The guard is on the cost basis, so a break-even posit... | closed - audit |
| T-03-64 | 03-09 | Information disclosure | The 422 validation body naming the model and field back to a cross-origin attacker | low | accept | The attacker's page cannot read the response - no CORS headers are sent, so the fetch is opaque - and the field name is already public in `/docs`, which Phase 2 deliberately left enabled | closed - accepted |
| T-03-65 | 03-09 | Elevation of privilege | Any local process able to reach port 8000 can reset the portfolio | medium | accept | Fixed by the no-auth, single-local-operator design in `planning/PLAN.md`. Blast radius is bounded by D-10: the watchlist and the append-only `trades` log survive, so what was destroyed stays... | closed - accepted |
| T-03-SC | all 9 | Tampering | Package-manager installs (restated identically in all nine plans) | informational | accept | This phase installs zero packages; `backend/pyproject.toml` and `backend/uv.lock` are not edited, so there is no supply-chain surface to audit. Recorded at `informational` rather than `high`... | closed - accepted |
*Status: `closed - audit` = verified this run with file:line evidence (26) · `closed - summary` = mitigation confirmed by the plan's SUMMARY.md Threat Flags entry (17) · `closed - accepted` = documented in the Accepted Risks Log (14)*
*Severity: critical > high > medium > low — only open threats at or above `block_on: high` count toward `threats_open`*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Verification Evidence

The 26 `closed - audit` threats were verified this run by `gsd-security-auditor` against
the implementation and the test suite. The load-bearing citations:

| Threat | Evidence |
|--------|----------|
| T-03-32 (03-03) | POST-only at `backend/app/api/portfolio.py:103`, no GET alias; `backend/tests/api/test_portfolio.py:265` asserts a GET leaves cash untouched |
| T-03-34 (03-03) | Single `with writing(conn):` over delete loop + cash write + snapshot, `backend/app/services/portfolio.py:171-175`; rollback proven `backend/tests/services/test_portfolio.py:379-396` |
| T-03-35 (03-03) | `backend/app/services/portfolio.py:61-73` emits nulls and `continue`s on a missing price - no `avg_cost`, last-known or zero fallback exists |
| T-03-50 (03-05) | One `with writing(conn):` enclosing the whole snapshot read-value-write, `backend/app/services/snapshots.py:57-64`; `TestTradeCollision` at `backend/tests/services/test_snapshots.py:215-244` |
| T-03-51 (03-05) | `backend/app/main.py:82-87` `try: yield` / `finally:` cancel + `gather(..., return_exceptions=True)` + `source.stop()` |
| T-03-57 (03-07) | Same `finally` block; idempotency contract at `backend/app/market/interface.py:37`; `test_lifespan_stops_the_source_when_the_snapshot_task_died` at `backend/tests/test_main.py:150` |
| T-03-60 (03-07) | `app.frontend(...)` is the last statement before `return app` (`backend/app/main.py:99-100`); `test_api_not_shadowed` asserts it over real HTTP at `backend/tests/test_main.py:213-235` |
| T-03-60 (03-09) | Required JSON body `ResetRequest` at `backend/app/api/portfolio.py:105`; three 422-plus-untouched-state tests at `backend/tests/api/test_portfolio.py:207, :226, :242` |
| T-03-63 (03-09) | Cost-basis guard at `backend/app/services/portfolio.py:85-87`; break-even still reports 0.0 and stays in `total_value` |

Empirically confirmed alongside the audit: the full suite for the touched packages passes
(156 tests) and `git status --porcelain -- db/finally.db` is empty after the run, closing
T-03-52 by observation rather than by inspection alone.

**Scope note on T-03-58 (03-06).** Marked closed because the implementation matches what
the plan declares - the startup read goes through the same `run_db` door every request
uses, with `busy_timeout=5000` absorbing contention. It is *not* a claim that startup is
resilient to an unreadable database: there is no retry, no fallback and no degradation
path at `backend/app/main.py:79`, and the plan deliberately claims none. A locked
database fails startup by design, on the reasoning that it would have failed the first
request a moment later and that failing at startup is the more legible failure.

**Note on T-03-51 (03-05).** The shipped code uses
`await asyncio.gather(task, return_exceptions=True)` in a `finally` block rather than the
plan's literal `await task` + cancellation-only `except`. This is strictly stronger, not
a substitution of convenience: the plan's form re-raises when the task died of a
non-cancellation error, which skips `source.stop()` and leaks `simulator-loop` - the
exact defect T-03-57 (03-07) exists to fix. Both threats are closed by the same code.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-03-01 | T-03-02-06 (03-02) | The 2s first-tick wait is bounded by `wait_for_price`'s own deadline and runs before the transaction opens, so it holds no write lock. A single-operator localhost app has no adversarial request volume | Plan author, reaffirmed at audit | 2026-08-15 |
| AR-03-02 | T-03-13 (03-04) | Unbounded watchlist growth: single-operator localhost app, no auth, fake money. `normalize_ticker` caps the namespace at well-formed symbols. Recorded rather than mitigated so a future multi-user phase inherits the open question, not a silent assumption | Plan author, reaffirmed at audit | 2026-08-15 |
| AR-03-03 | T-03-14 (03-04), T-03-45 (03-08) | Rejection messages echo the submitted string. The body is `{"detail": str(exc)}` carrying a service-authored message - no path, no repr, no traceback - and is JSON-encoded on the way out. **Carries a Phase 4 obligation: render `detail` as text, never as markup** | Plan author, reaffirmed at audit | 2026-08-15 |
| AR-03-04 | T-03-55 (03-05) | `portfolio_snapshots` growth at 2880 rows/day. The unchanged-value skip removes the idle case entirely; reads are bounded by the `?limit=` cap of 5000. Growth degrades storage, not any response | Plan author, reaffirmed at audit | 2026-08-15 |
| AR-03-05 | T-03-56 (03-06) | `execute_trade` registering an untrusted symbol costs an O(n^3) Cholesky rebuild. Same posture as AR-03-02; `normalize_ticker` caps the namespace before registration, and registration runs only after `validate_quantity`, so a malformed request allocates nothing | Plan author, reaffirmed at audit | 2026-08-15 |
| AR-03-06 | T-03-57 (03-06) | Boot hands ticker strings from SQLite to the simulator without re-validation. Rows can only be written through `add_watchlist_ticker`, which calls `normalize_ticker` at the only write door; `params_for` synthesizes parameters for any unknown symbol, and no statement text is ever built from the value | Plan author, reaffirmed at audit | 2026-08-15 |
| AR-03-07 | T-03-59 (03-06) | The amended seam could be called by Phase 6's LLM path with a caller-chosen source. `execute_trade` takes the source as a collaborator exactly as `watchlist.add` does; the only production caller is the router factory holding `create_app`'s single instance. No signature accepts a source from a request body | Plan author, reaffirmed at audit | 2026-08-15 |
| AR-03-08 | T-03-61 (03-07) | Shutdown can block up to ~5s while a mid-flight `run_db` call returns, since `asyncio.to_thread` is not interruptible. Bounded by `busy_timeout=5000`, so the worst case is a delay, not a hang. The only way to shorten it is to abandon the task without reclaiming it, which reintroduces T-03-57 | Plan author, reaffirmed at audit | 2026-08-15 |
| AR-03-09 | T-03-61 (03-09) | `/api/portfolio/trade` and `/api/watchlist` already require a JSON body (`TradeRequest`, `WatchlistAddRequest`), so a form-encoded or `text/plain` POST fails model validation today. No change needed | Plan author, reaffirmed at audit | 2026-08-15 |
| AR-03-10 | T-03-64 (03-09) | The 422 body names the model and field to a cross-origin attacker. The attacker's page cannot read the response - no CORS headers are sent, so the fetch is opaque - and the field name is already public in `/docs`, which Phase 2 deliberately left enabled | Plan author, reaffirmed at audit | 2026-08-15 |
| AR-03-11 | T-03-65 (03-09) | Any local process reaching port 8000 can reset the portfolio. Fixed by the no-auth, single-local-operator design in `planning/PLAN.md`. Blast radius is bounded: the watchlist and the append-only `trades` log survive, so what was destroyed stays reconstructible | Plan author, reaffirmed at audit | 2026-08-15 |
| AR-03-12 | T-03-SC (all 9) | This phase installs zero packages; `backend/pyproject.toml` and `backend/uv.lock` are unmodified, so there is no supply-chain surface to audit. Recorded at `informational` rather than `high` precisely so an `accept` on a non-existent surface does not trip the phase's own `block_on: high` rule | Plan author, reaffirmed at audit | 2026-08-15 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-08-15 | 57 | 57 | 0 | gsd-security-auditor (opus), 2 passes |

Pass 1 verified 18 threats from an ID-keyed register, and incidentally closed 4 more it
found missing from that register (T-03-40, T-03-42, T-03-56/03-05, T-03-60/03-09). Pass 2
verified the 4 mitigate threats that the ID collisions had hidden entirely
(T-03-57/03-07, T-03-58/03-06, T-03-58/03-07, T-03-59/03-07). The remaining 17 mitigate
threats were confirmed by their plans' SUMMARY.md Threat Flags entries; the 14 accepted
risks are logged above.

**Process finding (not a code gap):** `03-03-SUMMARY.md` and `03-05-SUMMARY.md` have no
`## Threat Flags` section at all - an omission rather than a declared "None". Those two
plans' registers (T-03-30..36 and T-03-50..56) were verified directly against the plans
instead of trusting the summaries, so no threat went unverified, but both summaries are
non-conformant with the template.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-08-15
