# Codebase Concerns

**Analysis Date:** 2026-08-04

## Scope Note

Only `backend/app/market/` (8 modules) and its pytest suite `backend/tests/market/` (9 files, 154 tests, all passing) are implemented. Everything else described in `planning/PLAN.md` — database, portfolio API, watchlist API, chat/LLM integration, frontend, Docker, E2E tests — does not exist yet under `backend/app/` or `frontend/`. This document covers only what exists, plus the specific gap analysis requested against PLAN.md section 13, build-order step 1.

## PLAN.md Step 1 Gap Analysis (Session Baseline)

PLAN.md section 13 lists four deliverables for build-order step 1. All four are implemented and covered by tests as of commit `446b350` ("Complete the market data backend: session baseline, backfill, heartbeat"):

| Deliverable | Status | Evidence |
|---|---|---|
| `open_price` in `PriceCache` | Done | `backend/app/market/cache.py:38-58` — `PriceCache.update()` carries `open_price` forward from the previous entry, pinning it on first tick (`previous.open_price if previous else price`) |
| `open_price` / `change_from_open_percent` in `PriceUpdate` | Done | `backend/app/market/models.py:20,48-58` — both fields present; `to_dict()` at line 60-72 includes `change_from_open_percent` in the SSE payload as specified |
| History backfill (~60 points, oldest first) | Done | `backend/app/market/simulator.py:141-165` (`GBMSimulator.backfill_history`, runs GBM backwards to end at the live price) and `simulator.py:280-288` (`SimulatorDataSource._seed` calls `seed_history` before the first `update`, so sparklines are never empty). `cache.py:69-82` (`PriceCache.seed_history`) stores it. Also implemented for the Massive path in `backend/app/market/massive_client.py:183-221` (`_backfill_all` / `_fetch_history`, rate-limit-aware, one ticker at a time) |
| Synthesized params for unknown tickers | Done | `backend/app/market/seed_prices.py:47-68` (`synthesize_params` / `params_for`) — deterministic SHA-256-derived price ($20-$500), sigma (0.15-0.50), mu (0.02-0.08); unknown tickers join `CROSS_GROUP_CORR` (0.3) in `simulator.py:200-210` |
| SSE heartbeat every 15s | Done | `backend/app/market/stream.py:19,90-93` — `HEARTBEAT_INTERVAL = 15.0`, `: ping\n\n` comment frame emitted independent of price activity |

**Conclusion: build-order step 1 is complete.** The market module is ready for step 2 (database and portfolio API) to build against without further changes to the session-baseline contract.

## Tech Debt

**Massive package is a hard dependency, not optional:**
- Issue: `backend/pyproject.toml:11` lists `massive==2.2.0` under `[project.dependencies]` rather than `[project.optional-dependencies]`. `massive_client.py:10-11` imports `RESTClient` and `SnapshotMarketType` at module level (no longer lazy-imported, unlike the state described in the archived code review).
- Files: `backend/pyproject.toml`, `backend/app/market/massive_client.py`
- Impact: None currently — every environment gets the package regardless of whether `MASSIVE_API_KEY` is set, so this is a design simplification rather than a bug. It does mean the "optional integration" framing in PLAN.md section 6 is no longer reflected in the dependency graph; a `uv sync` failure or version conflict in the `massive` package would block simulator-only development too.
- Fix approach: leave as-is unless the `massive` package proves unstable; if optionality is later wanted, move it back to `optional-dependencies` and restore `TYPE_CHECKING`-guarded imports.

**`PriceCache.version` read outside the lock:**
- Issue: `backend/app/market/cache.py:119-122` reads `self._version` without acquiring `self._lock`. Safe under CPython's GIL today.
- Files: `backend/app/market/cache.py`
- Impact: None under current CPython. Would become a genuine race if the project ever runs on a no-GIL build (PEP 703).
- Fix approach: wrap the read in `with self._lock:` for consistency with the rest of the class; low priority.

**`stream.py` has the lowest test coverage in the module (per the archived review, 31%):**
- Issue: SSE generator logic (`_generate_events` in `backend/app/market/stream.py:55-98`) is exercised by `backend/tests/market/test_stream.py`, but full integration coverage (multiple clients, real disconnect detection, heartbeat timing under load) requires a running ASGI server and is comparatively thin next to `cache.py`/`models.py` (both 100% per the same review).
- Files: `backend/app/market/stream.py`, `backend/tests/market/test_stream.py`
- Impact: the SSE endpoint is the single feed every downstream feature (watchlist, portfolio valuation, price flash) will depend on; a regression here surfaces as "frontend looks frozen," which is hard to diagnose from symptoms alone.
- Fix approach: add an `httpx.AsyncClient`-based integration test against a real FastAPI app instance once the app assembly point exists (currently there is no `backend/app/main.py` to mount it into).

## Known Bugs

None identified in the implemented market module. All 154 tests pass (`uv run --extra dev pytest -q`), and `ruff check app/ tests/` reports no violations.

## Security Considerations

**No app entrypoint yet, so surface is minimal:**
- Risk: not applicable to current code — there is no `backend/app/main.py`, no FastAPI `app` instance, and no routes are mounted anywhere. `create_stream_router()` (`backend/app/market/stream.py:22`) is a router factory that nothing currently calls in production code (only tests exercise it via a locally constructed app).
- Files: n/a
- Current mitigation: n/a
- Recommendations: when the app is assembled (PLAN.md build-order step 2 onward), follow the mount-order rule in PLAN.md section 11 — API routers before the static file mount — since that specific ordering mistake is called out in the plan as the most common way this architecture breaks.

**Massive API key handling:**
- Risk: `MassiveDataSource.__init__` (`backend/app/market/massive_client.py:33-48`) takes `api_key` as a plain constructor argument; `factory.py` reads it from the environment. No masking/redaction is applied to `api_key` in logging paths.
- Files: `backend/app/market/massive_client.py`, `backend/app/market/factory.py`
- Current mitigation: none of the `logger.info`/`logger.error`/`logger.warning` calls in `massive_client.py` log the key itself, so this is not an active leak today — noted as a thing to keep true as the module grows.
- Recommendations: none required now; keep key values out of exception messages if `RESTClient` construction ever changes to log its arguments.

## Performance Bottlenecks

**None material yet.** `GBMSimulator.step()` (`backend/app/market/simulator.py:75-114`) is vectorized with numpy (single `standard_normal` draw plus one matrix multiply per tick) and `_rebuild_cholesky` is O(n³) but only runs on ticker add/remove, not every tick — appropriate for the tracked ticker counts (10 default, watchlist-scale additions). The SSE loop polls the cache every 500ms per connected client (`stream.py:77-95`); this is fine at demo scale (single user) but would need per-client fan-out review if the app ever serves concurrent connections, per the multi-user note in PLAN.md section 6.

## Fragile Areas

**Massive snapshot timestamp unit handling:**
- Files: `backend/app/market/massive_client.py:155-179` (`_extract_quote`)
- Why fragile: the Massive/Polygon API returns timestamps in different units depending on which field supplies the quote (nanoseconds for `last_trade`/`last_quote`, milliseconds for minute aggregates, "now" fallback for daily close). The code handles this correctly today with an explicit comment warning about the inconsistency, but any future addition of a new quote source path must get the divisor right or timestamps silently land ~50,000 years in the future (their own words, `massive_client.py:165`).
- Safe modification: any new branch added to `_extract_quote` needs an explicit unit-conversion test in `test_massive.py`, not just a happy-path assertion.
- Test coverage: `backend/tests/market/test_massive.py` covers `_extract_quote`'s existing three branches; no test asserts on a bad/missing timestamp unit for a hypothetical fourth quote source.

**Stale compiled bytecode outside the actual source tree:**
- Files: `backend/tests/db/__pycache__/*`, `backend/tests/api/__pycache__/*`, `backend/tests/llm/__pycache__/*`, `backend/tests/services/__pycache__/*` exist with no corresponding `.py` source files anywhere in the tree or git history at HEAD.
- Why fragile: not a functional risk (gitignored, harmless), but a source of confusion — these directories look like abandoned or reverted work (test files for `db`, `api`, `llm`, `services` subsystems that PLAN.md build-order steps 2, 3, and 6 will introduce) and could mislead a contributor into thinking those subsystems were built and then removed.
- Safe modification: delete these stale `__pycache__` directories before starting the next phase to avoid confusion; no functional change needed.

## Scaling Limits

Not applicable — the implemented module is a single-process, single-cache, in-memory design explicitly scoped to single-user use (PLAN.md section 4, "no auth = no multi-user"). No scaling concerns exist at this stage.

## Dependencies at Risk

**`massive==2.2.0` pinned exactly, no range:**
- Risk: `backend/pyproject.toml:11` pins `massive==2.2.0` with no upper or lower bound flexibility. A yanked or broken release at that exact version would block every `uv sync`, including simulator-only development, since it's a required (not optional) dependency.
- Impact: blocks `uv sync --frozen` in Docker builds and local dev alike if the pin becomes unavailable.
- Migration plan: relax to a compatible-release specifier (e.g. `>=2.2.0,<3`) once the API surface used (`RESTClient`, `SnapshotMarketType`, `get_snapshot_all`, `get_aggs`, `get_market_status`) is confirmed stable across minor versions.

## Missing Critical Features

These are PLAN.md-specified pieces with zero implementation, not speculative gaps:

- **No `backend/app/main.py` / FastAPI app assembly.** `create_stream_router()` exists but nothing mounts it. PLAN.md section 11's static-mount-ordering warning has no code to apply to yet.
- **No database layer.** `backend/app/db/` does not exist — no schema SQL, no lazy init, no seed data (PLAN.md section 7).
- **No portfolio, watchlist, or chat routers.** None of `/api/portfolio`, `/api/portfolio/trade`, `/api/portfolio/history`, `/api/watchlist`, `/api/chat`, or `/api/health` exist (PLAN.md section 8).
- **No LLM integration.** No LiteLLM/OpenRouter client, no structured-output schema, no `LLM_MOCK` mode (PLAN.md section 9).
- **No frontend.** `frontend/` does not exist as a Next.js project in this tree.
- **No Docker artifacts.** No `Dockerfile`, no `docker-compose.yml`, no `scripts/start_*`/`stop_*` scripts (PLAN.md section 11).
- **No E2E test suite.** `test/` (Playwright) does not exist (PLAN.md section 12).

## Test Coverage Gaps

**SSE integration path (see Tech Debt above):** no ASGI-server-backed test exercises `stream.py` end-to-end; unit-level generator tests exist in `test_stream.py` but real HTTP streaming behavior (chunked response, client disconnect via `request.is_disconnected()`) is untested. Priority: Medium — becomes higher priority once the frontend depends on this stream for its primary feature.

**Massive concurrent/thread-safety of `PriceCache`:** no test drives `PriceCache.update()` from multiple threads simultaneously to empirically verify the `Lock` usage, despite the Massive client running fetches via `asyncio.to_thread`. Priority: Low — code inspection shows correct lock usage, but this is the one place true concurrency (not just async concurrency) can occur.

---

*Concerns audit: 2026-08-04*
