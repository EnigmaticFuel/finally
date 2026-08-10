# Phase 2: Walking-Skeleton Container - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-10
**Phase:** 2-Walking-Skeleton Container
**Areas discussed:** Frontend build stage, Image layout & config, Start/stop script contract, Proving the skeleton

---

## Area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Frontend build stage | `frontend/` is empty; DOCK-01 wants a Node 24 stage | ✓ |
| Image layout & config | Where backend/ lands, container user, `/docs` (R-05) | ✓ |
| Start/stop script contract | Rebuild policy, already-running behavior, idempotence | ✓ |
| Proving the skeleton | Verification approach and the WAL bind-mount risk | ✓ |

**User's choice:** All four areas.

---

## Frontend build stage

### What the Node stage does

| Option | Description | Selected |
|--------|-------------|----------|
| Real stage, placeholder output | Stage exists and emits static output the Python stage pulls in with `COPY --from`; proves the seam Phase 7 swaps `npm ci && npm run build` into | ✓ |
| Stage exists but no-op | Satisfies DOCK-01's letter at near-zero cost, but Phase 7 meets the cross-stage COPY for the first time | |
| Python-only image now | Simplest Dockerfile, but DOCK-01 goes unmet and would move to Phase 7 | |

**User's choice:** Real stage, placeholder output.
**Notes:** Retiring the cross-stage seam risk early is the stated reason Phase 2 sits before the feature phases at all, so a stage that proves nothing would undercut the phase's rationale.

### Where the placeholder page comes from

| Option | Description | Selected |
|--------|-------------|----------|
| Pass through committed `static/` | One page, one source of truth; local uvicorn and container serve byte-identical content | ✓ |
| Node stage synthesizes its own page | Container-distinct page gives an at-a-glance Docker-vs-local signal, but is a second page to maintain and dies in Phase 7 | |
| Pass through, plus a build stamp | Both benefits, at the cost of a build-time text substitution Phase 7 deletes | |

**User's choice:** Pass through committed `static/`.

### Python dependency install

| Option | Description | Selected |
|--------|-------------|----------|
| `uv sync --frozen --no-dev` now | Lockfile already exists; DOCK-02 then narrows in Phase 7 to the `npm ci` half | ✓ |
| Looser install now, harden in Phase 7 | Keeps DOCK-02 as one unit of work, but Phase 2 never exercises the install path that ships | |

**User's choice:** `uv sync --frozen --no-dev` now.
**Notes:** Consequence worth carrying forward — DOCK-02 shrinks rather than moves, and Phase 7 should be told so it does not re-plan completed work.

### The `backend/static/` contract

| Option | Description | Selected |
|--------|-------------|----------|
| Export only ever happens in-image | Placeholder stays the only committed content; the Next.js export never touches the host tree | ✓ |
| Gitignore the export artifacts | More flexible for Phase 4 frontend dev, but ignore rules must anticipate Next.js output and a stale host export could shadow the placeholder | |
| Export to a separate directory | Cleanest separation, but two static directories and it would change `main.py`'s `STATIC_DIR` — Phase 1 code | |

**User's choice:** Export only ever happens in-image.

---

## Image layout & config

### Where the backend lands in the image

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror the repo: `/app/backend/` | `parents[2]` resolves to `/app` exactly as it resolves to the repo root locally; container and host reason identically | ✓ |
| Flatten to `/app`, rely on `--env-file` | Conventional Docker layout; works today, but only by accident of layering | |
| Flatten, and set `PROJECT_ROOT` from an env var | Removes the accident, but edits Phase 1 code and adds a fifth environment variable | |

**User's choice:** Mirror the repo.
**Notes:** Raised from a live read of `backend/app/config.py:13` — flattening would make `load_dotenv` look for `/.env` and silently find nothing.

### Container user

| Option | Description | Selected |
|--------|-------------|----------|
| Root, documented as deliberate | Guarantees the bind-mount write DOCK-04 depends on across all platforms; same accept rationale `01-SECURITY.md` used for T-1-07/08/10 | ✓ |
| Non-root user | Standard hardening, but a non-root uid commonly cannot write a Windows drvfs bind mount — failing DOCK-04 on the development platform | |
| Non-root, with a fallback | Hardened and diagnosable, but defensive code in a phase whose job is proving the happy path | |

**User's choice:** Root, documented as deliberate.
**Notes:** Must appear in the Phase 2 threat register as an explicit accept with rationale, not as an unexamined default.

### Config delivery

| Option | Description | Selected |
|--------|-------------|----------|
| `--env-file` only | One mechanism, exactly what PLAN.md section 11 documents, no secrets file inside the container | ✓ |
| Bind-mount `.env` read-only at `/app/.env` | Host and container use the identical code path, at the cost of a second mount and secrets inside the container | |
| Both | Nothing breaks, but two mechanisms for one job give a future config bug two places to hide | |

**User's choice:** `--env-file` only.

### `/docs`, `/redoc`, `/openapi.json` (R-05 / T-1-18)

| Option | Description | Selected |
|--------|-------------|----------|
| Leave enabled, close R-05 as accepted | No secrets in the schema, localhost single-operator app, interactive docs are a feature for a teaching project; no code change | ✓ |
| Disable in the container image only | Textbook production posture, but adds a branch in `create_app()` and the shipped app loses an affordance the dev app has | |
| Disable everywhere | Smallest surface, but removes a useful teaching tool to defend a threat already rated low | |

**User's choice:** Leave enabled, close R-05 as accepted.
**Notes:** `01-SECURITY.md` names Phase 7 as R-05's owner; this decision supersedes that. Phase 7 inherits it rather than re-opening it.

---

## Start/stop script contract

### Start when already running

| Option | Description | Selected |
|--------|-------------|----------|
| No-op, print the URL | Same command, same end state; no downtime and no reset of session open prices | ✓ |
| Stop and recreate | Removes staleness doubt, but an accidental second run drops the SSE stream | |
| Recreate only if the image changed | Most helpful in daily use, but needs digest-comparison logic written twice, in bash and PowerShell | |

**User's choice:** No-op, print the URL.

### Rebuild policy

| Option | Description | Selected |
|--------|-------------|----------|
| Build if missing, or on `--build` | Exactly PLAN.md section 11; fast after first run | ✓ |
| Always build | Never stale, but slows the first-run experience students actually judge | |

**User's choice:** Build if missing, or on `--build`.
**Notes:** Mitigation attached — the script must print which image it is using and when it was built, so the forgot-`--build` failure mode is visible rather than silent.

### Browser launch

| Option | Description | Selected |
|--------|-------------|----------|
| Print the URL, do not open | Predictable, works over SSH and CI, never spawns a tab on the no-op second run | ✓ |
| Open automatically | Best first-launch moment, but two platform-specific code paths and needs suppressing on the no-op | |
| Open behind a flag | Both behaviors available, at the cost of another flag to document | |

**User's choice:** Print the URL, do not open.

### Stop semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Report nothing to stop, exit 0 | Stop-twice is a successful no-op; never touches `db/` | ✓ |
| Report nothing to stop, exit non-zero | Matches some CI conventions, but breaks the safe stop-then-start pattern | |

**User's choice:** Report nothing to stop, exit 0.

---

## Proving the skeleton

### Verification approach

| Option | Description | Selected |
|--------|-------------|----------|
| Committed smoke script + UAT | Machine-checkable and re-runnable; becomes the foundation Phase 7's E2E layers on | ✓ |
| Manual UAT only | Zero tooling, but nothing re-checks it when Phase 7 replaces the build stages | |
| pytest that drives docker | One test command, but puts a Docker daemon dependency in a suite that runs in seconds without one | |

**User's choice:** Committed smoke script + UAT.

### WAL over the Windows bind mount

| Option | Description | Selected |
|--------|-------------|----------|
| Deliberately stress it now | The bind mount is the untested variable; cheapest moment to learn the answer | ✓ |
| Wait for it to appear | Keeps Phase 2 focused, but moves discovery into Phase 3 where a lock failure looks like a trade bug | |
| Confirm WAL is active, do not stress it | Catches a silent journal-mode fallback cheaply, but does not prove concurrent writes hold | |

**User's choice:** Deliberately stress it now.
**Notes:** If it fires, the response is diagnosis in place. Relocating the repo, changing the mount source, and untracking `db/finally.db` are all forbidden by PROJECT.md Key Decisions.

### Readiness gate

| Option | Description | Selected |
|--------|-------------|----------|
| Start script polls `/api/health` | Gate belongs to the script, so smoke check, human, and Phase 7 `globalSetup` all inherit it | ✓ |
| Smoke check polls, script does not wait | Thinner scripts, but readiness logic gets rewritten three times and a human still hits a blank page | |
| Docker `HEALTHCHECK` instruction | Idiomatic and visible in `docker ps`, but adds an in-container poller and scripts still need an HTTP same-origin check | |

**User's choice:** Start script polls `/api/health`.

### `docker-compose.yml`

| Option | Description | Selected |
|--------|-------------|----------|
| No compose file | Start scripts already wrap the one `docker run`; a compose file duplicates port, mount and env config | ✓ |
| Ship it as documented | Matches PLAN.md section 4's tree and `docker compose up` is familiar, at the cost of a duplicated config surface | |
| Defer to Phase 7 | Keeps Phase 2 minimal, but leaves a documented file absent with no recorded reason | |

**User's choice:** No compose file.
**Notes:** A deliberate deviation from PLAN.md section 4. Recorded so it is not silently re-added.

---

## Claude's Discretion

The user took the recommended option on every question, so no area was explicitly delegated. Left open to the planner and executor by omission rather than instruction:

- The uvicorn invocation's exact form and how DOCK-06's single-worker guarantee is made visible
- `.dockerignore` scope
- Image and container naming
- Port-8000 conflict detection and reporting
- Base-image variants and pinning for both stages, and layer ordering for cache efficiency
- The precise assertions the smoke script makes beyond those named in the decisions

## Deferred Ideas

- `npm ci` and the real Next.js build stage — Phase 7 (DOCK-02, remaining half)
- Playwright E2E against the container — Phase 7
- Docker `HEALTHCHECK` — considered and rejected here; revisitable in Phase 7
- Non-root container user — rejected on DOCK-04 grounds; first thing to revisit if the app ever leaves localhost
- `docker-compose.yml` — rejected outright, not deferred

No scope creep arose during the discussion; every area stayed inside the container-and-scripts boundary.
