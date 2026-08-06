---
phase: 01
slug: foundation-spine
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-08-06
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

Register origin: **authored at plan time**. All five plans (`01-01` … `01-05`) carry a
`<threat_model>` block, so this audit verifies that registered mitigations exist rather
than constructing a register retroactively. ASVS L1, `block_on: high`.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| browser -> FastAPI `/api/*` | Untrusted request paths, methods and Accept headers | Request paths, headers |
| browser -> FastAPI static `/` | Untrusted request paths reach the static file server | Request paths |
| process env -> `config.py` | `.env` values including API keys enter the process | Credentials |
| request handler -> `run_db` | Untrusted request values reach SQL parameters | Tickers, quantities, message text |
| `app/db/` -> `db/finally.db` | Process writes cross into a bind-mounted, cloud-synced file | Portfolio and chat rows |
| concurrent threads -> `db/finally.db` | Multiple executor threads write the same file | Positions, trades, snapshots |
| local `.env` -> committed `.env.example` | A real credential can cross into git history | Credentials |
| working tree -> git index | Renormalization rewrites stored content across every tracked path | All tracked bytes |
| SQLite process -> `db/` -> OneDrive sync | WAL sidecars written locally are picked up by cloud sync | Uncommitted DB pages |
| generation script -> tracked `db/finally.db` | A destructive write crosses into a committed, shared artifact | Seeded DB contents |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-1-SC | Tampering | `uv add` / `uv sync` package installs | high | mitigate | `01-RESEARCH.md` §Package Legitimacy Audit covers all six packages: zero `[SLOP]`, zero requiring a human checkpoint; the `SUS` verdicts are recorded as artifacts of an unavailable downloads feed | closed |
| T-1-02 | Tampering | concurrent writers against `db/finally.db` | high | mitigate | `connection.py:62-63` sets `journal_mode=WAL` and `busy_timeout` on every open; `writing()` issues `BEGIN IMMEDIATE` (`:85`) taking the write lock up front. `test_concurrency.py::TestLostUpdates` asserts the final value equals the committed write count, not merely absence of errors | closed |
| T-1-04 | Tampering | SQL construction in `seed.py` and `queries.py` | high | mitigate | Interpolated-SQL grep over both modules returns **0**. `executescript()` is used only for the static packaged `schema.sql`, never a caller-supplied string | closed |
| T-1-13 | Tampering | renormalization rewriting the tracked binary database | high | mitigate | `.gitattributes:23` ships `*.db -text` in the same file and same commit as `* text=auto` (`:5`). Verification confirmed commit `54c861c` touched `.gitattributes` only and `db/finally.db` came through byte-identical | closed |
| T-1-15 | Tampering | destructive rewrite of a tracked database | high | accept | Procedural precondition (`git status --porcelain db/finally.db` empty) was performed and recorded in `01-05-SUMMARY.md`, but no gating script was committed. Human-accepted in UAT test 3 — see Accepted Risks R-03 | closed |
| T-1-01 | Spoofing | `app.frontend()` static fallback vs `/api/*` routes | medium | mitigate | `main.py:52-53` registers both routers **before** `app.frontend()` at `:54`, with an absolute `STATIC_DIR`. `test_api_not_shadowed` asserts the Accept matrix over real HTTP so an API path cannot silently return the SPA to a JSON client | closed |
| T-1-05a | Input Validation | ticker symbols reaching SQL | medium | mitigate | 9 `normalize_ticker` call sites in `queries.py`, one per ticker argument, enforcing the shared `^[A-Z]{1,5}$` rule after uppercasing. Covered by `test_invalid_ticker_raises`, `test_lowercase_ticker_is_stored_uppercased` | closed |
| T-1-05b | Information Disclosure | `.env.example` committed to git | medium | mitigate | Full file read: one placeholder string, three empty/false values, zero credentials. `.env` itself confirmed absent from `git ls-files` | closed |
| T-1-06 | Tampering | WAL sidecars committed and independently cloud-synced | medium | mitigate | `.gitignore:213-214` carry `db/*.db-wal` and `db/*.db-shm`, scoped so `db/finally.db` stays tracked (confirmed present in `git ls-files`) | closed |
| T-1-09 | Denial of Service | a lock-contended write stalling the SSE stream | medium | mitigate | All DB work crosses the single `asyncio.to_thread` seam at `connection.py:150`; a busy wait blocks an executor thread, never the event loop. `test_run_db_offloads` asserts the query runs on a different thread than the caller | closed |
| T-1-11 | Repudiation | trade audit log integrity | medium | mitigate | `insert_trade` is the sole writer; grep for `update_trade`/`delete_trade`/`remove_trade`/`edit_trade` returns 0, and a recursive grep for `UPDATE trades` / `DELETE FROM trades` across `backend/app/` returns none. Enforcement is by inspection, not by test — human-accepted in UAT test 3, see R-04 | closed |
| T-1-17 | Repudiation | a real regression waved through as the known flake | medium | mitigate | The gate names one specific node ID, requires isolated re-runs, and treats a reproducible failure as a regression. The run tolerated **zero** failures (243 passed / 0 failed), so the tolerance path was never exercised. Human-accepted in UAT test 4 | closed |
| T-1-03 | Information Disclosure | `GET /api/health` payload and startup logs | low | mitigate | `health.py:33-38` returns exactly four keys; `market_source` carries only the short name. `test_payload_is_exactly_four_keys` and `test_payload_never_names_an_api_key` pin both properties | closed |
| T-1-14 | Denial of Service | `git add --renormalize .` sweeping unrelated work into one commit | low | mitigate | Precondition required a clean working tree; verification confirmed the renormalization commit staged `.gitattributes` only | closed |
| T-1-18 | Information Disclosure | FastAPI interactive docs at `/docs`, `/redoc`, `/openapi.json` | low | accept | **Not in the plan-time register** — raised as a threat flag in `01-01-SUMMARY.md`. `main.py:47` constructs `FastAPI(title="FinAlly", lifespan=lifespan)` with default docs URLs, so the full API schema is served. Localhost single-operator app with no auth and no secrets in the schema. See R-05 | open — below high threshold (non-blocking) |
| T-1-07 | Information Disclosure | path traversal through static serving | low | accept | `app.frontend()` delegates path resolution to Starlette; no hand-rolled path joining introduced. See R-01 | closed |
| T-1-08 | Denial of Service | unbounded concurrent SSE connections | low | accept | Single local operator behind a single uvicorn worker. See R-01 | closed |
| T-1-10 | Information Disclosure | database path leaking through logs or error bodies | low | accept | `ensure_initialized` logs the local operator's own filesystem path at info level. See R-01 | closed |
| T-1-12 | Information Disclosure | chat message content stored in plaintext | low | accept | Single local operator, no auth by design, no multi-tenancy. See R-01 | closed |
| T-1-16 | Information Disclosure | the prior session's data persisting in git history | low | accept | The replaced contents are simulated-portfolio data: no real money, no credentials, no personal data. See R-02 | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above `workflow.security_block_on` count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

**Register note — threat ID collision.** `T-1-05` was assigned twice at plan time: in `01-03-PLAN.md` as *Input Validation — ticker symbols reaching SQL*, and in `01-04-PLAN.md` as *Information Disclosure — `.env.example` committed to git*. They are unrelated threats. Split here as `T-1-05a` and `T-1-05b`; both verified independently. Future phases should not reuse `T-1-05`.

**Reviewed non-issue.** `connection.py:63` builds a PRAGMA with an f-string: `conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")`. SQLite does not accept a bound parameter in a PRAGMA, and the interpolated value is a module-level integer constant with no path from user input. Not a T-1-04 instance.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-01 | T-1-07, T-1-08, T-1-10, T-1-12 | Localhost single-operator simulation with no auth, no real money and no personal data. Registered as `accept` at plan time under ASVS L1 | Planner (plan-time disposition) | 2026-08-05 |
| R-02 | T-1-16 | The rewritten `db/finally.db` contents are simulated-portfolio data only — no credentials, no personal data — so their persistence in git history carries no disclosure risk | Planner (plan-time disposition) | 2026-08-05 |
| R-03 | T-1-15 | The `db/finally.db` rewrite gate was performed as a one-time procedure and recorded in `01-05-SUMMARY.md`, but no committed script enforces it for a future rewrite. Accepted for this milestone rather than adding a guard | Essam (UAT test 3) | 2026-08-06 |
| R-04 | T-1-11 | The `trades` append-only rule holds by inspection (zero mutators, `insert_trade` sole writer) but no test asserts it, so a future query function could violate it undetected. Accepted for this milestone rather than adding a guard | Essam (UAT test 3) | 2026-08-06 |
| R-05 | T-1-18 | FastAPI's interactive docs expose the full API schema at `/docs`, `/redoc` and `/openapi.json`. No secrets appear in the schema, and the app is a localhost single-operator terminal. `01-01-SUMMARY.md` recommends a deliberate decision on disabling them in the container image — carried forward, not resolved here | Auditor (below `block_on: high`) | 2026-08-06 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-08-06 | 20 | 19 | 1 (low, non-blocking) | Claude (`/gsd-secure-phase 01`) |

Short-circuit applied per workflow §3: `threats_open: 0` (no open threat at or above `high`),
`register_authored_at_plan_time: true`, `asvs_level: 1` — L1 grep-depth verification is
sufficient and no auditor subagent was spawned. Every mitigation above was re-derived from
the code, from git, or from live command output rather than read out of a SUMMARY claim.

---

## Carried Forward

| Item | Threat | Owner phase | Note |
|------|--------|-------------|------|
| Decide whether to disable `/docs`, `/redoc`, `/openapi.json` in the container image | T-1-18 | Phase 7 (Docker) | `01-01-SUMMARY.md` raised this for Phase 2; the container image is where the decision actually lands |
| Real external-API integration arrives with OpenRouter chat | — | Phase 6 | The `api-coverage` gate was overridden as a false positive for Phase 1 (see `01-UAT.md` frontmatter). It should be honored in Phase 6 |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed — the one open threat is `low`, below the `high` block threshold
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-08-06
