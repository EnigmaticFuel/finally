---
phase: 2
slug: walking-skeleton-container
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-10
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `02-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

**Two tiers by design.** D-15 states that folding the container assertions into pytest "would put a Docker daemon dependency inside a suite that currently runs in seconds without one." The pytest suite stays Docker-free and acts as the regression guard; the smoke script is the phase proof and requires Docker.

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3+ with pytest-asyncio (`asyncio_mode = "auto"`) |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]`, `testpaths = ["tests"]` |
| **Quick run command** | `cd backend && uv run --extra dev pytest -q` |
| **Full suite command** | `cd backend && uv run --extra dev pytest -v` |
| **Estimated runtime** | ~5 seconds (no Docker dependency) |
| **Phase-2 harness** | `uv run scripts/smoke_check.py` — outside pytest by design (D-15) |
| **Lint** | `cd backend && uv run --extra dev ruff check app/ tests/` |

---

## Sampling Rate

- **After every task commit:** `cd backend && uv run --extra dev pytest -q` — this phase changes no `backend/app/` code, so any failure here is a regression from something the phase should not have touched
- **After every plan wave:** `docker build` + `uv run scripts/smoke_check.py`
- **Before `/gsd-verify-work`:** full `pytest -v` green, `ruff check app/ tests/` clean, `smoke_check.py` green
- **Max feedback latency:** ~10 seconds for the pytest tier; the Docker tier is wave-level, not per-task

---

## Per-Task Verification Map

Task rows are filled once PLAN.md files exist. The requirement-to-assertion map below is the contract each task's `<verify>` must draw from.

| Req ID | Behavior | Threat Ref | Test Type | Automated Command | File Exists |
|--------|----------|------------|-----------|-------------------|-------------|
| DOCK-01 | Multi-stage build completes; both stages present | T-2-05 | build | `docker build` exits 0 | ❌ W0 (`Dockerfile`) |
| DOCK-01 | Node stage output actually reaches the image | — | smoke | `GET /` returns the placeholder markup | ❌ W0 |
| DOCK-03 | API and static served from one origin, one port | — | smoke | `GET :8000/api/health` → 200 JSON **and** `GET :8000/` → 200 `text/html`, same host:port | ❌ W0 |
| DOCK-03 | Static mount does not shadow `/api/*` | — | smoke | `GET /api/health` body parses as JSON with key `status`, not HTML | ❌ W0 |
| DOCK-03 | SSE streams through the container | — | smoke | bounded read of `/api/stream/prices`; `content-type: text/event-stream` and ≥1 `data: ` frame | ❌ W0 |
| DOCK-04 | DB survives a restart | — | smoke | read `cash_balance` → restart → re-read; assert equal | ❌ W0 |
| DOCK-04 | The bind mount is the file being written | T-2-06 | smoke | host `db/finally.db` mtime advances after a container write | ❌ W0 |
| DOCK-04 | WAL actually engaged over the mount (D-16) | — | stress | assert `PRAGMA journal_mode` readback == `wal`, then N-way `BEGIN IMMEDIATE` contention; final value == committed count | ❌ W0 |
| DOCK-05 | `start` twice is safe | — | smoke | exit 0 both times; exactly one container exists | ❌ W0 |
| DOCK-05 | `stop` twice is safe | — | smoke | exit 0 both times | ❌ W0 |
| DOCK-05 | `stop` never touches `db/` | — | smoke | hash `db/finally.db` before and after `stop`; unchanged | ❌ W0 |
| DOCK-06 | Exactly one uvicorn worker (static) | — | smoke | `docker inspect --format '{{json .Config.Cmd}}'` contains `--workers 1` | ❌ W0 |
| DOCK-06 | Exactly one app process (runtime) | — | smoke | `docker top`; exactly 1 line matching `app.main:create_app` | ❌ W0 |
| DOCK-07 | `.env` reaches the container | — | smoke | `docker exec … printenv LLM_MOCK` matches `.env` | ❌ W0 |
| DOCK-07 | `.env` is NOT baked into the image | T-2-01 | build | `test ! -f /app/.env` inside the image | ❌ W0 |
| (regression) | Phase 1 suite still green | — | unit | `cd backend && uv run --extra dev pytest -q` | ✅ exists |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `.dockerignore` — prerequisite for every build task (build context is 298 MB today, 257 MB of it `backend/.venv`); blocks DOCK-01
- [ ] `Dockerfile` — covers DOCK-01, DOCK-03, DOCK-06, DOCK-07
- [ ] `scripts/smoke_check.py` — covers DOCK-01, DOCK-03, DOCK-04, DOCK-05, DOCK-06, DOCK-07
- [ ] `scripts/start_mac.sh`, `scripts/stop_mac.sh` — covers DOCK-05 (LF per `.gitattributes`)
- [ ] `scripts/start_windows.ps1`, `scripts/stop_windows.ps1` — covers DOCK-05 (CRLF, Windows PowerShell 5.1 semantics — `pwsh` is absent on this machine)
- [ ] WAL-over-bind-mount stress task — covers DOCK-04 / D-16
- [ ] `.gitignore` addition for the stress scratch DB
- [ ] Framework install: **none needed** — pytest is already configured and the smoke check runs on stdlib via `uv run`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A first-time user reaches a working terminal from one command | DOCK-05, success criterion 1 | "One command and it works" is a UX judgement the smoke check cannot make — the script asserts the endpoints respond, not that the experience reads as intended | Run `scripts/start_windows.ps1` from a clean state; confirm the printed output names the image and its build time (D-10), prints the URL without opening a browser (D-11), and that the page loads |
| Staleness print is legible | D-10 | The countermeasure's value is whether a human notices it | Build, then edit backend code and start without `--build`; confirm the printed build timestamp makes the staleness obvious |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s (pytest tier)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
