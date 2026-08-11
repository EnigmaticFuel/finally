# Roadmap: FinAlly — AI Trading Workstation

## Overview

The market data subsystem is already built, tested, and frozen — it produces live prices but nothing yet consumes them. This roadmap takes the project from "a price engine with no app around it" to the full loop: **watch → trade → visualize → chat**, running as one Docker container on one port, with green pytest and Playwright suites.

The path is deliberately spine-first. Phase 1 assembles the FastAPI app so the already-frozen SSE router becomes reachable for the first time, and lands the entire SQLite layer — including every query function later phases need — so that the phases after it do not collide in the same files. Phase 2 wraps that spine in a walking-skeleton container immediately, because single-origin static serving is the single highest-risk integration point in this architecture and proving it while surface area is small beats discovering it at the end. Phase 3 makes the money real. Phases 4-6 build the terminal the user actually looks at: the live shell, then the charts, then the AI copilot. Phase 7 replaces the skeleton container with the real lockfile build and proves the whole thing with three green test suites.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation & Spine** - Assembled FastAPI app, live SSE stream, seeded SQLite layer (completed 2026-08-06)
- [ ] **Phase 2: Walking-Skeleton Container** - One container on port 8000 with a persistent database
- [ ] **Phase 3: Portfolio & Watchlist APIs** - Real money, enforced trade rules, live watchlist
- [ ] **Phase 4: Frontend Shell** - Dark trading terminal streaming prices and taking trades
- [ ] **Phase 5: Charts & Visualization** - Main chart, sparklines, portfolio treemap, P&L line
- [ ] **Phase 6: AI Chat Copilot** - Conversational analysis that executes trades and watchlist changes
- [ ] **Phase 7: Production Container & Full Verification** - Lockfile image plus three green test suites

## Phase Details

### Phase 1: Foundation & Spine

**Goal**: The backend runs as one assembled FastAPI app with a lazily seeded database and a reachable live price stream
**Depends on**: Nothing (first phase)
**Requirements**: SETUP-01, SETUP-02, SETUP-03, SETUP-04, SETUP-05, SETUP-06, CORE-01, CORE-02, CORE-03, CORE-04, CORE-05, CORE-06, CORE-07, CORE-08, CORE-09, CORE-10, TEST-01
**Success Criteria** (what must be TRUE):

  1. The assembled app streams live prices at `GET /api/stream/prices` for all ten default tickers with heartbeats, answers `GET /api/health` with market source, tickers cached and newest price age, and lets `/api/*` routes take precedence over the static frontend fallback.
  2. On a machine with no database file, the first request creates and seeds it — six tables, one profile with $10,000 cash, ten watchlist tickers, and one portfolio snapshot.
  3. A snapshot write and a trade write running at the same time never produce `database is locked`, and selling an entire position leaves no residual fractional shares.
  4. `uv sync --frozen` from the committed lockfile produces an environment where the chat dependencies import cleanly and all 154 existing market-data tests still pass.
  5. A fresh clone carries `.env.example` and a `.gitattributes` that keeps `.sh`/`Dockerfile` at LF and `.ps1` at CRLF, and no stale `__pycache__` trees remain under `backend/`.

**Plans**: 5/5 plans executed

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Spine tracer: dependency floor, `create_app()`, health, live stream, static fallback, proven end to end over HTTP

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — SQLite foundation: money and quantity rounding, six-table schema, fresh-database seed, connection layer with WAL and the offload seam

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Complete query surface for profile, positions, trades, snapshots, watchlist and chat, plus the threaded contention proof
- [x] 01-04-PLAN.md — Repo hygiene: `.gitattributes` and renormalization, `.env.example`, WAL sidecar ignores, stale bytecode cleanup

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-05-PLAN.md — Freshly seeded tracked `db/finally.db` (one-way, gated) and the dependency-change regression gate

**Ordering constraint (load-bearing)**: `create_stream_router(cache)` requires the `PriceCache` to exist *before* `include_router()`, which happens before lifespan runs. `main.py` must therefore construct the cache and market source inside `create_app()`, not inside the lifespan handler. This is invisible in PLAN.md's build order and dictates the whole file's shape.

**Scope note (load-bearing)**: Every SQLite query function lands here — including cross-cutting ones like `add_watchlist_ticker`, which `execute_trade` needs for its auto-add. Deferring those into Phase 3 would make the portfolio and watchlist work collide in `queries.py`.

**Frozen**: `backend/app/market/` is not modified by this phase or any other. It is consumed through `PriceCache` and `create_stream_router(cache)` only.

### Phase 2: Walking-Skeleton Container

**Goal**: The app runs as a single container on port 8000 with a database that survives restarts
**Depends on**: Phase 1
**Parallel with**: Phase 3 (disjoint files — infrastructure vs. API modules)
**Requirements**: DOCK-01, DOCK-03, DOCK-04, DOCK-05, DOCK-06, DOCK-07
**Success Criteria** (what must be TRUE):

  1. A user runs one start script — `start_mac.sh` or `start_windows.ps1` — and reaches a working `http://localhost:8000` where API routes and static assets are served from the same origin and the same port.
  2. Stopping and restarting the container preserves cash balance and watchlist, because the SQLite file lives in the bind-mounted `db/` directory.
  3. Running start twice, or stop twice, is safe and produces the same result.
  4. The container reads `OPENROUTER_API_KEY`, `MASSIVE_API_KEY` and `LLM_MOCK` from the root `.env`, and runs a single uvicorn worker so there is exactly one price universe and fills always agree with streamed prices.

**Plans**: 3/4 plans executed

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Container image: `.dockerignore`, multi-stage `Dockerfile`, and one proven end-to-end path serving `/api/health` and `/` on port 8000

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — Idempotent start/stop scripts for macOS/Linux (LF) and Windows PowerShell 5.1 (CRLF), with the readiness gate and the image-staleness print

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-03-PLAN.md — Deliberate WAL-over-bind-mount stress against a scratch database, plus write-through and restart-persistence proof

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 02-04-PLAN.md — Committed `scripts/smoke_check.py` proving all four success criteria against a real container

**Why here and not at the end**: PLAN.md itself calls single-origin static serving "the most common way this architecture breaks." Proving it while the app is a spine, rather than after every feature exists, is the user-approved deviation from PLAN.md build-order step 7. The real lockfile build stages land in Phase 7.

**Watch for**: WAL over a Windows Docker Desktop bind mount is not empirically confirmed on this machine. If `database is locked` appears, the cause is the accepted OneDrive/bind-mount risk recorded in PROJECT.md Key Decisions — diagnose it, do not plan a relocation.

### Phase 3: Portfolio & Watchlist APIs

**Goal**: The user's cash, positions and watched tickers are real, live-valued, and rule-enforced
**Depends on**: Phase 1
**Parallel with**: Phase 2. Internally, the portfolio and watchlist work are disjoint modules and can run as parallel plan waves.
**Requirements**: PORT-01, PORT-02, PORT-03, PORT-04, PORT-05, PORT-06, PORT-07, PORT-08, PORT-09, PORT-10, PORT-11, PORT-12, PORT-13, PORT-14, WATCH-01, WATCH-02, WATCH-03, WATCH-04, WATCH-05, WATCH-06, TEST-02
**Success Criteria** (what must be TRUE):

  1. A user can read their portfolio — cash, total value, and every position with quantity, avg cost, current price, market value and unrealized P&L — and can buy or sell at the server's price, receiving back the actual `fill_price` used, even on a ticker added moments earlier whose first tick is waited on for up to 2 seconds rather than rejected.
  2. Every trade rule holds and is covered by tests: no buying past available cash, no selling shares not held, no zero/negative/`NaN`/`Infinity`/over-precision quantities, a position that reaches zero disappears entirely, and trading an unwatched ticker adds it to the watchlist as part of the trade.
  3. A user can read the watchlist with each ticker's live price, open price, change from open and ~60 points of sparkline history, and can add a ticker that immediately starts producing prices — with an invalid symbol rejected 400, an unknown removal 404, and removing a held ticker rejected 409 with a message readable verbatim.
  4. Portfolio value history accumulates — one snapshot on every trade plus one every 30 seconds when the value actually changed — and is retrievable with `?limit=` and `?since=`.
  5. A user can reset to the starting state: $10,000 cash and no positions.

**Plans**: TBD

**Service seam**: `services/trading.execute_trade()` and `services/watchlist.add/remove()` exist because each has two independent callers (manual API and, later, the LLM). Phase 6 must route through these exact functions, so their signatures are a contract.

### Phase 4: Frontend Shell

**Goal**: The user sees a live dark trading terminal and can trade from it
**Depends on**: Phase 2, Phase 3
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-07, UI-08, UI-09, UI-10, UI-11, UI-12, UI-13, UI-14, UI-15, UI-16
**Success Criteria** (what must be TRUE):

  1. Opening the app shows a dark, data-dense terminal — a watchlist panel with symbol, live price and session change where clicking a ticker selects it, a header carrying cash, live total value and total return against the $10,000 start, and a trade bar — with a designed empty state on every panel that has no data yet.
  2. A price change flashes green on an uptick and red on a downtick and fades within ~500ms, while the persistent cell colour and change column use change-from-open and are labeled to say so rather than "Change %".
  3. A connection status dot is green when the stream is open and receiving, yellow while reconnecting or silent past 30 seconds, and red when closed — and every live-updating element carries stable data attributes for its state and direction.
  4. A user can buy or sell from the trade bar with no confirmation dialog, immediately sees a confirmation showing the server's actual fill price, and watches the header, cash and positions table refetch and update.
  5. Total value and P&L recompute on every price frame from exactly one `EventSource` connection that survives a React StrictMode remount without leaking a second one — no polling, no second live channel.

**Plans**: TBD
**UI hint**: yes

**Seam with Phase 5**: UI-03 delivers the watchlist row and its data plumbing; the sparkline that fills the row's chart slot is CHART-02 in Phase 5. UI-14 delivers selection state; the main chart that consumes it is CHART-01. UI-13's refetch rule is written here and extended to chat responses in Phase 6.

### Phase 5: Charts & Visualization

**Goal**: The user can see price action, portfolio composition and value over time
**Depends on**: Phase 3, Phase 4
**Parallel with**: Phase 6 (charts and chat touch no shared files)
**Requirements**: CHART-01, CHART-02, CHART-03, CHART-04, CHART-05, CHART-06
**Success Criteria** (what must be TRUE):

  1. The main chart shows price over time for the selected ticker and auto-selects the first watchlist ticker on load, so the largest panel is never blank.
  2. Every watchlist row carries a sparkline that is already populated on first paint from the watchlist response and extends live as prices stream.
  3. A treemap sizes each position by portfolio weight and colours it by P&L — green for profit, red for loss — and reads sensibly at zero positions and at one position, not only at many.
  4. A P&L line chart shows total portfolio value over time and is meaningful from the very first launch, when only the one seeded snapshot exists.
  5. Charts hold a steady frame at streaming update rates — no per-tick animation, no re-render storms.

**Plans**: TBD
**UI hint**: yes
**Research**: yes — Recharts 3.x rewrote state management (`CategoricalChartState` and `activeIndex` are gone), so any v2-era snippet recalled from memory will not compile. Build from the shipped `.d.ts`, and verify Treemap behaviour at 0/1/N positions and `ResponsiveContainer` behaviour cross-browser before committing to a layout.

### Phase 6: AI Chat Copilot

**Goal**: The user can converse with FinAlly and have it analyze and act on the portfolio
**Depends on**: Phase 3, Phase 4
**Parallel with**: Phase 5. Internally the chat backend and the chat panel are separable — the response shape is fully specified in PLAN.md section 9, so the panel can be built against a fixture as a parallel plan wave.
**Requirements**: CHAT-01, CHAT-02, CHAT-03, CHAT-04, CHAT-05, CHAT-06, CHAT-07, CHAT-08, CHAT-09, CHAT-10, CHAT-11, CHAT-12, CHAT-13, CHAT-14, TEST-03
**Success Criteria** (what must be TRUE):

  1. A user types into a collapsible chat sidebar, sees a loading indicator, and gets back a reply grounded in their actual cash, positions with P&L, watchlist prices and total value — with earlier turns of the conversation carried into the prompt so multi-turn exchanges make sense.
  2. Asking the AI to buy, sell, or change the watchlist executes it immediately through the same `execute_trade` / `add_ticker` / `remove_ticker` path as a manual action, and the transcript shows an inline receipt with the server's real fill price — with failures visually distinct from successes, each carrying its own status and reason rather than being silently dropped.
  3. The conversation and its executed actions survive a page reload, replayed oldest first.
  4. With `LLM_MOCK=true` the same execution path runs deterministically against the keyword contract in PLAN.md section 9; with no `OPENROUTER_API_KEY` the app still starts and `/api/chat` returns a normal-shaped response explaining the key is missing, with empty arrays.
  5. The live `openrouter/openai/gpt-oss-120b` call on pinned Cerebras routing returns schema-valid structured output, and a malformed or schema-violating response degrades into a readable message instead of a 500.

**Plans**: TBD
**UI hint**: yes
**Research**: yes — structured-output reliability through OpenRouter → Cerebras is the least-pinned-down part of the system. Run a live spike (not `LLM_MOCK`) before writing the router, to confirm `require_parameters: True` / `allow_fallbacks: False` behaviour against the real endpoint and to validate the degradation contract.

**Project skill**: `.claude/skills/cerebras/SKILL.md` is the house pattern for this call — LiteLLM `completion()` with `MODEL = "openrouter/openai/gpt-oss-120b"`, `extra_body={"provider": {"order": ["cerebras"]}}`, `reasoning_effort="low"`, and a Pydantic subclass as `response_format`. CHAT-06 extends that `provider` block with the pinning flags.

### Phase 7: Production Container & Full Verification

**Goal**: The shipped container is the one that has been tested, and the whole watch → trade → visualize → chat loop is proven green
**Depends on**: Phase 2, Phase 5, Phase 6
**Requirements**: DOCK-02, TEST-04, TEST-05, TEST-06, TEST-07, TEST-08, TEST-09, TEST-10, TEST-11, TEST-12, TEST-13, TEST-14, TEST-15
**Success Criteria** (what must be TRUE):

  1. A clean clone builds the production image entirely from lockfiles — `npm ci` and `uv sync --frozen --no-dev` — replacing the Phase 2 placeholder stages, and the resulting container serves the complete app on port 8000.
  2. Against a fresh container, the default watchlist, $10,000 balance, streaming prices and populated sparklines all appear; adding and removing a ticker works; and removing a ticker with an open position shows a visible error.
  3. Buying decreases cash, creates a position, displays the fill price and updates the portfolio; selling increases cash and removes the position entirely when it hits zero; the heatmap renders with correct colours and the P&L chart has data points.
  4. A mocked chat message returns a response with an inline trade receipt that is still there after a page reload, and interrupting the price stream moves the connection dot off green until the stream is restored.
  5. All three suites are green: the backend suite covering every API route's status codes and response shapes, the frontend suite covering rendering, price flash, watchlist operations, portfolio math and chat rendering, and the Playwright suite running serialized on the host against the running container.

**Plans**: TBD
**Research**: yes — PLAN.md section 12's literal approach of blocking `/api/stream/prices` with `page.route()` does not reliably intercept `EventSource` (microsoft/playwright#15353). Confirm the `context.setOffline(true)/setOffline(false)` approach during planning, along with `globalSetup` health-check over a `webServer` block, `workers: 1` / `fullyParallel: false` for shared SQLite state, and delta rather than absolute-value assertions against live-updating UI.

**Not parallelizable**: E2E runs against the assembled container by design, not a dev server, so it cannot overlap feature work.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

**Parallelizable pairs** (parallelization enabled in config):

- Phase 2 ∥ Phase 3 — both depend only on Phase 1, and touch disjoint files (Dockerfile/scripts vs. `app/api` + `app/services`)
- Phase 5 ∥ Phase 6 — charts and chat share no files; both depend on Phases 3 and 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Spine | 5/5 | Complete    | 2026-08-06 |
| 2. Walking-Skeleton Container | 3/4 | In Progress|  |
| 3. Portfolio & Watchlist APIs | 0/TBD | Not started | - |
| 4. Frontend Shell | 0/TBD | Not started | - |
| 5. Charts & Visualization | 0/TBD | Not started | - |
| 6. AI Chat Copilot | 0/TBD | Not started | - |
| 7. Production Container & Full Verification | 0/TBD | Not started | - |

## Coverage

All 94 v1 requirements are mapped to exactly one phase. See REQUIREMENTS.md Traceability.

| Phase | Requirements | Count |
|-------|--------------|-------|
| 1 | SETUP-01..06, CORE-01..10, TEST-01 | 17 |
| 2 | DOCK-01, DOCK-03..07 | 6 |
| 3 | PORT-01..14, WATCH-01..06, TEST-02 | 21 |
| 4 | UI-01..16 | 16 |
| 5 | CHART-01..06 | 6 |
| 6 | CHAT-01..14, TEST-03 | 15 |
| 7 | DOCK-02, TEST-04..15 | 13 |
| **Total** | | **94** |

## Out of Roadmap

Recorded here so no phase accidentally picks them up:

- **Moving the repo out of OneDrive, changing the `db/` bind-mount source, untracking `db/finally.db`** — the user reviewed both risks and accepted them. See PROJECT.md Key Decisions. No phase, plan, task or success criterion may address these.
- **`backend/app/market/`** — built, tested (154 passing) and frozen. Consumed, never modified.

---
*Roadmap created: 2026-08-05*
