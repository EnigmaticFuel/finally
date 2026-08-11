---
phase: 02-walking-skeleton-container
verified: 2026-08-11T17:05:00Z
status: passed
score: 3/4 must-haves verified
behavior_unverified: 1
overrides_applied: 0
behavior_unverified_items:

  - truth: "A user runs one start script - start_mac.sh or start_windows.ps1 - and reaches a working http://localhost:8000 (ROADMAP SC1)"
    test: "On a native macOS or Linux host with Docker: from a clean state run `bash scripts/start_mac.sh`, then `docker inspect finally-app --format '{{(index .Mounts 0).Source}}'`, then open the printed URL. Then run `bash scripts/stop_mac.sh` twice."
    expected: "Start exits 0 printing the image tag, an RFC3339 build timestamp and http://localhost:8000; the mount Source is the repository's own db/ directory; the page loads; both stops exit 0. On POSIX the host's real uid/gid apply to the bind mount, which is the one behaviour Windows cannot stand in for (D-06 / T-2-02 rationale)."
    why_human: "No native POSIX host exists on this machine and Docker Desktop's WSL integration is disabled for the installed distro. Both Git Bash modes failed at the host-path argument, so the .sh pair's bind-mount branch has never executed successfully anywhere. The Windows half of this criterion IS behaviourally proven; only the POSIX half rests on code review."
human_verification:

  - test: "On a native macOS or Linux host, run scripts/start_mac.sh from a clean state, confirm the bind-mount Source resolves to the repo's db/ directory, open the URL, then run scripts/stop_mac.sh twice."
    expected: "Exit 0 throughout, mount Source correct, page loads, second stop reports nothing to stop."
    why_human: "Platform coverage gap A-05 - no POSIX host available to this phase."

  - test: "Run scripts/start_windows.ps1 from a clean state (no container) and judge the output as a first-time operator would."
    expected: "The three printed lines name the image and its build time, print http://localhost:8000, open no browser, and the page actually renders in a browser you open yourself."
    why_human: "Whether one command reads as reaching a working terminal is a UX judgement; the smoke check asserts endpoints respond, not that the experience lands. Carried as coverage entry D5 (02-01) and D6 (02-04) under workflow.human_verify_mode = end-of-phase."

  - test: "Build the image, then edit a file under backend/app/ and run scripts/start_windows.ps1 again WITHOUT --build. Revert the edit afterwards."
    expected: "The printed build timestamp makes the staleness obvious at a glance."
    why_human: "T-2-05's countermeasure has value only if a human notices it. A print that is technically present but visually buried has failed, and no script can judge that."

  - test: "With the container running, change a value in the root .env, then read it back inside the container with `docker exec finally-app printenv <KEY>`."
    expected: "The container still reports the OLD value - docker run --env-file snapshots the environment at creation time, so a config change requires stop + start."
    why_human: "Declared `verification: backstop` in 02-01-PLAN.md must_haves. No summary records this having been exercised, and a backstop truth abstains absent explicit evidence rather than being assumed from Docker's documented behaviour."
prohibitions_flagged:

  - statement: "MUST NOT read, echo, log or otherwise surface the contents of .env on any code path including failure paths"
    tier: judgment
    llm_judge_verdict: "no violation observed - both start scripts pass .env to Docker by filename only (start_mac.sh:66, start_windows.ps1:100) and never open it; smoke_check.py reads values into memory and every failure message names the key alone (scripts/smoke_check.py:322-337)"
    status: unverified-prohibition
    note: "human review recommended - judgment-tier, non-authoritative verdict"
---

# Phase 2: Walking-Skeleton Container Verification Report

**Phase Goal:** The app runs as a single container on port 8000 with a database that survives restarts
**Verified:** 2026-08-11T17:05:00Z
**Status:** human_needed
**Re-verification:** No - initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | One start script reaches a working `http://localhost:8000` with API and static assets on the same origin and port | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED (Windows half VERIFIED) | Mechanism verified independently: image `finally-app:latest` exists on the daemon, `Created` = 2026-08-11 12:04:12 BST = the `2026-08-11T11:04:12.472781294Z` the summaries claim; `Config.Cmd` = `["uvicorn","--factory","app.main:create_app","--host","0.0.0.0","--port","8000","--workers","1"]`; `WorkingDir=/app/backend`; `ExposedPorts={"8000/tcp":{}}`. `main.py` registers both routers *then* `app.frontend("/")` (line 52-54), so the mount-order hazard is closed in source. Behaviourally proven on Windows only: smoke run `PASS check_health / check_static_page / check_api_not_shadowed / check_sse_stream`. **The `.sh` pair has never executed successfully against a bind mount on any host** (A-05) - see behaviour-unverified item |
| 2 | Stopping and restarting preserves cash balance and watchlist, because the SQLite file lives in the bind-mounted `db/` | ✓ VERIFIED | `check_db_identity` + `check_persistence_across_restart` + `check_stop_leaves_db_untouched` all PASS; identity turns on `users_profile.created_at = 2026-08-06T18:04:55.054196+00:00` matching host and container, which a freshly seeded container-local DB cannot reproduce. Independently re-measured now: `sha256sum db/finally.db` = `c8d433f3cd87ecca57c160ba07789a978807cc3217cd902e7c1c96460e1d1257`, byte-identical to the digest recorded across plans 02-02, 02-03 and 02-04. Both stop scripts read in full - neither contains any path under `db/` |
| 3 | Running start twice, or stop twice, is safe and produces the same result | ✓ VERIFIED | `check_start_is_idempotent` (StartedAt equality + exactly one container) and `check_stop_is_idempotent` PASS. Native PowerShell runs recorded `.State.StartedAt = 2026-08-11T12:27:04.067833747Z` on both invocations. Source confirms the no-op branch: `start_mac.sh:43-48` and `start_windows.ps1:55-64` exit 0 on a running container without stop/rm/restart; `stop_mac.sh:19-23` and `stop_windows.ps1:26-34` exit 0 with a nothing-to-stop message |
| 4 | The container reads `OPENROUTER_API_KEY`, `MASSIVE_API_KEY` and `LLM_MOCK` from the root `.env`, and runs a single uvicorn worker | ✓ VERIFIED | Env: `--env-file` is the sole channel (`start_mac.sh:66`, `start_windows.ps1:100`); no `-e` flags, no second `-v`. `.env.example` (tracked) declares exactly those three keys plus `FINALLY_DB_PATH`; 02-01 measured 3 of 3 keys matching host-vs-container without echoing values, `check_env_delivered` re-proves it, and `/app/.env` is absent from the image. Worker: verified by me directly against the daemon - the image CMD carries `--workers 1`; `docker top` showed exactly one `app.main:create_app` process, and `check_single_worker` asserts both halves |

**Score:** 3/4 truths verified (1 present, behavior-unverified on the POSIX platform half)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `Dockerfile` | Two-stage node:24-trixie-slim -> python:3.12-slim-trixie | ✓ VERIFIED | 61 lines, read in full. Stage `frontend` emits `/build/out`; runtime stage copies uv from `ghcr.io/astral-sh/uv:0.12.3`, `uv sync --frozen --no-dev` twice (dep layer + project install), `WORKDIR /app/backend`, exec-form CMD with `--factory` and `--workers 1`. Not a stub - the built image's metadata matches the file line for line |
| `.dockerignore` | Excludes `backend/.venv` and `.env`, keeps build inputs | ✓ VERIFIED | 55 lines with per-group reasons. `**/.venv` and `.env` excluded; `backend/README.md`, `uv.lock`, `pyproject.toml`, `static/index.html` deliberately kept (documented at the head). Effective - context measured at 706.1 kB against 298 MB unfiltered |
| `scripts/start_mac.sh` | Build-if-missing, identity print, run, readiness gate, URL | ✓ VERIFIED | 85 lines, `bash -n` clean, mode `100755`, `w/lf`. Anchored container filter, gate polls `/api/health` (line 75) *before* the URL print (line 84). No MSYS/Windows accommodation present, as required |
| `scripts/stop_mac.sh` | Idempotent stop and remove; never touches `db/` | ✓ VERIFIED | 27 lines, `bash -n` clean, `100755`, `w/lf`. Zero references to the database directory anywhere in the file |
| `scripts/start_windows.ps1` | PS 5.1 behavioural mirror | ✓ VERIFIED | 128 lines, `w/crlf`. `Invoke-WebRequest -UseBasicParsing` (never bare `curl`), no `-SkipHttpErrorCheck`, `$LASTEXITCODE` checked after all eight docker calls, same strings and same order as the bash script |
| `scripts/stop_windows.ps1` | PS 5.1 behavioural mirror | ✓ VERIFIED | 48 lines, `w/crlf`, three docker calls with three `$LASTEXITCODE` checks, no `db` path |
| `scripts/wal_stress.py` | WAL readback, contention, lost-update assertion | ✓ VERIFIED | 231 lines, parses clean. `assert_journal_mode_is_wal` fetches the pragma row (line 73) rather than discarding it; load-bearing assertion is the final stored value (line 155-164), not "no errors"; `classify_failure` names the four documented signatures; pinned `key=value` result line |
| `scripts/smoke_check.py` | 11 named checks + 2 lifecycle helpers | ✓ VERIFIED | 468 lines (min 120), parses clean. Function-definition gates re-run now: 9 and 5 as specified; third-party imports `0`; `mode=ro` `2`; `INSERT/UPDATE/DELETE/DROP` `0`. Every check performs a real assertion - no stub, no skipped path |
| `.gitignore` | Ignore the scratch DB without widening | ✓ VERIFIED | `git check-ignore -v db/wal_stress.db` -> `.gitignore:221:db/wal_stress.db*`; `git check-ignore db/finally.db` exits 1; `git ls-files db/finally.db` still lists it |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `Dockerfile` | `backend/app/config.py` | `WORKDIR /app/backend` keeps `PROJECT_ROOT = parents[2]` on `/app` | ✓ WIRED | Dockerfile:34; `config.py:13` confirms `parents[2]`; image metadata reports `WorkingDir=/app/backend` |
| `Dockerfile` | `backend/app/main.py` | `--factory app.main:create_app` because there is no module-level `app` | ✓ WIRED | Dockerfile:61; `main.py` exposes only `create_app()` - confirmed by reading it |
| `Dockerfile` | `main.py STATIC_DIR` | `COPY --from=frontend /build/out/ /app/backend/static/` | ✓ WIRED | Dockerfile:43; `main.py:20` resolves `STATIC_DIR` to `<pkg parent>/static` = `/app/backend/static` |
| start scripts | `backend/app/api/health.py` | readiness gate polls `/api/health` until 200 before printing the URL | ✓ WIRED | `start_mac.sh:75-84`, `start_windows.ps1:111-128`. Health returns exactly the four keys the gate and smoke check expect (`health.py`) |
| `start_windows.ps1` | `start_mac.sh` | line-for-line behavioural mirror | ✓ WIRED | Both read in full - same checks in the same order, same printed strings, same exit codes, same `docker run` argument set |
| `smoke_check.py` | the platform start/stop scripts | `sys.platform` selection, shells out, inherits the D-13 gate | ✓ WIRED | `_platform_command` (line 112-116); no wait logic anywhere in the script |
| `smoke_check.py` | `backend/tests/test_main.py` | ports the assertion set rather than re-deriving it | ✓ WIRED | `HEALTH_KEYS` identical to `test_main.py:22`; `retry: 1000` opener matches `test_main.py:77`; the Accept matrix incl. the `text/html` -> 200 row matches `test_main.py:131-143` |
| `smoke_check.py` | `db/finally.db` | read-only sqlite URI for identity and persistence | ✓ WIRED | `mode=ro` on both the host read (line 176) and the in-container read source (line 82) |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Produces Real Data | Status |
|----------|------|--------|--------------------|--------|
| `smoke_check.check_db_identity` | `users_profile.created_at`, `cash_balance`, `watchlist` count | real host `db/finally.db` vs `docker exec` read through `app.config.DB_PATH` | Yes - `2026-08-06T18:04:55.054196+00:00`, a seed timestamp no fresh seed reproduces | ✓ FLOWING |
| `wal_stress.assert_no_lost_updates` | `counter.value` | 6 threads x 40 `BEGIN IMMEDIATE` increments over the real bind mount | Yes - 240/240 on three runs, re-read as 240 from a second container | ✓ FLOWING |
| `check_health` / `check_static_page` | health payload, page bytes | live container over HTTP; page compared byte-for-byte to `backend/static/index.html` | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

Container starts and builds were out of scope for this verification by instruction. Read-only daemon metadata and static gates were run instead.

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| The certified image exists and is the one the summaries name | `docker images --format '{{.Repository}}:{{.Tag}} {{.CreatedAt}}'` | `finally-app:latest 2026-08-11 12:04:12 +0100 BST` = the recorded `11:04:12Z` build | ✓ PASS |
| Single-worker guarantee is in the built image, not just the file | `docker image inspect finally-app:latest --format '{{json .Config.Cmd}}'` | `["uvicorn","--factory","app.main:create_app",...,"--workers","1"]` | ✓ PASS |
| Repo-mirroring layout and DB path baked correctly | `docker image inspect ... WorkingDir/Env` | `WorkingDir=/app/backend`, `FINALLY_DB_PATH=/app/db/finally.db`, `8000/tcp` exposed | ✓ PASS |
| The stale `finally:latest` was left untouched | `docker images` | still listed, dated 2026-08-04 | ✓ PASS |
| Tracked database unchanged | `sha256sum db/finally.db` | `c8d433f3...1d1257` - matches all three plans' recorded digest | ✓ PASS |
| Shell scripts parse | `bash -n` on both `.sh` | exit 0 | ✓ PASS |
| Python scripts parse | `ast.parse` on both `.py` | `PY_PARSE_OK` | ✓ PASS |
| Line endings and exec bits | `git ls-files --eol` / `-s` | `w/lf` + `100755` on both `.sh`; `w/crlf` on both `.ps1` | ✓ PASS |
| Backend left frozen | `git log --name-only <phase commits> -- backend/` | no backend file in any phase-02 commit; `git status --porcelain backend/` empty | ✓ PASS |
| Full smoke run | `uv run scripts/smoke_check.py` | not re-run here (starts containers); recorded green run `11 checks, 11 passed, 0 failed` | ? SKIP - corroborated by image metadata and digest above |

**Note on the first `docker image inspect` call:** it returned `No such image` once, then succeeded on retry - the identical transient plan 02-02 documented under Issues Encountered. Recorded, not treated as a defect.

### Probe Execution

No `scripts/*/tests/probe-*.sh` exist and no plan declares one. The phase's equivalent is `scripts/smoke_check.py`, which by instruction was not re-executed (it starts and destroys containers). Its static contract was re-verified independently: function set, absence of third-party imports, `mode=ro` presence, zero write statements.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DOCK-01 | 02-01, 02-04 | Multi-stage Dockerfile builds frontend on Node and backend on Python 3.12 into one image | ✓ SATISFIED in code, ⚠️ NOT MARKED in REQUIREMENTS.md | Two real stages with a cross-stage copy; image exists; `check_static_page` proves the Node-stage payload reached it. REQUIREMENTS.md:109 still `[ ]`, line 189 still "Pending" |
| DOCK-03 | 02-01, 02-04 | One container on port 8000 serves both API and static frontend | ✓ SATISFIED in code, ⚠️ NOT MARKED | `check_health` + `check_static_page` + `check_api_not_shadowed` + `check_sse_stream`. REQUIREMENTS.md:111 still `[ ]`, line 190 "Pending" |
| DOCK-04 | 02-03, 02-04 | SQLite persists across container restarts via the `db/` bind mount | ✓ SATISFIED | Marked complete (REQUIREMENTS.md:112, 191). Proven in the strong reading - full destroy-and-recreate, value compared not printed |
| DOCK-05 | 02-02, 02-04 | Start/stop scripts for macOS/Linux and Windows, safe to run repeatedly | ✓ SATISFIED (Windows), ⚠️ POSIX unexercised | Marked complete (113, 192). Idempotency proven both directions; A-05 limits the POSIX half |
| DOCK-06 | 02-01, 02-04 | Single uvicorn worker | ✓ SATISFIED in code, ⚠️ NOT MARKED | Verified by me against the live daemon. REQUIREMENTS.md:114 still `[ ]`, line 193 "Pending" |
| DOCK-07 | 02-01, 02-02, 02-04 | Container receives configuration from the root `.env` | ✓ SATISFIED | Marked complete (115, 194). `--env-file` only; `/app/.env` absent from the image |

**Orphaned requirements:** none. Every ID the ROADMAP maps to Phase 2 is claimed by at least one plan.

**DOCK-02** is correctly *not* in scope: REQUIREMENTS.md:253 maps it to Phase 7. Plan 02-04's forward note that its `uv sync --frozen --no-dev` half already landed here (Dockerfile:40, 49) and only `npm ci` remains for Phase 7 is accurate against the code.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| - | - | `TBD` / `FIXME` / `XXX` scan across `Dockerfile`, `.dockerignore` and all six scripts | none found | No unreferenced debt markers - the debt-marker gate passes |
| `Dockerfile` | 5 | the word "placeholder" | ℹ️ Info | Refers to Phase 1's committed `backend/static/index.html` and the deliberate Phase 7 seam, not to unfinished Phase 2 work. Correct as written |
| `scripts/smoke_check.py` | 237 | the word "placeholder" | ℹ️ Info | Same - a docstring describing the page under test |

No empty implementations, no console-log-only handlers, no hardcoded empty returns, no stub props. Every check function in `smoke_check.py` raises on a real comparison.

### Prohibition Review

| Prohibition (plan) | Tier | Verdict | Evidence |
|---|---|---|---|
| MUST NOT edit anything under `backend/app/` (02-01) | judgment | no violation | `git log --name-only` across every phase-02 commit touches no `backend/` path; `git status --porcelain backend/` empty |
| MUST NOT touch `db/` in any stop path (02-02) | judgment | no violation | Both stop scripts read in full - no `rm`, no `find`, no redirect, no path under the database directory. Digest identical across the recorded stops and now |
| MUST NOT surface `.env` contents on any code path (02-02) | judgment | no violation observed - **flagged** | Scripts pass the file by name only; `smoke_check.check_env_delivered` compares in memory and names only the key on failure. Judgment-tier: this verdict is non-authoritative, human review recommended |
| MUST NOT relocate the repo, change the mount source, or untrack `db/finally.db` (02-03) | judgment | no violation | Mount is still `<repo>/db:/app/db`; `git ls-files db/finally.db` lists it; `git check-ignore db/finally.db` exits 1; no named volume anywhere |
| MUST NOT write to / reseed / delete `db/finally.db` (02-03, 02-04) | judgment | no violation | Zero `INSERT|UPDATE|DELETE|DROP` in `smoke_check.py`; host connection `mode=ro`; digest unchanged. `wal_stress.py` targets `/app/db/wal_stress.db` exclusively (line 34) |
| MUST NOT add container assertions to `backend/tests/` (02-04) | judgment | no violation | `backend/tests/` untouched by every phase commit; the pytest suite still runs Docker-free |

### Human Verification Required

#### 1. Native POSIX run of the `.sh` pair (A-05)

**Test:** On a macOS or Linux host with Docker, from a clean state: `bash scripts/start_mac.sh`, then `docker inspect finally-app --format '{{(index .Mounts 0).Source}}'`, open the printed URL, then `bash scripts/stop_mac.sh` twice.
**Expected:** Exit 0 throughout; mount Source is the repo's own `db/`; the page renders; the second stop reports nothing to stop.
**Why human:** No POSIX host is available and Docker Desktop's WSL integration is disabled for the installed distro. Both Git Bash modes failed at the host-path argument, so the `.sh` bind-mount branch has never executed successfully on any host. The uid/gid behaviour that D-06's root-user rationale turns on is POSIX-specific and Windows cannot stand in for it.

#### 2. One command reaches a working terminal (coverage D5 / D6)

**Test:** Run `scripts/start_windows.ps1` from a clean state and judge the output as a first-time operator.
**Expected:** Three lines naming the image and its build time, then `http://localhost:8000`; no browser opens; the page actually renders in a browser you open yourself.
**Why human:** UX judgement the smoke check cannot make - it asserts endpoints respond, not that the experience reads as intended.

#### 3. Is the staleness print legible? (T-2-05)

**Test:** Build the image, edit a file under `backend/app/`, run start again without `--build`, then revert the edit.
**Expected:** The printed build timestamp makes the staleness obvious at a glance.
**Why human:** The countermeasure's entire value is whether a human notices it; a technically-present but visually buried print has failed.

#### 4. `.env` changes do not reach a running container (backstop truth)

**Test:** With the container running, change a value in the root `.env`, then `docker exec finally-app printenv <KEY>`.
**Expected:** The old value - `--env-file` snapshots at creation time, so a config change requires stop + start.
**Why human:** Declared `verification: backstop` in 02-01. No summary records it being exercised, and a backstop truth abstains rather than inheriting a documented platform behaviour as evidence.

### Gaps Summary

**No blockers.** Every artifact this phase promised exists, is substantive, is wired, and carries real data through it. The four ROADMAP success criteria are backed by eleven named checks in a committed, re-runnable script, and the load-bearing claims I could re-derive without starting a container all held: the image on the daemon carries `--workers 1`, `WorkingDir=/app/backend` and `FINALLY_DB_PATH=/app/db/finally.db`; its build timestamp matches the one the summaries say was certified; `db/finally.db` still hashes to the exact digest recorded across three plans; and no phase commit touched `backend/`.

Two things stop this from being a clean `passed`, and neither is a defect in the code:

**1. Criterion 1 is proven on one of its two platforms.** The `.sh` pair is committed, syntactically valid, correctly LF-and-executable, and a faithful mirror of the PowerShell pair - but it has never run on a native POSIX host, and its bind-mount branch failed under both Git Bash modes. The summaries are commendably honest about this (A-05 is restated and *widened* with observed evidence rather than quietly narrowed), which is why this is a coverage limit rather than an overclaim. The Windows half is genuinely proven end to end. A macOS or Linux operator is nonetheless the first person who will ever execute `start_mac.sh` against Docker.

**2. Three human UAT items remain outstanding by construction**, plus one backstop truth that was declared and never exercised. `config.json` sets `workflow.human_verify_mode: "end-of-phase"`, so this is the intended arrival point, not a miss.

**One documentation defect found, not claimed by any summary:** `REQUIREMENTS.md` still shows **DOCK-01, DOCK-03 and DOCK-06 as `[ ]` / "Pending"** (lines 109, 111, 114 and 189, 190, 193) even though plans 02-01 and 02-04 both declare them in `requirements-completed` and the implementation for all three is verified. Plans 02-02 and 02-03 updated the file for DOCK-04, DOCK-05 and DOCK-07; plans 02-01 and 02-04 did not. The code is right and the ledger is stale. Fix is three checkbox flips and three traceability rows - worth doing before `/gsd-ship` or any milestone audit reads that file and reports Phase 2 as two-thirds done.

**Carried forward, correctly out of scope here:**

- `backend/app/db/connection.py:62` discards the `PRAGMA journal_mode=WAL` return row, so a silent downgrade to `delete` would be invisible (T-2-11). Phase 1 code is frozen by `02-CONTEXT.md`; `scripts/wal_stress.py` is currently the only reader of that value. One-line fix when a later phase unfreezes it.
- `test_custom_update_interval` is timing-marginal on Windows (~15.6 ms granularity against an assertion needing three ticks in 50 ms). Pre-existing, logged in `deferred-items.md`, not caused by and not fixable within this phase.

## Acknowledged Gaps

Accepted by the operator on 2026-08-11 during `/gsd-verify-work 02`, after the UAT
session closed 3 passed / 0 issues / 1 skipped.

| Gap | Status | Rationale |
|---|---|---|
| **A-05 — the `.sh` pair has never run on a native POSIX host** (human verification item 1) | Acknowledged, not closed | No macOS or Linux host is available. Re-confirmed at verification time rather than inherited: `wsl -d Ubuntu -- docker version` resolves `docker` only to the Windows binary under `/mnt/c` and refuses to run, so Docker Desktop's WSL integration is still disabled for the installed distro. The Windows half of ROADMAP SC1 is behaviourally proven end to end; the POSIX half rests on code review — the scripts are committed, `bash -n` clean, LF, `100755`, and a line-for-line mirror of the proven PowerShell pair. A macOS or Linux operator will be the first person to execute `start_mac.sh` against Docker. |

**Consequence for phase state.** `phase uat-passed` treats any UAT result outside
`{pass, passed}` as a blocker (`uat-predicate.cjs:43`, `:235`), so the skipped item
leaves the predicate at `passed: false` with blocker `02-UAT.md: test 1 (skipped)`.
Phase 2 is therefore **executed and verified but not transitioned** — ROADMAP.md and
STATE.md still carry it as open by design, not by oversight. This does not gate Phase 3,
which depends only on Phase 1 and touches disjoint files.

**To close it later:** enable Docker Desktop's WSL integration for Ubuntu, clone the repo
into the WSL ext4 home (not `/mnt/c` — `drvfs` fakes file ownership and would not exercise
the uid/gid semantics this test exists for), then re-run `/gsd-verify-work 02`.

---

*Verified: 2026-08-11T17:05:00Z*
*Verifier: Claude (gsd-verifier)*
*Gaps acknowledged: 2026-08-11T18:45:00Z*
