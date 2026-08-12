# Phase 3: Portfolio & Watchlist APIs - Context

**Gathered:** 2026-08-12
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase makes the money real. Phase 1 landed every SQLite query function and Phase 2 wrapped the spine in a container; this phase builds the service layer and the HTTP routes on top of them, so cash, positions and watched tickers become readable, tradeable and rule-enforced.

**In scope:** `app/services/portfolio.py`, `app/services/trading.py`, `app/services/watchlist.py`, `app/services/errors.py`; `app/api/portfolio.py` and `app/api/watchlist.py` routers; `GET /api/portfolio`, `POST /api/portfolio/trade`, `POST /api/portfolio/reset`, `GET /api/portfolio/history`, `GET/POST /api/watchlist`, `DELETE /api/watchlist/{ticker}`; the full trade rule set (PORT-02..PORT-11); the 30-second snapshot background task (PORT-12); Pydantic request/response models for these routes; the app-level exception handlers; and TEST-02's trade execution and rejection-path tests.

**Out of scope:** any frontend (Phase 4), charts (Phase 5), `/api/chat` and the LLM path (Phase 6), the real lockfile Docker build and the Playwright E2E suite (Phase 7). No new SQL query function should be needed — if one is, that is a signal to re-read `app/db/queries.py` first.

**Frozen:** `backend/app/market/` is untouched, consumed only through `PriceCache`, `wait_for_price`, `normalize_ticker` and `MarketDataSource`. Phase 1's `app/db/` is consumed as it stands — **no decision in this phase edits `queries.py`, `connection.py`, `money.py`, `seed.py` or `schema.sql`.** The only Phase 1 file this phase modifies is `app/main.py`, to register the new routers, the exception handlers and the snapshot task.

</domain>

<decisions>
## Implementation Decisions

### Trade as one unit of work

- **D-01:** A trade is **one composed function passed to `run_db`**. `app/services/trading.py` defines a plain `def _apply_trade(conn, ...)` that opens `writing(conn)` and calls `get_profile`, `get_position`, `upsert_position`, `update_cash_balance`, `insert_trade`, `insert_snapshot` and `add_watchlist_ticker` in sequence. One connection, one `BEGIN IMMEDIATE`, no read-then-write race. Rejected: adding a `run_db_write()` helper to `connection.py` (edits Phase 1 code two phases already build against), and two `run_db` calls (opens a window where the snapshot task or a concurrent trade changes cash between the check and the write). — **Reversibility:** costly — this is the shape `execute_trade` is written in, and the ROADMAP records that function's signature as a contract Phase 6 must route through.

- **D-02:** The **prices used for the trade-time snapshot are captured before the transaction opens** and passed in as a plain `{ticker: price}` dict. The async service calls `cache.get_all()` (or equivalent), then hands the dict to `_apply_trade`. The thread function never touches `PriceCache`, so it stays pure, is testable with literal dicts, and the snapshot value agrees with the fill price the user was just quoted. Rejected: reading the cache inside the executor thread (legal, since `PriceCache` is thread-safe, but makes the transaction depend on state that moves every 500ms and forces every trade test to build a live cache), and snapshotting after commit in a second write (a crash between the two leaves a trade with no P&L step, violating PORT-11's "immediately").

- **D-03:** The service seam signature is **`async def execute_trade(db_path, cache, ticker, side, quantity) -> TradeResult`** — explicit arguments in, a dataclass out. The service owns validation, the `wait_for_price` call and the transaction. No FastAPI object crosses the seam, so Phase 6's LLM path passes exactly what the router passes. Rejected: a Pydantic request model as the parameter (couples the service to an HTTP shape Phase 6 has no natural instance of) and a bundled context object (hides what the function depends on). — **Reversibility:** costly — `.planning/ROADMAP.md` states these signatures are a contract, and Phase 6 (CHAT-07) is planned against them.

- **D-04:** Validation runs in the order **cheap checks → price → balance**. Ticker format and quantity rules validate first with no I/O; then `await wait_for_price(cache, ticker, timeout=2.0)`; then the transaction checks cash on a buy or shares held on a sell. A malformed quantity therefore returns 400 immediately rather than after a two-second wait, and the PORT-08 wait only ever runs for input that could actually fill.

- **D-05:** `avg_cost` arithmetic: on a **buy**, `avg_cost = (old_qty * old_avg + fill_qty * fill_price) / new_qty`, stored at 4dp per Phase 1's D-15. On a **sell**, quantity drops and `avg_cost` is untouched — cost basis per share does not change when you sell some of a holding. A sell to zero deletes the row (PORT-09), so `avg_cost` never survives with no shares. Realized P&L stays deliberately untracked. Rejected: recomputing `avg_cost` by replaying the `trades` table, which would make the append-only audit log a read dependency of the trade path — PLAN.md §7 is explicit that `trades` has no reader.

### How service failures become status codes

- **D-06:** `app/services/errors.py` defines a **small exception taxonomy — `TradeError` (400), `NotFound` (404), `Conflict` (409) — all subclassing `ValueError`**, so Phase 1's raise-a-`ValueError`-with-a-user-facing-message style and `wait_for_price`'s existing `ValueError` both still fit. Services never import `HTTPException`. Phase 6 catches the same classes and reads `str(exc)` for CHAT-09's per-action error text. Rejected: plain `ValueError` everywhere (the router cannot tell 409 from 400, so the held-position rule ends up restated in the route) and returning a result object instead of raising (a forgotten `ok` check silently succeeds, which inverts the raise-don't-swallow rule). — **Reversibility:** costly — Phase 6's per-action error reporting is planned against these classes.

- **D-07:** **One app-level exception handler per error class**, registered in `create_app()`, returning `JSONResponse({"detail": str(exc)}, status_code=...)`. This produces PLAN.md §8's envelope verbatim, every route inherits it, and a new service raising `Conflict` is correctly a 409 the day it is written. Rejected: `try/except` in each route (seven routes repeating the same three-branch block, and a new route silently 500s if its author forgets) and a dependency wrapper (an indirection layer to understand before any route reads clearly). Messages are written to be shown to the user verbatim — e.g. `Insufficient cash: need $1905.20, have $800.00`.

- **D-08:** The **WATCH-05 held-position check and the watchlist delete share one `writing()` transaction**. `services/watchlist.remove()` passes a composed function to `run_db` that opens `writing(conn)`, calls `get_position`, raises `Conflict` if a position is held, then calls `remove_watchlist_ticker`. Same unit-of-work shape as D-01, so both services read alike, and the invariant "every position has a live price feed" holds under concurrency rather than probabilistically. Rejected: check-then-delete in two calls, and a schema-level foreign key or trigger — the latter would edit Phase 1's `schema.sql` after `db/finally.db` is already tracked in git, and would turn a readable 409 message into a translated SQLite error.

- **D-09:** On watchlist add, the **database write happens first, then `await source.add_ticker()`**. The watchlist row is the durable record and the source is restarted from it on every boot. If `add_ticker` fails, the row still exists and the ticker gets a feed on the next start — a missing price is visible and self-healing, whereas an orphaned feed is neither. Rejected: registering with the source first (a failed DB write leaves the simulator streaming a ticker nobody watches, with nothing to clean it up) and a rollback wrapper (defensive machinery for a failure `SimulatorDataSource.add_ticker` cannot realistically produce).

### Reset (PORT-14)

- **D-10:** **Reset touches the portfolio only.** Cash returns to `STARTING_CASH`, every position row is deleted, and one snapshot is written at the new total. The **watchlist, `trades` and `chat_messages` are left completely alone.** This is the narrowest reading of "reset to the starting state: $10,000 cash and no positions", it keeps the append-only `trades` rule intact, and it does not contradict Phase 1's D-09 gate (an emptied watchlist stays empty). Consequence, deliberately accepted: after a reset the user keeps whatever tickers they had added, and the P&L chart shows the reset as a visible step rather than restarting flat. Rejected: full first-launch state (silently discards user-added tickers) and clearing `portfolio_snapshots` (the chart loses the record that a reset happened).

- **D-11:** The endpoint is **`POST /api/portfolio/reset`**, a verb-shaped sub-resource matching `/api/portfolio/trade`, returning **the same body as `GET /api/portfolio`** so the client's refetch rule needs no special case. It reads `app.db.seed.STARTING_CASH` rather than restating `10000.0` — this is the reuse Phase 1's deferred note asked for. It does **not** call `seed_fresh()`, which also writes the ten default watchlist tickers and would contradict D-10. Rejected: `DELETE /api/portfolio` (reads oddly for a resource that still exists afterwards, and collides conceptually with `DELETE /api/watchlist/{ticker}`).

- **D-12:** Reset **writes a snapshot and never writes a trade row.** The snapshot goes inside the reset transaction so `GET /api/portfolio/history` is never stale and the P&L chart shows the step. Nothing is appended to `trades` — a reset is not a sale, and synthetic sell rows would corrupt the audit log that realized P&L would later be derived from (PROJECT.md keeps that derivable). Rejected: writing neither (leaves history reporting a portfolio value that no longer exists for up to 30 seconds) and writing synthetic sells.

- **D-13:** **Reset has no API-level guard** — no confirmation token, no required body field. `POST` and it happens, exactly like a trade. It is fake money in a single-operator localhost simulator, and PLAN.md deliberately gives trades no confirmation dialog; any confirmation belongs in the Phase 4 UI where the user actually clicks. Recorded so Phase 4 owns that step and it is not dropped.

### Valuation and the snapshot task

- **D-14:** A held ticker with **no price in the cache returns nulls, and is excluded from `total_value`.** `current_price`, `market_value` and `unrealized_pnl` come back as `null` for that position; `total_value` is cash plus only those positions that have a price. This is the honest answer — the client renders a dash rather than a wrong number — and Phase 4's UI-15 empty-state work has something real to render. Rejected: falling back to `avg_cost` (presents a fabricated price as real, and a stalled feed would look like a flat portfolio rather than a broken one) and calling `wait_for_price` per position (`GET /api/portfolio` is refetched after every trade and would block for seconds).

- **D-15:** The **same null rule applies to `GET /api/watchlist`.** A ticker with no price yet is **always present in the response** — the watchlist is database state, not cache state — with `price`, `open_price` and `change_from_open_percent` as `null` and `history` as `[]`. Rejected: omitting priceless tickers (a ticker the user just added would be missing from the list they just added it to, reading as a failed add) and returning zeros (`$0.00` is a real price a client will happily render and multiply).

- **D-16:** PORT-12's "unchanged" means **`round_money(new_total) == round_money(last_total)`** — cents-rounded comparison, reusing Phase 1's `money.py` rather than inventing a second precision rule. The skip genuinely fires on an all-cash portfolio, which is the idle and first-launch case; a held portfolio writing a row every 30 seconds is correct, because the value really did change and the P&L chart needs the point. Rejected: exact float equality (two identical cash-only values can still differ in the last bit after arithmetic, so the requirement would be satisfied in code and not in behavior) and a third epsilon constant alongside `MONEY_PLACES` and `QUANTITY_EPSILON`.

- **D-17:** The snapshot task is an **`asyncio` task created in `create_app()`'s lifespan**, started beside `source.start()` and cancelled before `source.stop()`, named per the house convention (`asyncio.create_task(..., name="snapshot-loop")`). Both dependencies — the DB path and the cache — are already on `app.state` at that point, and CORE-02 already established this pattern for the market source. One lifespan owns every background task, so nothing outlives the app. Rejected: lazy start on first request (shutdown has no natural owner) and piggybacking on the market source's tick loop (writes to the frozen `app/market/` module).

- **D-18:** The valuation arithmetic lives in **one pure function, `value_portfolio(cash, positions, prices)` in `app/services/portfolio.py`** — no I/O, no cache, no connection. It takes already-fetched rows and a prices dict and returns the per-position figures and the total. Because it is pure it is callable from inside the trade's executor thread (which D-01 requires) and unit-testable with literals, including the null-price case. All four consumers — `GET /api/portfolio`, the trade-time snapshot, the 30-second task and reset — share this one rule. Rejected: an async fetch-and-compute function (cannot be called from inside the trade transaction, so the trade would need a second copy of the arithmetic) and computed properties on a Pydantic model (derived values are full-precision per Phase 1's D-18 and the client recomputes them every SSE frame anyway).

### Response shapes

- **D-19:** Phase 3's routes use **Pydantic request and response models**, declared in `app/api/models.py`, with `response_model` on each route. Phase 2's D-08 kept `/docs`, `/redoc` and `/openapi.json` enabled as a teaching feature; typed models are what makes that decision pay — a student can read every field and its type before calling anything. Nullable fields from D-14/D-15 become explicit `float | None` in the schema. `GET /api/health` stays a plain dict; **no Phase 1 code is edited to add models.**

- **D-20:** **Pydantic models declare shape only — the service owns every business rule.** `TradeRequest` declares `ticker: str`, `side: str`, `quantity: float` and nothing more: no `gt=0`, no constraints. Every quantity rule (zero, negative, `NaN`, `Infinity`, more than 4 decimal places) lives in one service-level validator that both the router and Phase 6 call, so there is one rule, one message and one place the tests point at. This also keeps PORT-06's status code correct — PLAN.md §8 specifies **400** for quantity failures, and a Pydantic constraint would return 422. Rejected: constraining in the model and restating in the service (two copies that drift) and constraining in the model only (Phase 6 never builds a `TradeRequest`, so LLM-supplied quantities would go unvalidated).

- **D-21:** `GET /api/portfolio/history` validates its query parameters with **FastAPI `Query` constraints** — `limit: int = Query(500, ge=1, le=5000)`, `since: str | None = None` — returning FastAPI's 422 on bad input and documenting the bounds in `/docs`. This is pure transport validation with exactly one caller (Phase 6 never reads history), so it does not conflict with D-20's service-owns-rules rule for trades. Rejected: accepting anything and letting SQL absorb it (`?limit=-1` would silently return an empty list, reading as "no history" rather than "bad request").

### Claude's Discretion

The user took the recommended option on every question, so no area was explicitly delegated. Left to the planner and executor:

- Internal module decomposition beyond the file names fixed above, and whether the two routers live in one file or two
- The exact wording of every error message, subject to D-07's rule that they are shown to the user verbatim and PLAN.md §8's worked example
- Whether `side` is validated as a literal `"buy" | "sell"` in the model or in the service validator (D-20 makes the service authoritative either way)
- TEST-02's test file layout and fixture structure, subject to reusing Phase 1's `app` / `db_path` conftest fixtures per its D-22
- The snapshot task's exact sleep/cancel mechanics and how it behaves when the app is torn down mid-write
- Whether reset is expressed as its own composed transaction function or reuses parts of the trade one

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product specification (authoritative for behavior and shapes)
- `planning/PLAN.md` §7 — the six-table schema and, critically, the "What Is Not Tracked" note: realized P&L has no column, and `trades` is an audit log with no reader
- `planning/PLAN.md` §8 — the endpoint table, every request/response shape, the `{"detail": ...}` error envelope, the 400/404/409 mapping, and the full Trade Rules list (server-side fill price, 2s price wait, 4dp quantity, delete-at-zero, auto-add-to-watchlist, snapshot per trade)
- `planning/PLAN.md` §6 — `open_price` and `change_from_open_percent`, which `GET /api/watchlist` surfaces
- `planning/PLAN.md` §13 — build order; this phase is steps 2 (remainder) and 3

### Phase scope and constraints
- `.planning/ROADMAP.md` — Phase 3's goal, its five success criteria, and the **"Service seam" note**: `services/trading.execute_trade()` and `services/watchlist.add/remove()` signatures are a contract Phase 6 must route through
- `.planning/REQUIREMENTS.md` — PORT-01..PORT-14, WATCH-01..WATCH-06, TEST-02. Note PORT-14 is `[NEW]` and has no PLAN.md specification, which is why D-10..D-13 exist
- `.planning/PROJECT.md` — Key Decisions. The OneDrive location, the `db/` bind mount and the tracked `db/finally.db` are accepted risks, not tasks. Realized P&L is deliberately out of scope

### Phase 1 contracts this phase builds on
- `.planning/phases/01-foundation-spine/01-CONTEXT.md` — D-01/D-02 (plain `def` query functions, one `run_db` offload seam), D-05 (`writing()` for writes only), D-06 (`get_db_path` dependency), D-15/D-17/D-18 (rounding at the write boundary, derived values full precision), D-22 (test fixture reuse), and the deferred note asking that reset reuse the seed helper rather than restating `$10,000`
- `backend/app/db/queries.py` — **every query function this phase needs already exists.** Read it before writing any SQL
- `backend/app/db/connection.py` — `run_db`, `writing`, `connect`, `ensure_initialized`, `get_db_path`
- `backend/app/db/money.py` and `backend/app/db/seed.py` — `round_money`, `round_quantity`, `is_zero`, `STARTING_CASH`, `DEFAULT_TICKERS`
- `backend/app/main.py` — `create_app()`, the lifespan that starts and stops the market source, and the `app.frontend()` call that must stay registered last
- `backend/app/api/health.py` — the `create_X_router(...)` factory convention this phase's routers follow

### Phase 2 decisions this phase inherits
- `.planning/phases/02-walking-skeleton-container/02-CONTEXT.md` — D-08 (`/docs` stays enabled, which is what makes D-19's response models worth writing) and the stale-map warning below

### Market module surface (frozen)
- `backend/CLAUDE.md` — the market data public API as it is meant to be consumed
- `backend/app/market/cache.py` — `wait_for_price(cache, ticker, timeout=2.0)`, `get_history()`, `get_all()`, `get_price()`, and the `open_price` / `change_from_open_percent` fields on `PriceUpdate`
- `backend/app/market/interface.py` — `add_ticker` / `remove_ticker` / `get_tickers` on `MarketDataSource`

### Code style
- `.planning/codebase/CONVENTIONS.md` — style rules this phase must match

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`app.market.wait_for_price(cache, ticker, timeout=2.0)`** — PORT-08 is **already built**. It polls every 200ms and raises `ValueError` with a user-facing message on timeout. Do not reimplement the wait loop.
- **`app/db/queries.py`** — all sixteen query functions this phase calls already exist and are tested: `get_profile`, `update_cash_balance`, `get_positions`, `get_position`, `upsert_position`, `delete_position`, `insert_trade`, `insert_snapshot`, `get_latest_snapshot`, `get_snapshots`, `get_watchlist`, `add_watchlist_ticker`, `remove_watchlist_ticker`, `is_ticker_watched`. **PORT-07's auto-add is a call to `add_watchlist_ticker`, which already no-ops on conflict.**
- **`get_snapshots(conn, limit, since, user_id)`** — already takes both `limit` and `since` and binds them as parameters, so PORT-13 is a route over an existing function.
- **`normalize_ticker` / `TICKER_PATTERN`** — the one `^[A-Z]{1,5}$` rule. `queries.py` already routes every ticker argument through `normalize_ticker`, so the service layer must not add a second regex.
- **`round_money`, `round_quantity`, `is_zero`, `STARTING_CASH`, `DEFAULT_TICKERS`** — exported from `app.db`. D-16's skip rule and D-11's reset both consume these rather than restating constants.
- **`PriceCache.get_history(ticker)`** — returns up to 60 points oldest-first, exactly WATCH-01's sparkline payload. Already backfilled at startup and on ticker add.
- **Phase 1's conftest fixtures** — `db_path` (a `tmp_path` file per test) and `app` (an app with `get_db_path` overridden). D-22 says Phase 3's route tests reuse these verbatim.

### Established Patterns

- `from __future__ import annotations` as the first import in every module
- Full type hints on every signature, including private helpers
- Docstrings carry the "why"; inline comments are rare
- `ruff` with `["E", "F", "I", "N", "W"]`, line-length 100, target py312
- `%s`-style lazy formatting in log calls, never f-strings; **no emojis anywhere**
- Router factories, not module-level routers: `create_health_router(cache, source)`
- Test files mirror their module 1:1 — `app/services/trading.py` → `tests/services/test_trading.py`. `tests/services/` and `tests/api/` already exist
- Raise, don't swallow; no defensive `try/except` for conditions that cannot occur

### Integration Points

- **`create_app()`** gains three things and nothing else: `include_router` calls for the portfolio and watchlist routers (registered **before** the existing `app.frontend()` call — the mount-order hazard), the D-07 exception handlers, and the D-17 snapshot task in the lifespan.
- **`app.state`** already carries `price_cache`, `market_source` and `db_path`. The watchlist service needs `market_source` (D-09), which no route has reached for yet — a dependency for it is new surface.
- **`run_db(path, fn, *args)`** is the single door into the database. D-01, D-08 and D-11 all pass composed functions through it rather than adding a second offload path.
- **`tests/services/`** exists as an empty package awaiting exactly this phase.

### Stale map warning

`.planning/codebase/*.md` are dated 2026-08-04, **before Phase 1**. They state that no FastAPI app, no `app/db/` and no `.env.example` exist; all three now do. Scout the live tree rather than trusting those maps. `.planning/codebase/CONVENTIONS.md` is still accurate for style.

### Known tolerated flake

`tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval` fails roughly 3 runs in 10 on Windows for platform timer-granularity reasons (Phase 1 D-24, and `02-.../deferred-items.md`). It is pre-existing, owned by the frozen market module, and must not be chased as a Phase 3 regression.

</code_context>

<specifics>
## Specific Ideas

- **`app/db/` is closed for edits.** If a task appears to need a new query function, that is a signal to re-read `queries.py` first — Phase 1's load-bearing scope note put every query there specifically so Phase 3 would not have to touch it. The one Phase 1 file this phase modifies is `main.py`.
- **The seam signatures are a contract, not a suggestion.** `.planning/ROADMAP.md` records `execute_trade()` and `watchlist.add/remove()` as the exact functions Phase 6 will call. Changing their shape later means replanning Phase 6.
- **Nulls, not zeros, and never a fabricated price.** D-14 and D-15 are the same rule applied twice. A position or ticker without a live price reports `null` and is excluded from totals — the client renders a dash. Zero is a price; absent is not.
- **PORT-12's skip is mostly about the idle case.** D-16 is honest about this: with a held portfolio under GBM the value genuinely changes every 30 seconds, so the row is written and should be. The skip exists so an all-cash portfolio does not accumulate identical rows.
- **PORT-14 is `[NEW]` with no PLAN.md text.** D-10 through D-13 are the whole specification. A reviewer should not expect to find it in `planning/PLAN.md` and conclude something is missing.
- **Reset leaves tickers watched with no position.** That is intentional and does not break anything — the invariant runs the other way (every position is watched), not both ways.

</specifics>

<deferred>
## Deferred Ideas

- **Confirmation UX for reset** — Phase 4. D-13 puts no guard in the API and explicitly assigns the confirmation step to the UI, where the user actually clicks. Recorded so it is not dropped.
- **Realistic snapshot-task-versus-`execute_trade` collision test** — Phase 1's D-20 proved the query layer under concurrency and deferred the realistic test to "once both real callers exist". Both now exist in this phase, so it is in scope here if the planner wants it; it is listed as a deferral only because Phase 1 named it as one.
- **`/api/chat` routing through `execute_trade` and `watchlist.add/remove`** — Phase 6 (CHAT-07, CHAT-08, CHAT-09). D-03 and D-06 exist to make that call site trivial.
- **Realized P&L and a trade history panel** — v2 (ANLY-01, ANLY-02). D-12's refusal to write synthetic trade rows is what keeps this derivable.
- **Fixing `test_custom_update_interval`** — owned by the frozen market module, not this phase.

</deferred>

---

*Phase: 3-Portfolio & Watchlist APIs*
*Context gathered: 2026-08-12*
