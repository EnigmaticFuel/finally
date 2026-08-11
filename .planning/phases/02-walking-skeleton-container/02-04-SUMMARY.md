---
phase: 02-walking-skeleton-container
plan: 04
subsystem: infra
tags: [smoke-test, docker, sse, sqlite, bind-mount, idempotency, verification, pep723]

requires:
  - phase: 02-walking-skeleton-container
    provides: "finally-app:latest image (02-01), the four lifecycle scripts (02-02), the container-invocation shape and the db/finally.db baseline digest (02-03)"
  - phase: 01-backend-spine
    provides: "backend/tests/test_main.py assertion set (HEALTH_KEYS, the retry frame, the Accept matrix), backend/app/api/health.py, backend/static/index.html"
provides:
  - "scripts/smoke_check.py - stdlib-only PEP 723 script, eleven named checks plus two lifecycle helpers, run as uv run scripts/smoke_check.py"
  - "One recorded green run: 11 checks, 11 passed, 0 failed, exit 0, from a clean container namespace"
  - "The proof that all four ROADMAP Phase 2 success criteria hold against a real container"
  - "The foundation Phase 7's Playwright E2E suite layers on rather than duplicates"
affects: [07-docker-e2e, 03-portfolio-api]

actuals:
  tokens: 2100
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A verification script drives the container through the platform's own lifecycle scripts, so the readiness gate is inherited and a script regression fails the check"
    - "A bounded SSE read (line-count ceiling plus socket timeout) rather than curl -N --max-time, which exits 28 on the timeout it was told to hit"
    - "Host-side sqlite access through a mode=ro URI whenever the file being read is tracked"

key-files:
  created:
    - "scripts/smoke_check.py"
  modified: []

key-decisions:
  - "The identity assertion turns on users_profile.created_at, not cash_balance or the watchlist count - the latter two are exactly what a freshly seeded container-local database would also produce, so only the seed timestamp distinguishes a real mount from a convincing fake"
  - "check_stop_leaves_db_untouched starts the container itself before hashing, because hashing either side of a stop that had nothing to stop would prove nothing"
  - "The per-check report continues past a failure rather than aborting, so a run says how much of the skeleton is standing rather than naming one problem and hiding the rest"
  - "The 200-on-text/html row is asserted as correct behaviour with the reason written into the docstring, because the next reader's instinct is to fix it"

patterns-established:
  - "Lifecycle helpers are named, ordered and deliberately excluded from the check count - they are how the container reaches the state a check needs, not something being asserted"

requirements-completed: [DOCK-01, DOCK-03, DOCK-04, DOCK-05, DOCK-06, DOCK-07]

coverage:
  - id: D1
    description: "One container serves the API and the page on one origin and port, and the static mount does not shadow the API for any JSON client"
    requirement: DOCK-03
    verification:
      - kind: integration
        ref: "check_health, check_static_page, check_api_not_shadowed - all PASS in the recorded run"
        status: pass
    human_judgment: false
  - id: D2
    description: "The live price stream survives containerization - text/event-stream, retry: 1000 opener, at least one data frame within a bounded read"
    requirement: DOCK-03
    verification:
      - kind: integration
        ref: "check_sse_stream - PASS"
        status: pass
    human_judgment: false
  - id: D3
    description: "The container reads the host's database through the bind mount, not a container-local copy, and the seeded values survive a full destroy and recreate"
    requirement: DOCK-04
    verification:
      - kind: integration
        ref: "check_db_identity and check_persistence_across_restart - PASS; created_at 2026-08-06T18:04:55.054196+00:00 identical host and container, and identical across the recreate"
        status: pass
    human_judgment: false
  - id: D4
    description: "Start and stop are both idempotent, and a stop cannot cost the user their portfolio"
    requirement: DOCK-05
    verification:
      - kind: integration
        ref: "check_start_is_idempotent, check_stop_is_idempotent, check_stop_leaves_db_untouched - PASS; sha256 c8d433f3...1d1257 identical before and after"
        status: pass
    human_judgment: false
  - id: D5
    description: "Exactly one uvicorn worker, and every .env key delivered by --env-file with no .env in any image layer"
    requirement: DOCK-06, DOCK-07
    verification:
      - kind: integration
        ref: "check_single_worker and check_env_delivered - PASS"
        status: pass
    human_judgment: false
  - id: D6
    description: "One command reaches a working terminal, and the staleness print is legible enough that a human notices it"
    verification: []
    human_judgment: true
    rationale: "Recorded in 02-VALIDATION.md as a Manual-Only Verification and restated in this plan's phase-level human check. The smoke check asserts the endpoints respond; whether the experience reads as intended and whether a buried build timestamp is noticed are UX judgements no script can make"

duration: 47min
completed: 2026-08-11
status: complete
---

# Phase 02 Plan 04: Smoke Check Summary

**One committed, re-runnable command - `uv run scripts/smoke_check.py` - drives the container through the platform's own start and stop scripts and proves all four ROADMAP Phase 2 success criteria in eleven named checks, green from a clean state with `db/finally.db` byte-identical either side of the run.**

## Performance

- **Duration:** 47 min
- **Started:** 2026-08-11T15:58:00Z
- **Completed:** 2026-08-11T16:45:00Z
- **Tasks:** 2
- **Files modified:** 1 created, 0 modified

## Accomplishments

- **The phase's claim is now re-checkable rather than historical.** Every assertion plans 02-01, 02-02 and 02-03 made by hand at a terminal is now a named function anyone can re-run in one command.
- **D-13's claim is literally true rather than aspirational.** The script contains no wait logic of its own. It shells out to `start_windows.ps1` / `start_mac.sh`, which do not return until `/api/health` has answered 200, so a regression in either start script fails the smoke check instead of hiding behind a duplicated timer.
- **The mount assertion is not satisfiable by a fake.** `users_profile.created_at` is the load-bearing value; `cash_balance = 10000.0` and a watchlist of ten are exactly what a freshly seeded container-local database would also produce.
- **The Accept-gated SPA fallback is documented in the place a future reader will look.** `/api/nope` with `Accept: text/html` returning **200** is asserted as correct, with the reason in the docstring, because a smoke check written from scratch would report it as a bug and "fix" the mount order.
- **The pytest suite stayed Docker-free.** 243 passed in **8.66s** with no Docker daemon involved, which is the whole reason D-15 rejected folding these assertions into `backend/tests/`.

## The recorded green run (verbatim)

Run from a clean container namespace (`docker ps -aq --filter "name=^finally-app$"` empty):

```
  start: Image:      finally-app:latest
  start: Built:      2026-08-11T11:04:12.472781294Z
  start: http://localhost:8000
PASS check_health
PASS check_static_page
PASS check_api_not_shadowed
PASS check_sse_stream
PASS check_single_worker
PASS check_env_delivered
PASS check_db_identity
  stop: Stopped and removed container finally-app.
  start: Image:      finally-app:latest
  start: Built:      2026-08-11T11:04:12.472781294Z
  start: http://localhost:8000
PASS check_persistence_across_restart
  start: Container finally-app is already running.
  start: http://localhost:8000
  start: Container finally-app is already running.
  start: http://localhost:8000
PASS check_start_is_idempotent
  stop: Stopped and removed container finally-app.
  stop: No container named finally-app exists. Nothing to stop.
PASS check_stop_is_idempotent
  start: Image:      finally-app:latest
  start: Built:      2026-08-11T11:04:12.472781294Z
  start: http://localhost:8000
  stop: Stopped and removed container finally-app.
PASS check_stop_leaves_db_untouched
  stop: No container named finally-app exists. Nothing to stop.
11 checks, 11 passed, 0 failed
EXIT=0
```

`start_container` and `stop_container` print with a `  start:` / `  stop:` prefix and produce no `PASS` line, which is the visible form of their not being checks.

## Measured evidence (requested by the plan's `<output>`)

| Measurement | Value |
|---|---|
| Image certified by the run | `finally-app:latest` |
| Build timestamp certified (T-2-05) | `2026-08-11T11:04:12.472781294Z` |
| `users_profile.created_at`, host read (`mode=ro`) | `2026-08-06T18:04:55.054196+00:00` |
| `users_profile.created_at`, in-container read | `2026-08-06T18:04:55.054196+00:00` |
| `users_profile.cash_balance`, host / container | `10000.0` / `10000.0` |
| `count(*)` from `watchlist`, host / container | `10` / `10` |
| Same three values after a full destroy and recreate | identical |
| `sha256sum db/finally.db` before the run | `c8d433f3cd87ecca57c160ba07789a978807cc3217cd902e7c1c96460e1d1257` |
| `sha256sum db/finally.db` after the run | `c8d433f3cd87ecca57c160ba07789a978807cc3217cd902e7c1c96460e1d1257` |
| `git status --porcelain db/` after the run | empty |
| `ls db/` after the run | `finally.db`, `finally.db-shm`, `finally.db-wal` (both sidecars gitignored) |
| Backend suite, `uv run --extra dev pytest -q` from `backend/` | **243 passed in 8.66s**, 2 pre-existing websockets deprecation warnings |
| `uv run --extra dev ruff check app/ tests/` | `All checks passed!` |
| `uv run --extra dev ruff check ../scripts/smoke_check.py` | `All checks passed!` |

### Script gates

| Gate | Result |
|---|---|
| `head -6` contains `# /// script` | pass |
| `from __future__ import annotations` present | pass |
| Non-printable bytes (emoji check) | `0` |
| The nine Task 1 function definitions | `9` |
| The five Task 2 check definitions | `5` |
| Third-party imports (`httpx`, `requests`, `pytest`) | `0` |
| `sys.platform` occurrences | `1` |
| `INSERT` / `UPDATE` / `DELETE` / `DROP` occurrences | `0` |
| `mode=ro` occurrences | `2` (host read and the in-container read source) |
| `git status --porcelain backend/tests/` | empty |

### The induced failure (Task 1 acceptance criterion)

The container was stopped mid-run by inserting one stand-in step into `CHECK_ORDER` from a throwaway driver, so the real check functions and the real `main()` reporting loop were exercised rather than simulated:

```
PASS check_health
PASS stop_the_container_mid_run
FAIL check_static_page: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
FAIL check_single_worker: docker top finally-app exited 1: Error response from daemon: container 95e34bbc... is not running
4 checks, 2 passed, 2 failed
EXIT=1
```

Each failure names its check, the run continues rather than aborting on the first, and the exit code is non-zero.

### Success criteria to checks

| ROADMAP Phase 2 success criterion | Checks proving it |
|---|---|
| 1. One container serves the API and the page on one origin | `check_health`, `check_static_page`, `check_api_not_shadowed` (+ `check_sse_stream`) |
| 2. Data persists across container restarts | `check_db_identity`, `check_persistence_across_restart`, `check_stop_leaves_db_untouched` |
| 3. Start and stop scripts are safe to run repeatedly | `check_start_is_idempotent`, `check_stop_is_idempotent` |
| 4. Configuration arrives by one channel, one worker serves | `check_env_delivered`, `check_single_worker` |

## Task Commits

1. **Task 1: serving, streaming, worker and configuration assertions** - `5d7709a` (feat)
2. **Task 2: persistence, lifecycle idempotency, and one full green run** - `3e845ed` (feat)

## Files Created/Modified

- `scripts/smoke_check.py` - stdlib-only PEP 723 script, 468 lines. Two lifecycle helpers (`start_container`, `stop_container`) select the platform script on `sys.platform` and shell out; eleven checks assert the four-key health contract, the byte-identical static page, the full Accept matrix, the bounded SSE read, both halves of the single-worker guarantee, both halves of `.env` delivery, database identity by seed timestamp, persistence across a destroy-and-recreate, start and stop idempotency, and the `db/finally.db` digest across a stop. `main()` runs `CHECK_ORDER` in a fixed order, prints one line per check, and ends with `11 checks, N passed, M failed`.

## Decisions Made

- **`check_stop_leaves_db_untouched` starts the container itself.** Placing it after `check_stop_is_idempotent` in the plan's stated order left nothing running, and hashing either side of a no-op stop would have turned the check into a test of nothing. It now starts, hashes, stops a live container, and hashes again.
- **The checks are a flat ordered tuple, and the lifecycle-driving checks own their own start and stop.** This keeps `main()` a single loop with one reporting path, rather than a procedural body where the failure handling would have to be repeated around each lifecycle step.
- **`urllib.error.HTTPError` is caught in exactly one helper.** This is required control flow, not defensive programming: `urllib` raises on every non-2xx, so the mount-order check could not observe the 404 it exists to assert without it. Every other HTTP failure surfaces with its traceback, as the plan requires.
- **`.env` values are read into memory and never printed on any path.** A mismatch names the key and stops (T-2-08).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `.env` was absent from the parallel-execution worktree**

- **Found during:** Task 1 precondition check
- **Issue:** `.env` is gitignored (`.gitignore:138`), so a fresh worktree checkout does not contain it. Both `--env-file .env` in the start script and `check_env_delivered` are unsatisfiable without it. Plans `02-01` and `02-02` hit and documented the identical condition.
- **Fix:** Copied the project root's `.env` into the worktree root. The precondition holds at the project level; the worktree simply lacked an untracked local file.
- **Files modified:** none tracked; the copied `.env` is untracked and gitignored
- **Verification:** `git check-ignore -v .env` -> `.gitignore:138:.env`; `git status --porcelain` never shows it
- **Committed in:** nothing - deliberately not committed

---

**2. [Rule 3 - Blocking] `uv` could not create the worktree venv under OneDrive**

- **Found during:** Task 1 lint gate
- **Issue:** `uv run --project backend` failed with `failed to hardlink file ... The cloud operation cannot be performed on a file with incompatible hardlinks. (os error 396)`. The worktree lives inside a OneDrive-synced tree, which does not support the hardlinks uv's default link mode uses.
- **Fix:** `export UV_LINK_MODE=copy` for every `uv` invocation in this session - the mode uv's own warning recommends for this exact condition. No project file changed.
- **Files modified:** none
- **Verification:** the venv installed 68 packages and every subsequent `uv run` succeeded
- **Committed in:** nothing - an environment setting, not a repository change

---

**Total deviations:** 2 auto-fixed (both blocking)
**Impact on plan:** No scope change. Both are artifacts of running inside a OneDrive-synced git worktree, not of the plan.

## Issues Encountered

- **Four spurious pytest failures traced to the working directory, not to a regression.** Running `uv run --project backend --extra dev pytest -q` from the *worktree root* reported `4 failed, 239 passed in 25.95s` (`test_connection.py::TestRunDb` x2, `test_stream_integration.py::TestHeartbeat::test_heartbeat_is_emitted`, `test_main.py::test_lifespan_starts_and_stops_source`). The plan's command is `cd backend && uv run --extra dev pytest -q`, and run with the correct CWD - `uv run --directory backend --extra dev pytest -q` - the same tree reported **243 passed in 8.66s**. Root cause identified before any conclusion was drawn: `--project` selects the project but leaves the process CWD at the worktree root, and these are the async and path-sensitive tests. **No backend file was touched** (`git status --porcelain backend/` empty). The lesson for the next agent on this machine: use `uv run --directory backend`, not `--project backend`, when the plan says `cd backend`.

- **The known pre-existing flake did not fire this session.** `tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval` passed in the correct-CWD full-suite run. It remains logged in `deferred-items.md` and is unowned by this phase.

- **The read-only host connection creates WAL sidecars.** `db/finally.db` is in `journal_mode=wal`, and SQLite writes `-shm` and `-wal` beside it even for a `mode=ro` connection when the directory is writable. The tracked database file itself is unmodified (identical sha256), and both sidecars are already gitignored by the rules plan 02-03 relies on, so `git status --porcelain db/` stays empty. No accommodation was added; this is normal SQLite behaviour and the prohibition it might look like it violates is about *the database file*, which was never opened for writing.

## Forward notes for Phase 7

**DOCK-02 shrinks rather than moves.** D-03 landed the `uv sync --frozen --no-dev` half of it in plan `02-01` - it is in the Dockerfile today, executed twice (dependency layer, then project install). Phase 7 owns **only the `npm ci` half**, which genuinely cannot exist yet because there is no `frontend/package.json`. Phase 7 should not re-plan the Python half as if it were outstanding.

**D-08 closed R-05 / T-1-18.** `/docs`, `/redoc` and `/openapi.json` stay enabled. This supersedes the `01-SECURITY.md` row that named Phase 7 as that item's owner - it is decided, not deferred, and Phase 7 should not reopen it.

**And one addition.** Playwright's `globalSetup` should call the platform start script rather than `docker run`, and target `http://localhost:8000` as a browser does; the scripts' internal `127.0.0.1` gate is an implementation detail. `scripts/smoke_check.py` is the layer beneath the E2E suite: Phase 7 should assume same-origin serving, SSE framing, single-worker and persistence are already proven and test user journeys instead of re-proving infrastructure.

## Threat Flags

None. The script adds no network endpoint, no auth path and no schema change. Every mitigation this plan owned was implemented and asserted: **T-2-15** (host connection opened `mode=ro`, zero `INSERT`/`UPDATE`/`DELETE`/`DROP` occurrences, sha256 equality and an empty `git status --porcelain db/` bracketing the run), **T-2-08** (`.env` values compared in memory, never printed on any path including the failure path, which names the key only), **T-2-13** (the SSE read is bounded by `SSE_MAX_LINES = 40` and a 20s socket timeout, and the response closes as soon as the `retry:` frame and one `data:` frame are in hand), and **T-2-05** (the start script's image tag and build timestamp are printed on every invocation and captured into the run record above, so the summary records which image was certified).

## Known Stubs

None. Every check performs a real assertion against a real container; no placeholder, no `TODO`, no skipped path.

## User Setup Required

None. The script is stdlib only and adds no dependency to `backend/pyproject.toml`. It reads the existing root `.env` and needs no key of its own.

## Next Phase Readiness

- **Phase 2's verification is complete and re-runnable.** `uv run scripts/smoke_check.py` is the one command; the phase-level human UAT in the plan's `<verification>` block (one command reaches a working terminal, and the staleness print is legible) is the only outstanding item and is by construction a human judgement.
- **The container namespace is left clean.** The run's final `stop_container` removed `finally-app`; `docker ps -aq --filter "name=^finally-app$"` is empty. `finally-app:latest` remains built.
- **`db/finally.db` is untouched** and byte-identical to the digest plans 02-02 and 02-03 recorded, so it has now held across three plans.
- **Ready for Phase 3 (portfolio API).** The infrastructure is proven, and any new `/api/*` router inherits `check_api_not_shadowed` as a free regression guard the moment it is added to the app.
- **No blockers.**

## Self-Check: PASSED

- `scripts/smoke_check.py` - FOUND
- `.planning/phases/02-walking-skeleton-container/02-04-SUMMARY.md` - FOUND
- Commit `5d7709a` - FOUND in `git log`
- Commit `3e845ed` - FOUND in `git log`
- `backend/` unmodified - CONFIRMED (`git status --porcelain backend/` empty)
- `backend/tests/` unmodified - CONFIRMED (no container assertion entered the pytest suite)
- `db/finally.db` unmodified - CONFIRMED (sha256 unchanged, `git status --porcelain db/` empty)

---
*Phase: 02-walking-skeleton-container*
*Completed: 2026-08-11*
