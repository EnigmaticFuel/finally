# Requirements: FinAlly — AI Trading Workstation

**Defined:** 2026-08-05
**Core Value:** The whole loop works as one experience: watch → trade → visualize → chat

## Scope Note

The market data subsystem (`backend/app/market/`) is **built, tested, and frozen** — it is not restated as requirements here. See PROJECT.md "Validated". These requirements cover PLAN.md build-order steps 2-8 plus the corrections and additions accepted from `.planning/research/SUMMARY.md`.

Requirements marked **[NEW]** are additions beyond PLAN.md, approved by the user. Requirements marked **[CORR]** deviate from PLAN.md as a documented correction — the rationale lives in `SUMMARY.md` "Deviations from PLAN.md".

## v1 Requirements

### Foundation

- [x] **SETUP-01**: `litellm`, `pydantic`, and `python-dotenv` are declared in `backend/pyproject.toml` and present in `uv.lock`, so `uv sync --frozen` produces a container whose chat endpoint imports successfully
- [x] **SETUP-02**: FastAPI floor is raised to `>=0.141.1` so `app.frontend()` is available **[CORR]**
- [x] **SETUP-03**: `.gitattributes` is committed enforcing LF for `.sh`/`Dockerfile` and CRLF for `.ps1`, with the repo renormalized, so shell scripts do not fail with `bad interpreter` on macOS/Linux
- [x] **SETUP-04**: `.env.example` is committed documenting `OPENROUTER_API_KEY`, `MASSIVE_API_KEY`, and `LLM_MOCK`
- [x] **SETUP-05**: Stale `__pycache__` directories under `backend/app/{api,db,llm,services}` and `backend/tests/{api,db,llm,services}` are removed
- [x] **SETUP-06**: The 154 existing market-data tests still pass after all dependency changes

### Core (App Assembly + Database)

- [x] **CORE-01**: A `create_app()` factory assembles the FastAPI app, constructing `PriceCache` and the market data source before router registration
- [x] **CORE-02**: The market data background task starts and stops with the app lifespan, not a deprecated startup event
- [x] **CORE-03**: The already-built SSE router is mounted and `GET /api/stream/prices` streams live prices from the running app
- [x] **CORE-04**: The SQLite database is created and seeded lazily on first use — six tables, one profile with $10,000 cash, ten default watchlist tickers, and one portfolio snapshot
- [x] **CORE-05**: Database writes use WAL, a busy timeout, and a `BEGIN IMMEDIATE` transaction helper so a snapshot task and a trade cannot collide with `database is locked` **[CORR]**
- [x] **CORE-06**: Money and share quantities are rounded at the write boundary and compared with an epsilon, so selling an entire position leaves no residual fractional shares **[CORR]**
- [x] **CORE-07**: The shared `PriceCache` is reachable by dependency injection from the portfolio, watchlist, and chat routers without a module-level singleton
- [x] **CORE-08**: `GET /api/health` returns `{status, market_source, tickers_cached, newest_price_age_seconds}`
- [x] **CORE-09**: The static frontend is served from the same origin on port 8000 without shadowing any `/api/*` route **[CORR]**
- [x] **CORE-10**: Database access never blocks the event loop, so a slow write cannot stall the SSE stream

### Portfolio

- [ ] **PORT-01**: User can retrieve their portfolio — cash balance, total value, and each position with quantity, avg cost, current price, market value, and unrealized P&L
- [ ] **PORT-02**: User can buy shares of a ticker at the server's current price, and cash decreases by the fill amount
- [ ] **PORT-03**: User can sell shares they hold, and cash increases by the fill amount
- [ ] **PORT-04**: A buy exceeding available cash is rejected with a 400 and a message stating what was needed and what was available
- [ ] **PORT-05**: A sell exceeding shares held is rejected with a 400 — no shorting
- [ ] **PORT-06**: A quantity that is zero, negative, `NaN`, `Infinity`, or beyond 4 decimal places is rejected with a 400
- [ ] **PORT-07**: Trading a ticker that is not on the watchlist adds it to the watchlist as part of the trade
- [ ] **PORT-08**: A trade on a just-added ticker with no price yet waits up to 2 seconds for a first tick rather than failing immediately
- [ ] **PORT-09**: A sell that takes a position to zero deletes the position row entirely
- [ ] **PORT-10**: The trade response reports the server-side `fill_price` actually used, not the price the client sent
- [ ] **PORT-11**: Every executed trade writes a portfolio snapshot immediately
- [ ] **PORT-12**: A background task snapshots portfolio value every 30 seconds, skipping the write when total value is unchanged
- [ ] **PORT-13**: User can retrieve portfolio value history with `?limit=` and `?since=` query parameters
- [ ] **PORT-14**: User can reset their portfolio to the starting state — $10,000 cash, no positions **[NEW]**

### Watchlist

- [ ] **WATCH-01**: User can retrieve the watchlist with each ticker's latest price, open price, change from open, and ~60 points of history for sparklines
- [ ] **WATCH-02**: User can add a ticker, validated by the shared `^[A-Z]{1,5}$` rule after uppercasing, rejected with a 400 otherwise
- [ ] **WATCH-03**: Adding a ticker registers it with the live market data source so it starts producing prices
- [ ] **WATCH-04**: User can remove a ticker they hold no position in
- [ ] **WATCH-05**: Removing a ticker with an open position is rejected with a 409 and a message the user can read verbatim
- [ ] **WATCH-06**: Removing a ticker that is not on the watchlist returns a 404

### Frontend Shell

- [ ] **UI-01**: The app presents a dark, data-dense trading terminal layout using the specified accent colors, desktop-first and functional on tablet
- [ ] **UI-02**: Exactly one `EventSource` connection serves the whole app, and React StrictMode's double-effect does not create a second one or leak it
- [ ] **UI-03**: The watchlist panel shows each ticker with symbol, live price, session change, and a sparkline populated on first paint
- [ ] **UI-04**: A price change briefly flashes green on an uptick and red on a downtick, driven by tick direction, fading over ~500ms **[CORR]**
- [ ] **UI-05**: Persistent cell coloring and the change column use change-from-open, and the column is labeled to reflect that rather than "Change %" **[CORR]**
- [ ] **UI-06**: The header shows portfolio total value updating live, plus cash balance
- [ ] **UI-07**: A connection status dot reflects observable `EventSource` state — green when open and receiving, yellow when reconnecting or silent past 30s, red when closed
- [ ] **UI-08**: User can place a trade from a trade bar with ticker and quantity fields and buy/sell buttons, filled instantly with no confirmation dialog
- [ ] **UI-09**: After a trade, the user sees a visible confirmation showing the actual fill price received **[NEW]**
- [ ] **UI-10**: A positions table shows ticker, quantity, avg cost, current price, unrealized P&L, and % change
- [ ] **UI-11**: The header shows total return against the $10,000 starting balance **[NEW]**
- [ ] **UI-12**: Live totals are recomputed on the client from cash, positions, and each SSE frame — no portfolio polling and no second live channel
- [ ] **UI-13**: Server state is refetched after any manual trade and after any chat response carrying non-empty trades or watchlist changes
- [ ] **UI-14**: Clicking a ticker in the watchlist selects it for the main chart
- [ ] **UI-15**: Every panel has a designed empty state, so nothing reads as broken before data exists
- [ ] **UI-16**: Live-updating elements expose stable data attributes for state and direction, so E2E tests have something deterministic to assert against

### Charts

- [ ] **CHART-01**: A main chart shows price over time for the selected ticker, auto-selecting the first watchlist ticker on load so the largest panel is never blank
- [ ] **CHART-02**: Sparklines render beside each watchlist ticker, seeded from the watchlist response and extended live from the SSE stream
- [ ] **CHART-03**: A treemap shows each position sized by portfolio weight and colored by P&L, green for profit and red for loss
- [ ] **CHART-04**: The treemap renders sensibly at zero positions and at one position, not just at many
- [ ] **CHART-05**: A P&L line chart tracks total portfolio value over time and renders meaningfully from the first launch
- [ ] **CHART-06**: Charts do not animate on every price tick and do not cause re-render storms at streaming update rates

### Chat

- [ ] **CHAT-01**: User can send a chat message and receive a response containing `message`, `trades`, and `watchlist_changes`, all three always present
- [ ] **CHAT-02**: The LLM receives current portfolio context — cash, positions with P&L, watchlist with live prices, total value
- [ ] **CHAT-03**: The LLM receives recent conversation history so multi-turn exchanges make sense
- [ ] **CHAT-04**: User can retrieve conversation history, oldest first, so the panel repopulates after a page reload
- [ ] **CHAT-05**: Chat calls the live `openrouter/openai/gpt-oss-120b` model via LiteLLM through OpenRouter with Cerebras inference, using structured outputs
- [ ] **CHAT-06**: Provider routing is pinned so the request cannot silently fall back to a provider that ignores the JSON schema **[CORR]**
- [ ] **CHAT-07**: Trades specified by the LLM execute automatically through exactly the same validation and fill-price path as manual trades
- [ ] **CHAT-08**: Watchlist changes specified by the LLM apply under the same ticker validation and held-position rules as manual changes
- [ ] **CHAT-09**: A trade the LLM requested that fails validation is reported back with a per-action status and error, not silently dropped **[CORR]**
- [ ] **CHAT-10**: With no `OPENROUTER_API_KEY` configured, the app still starts and `/api/chat` returns a normal-shaped response explaining the key is missing, with empty arrays
- [ ] **CHAT-11**: With `LLM_MOCK=true`, the backend returns deterministic responses matching the keyword contract, still routed through the real execution path
- [ ] **CHAT-12**: The chat panel is a collapsible sidebar with scrolling history, a message input, and a loading indicator while awaiting a response
- [ ] **CHAT-13**: Executed trades and watchlist changes appear inline in the transcript as receipts showing the server's actual fill price, with failures visually distinct from successes **[CORR]**
- [ ] **CHAT-14**: Chat messages and their actions persist to the database and survive a page reload

### Packaging

- [ ] **DOCK-01**: A multi-stage Dockerfile builds the frontend on Node and the backend on Python 3.12 into a single image **[CORR: Node 24]**
- [ ] **DOCK-02**: The image builds from lockfiles via `npm ci` and `uv sync --frozen --no-dev`
- [ ] **DOCK-03**: One container on port 8000 serves both the API and the static frontend
- [ ] **DOCK-04**: The SQLite database persists across container restarts via the `db/` bind mount
- [ ] **DOCK-05**: Start and stop scripts exist for macOS/Linux and Windows PowerShell, and are safe to run repeatedly
- [ ] **DOCK-06**: The container runs a single uvicorn worker, so there is exactly one price universe and fills always agree with streamed prices **[CORR]**
- [ ] **DOCK-07**: The container receives configuration from the root `.env` file

### Testing

- [x] **TEST-01**: Backend tests cover database initialization, seeding, and the money/quantity rounding rules
- [ ] **TEST-02**: Backend tests cover trade execution and every rejection path — insufficient cash, insufficient shares, invalid quantity, position deletion at zero
- [ ] **TEST-03**: Backend tests cover LLM structured-output parsing, including malformed and schema-violating responses
- [ ] **TEST-04**: Backend tests cover every API route's status codes and response shapes
- [ ] **TEST-05**: Frontend tests cover component rendering, price flash behavior, watchlist operations, portfolio math, and chat rendering
- [ ] **TEST-06**: E2E — a fresh start shows the default watchlist, $10,000 balance, streaming prices, and populated sparklines
- [ ] **TEST-07**: E2E — adding and removing a watchlist ticker works
- [ ] **TEST-08**: E2E — removing a ticker with an open position shows a visible error
- [ ] **TEST-09**: E2E — buying decreases cash, creates a position, updates the portfolio, and displays the fill price
- [ ] **TEST-10**: E2E — selling increases cash and removes the position entirely when it hits zero
- [ ] **TEST-11**: E2E — the heatmap renders with correct colors and the P&L chart has data points
- [ ] **TEST-12**: E2E — a mocked chat message returns a response with an inline trade receipt, and the conversation survives a reload
- [ ] **TEST-13**: E2E — interrupting the price stream moves the connection dot off green, and restoring it returns the dot to green **[CORR]**
- [ ] **TEST-14**: The E2E suite runs on the host against the running container, serialized so shared database state cannot cause flake
- [ ] **TEST-15**: The full backend, frontend, and E2E suites all pass

## v2 Requirements

Deferred. Tracked but not in the current roadmap.

### Analytics

- **ANLY-01**: Realized P&L computed from the `trades` audit log and displayed alongside unrealized
- **ANLY-02**: A trade history panel reading the `trades` table

### Market Data

- **MKT-01**: Sector grouping in the portfolio treemap
- **MKT-02**: Configurable simulator drift and volatility from the UI

## Out of Scope

| Feature | Reason |
|---------|--------|
| Cloud deployment (Terraform, App Runner, Render) | User excluded it; local Docker is the deliverable |
| Authentication / multi-user | No login by design; `user_id` exists to allow it later without migration |
| Realized P&L storage | Deliberately untracked; derivable from `trades`. Total-return-vs-$10k covers the visible gap |
| Limit orders, order books, partial fills, fees, shorting, margin | Market orders only — this is what keeps portfolio math simple |
| WebSockets | SSE is one-way and sufficient; bidirectional complexity is not earned |
| Postgres or any database server | SQLite is self-contained and correct for a single-user app |
| Token-by-token LLM streaming | Cerebras is fast enough for a loading indicator; partial JSON from a structured output is not renderable anyway |
| A second charting library | Recharts covers the treemap, so anything else means two bundles for one panel |
| Candlestick/OHLC charts, technical indicators | GBM ticks make both meaningless — they would present numerology as analysis |
| Multi-timeframe selectors | Four buttons rendering the same series is a textbook broken signal |
| Order book / Time & Sales panels | Pure fabrication, and would introduce a third conflicting green/red meaning |
| News, fundamentals, alerts, scheduled autonomous trading | Out of scope for a simulated single-session demo |
| Moving the repo out of OneDrive; untracking `db/finally.db` | User reviewed both risks and chose to accept them — see PROJECT.md Key Decisions |
| Mobile-first layout | Desktop-first, functional on tablet |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SETUP-01 | Phase 1 | Complete |
| SETUP-02 | Phase 1 | Complete |
| SETUP-03 | Phase 1 | Complete |
| SETUP-04 | Phase 1 | Complete |
| SETUP-05 | Phase 1 | Complete |
| SETUP-06 | Phase 1 | Complete |
| CORE-01 | Phase 1 | Complete |
| CORE-02 | Phase 1 | Complete |
| CORE-03 | Phase 1 | Complete |
| CORE-04 | Phase 1 | Complete |
| CORE-05 | Phase 1 | Complete |
| CORE-06 | Phase 1 | Complete |
| CORE-07 | Phase 1 | Complete |
| CORE-08 | Phase 1 | Complete |
| CORE-09 | Phase 1 | Complete |
| CORE-10 | Phase 1 | Complete |
| TEST-01 | Phase 1 | Complete |
| DOCK-01 | Phase 2 | Pending |
| DOCK-03 | Phase 2 | Pending |
| DOCK-04 | Phase 2 | Pending |
| DOCK-05 | Phase 2 | Pending |
| DOCK-06 | Phase 2 | Pending |
| DOCK-07 | Phase 2 | Pending |
| PORT-01 | Phase 3 | Pending |
| PORT-02 | Phase 3 | Pending |
| PORT-03 | Phase 3 | Pending |
| PORT-04 | Phase 3 | Pending |
| PORT-05 | Phase 3 | Pending |
| PORT-06 | Phase 3 | Pending |
| PORT-07 | Phase 3 | Pending |
| PORT-08 | Phase 3 | Pending |
| PORT-09 | Phase 3 | Pending |
| PORT-10 | Phase 3 | Pending |
| PORT-11 | Phase 3 | Pending |
| PORT-12 | Phase 3 | Pending |
| PORT-13 | Phase 3 | Pending |
| PORT-14 | Phase 3 | Pending |
| WATCH-01 | Phase 3 | Pending |
| WATCH-02 | Phase 3 | Pending |
| WATCH-03 | Phase 3 | Pending |
| WATCH-04 | Phase 3 | Pending |
| WATCH-05 | Phase 3 | Pending |
| WATCH-06 | Phase 3 | Pending |
| TEST-02 | Phase 3 | Pending |
| UI-01 | Phase 4 | Pending |
| UI-02 | Phase 4 | Pending |
| UI-03 | Phase 4 | Pending |
| UI-04 | Phase 4 | Pending |
| UI-05 | Phase 4 | Pending |
| UI-06 | Phase 4 | Pending |
| UI-07 | Phase 4 | Pending |
| UI-08 | Phase 4 | Pending |
| UI-09 | Phase 4 | Pending |
| UI-10 | Phase 4 | Pending |
| UI-11 | Phase 4 | Pending |
| UI-12 | Phase 4 | Pending |
| UI-13 | Phase 4 | Pending |
| UI-14 | Phase 4 | Pending |
| UI-15 | Phase 4 | Pending |
| UI-16 | Phase 4 | Pending |
| CHART-01 | Phase 5 | Pending |
| CHART-02 | Phase 5 | Pending |
| CHART-03 | Phase 5 | Pending |
| CHART-04 | Phase 5 | Pending |
| CHART-05 | Phase 5 | Pending |
| CHART-06 | Phase 5 | Pending |
| CHAT-01 | Phase 6 | Pending |
| CHAT-02 | Phase 6 | Pending |
| CHAT-03 | Phase 6 | Pending |
| CHAT-04 | Phase 6 | Pending |
| CHAT-05 | Phase 6 | Pending |
| CHAT-06 | Phase 6 | Pending |
| CHAT-07 | Phase 6 | Pending |
| CHAT-08 | Phase 6 | Pending |
| CHAT-09 | Phase 6 | Pending |
| CHAT-10 | Phase 6 | Pending |
| CHAT-11 | Phase 6 | Pending |
| CHAT-12 | Phase 6 | Pending |
| CHAT-13 | Phase 6 | Pending |
| CHAT-14 | Phase 6 | Pending |
| TEST-03 | Phase 6 | Pending |
| DOCK-02 | Phase 7 | Pending |
| TEST-04 | Phase 7 | Pending |
| TEST-05 | Phase 7 | Pending |
| TEST-06 | Phase 7 | Pending |
| TEST-07 | Phase 7 | Pending |
| TEST-08 | Phase 7 | Pending |
| TEST-09 | Phase 7 | Pending |
| TEST-10 | Phase 7 | Pending |
| TEST-11 | Phase 7 | Pending |
| TEST-12 | Phase 7 | Pending |
| TEST-13 | Phase 7 | Pending |
| TEST-14 | Phase 7 | Pending |
| TEST-15 | Phase 7 | Pending |

**Coverage:**

- v1 requirements: 94 total
- Mapped to phases: 94 ✓
- Unmapped: 0

### Cross-Phase Seams

Three requirements are owned by one phase but visibly completed by the next. Recorded here so neither phase treats the other's half as already done:

| Requirement | Owned by | Completed by |
|-------------|----------|--------------|
| UI-03 (watchlist row incl. sparkline) | Phase 4 — the row layout and its data plumbing | Phase 5 — the sparkline itself (CHART-02) |
| UI-13 (refetch rule) | Phase 4 — the manual-trade path | Phase 6 — extended to chat responses with non-empty actions |
| UI-14 (click-to-select) | Phase 4 — the selection state | Phase 5 — the main chart that consumes it (CHART-01) |

---
*Requirements defined: 2026-08-05*
*Last updated: 2026-08-05 after roadmap creation*
