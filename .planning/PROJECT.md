# FinAlly — AI Trading Workstation

## What This Is

FinAlly (Finance Ally) is a single-container AI-powered trading workstation: live streaming market prices, a simulated $10,000 portfolio the user can trade, rich data visualization, and an LLM chat copilot that can analyze positions and execute trades on the user's behalf. It looks and feels like a modern Bloomberg terminal with an AI assistant docked beside it.

It is the capstone project for an agentic AI coding course — built entirely by orchestrated coding agents to demonstrate that AI agents can produce a production-quality full-stack application. The user is a single local operator running one Docker command and opening `http://localhost:8000`. No login, no signup, no real money.

## Core Value

**The whole loop works as one experience: watch → trade → visualize → chat.** No single component is the point; the project is pointless unless a user can watch prices stream, place a trade, see the portfolio react, and ask the AI to do it for them — all in one continuous session.

## Requirements

### Validated

<!-- Shipped and confirmed working. Inferred from existing code + codebase audit. -->

- ✓ Market data abstraction — `MarketDataSource` ABC with two interchangeable implementations selected by `MASSIVE_API_KEY` — existing (`backend/app/market/`)
- ✓ GBM price simulator with per-ticker drift/volatility, sector correlation via Cholesky, and random shock events — existing
- ✓ Massive (Polygon.io) REST-polling client parsing into the same `PriceUpdate` shape — existing
- ✓ Thread-safe in-memory `PriceCache` with a monotonic version counter for cheap change detection — existing
- ✓ Session baseline — `open_price` and `change_from_open_percent` on `PriceCache` and `PriceUpdate` — existing (build-order step 1 complete)
- ✓ ~60-point history backfill per ticker at startup and on ticker add, for both simulator and Massive paths — existing
- ✓ Deterministic synthesized seed price/volatility for unknown tickers (hash-derived, stable across runs) — existing
- ✓ Shared ticker validation — `TICKER_PATTERN` / `normalize_ticker()`, one rule for manual and LLM paths — existing
- ✓ SSE stream router — `GET /api/stream/prices`, one event carrying all tickers, emitted only on cache change, with a 15s heartbeat comment frame — existing
- ✓ Market data test suite — 154 pytest tests passing, ruff clean — existing

### Active

<!-- Current scope. Build-order steps 2-8 of PLAN.md. -->

- [ ] SQLite database layer with lazy initialization, schema creation, and default seed data (six tables, `user_id` defaulting to `"default"`)
- [ ] FastAPI app assembly (`backend/app/main.py`) mounting every `/api/*` router before the static file mount
- [ ] Portfolio API — `GET /api/portfolio`, `POST /api/portfolio/trade`, `GET /api/portfolio/history`
- [ ] Trade execution honoring the full rule set: market orders only, no shorting, no margin, server-side fill price, auto-add-to-watchlist, 2s price wait, immediate snapshot write
- [ ] 30-second portfolio snapshot background task that skips unchanged values
- [ ] Watchlist API — `GET/POST /api/watchlist`, `DELETE /api/watchlist/{ticker}` with 409 on held positions, wired to `add_ticker`/`remove_ticker` on the market source
- [ ] `GET /api/health` reporting market source, tickers cached, and newest price age
- [ ] Next.js TypeScript frontend as a static export, served by FastAPI on one origin/one port
- [ ] Frontend shell — dark terminal layout, `EventSource` SSE wiring, watchlist panel with price flash animations, header with live total and connection status dot, trade bar
- [ ] Client-side live valuation — cash + Σ(quantity × live price) recomputed on every SSE frame, driving header, positions table, heatmap, and the live end of the P&L line
- [ ] Charts via Recharts throughout — main ticker chart, watchlist sparklines, portfolio treemap heatmap, P&L line chart
- [ ] Positions table — ticker, quantity, avg cost, current price, unrealized P&L, % change
- [ ] Chat API — `GET /api/chat` (history) and `POST /api/chat`, with portfolio context injection and conversation history
- [ ] Live LLM integration via LiteLLM → OpenRouter → `openrouter/openai/gpt-oss-120b` on Cerebras, using structured outputs
- [ ] Auto-execution of LLM-specified trades and watchlist changes through the same validation path as manual actions
- [ ] `LLM_MOCK=true` deterministic mock mode matching the keyword contract in PLAN.md section 9
- [ ] AI chat panel — collapsible sidebar, scrolling history, loading indicator, inline action confirmations
- [ ] Multi-stage Dockerfile (Node 22 → Python 3.12), bind-mounted `db/`, port 8000
- [ ] Start/stop scripts for macOS/Linux and Windows PowerShell, all idempotent
- [ ] Backend unit tests (pytest) covering DB, portfolio, trade rules, LLM parsing, and API routes
- [ ] Frontend unit tests covering component rendering, price flash, watchlist CRUD, portfolio math, chat rendering
- [ ] Playwright E2E suite in `test/`, run on the host against the container, covering every scenario in PLAN.md section 12

### Out of Scope

- Cloud deployment (Terraform, AWS App Runner, Render) — explicitly excluded by the user; local Docker is the deliverable
- Authentication / multi-user — no login by design; `user_id` column exists to allow it later without migration
- Realized P&L tracking or display — deliberately not stored; derivable from the `trades` audit log if ever wanted
- Trade history UI panel — `trades` is an append-only audit log with no reader and no endpoint
- Limit orders, order books, partial fills, fees, shorting, margin — market orders only, which is what makes portfolio math simple
- WebSockets — SSE is one-way and sufficient; bidirectional complexity is not earned
- Postgres or any database server — SQLite is self-contained and correct for a single-user app
- docker-compose for production — students run one container with one command
- Token-by-token LLM streaming — Cerebras inference is fast enough that a loading indicator suffices
- A second charting library — Recharts covers the treemap, so Lightweight Charts would mean two bundles for one panel
- Mobile-first layout — desktop-first, functional on tablet

## Context

**This is a brownfield project with a finished foundation.** The market data subsystem (`backend/app/market/`, 8 modules) is complete and audited: 154 tests passing, ruff clean, build-order step 1 (session baseline, backfill, heartbeat, synthesized params) verified done at commit `446b350`. Everything else in PLAN.md is unbuilt.

**Two planning directories exist and mean different things.** `planning/` holds the human-authored project specification — `PLAN.md` is the authoritative product spec, with `MARKET_DATA_SUMMARY.md` and `archive/` documenting the completed subsystem. `.planning/` holds GSD workflow artifacts (this file, requirements, roadmap, state, codebase map). PLAN.md remains the source of truth for product behavior; GSD artifacts sequence the work to deliver it.

**PLAN.md is unusually complete.** It has already survived a documentation review that resolved 24 issues (section 14 logs every decision and where it lives). API request/response shapes, error envelopes, trade rules, the SSE payload, the DB schema, and the LLM mock contract are all specified concretely. Downstream phases should read it rather than re-deriving these.

**Known state to clean up:** stale `__pycache__` directories exist under `backend/app/{api,db,llm,services}/` and `backend/tests/{api,db,llm,services}/` with no corresponding `.py` sources. They are leftover bytecode and hint at the intended structure — they are not evidence code exists. Delete them to avoid confusing contributors. `litellm` is present in the venv but absent from `pyproject.toml` and `uv.lock`; it must be added properly with `uv add litellm`.

**Environment:** Windows 11, Git Bash available, `uv` as the Python package manager (never bare `python`/`pip`). `.env` exists at the project root with an `OPENROUTER_API_KEY`; `.env.example` is specified in PLAN.md but not yet committed.

## Constraints

- **Tech stack**: FastAPI + Python 3.12 (uv), Next.js + TypeScript static export, SQLite, Recharts, Tailwind — fixed by PLAN.md; chosen for single-container simplicity and teaching value
- **Architecture**: One container, one port (8000), one origin — no CORS, no service orchestration, no docker-compose in production
- **Transport**: SSE only for live data — one-way push is all that's needed and it works everywhere
- **LLM**: LiteLLM → OpenRouter → `openrouter/openai/gpt-oss-120b` with Cerebras inference, via the `cerebras` skill; structured outputs for trade parsing
- **Degradation**: A missing `OPENROUTER_API_KEY` must never fail startup — `/api/chat` returns a normal-shaped response explaining the key is absent, and every other feature works
- **Mount order**: `StaticFiles` must mount after every `/api/*` router — mounting first shadows the API and 404s every endpoint while the UI appears fine
- **Timestamps**: SSE carries Unix epoch seconds (float); every REST payload and every `*_at` DB column is an ISO 8601 UTC string. The two never mix in one payload
- **Code style**: No overengineering, no defensive programming, short modules and functions, no emojis in code or log output, docstrings over inline comments — per the project's global instructions
- **Reproducibility**: `npm ci` and `uv sync --frozen --no-dev` build from lockfiles; that is the reason the lockfiles exist

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Build the entire remaining platform in one project (PLAN.md steps 2-8) | The whole loop is the core value; a partial build has no demo | — Pending |
| "Done" means a working end-to-end demo **and** green pytest + Playwright suites | User's explicit bar — a demo that passes no tests isn't finished | — Pending |
| PLAN.md is a strong guide, not a binding contract | Agents may improve implementation details provided the reasoning is documented in the plan; product behavior and API shapes still come from PLAN.md | — Pending |
| Live LLM path must actually work, not just mock mode | The agentic AI copilot is the course's central demonstration; `LLM_MOCK` exists for E2E determinism only | — Pending |
| Cloud deployment excluded | Local Docker is the deliverable; deploy work adds infrastructure surface with no demo value | — Pending |
| No hard deadline — quality over speed | User chose to build it properly rather than rush a vertical slice | — Pending |
| Market data subsystem is frozen as Validated | Complete, tested, and audited; downstream phases build against its contract rather than changing it | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-05 after initialization*
