---
phase: 01-foundation-spine
plan: 01
subsystem: app-assembly
tags: [fastapi, sse, static-serving, dependency-injection, lifespan, uv]
status: complete

requires: []
provides:
  - "create_app() factory in backend/app/main.py"
  - "app.state.price_cache / market_source / db_path DI seam"
  - "create_health_router(cache, source) in backend/app/api/health.py"
  - "GET /api/health four-key payload"
  - "GET /api/stream/prices mounted and reachable over HTTP"
  - "backend/static/index.html served via app.frontend()"
  - "FINALLY_DB_PATH env var and DB_PATH constant in backend/app/config.py"
  - "app / db_path pytest fixtures in backend/tests/conftest.py"
  - "fastapi>=0.141.1, litellm, pydantic, python-dotenv, httpx dev extra in the lockfile"
affects:
  - "plan 01-02 (app/db/* builds on app.state.db_path and the app fixture)"
  - "plan 01-03 (reuses the app fixture)"
  - "phase 2 Dockerfile and start scripts (create_app seam, FINALLY_DB_PATH)"
  - "phase 3 routers (app fixture, DI seam)"
  - "phase 6 chat (litellm now a locked dependency)"

tech-stack:
  added:
    - "fastapi>=0.141.1 (resolves 0.141.1) - app.frontend() SPA serving"
    - "litellm>=1.95.0 (resolves 1.95.0) - phase 6 LLM gateway, locked now"
    - "pydantic>=2.10.0 (resolves 2.12.5) - made explicit, was transitive"
    - "python-dotenv>=1.0.0 (resolves 1.2.1) - load_dotenv in config.py"
    - "httpx>=0.28.0 (dev extra) - SSE integration test client"
  patterns:
    - "Router factories over module-level routers (mirrors create_stream_router)"
    - "Cache and source constructed in the create_app() body before include_router()"
    - "asynccontextmanager lifespan, no @app.on_event"
    - "Absolute STATIC_DIR derived from Path(__file__).resolve()"
    - "uvicorn-in-thread for any test touching the SSE stream"

key-files:
  created:
    - backend/app/main.py
    - backend/app/config.py
    - backend/app/api/__init__.py
    - backend/app/api/health.py
    - backend/static/index.html
    - backend/.python-version
    - backend/tests/test_main.py
    - backend/tests/api/__init__.py
    - backend/tests/api/test_health.py
    - backend/tests/market/test_stream_integration.py
  modified:
    - backend/pyproject.toml
    - backend/uv.lock
    - backend/tests/conftest.py

decisions:
  - "Health payload restricted to exactly four keys, with newest_price_age_seconds truthfully None until a price exists (CORE-08)"
  - "DEFAULT_TICKERS named locally in main.py; plan 01-02 moves the canonical list to app/db/seed.py"
  - "conftest sets app.state.db_path directly; plan 01-02 replaces it with dependency_overrides[get_db_path]"
  - "Route existence asserted via app.openapi()['paths'] because FastAPI 0.141 include_router() no longer flattens into app.routes"
  - "LLM_MOCK exposed as a bool rather than a raw string, matching PLAN.md's 'true' contract"

metrics:
  duration: "~2.5h across two sessions (interrupted by a usage limit)"
  completed: 2026-08-06
  tasks: 2
  commits: 3
  files_created: 10
  files_modified: 3

actuals:
  tokens: 5516
  tasks: 2
  commits: 3
---

# Phase 01 Plan 01: Foundation Spine Summary

FastAPI app assembled for the first time — `create_app()` wires the frozen market module into a live HTTP surface serving health, an SSE price stream and the static frontend on one origin, proven end to end against a real uvicorn server.

## What Was Built

`backend/app/market/` had been finished and frozen for a while but nothing consumed it: there was no `main.py`, so the SSE router had never been mounted and had never been exercised over HTTP. This plan created the object graph the rest of the project hangs from.

**The assembly (`backend/app/main.py`).** `create_app()` constructs the `PriceCache`, then the market data source, then registers routers, then the static frontend. The cache-before-router ordering is load-bearing and is the single most likely way to get this file wrong: both router factories take the cache as a constructor argument, and `include_router()` runs long before lifespan does, so a cache created inside the lifespan handler would arrive too late. The source is started and stopped by an `asynccontextmanager` lifespan; there is no `@app.on_event`. `STATIC_DIR` is absolute, derived from `Path(__file__).resolve()`, because `app.frontend()` resolves `directory` against the process CWD and its `check_dir="auto"` raises at app-creation time — a relative path would break the entire suite at collection depending on where the process was launched.

**Health (`backend/app/api/health.py`).** A `create_health_router(price_cache, source)` factory mirroring the frozen module's `create_stream_router` convention, returning a router built inside the factory body so constructing an app twice does not register the route twice. The payload is exactly four keys. All three non-constant values come from the frozen module's own accessors (`source.source_name`, `len(cache)`, `cache.newest_timestamp()`), which exist for precisely this purpose.

**Config (`backend/app/config.py`).** `load_dotenv` on the project-root `.env`, resolved by walking up from `Path(__file__)` rather than from the process CWD, because the backend runs from `backend/` locally and `/app` in the container. `DB_PATH` reads `FINALLY_DB_PATH` and defaults to the repo-root `db/finally.db` — deliberately not `backend/db/`, which is where a naive relative derivation lands and which would diverge from the tracked, bind-mounted top-level `db/`. Verified: with the variable unset, `DB_PATH` resolves to the sibling of `backend/`.

**Dependency floor.** Raised FastAPI to `>=0.141.1` (`app.frontend()` does not exist below it) and added `litellm`, `pydantic` and `python-dotenv` as real runtime dependencies plus `httpx` as a dev extra, with a regenerated lockfile. `litellm` was previously present in the venv but absent from both `pyproject.toml` and `uv.lock` — it is now genuinely reproducible. `backend/.python-version` pins 3.12 for parity with the Docker image.

**Tests.** 16 new tests across four files, all driving the real assembled app.

## Key Decisions

**`newest_price_age_seconds` is truthful, not decorative (CORE-08 prohibition).** It is `None` before any price exists and a real measurement afterwards. This is the whole reason the endpoint is worth calling: a fixed `"ok"` reads identically whether the feed is streaming or stopped. `tests/api/test_health.py` asserts both states, and asserts the payload contains no key-shaped field.

**Two deliberate handoffs to plan 01-02, both named in the plan.** `DEFAULT_TICKERS` sits in `main.py` rather than `app/db/seed.py`, and the conftest `app` fixture sets `app.state.db_path` directly rather than overriding a `get_db_path` dependency that does not exist yet. Both carry in-code notes naming 01-02 as the resolving plan. These are sequencing, not defects — see *Planned Handoffs* below.

**Route existence asserted through the OpenAPI schema.** See *Deviations*.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Route-existence assertion used an API that FastAPI 0.141 changed**

- **Found during:** Task 2
- **Issue:** `test_create_app_builds_cache_before_routers` asserted `/api/health` and `/api/stream/prices` were in `{route.path for route in app.routes}`. It failed, with `app.routes` containing only `/docs`, `/redoc`, `/openapi.json` and two unnamed entries — even though the endpoints demonstrably worked in four other passing tests.
- **Root cause (proven, not guessed):** Inspecting `app.routes` directly showed that since FastAPI 0.141, `include_router()` appends an internal `_IncludedRouter` wrapper object instead of flattening the child routes into `app.routes`. The routes are nested one level down. This is a real behavior change in the same release line that introduced `app.frontend()`, not a wiring error — the app was correct all along, the test's introspection was not.
- **Fix:** Assert against `app.openapi()["paths"]`, which is a public, stable enumeration and returned exactly `['/api/health', '/api/stream/prices']`. The reasoning is recorded in the test docstring.
- **Files modified:** `backend/tests/test_main.py`
- **Commit:** `a9c0ef0`
- **Worth carrying forward:** Phase 3 will add more routers and will hit this same surprise if it tries to enumerate `app.routes`.

No other deviations. Rules 2, 3 and 4 were not triggered.

## Planned Handoffs to Plan 01-02

Recorded here for visibility rather than filed as broken windows: each is an intentional interim state, explicitly specified by this plan, with a named owner plan inside the same phase.

| Item | File | Resolved by |
|------|------|-------------|
| `DEFAULT_TICKERS` declared locally instead of in the db seed module | `backend/app/main.py` | Plan 01-02 Task 1 moves the canonical list to `app/db/seed.py` |
| `app` fixture sets `app.state.db_path` directly instead of overriding a DB dependency | `backend/tests/conftest.py` | Plan 01-02 replaces it with `dependency_overrides[get_db_path]` once `get_db_path` exists |

Neither blocks this plan's goal; both are documented in code at the point of use.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: information-disclosure | `backend/app/main.py` | `FastAPI(title="FinAlly")` serves interactive API docs at `/docs`, `/redoc` and `/openapi.json` by default. This surface is not in the phase threat register (which covers `/api/health`, static serving and env handling). Low risk for a localhost single-operator app and useful during development, but Phase 2 should decide deliberately whether to disable it in the container image rather than shipping it by default. |

## Verification

All checks run from `backend/`.

| Check | Result |
|-------|--------|
| `uv run --extra dev pytest -q` (full suite) | **170 passed**, 0 failed |
| `uv run --extra dev pytest -q tests/test_main.py tests/api tests/market/test_stream_integration.py` | 16 passed (plan required at least 8) |
| `uv run --extra dev ruff check app/ tests/` | All checks passed |
| `uv run --frozen python -c "import litellm, pydantic, dotenv, httpx, fastapi"` | exit 0, fastapi 0.141.1 |
| `uv sync --frozen --extra dev` | Checked 72 packages, no resolution error |
| `git status --porcelain backend/app/market/` | empty — frozen module untouched |
| `git status --porcelain backend/tests/market/` | only `test_stream_integration.py` |

**Regression gate (D-24):** the pre-phase baseline was 154 tests. The suite now runs 170 (154 + 16 new) with **zero failures**. The known flake `tests/market/test_simulator_source.py::test_custom_update_interval` passed on this run; no test that passed before this plan fails now.

**Live verification at the tracer checkpoint.** The app was served on port 8000 and confirmed by both the executor and the orchestrator: `/api/health` returned `{"status":"ok","market_source":"simulator","tickers_cached":10,"newest_price_age_seconds":0.013}`, `/` served the placeholder page, and `/api/stream/prices` opened with `retry: 1000` and streamed frames carrying `open_price` and `change_from_open_percent`. `tickers_cached: 10` with a sub-second age is the substantive evidence that the simulator really runs under lifespan rather than the endpoint reporting a hardcoded green signal. The server was stopped afterwards; port 8000 is free.

## Requirements Satisfied

| ID | Evidence |
|----|----------|
| SETUP-01 | `litellm`, `pydantic`, `python-dotenv` declared and locked; import probe exits 0 |
| SETUP-02 | `fastapi>=0.141.1` in `[project].dependencies`; `app.frontend()` in use |
| CORE-01 | `test_create_app_builds_cache_before_routers`; cache and source constructed before the first `include_router(` |
| CORE-02 | `test_lifespan_starts_and_stops_source` — source unstarted, then 10 tickers with the `simulator-loop` task live, then the task gone on exit; no `on_event` in `main.py` |
| CORE-03 | `tests/market/test_stream_integration.py` — stream over real HTTP, two independent clients, heartbeat frame |
| CORE-07 | `test_cache_via_dependency` — routers read the cache on `app.state`, and two `create_app()` calls yield distinct caches |
| CORE-08 | `tests/api/test_health.py` — exact four keys, `None` before a price, non-negative float after, no key-shaped field |
| CORE-09 | `test_api_not_shadowed` — all four Accept rows; `test_concurrent_health_and_stream` holds the same under a live stream |

## Notes for Future Phases

- **Any test that touches `/api/stream/prices` must use a real server.** `TestClient.stream()` and `httpx.ASGITransport` both hang forever against the infinite SSE generator — they never return headers, so no read timeout rescues them. The `live_app` fixture in `tests/test_main.py` and `sse_server` in `tests/market/test_stream_integration.py` are the working pattern. Non-streaming endpoints use `TestClient` normally.
- **The `app` fixture is the Phase 3 seam.** It takes no arguments beyond `tmp_path` (via `db_path`) and returns an app whose lifespan has *not* run, so the cache is empty and the source unstarted. Tests needing a live feed either drive `app.router.lifespan_context(app)` or serve the app from uvicorn.
- **A session-scoped autouse fixture clears `MASSIVE_API_KEY`** for the whole suite, so a developer holding a real key never has the tests poll the live Massive API.
- **The unmatched-`/api/*` SPA fallback is Accept-gated and this is correct.** `Accept: text/html` gets `index.html` with a 200; `application/json` and `*/*` get a JSON 404. Since `fetch()` sends `*/*`, frontend calls always receive JSON 404s. Probe API routes with curl, never the browser address bar.
- **`litellm` pulls a large transitive tree** (21 packages: `openai`, `tiktoken`, `tokenizers`, `aiohttp`, `jinja2`, `typer`, `huggingface-hub`). Phase 2 should expect a materially larger image layer.
- **CRLF warnings on every new file are expected and unfixed here** — `.gitattributes` is SETUP-03, owned by plan 01-04.

## Self-Check: PASSED

All 10 created files exist on disk and are tracked by git. Both task commits (`769b199`, `a9c0ef0`) are present in `git log`. `backend/app/market/` is unmodified.

**Note on `actuals.tokens`:** 5,516 is chars/4 over the 12 files actually authored (22,064 chars). It deliberately excludes `backend/uv.lock`, which also changed but is machine-generated — including its 451,747 chars would report ~118,000 tokens and would corrupt future estimates upward for any phase that touches a dependency, since regenerating a lockfile costs one command regardless of its size. Against the plan's estimate of 60,000 the authored work came in far under; the estimate appears to have been sized for total phase context rather than diff volume.
