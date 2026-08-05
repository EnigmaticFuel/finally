# Project Research Summary

**Project:** FinAlly — AI Trading Workstation
**Domain:** Single-container real-time trading workstation
**Researched:** 2026-08-05
**Confidence:** MEDIUM-HIGH

## Executive Summary

FinAlly is a brownfield build.

Four independent researchers converge on the same architecture: FastAPI with plain `def` endpoints for SQLite work (never `async def` touching the DB directly), stdlib `sqlite3` with WAL + `BEGIN IMMEDIATE` (no ORM, no aiosqlite), a Next.js 16 static export served by FastAPI on one origin/port, Recharts for every chart including the treemap, and LiteLLM -> OpenRouter -> Cerebras with structured outputs for the chat/trade copilot. This is a well-trodden shape with no exotic technology risk.

The single highest-priority finding, confirmed against the live repository: db/finally.db is currently committed to git, contradicting PLAN.md's own claim that it is gitignored, and the project root lives inside a OneDrive-synced Windows path with spaces, which is a documented generator of intermittent "database is locked" errors under Docker bind mounts.

A second class of risk is LLM structured-output reliability: gpt-oss-120b via OpenRouter can silently fall back to a provider that ignores response_format unless allow_fallbacks: False and require_parameters: True are set explicitly.

The recommended approach is to spend a small, explicit "Phase 0" fixing housekeeping/environment issues, then build a "spine" phase that assembles the FastAPI app and makes the already-frozen SSE stream reachable, then parallelize the portfolio API, watchlist API, and a walking-skeleton Docker container, then layer frontend shell -> charts -> chat, finishing with hardened Docker and E2E. Feature research adds several small, high-value items PLAN.md omits entirely (Reset Portfolio, a visible fill-confirmation moment, low-N/empty-state handling for the treemap and P&L chart).

## Key Findings

### Recommended Stack

Frontend: Next.js 16.3.0 static export (output: 'export', trailingSlash: true), React 19.2.8, TypeScript pinned ^5 (npm latest is TypeScript 7, which breaks Next.js), Tailwind CSS 4.3.3 (CSS-first @theme), Recharts 3.10.1 (Treemap confirmed present and typed), Vitest 4 + Testing Library, Playwright 1.62.1 for E2E run on the host against the container.

Backend: FastAPI floor bumped to >=0.141.1 (adds app.frontend()), stdlib sqlite3 with def endpoints run in FastAPI's threadpool, LiteLLM 1.95.0 -> OpenRouter -> openrouter/openai/gpt-oss-120b on Cerebras with Pydantic structured outputs, python-dotenv to load the root .env. Node 24 (Active LTS) for the Docker build stage, not Node 22 (now Maintenance LTS).

**Core technologies:**
- Next.js 16.3.0 (static export) - frontend framework - first-class output: export mode, single-origin serving
- FastAPI >=0.141.1 - backend framework - app.frontend() removes the mount-ordering hazard PLAN.md warns about
- stdlib sqlite3 (def endpoints, threadpool) - persistence - FastAPI's own docs prescribe this for blocking libraries
- Recharts 3.10.1 - all charts including the treemap - only mainstream React chart lib with line + sparkline + treemap
- LiteLLM 1.95.0 -> OpenRouter -> Cerebras - LLM gateway - verified supports_response_schema true; requires allow_fallbacks False

### Expected Features

**Must have (table stakes) - beyond what PLAN.md already specifies:**
- Total return vs. starting $10,000, shown in the header - compensates for the deliberate absence of realized P&L
- Reset Portfolio (POST /api/portfolio/reset) - every competitor product has it; doubles as the "undo" for auto-executed AI trades
- Visible fill confirmation after a trade - the trade response already carries fill_price; PLAN.md specifies the data but not the UI moment
- Correct flash-vs-cell-color separation - tick-direction flash (direction) vs. session-change persistent color (change_from_open_percent); PLAN.md currently conflates them
- "Chg from Open" / "Session %" labeling, not bare "Change %" - the baseline is "since process start," not "since previous close"
- Low-N/empty-state handling for the treemap (0 and 1 positions) and the P&L chart (a single seeded snapshot draws no line)

**Should have (differentiators, already central to PLAN.md):**
- AI auto-executes trades with no confirmation dialog - correct here because stakes are zero; the receipt (not a confirmation prompt) is what earns trust
- Inline per-action chat receipts showing server-truth fill price and per-action success/failure
- Whole UI live off one SSE stream with client-side derived valuation - no polling, no second channel

**Defer (v2+):**
- Realized P&L with cost-basis tracking, limit orders, sector grouping in the treemap, multiple watchlists, trade history UI panel, candlesticks/technical indicators

### Architecture Approach

Two layers plus one narrow service seam: api/ (thin routers) -> services/ (only trading.execute_trade() and watchlist.add/remove(), because each has 2-3 independent callers) -> db/ (free functions taking a sqlite3.Connection, no repository class, no ORM). The frozen app/market/ module is the one component nothing else may modify; it exposes PriceCache and a create_stream_router(cache) factory that requires the cache to exist before include_router() - which forces the cache to be constructed at create_app() time, not inside lifespan. Client state splits cleanly: the DB owns what the user holds and watches, the in-memory PriceCache owns what things are worth right now, and the only place they meet is valuation (cash + sum(qty x live price)), computed identically on server and client from one shared formula.

**Major components:**
1. app/main.py - create_app() factory: builds PriceCache + market source, wires lifespan, registers every /api/* router, then app.frontend("/", ...) as fallback
2. app/services/{trading,watchlist}.py - the only two service modules; each exists because it has 2+ independent callers (manual + LLM)
3. app/db/{connection,schema.sql,init,queries}.py - connect() context manager (WAL, busy_timeout, BEGIN IMMEDIATE for read-then-write paths), lazy init, free query functions
4. frontend/lib/priceStore.ts - a module-scope (non-React) EventSource store, subscribed to via useSyncExternalStore with primitive, not object, selectors
5. app/llm/ - LiteLLM client with allow_fallbacks False + require_parameters True, mock mode, structured-output schema with extra="ignore" and default-empty-array fields

### Critical Pitfalls

1. **db/finally.db is committed to git right now** (verified: git ls-files db/ returns it) - every trade becomes a binary diff, and a branch switch overwrites a running portfolio. Fix immediately: git rm --cached db/finally.db, ignore db/*.db*, keep .gitkeep.
2. **The project lives inside a OneDrive-synced path with spaces** - Docker Desktop bind-mounting SQLite from there is a documented "database is locked" generator. Fix: relocate the DB bind-mount source outside OneDrive, or relocate the whole project.
3. **core.autocrlf=true with no .gitattributes** - shell scripts and .env will get CRLF line endings, breaking start_mac.sh for macOS/Linux students and silently corrupting OPENROUTER_API_KEY with a trailing \r. Fix: commit .gitattributes before any shell script exists.
4. **Float money math is unaddressed by PLAN.md** - REAL columns plus fractional shares produce dust positions, breaking the "no zero-quantity positions" invariant. Fix: round at write boundary, compare with epsilon tolerance, never ==.
5. **OpenRouter can silently drop structured outputs** - without allow_fallbacks False and require_parameters True, a saturated Cerebras endpoint reroutes to a provider that ignores response_format. One-line fix, high blast radius if missed.
6. **SQLite read-then-write races bypass busy_timeout entirely** - Python's default DEFERRED transactions upgrade-fail immediately when another connection wrote since the read snapshot. Fix: BEGIN IMMEDIATE for any read-then-write transaction.

## Deviations from PLAN.md

PLAN.md is the authoritative product spec and remains a "strong guide" per PROJECT.md - these are documented, reasoned corrections, not silent overrides. Each should be visible to the roadmapper and the user, and PLAN.md itself should be updated once accepted.

| # | PLAN.md says | Research says | Rationale | Severity |
|---|---|---|---|---|
| 1 | Section 11: StaticFiles mounted last, after every router | FastAPI >=0.141.0 added app.frontend(): path operations always take precedence over frontend files, order-independent by design | Converts PLAN.md's most-flagged fragility into a non-issue. The project's existing fastapi>=0.115.0 floor already resolves to 0.141.x under uv sync | Medium |
| 2 | Section 10: price-flash coloring uses change_from_open_percent | Flash should be driven by tick direction (direction/change, tick-over-tick); persistent cell color should use change_from_open_percent | PLAN.md conflates two distinct real-terminal conventions. As written, a downtick on a ticker that is up on the session flashes green. Both fields already exist on the SSE payload | High |
| 3 | Section 10 (implicit): watchlist column labeled "Change %" | Label it "Chg from Open" or "Session %", with a tooltip | Every mainstream ticker computes "Change %" against previous close. FinAlly's baseline is "first price after process start" | Low |
| 4 | Section 12: SSE-resilience E2E test blocks /api/stream/prices with page.route() | page.route() does not reliably intercept EventSource; use context.setOffline(true)/setOffline(false) instead, with a 40s timeout | Documented Playwright limitation (microsoft/playwright#15353). As specified, the test would either never fire or falsely pass | Medium |
| 5 | (absent) Reset Portfolio; visible fill confirmation | Both are competitor-universal table stakes (TradingView, thinkorswim, Webull, Investopedia) | In an auto-executing AI product, Reset is the functional substitute for a confirmation dialog | High |
| 6 | Section 11: Node 22 slim | Node 24 is Active LTS as of 2026-08-05; Node 22 went to Maintenance on 2025-10-21 | One-line Dockerfile change | Low |
| 7 | Section 13: Docker is build step 7, near the end | Move a walking-skeleton Dockerfile earlier, immediately after the app-assembly "spine" phase | PLAN.md itself calls single-origin static serving "the most common way this architecture breaks" | Medium |
| 8 | (absent) transaction discipline for concurrent SQLite writers; float-money handling | BEGIN IMMEDIATE for read-then-write transactions; round-at-write-boundary + epsilon comparisons for money/quantity | Both are real, reproducible bug generators specific to this schema that PLAN.md does not mention at all | High |

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 0: Housekeeping & Environment
**Rationale:** Every other phase writes to the database, the frontend build tree, or shell scripts. Fixing these after the fact means retrofitting through everything already built; fixing them first costs under an hour combined.
**Delivers:** git rm --cached db/finally.db + updated .gitignore; .gitattributes committed (LF for .sh/Dockerfile, CRLF for .ps1/.bat) + git add --renormalize .; uv add litellm pydantic python-dotenv with uv.lock committed; fastapi floor bumped to >=0.141.1; .env.example committed; a decision recorded on the OneDrive/DB-bind-mount-source question.
**Addresses:** Pitfalls 1, 2, 11, 17, 21 (PITFALLS.md).
**Avoids:** intermittent "database is locked" errors, binary git conflicts overwriting a live portfolio, "bad interpreter" failures on macOS/Linux, a container that 500s on the chat endpoint.

### Phase 1: Spine - App Assembly + Database Layer
**Rationale:** create_app() is what makes the already-frozen SSE router reachable for the first time, and every later phase depends on it. Isolating it from "database + portfolio API" (as PLAN.md's step 2 conflates them) makes phases 2 and 3 genuinely parallel.
**Delivers:** main.py (create_app, lifespan, app.state, app.frontend() fallback), deps.py (Annotated DI for PriceCache/MarketDataSource/Db), db/{connection,schema.sql,init,queries}.py including all query functions needed by later phases (notably add_watchlist_ticker), GET /api/health. WAL + busy_timeout=5000 + BEGIN IMMEDIATE transaction helper established here. Float-money epsilon rules land here too.
**Uses:** FastAPI >=0.141.1 app.frontend(), stdlib sqlite3.
**Implements:** the api/ -> services/ -> db/ layering; the DI pattern for PriceCache.

### Phase 2: Walking-Skeleton Docker
**Rationale:** Deviation #7 above - proves single-origin static serving and the bind-mount volume early, while surface area is minimal, rather than discovering integration issues after all other code exists.
**Delivers:** Multi-stage Dockerfile (Node 24 -> Python 3.12), bind-mounted db/ from the Phase-0-decided path, start/stop scripts (macOS/Linux + PowerShell), a container-level smoke test.
**Addresses:** none from FEATURES.md directly - infrastructure.
**Avoids:** Pitfalls 3 (static mount shadowing), 10 (--workers > 1), 18 (Next export path mismatch), 22 (PowerShell script quirks).

### Phase 3: Portfolio API
**Rationale:** Depends only on Phase 1's DB layer and cache DI; independent of watchlist and frontend.
**Delivers:** services/trading.py (execute_trade() - two callers, manual and LLM), GET /api/portfolio, POST /api/portfolio/trade, GET /api/portfolio/history, POST /api/portfolio/reset (new), 30-second snapshot background task with skip-if-unchanged.
**Addresses:** Positions table, cash/total-value header, total-return-vs-$10k (new), fill confirmation surface (new), Reset Portfolio (new).
**Avoids:** Pitfalls 4 (float dust), 5 (BEGIN IMMEDIATE), 15 (compression/buffering middleware never applied to /api/stream/*).

### Phase 4: Watchlist API
**Rationale:** Parallel with Phase 3 - disjoint files, both depend only on Phase 1.
**Delivers:** services/watchlist.py (add_ticker()/remove_ticker() - three callers), GET/POST /api/watchlist, DELETE /api/watchlist/{ticker} with 409-if-held.
**Addresses:** Watchlist panel data, add/remove.
**Avoids:** Pitfall 16 (DB/market-source drift).

### Phase 5: Frontend Shell
**Rationale:** Needs the SSE stream (already live) and /api/health; can start against fixture data for portfolio/watchlist and switch to live calls once Phases 3-4 land.
**Delivers:** Next.js static export scaffold (TypeScript pinned ^5, Tailwind v4 @theme), priceStore.ts (module-scope EventSource, one connection for the whole app, useSyncExternalStore with primitive selectors), appStore (Zustand), header + connection dot, watchlist panel with correct flash-vs-cell-color separation (deviation #2) and "Chg from Open" labeling (deviation #3), trade bar with visible fill confirmation, positions table, designed empty states.
**Uses:** Next.js 16.3.0, Tailwind 4.3.3, Zustand.
**Avoids:** Pitfalls 8 (StrictMode EventSource double-mount/leak), 20 (asserting on live-updating UI - expose data-direction/data-state attributes now, for E2E later).

### Phase 6: Charts
**Rationale:** Depends on Phase 3 (portfolio/history) and Phase 5 (store, layout). Parallel with Phase 7a (chat backend) - no shared files.
**Delivers:** Main chart (auto-selects first watchlist ticker on load), sparklines, portfolio treemap (sized by market value, colored by clamped diverging P&L% gradient, with explicit 0-position and 1-position handling), P&L line chart that renders meaningfully with one seeded snapshot.
**Uses:** Recharts 3.10.1 (isAnimationActive=false and animationDuration=0 on every chart; fixed-size sparklines; React.memo + useMemo).
**Avoids:** Pitfalls 12 (re-render storm), 13 (ResponsiveContainer collapse - verify in Firefox), 14 (Treemap zero/negative value clamping).

### Phase 7a: Chat Backend (parallel with 7b)
**Rationale:** Depends on Phases 3-4 (must route through the same execute_trade/add_ticker services as manual paths).
**Delivers:** llm/{client,mock,prompt,schema}.py, GET/POST /api/chat, LLM_MOCK keyword contract, structured-output parsing with extra="ignore" + default-empty-array fields + fence-stripping, allow_fallbacks False + require_parameters True on the OpenRouter call, notional-cap guard against the LLM trading on a question, sequential per-trade execution with per-action status/error in the actions payload.
**Avoids:** Pitfalls 6a-6e (double execution, trading on a question, stale context in multi-trade turns, float dust from AI-sourced quantities, hallucinated tickers) and 7 (structured-output silent failure). Needs a spike before the router is written to confirm require_parameters behavior against the live Cerebras endpoint.

### Phase 7b: Chat Panel (parallel with 7a)
**Rationale:** The response shape is fully specified in PLAN.md section 9; the panel can build against a fixture while 7a is in progress.
**Delivers:** Collapsible chat sidebar, scrolling history, loading indicator, inline per-action receipts rendered as a distinct visual block with server-truth fill_price, visibly different treatment for failed actions.
**Addresses:** the receipt pattern from FEATURES.md - the primary trust mechanism for auto-execution.

### Phase 8: Harden Docker
**Rationale:** Depends on 2, 6, 7 - the real frontend build stage and locked dependency install can only be verified once the full app exists.
**Delivers:** Real npm ci + uv sync --frozen --no-dev build stages replacing the Phase 2 placeholder, build-time assertions.

### Phase 9: E2E
**Rationale:** Not parallelizable with feature work - runs against the built container, not a dev server.
**Delivers:** Playwright suite with globalSetup health-check (not a webServer block), workers: 1/fullyParallel: false (shared SQLite state), DB reset in globalSetup between full-suite runs, context.setOffline() for the SSE-resilience test (deviation #4), delta assertions instead of absolute-value assertions.
**Avoids:** Pitfalls 9 (Playwright/EventSource interception), 19 (persistent-DB test pollution), 20 (live-UI assertions).

### Phase Ordering Rationale

- Phase 0 must precede everything: it fixes state (tracked DB file, missing dependency, environment path) that later phases would otherwise build on top of and have to retrofit.
- Phase 1 (spine) is a hard prerequisite for all API and frontend phases because create_stream_router(cache) requires the cache to exist before include_router(), which happens before lifespan - this ordering constraint is invisible in PLAN.md's build order but is load-bearing for how main.py must be written.
- Phases 2, 3, 4 are mutually independent once Phase 1 lands only if all DB query functions (including cross-cutting ones like add_watchlist_ticker) are written in Phase 1, not deferred into Phase 3/4 - otherwise the two API phases collide in queries.py.
- Docker is moved earlier (Phase 2, walking skeleton) rather than PLAN.md's step 7, because the single-origin static-serving path is independently flagged by both ARCHITECTURE.md and PITFALLS.md as the highest-risk integration point.
- Chat backend and chat panel split into parallel 7a/7b because the response contract is fully specified up front (PLAN.md section 9), so the frontend can be built against a fixture.
- E2E is last and not parallelizable because it runs against the assembled container by design.

### Research Flags

Phases likely needing deeper research during planning (/gsd-plan-phase --research-phase N):
- **Phase 7a (Chat backend / LLM integration):** Structured-output reliability through OpenRouter->Cerebras is the least-pinned-down part of the system; needs a live spike (not just LLM_MOCK) before the router is written to confirm require_parameters/allow_fallbacks behavior and to validate the failure-path degradation contract.
- **Phase 6 (Charts):** Recharts v3's rewritten state management (removed CategoricalChartState, activeIndex) means any v2-era snippet an agent recalls will not compile; build from the shipped .d.ts, and verify Treemap behavior at 0/1/N positions and cross-browser ResponsiveContainer behavior before committing to a layout.
- **Phase 9 (E2E):** PLAN.md's literal SSE-resilience test approach (page.route()) does not work as specified - the roadmap should not copy that wording verbatim; confirm the context.setOffline() approach during phase planning.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Spine/DB):** FastAPI lifespan, DI, and SQLite threadpool discipline are documented verbatim in official docs and already fully specified in ARCHITECTURE.md with working code.
- **Phase 3 / Phase 4 (Portfolio/Watchlist API):** Trade rules, error envelopes, and schema are already concretely specified in PLAN.md sections 7-8; this is implementation, not discovery.
- **Phase 2 / Phase 8 (Docker):** Mechanical multi-stage build; the failure modes are known and enumerated (PITFALLS.md 18, 22).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versions verified against live npm/PyPI registries and shipped package artifacts (e.g., Recharts Treemap .d.ts extracted directly from the 3.10.1 tarball), not training-data recall |
| Features | MEDIUM | Cross-checked across multiple live competitor products (TradingView, thinkorswim, Webull) and design-literature sources (NN/g, Finviz, Storytelling with Data), but no primary user research exists for this specific product |
| Architecture | MEDIUM-HIGH | FastAPI/Starlette threadpool and lifespan behavior verified against first-party docs with verbatim quotes; frontend state-management guidance (Zustand, useSyncExternalStore) is strong community consensus, not first-party spec |
| Pitfalls | MEDIUM-HIGH | Three pitfalls (tracked DB file, CRLF/no .gitattributes, OneDrive path) verified directly against this repository's live git state - HIGH confidence, not inference. The rest are corroborated across 2+ independent sources - MEDIUM |

**Overall confidence:** MEDIUM-HIGH - the stack and architecture recommendations rest on primary sources (registries, shipped artifacts, official docs, and this repo's own state); feature and some pitfall findings rest on cross-checked secondary sources and are flagged accordingly.

### Gaps to Address

- **Live LLM structured-output behavior is unverified against a real API key.** All confidence here is from OpenRouter's /models//endpoints metadata and LiteLLM's static capability data, not an actual call. Validate in a Phase 7a spike before building the chat router around the assumption that require_parameters: True behaves as documented.
- **WAL over a Windows Docker Desktop bind mount, even after relocating outside OneDrive, is not empirically confirmed on this specific machine.** Expected fine (single writer, not a network filesystem) but worth one explicit stress test during Phase 2.
- **pytest>=8.3.0 floating to 9.1.1** is a major-version bump under the existing constraint; run the 154 existing market-data tests after any uv sync that picks it up.
- **The OneDrive/DB-bind-mount decision is not made by this research** - it is a project-level choice that Phase 0 must resolve explicitly and record in Key Decisions, not silently default.

## Sources

### Primary (HIGH confidence)
- npm/PyPI live registry queries (Next.js, React, TypeScript, Tailwind, Recharts, LiteLLM, Pydantic, FastAPI, pytest) - 2026-08-05
- recharts@3.10.1 shipped tarball - types/chart/Treemap.d.ts read directly
- nodejs/Release official schedule.json
- OpenRouter live API - /api/v1/models, /api/v1/models/openai/gpt-oss-120b/endpoints, /api/v1/providers
- FastAPI official docs - Lifespan Events, Concurrency/async, Static Files, Frontend (app.frontend()), Release Notes 0.141.0/0.141.1
- Starlette official docs - Lifespan state; starlette/staticfiles.py source read directly
- recharts/recharts - src/chart/Treemap.tsx source read directly (value clamping behavior)
- This repository's live git state - git ls-files db/, git log, git config core.autocrlf, .gitignore, backend/pyproject.toml, backend/uv.lock

### Secondary (MEDIUM confidence)
- Competitor product docs/guides - TradingView Paper Trading, thinkorswim paperMoney, Webull paperTrade, Finviz heatmap conventions
- Design/UX literature - NN/g (treemaps), Storytelling with Data, Carbon/Cloudscape (empty states)
- AI copilot trust/HITL literature - arXiv agent-security paper, Microsoft Security blog, tool-call render pattern write-ups
- GitHub issue trackers - recharts#945, recharts#2251, microsoft/playwright#15353, pnpm#7592, fastapi discussion #10458, Harmony-format leakage reports across TensorRT-LLM/sglang/vllm
- Docker bind-mount documentation and forum threads on Windows/SQLite locking

### Tertiary (LOW confidence)
- Reddit/community complaint threads for paper-trading products - searched, returned no usable results; feature "what users find broken" claims are inferred from product-guide framing rather than observed complaints (explicitly flagged as a gap in FEATURES.md)

---
*Research completed: 2026-08-05*
*Ready for roadmap: yes*
