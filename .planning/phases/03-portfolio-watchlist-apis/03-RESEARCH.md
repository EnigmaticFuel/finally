# Phase 3: Portfolio & Watchlist APIs - Research

**Researched:** 2026-08-12
**Domain:** FastAPI service layer + routers over an existing SQLite data layer and an in-memory price cache (backend only)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

*Copied verbatim from `03-CONTEXT.md` `<decisions>`. The planner must honor every one; none is open for re-derivation.*

**Trade as one unit of work**

- **D-01:** A trade is **one composed function passed to `run_db`**. `app/services/trading.py` defines a plain `def _apply_trade(conn, ...)` that opens `writing(conn)` and calls `get_profile`, `get_position`, `upsert_position`, `update_cash_balance`, `insert_trade`, `insert_snapshot` and `add_watchlist_ticker` in sequence. One connection, one `BEGIN IMMEDIATE`, no read-then-write race. Rejected: adding a `run_db_write()` helper to `connection.py` (edits Phase 1 code two phases already build against), and two `run_db` calls (opens a window where the snapshot task or a concurrent trade changes cash between the check and the write). — **Reversibility:** costly — this is the shape `execute_trade` is written in, and the ROADMAP records that function's signature as a contract Phase 6 must route through.

- **D-02:** The **prices used for the trade-time snapshot are captured before the transaction opens** and passed in as a plain `{ticker: price}` dict. The async service calls `cache.get_all()` (or equivalent), then hands the dict to `_apply_trade`. The thread function never touches `PriceCache`, so it stays pure, is testable with literal dicts, and the snapshot value agrees with the fill price the user was just quoted. Rejected: reading the cache inside the executor thread (legal, since `PriceCache` is thread-safe, but makes the transaction depend on state that moves every 500ms and forces every trade test to build a live cache), and snapshotting after commit in a second write (a crash between the two leaves a trade with no P&L step, violating PORT-11's "immediately").

- **D-03:** The service seam signature is **`async def execute_trade(db_path, cache, ticker, side, quantity) -> TradeResult`** — explicit arguments in, a dataclass out. The service owns validation, the `wait_for_price` call and the transaction. No FastAPI object crosses the seam, so Phase 6's LLM path passes exactly what the router passes. Rejected: a Pydantic request model as the parameter (couples the service to an HTTP shape Phase 6 has no natural instance of) and a bundled context object (hides what the function depends on). — **Reversibility:** costly — `.planning/ROADMAP.md` states these signatures are a contract, and Phase 6 (CHAT-07) is planned against them.

- **D-04:** Validation runs in the order **cheap checks → price → balance**. Ticker format and quantity rules validate first with no I/O; then `await wait_for_price(cache, ticker, timeout=2.0)`; then the transaction checks cash on a buy or shares held on a sell. A malformed quantity therefore returns 400 immediately rather than after a two-second wait, and the PORT-08 wait only ever runs for input that could actually fill.

- **D-05:** `avg_cost` arithmetic: on a **buy**, `avg_cost = (old_qty * old_avg + fill_qty * fill_price) / new_qty`, stored at 4dp per Phase 1's D-15. On a **sell**, quantity drops and `avg_cost` is untouched — cost basis per share does not change when you sell some of a holding. A sell to zero deletes the row (PORT-09), so `avg_cost` never survives with no shares. Realized P&L stays deliberately untracked. Rejected: recomputing `avg_cost` by replaying the `trades` table, which would make the append-only audit log a read dependency of the trade path — PLAN.md §7 is explicit that `trades` has no reader.

**How service failures become status codes**

- **D-06:** `app/services/errors.py` defines a **small exception taxonomy — `TradeError` (400), `NotFound` (404), `Conflict` (409) — all subclassing `ValueError`**, so Phase 1's raise-a-`ValueError`-with-a-user-facing-message style and `wait_for_price`'s existing `ValueError` both still fit. Services never import `HTTPException`. Phase 6 catches the same classes and reads `str(exc)` for CHAT-09's per-action error text. Rejected: plain `ValueError` everywhere (the router cannot tell 409 from 400, so the held-position rule ends up restated in the route) and returning a result object instead of raising (a forgotten `ok` check silently succeeds, which inverts the raise-don't-swallow rule). — **Reversibility:** costly — Phase 6's per-action error reporting is planned against these classes.

- **D-07:** **One app-level exception handler per error class**, registered in `create_app()`, returning `JSONResponse({"detail": str(exc)}, status_code=...)`. This produces PLAN.md §8's envelope verbatim, every route inherits it, and a new service raising `Conflict` is correctly a 409 the day it is written. Rejected: `try/except` in each route (seven routes repeating the same three-branch block, and a new route silently 500s if its author forgets) and a dependency wrapper (an indirection layer to understand before any route reads clearly). Messages are written to be shown to the user verbatim — e.g. `Insufficient cash: need $1905.20, have $800.00`.

- **D-08:** The **WATCH-05 held-position check and the watchlist delete share one `writing()` transaction**. `services/watchlist.remove()` passes a composed function to `run_db` that opens `writing(conn)`, calls `get_position`, raises `Conflict` if a position is held, then calls `remove_watchlist_ticker`. Same unit-of-work shape as D-01, so both services read alike, and the invariant "every position has a live price feed" holds under concurrency rather than probabilistically. Rejected: check-then-delete in two calls, and a schema-level foreign key or trigger — the latter would edit Phase 1's `schema.sql` after `db/finally.db` is already tracked in git, and would turn a readable 409 message into a translated SQLite error.

- **D-09:** On watchlist add, the **database write happens first, then `await source.add_ticker()`**. The watchlist row is the durable record and the source is restarted from it on every boot. If `add_ticker` fails, the row still exists and the ticker gets a feed on the next start — a missing price is visible and self-healing, whereas an orphaned feed is neither. Rejected: registering with the source first (a failed DB write leaves the simulator streaming a ticker nobody watches, with nothing to clean it up) and a rollback wrapper (defensive machinery for a failure `SimulatorDataSource.add_ticker` cannot realistically produce).

**Reset (PORT-14)**

- **D-10:** **Reset touches the portfolio only.** Cash returns to `STARTING_CASH`, every position row is deleted, and one snapshot is written at the new total. The **watchlist, `trades` and `chat_messages` are left completely alone.** This is the narrowest reading of "reset to the starting state: $10,000 cash and no positions", it keeps the append-only `trades` rule intact, and it does not contradict Phase 1's D-09 gate (an emptied watchlist stays empty). Consequence, deliberately accepted: after a reset the user keeps whatever tickers they had added, and the P&L chart shows the reset as a visible step rather than restarting flat. Rejected: full first-launch state (silently discards user-added tickers) and clearing `portfolio_snapshots` (the chart loses the record that a reset happened).

- **D-11:** The endpoint is **`POST /api/portfolio/reset`**, a verb-shaped sub-resource matching `/api/portfolio/trade`, returning **the same body as `GET /api/portfolio`** so the client's refetch rule needs no special case. It reads `app.db.seed.STARTING_CASH` rather than restating `10000.0` — this is the reuse Phase 1's deferred note asked for. It does **not** call `seed_fresh()`, which also writes the ten default watchlist tickers and would contradict D-10. Rejected: `DELETE /api/portfolio` (reads oddly for a resource that still exists afterwards, and collides conceptually with `DELETE /api/watchlist/{ticker}`).

- **D-12:** Reset **writes a snapshot and never writes a trade row.** The snapshot goes inside the reset transaction so `GET /api/portfolio/history` is never stale and the P&L chart shows the step. Nothing is appended to `trades` — a reset is not a sale, and synthetic sell rows would corrupt the audit log that realized P&L would later be derived from (PROJECT.md keeps that derivable). Rejected: writing neither (leaves history reporting a portfolio value that no longer exists for up to 30 seconds) and writing synthetic sells.

- **D-13:** **Reset has no API-level guard** — no confirmation token, no required body field. `POST` and it happens, exactly like a trade. It is fake money in a single-operator localhost simulator, and PLAN.md deliberately gives trades no confirmation dialog; any confirmation belongs in the Phase 4 UI where the user actually clicks. Recorded so Phase 4 owns that step and it is not dropped.

**Valuation and the snapshot task**

- **D-14:** A held ticker with **no price in the cache returns nulls, and is excluded from `total_value`.** `current_price`, `market_value` and `unrealized_pnl` come back as `null` for that position; `total_value` is cash plus only those positions that have a price. This is the honest answer — the client renders a dash rather than a wrong number — and Phase 4's UI-15 empty-state work has something real to render. Rejected: falling back to `avg_cost` (presents a fabricated price as real, and a stalled feed would look like a flat portfolio rather than a broken one) and calling `wait_for_price` per position (`GET /api/portfolio` is refetched after every trade and would block for seconds).

- **D-15:** The **same null rule applies to `GET /api/watchlist`.** A ticker with no price yet is **always present in the response** — the watchlist is database state, not cache state — with `price`, `open_price` and `change_from_open_percent` as `null` and `history` as `[]`. Rejected: omitting priceless tickers (a ticker the user just added would be missing from the list they just added it to, reading as a failed add) and returning zeros (`$0.00` is a real price a client will happily render and multiply).

- **D-16:** PORT-12's "unchanged" means **`round_money(new_total) == round_money(last_total)`** — cents-rounded comparison, reusing Phase 1's `money.py` rather than inventing a second precision rule. The skip genuinely fires on an all-cash portfolio, which is the idle and first-launch case; a held portfolio writing a row every 30 seconds is correct, because the value really did change and the P&L chart needs the point. Rejected: exact float equality (two identical cash-only values can still differ in the last bit after arithmetic, so the requirement would be satisfied in code and not in behavior) and a third epsilon constant alongside `MONEY_PLACES` and `QUANTITY_EPSILON`.

- **D-17:** The snapshot task is an **`asyncio` task created in `create_app()`'s lifespan**, started beside `source.start()` and cancelled before `source.stop()`, named per the house convention (`asyncio.create_task(..., name="snapshot-loop")`). Both dependencies — the DB path and the cache — are already on `app.state` at that point, and CORE-02 already established this pattern for the market source. One lifespan owns every background task, so nothing outlives the app. Rejected: lazy start on first request (shutdown has no natural owner) and piggybacking on the market source's tick loop (writes to the frozen `app/market/` module).

- **D-18:** The valuation arithmetic lives in **one pure function, `value_portfolio(cash, positions, prices)` in `app/services/portfolio.py`** — no I/O, no cache, no connection. It takes already-fetched rows and a prices dict and returns the per-position figures and the total. Because it is pure it is callable from inside the trade's executor thread (which D-01 requires) and unit-testable with literals, including the null-price case. All four consumers — `GET /api/portfolio`, the trade-time snapshot, the 30-second task and reset — share this one rule. Rejected: an async fetch-and-compute function (cannot be called from inside the trade transaction, so the trade would need a second copy of the arithmetic) and computed properties on a Pydantic model (derived values are full-precision per Phase 1's D-18 and the client recomputes them every SSE frame anyway).

**Response shapes**

- **D-19:** Phase 3's routes use **Pydantic request and response models**, declared in `app/api/models.py`, with `response_model` on each route. Phase 2's D-08 kept `/docs`, `/redoc` and `/openapi.json` enabled as a teaching feature; typed models are what makes that decision pay — a student can read every field and its type before calling anything. Nullable fields from D-14/D-15 become explicit `float | None` in the schema. `GET /api/health` stays a plain dict; **no Phase 1 code is edited to add models.**

- **D-20:** **Pydantic models declare shape only — the service owns every business rule.** `TradeRequest` declares `ticker: str`, `side: str`, `quantity: float` and nothing more: no `gt=0`, no constraints. Every quantity rule (zero, negative, `NaN`, `Infinity`, more than 4 decimal places) lives in one service-level validator that both the router and Phase 6 call, so there is one rule, one message and one place the tests point at. This also keeps PORT-06's status code correct — PLAN.md §8 specifies **400** for quantity failures, and a Pydantic constraint would return 422. Rejected: constraining in the model and restating in the service (two copies that drift) and constraining in the model only (Phase 6 never builds a `TradeRequest`, so LLM-supplied quantities would go unvalidated).

- **D-21:** `GET /api/portfolio/history` validates its query parameters with **FastAPI `Query` constraints** — `limit: int = Query(500, ge=1, le=5000)`, `since: str | None = None` — returning FastAPI's 422 on bad input and documenting the bounds in `/docs`. This is pure transport validation with exactly one caller (Phase 6 never reads history), so it does not conflict with D-20's service-owns-rules rule for trades. Rejected: accepting anything and letting SQL absorb it (`?limit=-1` would silently return an empty list, reading as "no history" rather than "bad request").

### Claude's Discretion

*Copied verbatim from `03-CONTEXT.md`. The user took the recommended option on every question, so no area was explicitly delegated. Left to the planner and executor:*

- Internal module decomposition beyond the file names fixed above, and whether the two routers live in one file or two
- The exact wording of every error message, subject to D-07's rule that they are shown to the user verbatim and PLAN.md §8's worked example
- Whether `side` is validated as a literal `"buy" | "sell"` in the model or in the service validator (D-20 makes the service authoritative either way)
- TEST-02's test file layout and fixture structure, subject to reusing Phase 1's `app` / `db_path` conftest fixtures per its D-22
- The snapshot task's exact sleep/cancel mechanics and how it behaves when the app is torn down mid-write
- Whether reset is expressed as its own composed transaction function or reuses parts of the trade one

### Deferred Ideas (OUT OF SCOPE)

*Copied verbatim from `03-CONTEXT.md` `<deferred>`.*

- **Confirmation UX for reset** — Phase 4. D-13 puts no guard in the API and explicitly assigns the confirmation step to the UI, where the user actually clicks. Recorded so it is not dropped.
- **Realistic snapshot-task-versus-`execute_trade` collision test** — Phase 1's D-20 proved the query layer under concurrency and deferred the realistic test to "once both real callers exist". Both now exist in this phase, so it is in scope here if the planner wants it; it is listed as a deferral only because Phase 1 named it as one.
- **`/api/chat` routing through `execute_trade` and `watchlist.add/remove`** — Phase 6 (CHAT-07, CHAT-08, CHAT-09). D-03 and D-06 exist to make that call site trivial.
- **Realized P&L and a trade history panel** — v2 (ANLY-01, ANLY-02). D-12's refusal to write synthetic trade rows is what keeps this derivable.
- **Fixing `test_custom_update_interval`** — owned by the frozen market module, not this phase.

### Additional hard scope boundaries (from CONTEXT.md `<domain>` and `<specifics>`)

- **`backend/app/market/` is frozen.** Consumed only through `PriceCache`, `wait_for_price`, `normalize_ticker` and `MarketDataSource`.
- **Phase 1's `app/db/` is consumed as it stands.** No decision in this phase edits `queries.py`, `connection.py`, `money.py`, `seed.py` or `schema.sql`. **The only Phase 1 file this phase modifies is `app/main.py`.**
- **Out of scope:** any frontend (Phase 4), charts (Phase 5), `/api/chat` and the LLM path (Phase 6), the lockfile Docker build and the Playwright E2E suite (Phase 7).
- No plan, task or success criterion may propose relocating the repo out of OneDrive, changing the `db/` bind-mount source, or untracking `db/finally.db`.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PORT-01 | Retrieve portfolio — cash, total value, per-position quantity, avg cost, current price, market value, unrealized P&L | `value_portfolio` pure function (Code Examples); `get_profile` + `get_positions` + `cache.get_all()`; D-14 null rule for priceless positions |
| PORT-02 | Buy at the server's price, cash decreases by the fill amount | `_apply_trade` composed unit of work (Pattern 2); `update_cash_balance` + `upsert_position` |
| PORT-03 | Sell shares held, cash increases by the fill amount | Same transaction; D-05 leaves `avg_cost` untouched on a sell |
| PORT-04 | Buy over cash → 400 naming need and have | `round_money(cost) > round_money(cash)` — exact comparison proven safe (all-in-buy verification); message form from PLAN.md §8 |
| PORT-05 | Sell over shares held → 400, no shorting | `remaining < 0 and not is_zero(remaining)` (Code Examples) |
| PORT-06 | Zero / negative / `NaN` / `Infinity` / >4dp quantity → 400 | `validate_quantity` with **isfinite before precision** — Pitfalls 2 and 3, both proven empirically |
| PORT-07 | Trading an unwatched ticker adds it to the watchlist as part of the trade | `add_watchlist_ticker` inside the same `writing()` block; `ON CONFLICT DO NOTHING` verified |
| PORT-08 | Priceless ticker waits up to 2s rather than failing | `await wait_for_price(cache, ticker, timeout=2.0)` — already built, do not reimplement (Don't Hand-Roll) |
| PORT-09 | Sell to zero deletes the position row | `is_zero(remaining)` → `delete_position`; epsilon 1e-6 residue behavior verified |
| PORT-10 | Response reports the server-side `fill_price` | `fill_price` is `wait_for_price`'s return value, captured before the transaction (D-02) |
| PORT-11 | Every trade writes a snapshot immediately | `insert_snapshot(conn, total_value)` inside the trade transaction, using `value_portfolio` with the pre-captured prices dict |
| PORT-12 | 30s background snapshot, skipping an unchanged total | D-16 `round_money` comparison against `get_latest_snapshot`; `_snapshot_loop` skeleton (Code Examples); sleep-first ordering per Pitfall 1 |
| PORT-13 | History with `?limit=` and `?since=` | `get_snapshots(conn, limit, since, user_id)` already exists; `Annotated[int, Query(ge=1, le=5000)]`; **Pitfall 5** on `since` format |
| PORT-14 | Reset to $10,000 cash and no positions | D-10..D-13; `STARTING_CASH` from `app.db.seed`; **Open Question 1** on the missing bulk-delete query |
| WATCH-01 | Watchlist with price, open price, change from open, ~60 history points | `cache.get_history(ticker)` (60 points, oldest first) + `PriceUpdate.open_price` / `.change_from_open_percent`; D-15 null rule |
| WATCH-02 | Add validated by `^[A-Z]{1,5}$` after uppercasing, else 400 | `normalize_ticker` raises plain `ValueError` — requires the bare-`ValueError`→400 handler (Pattern 3) |
| WATCH-03 | Adding registers the ticker with the live source | DB write first, then `await source.add_ticker()` (D-09); **Pitfall 4** — the simulator no-ops before `start()`, so tests need a fake source |
| WATCH-04 | Remove a ticker held no position in | `remove_watchlist_ticker` returns `rowcount == 1` |
| WATCH-05 | Remove a held ticker → 409, readable message | D-08 single-transaction check-and-delete (Pitfall 6); `Conflict` → 409 handler |
| WATCH-06 | Remove an unwatched ticker → 404 | `remove_watchlist_ticker` returning `False` → raise `NotFound` |
| TEST-02 | Tests cover trade execution and every rejection path | Validation Architecture § Requirements→Test Map and Wave 0 Gaps; baseline 243 tests |
</phase_requirements>

## Summary

This phase adds **no new dependencies and no new SQL**. Everything it needs already exists on disk and was read this session: `app/db/connection.py` supplies the transaction and offload seam (`connect`, `writing`, `run_db`, `ensure_initialized`, `get_db_path`), `app/db/queries.py` supplies all sixteen query functions, `app/db/money.py` supplies the three rounding/epsilon rules, and `app/market/` supplies `PriceCache`, `wait_for_price` and `normalize_ticker`. The work is therefore composition, not construction: four service modules, two router modules, one Pydantic model module, one exception-handler module, and three additions to `create_app()`.

The genuinely hard parts are three, and all three are settled by evidence rather than opinion. First, **`math.isfinite()` is mandatory** — this session proved empirically that a plain Pydantic `float` field accepts `Infinity` and `NaN` from a JSON body (`{"quantity": 1e999}` deserializes to `inf` because Python's `json` module produces `inf` for that literal, and `{"quantity": "NaN"}` coerces to `nan`), and that `round(float('inf'), 4)` returns `inf` rather than raising, so an isfinite check must run *before* the 4dp precision check. Second, **Starlette resolves exception handlers by walking `type(exc).__mro__` and taking the first registered class** (verified by reading the installed `starlette._exception_handler._lookup_exception_handler` source), which is exactly what makes D-06's `Conflict`/`NotFound`/`TradeError`-all-subclassing-`ValueError` taxonomy work — provided a handler is *also* registered for bare `ValueError`, because `normalize_ticker` and `wait_for_price` raise plain `ValueError` and would otherwise 500. Third, **the test `app` fixture overrides only the `get_db_path` dependency and does not set `app.state.db_path`**, so the D-17 snapshot task — which cannot use a FastAPI dependency — would write into the git-tracked repo database during any test that enters lifespan.

Money arithmetic needs no epsilon on the cash side and one epsilon on the share side. Compare `round_money(cost) > round_money(cash)` for the buy check (both are `round()` outputs, so equal decimals produce bit-identical floats — verified: an all-in buy of 52.4879 shares at $190.52 costs exactly $9999.99 against $10,000 and is not falsely rejected), and use the existing `is_zero()` for the sell-to-zero check (verified: `round_quantity(0.3) - round_quantity(0.1) - round_quantity(0.2)` leaves `-2.78e-17`, which `is_zero` correctly calls zero).

**Primary recommendation:** Build four services (`portfolio.py`, `trading.py`, `watchlist.py`, `errors.py`) as thin composers over `run_db(path, composed_fn, *args)`, register `ValueError`→400, `TradeError`→400, `NotFound`→404, `Conflict`→409 as app-level handlers, put the isfinite-then-precision quantity validator in one service function both the router and Phase 6 call, and fix the conftest `app` fixture to also set `application.state.db_path = db_path` before writing a single snapshot-task test.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Trade validation (ticker, quantity, side) | Service (`app/services/trading.py`) | — | D-20: two callers (router now, LLM in Phase 6); a Pydantic constraint would also return 422 where PLAN.md §8 requires 400 |
| Price lookup / 2s first-tick wait | Market module (`wait_for_price`) | Service orchestrates | Already built and tested; the service awaits it, nothing reimplements the loop |
| Read-modify-write of cash + position | Database (one `writing()` transaction inside one `run_db` call) | — | D-01: `BEGIN IMMEDIATE` is the only thing that makes concurrent trades safe |
| Portfolio valuation arithmetic | Pure function (`value_portfolio`) | — | D-18: must be callable from inside the executor thread, so it cannot be async or touch the cache |
| Error → HTTP status mapping | App-level exception handlers (`create_app()`) | — | D-07: services never import `HTTPException`; Phase 6 catches the same classes |
| Response shape / serialization | API tier (Pydantic models + `response_model`) | — | D-19: makes the retained `/docs` a teaching surface |
| Query-param bounds on `/history` | API tier (FastAPI `Query`) | — | D-21: pure transport validation, exactly one caller |
| Background 30s snapshot | Lifespan-owned asyncio task | Pure `value_portfolio` + `run_db` | D-17: one lifespan owns every background task |
| Ticker registration with the price feed | Market source (`MarketDataSource.add_ticker`) | Watchlist service orchestrates, DB write first | D-09: the DB row is the durable record |

## Standard Stack

### Core

No new packages. Every dependency this phase needs is already declared in `backend/pyproject.toml` and pinned in `backend/uv.lock` — both read this session.

| Library | Version (locked) | Purpose | Why Standard |
|---------|------------------|---------|--------------|
| `fastapi` | 0.141.1 | Routers, `Depends`, `Query`, exception handlers, `response_model` | Already the app framework; `>=0.141.1` floor exists for `app.frontend()` (SETUP-02) [VERIFIED: backend/uv.lock:352-354, backend/pyproject.toml:8] |
| `pydantic` | 2.12.5 | Request/response models (D-19) | Transitive requirement of FastAPI, declared explicitly at `>=2.10.0` [VERIFIED: backend/uv.lock:1225-1226, backend/pyproject.toml:14] |
| `sqlite3` (stdlib) | — | All persistence | Phase 1 D-01: no `aiosqlite` |
| `asyncio` (stdlib) | — | `to_thread` offload, snapshot task | Phase 1 D-01, D-17 |
| `math` (stdlib) | — | `math.isfinite` for PORT-06 | The only thing that stops `inf`/`nan` reaching the trade math |

### Supporting (dev / test)

| Library | Version (locked) | Purpose | When to Use |
|---------|------------------|---------|-------------|
| `pytest` | >=8.3.0 | Test runner | All of TEST-02 [VERIFIED: backend/pyproject.toml:21] |
| `pytest-asyncio` | 1.3.0 | `asyncio_mode = "auto"` — async tests need no decorator | Service-level async tests [VERIFIED: backend/uv.lock:1336-1337, backend/pyproject.toml:39] |
| `httpx` | 0.28.1 | Real-server integration tests | Only if a test needs a live uvicorn (SSE-style); route tests use `TestClient` [VERIFIED: backend/uv.lock:633-634] |
| `fastapi.testclient.TestClient` | — | Route status/shape tests | The established pattern in `backend/tests/api/test_health.py` |
| `ruff` | >=0.7.0 | Lint gate, `["E","F","I","N","W"]`, line-length 100 | `uv run --extra dev ruff check app/ tests/` [VERIFIED: backend/pyproject.toml:42-48] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `math.isfinite` in the service | Pydantic `Field(allow_inf_nan=False)` | **Rejected — locked by D-20.** Returns 422, not the 400 PLAN.md §8 requires, and Phase 6 never builds a `TradeRequest` so LLM quantities would bypass it |
| App-level exception handlers | `try/except` per route | **Rejected — locked by D-07** |
| `run_db` composed functions | A new `run_db_write()` helper | **Rejected — locked by D-01**; `app/db/connection.py` is frozen this phase |
| `Decimal` money | float + `round_money` | **Rejected — locked by Phase 1 D-15/money.py**; columns are REAL |

**Installation:** none. Do not run `uv add` in this phase. If a task appears to need a package, that is a signal the task is out of scope.

## Package Legitimacy Audit

**Not applicable — this phase installs zero external packages.** Every import it needs (`fastapi`, `pydantic`, stdlib `sqlite3`/`asyncio`/`math`/`datetime`) is already resolved in `backend/uv.lock`, which was read this session. `backend/pyproject.toml` must not be edited by this phase.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                    HTTP request (browser or, in Phase 6, the LLM path)
                                     |
                                     v
              +-------------------------------------------+
              |  app/api/portfolio.py  |  app/api/watchlist.py
              |  (router factories; Pydantic models in     |
              |   app/api/models.py; db_path via           |
              |   Depends(get_db_path); cache + source     |
              |   injected as factory arguments)           |
              +-------------------------------------------+
                                     |
                       raises ValueError subclasses
                                     |            \
                                     v             \--> app/api/errors.py
              +-------------------------------------+     register_exception_handlers(app)
              |  app/services/  trading | portfolio  |     ValueError  -> 400 {"detail": ...}
              |                 watchlist | errors   |     TradeError  -> 400
              |  - validate (cheap, no I/O)          |     NotFound    -> 404
              |  - await wait_for_price(...)  -------+---> Conflict    -> 409
              |  - capture prices = cache.get_all()  |
              |  - await run_db(path, _apply_x, ...) |
              +-------------------------------------+
                          |                    |
        reads (no txn)    |                    |  writes
                          v                    v
              +-----------------------------------------------+
              | app/db/connection.py                          |
              |  run_db -> asyncio.to_thread -> connect(path)  |
              |  ensure_initialized(path) (lazy, memoized)     |
              |  writing(conn) = BEGIN IMMEDIATE / COMMIT      |
              +-----------------------------------------------+
                                     |
                        app/db/queries.py (16 fns, frozen)
                                     |
                                     v
                        db/finally.db  (WAL, busy_timeout 5000ms)
                                     ^
                                     |
              +-----------------------------------------------+
              | lifespan-owned tasks (app/main.py create_app)  |
              |   "simulator-loop"  (existing, market source)  |
              |   "snapshot-loop"   (NEW, D-17, every 30s)     |
              +-----------------------------------------------+
                                     |
                    reads app.state.price_cache + app.state.db_path
                                     |
                                     v
              +-----------------------------------------------+
              | app/market/  PriceCache  (in-memory, threadsafe)|
              |   <- SimulatorDataSource / MassiveDataSource    |
              +-----------------------------------------------+
```

### Component Responsibilities (files this phase creates)

| File | Responsibility | Notes |
|------|----------------|-------|
| `app/services/__init__.py` | Public API docstring + re-exports | **Directory exists but has NO `__init__.py`** — must be created [VERIFIED: `ls -la backend/app/services` returns only `.` and `..`] |
| `app/services/errors.py` | `TradeError`, `NotFound`, `Conflict`, all subclassing `ValueError` (D-06) | No `HTTPException` import anywhere under `app/services/` |
| `app/services/portfolio.py` | `value_portfolio(cash, positions, prices)` pure fn (D-18); async `get_portfolio`, `get_history`, `reset_portfolio` | Pure fn must be importable by `trading.py` for the trade-time snapshot |
| `app/services/trading.py` | `execute_trade(db_path, cache, ticker, side, quantity) -> TradeResult` (D-03); `_apply_trade(conn, ...)` plain def (D-01); quantity validator | The contract Phase 6 routes through |
| `app/services/watchlist.py` | `get_watchlist(...)`, `add(...)`, `remove(...)`; `_remove_checked(conn, ticker)` plain def (D-08) | `add` writes DB first, then `await source.add_ticker()` (D-09) |
| `app/api/models.py` | Pydantic request/response models (D-19, D-20 — shape only, no constraints) | Nullable fields are `float \| None` (D-14/D-15) |
| `app/api/errors.py` | `register_exception_handlers(app)` | Keeps `main.py` short per the house rule |
| `app/api/portfolio.py` | `create_portfolio_router(price_cache)` | Follows `create_health_router` factory convention |
| `app/api/watchlist.py` | `create_watchlist_router(price_cache, source)` | Needs the source for D-09 |
| `app/api/__init__.py` | **Edit:** extend the "Public API" docstring list and `__all__` | Existing file lists only `create_health_router` [VERIFIED: backend/app/api/__init__.py:1-11] |
| `app/main.py` | **Edit (the only Phase 1 file this phase touches):** two `include_router` calls before `app.frontend()`, `register_exception_handlers(app)`, `snapshot-loop` task in lifespan | |
| `tests/services/__init__.py` | Test package marker | **Directory exists but has NO `__init__.py`** — must be created [VERIFIED: `ls -la backend/tests/services`] |

### Pattern 1: Router factory with mixed injection

The house convention is a `create_X_router(...)` factory (not a module-level router) so a second app instance does not double-register routes. The database path is the one thing that must come through `Depends`, because that is the seam the test fixture overrides.

```python
# Source: pattern read from backend/app/api/health.py:12-18 and backend/tests/conftest.py:44-58
from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from app.db.connection import get_db_path
from app.market import MarketDataSource, PriceCache


def create_watchlist_router(price_cache: PriceCache, source: MarketDataSource) -> APIRouter:
    """Build the /api/watchlist router bound to a specific cache and source."""
    router = APIRouter(prefix="/api", tags=["watchlist"])

    @router.get("/watchlist", response_model=WatchlistResponse)
    async def read_watchlist(db_path: Annotated[Path, Depends(get_db_path)]) -> WatchlistResponse:
        ...

    return router
```

Verbatim from the existing router this mirrors: `router = APIRouter(prefix="/api", tags=["system"])` [VERIFIED: backend/app/api/health.py:18].

### Pattern 2: Trade as one composed unit of work (D-01, D-02)

```python
# Composition of functions verified present in backend/app/db/queries.py and connection.py
def _apply_trade(
    conn: sqlite3.Connection,
    ticker: str,
    side: str,
    quantity: float,
    fill_price: float,
    prices: dict[str, float],
) -> dict[str, object]:
    """One BEGIN IMMEDIATE covering the whole trade. No PriceCache in this thread."""
    with writing(conn):
        add_watchlist_ticker(conn, ticker)          # PORT-07, no-ops on conflict
        profile = get_profile(conn)
        position = get_position(conn, ticker)
        ...                                          # cash / shares checks -> raise TradeError
        update_cash_balance(conn, new_cash)
        upsert_position(conn, ticker, new_qty, new_avg) or delete_position(conn, ticker)
        executed_at = insert_trade(conn, ticker, side, quantity, fill_price)
        insert_snapshot(conn, total_value)           # PORT-11
    return {...}
```

Called as `await run_db(db_path, _apply_trade, ticker, side, quantity, fill_price, prices)`.

`run_db`'s exact signature, read this session: `async def run_db(path: Path, fn: Callable[..., Any], *args: Any) -> Any` [VERIFIED: backend/app/db/connection.py:137] — it calls `ensure_initialized(path)` then `with connect(path) as conn: return fn(conn, *args)` inside `asyncio.to_thread`, so the composed function receives the connection first, matching every function in `queries.py`.

### Pattern 3: Exception handler registration, most-specific-wins

```python
# Source: https://fastapi.tiangolo.com/tutorial/handling-errors
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.errors import Conflict, NotFound, TradeError


def register_exception_handlers(app: FastAPI) -> None:
    """Map the service exception taxonomy onto PLAN.md section 8's envelope."""

    def _detail(exc: Exception, status: int) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status)

    app.add_exception_handler(Conflict, lambda r, e: _detail(e, 409))
    app.add_exception_handler(NotFound, lambda r, e: _detail(e, 404))
    app.add_exception_handler(TradeError, lambda r, e: _detail(e, 400))
    app.add_exception_handler(ValueError, lambda r, e: _detail(e, 400))
```

The bare-`ValueError` handler is **load-bearing, not belt-and-braces**: `normalize_ticker` raises `ValueError(f"Invalid ticker symbol: {raw!r}")` [VERIFIED: backend/app/market/tickers.py:21] and `wait_for_price` raises `ValueError(f"No price available for {ticker} yet, please try again")` [VERIFIED: backend/app/market/cache.py:157]. Neither is a `TradeError`. Without the `ValueError` row, WATCH-02's invalid symbol and PORT-08's timeout both become 500s.

### Anti-Patterns to Avoid

- **Registering the routers after `app.frontend()`.** `create_app()` currently ends `app.frontend("/", directory=STATIC_DIR, fallback="index.html")` [VERIFIED: backend/app/main.py:54]. New `include_router` calls go above that line. `tests/test_main.py::test_api_not_shadowed` is the existing guard.
- **Reading `PriceCache` inside the executor thread.** Legal (the cache is lock-protected) but forbidden by D-02: it makes the transaction depend on state that moves every 500ms and forces every trade test to build a live cache.
- **Adding a second ticker regex or a second rounding rule.** `normalize_ticker` and `money.py` are the single sources. `queries.py` already routes every ticker argument through `normalize_ticker` [VERIFIED: backend/app/db/queries.py:31, 85, 113, 165, 261, 277, 288].
- **Rounding derived values server-side.** `money.py`'s module docstring forbids it explicitly and deliberately exposes no helper for it [VERIFIED: backend/app/db/money.py:9-14]. `insert_snapshot` stores `total_value` at full float precision [VERIFIED: backend/app/db/queries.py:186-190].
- **Reformatting timestamps.** `_utc_now()` returns `dt.datetime.now(dt.UTC).isoformat()` [VERIFIED: backend/app/db/queries.py:337-339] — verified output `'2026-08-12T16:37:28.134072+00:00'`. Return `executed_at` and `recorded_at` exactly as stored.
- **Using `seed_fresh()` for reset.** It also inserts the ten default watchlist tickers [VERIFIED: backend/app/db/seed.py:79-82], which contradicts D-10. Read `STARTING_CASH` from `app.db.seed` instead (D-11).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Waiting up to 2s for a first tick (PORT-08) | An `asyncio.sleep` polling loop in the router | `await wait_for_price(cache, ticker, timeout=2.0)` | Already built, tested, and raises the user-facing message. `async def wait_for_price(cache: PriceCache, ticker: str, timeout: float = 2.0) -> float` [VERIFIED: backend/app/market/cache.py:145] |
| Ticker validation | A second `^[A-Z]{1,5}$` regex | `normalize_ticker(raw)` | One rule shared by manual and LLM paths [VERIFIED: backend/app/market/tickers.py:7-22] |
| "Is this position gone?" | `if quantity == 0` | `is_zero(remaining)` | Epsilon 1e-6; empirically `round_quantity(0.3)-round_quantity(0.1)-round_quantity(0.2)` = `-2.78e-17`, which `is_zero` correctly calls zero [VERIFIED: backend/app/db/money.py:56-65 + executed this session] |
| Rounding for storage | `round(x, 2)` inline | `round_money` / `round_quantity` | Rounding lives at the write boundary inside `queries.py`; callers pass raw values [VERIFIED: backend/app/db/queries.py:19-21, 58, 114-115, 167-168] |
| Auto-add on trade (PORT-07) | Read-then-insert | `add_watchlist_ticker(conn, ticker)` | `ON CONFLICT (user_id, ticker) DO NOTHING`, returns `cursor.rowcount == 1` [VERIFIED: backend/app/db/queries.py:258-263] |
| History with `?limit=`/`?since=` (PORT-13) | New SQL | `get_snapshots(conn, limit, since, user_id)` | Already binds both as parameters [VERIFIED: backend/app/db/queries.py:210-228] |
| Sparkline history (WATCH-01) | Accumulating points in the service | `cache.get_history(ticker)` | Returns up to 60 points oldest-first, already backfilled at startup and on add [VERIFIED: backend/app/market/cache.py:106-110, HISTORY_POINTS = 60 at line 12] |
| Trade timestamp | A second `datetime.now()` | The return value of `insert_trade` | It returns the `executed_at` it actually wrote [VERIFIED: backend/app/db/queries.py:146, 158, 172] |
| Concurrency safety | A Python `Lock` around trades | `writing(conn)` inside `run_db` | `BEGIN IMMEDIATE` takes the write lock up front; `busy_timeout=5000` absorbs contention [VERIFIED: backend/app/db/connection.py:31, 63, 85] |

**Key insight:** Phase 1's load-bearing scope note ("every query function lands in Phase 1") means the correct instinct in this phase is always *"which existing function does this?"* — never *"what SQL do I write?"* The one exception the researcher found: **there is no `delete_all_positions` query for PORT-14's reset.** See Open Questions.

## Runtime State Inventory

Not applicable — this is a greenfield feature phase, not a rename/refactor/migration. No stored strings change meaning, no OS registrations exist, no env var names change, no build artifacts carry a stale name.

One adjacent runtime-state fact worth recording: **`db/finally.db` is tracked in git** (PROJECT.md accepted risk, Phase 1 D-23 reseeded it). Any code path that writes to the *real* `DB_PATH` during a test run dirties the working tree. See Pitfall 1.

## Common Pitfalls

### Pitfall 1: The test `app` fixture does not override `app.state.db_path` — the snapshot task will write to the tracked repo database

**What goes wrong:** `tests/conftest.py` sets `application.dependency_overrides[get_db_path] = lambda: db_path` and nothing else [VERIFIED: backend/tests/conftest.py:56-58]. `create_app()` sets `app.state.db_path = DB_PATH` [VERIFIED: backend/app/main.py:50], and `DB_PATH` resolves to `PROJECT_ROOT / "db" / "finally.db"` [VERIFIED: backend/app/config.py:22]. A lifespan-owned background task cannot use `Depends`, so D-17's snapshot loop must read `app.state.db_path` — the un-overridden real path. Any test entering lifespan (`tests/test_main.py`'s `live_app` fixture serves the app from uvicorn; `test_lifespan_starts_and_stops_source` uses `app.router.lifespan_context(app)`) would then have a background task writing snapshot rows into the git-tracked database.

**Why it happens:** the dependency-override seam and the `app.state` seam are two different doors, and Phase 1 only had request-scoped callers.

**How to avoid:** two independent mitigations, apply both.
1. Add one line to the conftest `app` fixture: `application.state.db_path = db_path`. This is a *test* file, not `app/db/`, so it does not violate the phase freeze — but it is a change to Phase 1's fixture and should be an explicit task, not an incidental edit.
2. Order the snapshot loop **sleep-first, write-second** (`while True: await asyncio.sleep(30); ...`). With a 30-second interval no existing test runs long enough to reach the first write even if mitigation 1 were forgotten.

**Warning signs:** `git status` shows `db/finally.db` modified after `pytest`; snapshot counts in unrelated tests drift.

### Pitfall 2: A plain Pydantic `float` accepts `Infinity` and `NaN` (PORT-06)

**What goes wrong:** `{"quantity": 1e999}` deserializes to `inf` and `{"quantity": "NaN"}` to `nan`, both passing a `quantity: float` field cleanly. Verified this session against the installed pydantic 2.12.5:

```
{"quantity": 1e999}     -> inf  isfinite=False
{"quantity": "NaN"}     -> nan  isfinite=False
{"quantity": "Infinity"}-> inf  isfinite=False
```

Python's own `json.loads('{"q": 1e999}')` yields `{'q': inf}`, so this is not a Pydantic quirk — it is the JSON layer.

**Why it happens:** `allow_inf_nan` defaults to true on Pydantic float fields, and lax-mode string→float coercion uses `float()`, which parses `"NaN"` and `"Infinity"`.

**How to avoid:** the service validator checks `math.isfinite(quantity)` first. D-20 forbids fixing this with a Pydantic constraint (wrong status code, and Phase 6 bypasses the model entirely).

**Warning signs:** an `inf` cash balance in the database; a position with `nan` quantity that no comparison ever matches.

### Pitfall 3: `round(float('inf'), 4)` returns `inf` — check order matters

**What goes wrong:** the natural 4dp precision test is `round_quantity(q) != q`. For `q = inf`, `round(inf, 4)` returns `inf` (verified this session — it does not raise), so `inf != inf` is `False` and the precision check *passes*. If `isfinite` runs second, an infinite quantity slips through.

**How to avoid:** fixed order in one validator: `isfinite` → `> 0` → `round_quantity(q) == q`. D-04 already fixes the outer order (cheap checks → price → balance); this is the inner order.

**Warning signs:** none until the trade math produces `inf` cash.

### Pitfall 4: `SimulatorDataSource.add_ticker` is a silent no-op before `start()`

**What goes wrong:** `async def add_ticker(self, ticker)` begins `if self._sim is None: return` [VERIFIED: backend/app/market/simulator.py:260-262]. The `app` fixture does not run lifespan [VERIFIED: backend/tests/conftest.py:52-54 docstring: "Lifespan has not run yet, so the cache is empty and the market source is unstarted"]. So in a `TestClient(app)` route test, WATCH-03's `await source.add_ticker(...)` registers nothing and produces no price — and a subsequent trade on that ticker will spend a real 2 seconds in `wait_for_price` and then 400.

**How to avoid:** route/service tests seed the cache directly, exactly as `tests/api/test_health.py` does: `app.state.price_cache.update("AAPL", 190.50)` [VERIFIED: backend/tests/api/test_health.py:42]. Reserve the "adding a ticker really produces prices" assertion for one lifespan-driving test.

**Warning signs:** a trade test that takes >2s and 400s with "No price available".

### Pitfall 5: `since` string comparison is format-sensitive

**What goes wrong:** `get_snapshots` compares `recorded_at >= ?` as a plain string [VERIFIED: backend/app/db/queries.py:225]. Stored values look like `'2026-08-12T16:37:28.134072+00:00'`. A client sending PLAN.md §8's `Z` form (`2026-07-25T14:00:00Z`) compares as *greater* than a same-second stored value, because `'Z'` (0x5A) sorts above `'.'` (0x2E) — verified this session: `'2026-08-12T16:00:00Z' > '2026-08-12T16:00:00.123456+00:00'` is `True`. Sub-second boundary rows get silently dropped.

**Why it happens:** PLAN.md's illustrative examples use `Z`; Phase 1's `_utc_now()` uses `isoformat()`'s `+00:00`. Both are valid ISO 8601 UTC; they do not sort compatibly.

**How to avoid:** document in the route docstring and the OpenAPI description that `since` must be in the same format `recorded_at` returns (i.e. echo a `recorded_at` value straight back). Do **not** normalize inside the service — that would create a second timestamp rule and `queries.py` is frozen. Add a test that round-trips a real `recorded_at` value as `since`.

**Warning signs:** the P&L chart in Phase 5 missing its most recent points after an incremental fetch.

### Pitfall 6: Held-position check and delete must share one transaction (WATCH-05)

**What goes wrong:** `get_position` then `remove_watchlist_ticker` as two `run_db` calls opens a window in which a concurrent trade creates the position between the check and the delete, breaking the "every position has a live price feed" invariant.

**How to avoid:** D-08 — one composed function passed to `run_db` that opens `writing(conn)`, calls `get_position`, raises `Conflict` if held, then `remove_watchlist_ticker`. `writing()` rolls back and re-raises on exception [VERIFIED: backend/app/db/connection.py:85-92], so raising `Conflict` inside it is safe and leaves nothing committed.

**Warning signs:** a position whose ticker is not on the watchlist and therefore has no price.

### Pitfall 7: Order of operations in `_apply_trade` around watchlist auto-add

**What goes wrong:** if `add_watchlist_ticker` runs *after* the cash check raises, the ticker is not added — correct. If it runs before and the trade then fails, the rollback in `writing()` un-does it — also correct. But if the auto-add is done in a *separate* `run_db` call before the transaction, a rejected trade leaves an orphan watchlist row.

**How to avoid:** keep `add_watchlist_ticker` inside the same `writing()` block as everything else. `writing()` rolls back the whole unit.

### Pitfall 8: `avg_cost` is stored via `round_quantity`, not `round_money`

`upsert_position` calls `round_quantity(avg_cost)` [VERIFIED: backend/app/db/queries.py:115]. This is deliberate (4dp for a derived ratio, per `money.py`'s docstring and Phase 1 D-15) and looks like a bug to a reviewer. Do not "fix" it, and do not pre-round `avg_cost` in the service — pass the raw computed value and let the write boundary round it once.

## Code Examples

### The quantity validator (PORT-06) — the one place, both callers

```python
# Ordering proven this session: round(float('inf'), 4) returns inf, so isfinite must run first.
from __future__ import annotations

import math

from app.db.money import round_quantity

from .errors import TradeError


def validate_quantity(quantity: float) -> float:
    """Validate a share quantity and return it. Raises TradeError (400) otherwise.

    One rule, called by the trade router and by Phase 6's LLM path, so an
    LLM-supplied quantity cannot bypass what a manual one is held to.
    """
    if not math.isfinite(quantity):
        raise TradeError(f"Quantity must be a finite number, got {quantity}")
    if quantity <= 0:
        raise TradeError(f"Quantity must be greater than zero, got {quantity}")
    if round_quantity(quantity) != quantity:
        raise TradeError(f"Quantity may have at most 4 decimal places, got {quantity}")
    return quantity
```

### Sufficiency checks — cash exact, shares by epsilon

```python
# Verified this session: an all-in buy of 52.4879 shares at 190.52 costs exactly 9999.99
# against a 10000.0 balance, and round_money(cost) > round_money(cash) is False.
cost = round_money(fill_price * quantity)
cash = profile["cash_balance"]
if cost > round_money(cash):
    raise TradeError(f"Insufficient cash: need ${cost:.2f}, have ${cash:.2f}")

# Sell side: is_zero closes the residue gap (verified: 0.3 - 0.1 - 0.2 leaves -2.78e-17).
held = position["quantity"] if position else 0.0
remaining = held - quantity
if remaining < 0 and not is_zero(remaining):
    raise TradeError(f"Insufficient shares: tried to sell {quantity} {ticker}, hold {held}")
if is_zero(remaining):
    delete_position(conn, ticker)          # PORT-09
else:
    upsert_position(conn, ticker, remaining, position["avg_cost"])   # D-05: avg_cost untouched
```

The error string `Insufficient cash: need $1905.20, have $800.00` is PLAN.md §8's worked example and should be matched character-for-character in form.

### `value_portfolio` — the one pure valuation rule (D-18, D-14)

```python
def value_portfolio(
    cash: float,
    positions: list[sqlite3.Row],
    prices: dict[str, float],
) -> tuple[list[dict[str, object]], float]:
    """Per-position figures and the total. No I/O, no cache, no connection.

    A position with no price reports nulls and is excluded from the total: the
    client renders a dash rather than a fabricated number (D-14).
    """
    rows: list[dict[str, object]] = []
    total = cash
    for position in positions:
        price = prices.get(position["ticker"])
        if price is None:
            rows.append({..., "current_price": None, "market_value": None,
                         "unrealized_pnl": None, "unrealized_pnl_percent": None})
            continue
        market_value = position["quantity"] * price
        cost_basis = position["quantity"] * position["avg_cost"]
        rows.append({..., "current_price": price, "market_value": market_value,
                     "unrealized_pnl": market_value - cost_basis,
                     "unrealized_pnl_percent": (market_value - cost_basis) / cost_basis * 100})
        total += market_value
    return rows, total
```

Derived values are returned unrounded — `money.py`'s docstring makes this a rule, not a style choice [VERIFIED: backend/app/db/money.py:9-14].

### Snapshot loop in lifespan (D-17, PORT-12)

```python
# Cancel pattern copied verbatim from SimulatorDataSource.stop (backend/app/market/simulator.py:248-256).
SNAPSHOT_INTERVAL_SECONDS = 30.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await source.start(list(DEFAULT_TICKERS))
    task = asyncio.create_task(
        _snapshot_loop(app.state.db_path, cache), name="snapshot-loop"
    )
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await source.stop()


async def _snapshot_loop(db_path: Path, cache: PriceCache) -> None:
    """Record portfolio value every 30 seconds, skipping an unchanged total.

    Sleeps first so a short-lived test app never reaches a write.
    """
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL_SECONDS)
        prices = {t: u.price for t, u in cache.get_all().items()}
        await run_db(db_path, _record_if_changed, prices)
```

D-16's skip rule is `round_money(new_total) == round_money(last_total)`, reading the last value from `get_latest_snapshot(conn)` [VERIFIED: backend/app/db/queries.py:194-207].

**Note the lifespan ordering:** the existing lifespan is `await source.start(...)` / `yield` / `await source.stop()` [VERIFIED: backend/app/main.py:43-45]. D-17 says the snapshot task is started beside `source.start()` and cancelled *before* `source.stop()` — the skeleton above follows that.

## Exact Existing Symbols (cite these verbatim, do not guess)

### `backend/app/db/connection.py`
```
BUSY_TIMEOUT_MS = 5000                                                     # line 31
@contextmanager connect(path: Path) -> Iterator[sqlite3.Connection]        # line 41
@contextmanager writing(conn: sqlite3.Connection) -> Iterator[...]         # line 74
ensure_initialized(path: Path) -> None                                     # line 98
get_db_path(request: Request) -> Path                                      # line 125
async run_db(path: Path, fn: Callable[..., Any], *args: Any) -> Any        # line 137
```
[VERIFIED: backend/app/db/connection.py:31-150]

### `backend/app/db/money.py`
```
MONEY_PLACES = 2 ; QUANTITY_PLACES = 4 ; QUANTITY_EPSILON = 1e-6           # lines 28-30
round_money(value: float) -> float                                         # line 33
round_quantity(value: float) -> float                                      # line 46
is_zero(value: float) -> bool                                              # line 56
```
[VERIFIED: backend/app/db/money.py:28-65]

### `backend/app/db/seed.py`
```
DEFAULT_USER_ID = "default" ; STARTING_CASH = 10000.0                      # lines 33-34
DEFAULT_TICKERS: tuple[str, ...] = ("AAPL","GOOGL","MSFT","AMZN","TSLA",
                                    "NVDA","META","JPM","V","NFLX")        # lines 36-47
apply_schema(conn) / is_fresh_database(conn) -> bool / seed_fresh(conn, user_id=DEFAULT_USER_ID)
```
[VERIFIED: backend/app/db/seed.py:33-87]

### `backend/app/db/queries.py` — every function this phase calls
```
get_profile(conn, user_id=DEFAULT_USER_ID) -> sqlite3.Row | None                        # 39
update_cash_balance(conn, new_balance: float, user_id=...) -> None                       # 47
get_positions(conn, user_id=...) -> list[sqlite3.Row]                                    # 65
get_position(conn, ticker: str, user_id=...) -> sqlite3.Row | None                       # 78
upsert_position(conn, ticker: str, quantity: float, avg_cost: float, user_id=...) -> None # 89
delete_position(conn, ticker: str, user_id=...) -> None                                  # 121
insert_trade(conn, ticker, side, quantity, price, user_id=...) -> str   # returns executed_at  # 139
insert_snapshot(conn, total_value: float, user_id=...) -> None                           # 178
get_latest_snapshot(conn, user_id=...) -> sqlite3.Row | None                             # 194
get_snapshots(conn, limit=500, since: str | None = None, user_id=...) -> list[sqlite3.Row] # 210
get_watchlist(conn, user_id=...) -> list[sqlite3.Row]                                    # 234
add_watchlist_ticker(conn, ticker, user_id=...) -> bool                                  # 246
remove_watchlist_ticker(conn, ticker, user_id=...) -> bool                               # 266
is_ticker_watched(conn, ticker, user_id=...) -> bool                                     # 282
_utc_now() -> str    # 'YYYY-MM-DDTHH:MM:SS.ffffff+00:00'                                # 337
```
Row column sets, verbatim from the SELECT lists:
- profile: `id, cash_balance, created_at`
- position: `id, user_id, ticker, quantity, avg_cost, updated_at`
- snapshot: `id, total_value, recorded_at`
- watchlist: `id, user_id, ticker, added_at`

[VERIFIED: backend/app/db/queries.py:39-339]

### `backend/app/market/` (frozen)
```
PriceCache.get(ticker) -> PriceUpdate | None                              # cache.py:93
PriceCache.get_price(ticker) -> float | None                              # cache.py:97
PriceCache.get_all() -> dict[str, PriceUpdate]                            # cache.py:101
PriceCache.get_history(ticker) -> list[float]   # oldest first, <= 60     # cache.py:106
PriceCache.newest_timestamp() -> float | None                             # cache.py:112
PriceCache.version -> int                                                 # cache.py:119
HISTORY_POINTS = 60                                                       # cache.py:12
async wait_for_price(cache, ticker, timeout: float = 2.0) -> float        # cache.py:145
  raises ValueError(f"No price available for {ticker} yet, please try again")  # cache.py:157

PriceUpdate fields: ticker, price, previous_price, open_price, timestamp  # models.py:17-21
PriceUpdate props: change, change_percent, direction,
                   change_from_open, change_from_open_percent, to_dict()  # models.py:25-72

TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}$")                              # tickers.py:7
normalize_ticker(raw: str) -> str                                         # tickers.py:10
  raises ValueError(f"Invalid ticker symbol: {raw!r}")                    # tickers.py:21

MarketDataSource: source_name (property), async start(tickers: list[str]),
  async stop(), async add_ticker(ticker: str), async remove_ticker(ticker: str),
  get_tickers() -> list[str]                                              # interface.py:22-49
```
[VERIFIED: backend/app/market/cache.py:12-158, models.py:17-72, tickers.py:7-22, interface.py:22-49]

### `backend/app/main.py` (the only Phase 1 file this phase edits)
```
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"             # line 20
create_app() -> FastAPI                                                    # line 23
  cache = PriceCache() ; source = create_market_data_source(cache)         # lines 31-32
  lifespan: await source.start(list(DEFAULT_TICKERS)) / yield / await source.stop()  # 43-45
  app = FastAPI(title="FinAlly", lifespan=lifespan)                        # line 47
  app.state.price_cache / app.state.market_source / app.state.db_path      # lines 48-50
  app.include_router(create_health_router(cache, source))                  # line 52
  app.include_router(create_stream_router(cache))                          # line 53
  app.frontend("/", directory=STATIC_DIR, fallback="index.html")           # line 54  <-- MUST STAY LAST
```
[VERIFIED: backend/app/main.py:20-55]

### `backend/tests/conftest.py` (reuse verbatim per D-22)
```
event_loop_policy (fixture)                                                # line 17
_no_massive_api_key (session-scoped, autouse)                              # line 25
db_path(tmp_path) -> Path      # tmp_path / "finally.db"                   # line 39
app(db_path) -> FastAPI        # create_app() + dependency_overrides[get_db_path]  # line 45
```
[VERIFIED: backend/tests/conftest.py:16-58]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `lifespan=` async context manager | FastAPI 0.93 / Starlette | Already adopted (CORE-02); the snapshot task joins the existing lifespan, never a startup event |
| `q: int = Query(500, ge=1)` | `q: Annotated[int, Query(ge=1, le=5000)] = 500` | FastAPI 0.95+ | Annotated is the documented modern form [CITED: fastapi.tiangolo.com/tutorial/path-params-numeric-validations] |
| `app.routes` to enumerate routes | `app.openapi()["paths"]` | FastAPI 0.141 | `include_router()` now appends an `_IncludedRouter` wrapper rather than flattening — already documented in `tests/test_main.py:88-91` |
| Ad-hoc `try/except HTTPException` per route | App-level `add_exception_handler` | Stable FastAPI API | D-07; handlers resolve by MRO, most-specific-first |

**Deprecated/outdated:** nothing in this phase's surface is deprecated. Do not introduce `aiosqlite`, `SQLAlchemy`, `Decimal`, or a second charting/validation library.

## Project Constraints (from CLAUDE.md)

Extracted from `./CLAUDE.md`, `./.claude/CLAUDE.md`, `backend/CLAUDE.md`, and `~/.claude/CLAUDE.md`. The planner must verify every plan against these.

| # | Directive | Applies to this phase as |
|---|-----------|--------------------------|
| C-1 | No overengineering, no defensive programming; exception managers only when needed | No speculative `try/except`; `writing()` already handles rollback |
| C-2 | Identify root cause before fixing; prove with evidence | Do not chase `test_custom_update_interval` (known tolerated flake) |
| C-3 | Work incrementally, validate each increment | Wave structure: services before routers before wiring |
| C-4 | Use latest library APIs | `Annotated[..., Query(...)]`, `lifespan=`, `add_exception_handler` |
| C-5 | `uv run xxx` never `python3 xxx`; `uv add xxx` never `pip install` | All test/lint commands are `uv run --extra dev ...` from `backend/` |
| C-6 | Clear, concise docstring comments; sparing inline comments | Every module/class/public function gets a docstring carrying the *why* |
| C-7 | Short modules, short methods and functions; name things clearly | Every existing `app/market/` and `app/db/` module is under ~200 lines; match that |
| C-8 | **Never use emojis** in code, print statements, or logging | Includes docstrings and log messages |
| C-9 | `from __future__ import annotations` first in every module | Every new file |
| C-10 | Full type hints on every signature including private helpers | Including `_apply_trade`, `_snapshot_loop` |
| C-11 | ruff `["E","F","I","N","W"]`, line-length 100, target py312 | `uv run --extra dev ruff check app/ tests/` must pass |
| C-12 | `%s`-style lazy formatting in log calls, never f-strings | `logger.info("Trade executed: %s %s %s", side, quantity, ticker)` |
| C-13 | Raise, don't swallow | Services raise; only the app-level handlers translate |
| C-14 | Router factories, not module-level routers | `create_portfolio_router(...)`, `create_watchlist_router(...)` |
| C-15 | Test files mirror their module 1:1 | `app/services/trading.py` → `tests/services/test_trading.py` |
| C-16 | Explicit `__all__` + "Public API" docstring in each package `__init__.py` | New `app/services/__init__.py`; extend `app/api/__init__.py` |
| C-17 | Mount order: `StaticFiles`/`app.frontend()` after every `/api/*` router | The single most consequential wiring rule |
| C-18 | Timestamps: SSE = epoch float; REST + every `*_at` column = ISO 8601 UTC string | Never mix in one payload |
| C-19 | Use Context7 MCP for library docs rather than training data | Applied in this research |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `Conflict` should be raised *inside* `writing()` and rely on its ROLLBACK, rather than checked before `BEGIN IMMEDIATE` | Pitfall 6 / Pattern 2 | Low — `writing()`'s rollback-and-reraise is verified [connection.py:88-90]; the alternative merely reopens the race D-08 exists to close |
| A2 | Error message wording beyond PLAN.md §8's one worked example | Code Examples | Low — CONTEXT.md explicitly delegates exact wording to the planner/executor |
| A3 | `total_cost` is the field name for a sell's proceeds as well as a buy's cost | Response shapes | Low — PLAN.md §8's shape lists `total_cost` with no side-specific variant; the frontend contract (Phase 4) is written against it |
| A4 | `GET /api/portfolio/history` returns snapshots **newest first** | Response shapes | Low — `get_snapshots`' docstring says "Snapshots newest first" and the SQL is `ORDER BY recorded_at DESC` [queries.py:216, 226]; PLAN.md §8's example has one element so it does not disambiguate. Phase 5's chart will need to reverse |
| A5 | Reset should delete positions with per-ticker `delete_position` calls in a loop | Open Question 1 | Medium — see Open Questions; a per-ticker loop is correct but O(n) statements |
| A6 | `side` accepts only lowercase `"buy"`/`"sell"` | Trade rules | Low — PLAN.md §7 schema comment says `side TEXT ("buy" or "sell")` and the LLM schema in §9 emits lowercase; a case-insensitive normalize in the validator is the safe reading |

## Open Questions (RESOLVED)

All three questions are answered below and each answer is carried into the plans: Q1's per-ticker
delete loop into `03-03` Task 2, Q2's explicit single-line conftest task into `03-05` Task 2, and
Q3's no-special-casing into `03-04`. Nothing here is still open.

1. **(RESOLVED)** **PORT-14 reset has no bulk-delete query, and `app/db/queries.py` is frozen.**
   - What we know: `delete_position(conn, ticker, user_id)` deletes exactly one ticker [VERIFIED: backend/app/db/queries.py:121]. There is no `delete_all_positions`. `get_positions(conn)` returns every row [queries.py:65]. CONTEXT.md's `<specifics>` says a task appearing to need a new query function is "a signal to re-read `queries.py` first" — but this one genuinely does not exist.
   - What's unclear: whether the intended composition is `for row in get_positions(conn): delete_position(conn, row["ticker"])` inside one `writing()` block, or whether an exception to the freeze is warranted.
   - Recommendation: **use the loop.** It reuses the existing function, stays inside one `BEGIN IMMEDIATE`, is at most ~12 statements for a realistic portfolio, and keeps the freeze intact. Do not add a query function.
   - Resolution: adopted verbatim in `03-03` Task 2 (`_apply_reset` iterates `get_positions` and calls `delete_position` per row inside one `writing()` block), with the freeze on `app/db/` intact.

2. **(RESOLVED)** **Should the conftest `app` fixture be modified (Pitfall 1)?**
   - What we know: D-22 says "Phase 3's route tests reuse this fixture verbatim"; CONTEXT.md's freeze names `app/db/` files and says `main.py` is the only Phase 1 *app* file edited — it does not name `tests/conftest.py`.
   - What's unclear: whether "verbatim" is a prohibition on extending the fixture.
   - Recommendation: **make it an explicit, single-line task with the rationale in the plan** (`application.state.db_path = db_path`), and pair it with the sleep-first snapshot loop so correctness does not depend on the fixture change alone. Flag it for the plan-checker rather than doing it silently.
   - Resolution: adopted verbatim as `03-05` Task 2, a task of its own carrying the rationale, paired with `03-05` Task 1's sleep-first loop ordering as the second independent mitigation.

3. **(RESOLVED)** **Does the watchlist response include tickers the user holds but somehow un-watched?**
   - What we know: the invariant runs one way only — every position is watched, not every watched ticker is held (CONTEXT.md `<specifics>`). `GET /api/watchlist` reads `get_watchlist(conn)`, which is pure database state (D-15).
   - Recommendation: no special-casing. Database state is the answer.
   - Resolution: adopted verbatim in `03-04` — `read_watchlist` returns one entry per `get_watchlist` row and nothing else, and a held-but-unwatched ticker cannot arise because every trade auto-adds its ticker (PORT-07) and a held ticker cannot be removed (WATCH-05).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Everything | ✓ | 3.12+ (`requires-python = ">=3.12"`) | — |
| `uv` | All commands | ✓ | in use — `uv run --extra dev pytest --collect-only -q` succeeded this session | — |
| `fastapi` | Routers, handlers | ✓ | 0.141.1 (locked) | — |
| `pydantic` | Models | ✓ | 2.12.5 (locked) | — |
| `pytest` + `pytest-asyncio` | TEST-02 | ✓ | pytest-asyncio 1.3.0, `asyncio_mode = "auto"` | — |
| `httpx` | Live-server tests | ✓ | 0.28.1 (locked, dev extra) | `TestClient` suffices for all Phase 3 route tests |
| `ruff` | Lint gate | ✓ | >=0.7.0 (dev extra) | — |
| SQLite (stdlib) | Persistence | ✓ | bundled; WAL + `busy_timeout` proven by `tests/db/test_concurrency.py` | — |
| Docker | Not needed | — | — | Phase 3 is backend unit/route tests only |
| Node/npm | Not needed | — | — | Frontend is Phase 4 |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none.

**Baseline for the regression gate:** `243 tests collected` [VERIFIED: `uv run --extra dev pytest --collect-only -q` executed this session, 2026-08-12]. The known tolerated flake is `tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval` (Phase 1 D-24, `02-.../deferred-items.md`) — do not chase it.

## Validation Architecture

`workflow.nyquist_validation` is `true` [VERIFIED: .planning/config.json].

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=8.3.0 with pytest-asyncio 1.3.0 |
| Config file | `backend/pyproject.toml` → `[tool.pytest.ini_options]` (`testpaths = ["tests"]`, `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"`) [VERIFIED: backend/pyproject.toml:34-40] |
| Quick run command | `cd backend && uv run --extra dev pytest tests/services tests/api -q` |
| Full suite command | `cd backend && uv run --extra dev pytest -q` |
| Lint gate | `cd backend && uv run --extra dev ruff check app/ tests/` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| PORT-01 | Portfolio read: cash, total, per-position figures | unit + route | `pytest tests/services/test_portfolio.py tests/api/test_portfolio.py -q` | ❌ Wave 0 |
| PORT-02 | Buy decreases cash by fill amount | service | `pytest tests/services/test_trading.py -k buy -q` | ❌ Wave 0 |
| PORT-03 | Sell increases cash by fill amount | service | `pytest tests/services/test_trading.py -k sell -q` | ❌ Wave 0 |
| PORT-04 | Buy over cash → 400 + message naming need/have | service + route | `pytest tests/services/test_trading.py -k insufficient_cash -q` | ❌ Wave 0 |
| PORT-05 | Sell over shares held → 400 | service | `pytest tests/services/test_trading.py -k insufficient_shares -q` | ❌ Wave 0 |
| PORT-06 | 0 / negative / NaN / Infinity / >4dp → 400 | unit (parametrized) | `pytest tests/services/test_trading.py -k quantity -q` | ❌ Wave 0 |
| PORT-07 | Unwatched ticker auto-added by the trade | service | `pytest tests/services/test_trading.py -k auto_add -q` | ❌ Wave 0 |
| PORT-08 | 2s wait on a priceless ticker, then fill | service (fake cache populated on a timer) | `pytest tests/services/test_trading.py -k wait -q` | ❌ Wave 0 |
| PORT-09 | Sell to zero deletes the row | service | `pytest tests/services/test_trading.py -k delete_at_zero -q` | ❌ Wave 0 |
| PORT-10 | Response carries the server-side `fill_price` | route | `pytest tests/api/test_portfolio.py -k fill_price -q` | ❌ Wave 0 |
| PORT-11 | Every trade writes a snapshot | service | `pytest tests/services/test_trading.py -k snapshot -q` | ❌ Wave 0 |
| PORT-12 | 30s task writes on change, skips on no-change | unit (call the loop body directly, not the sleep) | `pytest tests/services/test_snapshots.py -q` | ❌ Wave 0 |
| PORT-13 | `?limit=` and `?since=` | route | `pytest tests/api/test_portfolio.py -k history -q` | ❌ Wave 0 |
| PORT-14 | Reset → $10k, no positions, watchlist untouched | service + route | `pytest tests/services/test_portfolio.py -k reset -q` | ❌ Wave 0 |
| WATCH-01 | Price, open, change-from-open, ~60 history points | route | `pytest tests/api/test_watchlist.py -k read -q` | ❌ Wave 0 |
| WATCH-02 | Invalid symbol → 400 | route | `pytest tests/api/test_watchlist.py -k invalid -q` | ❌ Wave 0 |
| WATCH-03 | Add registers with the live source | service (fake source recording calls) | `pytest tests/services/test_watchlist.py -k register -q` | ❌ Wave 0 |
| WATCH-04 | Remove an unheld ticker succeeds | route | `pytest tests/api/test_watchlist.py -k remove -q` | ❌ Wave 0 |
| WATCH-05 | Remove a held ticker → 409, readable message | service + route | `pytest tests/api/test_watchlist.py -k conflict -q` | ❌ Wave 0 |
| WATCH-06 | Remove an unwatched ticker → 404 | route | `pytest tests/api/test_watchlist.py -k not_found -q` | ❌ Wave 0 |
| TEST-02 | Aggregate: trade execution + every rejection path | suite | `pytest tests/services -q` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && uv run --extra dev pytest tests/services tests/api -q` plus `ruff check app/ tests/`
- **Per wave merge:** `cd backend && uv run --extra dev pytest -q` — must be **≥ 243 + new tests passing**, with at most the one known `test_custom_update_interval` flake
- **Phase gate:** full suite green (allowing one retry of the known flake) before `/gsd-verify-work`

Rationale for the rate: the trade path is a read-modify-write on money with six independent rejection branches. Anything less than running the whole `tests/services` package per commit lets a rounding or ordering regression in one branch hide behind a passing sibling.

### Wave 0 Gaps

- [ ] `backend/app/services/__init__.py` — package does not exist (directory is empty)
- [ ] `backend/tests/services/__init__.py` — test package does not exist (directory is empty)
- [ ] `backend/tests/services/test_trading.py` — covers PORT-02..PORT-11, TEST-02
- [ ] `backend/tests/services/test_portfolio.py` — covers PORT-01, PORT-14
- [ ] `backend/tests/services/test_watchlist.py` — covers WATCH-03, WATCH-05
- [ ] `backend/tests/services/test_snapshots.py` — covers PORT-12
- [ ] `backend/tests/api/test_portfolio.py` — covers PORT-01, PORT-10, PORT-13, status codes
- [ ] `backend/tests/api/test_watchlist.py` — covers WATCH-01, WATCH-02, WATCH-04, WATCH-05, WATCH-06
- [ ] A shared fixture for a **fake `MarketDataSource`** that records `add_ticker`/`remove_ticker` calls — needed because `SimulatorDataSource.add_ticker` no-ops before `start()` (Pitfall 4). Put it in `tests/services/conftest.py`, not the root conftest, so Phase 1's fixtures stay untouched
- [ ] Framework install: **none required** — pytest, pytest-asyncio, httpx and ruff are already in the `dev` extra

## Security Domain

`workflow.security_enforcement` is `true`, `security_asvs_level` is `1` [VERIFIED: .planning/config.json].

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | No login by design (REQUIREMENTS.md "Out of Scope"); `user_id` is a hardcoded `"default"` column for future multi-user |
| V3 Session Management | no | No sessions |
| V4 Access Control | partial | Business-rule authorization only: no shorting (sell ≤ held), no margin (buy ≤ cash), no removing a held ticker. Enforced in the service layer inside `BEGIN IMMEDIATE`, never in the router |
| V5 Input Validation | **yes** | `normalize_ticker` (`^[A-Z]{1,5}$`) for every symbol; `math.isfinite` + `> 0` + 4dp for every quantity; `Annotated[int, Query(ge=1, le=5000)]` for `limit` |
| V5.3 Output Encoding / Injection | **yes** | Every statement in `queries.py` binds `?` placeholders; no SQL text is assembled by interpolation, "not for a ticker, not for a limit, not for a user id" [VERIFIED: backend/app/db/queries.py:9-12]. This phase writes **zero** SQL, which is the strongest possible control |
| V6 Cryptography | no | No secrets handled by this phase |
| V7 Error Handling / Logging | **yes** | Error messages are designed to be shown to the user verbatim and must therefore contain no filesystem paths, no stack traces, and no API keys. `{"detail": str(exc)}` only |
| V13 API | **yes** | Correct status codes (400/404/409), typed response models, bounded query params |

### Known Threat Patterns for FastAPI + SQLite

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via `ticker` or `limit` | Tampering | Parameterized statements only — already true across `queries.py`; this phase adds no SQL |
| TOCTOU double-spend (two concurrent buys both pass the cash check) | Tampering | `writing()` = `BEGIN IMMEDIATE` around the whole read-modify-write (D-01), with `busy_timeout=5000` |
| `Infinity`/`NaN` quantity corrupting the cash balance | Tampering / DoS | `math.isfinite` before any arithmetic (Pitfall 2, verified empirically) |
| Unbounded `?limit=` exhausting memory | DoS | `Query(ge=1, le=5000)` (D-21) |
| Unbounded ticker cardinality via repeated adds (each add spawns a simulated series) | DoS | Out of scope for a single-operator localhost app; `^[A-Z]{1,5}$` caps the namespace at ~12M and the risk is accepted by the no-auth design |
| Information disclosure in error bodies | Info disclosure | `{"detail": str(exc)}` where `exc` is a service-authored message; never `repr()` of an internal exception, never a path |
| Blocking the event loop and stalling the SSE stream | DoS | All DB work goes through `run_db`'s `asyncio.to_thread` (CORE-10); no new synchronous DB call may be added |

**ASVS L1 verdict:** this phase introduces no new attack surface class. Its security work is entirely "keep using the controls Phase 1 built and do not open a second door."

## Sources

### Primary (HIGH confidence)
- Live codebase, read this session with `Read`: `backend/app/db/{connection,money,queries,seed,schema.sql,__init__}.py`, `backend/app/market/{cache,models,interface,tickers,__init__}.py`, `backend/app/market/simulator.py` (lines 200-285), `backend/app/{main,config}.py`, `backend/app/api/{health,__init__}.py`, `backend/tests/{conftest,test_main}.py`, `backend/tests/api/test_health.py`, `backend/tests/db/test_concurrency.py`, `backend/pyproject.toml`, `backend/uv.lock`
- Executed this session: `uv run --extra dev python -c ...` proving Pydantic float accepts `inf`/`nan`, `round(inf, 4) == inf`, the all-in-buy cash comparison, `is_zero` residue behavior, `_utc_now()` output format, `Z`-vs-`+00:00` string ordering, Starlette's `_lookup_exception_handler` MRO walk, and `RequestValidationError.__mro__` (not a `ValueError`)
- `uv run --extra dev pytest --collect-only -q` → `243 tests collected`
- Project documents: `planning/PLAN.md` §§6-8, `.planning/{REQUIREMENTS,ROADMAP,config.json}`, `.planning/phases/01-foundation-spine/01-CONTEXT.md`, `.planning/phases/02-walking-skeleton-container/deferred-items.md`, `.planning/phases/03-portfolio-watchlist-apis/03-CONTEXT.md`

### Secondary (MEDIUM confidence)
- [CITED: fastapi.tiangolo.com/tutorial/handling-errors] — `@app.exception_handler(ExcClass)` / `add_exception_handler`, handler signature `(request, exc)`, `JSONResponse(status_code=..., content=...)` (via Context7 `/websites/fastapi_tiangolo`)
- [CITED: fastapi.tiangolo.com/tutorial/path-params-numeric-validations] — `Annotated[int, Query(ge=..., le=...)]` is the documented modern form (via Context7)
- [CITED: fastapi.tiangolo.com/advanced/events] — lifespan `@asynccontextmanager` shape (via Context7)

### Tertiary (LOW confidence)
- None. Every claim in this document is either read from a file in this repo this session, executed this session, or cited to official FastAPI documentation.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — zero new packages; every version read from the committed lockfile
- Architecture: **HIGH** — every symbol, signature and line number read from source this session; the shape is locked by CONTEXT.md D-01..D-21
- Pitfalls: **HIGH** — the three highest-severity pitfalls (inf/NaN, round(inf), conftest `db_path` gap) were each proven by execution or by reading the exact file, not recalled
- Security: **HIGH** for the controls (all pre-existing and read), MEDIUM for the ASVS category mapping (judgement applied to a no-auth localhost app)

**Research date:** 2026-08-12
**Valid until:** 2026-09-11 (30 days — stable stack, pinned lockfile; the only invalidator would be an edit to `backend/app/db/` or `backend/app/market/`, both of which this phase freezes)
