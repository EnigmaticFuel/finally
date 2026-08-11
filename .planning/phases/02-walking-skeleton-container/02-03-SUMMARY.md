---
phase: 02-walking-skeleton-container
plan: 03
subsystem: infra
tags: [sqlite, wal, bind-mount, concurrency, docker, persistence, diagnostics]

requires:
  - phase: 02-walking-skeleton-container
    provides: "finally-app:latest image, the proven -v <repo>/db:/app/db bind mount, container name namespace"
  - phase: 01-backend-spine
    provides: "backend/tests/db/test_concurrency.py (the load-bearing-assertion doctrine this script is held to), connection.py BUSY_TIMEOUT_MS = 5000"
provides:
  - "scripts/wal_stress.py - stdlib-only PEP 723 script: journal-mode readback, 6-way BEGIN IMMEDIATE contention, lost-update and integrity assertions, pinned key=value result line"
  - ".gitignore rule db/wal_stress.db* covering the scratch database and its sidecars"
  - "The measured answer to D-16: WAL works over this bind mount, three samples, zero errors"
  - "The recorded Git Bash bind-mount recipe that does work on this host (MSYS_NO_PATHCONV=1 plus a pwd -W host side)"
  - "External assertion for DOCK-04, by real write-through and a real container destroy-and-recreate"
affects: [02-04-smoke-check, 03-portfolio-api, 07-docker-e2e]

actuals:
  tokens: 1620
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "PEP 723 inline metadata on standalone scripts, so they run under uv run --script with no project context"
    - "A pinned space-separated key=value result line, because a wave gate greps it and a loose format is satisfiable by accident"
    - "Failure classification before remedy - four named signatures separating mount-layer facts from application-layer contention"

key-files:
  created:
    - "scripts/wal_stress.py"
  modified:
    - ".gitignore"
    - ".planning/REQUIREMENTS.md"

key-decisions:
  - "The scratch database carries a fixed schema (counter.value at id=1) treated as contract, because a second container re-reads it to prove persistence - renaming any of the three breaks the persistence assertion, not just an internal detail"
  - "Plain sqlite3 rather than app.db.connection - the script exists to observe the mount's pragma behaviour directly, and connection.py is the code whose blind spot it covers"
  - "A container-local control run was added (not in the plan) to attribute the elapsed-time divergence from the research reference to the mount rather than to the script"
  - "Git Bash drove Docker successfully here, contrary to plan 02-02's finding, because the host side of every -v was a Windows path from pwd -W rather than a POSIX /c/... path"

patterns-established:
  - "A standalone diagnostic script states in its docstring which layer it measures and which already-tested layer it deliberately does not, so a later reader knows what a passing run does and does not prove"

requirements-completed: [DOCK-04]

coverage:
  - id: D1
    description: "SQLite genuinely engages WAL over the db/ bind mount - PRAGMA journal_mode=WAL executed inside the container reads back wal, not delete"
    requirement: DOCK-04
    verification:
      - kind: integration
        ref: "docker run -v <repo>/db:/app/db finally-app:latest python /stress/wal_stress.py -> journal_mode=wal on 3 of 3 runs"
        status: pass
    human_judgment: false
  - id: D2
    description: "Concurrent writers against a bind-mounted database lose no updates - the final stored value equals start plus increment times committed write count"
    requirement: DOCK-04
    verification:
      - kind: integration
        ref: "6 threads x 40 BEGIN IMMEDIATE increments -> commits=240 expected=240 actual=240 errors=0 on 3 of 3 runs; PRAGMA integrity_check = ok"
        status: pass
    human_judgment: false
  - id: D3
    description: "Data written inside the container appears on the host through the bind mount and survives a full container destroy-and-recreate"
    requirement: DOCK-04
    verification:
      - kind: integration
        ref: "host test -f db/wal_stress.db after the --rm container exited; a second docker run re-read select value from counter where id = 1 -> 240, equal to the parsed actual=240"
        status: pass
    human_judgment: false
  - id: D4
    description: "The stress leaves the tracked db/finally.db untouched"
    requirement: DOCK-04
    verification:
      - kind: integration
        ref: "sha256 c8d433f3...1d1257 identical before and after; git status --porcelain db/finally.db empty; db/ clean after cleanup"
        status: pass
    human_judgment: false

duration: 22min
completed: 2026-08-11
status: complete
---

# Phase 02 Plan 03: WAL Over the Bind Mount Summary

**D-16's flagged risk does not materialise against the real `db/` directory: six writers times forty `BEGIN IMMEDIATE` increments over the OneDrive-synced Windows bind mount produced 240/240 with `journal_mode=wal` and `integrity_check=ok` on three consecutive runs, and a second container re-read the value across a full destroy-and-recreate.**

## Performance

- **Duration:** 22 min
- **Started:** 2026-08-11T13:40:00Z
- **Completed:** 2026-08-11T14:02:00Z
- **Tasks:** 2
- **Files modified:** 1 created, 2 modified

## Accomplishments

- **The one genuinely unconfirmed variable in this phase is now measured against the directory it actually matters for.** Research measured WAL in a throwaway directory; this measured it against `db/`, which is OneDrive-synced, tracked in git, and the bind-mount source the shipped container uses.
- **The journal-mode readback is now written down somewhere.** `PRAGMA journal_mode=WAL` returns the *resulting* mode and returns the *original* mode when the change fails, so a silent downgrade to `delete` raises nothing. `backend/app/db/connection.py:62` executes the pragma and discards the row. This script is currently the only place in the repository that reads it.
- **DOCK-04 is proven in the strong reading, not the weak one.** "Persists across container restarts" is asserted as surviving a full container destroy-and-recreate (`--rm` on the writer, then a fresh `docker run`), and the re-read is compared to a parsed number rather than printed.
- **A regression guard exists where a research session did not.** `scripts/wal_stress.py` is re-runnable, calibrated to the recorded numbers, and classifies a failure into one of four named signatures before any remedy is considered.
- **A Git Bash bind-mount recipe that works on this host is now on record**, which plan 02-02 had concluded was unavailable (see Issues Encountered).

## Measured evidence (requested by the plan's `<output>`)

### The stress, three consecutive runs against `db/`

| Run | journal_mode | commits | expected | actual | errors | integrity_check | elapsed |
|---|---|---|---|---|---|---|---|
| 1 | `wal` | 240 | 240 | 240 | 0 | `ok` | 2.62s |
| 2 (full gate) | `wal` | 240 | 240 | 240 | 0 | `ok` | 3.96s |
| 3 | `wal` | 240 | 240 | 240 | 0 | `ok` | 2.66s |
| Control, container-local `/tmp` (not the mount) | `wal` | 240 | 240 | 240 | 0 | `ok` | 1.76s |

Verbatim result line from the gate run:

```
database=/app/db/wal_stress.db
journal_mode=wal commits=240 expected=240 actual=240 errors=0 integrity_check=ok elapsed=3.96s
```

### Comparison against the research reference

| Dimension | Research reference (throwaway dir) | Measured here (`db/`) | Divergence |
|---|---|---|---|
| Journal mode read back | `wal` | `wal` | none |
| Committed writes | 240 / 240 | 240 / 240 | none |
| Errors | 0 | 0 | none |
| `integrity_check` | `ok` | `ok` | none |
| Elapsed | 1.18s | 2.62s / 3.96s / 2.66s | **2.2x to 3.4x slower** |

**The elapsed divergence is material enough to name, and it was attributed rather than assumed.** The same script, same image, same 240 writes against a container-local path (`--db /tmp/wal_stress.db`, no bind mount involved) took **1.76s**. So roughly 1.5x-2.2x of the gap is the 9p/drvfs bind mount itself and the rest is ordinary run-to-run variance - run 2's 3.96s is an outlier against runs 1 and 3 at 2.62s and 2.66s. No correctness dimension diverged at all. The research figure was also taken in a directory outside OneDrive, so the two elapsed numbers were never measuring quite the same filesystem.

### Write-through and restart persistence (DOCK-04, ROADMAP success criterion 2)

| Assertion | Result |
|---|---|
| Host `db/wal_stress.db` exists after the `--rm` container exited | **Yes**, 8192 bytes |
| `actual=<n>` parsed from the result line | `240` |
| Fresh `docker run`, `select value from counter where id = 1` | `240` |
| Equal across a full container destroy-and-recreate | **Yes** (`ACTUAL=240 REREAD=240`) |
| WAL sidecars left behind after a clean close | none - SQLite checkpointed and removed them |

### The tracked database was untouched (T-2-09)

| Measurement | Value |
|---|---|
| `sha256sum db/finally.db` before the task | `c8d433f3cd87ecca57c160ba07789a978807cc3217cd902e7c1c96460e1d1257` |
| `sha256sum db/finally.db` after every run and cleanup | `c8d433f3cd87ecca57c160ba07789a978807cc3217cd902e7c1c96460e1d1257` |
| `git status --porcelain db/finally.db` | empty |
| `ls db/` after cleanup | `finally.db` |
| `git status --porcelain db/` after cleanup | empty |

This is also byte-identical to the digest plan 02-02 recorded, so the file has not moved across two plans.

### The ignore rule

| Check | Result |
|---|---|
| `git check-ignore -v db/wal_stress.db` | `.gitignore:221:db/wal_stress.db*` |
| `git check-ignore db/wal_stress.db-wal` | exit 0 |
| `git check-ignore db/wal_stress.db-shm` | exit 0 |
| `git check-ignore db/finally.db` | exit **1** - the rule did not widen |
| `git ls-files db/finally.db` | still tracked |

### Script gates

| Gate | Result |
|---|---|
| `head -6` contains `# /// script` | pass |
| `from __future__ import annotations` present | pass |
| Non-printable bytes (emoji check) | `0` |
| Module-level `^[A-Z_]+ = ` constants | `6` (needed >= 4) |
| `uv run --extra dev ruff check ../scripts/wal_stress.py` | `All checks passed!` |
| `uv run --script scripts/wal_stress.py --help` | exit 0 |
| Backend regression gate | `1 failed, 242 passed` - the known pre-existing flake, see Issues Encountered |

## Task Commits

1. **Task 1: `scripts/wal_stress.py` and the `.gitignore` rule** - `c7c81f0` (feat)
2. **Task 2: Run the stress inside the container and prove write-through plus restart persistence** - no code commit. Every assertion passed against the Task 1 artifact, so the script needed no edit; the task's product is the evidence above, which lands in this SUMMARY commit. This matches how plan 02-01 Task 2 and plan 02-02 Task 3 resolved the same shape.

## Files Created/Modified

- `scripts/wal_stress.py` - stdlib-only PEP 723 script. `assert_journal_mode_is_wal()` runs first and fetches the pragma's returned row; `create_counter_table()` builds the fixed `counter(id, value)` schema that Task 2's second container re-reads; `run_writers()` drives six threads times forty read-modify-writes inside `BEGIN IMMEDIATE` at the application's own 5000 ms busy timeout; `assert_no_lost_updates()` checks errors, commit count, final stored value and `PRAGMA integrity_check`; `classify_failure()` names which of the four documented signatures fired; `main()` prints the pinned `key=value` result line.
- `.gitignore` - appended a `db/wal_stress.db*` block below the existing SQLite WAL sidecars block, in the same comment-explaining-why form, stating explicitly that it is an ignore rule for a scratch file and not an untracking of `db/finally.db`.
- `.planning/REQUIREMENTS.md` - DOCK-04 marked complete (checkbox and traceability row).

## Decisions Made

- **The scratch schema is contract.** `counter`, `value` and `id = 1` are re-read by a second container to prove persistence, so renaming any of the three would silently turn the persistence assertion into a test of nothing. Recorded in the function's docstring rather than only in the plan.
- **Plain `sqlite3`, not `app.db.connection`.** The script's purpose is to observe what the mount does to the pragma. Routing through the module whose blind spot it exists to cover would defeat it. It does mirror `connection.py` where the mirroring is load-bearing: `isolation_level=None` and `busy_timeout=5000`, so a timeout here means what a timeout in production would mean.
- **A control run was added beyond the plan.** The plan asked for divergence from the research reference to be noted. Noting a 2.2x-3.4x elapsed gap without attributing it would have been a guess, and the project's rule is root cause before conclusion. One extra container run against `/tmp` cost seconds and turned "slower, unclear why" into "the bind mount costs roughly 1.5x-2.2x on this workload, and correctness is unaffected".
- **Three samples rather than one.** A single elapsed figure would have made run 2's 3.96s look like the measurement instead of an outlier.

## Deviations from Plan

None. The plan executed exactly as written, and no forbidden remedy was needed or proposed - the repository was not moved, the bind-mount source was not changed, no named volume was introduced, `db/finally.db` was not untracked, and `PRAGMA locking_mode=EXCLUSIVE` remains a recorded contingency that was neither needed nor implemented. No file under `backend/app/` was modified.

The one addition beyond the plan's letter is the container-local control run described under Decisions Made, which adds a measurement rather than changing scope.

## Issues Encountered

- **Git Bash drove Docker successfully here, which plan 02-02 concluded it could not.** Both of 02-02's Git Bash modes failed, and its finding was carried forward as "drive Docker from PowerShell for anything involving a bind mount". That finding is narrower than it reads. The root cause of both 02-02 failures was the *host side* of the argument being a POSIX path (`/c/Users/...`), which native `docker.exe` resolves against the Windows namespace and cannot find. With `MSYS_NO_PATHCONV=1` **and** the host side taken from `pwd -W` (`C:/Users/...`), both the container-side `/app/db` and the host-side Windows path survive intact. The mount was asserted rather than trusted, exactly as the prior wave instructed: a probe container ran `ls -la /app/db` and saw the tracked 61440-byte `finally.db`, which is impossible unless the real host directory was mounted. **This does not invalidate 02-02's scripts or its A-05 assumption** - `start_mac.sh` correctly carries no MSYS accommodation, and none of this says anything about a native POSIX host. It is a note for whoever next needs a one-off `docker run` from Git Bash on this machine.

- **The known pre-existing test flake fired again.** `tests/market/test_simulator_source.py::TestSimulatorDataSource::test_custom_update_interval` failed in the full-suite run (`1 failed, 242 passed`) and **passes in isolation** (`1 passed in 0.20s`, re-confirmed this session). `git status --porcelain backend/` is empty - this plan changed no backend code. It is already logged in `deferred-items.md` with its root cause (Windows' approximately 15.6 ms timer granularity against an assertion needing three ticks in a 50 ms window), and CONTEXT.md freezes Phase 1 code for this phase. Not fixed, per the scope boundary rule.

## Diagnostic gap recorded for a later phase

**`backend/app/db/connection.py:62` executes `PRAGMA journal_mode=WAL` and discards the returned row.** The pragma returns the *resulting* journal mode, and returns the *original* mode when the change could not be applied `[sqlite.org/pragma.html#pragma_journal_mode]`. A silent downgrade to `delete` therefore raises no exception, logs nothing, and leaves the application believing WAL is engaged while concurrent writes run unprotected. Today the only thing in the repository that reads that value is `scripts/wal_stress.py`.

This was **deliberately not fixed here.** Phase 1 code is frozen for Phase 2 by CONTEXT.md, and the plan's threat register (T-2-11) records the gap as a later-phase candidate rather than a task. It is also not currently causing a defect on this machine - the mode reads back `wal` on every measured run. The suggested fix when it is picked up: fetch the row in `connect()` and raise if it is not `wal`, which converts an invisible downgrade into a loud startup failure at the cost of one line.

## Threat Flags

None. The script adds no network endpoint, no auth path and no schema change to the application - its only schema is a scratch table in a gitignored file that is deleted after each run. The threat-register mitigations this plan owned were all implemented and asserted: T-2-09 (scratch database only, `.gitignore` rule, sha256 equality and empty `git status` on `db/finally.db`), T-2-11 (the journal-mode readback runs before any contention and fails loudly), T-2-12 (six-way contention driven deliberately at the application's own busy timeout, with the final stored value as the load-bearing assertion and four documented failure signatures), and T-2-14 (scratch database and sidecars deleted, `db/` confirmed clean).

## User Setup Required

None. The script is stdlib only, adds no dependency to `backend/pyproject.toml`, and needs no environment variable or API key.

## Next Phase Readiness

- **Ready for plan `02-04` (smoke check).** The bind-mount round-trip is proven in both directions and `scripts/wal_stress.py` is a working example of the container-invocation shape. The smoke check does not need to re-derive it.
- **Ready for Phase 3 (portfolio API).** The infrastructure question is answered: a `database is locked` under Phase 3's trade logic would be an application-layer fact, not a mount problem, and the fourth failure signature says so explicitly. Phase 3's 30-second snapshot task colliding with a real `execute_trade` is the realistic contention case, and it now runs on a mount that has been measured under harder synthetic load.
- **The container namespace is clean.** Every run used `--rm`; `docker ps -a` lists no `finally-wal-stress`. `finally-app:latest` remains built.
- **`db/` is clean.** Only `finally.db`, byte-identical to its committed state.
- **No blockers.**

## Self-Check: PASSED

- `scripts/wal_stress.py` - FOUND
- `.gitignore` contains `db/wal_stress.db*` - FOUND (line 221)
- `.planning/phases/02-walking-skeleton-container/02-03-SUMMARY.md` - FOUND
- Commit `c7c81f0` - FOUND in `git log`
- `backend/` unmodified - CONFIRMED (`git status --porcelain backend/` empty)
- `db/finally.db` unmodified - CONFIRMED (sha256 unchanged, `git status --porcelain db/` empty)

---
*Phase: 02-walking-skeleton-container*
*Completed: 2026-08-11*
