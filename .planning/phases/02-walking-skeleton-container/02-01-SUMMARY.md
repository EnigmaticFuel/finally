---
phase: 02-walking-skeleton-container
plan: 01
subsystem: infra
tags: [docker, dockerfile, multi-stage-build, uv, uvicorn, fastapi, node24, python312]

requires:
  - phase: 01-backend-spine
    provides: "create_app() factory, /api/health router, SSE router, app.frontend() mount ordering, config.py PROJECT_ROOT walk, backend/static/index.html placeholder, backend/uv.lock"
provides:
  - ".dockerignore at the repo root - build-context filter, 706 kB context down from 298 MB"
  - "Dockerfile at the repo root - two-stage node:24-trixie-slim -> python:3.12-slim-trixie build"
  - "finally-app:latest image - one container serving /api/* and / on port 8000"
  - "The frontend/runtime stage seam (stage name `frontend`, output path /build/out) that Phase 7 replaces with npm ci && npm run build"
  - "External assertions for DOCK-01, DOCK-03, DOCK-06 and DOCK-07"
affects: [02-02-start-stop-scripts, 02-03-wal-stress, 02-04-smoke-check, 04-frontend-shell, 07-docker-e2e]

actuals:
  tokens: 1137
  tasks: 2
  commits: 2

tech-stack:
  added:
    - "node:24-trixie-slim (build stage base)"
    - "python:3.12-slim-trixie (runtime base)"
    - "ghcr.io/astral-sh/uv:0.12.3 (uv binary, COPY --from)"
  patterns:
    - "Image mirrors the repository at /app/backend/, never flattened to /app"
    - "Two-step uv sync: dependency-only layer, then project install after COPY"
    - "Exec-form CMD with --factory and an explicit --workers 1"

key-files:
  created:
    - ".dockerignore"
    - "Dockerfile"
  modified: []

key-decisions:
  - "Image tagged finally-app:latest, container named finally-app - a distinct namespace from the pre-existing stale finally:latest, which carries the flattened layout and a non-bootable CMD"
  - "Published on 127.0.0.1:8000:8000 rather than 0.0.0.0, closing T-2-04 at zero cost since Playwright runs on the host"
  - "--workers 1 stated explicitly so DOCK-06's guarantee is readable from docker inspect rather than inferred from an omitted flag"
  - ".dockerignore trimmed to a plain `.env` line - the `.env.*` / `!.env.example` pair was written and then removed as speculative, no such files exist"

patterns-established:
  - "Dockerfile comments carry the rejected alternative and its failure mode, matching the tone of config.py and connection.py - a Dockerfile has no docstrings, so this is the one file where inline comments carry the why"
  - "Every container-shape guarantee is asserted from outside the image (docker inspect, docker top, docker exec printenv), never assumed from the build succeeding"

requirements-completed: [DOCK-01, DOCK-03, DOCK-06, DOCK-07]

coverage:
  - id: D1
    description: "A single docker build from the repo root produces one image containing the Node-stage static payload and the Python 3.12 backend"
    requirement: DOCK-01
    verification:
      - kind: integration
        ref: "docker build -t finally-app:latest . (exit 0); docker run --rm --entrypoint sh finally-app:latest -c 'test -d /app/backend/app && test -f /app/backend/static/index.html'"
        status: pass
    human_judgment: false
  - id: D2
    description: "One running container serves GET /api/health as JSON and GET / as HTML on the same origin and port; the static mount does not shadow the API"
    requirement: DOCK-03
    verification:
      - kind: integration
        ref: "curl http://localhost:8000/api/health -> 200 application/json with a status key; curl http://localhost:8000/ -> 200 text/html byte-identical to backend/static/index.html"
        status: pass
    human_judgment: false
  - id: D3
    description: "The container runs exactly one uvicorn worker - not zero, not two"
    requirement: DOCK-06
    verification:
      - kind: integration
        ref: "docker inspect finally-app --format '{{json .Config.Cmd}}' contains --workers 1; docker top finally-app | grep -c 'app.main:create_app' == 1"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every root .env key is delivered into the container by --env-file alone, and /app/.env does not exist in any image layer"
    requirement: DOCK-07
    verification:
      - kind: integration
        ref: "scripted printenv comparison over all 3 .env keys (values never echoed) -> 3 MATCH, 0 fail; docker run --rm --entrypoint sh finally-app:latest -c 'test ! -f /app/.env' exit 0"
        status: pass
    human_judgment: false
  - id: D5
    description: "The tracer slice as a whole - a fresh operator builds the image, starts one container, and sees a working page and a working API"
    verification: []
    human_judgment: true
    rationale: "human_verify_mode is end-of-phase; the tracer's human-verify checkpoint is deferred to the phase verification rather than taken mid-plan, and a human should confirm the page renders in a browser rather than only that curl matched bytes"

duration: 11min
completed: 2026-08-11
status: complete
---

# Phase 02 Plan 01: Walking-Skeleton Container Summary

**Two-stage Dockerfile (node:24-trixie-slim -> python:3.12-slim-trixie, uv sync --frozen --no-dev twice) producing `finally-app:latest`, whose single container answers `/api/health` with JSON and `/` with the byte-identical placeholder page on 127.0.0.1:8000.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-08-11T10:59:00Z
- **Completed:** 2026-08-11T11:10:07Z
- **Tasks:** 2
- **Files modified:** 2 created, 0 modified

## Accomplishments

- `.dockerignore` cuts the build context to **706.1 kB** (measured via the legacy builder's "Sending build context to Docker daemon" line, which reports the full filtered context rather than BuildKit's incremental delta). `**/.venv` and `.env` are excluded with header comments stating why; `backend/README.md`, `backend/uv.lock`, `backend/pyproject.toml` and `backend/static/index.html` are deliberately kept.
- `Dockerfile` lands D-05's repo-mirroring layout: `WORKDIR /app/backend`, `COPY backend/ /app/backend/`, and `PROJECT_ROOT` resolving to `/app` inside the container exactly as it resolves to the repo root on the host.
- The Node stage is real, not a formality: it consumes `backend/static/` and emits `/build/out`, which the runtime stage pulls in with `COPY --from=frontend`. Stage name, output path and destination are the three things Phase 7 must not change when it swaps the body for `npm ci && npm run build`.
- DOCK-03's mount-order hazard survives containerization: `/api/health` returns `application/json`, never the SPA HTML, from the same process on the same port that serves `/`.
- Both halves of DOCK-06 and both halves of DOCK-07 are proven by external assertion, not by inference.

## Measured evidence (requested by the plan's `<output>`)

| Measurement | Value |
|---|---|
| Build context transferred | **706.1 kB** (`Sending build context to Docker daemon  706.1kB`) |
| `docker top finally-app` lines matching `app.main:create_app` | **1** |
| `docker inspect finally-app --format '{{len .Mounts}}'` | **1** |
| Mount destination | **`/app/db`** |
| Mount source | `<worktree-root>/db` |
| `docker inspect finally-app:latest --format '{{json .Config.Cmd}}'` | `["uvicorn","--factory","app.main:create_app","--host","0.0.0.0","--port","8000","--workers","1"]` |
| `docker inspect finally-app --format '{{.HostConfig.PortBindings}}'` | `map[8000/tcp:[{127.0.0.1 8000}]]` |
| `docker exec finally-app printenv FINALLY_DB_PATH` | `/app/db/finally.db` |
| `docker exec finally-app python -c "…PROJECT_ROOT, DB_PATH"` | `/app /app/db/finally.db` |
| `docker exec finally-app python -c "import app.main; print(app.main.__file__)"` | `/app/backend/app/main.py` |
| `/api/health` response | `200`, `application/json`, `{"status":"ok","market_source":"simulator","tickers_cached":10,"newest_price_age_seconds":0.467}` |
| `/` response | `200`, `text/html; charset=utf-8`, `diff` against `backend/static/index.html` clean |
| `.env` keys compared host vs container | **3 of 3 MATCH, 0 fail** (values never echoed) |
| `/app/.env` present in image | **No** (`test ! -f /app/.env` exit 0) |
| Host-built venv leakage (`site-packages/win32`) | **None** (`test ! -d …` exit 0) |
| Pre-existing `finally:latest` | **Still present and untouched** (`docker image ls` lists `finally-app:latest`, `finally:latest`, `finally-backend-check:latest`) |
| Backend regression gate | `uv run --extra dev pytest -q` -> **243 passed**, 2 pre-existing websockets deprecation warnings |
| `git ls-files --eol Dockerfile` | `i/lf w/lf attr/text eol=lf` |
| `git status --porcelain backend/app/` | empty |

## Task Commits

1. **Task 1 (tracer): End-to-end "one container serves the API and the page"** - `a72713f` (feat)
2. **Task 2: Prove the image contract - one worker, one config channel, one mount** - no code commit; every assertion passed against the Task 1 artifact, so the Dockerfile needed no edit. The task's product is the evidence table above, which lands in this SUMMARY commit.

## Files Created/Modified

- `.dockerignore` - build-context filter. Excludes host virtualenvs (the 257 MB `backend/.venv` that would also shadow the container's own venv with Windows wheels), `.env`, VCS and planning trees, the host Playwright harness, the runtime `db/` directory and tooling caches.
- `Dockerfile` - two-stage build. Stage `frontend` (node:24-trixie-slim) emits `/build/out`; stage two (python:3.12-slim-trixie) copies `uv` from `ghcr.io/astral-sh/uv:0.12.3`, installs dependencies from the lockfile in a cache-mounted layer, copies the backend to `/app/backend/`, pulls the frontend output into `/app/backend/static/`, runs the second `uv sync --frozen --no-dev` to install the project itself, and declares an exec-form CMD.

## Decisions Made

- **Task 2 produced no commit of its own.** Its `<action>` says it "writes no new file; it runs the assertions and edits `Dockerfile` only if one fails". None failed, so there was nothing to commit. Creating an empty commit to satisfy the one-commit-per-task shape would have recorded a change that did not happen.
- **The `.env.*` / `!.env.example` pair was removed from `.dockerignore` after being written.** No `.env.local`-style file exists in this project, and the negation re-included a file the image has no use for. Two lines that guard nothing are the defensive programming CLAUDE.md forbids.
- **Build-context size was measured with the legacy builder.** BuildKit transfers the context incrementally, so after the first build its "transferring context" line reports a delta (8.95 kB), not the total. `DOCKER_BUILDKIT=0 docker build` reports the full filtered context in one number, which is what the acceptance criterion is asking about. The legacy builder was used only for this measurement against a throwaway `FROM scratch` Dockerfile in the scratchpad; the real image is built by BuildKit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `.env` was absent from the parallel-execution worktree**

- **Found during:** Task 1 precondition check
- **Issue:** This plan executed in a git worktree at `.claude/worktrees/agent-a9da00027b046bc96`. `.env` is gitignored (`.gitignore:138`), so it does not exist in a fresh worktree checkout. The precondition (`test -f .env`) and D-07's `--env-file .env` are both unsatisfiable without it, and DOCK-07 cannot be asserted at all.
- **Fix:** Copied the project root's `.env` into the worktree root (`cp ../../../.env .env`). The precondition holds at the project level - the operator does have a `.env` at the repo root - and the worktree simply lacked an untracked local file. Confirmed gitignored inside the worktree with `git check-ignore -v .env` before proceeding, so it cannot enter a commit, and it is excluded from the build context by the new `.dockerignore`.
- **Files modified:** none tracked; the copied `.env` is untracked and gitignored
- **Verification:** `git check-ignore -v .env` -> `.gitignore:138:.env`; `git status --short` shows no `.env` entry; `test ! -f /app/.env` inside the image exits 0
- **Committed in:** nothing - deliberately not committed

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** No scope change. The fix restores a precondition that holds in the real repository and is an artifact of worktree isolation, not of the plan.

## Issues Encountered

- **BuildKit's context-transfer number is not the context size after the first build.** Described under Decisions Made. Resolved by measuring once with the legacy builder rather than reporting an incremental delta as if it were a total.
- **The tracer feedback gate was deferred rather than taken.** `type="tracer"` normally stops for a `checkpoint:human-verify` immediately after the tracer commit in an interactive run. `.planning/config.json` sets `workflow.human_verify_mode: "end-of-phase"`, and this executor runs in a disposable worktree that the orchestrator force-removes on return - stopping mid-plan would have discarded Task 2 and this SUMMARY. The gate's substance was honored instead: the tracer's full `<verify>` was re-run end to end and passed before Task 2 began, and the human sign-off is carried forward as coverage entry `D5`.

## User Setup Required

None - no external service configuration required. The container reads the existing root `.env`; `FINALLY_DB_PATH` is set by the Dockerfile, not by `.env`.

## Next Phase Readiness

- **Ready for plan `02-02` (start/stop scripts).** The exact `docker run` line the scripts must wrap is proven: `-p 127.0.0.1:8000:8000`, `-v <repo-root>/db:/app/db`, `--env-file .env`, image `finally-app:latest`, container name `finally-app`. Note for `02-02`: the verification container was **stopped and removed** (`docker rm -f finally-app`) before this plan returned. It was bound to this disposable worktree's `db/` directory, and leaving it alive would have held the `finally-app` name against a bind-mount source that no longer exists. `02-02` starts from a clean container namespace with `finally-app:latest` already built.
- **Ready for plan `02-03` (WAL stress).** The bind mount is confirmed as exactly one mount landing on `/app/db`, and `FINALLY_DB_PATH` resolves inside the container.
- **Ready for plan `02-04` (smoke check).** Every assertion this plan made by hand is a candidate for the script; the `printenv`-comparison loop in particular is written to compare without echoing values.
- **Note for Phase 7.** The two lines it owns in the `frontend` stage are `COPY backend/static/ ./src/` and the `RUN mkdir -p /build/out && cp -r …` beneath it. The stage name `frontend`, the output path `/build/out` and the `COPY --from=frontend … /app/backend/static/` destination must all survive that edit.
- **No blockers.**

## Self-Check: PASSED

- `.dockerignore` - FOUND
- `Dockerfile` - FOUND
- `.planning/phases/02-walking-skeleton-container/02-01-SUMMARY.md` - FOUND
- Commit `a72713f` - FOUND in `git log`
- `backend/app/` unmodified - CONFIRMED (`git status --porcelain backend/app/` empty)

---
*Phase: 02-walking-skeleton-container*
*Completed: 2026-08-11*
