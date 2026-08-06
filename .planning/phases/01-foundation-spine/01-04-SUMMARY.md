---
phase: 01-foundation-spine
plan: 04
subsystem: repo-hygiene
tags: [git, line-endings, environment, gitignore, cleanup]
status: complete

requires:
  - "01-01: backend/app/config.py (FINALLY_DB_PATH), backend/app/db/connection.py (PRAGMA journal_mode=WAL)"
provides:
  - ".gitattributes: repo-wide line-ending policy Phase 2's scripts/*.sh and Dockerfile depend on"
  - ".env.example: committed template naming every variable the backend reads"
  - ".gitignore: WAL sidecar exclusions"
affects:
  - "Phase 2 Dockerfile and start/stop scripts (line endings, FINALLY_DB_PATH spelling)"

tech-stack:
  added: []
  patterns:
    - "git attributes as the enforcement point for line endings, not per-developer core.autocrlf"
    - "binary -text exclusion shipped in the same commit as the text=auto baseline"

key-files:
  created:
    - .gitattributes
    - .env.example
  modified:
    - .gitignore

decisions:
  - "Documented FINALLY_DB_PATH in .env.example even though SETUP-04 names only three variables: Phase 2's Dockerfile and start scripts depend on that exact spelling, and an undocumented name is how Phase 2 gets it wrong."
  - "Placed *.db -text and *.png -text in the same file and commit as * text=auto, so no window exists in which the baseline applies without the binary exclusion."
  - "Scoped the WAL ignore rules to db/*.db-wal and db/*.db-shm rather than a broad db/* rule, so db/finally.db stays tracked per PROJECT.md's accepted risk."
  - "Ran the bytecode cleanup against the main working directory rather than the worktree: the worktree is a tracked-file-only checkout and contained no ignored files to clear."

requirements: [SETUP-03, SETUP-04, SETUP-05]

metrics:
  duration: ~12 min
  completed: 2026-08-06

actuals:
  tokens: 800
  tasks: 2
  commits: 2
---

# Phase 1 Plan 04: Repo Hygiene Summary

Line endings, environment template, WAL sidecar ignores and stale bytecode cleanup — the
ordinary-looking work that determines whether Phase 2's Dockerfile and start scripts run on
the first try.

## What Was Built

### Task 1 — `.gitattributes` and index renormalization (`54c861c`)

Created `.gitattributes` at the repository root. It did not exist before; `core.autocrlf`
was `true` locally, meaning line endings were governed by one developer's git config rather
than by the repository.

Rules landed, all in one commit:

| Pattern | Attribute | Why |
|---------|-----------|-----|
| `*` | `text=auto` | Baseline: normalize text content to LF in the index |
| `*.sh`, `Dockerfile`, `*.dockerfile` | `text eol=lf` | A `.sh` checked out with CRLF fails on macOS and Linux with a bad interpreter error on the shebang line |
| `*.ps1`, `*.bat`, `*.cmd` | `text eol=crlf` | Phase 2's `scripts/start_windows.ps1` and `scripts/stop_windows.ps1` |
| `*.db`, `*.png` | `-text` | No end-of-line conversion on the tracked binary SQLite file |

`git add --renormalize .` was then run from a clean working tree. **It staged zero content
changes** — the index already held LF for every text file, so the renormalization was a
no-op in content terms and the commit contains only the new `.gitattributes`. This is the
best possible outcome for the `costly` reversibility rating the plan assigned the task:
there is no tree-wide content rewrite for a later branch to conflict against.

The tracked database came through untouched. `git ls-files --eol db/finally.db` reports
`i/-text w/-text attr/-text`, and `git diff --stat HEAD -- db/finally.db` is empty.

### Task 2 — `.env.example`, WAL ignores, bytecode cleanup (`fc1be83`)

**`.env.example`** created and committed, documenting four variables verified against
`backend/app/config.py` rather than against the spec:

- `OPENROUTER_API_KEY` — placeholder value; notes that absence degrades `/api/chat` to a
  normal-shaped explanatory response and never fails startup
- `MASSIVE_API_KEY` — empty; notes that empty selects the built-in simulator
- `LLM_MOCK` — `false`; notes the deterministic mock path for E2E tests
- `FINALLY_DB_PATH` — empty; documents both the repo-root `db/finally.db` default and the
  container value `/app/db/finally.db`

Every value is a placeholder or an empty string. `.env` remains untracked
(`git ls-files .env` outputs nothing).

**`.gitignore`** gained `db/*.db-wal` and `db/*.db-shm` under a comment naming them as
SQLite WAL sidecars. `PRAGMA journal_mode=WAL` in `backend/app/db/connection.py` (added by
plan 01-01) now genuinely produces these, and OneDrive syncing them independently of the
database is a corruption vector.

**Bytecode cleanup:** 12 stale `__pycache__` directories removed from under `backend/`.

## Verification

| Check | Result |
|-------|--------|
| `git check-attr eol -- Dockerfile` | `lf` |
| `git check-attr eol -- scripts/start_windows.ps1` | `crlf` |
| `git check-attr eol -- scripts/start_mac.sh` | `lf` |
| `git check-attr text -- db/finally.db` | `unset` |
| `git ls-files --eol db/finally.db` | `i/-text w/-text attr/-text` |
| `git diff --stat HEAD -- db/finally.db` | empty |
| `git ls-files .gitattributes` | `.gitattributes` |
| `git ls-files .env.example` | `.env.example` |
| `git ls-files .env` | empty (still untracked) |
| `git check-ignore -q db/finally.db-wal` | exit 0 (ignored) |
| `git check-ignore -q db/finally.db-shm` | exit 0 (ignored) |
| `git check-ignore -q db/finally.db` | exit 1 (not ignored) |
| `git ls-files db/finally.db` | `db/finally.db` (still tracked) |
| `find backend -type d -name __pycache__` after cleanup | 0 |
| `uv run --extra dev pytest -q` | **203 passed**, 2 warnings, 5.90s |
| `git ls-files backend \| grep -c pycache` | 0 |
| `git status --porcelain` | clean |

The suite came back at 203 passed with zero failures. The pre-existing timing flake in
`test_custom_update_interval` flagged in the wave-2 handoff did not reproduce on this run,
so the result is one better than the expected baseline rather than a regression.

After the test run, 8 `__pycache__` directories regenerated (not 12) and all are ignored.
The four that did not return are `app/llm`, `app/services`, `tests/llm` and `tests/services`
— they hold no `.py` files, so Python has nothing to cache there. As the plan anticipated,
they stay as empty directories until Phase 3 and Phase 6 fill them; git does not track empty
directories, so nothing is needed.

## Deviations from Plan

None affecting the outcome. Two execution notes worth recording:

**1. The bytecode cleanup targeted the main working directory, not the worktree.** This plan
ran as a parallel executor inside a git worktree, which is a checkout of tracked files only.
`__pycache__` is gitignored and therefore never existed in the worktree — `find` returned 0
there before any cleanup. The 12 stale directories RESEARCH.md recorded live in the main
working directory, which is the only place the deletion is meaningful. They were deleted
there, and the suite was re-run there (it is also the only tree carrying `backend/.venv`).
No git operation was involved either way, matching the plan's own framing of the step as a
disk deletion rather than an untracking operation.

**2. `git check-ignore` on a non-existent path reads as "not ignored".** An intermediate
check of `backend/app/market/__pycache__` from inside the worktree exited 1, which looks
like a missing ignore rule. It is not: `__pycache__/` carries a trailing slash and so
matches directories only, and git cannot classify a path that does not exist on disk. The
same check with an explicit trailing slash exits 0. Recorded here because the same false
alarm will recur for anyone verifying ignore rules from a fresh worktree.

## Known Stubs

None.

## Threat Model Coverage

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-1-05 (credential in committed `.env.example`) | mitigate | Covered — placeholders and empty strings only; `git ls-files .env` empty |
| T-1-06 (WAL sidecars committed and cloud-synced) | mitigate | Covered — both sidecars assert ignored, database asserts still tracked |
| T-1-13 (renormalization rewriting the binary database) | mitigate | Covered — `-text` shipped in the same commit as `text=auto`; `ls-files --eol` shows `-text`; `diff --stat` empty |
| T-1-14 (renormalize sweeping unrelated work into one commit) | mitigate | Covered — precondition satisfied, tree was clean, and the renormalize staged nothing at all |

No new threat surface. This plan adds no network endpoint, no auth path and no schema change.

## Notes for Later Phases

- **Phase 2 must set `FINALLY_DB_PATH=/app/db/finally.db` in the Dockerfile.** That exact
  spelling is now documented in `.env.example` and read by `backend/app/config.py`.
- **Phase 2's `scripts/*.sh` and `Dockerfile` will be checked out at LF automatically.** No
  per-file action is needed when those files are added; the attributes already cover them.
- The `flagged_assumptions` entry about `.env.example` drifting incomplete stands: any later
  phase that introduces a new environment variable must add it to the template.

## Self-Check: PASSED

- `.gitattributes` — FOUND, tracked
- `.env.example` — FOUND, tracked
- `.gitignore` — FOUND, modified and committed
- Commit `54c861c` — FOUND
- Commit `fc1be83` — FOUND
