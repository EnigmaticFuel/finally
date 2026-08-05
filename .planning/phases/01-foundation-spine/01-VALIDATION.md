---
phase: 1
slug: foundation-spine
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-05
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `01-RESEARCH.md` → `## Validation Architecture` (baseline verified by execution).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 (`asyncio_mode = "auto"`) |
| **Config file** | `backend/pyproject.toml` → `[tool.pytest.ini_options]`, `testpaths = ["tests"]` |
| **Quick run command** | `cd backend && uv run --extra dev pytest -q tests/db tests/api` |
| **Full suite command** | `cd backend && uv run --extra dev pytest -q` |
| **Lint command** | `cd backend && uv run --extra dev ruff check app/ tests/` |
| **Estimated runtime** | ~3 seconds (baseline: 154 passed in 2.41s, verified) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run --extra dev pytest -q tests/db tests/api` — fast, and the DB layer is where this phase's risk concentrates
- **After every plan wave:** Run `cd backend && uv run --extra dev pytest -q` plus `uv run --extra dev ruff check app/ tests/`
- **Before `/gsd-verify-work`:** Full suite green, subject to the D-24 gate wording below
- **Max feedback latency:** 5 seconds

**D-24 gate wording:** the phase gate is *no new failures relative to the pre-phase baseline*, not a literal 154/154. `tests/market/test_simulator.py::test_custom_update_interval` fails roughly 3 runs in 10 on the unmodified current environment — a pre-existing timing flake, not a regression. Record the pre-phase baseline before the first task lands, and compare against it.

---

## Per-Task Verification Map

Task IDs are assigned once plans exist; this map is keyed by requirement until then and is filled in by `/gsd-validate-phase`.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | CORE-01 | — | N/A | unit | `pytest tests/test_main.py::test_create_app_builds -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CORE-02 | — | N/A | integration | `pytest tests/test_main.py::test_lifespan_starts_and_stops_source -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CORE-03 | — | N/A | integration | `pytest tests/market/test_stream_integration.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CORE-04 | — | N/A | unit | `pytest tests/db/test_seed.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CORE-04 | — | N/A | unit | `pytest tests/db/test_seed.py::test_seed_is_idempotent -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CORE-05 | T-1-02 | Concurrent writes never corrupt or deadlock | integration | `pytest tests/db/test_concurrency.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CORE-05 | T-1-02 | WAL + `busy_timeout` set on every open | unit | `pytest tests/db/test_connection.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CORE-06 | — | N/A | unit | `pytest tests/db/test_money.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CORE-07 | — | N/A | unit | `pytest tests/test_main.py::test_cache_via_dependency -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CORE-08 | T-1-03 | Health payload leaks no secrets | unit | `pytest tests/api/test_health.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CORE-09 | T-1-01 | `/api/*` never shadowed by static mount | integration | `pytest tests/test_main.py::test_api_not_shadowed -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CORE-10 | — | N/A | unit | `pytest tests/db/test_connection.py::test_run_db_offloads -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | TEST-01 | — | N/A | unit | `pytest tests/db -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SETUP-01 | — | N/A | smoke | `uv run --frozen python -c "import litellm, pydantic, dotenv"` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SETUP-06 | — | N/A | regression | `uv run --extra dev pytest -q` | ✅ exists | ⬜ pending |
| TBD | TBD | TBD | SETUP-03 | — | N/A | manual | `git ls-files --eol scripts/ Dockerfile` | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — extend with the `create_app()` + DB-dependency-override fixture (D-22); clear `MASSIVE_API_KEY` for the session so a developer holding that key does not have the suite hit the live Massive API
- [ ] `tests/db/__init__.py`, `tests/api/__init__.py` — these package dirs currently hold only stale `__pycache__`
- [ ] `tests/db/test_connection.py` — WAL, `busy_timeout`, `writing()` rollback, `run_db` offload
- [ ] `tests/db/test_seed.py` — fresh seed plus idempotency (CORE-04)
- [ ] `tests/db/test_queries.py` — every query function
- [ ] `tests/db/test_money.py` — rounding and epsilon (CORE-06 / TEST-01)
- [ ] `tests/db/test_concurrency.py` — D-20 threaded contention against a `tmp_path` file DB
- [ ] `tests/api/test_health.py` — CORE-08
- [ ] `tests/test_main.py` — assembly, lifespan, DI, `/api/*` precedence
- [ ] `tests/market/test_stream_integration.py` — CORE-03, using the **uvicorn-in-thread** pattern, not `TestClient` (Pitfall 2: both `TestClient.stream()` and `httpx.ASGITransport` hang forever on an infinite stream)
- [ ] Dev dependency: `uv add --optional dev "httpx>=0.28.0"` (D-25)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Line endings normalized per `.gitattributes` | SETUP-03 | Git attribute behavior is a property of the index, not of running code | `git ls-files --eol scripts/ Dockerfile` — expect `w/lf` for `.sh` and `Dockerfile`, `w/crlf` for `.ps1` |
| Tracked `db/finally.db` ships the standard seed | D-23 / CORE-04 | Asserting on a committed binary is a one-time content check, not a repeatable unit test | Open the committed file and confirm $10,000 cash, ten watchlist tickers, one snapshot, no trades and no chat messages |
| No stale `__pycache__` under `backend/` | SETUP-05 | Filesystem hygiene check on the working tree | `git ls-files backend | grep __pycache__` returns nothing, and the directories are absent |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
