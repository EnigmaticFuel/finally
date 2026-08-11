---
phase: 02-walking-skeleton-container
plan: 02
subsystem: infra
tags: [docker, shell, bash, powershell, start-stop-scripts, idempotency, readiness-gate, line-endings]

requires:
  - phase: 02-walking-skeleton-container
    provides: "finally-app:latest image, container name finally-app, the proven docker run argument set (-p 127.0.0.1:8000:8000, -v <repo>/db:/app/db, --env-file .env)"
  - phase: 01-backend-spine
    provides: "GET /api/health returning 200 with a four-key payload, which the readiness gate polls"
provides:
  - "scripts/start_mac.sh - build-if-missing or --build, image identity print, fixed run argument set, bounded readiness gate, URL print; idempotent second run"
  - "scripts/stop_mac.sh - stop and remove, nothing-to-stop exits 0, no reference to the database directory"
  - "scripts/start_windows.ps1 - PowerShell 5.1 behavioural mirror of start_mac.sh"
  - "scripts/stop_windows.ps1 - PowerShell 5.1 behavioural mirror of stop_mac.sh"
  - "The container lifecycle contract that plan 02-04's smoke check selects between on sys.platform rather than reimplementing"
  - "The readiness-gate address rule: poll 127.0.0.1, print localhost"
affects: [02-03-wal-stress, 02-04-smoke-check, 07-docker-e2e]

actuals:
  tokens: 3045
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "One lifecycle contract, two platform implementations - same checks in the same order, same printed strings, same exit codes"
    - "Anchored container queries (docker ps -q --filter name=^finally-app$), emptiness as the test, docker ps never piped through grep"
    - "The readiness gate polls the address the container is published on (127.0.0.1) and prints the address the user types (localhost)"
    - "Explicit $LASTEXITCODE check after every docker invocation in PowerShell, because $ErrorActionPreference does not govern native commands"

key-files:
  created:
    - "scripts/start_mac.sh"
    - "scripts/stop_mac.sh"
    - "scripts/start_windows.ps1"
    - "scripts/stop_windows.ps1"
    - ".planning/phases/02-walking-skeleton-container/deferred-items.md"
  modified:
    - ".planning/REQUIREMENTS.md"

key-decisions:
  - "Both readiness gates poll http://127.0.0.1:8000/api/health and print http://localhost:8000. The container publishes on IPv4 loopback only, and localhost resolves to ::1 first on this dual-stack host - measured 2231ms against 145ms, longer than the 2s per-attempt timeout, so the PowerShell gate could never pass"
  - "--build is accepted via $args rather than a param() switch, so the PowerShell pair takes the literal --build the bash pair takes rather than PowerShell's -build"
  - "The PowerShell container-name filter is built by concatenation ('name=^' + $Container + '$') rather than interpolation, so the trailing anchor cannot be read as the start of a variable"
  - "The .sh runtime lifecycle was proven against real Docker but not on a native POSIX host - Git Bash cannot pass host paths to docker.exe in either mode, and Docker Desktop's WSL integration is disabled for the installed Ubuntu distro"

patterns-established:
  - "Script headers carry the why in a comment block, since a shell script has no docstring - matching the tone the Dockerfile established in plan 02-01"
  - "Prohibition gates strip comments before counting (grep -v '^[[:space:]]*#'), so a script's own header explaining a constraint cannot invalidate its own gate"

requirements-completed: [DOCK-05, DOCK-07]

coverage:
  - id: D1
    description: "Start and stop scripts exist for macOS/Linux and Windows PowerShell, and are safe to run repeatedly - start twice leaves .State.StartedAt unchanged with exactly one container, stop twice exits 0 both times"
    requirement: DOCK-05
    verification:
      - kind: integration
        ref: "powershell -NoProfile -File scripts/start_windows.ps1 x2 -> both exit 0, StartedAt 2026-08-11T12:27:04.067833747Z both times, 1 container; stop_windows.ps1 x2 -> exit 0, exit 0"
        status: pass
      - kind: integration
        ref: "bash scripts/start_mac.sh x2 -> exit 0, StartedAt 2026-08-11T11:55:54.351514632Z both times, 1 container; MSYS_NO_PATHCONV=1 bash scripts/stop_mac.sh x2 -> exit 0, exit 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "Both start scripts deliver configuration through --env-file .env alone, with no second mount and no -e flags, and the bind mount resolves to the repository's own database directory"
    requirement: DOCK-07
    verification:
      - kind: integration
        ref: "docker inspect finally-app: 1 mount, Source = <repo>\\db, Destination = /app/db; docker exec finally-app sh -c 'test -s /app/db/finally.db' exit 0"
        status: pass
    human_judgment: false
  - id: D3
    description: "stop never touches the database directory - db/finally.db is byte-identical across a stop and git reports it unmodified"
    requirement: DOCK-05
    verification:
      - kind: integration
        ref: "sha256 c8d433f3cd87ecca57c160ba07789a978807cc3217cd902e7c1c96460e1d1257 before and after stop; git status --porcelain db/finally.db empty; grep gate reports 0 database-directory references on executable lines of both stop scripts"
        status: pass
    human_judgment: false
  - id: D4
    description: "The four scripts are the first real consumers of the Phase 1 .gitattributes line-ending rules, and are stored correctly"
    verification:
      - kind: integration
        ref: "git ls-files --eol scripts/ -> w/lf on both .sh, w/crlf on both .ps1; git ls-files -s -> mode 100755 on both .sh"
        status: pass
    human_judgment: false
  - id: D5
    description: "The .sh pair runs correctly on a native macOS or Linux host"
    verification: []
    human_judgment: true
    rationale: "No native POSIX host is available and Docker Desktop's WSL integration is disabled for the installed Ubuntu distro, so the .sh pair could not be exercised against Docker from a real POSIX shell. See flagged assumption A-05 below - the script logic was exercised against real Docker from Git Bash, but bind-mount uid/gid behaviour on macOS and Linux is carried as an assumption"

duration: 59min
completed: 2026-08-11
status: complete
---

# Phase 02 Plan 02: Start and Stop Scripts Summary

**Four scripts implementing one container lifecycle contract - build-if-missing with a visible image identity, a fixed `docker run` argument set, a bounded `/api/health` readiness gate, then the URL - proven idempotent on both start and stop, with `db/finally.db` byte-identical across a stop.**

## Performance

- **Duration:** 59 min
- **Started:** 2026-08-11T11:36:00Z
- **Completed:** 2026-08-11T12:35:00Z
- **Tasks:** 3
- **Files modified:** 5 created, 1 modified

## Accomplishments

- **One command reaches a working terminal on each platform.** `scripts/start_windows.ps1` goes from no container to a printed `http://localhost:8000` in **5 seconds**, gated on a real 200 from `/api/health` rather than a sleep.
- **Running start twice is a genuine no-op, not a stop-and-recreate.** `.State.StartedAt` is byte-identical across both invocations on both platforms, which is the only externally visible witness that distinguishes the two - and the difference is whether every open SSE connection and every ticker's session open price survives.
- **A stop cannot cost the user their portfolio.** `db/finally.db` hashes identically before and after, `git status` reports it unmodified, and the executable lines of both stop scripts contain zero references to the database directory.
- **A readiness-gate defect that only PowerShell could expose was found and fixed** (see Deviations). The bash gate passed against the same container purely because curl implements Happy Eyeballs; the underlying address mismatch was real on both platforms.
- **The `.gitattributes` rules Phase 1 committed now have their first real consumers**, and SETUP-03's verification - weakened to `git check-attr` because no such file existed - is meaningful for the first time.

## Measured evidence (requested by the plan's `<output>`)

### The start no-op (D-09)

| Platform | Invocation | `.State.StartedAt` |
|---|---|---|
| Windows PowerShell (native) | first `start_windows.ps1` | `2026-08-11T12:27:04.067833747Z` |
| Windows PowerShell (native) | second `start_windows.ps1` | `2026-08-11T12:27:04.067833747Z` |
| Git Bash | first `start_mac.sh` | `2026-08-11T11:55:54.351514632Z` |
| Git Bash | second `start_mac.sh` | `2026-08-11T11:55:54.351514632Z` |

Identical in both pairs. `docker ps -aq --filter "name=^finally-app$" | wc -l` printed `1` after each second run.

### The `db/` prohibition (D-12, ROADMAP success criterion 2)

| Measurement | Value |
|---|---|
| `sha256sum db/finally.db` immediately before stop | `c8d433f3cd87ecca57c160ba07789a978807cc3217cd902e7c1c96460e1d1257` |
| `sha256sum db/finally.db` immediately after stop | `c8d433f3cd87ecca57c160ba07789a978807cc3217cd902e7c1c96460e1d1257` |
| `git status --porcelain db/finally.db` after the full sequence | empty |
| `ls db/` before and after stop | `finally.db` / `finally.db` |
| `grep -v '^[[:space:]]*#' scripts/stop_mac.sh \| grep -c 'db/'` | `0` |
| `grep -v '^[[:space:]]*#' scripts/stop_windows.ps1 \| grep -c 'db/'` | `0` |
| `grep -v '^[[:space:]]*#' scripts/stop_windows.ps1 \| grep -ci 'db\\'` | `0` |

### Stop idempotency (D-12)

| Invocation | Exit code | Output |
|---|---|---|
| `stop_windows.ps1` (container present) | `0` | `Stopped and removed container finally-app.` |
| `stop_windows.ps1` (nothing present) | `0` | `No container named finally-app exists. Nothing to stop.` |
| `stop_mac.sh` (container present) | `0` | `Stopped and removed container finally-app.` |
| `stop_mac.sh` (nothing present) | `0` | `No container named finally-app exists. Nothing to stop.` |

After the first stop, `docker ps -aq --filter "name=^finally-app$"` was empty.

### The resolved bind mount

From the container started by `scripts/start_windows.ps1`:

| Measurement | Value |
|---|---|
| `docker inspect finally-app --format '{{len .Mounts}}'` | `1` |
| `docker inspect finally-app --format '{{(index .Mounts 0).Source}}'` | `C:\Users\ehasi\OneDrive\Documents\AI Coder Course\Project\finally\.claude\worktrees\agent-af99a3702be5456b2\db` |
| `docker inspect finally-app --format '{{(index .Mounts 0).Destination}}'` | `/app/db` |
| Source normalised (case, slash direction, drive form) | `/c/users/ehasi/onedrive/documents/ai coder course/project/finally/.claude/worktrees/agent-af99a3702be5456b2/db` |
| The repository's own `db/` normalised the same way | `/c/users/ehasi/onedrive/documents/ai coder course/project/finally/.claude/worktrees/agent-af99a3702be5456b2/db` |
| `docker exec finally-app sh -c 'test -s /app/db/finally.db'` | exit `0`, `-rwxrwxrwx 1 root root 61440 finally.db` |

Byte-identical after normalisation, and the tracked seeded database is visible inside the container - which is impossible unless the real host directory was mounted.

### Line endings

```
i/lf    w/lf    attr/text eol=lf        scripts/start_mac.sh
i/lf    w/crlf  attr/text eol=crlf      scripts/start_windows.ps1
i/lf    w/lf    attr/text eol=lf        scripts/stop_mac.sh
i/lf    w/crlf  attr/text eol=crlf      scripts/stop_windows.ps1
```

`git ls-files -s scripts/` reports mode `100755` for both `.sh` files and `100644` for both `.ps1` files.

### The image identity print, verbatim (for the Phase 2 UAT to judge legibility)

This is the complete stdout of a successful cold `start_windows.ps1` - three lines, nothing else:

```
Image:      finally-app:latest
Built:      2026-08-11T11:04:12.472781294Z
http://localhost:8000
```

And of a second invocation against a running container:

```
Container finally-app is already running.
http://localhost:8000
```

### Which platform each pair was actually exercised on

**The PowerShell pair was exercised natively on Windows PowerShell 5.1 and is the one platform genuinely proven end to end here. The `.sh` pair was exercised from Git Bash on Windows against real Docker - never on a native macOS or Linux host, because no such host is available.** No reader should infer a macOS or Linux run from this document. See flagged assumption A-05 below.

### Other gates

| Gate | Result |
|---|---|
| `bash -n` on both `.sh` files | exit 0 |
| PowerShell `Parser::ParseFile` on both `.ps1` files | exit 0 (`PARSE_OK`) |
| Non-ASCII bytes in any of the four scripts | `0` (no emojis) |
| `SkipHttpErrorCheck` on executable lines of `start_windows.ps1` | `0` |
| Bare `curl` on executable lines of `start_windows.ps1` | `0` |
| `docker` invocations vs `$LASTEXITCODE` checks in `start_windows.ps1` | 8 vs 8 |
| `docker` invocations vs `$LASTEXITCODE` checks in `stop_windows.ps1` | 3 vs 3 |
| `MSYS_NO_PATHCONV` / `pwd -W` / drive-letter handling inside either `.sh` | absent |
| Backend regression gate | `1 failed, 242 passed` - see Issues Encountered |

## Task Commits

1. **Task 1: `scripts/start_mac.sh` and `scripts/stop_mac.sh`** - `28a01ea` (feat)
2. **Task 2: `scripts/start_windows.ps1` and `scripts/stop_windows.ps1`, plus the readiness-gate fix** - `9b951d1` (feat)
3. **Task 3: Prove the lifecycle contract** - `3f4b05a` (docs). The task's `<action>` says it "edits the four scripts only if an assertion fails". No lifecycle assertion failed, so the scripts needed no edit; the commit carries the deferred item the regression gate surfaced, and the task's real product is the evidence tables above, which land in this SUMMARY commit.

## Files Created/Modified

- `scripts/start_mac.sh` - macOS/Linux start. Resolves the repo root from `${BASH_SOURCE[0]}`, accepts `--build`, detects a running container with an anchored `--filter` and exits 0 on the no-op path, clears a stopped container of the same name, builds when the image is missing or `--build` was passed, prints the image tag and `docker image inspect --format '{{.Created}}'`, runs with the fixed argument set, polls `/api/health` against a 60s deadline, then prints the URL. Carries no Windows or MSYS accommodation.
- `scripts/stop_mac.sh` - macOS/Linux stop. One query, then `docker stop` and `docker rm`. 27 lines, and no path under the database directory anywhere in it.
- `scripts/start_windows.ps1` - the same contract on Windows PowerShell 5.1. `Invoke-WebRequest -UseBasicParsing -TimeoutSec 2` in a required `try`/`catch` for the gate, `$LASTEXITCODE` checked after all eight `docker` calls, `$PSScriptRoot` for the repo root.
- `scripts/stop_windows.ps1` - the same stop contract, three `docker` calls and three checks.
- `.planning/phases/02-walking-skeleton-container/deferred-items.md` - the out-of-scope backend test failure, with its root cause.
- `.planning/REQUIREMENTS.md` - DOCK-05 and DOCK-07 marked complete.

## Decisions Made

- **The readiness gate polls `127.0.0.1` and prints `localhost`.** This is not a Windows workaround. The container is published on `127.0.0.1:8000` deliberately (plan 02-01, threat T-2-04), so `127.0.0.1` is the address that actually exists and is the honest thing for a gate to verify. `localhost` is what the user should be told, because a browser resolves it with the same fallback the gate cannot afford to wait for. Both scripts changed together so the two implementations stay one contract.
- **`--build` is read from `$args`, not a `param()` switch.** A `[switch]$Build` would bind `-build`, giving the two platforms different command-line interfaces for the same flag. The plan's promote decision makes the contract primary, and the flag is part of it.
- **The PowerShell name filter is concatenated, not interpolated.** `'name=^' + $Container + '$'` rather than `"name=^$Container$"`, so the trailing regex anchor can never be parsed as the beginning of a variable reference. The bash side has the same hazard and the same care taken.
- **Task 3 produced no script edit.** Its `<action>` is explicit that it edits the four scripts only if an assertion fails. Every lifecycle assertion passed. Manufacturing an edit to satisfy a one-commit-per-task shape would record a change that did not happen.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `.env` was absent from the parallel-execution worktree**

- **Found during:** Task 1 precondition check
- **Issue:** `.env` is gitignored (`.gitignore:138`), so a fresh worktree checkout does not contain it. Both the precondition and D-07's `--env-file .env` are unsatisfiable without it. Plan `02-01` hit and documented the identical condition.
- **Fix:** Copied the project root's `.env` into the worktree root. The precondition holds at the project level; the worktree simply lacked an untracked local file.
- **Files modified:** none tracked; the copied `.env` is untracked and gitignored
- **Verification:** `git check-ignore -v .env` -> `.gitignore:138:.env`; `git status --short` never shows it
- **Committed in:** nothing - deliberately not committed

---

**2. [Rule 1 - Bug] The readiness gate polled an address the container is not published on**

- **Found during:** Task 2 (first native `start_windows.ps1` run)
- **Issue:** `start_windows.ps1` timed out after the full 60 seconds against a container that was up and healthy. `docker logs` showed uvicorn had completed startup and, decisively, contained **no access-log lines at all** - so no request had ever reached the container. Reproduced twice, deterministically.
- **Root cause, proven by measurement rather than inferred:** the container publishes on `127.0.0.1:8000`, IPv4 loopback only. On this dual-stack Windows host `localhost` resolves to `::1` first, and `Invoke-WebRequest` waits for the IPv6 connect to fail before falling back to IPv4. Measured against the same live container: `http://127.0.0.1:8000/api/health` returned 200 in **145 ms**, `http://localhost:8000/api/health` returned 200 in **2231 ms**. The gate's per-attempt `-TimeoutSec 2` aborts every attempt just short of the fallback, so it could never succeed - for 60 seconds or for 60 minutes. `curl` does not exhibit this because it implements Happy Eyeballs, which is the only reason the bash gate passed against the identical container.
- **Fix:** both start scripts now poll `http://127.0.0.1:8000/api/health` and still print `http://localhost:8000`. `start_mac.sh` was changed as well even though it was passing, because the address mismatch was real on both platforms and leaving the bash gate pointed at `localhost` would have left the two implementations diverging on an internal detail - exactly the drift the plan's promote decision exists to prevent.
- **Files modified:** `scripts/start_mac.sh`, `scripts/start_windows.ps1`
- **Verification:** cold `start_windows.ps1` went from a 60s timeout and exit 1 to exit 0 in **5 seconds**, printing all three expected lines
- **Committed in:** `9b951d1` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** No scope change. The blocking fix restores a precondition that holds in the real repository and is an artifact of worktree isolation. The bug fix was mandatory - without it `start_windows.ps1` could not satisfy DOCK-05 on any run.

## Issues Encountered

- **The `.sh` pair cannot be given a native POSIX runtime proof on this machine, and both Git Bash modes fail for opposite reasons.** This is Task 1's documented contingency, and it fired. The evidence:
  - **With `MSYS_NO_PATHCONV=1`:** the POSIX `$REPO_ROOT` (`/c/Users/...`) reaches `docker.exe` verbatim, and `docker.exe` is a native Windows binary that resolves host paths against the Windows namespace. It failed loudly at the first host-path argument: `docker: --env-file: open /c/Users/.../.env: The system cannot find the path specified.` Exit 1.
  - **Without the prefix:** MSYS rewrites the `-v` argument as a *path list* rather than a single path. The script exited 0 and printed all three expected lines, but `docker inspect` showed `Source = C:\Users\...\db;C` and `Destination = \Program Files\Git\app\db`, and `/app/db` did not exist inside the container. This is `02-RESEARCH.md` Pitfall 10, and it is precisely the silent mis-mount the plan warned would "start, answer `/api/health` and look entirely healthy while the host `db/` directory was never mounted".

  Per the plan's instruction, the mount assertions were **not weakened to make them pass**. A native Linux path was investigated rather than assumed: WSL2 is installed with an Ubuntu distro, but Docker Desktop's WSL integration is disabled for it - the only `docker` on the WSL `PATH` is the Windows `.exe` reached through interop, which would fail on `/mnt/c/...` for the same reason. Enabling that integration is a change to the operator's Docker Desktop settings and is out of this plan's scope.

  What the `.sh` pair *did* get at runtime, against real Docker: the image identity print, the `docker run` invocation, the readiness gate and its ordering ahead of the URL print, the already-running no-op branch with `.State.StartedAt` proven unchanged, and the complete stop path including the idempotent second stop. The branches that were not exercised are the build branch and the port-conflict branch. Recorded as **A-05** below.

- **One backend test fails and it is not a regression from this phase.** `tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval` failed on two consecutive full-suite runs (`1 failed, 242 passed`) and passes in isolation (`1 passed in 0.22s`). This phase changed no backend code: `git status --porcelain backend/` is empty and the diff across all three commits touches only `scripts/` and `.planning/`. Root cause: the test asserts `cache.version > initial_version + 2` after sleeping 50 ms at a 10 ms simulator interval - at least three ticks in a 50 ms window, against Windows' approximately 15.6 ms default timer granularity, which affords roughly 3.2. The margin is thin enough that ordinary event-loop load from the preceding 240 tests pushes it under. Per the scope boundary rule it was logged to `deferred-items.md` and **not fixed** - CONTEXT.md also freezes Phase 1 code for this phase.

- **`docker image inspect finally-app:latest` transiently reported "No such image"** at the very start of the session while `docker images` listed it, and resolved on its own within a minute. It was re-checked three times consecutively afterwards and has been stable since, including inside every script run. Recorded for the next agent's benefit; no code change was made for it, and no accommodation was added to any script.

## Flagged Assumptions

**A-05 (DOCK-05, platform coverage) - restated and widened with evidence.** The `.sh` pair is never run on a native macOS or Linux host by this phase; no such host is available, and Docker Desktop's WSL integration is disabled for the installed Ubuntu distro. It was exercised from Git Bash on Windows against real Docker, which proves the script's own logic - the image identity print, the readiness gate and its ordering, the URL print, the idempotent no-op with `.State.StartedAt` unchanged, and the stop path in full - but not the bind-mount host-path handling, because neither Git Bash mode can pass a host path to `docker.exe` correctly. Observed evidence for the widening, as the plan's contingency requires:

- With the prefix: `docker: --env-file: open /c/Users/.../.env: The system cannot find the path specified.`
- Without the prefix: `docker inspect` Source `C:\Users\ehasi\OneDrive\Documents\AI Coder Course\Project\finally\.claude\worktrees\agent-af99a3702be5456b2\db;C`, Destination `\Program Files\Git\app\db`.

What remains carried as an assumption rather than tested: everything that differs between MSYS and a real POSIX shell, and specifically the bind-mount uid/gid behaviour on macOS and Linux that T-2-02's D-06 rationale turns on. On those platforms the host's real uid/gid apply, which is the reason root is the portable choice. **The runtime lifecycle proof for this phase rests on the PowerShell pair**, which the plan anticipated and which Task 3 delivered natively.

**A-03 (DOCK-05, unclassified)** stands as written in the plan. Task 3 asserted both readings of "safe to run repeatedly" directly - D-09 via the `.State.StartedAt` equality that distinguishes a true no-op from a stop-and-recreate, and D-12 via two exit-0 stops. Any unstated edge beyond those two readings remains unowned.

## Threat Flags

None. The four scripts add no network endpoint, no auth path and no schema change. Every threat-register mitigation this plan owned was implemented and asserted: T-2-07 (the `db/` hash equality and the zero-reference grep gates), T-2-04 (`-p 127.0.0.1:8000:8000` preserved verbatim from plan 02-01), T-2-05 (the unconditional image tag and build timestamp print, under a tag distinct from the stale `finally:latest`), T-2-08 (`.env` is passed to Docker by filename and never opened, read or echoed on any path including the failure paths, which print only a fixed message and `docker logs --tail 40`), and T-2-10 (every container query uses the anchored `name=^finally-app$` form with `-q`).

## User Setup Required

None - no external service configuration required. The scripts read the existing root `.env` and pass it to Docker by name.

## Next Phase Readiness

- **Ready for plan `02-04` (smoke check).** The lifecycle contract is settled and both implementations are committed, so `smoke_check.py` can select on `sys.platform` and shell out rather than reimplementing start or stop. It inherits the readiness gate rather than writing a third one - and it should poll `127.0.0.1`, for the reason measured above.
- **Ready for plan `02-03` (WAL stress).** The bind mount is confirmed as exactly one mount landing on `/app/db`, with the seeded database visible inside the container.
- **Note for Phase 7.** Playwright's `globalSetup` should call the platform-appropriate start script rather than `docker run` directly, and should target `http://localhost:8000` as the browser does. The gate's `127.0.0.1` is an implementation detail of the scripts.
- **Note for whoever runs this on a Mac.** `scripts/start_mac.sh` and `scripts/stop_mac.sh` have never executed on a native POSIX host. The first macOS or Linux run is genuinely the first, and A-05 is the record of that.
- **The container namespace is left clean.** The final `stop_windows.ps1` removed `finally-app`; `docker ps -aq --filter "name=^finally-app$"` is empty. `finally-app:latest` remains built.
- **No blockers.**

## Self-Check: PASSED

- `scripts/start_mac.sh` - FOUND
- `scripts/stop_mac.sh` - FOUND
- `scripts/start_windows.ps1` - FOUND
- `scripts/stop_windows.ps1` - FOUND
- `.planning/phases/02-walking-skeleton-container/deferred-items.md` - FOUND
- Commit `28a01ea` - FOUND in `git log`
- Commit `9b951d1` - FOUND in `git log`
- Commit `3f4b05a` - FOUND in `git log`
- `backend/` unmodified - CONFIRMED (`git status --porcelain backend/` empty)
- `db/finally.db` unmodified - CONFIRMED (`git status --porcelain db/finally.db` empty)

---
*Phase: 02-walking-skeleton-container*
*Completed: 2026-08-11*
