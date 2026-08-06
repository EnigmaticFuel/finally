---
phase: 1
slug: foundation-spine
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-05
updated: 2026-08-06
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

**D-24 gate wording:** the phase gate is *no new failures relative to the pre-phase baseline*, not a literal 154/154. `tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval` fails roughly 3 runs in 10 on the unmodified current environment — a pre-existing timing flake, not a regression. Record the pre-phase baseline before the first task lands, and compare against it.

---

## Per-Task Verification Map

Filled in after execution. Plans are the unit of work in this phase, so the Plan column carries the identifier and `Task ID` stays `—`. Three node IDs seeded at plan time did not match the tests actually written; the corrected IDs are recorded below and each was confirmed to collect.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| — | 01-01 | 1 | CORE-01 | — | N/A | unit | `pytest tests/test_main.py::test_create_app_builds_cache_before_routers -x` | ✅ exists | ✅ green |
| — | 01-01 | 1 | CORE-02 | — | N/A | integration | `pytest tests/test_main.py::test_lifespan_starts_and_stops_source -x` | ✅ exists | ✅ green |
| — | 01-01 | 1 | CORE-03 | — | N/A | integration | `pytest tests/market/test_stream_integration.py -x` | ✅ exists | ✅ green |
| — | 01-02 | 2 | CORE-04 | — | N/A | unit | `pytest tests/db/test_seed.py -x` | ✅ exists | ✅ green |
| — | 01-02 | 2 | CORE-04 | — | N/A | unit | `pytest tests/db/test_seed.py::TestApplySchema::test_is_idempotent -x` | ✅ exists | ✅ green |
| — | 01-02 | 2 | CORE-05 | T-1-02 | Concurrent writes never corrupt or deadlock | integration | `pytest tests/db/test_concurrency.py -x` | ✅ exists | ✅ green |
| — | 01-02 | 2 | CORE-05 | T-1-02 | WAL + `busy_timeout` set on every open | unit | `pytest tests/db/test_connection.py -x` | ✅ exists | ✅ green |
| — | 01-02 | 2 | CORE-06 | — | N/A | unit | `pytest tests/db/test_money.py -x` | ✅ exists | ✅ green |
| — | 01-01 | 1 | CORE-07 | — | N/A | unit | `pytest tests/test_main.py::test_cache_via_dependency -x` | ✅ exists | ✅ green |
| — | 01-01 | 1 | CORE-08 | T-1-03 | Health payload leaks no secrets | unit | `pytest tests/api/test_health.py -x` | ✅ exists | ✅ green |
| — | 01-01 | 1 | CORE-09 | T-1-01 | `/api/*` never shadowed by static mount | integration | `pytest tests/test_main.py::test_api_not_shadowed -x` | ✅ exists | ✅ green |
| — | 01-02 | 2 | CORE-10 | — | N/A | unit | `pytest tests/db/test_connection.py::TestRunDb::test_run_db_offloads -x` | ✅ exists | ✅ green |
| — | 01-03 | 3 | TEST-01 | — | N/A | unit | `pytest tests/db -q` | ✅ exists | ✅ green |
| — | 01-01 | 1 | SETUP-01 | — | N/A | smoke | `uv run --frozen python -c "import litellm, pydantic, dotenv"` | ✅ exists | ✅ green |
| — | 01-05 | 4 | SETUP-06 | — | N/A | regression | `uv run --extra dev pytest -q` | ✅ exists | ✅ green |
| — | 01-04 | 3 | SETUP-03 | — | N/A | manual | `git check-attr text eol -- scripts/start_mac.sh scripts/start_windows.ps1 Dockerfile db/finally.db` | n/a | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Node-ID corrections made against the plan-time seed:**

| Seeded (did not collect) | Actual |
|---|---|
| `tests/test_main.py::test_create_app_builds` | `tests/test_main.py::test_create_app_builds_cache_before_routers` |
| `tests/db/test_seed.py::test_seed_is_idempotent` | `tests/db/test_seed.py::TestApplySchema::test_is_idempotent` |
| `tests/db/test_connection.py::test_run_db_offloads` | `tests/db/test_connection.py::TestRunDb::test_run_db_offloads` |

**SETUP-03 command changed.** `git ls-files --eol scripts/ Dockerfile` returns nothing — `scripts/` and `Dockerfile` are Phase 7 deliverables and are not tracked yet, so the command passes vacuously. `git check-attr` resolves the attribute for an untracked path and is the check the verification report actually used: `.sh` and `Dockerfile` resolve `eol: lf`, `.ps1` resolves `eol: crlf`, `db/finally.db` resolves `text: unset`.

**Last run:** 243 passed, 0 failed (`uv run --extra dev pytest -q`, 7.48s).

---

## Wave 0 Requirements

All eleven items delivered and passing.

- [x] `tests/conftest.py` — extend with the `create_app()` + DB-dependency-override fixture (D-22); clear `MASSIVE_API_KEY` for the session so a developer holding that key does not have the suite hit the live Massive API
- [x] `tests/db/__init__.py`, `tests/api/__init__.py` — these package dirs currently hold only stale `__pycache__`
- [x] `tests/db/test_connection.py` — WAL, `busy_timeout`, `writing()` rollback, `run_db` offload
- [x] `tests/db/test_seed.py` — fresh seed plus idempotency (CORE-04)
- [x] `tests/db/test_queries.py` — every query function
- [x] `tests/db/test_money.py` — rounding and epsilon (CORE-06 / TEST-01)
- [x] `tests/db/test_concurrency.py` — D-20 threaded contention against a `tmp_path` file DB
- [x] `tests/api/test_health.py` — CORE-08
- [x] `tests/test_main.py` — assembly, lifespan, DI, `/api/*` precedence
- [x] `tests/market/test_stream_integration.py` — CORE-03, using the **uvicorn-in-thread** pattern, not `TestClient` (Pitfall 2: both `TestClient.stream()` and `httpx.ASGITransport` hang forever on an infinite stream)
- [x] Dev dependency: `uv add --optional dev "httpx>=0.28.0"` (D-25)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Line endings normalized per `.gitattributes` | SETUP-03 | Git attribute behavior is a property of the index, not of running code | `git ls-files --eol scripts/ Dockerfile` — expect `w/lf` for `.sh` and `Dockerfile`, `w/crlf` for `.ps1` |
| Tracked `db/finally.db` ships the standard seed | D-23 / CORE-04 | Asserting on a committed binary is a one-time content check, not a repeatable unit test | Open the committed file and confirm $10,000 cash, ten watchlist tickers, one snapshot, no trades and no chat messages |
| No stale `__pycache__` under `backend/` | SETUP-05 | Filesystem hygiene check on the working tree | `git ls-files backend | grep __pycache__` returns nothing, and the directories are absent |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s — full suite runs in 7.48s; the per-commit `tests/db tests/api` slice stays under 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-08-06 during Phase 1 UAT (`/gsd-verify-work 01`, test 6).
