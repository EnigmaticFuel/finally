# External Integrations

**Analysis Date:** 2026-08-04

> **Scope note:** Only the market-data integration (Massive/Polygon.io + an in-process simulator) is implemented in code, under `backend/app/market/`. The LLM integration (LiteLLM/OpenRouter/Cerebras), the database, auth, hosting, and CI/CD described in `planning/PLAN.md` are **not yet implemented** — marked [SPEC ONLY] below.

## APIs & External Services

**Market Data:**
- **Massive (Polygon.io)** — [BUILT] `backend/app/market/massive_client.py`, class `MassiveDataSource`.
  - SDK/Client: `massive==2.2.0` (`from massive import RESTClient`, `from massive.rest.models import SnapshotMarketType`), declared in `backend/pyproject.toml`.
  - Auth: `MASSIVE_API_KEY` environment variable, read in `backend/app/market/factory.py` (`os.environ.get("MASSIVE_API_KEY", "").strip()`). If unset/empty, the factory silently falls back to the in-process simulator (`SimulatorDataSource` in `backend/app/market/simulator.py`) — there is no hard dependency on this API.
  - Endpoints used: `client.get_snapshot_all(market_type=SnapshotMarketType.STOCKS, tickers=[...])` (polling snapshot), `client.get_aggs(...)` (historical minute bars for sparkline backfill), `client.get_market_status()` (open/closed diagnostics).
  - Call pattern: REST polling (not WebSocket/streaming), synchronous SDK calls run via `asyncio.to_thread` to avoid blocking the event loop. Poll interval defaults to 15s (`poll_interval: float = 15.0` — sized for the free tier's 5 req/min limit); a backoff multiplier (up to 8x) kicks in on repeated failures.
  - Known API quirk documented in code: `massive_client.py:_extract_quote` — timestamp units are inconsistent across response fields (`last_trade.timestamp` is nanoseconds, `Agg.timestamp`/`min.timestamp` is milliseconds); the code explicitly divides by the correct unit per field to avoid silently producing timestamps decades in the future.

- **In-process GBM Simulator** — [BUILT] `backend/app/market/simulator.py`, classes `GBMSimulator` and `SimulatorDataSource`. Not an external integration (no network calls) but is the default/no-key data source, selected by `create_market_data_source()` in `backend/app/market/factory.py` whenever `MASSIVE_API_KEY` is empty.

**LLM / AI:**
- **LiteLLM → OpenRouter (Cerebras inference provider)** — [SPEC ONLY]. `planning/PLAN.md` section 9 specifies calling `openrouter/openai/gpt-oss-120b` via LiteLLM with structured outputs, guided by the `cerebras` skill. No code exists yet under `backend/app/llm/` (directory is empty). The `litellm` package is present in the venv (`backend/.venv/Lib/site-packages/litellm/`) but is **not declared** in `backend/pyproject.toml` or `backend/uv.lock` — it must be added as a real dependency before this integration can be built.
  - Auth (per PLAN.md, not yet consumed by any code): `OPENROUTER_API_KEY` environment variable. The app is specified to degrade gracefully (chat returns a friendly "no key configured" message) rather than fail startup — this behavior does not exist yet since `/api/chat` does not exist.

## Data Storage

**Databases:**
- SQLite — [SPEC ONLY]. PLAN.md section 7 specifies a single-file SQLite database at `db/finally.db` with lazy initialization (schema created and seeded on first request if missing). `db/finally.db` currently exists on disk at the repo root (0 bytes / uncreated by real code — no `backend/app/db/` code exists to have created it; likely a placeholder or artifact of local testing). No schema SQL, no ORM, no migration tooling declared in `backend/pyproject.toml`.
- Tables specified but not implemented: `users_profile`, `watchlist`, `positions`, `trades`, `portfolio_snapshots`, `chat_messages` (PLAN.md section 7).

**File Storage:**
- None. Local filesystem only (SQLite file + static frontend export, per PLAN.md). No cloud storage SDK present.

**Caching:**
- In-memory only — `PriceCache` (`backend/app/market/cache.py`), a thread-safe (`threading.Lock`) dict-backed cache of latest/previous/open price and a bounded `deque` history per ticker (60 points, `HISTORY_POINTS = 60`). Not a distributed cache (no Redis/Memcached); single-process, in-memory, lost on restart. This is the single source of truth read by the (not-yet-built) SSE stream consumers, portfolio valuation, and trade execution.

## Authentication & Identity

**Auth Provider:**
- None. PLAN.md explicitly states this is a single-user, no-login application (`user_id` columns default to `"default"` string, hardcoded). No auth library, no session/cookie handling, no OAuth integration anywhere in the codebase.

## Monitoring & Observability

**Error Tracking:**
- None. No Sentry/Datadog/error-tracking SDK declared.

**Logs:**
- Python stdlib `logging` module — used throughout `backend/app/market/` (e.g., `logger = logging.getLogger(__name__)` in `factory.py`, `massive_client.py`, `stream.py`, `simulator.py`). No structured logging framework, no external log shipping.

## CI/CD & Deployment

**Hosting:**
- [SPEC ONLY] PLAN.md section 11 specifies a single Docker container (multi-stage: Node 22 → Python 3.12 slim) exposing port 8000, deployable to AWS App Runner, Render, or similar. No `Dockerfile`, `docker-compose.yml`, or `deploy/` Terraform config exists in the repo yet.

**CI Pipeline:**
- GitHub Actions — [BUILT, but for AI-assisted code review, not build/test/deploy].
  - `.github/workflows/claude.yml` — triggers Claude Code on issue comments, PR review comments, and issue/PR events containing `@claude`, using `anthropics/claude-code-action@v1`. Auth: `secrets.CLAUDE_CODE_OAUTH_TOKEN` (GitHub Actions secret).
  - `.github/workflows/claude-code-review.yml` — present alongside (not inspected in detail, but implied to be an automated PR review workflow using the same Claude Code Action).
  - No test-running, lint-running, or build/deploy pipeline for the application itself was found (no `pytest`/`npm test`/`docker build` steps in workflows scanned).

## Environment Configuration

**Required env vars (per code, today):**
- `MASSIVE_API_KEY` — optional; read in `backend/app/market/factory.py`. Empty/absent → simulator used instead of real market data.

**Required env vars (per PLAN.md, not yet consumed by any code):**
- `OPENROUTER_API_KEY` — for LLM chat (not yet wired up).
- `LLM_MOCK` — deterministic mock LLM responses for testing (not yet wired up).

**Secrets location:**
- `.env` file at project root — confirmed present on disk, git-ignored (`.gitignore:138`). No `.env.example` found in this scan (PLAN.md section 5 specifies one should be committed as a template — currently missing or not detected).

## Webhooks & Callbacks

**Incoming:**
- None. No webhook receiver endpoints exist (no `backend/app/api/` code at all yet).

**Outgoing:**
- None currently invoked by application code (the Massive REST polling above is outbound HTTP but is request/response polling, not a webhook).

---

*Integration audit: 2026-08-04*
