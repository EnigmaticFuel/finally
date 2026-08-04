# Technology Stack

**Analysis Date:** 2026-08-04

> **Scope note:** Only `backend/app/market/` is implemented in code. The FastAPI app entrypoint, `backend/app/api/`, `backend/app/db/`, `backend/app/llm/`, `backend/app/services/`, the entire `frontend/` project, `scripts/`, `Dockerfile`, `docker-compose.yml`, and `test/specs/` Playwright tests do not yet exist as files (directories are empty or absent). Everything below is marked **[BUILT]** (exists in code) or **[SPEC ONLY]** (described in `planning/PLAN.md` but not yet present in the repository).

## Languages

**Primary:**
- Python 3.12+ **[BUILT]** — `backend/app/market/` (market data subsystem: cache, simulator, Massive client, SSE stream). Declared via `requires-python = ">=3.12"` in `backend/pyproject.toml`.
- TypeScript **[SPEC ONLY]** — `planning/PLAN.md` specifies a Next.js/TypeScript frontend; `frontend/` is currently an empty directory with no `package.json`, no source files.

**Secondary:**
- None detected yet (no shell/SQL migration scripts present — `backend/app/db/` is empty).

## Runtime

**Environment:**
- Python 3.12 (backend), managed via `uv`. A `.venv` exists at `backend/.venv` (interpreter `pyvenv.cfg` present), created by `uv sync`.
- Node.js — **[SPEC ONLY]** for the frontend (PLAN.md specifies Node 22 in the Docker build stage); no Node project exists yet at the repo's `frontend/` path.
- A separate Node project already exists at `test/` (Playwright), with its own `node_modules` — this is the E2E test harness, not the frontend app.

**Package Manager:**
- `uv` (Python) — `backend/pyproject.toml` + `backend/uv.lock` (lockfile present, committed).
- npm — **[SPEC ONLY]** for `frontend/` (not yet present). `test/` (Playwright) has its own npm-managed `node_modules` but no visible `package.json` was found in the immediate `test/` directory during this scan (dependencies present, manifest not confirmed).

## Frameworks

**Core:**
- FastAPI `>=0.115.0` **[BUILT — dependency declared, no app wired up yet]** — declared in `backend/pyproject.toml`; used directly inside `backend/app/market/stream.py` to build an `APIRouter` for SSE (`create_stream_router`). No top-level FastAPI `app` instance / `main.py` exists yet — the market module only exposes a router factory for something else to mount.
- uvicorn `[standard]>=0.32.0` **[BUILT — declared, unused until an app exists]** — ASGI server dependency declared but no run script/entrypoint yet.
- Next.js **[SPEC ONLY]** — PLAN.md specifies a static-export Next.js frontend (`output: 'export'`); not present in code.

**Testing:**
- pytest `>=8.3.0` + `pytest-asyncio >=0.24.0` + `pytest-cov >=5.0.0` **[BUILT]** — `backend/pyproject.toml` (`[project.optional-dependencies].dev`), configured in `[tool.pytest.ini_options]` (asyncio_mode = "auto", testpaths = ["tests"]). Tests exist under `backend/tests/market/` (and empty `backend/tests/{api,db,llm,services}/` directories awaiting future code), plus `backend/tests/conftest.py`.
- Playwright — **[BUILT as tooling, SPEC ONLY as tests]** — `test/` has `node_modules` including `playwright`, `@playwright/test`, `playwright-core` installed, and a `playwright-report/` from a prior run, but `test/specs/` contains no spec files yet.
- React Testing Library — **[SPEC ONLY]** (PLAN.md section 12 mentions it for frontend unit tests; no frontend project exists).

**Build/Dev:**
- ruff `>=0.7.0` **[BUILT]** — linter, configured in `backend/pyproject.toml` (`[tool.ruff]`: line-length 100, target py312, `select = ["E","F","I","N","W"]`, `ignore = ["E501"]`). Cache present at `backend/.ruff_cache/`.
- hatchling — build backend for the `finally-backend` Python package (`[build-system]` in `backend/pyproject.toml`).

## Key Dependencies

**Critical (declared in `backend/pyproject.toml`):**
- `fastapi>=0.115.0` — HTTP framework, used for the SSE router today.
- `uvicorn[standard]>=0.32.0` — ASGI server.
- `numpy>=2.0.0` — used in `backend/app/market/simulator.py` for the correlated GBM math (Cholesky factorization for correlated ticker moves).
- `massive==2.2.0` — official client SDK for the Massive (Polygon.io) market data API; used in `backend/app/market/massive_client.py` (`from massive import RESTClient`, `from massive.rest.models import SnapshotMarketType`).
- `rich>=13.0.0` — used by `backend/market_data_demo.py` for a live terminal dashboard demo of the simulated price feed.

**Declared but not yet in `pyproject.toml` / `uv.lock` — installed loose in the venv:**
- `litellm` is present under `backend/.venv/Lib/site-packages/litellm/` but is **absent from both `backend/pyproject.toml` and `backend/uv.lock`**. This means the LLM integration PLAN.md specifies (LiteLLM → OpenRouter with Cerebras inference) has not yet been added as a real project dependency — the package appears to be a stray/pre-installed artifact in the virtualenv, not a reproducible lockfile entry. Whoever builds `backend/app/llm/` must run `uv add litellm` (or equivalent) to make this dependency real and reproducible.
- No OpenRouter SDK, no `openai` package, no structured-output library declared.

**Infrastructure (all [SPEC ONLY], not present in code):**
- SQLite via Python's stdlib `sqlite3` or an ORM — `backend/app/db/` is an empty directory; no schema SQL, no ORM (SQLAlchemy/etc.) declared in `pyproject.toml`.
- Docker — no `Dockerfile` or `docker-compose.yml` present at repo root despite being specified in PLAN.md section 11.

## Configuration

**Environment:**
- `.env` exists at the project root (confirmed present, git-ignored via `.gitignore:138`). Contents not read (forbidden file — secrets). No `.env.example` file was found in this scan despite PLAN.md section 5 specifying one should be committed.
- Per PLAN.md, expected variables: `OPENROUTER_API_KEY`, `MASSIVE_API_KEY`, `LLM_MOCK`. Only `MASSIVE_API_KEY` is actually consumed by code today, in `backend/app/market/factory.py`:
  ```python
  api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
  ```
  `OPENROUTER_API_KEY` and `LLM_MOCK` are not referenced anywhere in `backend/app/` yet (no `backend/app/llm/` code exists).

**Build:**
- `backend/pyproject.toml` — Python project manifest, dependency groups, ruff/pytest/coverage config.
- `backend/uv.lock` — Python dependency lockfile (committed).
- No frontend build config (`next.config.js`, `tsconfig.json`, `tailwind.config.*`) exists yet.

## Platform Requirements

**Development:**
- Python >=3.12, `uv` package manager (per user's global CLAUDE.md: always `uv run`/`uv add`, never bare `python`/`pip`).
- Windows 11 dev environment (per environment info), Git Bash shell.
- Node.js for the future frontend and for the already-set-up Playwright E2E harness in `test/`.

**Production:**
- **[SPEC ONLY]** Single Docker container, multi-stage build (Node 22 → Python 3.12 slim), exposing port 8000, FastAPI serving both `/api/*` and the static Next.js export. None of this exists in code yet — no `Dockerfile`.

---

*Stack analysis: 2026-08-04*
