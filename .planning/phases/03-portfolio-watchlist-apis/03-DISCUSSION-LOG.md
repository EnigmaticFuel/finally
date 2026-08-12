# Phase 3: Portfolio & Watchlist APIs - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-12
**Phase:** 3-Portfolio & Watchlist APIs
**Areas discussed:** Trade as one unit of work, How service failures become status codes, What reset actually wipes (PORT-14), Valuation gaps and the snapshot skip rule, Response shapes and remaining edges

---

## Trade as one unit of work

### Q1 — Where does the BEGIN IMMEDIATE boundary get drawn?

| Option | Description | Selected |
|--------|-------------|----------|
| One composed fn to run_db (Recommended) | `_apply_trade(conn, ...)` opens `writing(conn)` and calls the existing query functions in sequence. One connection, one write lock, no read-then-write race. Phase 1 code untouched. | ✓ |
| Add run_db_write() to connection.py | Same shape, but the `writing()` wrap lives in one place for future write services. Cost: edits a Phase 1 module two phases build against. | |
| Two run_db calls: read, then write | Easiest to read linearly, but opens a window where the snapshot task or a concurrent trade changes cash between check and write. | |

**User's choice:** One composed fn to run_db
**Notes:** Became D-01. The same shape is reused for the watchlist 409 check (D-08) and reset (D-11).

### Q2 — Where do the live prices for the trade-time snapshot come from?

| Option | Description | Selected |
|--------|-------------|----------|
| Pass a prices dict in (Recommended) | Async service captures `cache.get_all()` before the transaction and passes `{ticker: price}`. Thread function stays pure and testable; snapshot agrees with the quoted fill price. | ✓ |
| Read the cache inside the thread | Legal (PriceCache is thread-safe) but the transaction depends on state moving every 500ms, and every trade test needs a live cache. | |
| Snapshot after commit, second write | Simpler transaction, but a crash between the two leaves a trade with no P&L step — violates PORT-11's "immediately". | |

**User's choice:** Pass a prices dict in
**Notes:** Became D-02. This purity is what later made D-18's `value_portfolio()` callable from inside the executor thread.

### Q3 — What is the execute_trade() seam signature?

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit args, dataclass out (Recommended) | `async def execute_trade(db_path, cache, ticker, side, quantity) -> TradeResult`. No FastAPI object crosses the seam, so Phase 6 passes what the router passes. | ✓ |
| Pydantic model in and out | Fewer shapes and richer /docs, but couples the service to an HTTP request model Phase 6 has no instance of. | |
| Pass app.state or a context object | Shortest call sites, but hides dependencies and makes test setup indirect. | |

**User's choice:** Explicit args, dataclass out
**Notes:** Became D-03. ROADMAP.md records this signature as a contract, so it carries a `costly` reversibility rating.

### Q4 — What order do validation, the price wait, and the balance check run in?

| Option | Description | Selected |
|--------|-------------|----------|
| Cheap checks, price, then balance (Recommended) | Format and quantity first with no I/O, then `wait_for_price`, then the transaction's cash/shares check. Bad quantity returns 400 instantly instead of after 2 seconds. | ✓ |
| Everything inside the transaction | One place to read the rule set, but `wait_for_price` is async and cannot run in the thread — the split returns anyway. | |
| Pydantic validates in the router | /docs shows the constraints, but Phase 6 never builds that model, so the rules would be restated and could drift. | |

**User's choice:** Cheap checks, price, then balance
**Notes:** Became D-04. Option 3's rejection was revisited in the Response shapes area and confirmed as D-20.

---

## How service failures become status codes

### Q1 — How do services signal which HTTP status applies?

| Option | Description | Selected |
|--------|-------------|----------|
| Small exception taxonomy (Recommended) | `TradeError` / `NotFound` / `Conflict`, all subclassing `ValueError` so the existing house style still fits. Routers map class to status; Phase 6 catches the same classes for CHAT-09. | ✓ |
| Plain ValueError everywhere | Matches CONVENTIONS.md exactly, adds no module. Cost: the router cannot tell 409 from 400, so the business rule ends up in two places. | |
| Return a result object, never raise | Per-action status for free in Phase 6. Cost: a forgotten `ok` check silently succeeds — inverts raise-don't-swallow. | |

**User's choice:** Small exception taxonomy
**Notes:** Became D-06.

### Q2 — How does the exception message become the {detail: ...} envelope?

| Option | Description | Selected |
|--------|-------------|----------|
| One app-level exception handler (Recommended) | Registered in `create_app()`. Every route inherits it; a new service raising `Conflict` is a 409 the day it is written. | ✓ |
| try/except in each route | Mapping visible where the route is. Cost: seven routes repeating the same block, and a forgotten branch silently 500s. | |
| Dependency-wrapped service calls | Clean routes without touching main.py, but adds indirection to understand first. | |

**User's choice:** One app-level exception handler
**Notes:** Became D-07.

### Q3 — How tightly is the WATCH-05 held-position check enforced?

| Option | Description | Selected |
|--------|-------------|----------|
| Check and delete in one writing() (Recommended) | Same unit-of-work shape as the trade, so both services read alike and the "every position has a live feed" invariant holds under concurrency. | ✓ |
| Check first, then delete | Plain and obvious; the race is tiny on a single-operator app. Cost: the invariant is enforced only probabilistically. | |
| Rely on a DB-level constraint | Airtight regardless of caller. Cost: edits Phase 1's schema.sql after db/finally.db is tracked, and replaces a readable 409 with a SQLite error. | |

**User's choice:** Check and delete in one writing()
**Notes:** Became D-08.

### Q4 — Ordering of the DB write vs source.add_ticker()?

| Option | Description | Selected |
|--------|-------------|----------|
| DB write first, then add_ticker (Recommended) | The row is the durable record and the source is rebuilt from it on boot. A failed add_ticker self-heals; an orphaned feed does not. | ✓ |
| add_ticker first, then DB write | Price guaranteed present immediately after POST. Cost: a failed DB write leaves the simulator streaming an unwatched ticker forever. | |
| Both, with rollback on failure | Strictly correct. Cost: defensive machinery for a failure `SimulatorDataSource.add_ticker` cannot produce. | |

**User's choice:** DB write first, then add_ticker
**Notes:** Became D-09.

---

## What reset actually wipes (PORT-14)

### Q1 — What happens to watchlist, snapshots, trades and chat?

| Option | Description | Selected |
|--------|-------------|----------|
| Reset the portfolio only (Recommended) | Cash and positions only, plus one fresh snapshot. Watchlist, trades and chat untouched. Keeps the append-only rule intact and does not contradict Phase 1's D-09 seed gate. | ✓ |
| Full first-launch state | Everything the seed writes, including restoring the ten default tickers. Cost: silently discards user-added tickers. | |
| Portfolio plus snapshot history | P&L chart genuinely restarts flat. Cost: the chart loses the record that a reset happened. | |

**User's choice:** Reset the portfolio only
**Notes:** Became D-10. PORT-14 is `[NEW]` with no PLAN.md text, so this discussion is its entire specification.

### Q2 — What does the endpoint look like?

| Option | Description | Selected |
|--------|-------------|----------|
| POST /api/portfolio/reset, reuse STARTING_CASH (Recommended) | Verb-shaped sub-resource matching `/trade`, returning the same body as `GET /api/portfolio`. Reads `STARTING_CASH` rather than restating 10000.0. Not `seed_fresh()`, which also writes the watchlist. | ✓ |
| DELETE /api/portfolio | More REST-correct for discarding state. Cost: reads oddly for a resource that still exists, and collides with the watchlist DELETE. | |
| POST calling seed_fresh() | Maximum reuse. Cost: also inserts the ten default tickers, contradicting Q1. | |

**User's choice:** POST /api/portfolio/reset, reuse STARTING_CASH
**Notes:** Became D-11. Satisfies Phase 1's deferred note asking that reset reuse the seed helper's constant.

### Q3 — Does reset write a trades row, or a snapshot?

| Option | Description | Selected |
|--------|-------------|----------|
| Snapshot yes, trades no (Recommended) | One snapshot inside the reset transaction so history is never stale. Nothing appended to trades — a reset is not a sale. | ✓ |
| Neither | Simplest transaction; the 30s task catches up. Cost: up to 30 seconds of history reporting a value that no longer exists. | |
| Both — synthetic sells plus snapshot | Keeps trades a complete ledger. Cost: those trades never happened, and realized P&L is meant to stay derivable from that table. | |

**User's choice:** Snapshot yes, trades no
**Notes:** Became D-12.

### Q4 — Does reset get an API-level guard?

| Option | Description | Selected |
|--------|-------------|----------|
| No guard — consistent with trades (Recommended) | POST and it happens. Fake money, localhost, single operator; confirmation belongs in the Phase 4 UI. | ✓ |
| Require a confirm field in the body | Prevents an accidental /docs click. Cost: ceremony the rest of the API lacks, and Phase 6 would need the magic field. | |
| Leave it to Phase 4 | Functionally identical today, but explicitly records UI ownership. | |

**User's choice:** No guard — consistent with trades
**Notes:** Became D-13. The Phase 4 confirmation step was still recorded as a deferred idea so it is not lost.

---

## Valuation gaps and the snapshot skip rule

### Q1 — What does GET /api/portfolio say for a held ticker with no price?

| Option | Description | Selected |
|--------|-------------|----------|
| Nulls, excluded from total (Recommended) | `current_price`, `market_value`, `unrealized_pnl` null; `total_value` counts only priced positions. Client renders a dash. | ✓ |
| Fall back to avg_cost | No nulls anywhere. Cost: presents a fabricated price as real; a stalled feed looks flat rather than broken. | |
| Wait for the price | Almost always complete. Cost: `GET /api/portfolio` blocks for seconds and is refetched after every trade. | |

**User's choice:** Nulls, excluded from total
**Notes:** Became D-14, and the same rule was applied to the watchlist as D-15.

### Q2 — What counts as "unchanged" for the PORT-12 skip?

| Option | Description | Selected |
|--------|-------------|----------|
| Compare rounded to cents (Recommended) | `round_money(new) == round_money(last)`, reusing money.py. Skip fires on the all-cash idle case; a held portfolio correctly writes every 30s. | ✓ |
| Exact float equality | Literal reading. Cost: identical cash-only values can differ in the last bit, so even the idle case might not skip. | |
| An explicit epsilon threshold | Tunable. Cost: a third precision rule alongside MONEY_PLACES and QUANTITY_EPSILON, with an arbitrary number. | |

**User's choice:** Compare rounded to cents
**Notes:** Became D-16.

### Q3 — Where does the 30-second task live?

| Option | Description | Selected |
|--------|-------------|----------|
| asyncio task in create_app()'s lifespan (Recommended) | Started beside `source.start()`, cancelled before `source.stop()`, named per house convention. Both dependencies already on app.state; CORE-02 set this pattern. | ✓ |
| Started lazily on first request | Mirrors ensure_initialized. Cost: shutdown has no natural owner. | |
| Inside the market source's own loop | No second task. Cost: writes to the frozen app/market/ module. | |

**User's choice:** asyncio task in create_app()'s lifespan
**Notes:** Became D-17.

### Q4 — Where does the valuation arithmetic live?

| Option | Description | Selected |
|--------|-------------|----------|
| One pure fn in services/portfolio.py (Recommended) | `value_portfolio(cash, positions, prices)` — no I/O, so it is callable from inside the trade's executor thread and testable with literals. All four callers share it. | ✓ |
| An async service function that fetches | Fewest call sites. Cost: cannot be called inside the trade transaction, so the trade needs a second copy of the arithmetic. | |
| A method on a Portfolio model | Rich /docs, automatic serialization. Cost: derived values are full-precision by D-18 and the client recomputes them each frame. | |

**User's choice:** One pure fn in services/portfolio.py
**Notes:** Became D-18. Depends on Q2 of the first area having kept the thread function cache-free.

---

## Response shapes and remaining edges

### Q1 — Pydantic models or plain dicts?

| Option | Description | Selected |
|--------|-------------|----------|
| Pydantic models for Phase 3 routes (Recommended) | `app/api/models.py` plus `response_model` on each route. Makes Phase 2's D-08 /docs decision pay off. Health stays a dict; no Phase 1 code edited. | ✓ |
| Plain dicts, consistent with health | One fewer layer. Cost: /docs shows an untyped object for exactly the endpoints with interesting shapes. | |
| Models for requests only | Free 422 on malformed input. Cost: documents what to send but not what comes back. | |

**User's choice:** Pydantic models for Phase 3 routes
**Notes:** Became D-19. This reopened the Q4 tension from the first area, resolved next.

### Q2 — How do Pydantic models and service-owned rules coexist?

| Option | Description | Selected |
|--------|-------------|----------|
| Model is shape-only, service owns rules (Recommended) | `TradeRequest` declares types and nothing more — no `gt=0`. Every quantity rule lives in one service validator both callers use. Also keeps PORT-06 at 400, not Pydantic's 422. | ✓ |
| Constrain in the model, restate in the service | Fastest rejection. Cost: two copies that drift, and the wrong status code. | |
| Constrain in the model only | Single declaration. Cost: Phase 6 never builds a TradeRequest, so LLM quantities go unvalidated. | |

**User's choice:** Model is shape-only, service owns rules
**Notes:** Became D-20. Directly reconciles D-04's rejection of router-side validation with D-19's adoption of models.

### Q3 — What does a priceless ticker look like in GET /api/watchlist?

| Option | Description | Selected |
|--------|-------------|----------|
| Row present, price fields null, history empty (Recommended) | The watchlist is database state, not cache state. Phase 4 renders a dash rather than the ticker vanishing. | ✓ |
| Omit tickers with no price | Every entry complete. Cost: a just-added ticker is missing from the list, reading as a failed add. | |
| Zeros instead of nulls | No nulls in the schema. Cost: $0.00 is a real price a client will render and multiply. | |

**User's choice:** Row present, price fields null, history empty
**Notes:** Became D-15.

### Q4 — avg_cost on partial buys and sells?

| Option | Description | Selected |
|--------|-------------|----------|
| Weighted average on buy, unchanged on sell (Recommended) | Buy recomputes the weighted average at 4dp; sell leaves cost basis per share alone. Sell-to-zero deletes the row, so avg_cost never outlives its shares. | ✓ |
| Recompute from the trades log | Self-correcting and auditable. Cost: makes trades a read dependency, and PLAN.md §7 says it has no reader. | |
| You decide | Leave the arithmetic to the planner within D-15's 4dp and PORT-09's delete-at-zero. | |

**User's choice:** Weighted average on buy, unchanged on sell
**Notes:** Became D-05.

### Q5 — How does /api/portfolio/history validate limit and since?

| Option | Description | Selected |
|--------|-------------|----------|
| FastAPI Query constraints, 422 (Recommended) | `Query(500, ge=1, le=5000)`. Pure transport validation with one caller, so it does not conflict with the service-owns-rules rule for trades. | ✓ |
| Accept anything, let SQL handle it | `get_snapshots()` already binds safely. Cost: `?limit=-1` silently returns nothing, reading as "no history". | |
| Validate in the service | Consistent with the trade path. Cost: ceremony for a single-caller read, and gives up free /docs bounds. | |

**User's choice:** FastAPI Query constraints, 422
**Notes:** Became D-21.

---

## Claude's Discretion

The user selected the recommended option in every question, so no area was explicitly delegated. The following were recorded as planner/executor latitude in CONTEXT.md:

- Internal module decomposition beyond the fixed file names; one router file or two
- Exact error message wording, subject to the verbatim-to-user rule and PLAN.md §8's example
- Whether `side` is a literal type in the model or validated in the service
- TEST-02's test file layout and fixtures, reusing Phase 1's conftest per its D-22
- The snapshot task's sleep/cancel mechanics and teardown-mid-write behavior
- Whether reset is its own composed transaction or reuses parts of the trade one

## Deferred Ideas

- **Confirmation UX for reset** — Phase 4, per D-13
- **Realistic snapshot-task-versus-execute_trade collision test** — Phase 1 deferred it to "once both callers exist"; both now exist in this phase
- **`/api/chat` routing through the seam** — Phase 6 (CHAT-07/08/09)
- **Realized P&L and a trade history panel** — v2 (ANLY-01, ANLY-02); D-12 keeps it derivable
- **Fixing `test_custom_update_interval`** — owned by the frozen market module

---

*Phase: 3-Portfolio & Watchlist APIs*
*Discussion logged: 2026-08-12*
