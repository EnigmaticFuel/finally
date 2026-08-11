---
phase: 02
slug: walking-skeleton-container
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-08-11
---

# Phase 02 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

Register origin: **authored at plan time**. All four plans (`02-01` … `02-04`) carry a
`<threat_model>` block, so this audit verifies that registered mitigations exist rather
than constructing a register retroactively. ASVS L1, `block_on: high`.

This phase moves the Phase 1 application into a distributable artifact. That shifts the
interesting surface away from application logic and onto four things the previous phase
did not have: an image that could bake in a credential, a bind mount that could be scoped
too wide, a published port that could reach the LAN, and lifecycle scripts that could
destroy the user's database on a routine stop.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| host build context -> image layers | Repository bytes cross into a distributable artifact; a credential that crosses is permanent | Source, lockfiles, potentially `.env` |
| public registries -> local image | Three third-party base images execute code at build and run time | Base image layers |
| host `db/` -> container `/app/db` | The only host filesystem the container can reach | SQLite database, WAL sidecars |
| host process environment -> container process environment | `.env` values including API keys cross at `docker run` time | `OPENROUTER_API_KEY`, `MASSIVE_API_KEY`, `LLM_MOCK` |
| container `:8000` -> host network interfaces | The published port decides who can reach the unauthenticated terminal | Full API surface, static UI |
| host shell -> Docker daemon | Scripts create, destroy and expose a service | Lifecycle commands |
| concurrent writers -> one SQLite file | Multiple threads contend for the write lock over a non-local filesystem | Portfolio state |
| verification scripts -> tracked repository state | A misdirected write lands in a committed binary artifact | `db/finally.db` |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-2-SC | Tampering | base images `node:24-trixie-slim`, `python:3.12-slim-trixie`, `ghcr.io/astral-sh/uv:0.12.3` | high | mitigate | Zero npm/PyPI packages added this phase (`pyproject.toml`/`uv.lock` untouched). All three base images verified against registry APIs as Docker Official / first-party `astral-sh`. Verified: `Dockerfile` pins every tag, `:latest` count is **0** | closed |
| T-2-01 | Information Disclosure | `.env` reaching an image layer | high | mitigate | `.dockerignore:21` excludes `.env`; no `COPY .` exists — the four `COPY` lines are scoped to `backend/`, `backend/static/`, the uv binary, and the frontend build output. `02-01` asserted `test ! -f /app/.env` inside the built image | closed |
| T-2-06 | Tampering | bind mount scoped wider than `db/`, exposing `.env`, `.git`, source | high | mitigate | Exactly one `-v` per start script, both `db:/app/db` (`start_mac.sh:65`, `start_windows.ps1:100`). `docker inspect` confirmed 1 mount, Destination `/app/db` | closed |
| T-2-07 | Denial of Service | `stop` deleting, truncating or corrupting the bind-mounted database | high | mitigate | Stop scripts issue only `docker stop` / `docker rm`. Verified: **0** `db/` references and **0** destructive verbs (`rm -rf`, `Remove-Item`, `del`, `unlink`) in either stop script. `sha256` of `db/finally.db` equal across a full stop | closed |
| T-2-09 | Tampering | the WAL stress writing into the tracked `db/finally.db` | high | mitigate | `wal_stress.py:34` pins `DB_PATH = "/app/db/wal_stress.db"`. `.gitignore:221` `db/wal_stress.db*`; `git check-ignore` confirms the scratch file is ignored and `db/finally.db` is **not** — the rule did not widen. sha256 unchanged across three runs | closed |
| T-2-11 | Tampering | a silent WAL downgrade to `delete` mode leaving concurrent writes unprotected | high | mitigate | `wal_stress.py:60` `assert_journal_mode_is_wal()` fetches the pragma's returned row and fails loudly before any contention is driven. Read back `wal` on 3 of 3 runs. **Residual gap carried forward** — see Carried Forward | closed |
| T-2-15 | Denial of Service | the smoke check writing to, reseeding or resetting `db/finally.db` | high | mitigate | `smoke_check.py:176` opens `file:...?mode=ro, uri=True`. Verified: **0** occurrences of `INSERT`/`UPDATE`/`DELETE`/`DROP`. Run bracketed by sha256 comparison and `git status --porcelain db/` | closed |
| T-2-02 | Elevation of Privilege | container runs as root with a host bind mount | medium | accept | **D-06, locked.** Localhost single-operator app, no auth, no untrusted input. See Accepted Risks R-06 | closed |
| T-2-04 | Information Disclosure | published port on all interfaces exposes the unauthenticated terminal to the LAN | medium | mitigate | Both start scripts publish `-p 127.0.0.1:8000:8000`, not PLAN.md section 11's `-p 8000:8000`. Confirmed via `.HostConfig.PortBindings` = `map[8000/tcp:[{127.0.0.1 8000}]]` | closed |
| T-2-05 | Tampering | a stale local image silently served as the current build | medium | mitigate | Two layers. Tag `finally-app:latest` is deliberately distinct from the pre-existing non-bootable `finally:latest`, so build-if-missing cannot latch onto it. Plus an unconditional print of the tag and `docker image inspect --format '{{.Created}}'` on every start (`start_mac.sh:60`, `start_windows.ps1:92`). Legibility confirmed by human UAT test 3 | closed |
| T-2-08 | Information Disclosure | failure paths echoing `.env` contents or API keys to terminal or CI logs | medium | mitigate | `.env` crosses to Docker **by filename only** (`--env-file`); verified **0** reads (`cat`/`Get-Content`/`source`/`.`) in either start script. `smoke_check.py` compares values in memory and every failure message names the key alone | closed |
| T-2-12 | Denial of Service | lock contention over the 9p/drvfs bind mount producing `database is locked` under trade load | medium | mitigate | Driven deliberately at 6-way contention at the application's own `BUSY_TIMEOUT_MS = 5000` (`wal_stress.py:39,50,123`). Load-bearing assertion is the final stored value, not absence of exceptions, so a silent lost update cannot pass. 240/240 commits, 0 errors, `integrity_check=ok` on 3 runs | closed |
| T-2-13 | Denial of Service | an unbounded SSE read hanging the smoke check indefinitely | medium | mitigate | Bounded by `SSE_MAX_LINES = 40` (`smoke_check.py:68,288`) and `SSE_TIMEOUT_SECONDS`; response closed as soon as the `retry:` frame and one `data:` frame are seen. `curl -N --max-time` deliberately rejected — it exits 28 on the timeout it was asked to hit | closed |
| T-2-03 | Information Disclosure | `/docs`, `/redoc`, `/openapi.json` served by the image | low | accept | **D-08, locked. Supersedes R-05 / T-1-18.** See Accepted Risks R-07 | closed |
| T-2-10 | Spoofing | an unanchored name filter matching an unrelated container and acting on it | low | mitigate | All four scripts use the anchored form `name=^finally-app$` with `-q`, emptiness of output as the test (`start_mac.sh:43,50`, `stop_mac.sh:19`, `start_windows.ps1:53`, `stop_windows.ps1:24`). Verified **0** instances of `docker ps ... \| grep`. Relevant: this machine already hosts `finally-backend-check`, which a substring filter would match | closed |
| T-2-14 | Denial of Service | scratch files left behind in the bind-mounted directory | low | mitigate | Scratch database and `-wal`/`-shm` sidecars deleted after each run; `git status --porcelain db/` empty; `.gitignore` rule is the second layer for an interrupted run | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-06 | T-2-02 | Container runs as root with a host bind mount. Localhost single-operator app, no auth, no untrusted input — the same rationale `01-SECURITY.md` used for R-01. **Rationale correction recorded so a later phase does not "fix" this on false grounds:** CONTEXT.md justified D-06 by asserting a non-root uid commonly cannot write to a Windows drvfs bind mount; research measured the **opposite** — drvfs presents the mount as `uid=0 gid=0` mode `0777` and `--user 1000:1000` wrote successfully. The reason that IS true: on macOS and Linux the host's real uid/gid apply, so a hardcoded non-root container uid would hit a genuine permission failure there. Root keeps one Dockerfile working on all three platforms | Planner (D-06, locked) | 2026-08-11 |
| R-07 | T-2-03 | `/docs`, `/redoc` and `/openapi.json` stay enabled in the image and locally. No secrets appear in the schema, the app is a localhost single-operator terminal with no auth, and for a capstone teaching project the interactive docs are a feature. **This resolves R-05 / T-1-18**, which `01-SECURITY.md` carried forward naming Phase 7 as owner; that row is superseded and Phase 7 inherits the decision rather than re-opening it | Planner (D-08, locked) | 2026-08-11 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-08-11 | 16 | 16 | 0 | Claude (`/gsd-secure-phase 02`) |

Short-circuit applied per workflow §3: `threats_open: 0`, `register_authored_at_plan_time: true`,
`asvs_level: 1` — L1 grep-depth verification is sufficient and no auditor subagent was spawned.
Every mitigation above was re-derived from the code, from `.gitignore`/`git check-ignore`, or from
recorded command output rather than read out of a SUMMARY claim. Where a count is quoted (`0`
destructive verbs, `0` write statements, `0` `.env` reads, `0` `:latest` tags) it is a measured
count, not an assertion.

---

## Carried Forward

| Item | Threat | Owner phase | Note |
|------|--------|-------------|------|
| `backend/app/db/connection.py:62` executes `PRAGMA journal_mode=WAL` and **discards the returned row** | T-2-11 | A later phase that unfreezes Phase 1 code | The pragma returns the *resulting* mode, and the *original* mode when the change fails, so a silent downgrade to `delete` raises nothing and leaves the app believing WAL is engaged while concurrent writes run unprotected. This phase's registered mitigation (a loud readback in `wal_stress.py`) is implemented, so T-2-11 is closed for Phase 2 — but `wal_stress.py` is currently the **only** reader of that value in the repository. Phase 1 code is frozen by `02-CONTEXT.md`, so this was deliberately not fixed. Fix is one line: fetch the row in `connect()` and raise if it is not `wal` |
| Native POSIX execution of `start_mac.sh` / `stop_mac.sh` | T-2-02, T-2-06, T-2-07 | Whoever first runs the project on macOS or Linux | The `.sh` pair's mitigations are verified by code inspection only — that branch has never executed on a POSIX host (UAT test 1, blocked). The uid/gid behaviour R-06 turns on is POSIX-specific, so a Windows run cannot stand in for it |
| Real external-API integration arrives with OpenRouter chat | — | Phase 6 | `COVERAGE.md` declares no external API integration for Phase 2, which is accurate — this phase only containerizes first-party routes. Phase 6 owns the first genuine coverage matrix |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed — every threat closed, none open at any severity
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-08-11
