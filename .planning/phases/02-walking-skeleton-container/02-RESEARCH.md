# Phase 2: Walking-Skeleton Container - Research

**Researched:** 2026-08-10
**Domain:** Container packaging (multi-stage Docker + uv), single-origin ASGI serving, SQLite-over-bind-mount durability, cross-platform idempotent shell tooling
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Build stages**

- **D-01:** The Node 24 stage is real, not a formality. It takes the committed `backend/static/index.html` as its input and emits it as build output; the Python stage pulls that output in with `COPY --from`. Nothing meaningful is compiled, but the stage boundary and the cross-stage copy — the exact seam Phase 7 replaces with `npm ci && npm run build` — are exercised now. A no-op stage would satisfy DOCK-01's wording while leaving Phase 7 to meet the seam for the first time, which is the risk this phase exists to retire.

- **D-02:** One page, one source of truth. The container and a local `uvicorn` serve byte-identical content because both resolve to the same committed placeholder. No synthesized container-only page and no build-time stamp — Phase 7 changes only the producer of the static output, never its destination or its content contract.

- **D-03:** The Python stage installs with `uv sync --frozen --no-dev` from the start. `backend/uv.lock` already exists and is committed, so a looser install would be extra work that proves less, and it would mean the image is built one way in Phase 2 and another in Phase 7. **DOCK-02 therefore narrows in Phase 7 to its `npm ci` half** — the only half that genuinely cannot exist yet, because there is no `package.json`. Planner should note this as a scope reduction for Phase 7, not a scope addition here.

- **D-04:** `backend/static/` stays tracked with the placeholder as its only committed content. The Next.js export exists solely inside the Docker build and is written into the image at `COPY --from` time — it never lands in the host working tree. Nothing to gitignore, nothing to clobber, and a local `uvicorn` always serves the placeholder until Phase 4 replaces it deliberately. — **Reversibility:** costly — Phase 4's frontend dev loop and Phase 7's build stage are both written against this contract, and switching to a host-side export later means adding ignore rules and reasoning about a stale export shadowing the tracked file.

**Image layout**

- **D-05:** The image mirrors the repository: backend code lands at `/app/backend/`, so `config.py`'s `PROJECT_ROOT = Path(__file__).resolve().parents[2]` resolves to `/app` exactly as it resolves to the repo root locally. Flattening `backend/` to `/app` — the conventional Docker layout — would make `parents[2]` resolve to `/`, so `load_dotenv` would look for `/.env` and silently find nothing. That currently happens to be harmless because `--env-file` populates the environment before Python starts, but it is harmless by accident, and any later code assuming `PROJECT_ROOT` is the repo root would be right on the host and wrong in the container. The bind mount stays at `/app/db` and `FINALLY_DB_PATH` stays `/app/db/finally.db`, exactly as D-26 documented in `.env.example`. — **Reversibility:** costly — the Dockerfile `COPY` paths, `WORKDIR`, the uvicorn invocation and every path in the start scripts encode this layout.

- **D-06:** The container runs as **root**, and this is a deliberate recorded choice rather than an unexamined default. DOCK-04 turns on writing `finally.db` and its `-wal`/`-shm` sidecars into a bind-mounted host directory; on Windows Docker Desktop that mount is presented through drvfs with host-controlled ownership, and a non-root uid commonly cannot create files there. Hardening the user would risk failing DOCK-04 on the exact platform this project is developed on. The justification is the same one `01-SECURITY.md` already applied to accept T-1-07, T-1-08 and T-1-10: a localhost single-operator app with no auth and no untrusted input. **The planner must carry this into the Phase 2 threat register as an explicit accept with this rationale, not leave it unmentioned.**

- **D-07:** `--env-file .env` on the `docker run` line is the only configuration mechanism, exactly as PLAN.md section 11 shows. No second bind mount for `.env` — one job, one mechanism, and the real secrets file stays out of the container filesystem. Note the consequence, which is now correct rather than accidental: inside the container `load_dotenv` looks at `/app/.env`, finds nothing, and no-ops, because Docker has already injected the variables.

- **D-08:** **R-05 / T-1-18 is resolved: `/docs`, `/redoc` and `/openapi.json` stay enabled**, in the image and locally. No secrets appear in the schema, the app is a localhost single-operator terminal with no auth, and for a capstone teaching project the interactive docs are a feature — a student can open `/docs` and exercise every endpoint by hand. This requires no code change to `main.py` and closes an item `01-SECURITY.md` carried forward. `01-SECURITY.md` lists the owner phase as Phase 7; that is superseded — the decision is made here and Phase 7 inherits it rather than re-opening it.

**Start and stop scripts**

- **D-09:** `start` is idempotent in the strict sense: if a container is already running it reports that, prints `http://localhost:8000`, and exits 0. It does not stop and recreate — an accidental second invocation must not drop the SSE stream or reset every ticker's session open price. This is the reading of success criterion 3 that matches "same command, same end state".

- **D-10:** The image is built when it is missing, or when `--build` is passed — PLAN.md section 11's stated behavior. The known failure mode is real (edit backend code, forget `--build`, wonder why nothing changed), so **the script must print which image it is using and when that image was built**, making staleness visible rather than silent. Always-rebuilding was rejected: it slows the first-run experience, which is the thing a student actually judges.

- **D-11:** The start script prints the URL and does not open a browser. Predictable, identical over SSH and in CI, and it never steals focus or spawns a tab on the no-op second run. No `--open` flag — the script pair already carries `--build`.

- **D-12:** `stop` stops and removes the container, reports "nothing to stop" and exits 0 when none is running, and **never touches `db/`**. Exiting non-zero on an already-stopped container would break the safe `stop` -then- `start` pattern and reads as unsafe against success criterion 3. The `db/` prohibition is what success criterion 2 and DOCK-04 turn on.

- **D-13:** The start script owns the readiness gate: it polls `/api/health` until 200 with a bounded timeout and a clear failure message, and only then prints the URL. Putting the gate in the script means the smoke check, a human, and Phase 7's Playwright `globalSetup` all inherit it instead of each re-implementing a wait. `/api/health` already reports `tickers_cached` and `newest_price_age_seconds`, so it answers "is the stream alive?" in the same request. A Docker `HEALTHCHECK` instruction was rejected — it adds a polling process inside the container and the scripts would still need an HTTP check to prove same-origin serving.

- **D-14:** **No `docker-compose.yml`.** The start scripts already wrap the single `docker run`, so a compose file would be a second expression of the same port, mount and env-file configuration — two sources of truth that drift. This is a deliberate deviation from PLAN.md section 4, which lists the file in its directory tree as an "optional convenience wrapper"; PROJECT.md's constraints ("one container, one command, no orchestration") win. Recorded so the next agent does not re-add it or re-ask.

**Proving the phase**

- **D-15:** Verification is a committed smoke script plus human UAT, not manual UAT alone and not pytest. The script starts the container, asserts `/api/health` and `/api/stream/prices` respond, asserts the static page and the API serve from the same origin and port, then restarts the container and re-reads the cash balance to prove persistence. It is re-runnable by anyone and becomes the foundation Phase 7's E2E suite layers on rather than duplicates. Folding these checks into the backend pytest suite was rejected: it would put a Docker daemon dependency inside a suite that currently runs in seconds without one.

- **D-16:** WAL over the bind mount is **stressed deliberately in this phase**, not left to surface later. Phase 1's concurrency test passed against a host-filesystem database; the bind mount is the untested variable, and the roadmap flags it as unconfirmed on this machine. Driving concurrent writes against the containerized, bind-mounted database here means a `database is locked` failure is diagnosed as an infrastructure fact, rather than discovered under Phase 3's trade logic where it would look like a trade bug. If it fires, PROJECT.md and the roadmap both apply: **diagnose it in place — no plan may propose relocating the repo out of OneDrive, changing the `db/` bind-mount source, or untracking `db/finally.db`.**

### Claude's Discretion

The user took the recommended option on every question, so no area was explicitly delegated. Left to the planner and executor: the uvicorn invocation's exact form and how DOCK-06's single-worker guarantee is made visible; `.dockerignore` scope (`db/`, `.venv`, `node_modules`, `.planning`, `.git`); image and container naming; how a port-8000 conflict is detected and reported; base-image variant and pinning strategy for both stages; layer ordering for cache efficiency; and the precise assertions the smoke script makes beyond those named in D-15.

### Deferred Ideas (OUT OF SCOPE)

- **`npm ci` and the real Next.js build stage** — Phase 7 (DOCK-02, remaining half). D-01 builds the seam it will slot into.
- **Playwright E2E against the container** — Phase 7 (TEST-04..15). D-15's smoke script is the foundation, deliberately not a replacement.
- **A Docker `HEALTHCHECK` instruction** — considered and rejected for this phase (D-13). Could be revisited in Phase 7 when the container becomes production-shaped, but it would not remove the need for an HTTP same-origin check.
- **Non-root container user** — rejected here on DOCK-04 grounds (D-06). If the project ever leaves localhost, this is the first thing to revisit.
- **`docker-compose.yml`** — rejected outright (D-14), not deferred. Recorded so it is not silently re-added to match PLAN.md section 4's tree.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DOCK-01 | A multi-stage Dockerfile builds the frontend on Node and the backend on Python 3.12 into a single image **[CORR: Node 24]** | §Standard Stack pins `node:24-trixie-slim` (verified Active LTS "Krypton", v24.19.0) and `python:3.12-slim-trixie`; §Code Examples gives the two-stage skeleton with the `COPY --from=frontend` seam D-01 requires |
| DOCK-03 | One container on port 8000 serves both the API and the static frontend | §Architecture Patterns "Single-origin serving is already solved in code" — `main.py:52-54` registers both routers before `app.frontend()`; §Validation Architecture gives the same-origin assertion the smoke check makes over one port |
| DOCK-04 | The SQLite database persists across container restarts via the `db/` bind mount | §Pitfall 4 and §WAL Over the Bind Mount — empirically measured on this machine; `FINALLY_DB_PATH=/app/db/finally.db` + `-v <repo>/db:/app/db`; `connection.py:114` already creates the parent directory so no `RUN mkdir` is needed |
| DOCK-05 | Start and stop scripts exist for macOS/Linux and Windows PowerShell, and are safe to run repeatedly | §Code Examples "Idempotent container detection" (anchored `--filter name=^…$`, `-q` emptiness test); §Pitfall 6 (PowerShell 5.1 `curl` alias) and §Pitfall 7 (`$LASTEXITCODE`) |
| DOCK-06 | The container runs a single uvicorn worker, so there is exactly one price universe and fills always agree with streamed prices **[CORR]** | §Architecture Patterns "Making the single-worker guarantee visible" — explicit `--workers 1` in the exec-form CMD plus a two-part assertion via `docker inspect` and `docker top` |
| DOCK-07 | The container receives configuration from the root `.env` file | §Pitfall 3 — `--env-file .env` (D-07) combined with `.dockerignore`-ing `.env`; §Architecture Patterns explains why `load_dotenv(/app/.env)` correctly no-ops under D-05 |
</phase_requirements>

## Summary

This phase has one genuinely unknown variable and a large number of already-solved ones. The unknown was **SQLite WAL over a Windows Docker Desktop bind mount of a OneDrive-synced path** (D-16), and it is no longer unknown: it was measured on this machine during this research session and it works. Everything else — single-origin serving, lazy DB init, the health endpoint, the static placeholder — was landed and proven in Phase 1, so this phase is packaging, not construction.

The measurement matters enough to state plainly. SQLite's own documentation says WAL "does not work over a network filesystem" because readers share a memory-mapped wal-index, and a Docker Desktop bind mount of a Windows host path is exactly the kind of filesystem that clause is warning about — it appears inside the container as `9p`/`drvfs`. Three probes were run against a OneDrive-synced Windows directory bind-mounted into a container: `PRAGMA journal_mode=WAL` returned `wal` and both sidecars appeared; six concurrent `BEGIN IMMEDIATE` writers produced 240/240 committed increments with zero errors in 1.18s; and a **host-native Windows writer racing a container writer against the same file** produced 300/300 with `integrity_check` returning `ok`. D-16's stress test should still be written — it is the regression guard — but the planner can size this phase as "confirm and lock in", not "discover".

Two live traps were found on this machine that the plan must handle, and neither is theoretical. First, a stale `finally:latest` image built 2026-08-04 is already in the local Docker image store, and it uses the **flattened** `/app` layout that D-05 exists to forbid, with `CMD ["uvicorn","app.main:app",...]`. That command cannot work: `backend/app/main.py` exposes only a `create_app()` factory and no module-level `app`, and running it produces `ERROR: Error loading ASGI app. Attribute "app" not found in module "app.main"` — verified by running it. D-10's "build if missing" policy would find that image present, skip the build, and start a container that fails to boot. D-10's "print which image and when it was built" mitigation is precisely the countermeasure, and there is a live instance on disk proving it earns its place. Second, **only Windows PowerShell 5.1 is installed here — `pwsh` is absent** — which rules out `-SkipHttpErrorCheck`, and in 5.1 `curl` is an alias for `Invoke-WebRequest`, so a readiness gate written as `curl http://localhost:8000/api/health` in a `.ps1` silently does something else entirely.

**Primary recommendation:** Build a two-stage Dockerfile (`node:24-trixie-slim` passing `backend/static/` through as build output → `python:3.12-slim-trixie` with uv copied in from `ghcr.io/astral-sh/uv`), keep `WORKDIR /app/backend` so `parents[2]` lands on `/app`, run `CMD ["uvicorn","--factory","app.main:create_app","--host","0.0.0.0","--port","8000","--workers","1"]` in exec form, write the smoke check as a single stdlib-only PEP 723 Python script driven by `uv run` so macOS and Windows execute identical logic, and add a `.dockerignore` before anything else — the build context is 298 MB today and 257 MB of that is `backend/.venv`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Serving `/api/*` routes | API / Backend | — | FastAPI routers registered in `create_app()`; already built in Phase 1 |
| Serving the static page at `/` | API / Backend | — | `app.frontend()` on the same FastAPI app; single origin is the point of DOCK-03, so this deliberately is *not* a separate static tier |
| Producing the static asset bundle | Build stage (Node) | — | D-01: the Node stage is the producer, the Python image is the destination. Phase 7 swaps the producer only |
| Python dependency resolution | Build stage (uv builder) | — | `uv sync --frozen --no-dev` runs at build time; the runtime image never resolves |
| Database persistence | Host filesystem (bind mount) | Database / Storage | The SQLite file's durability is a *host* property; the container tier only opens it |
| Process supervision / restart | Container runtime (Docker) | — | One container, one process, no in-container supervisor — DOCK-06 depends on there being no second layer here |
| Configuration delivery | Container runtime (`--env-file`) | — | D-07: Docker injects env vars before Python starts; `config.py` reads `os.environ` |
| Readiness determination | Host script (start scripts) | API / Backend | D-13 puts the gate in the script and the signal in `/api/health`; rejected a Docker `HEALTHCHECK` so there is exactly one gate |
| Lifecycle idempotency | Host script (start/stop) | — | D-09/D-12: `docker` CLI state queries, not application state |

**Note for the planner:** every row above is either a host-tier or build-tier responsibility except the two Phase 1 already owns. That is the tier-correctness signal for this phase — **any task that proposes editing `backend/app/` is misassigned**, since CONTEXT.md `<domain>` freezes Phase 1 code ("no decision here edits Phase 1 code").

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `node:24-trixie-slim` | Node 24.19.0 (LTS "Krypton") | Frontend build stage base | Node 24 is the Active LTS line; the `krypton-*` / `lts-krypton` tag aliases on Docker Hub confirm it. DOCK-01's `[CORR: Node 24]` names this exact major `[VERIFIED: nodejs.org/dist/index.json → v24.19.0, lts=Krypton, 2026-08-03; hub.docker.com library/node tags 24-trixie-slim + lts-krypton, refreshed 2026-08-05]` |
| `python:3.12-slim-trixie` | Python 3.12 | Runtime image base | `backend/.python-version` pins 3.12 and `pyproject.toml:6` declares `requires-python = ">=3.12"`. `slim-trixie` is the current Debian base for the 3.12 line `[VERIFIED: hub.docker.com library/python tag 3.12-slim-trixie, refreshed 2026-08-07]` |
| `ghcr.io/astral-sh/uv` | 0.12.3 | Provides the `uv` binary to the builder | The uv docs' own recommended install-into-image method is `COPY --from=ghcr.io/astral-sh/uv:<ver> /uv /uvx /bin/` `[CITED: docs/guides/integration/docker.md via Context7 /astral-sh/uv]`. Version 0.12.3 is current `[VERIFIED: pypi.org/pypi/uv/json → 0.12.3]` |
| `uvicorn[standard]` | >=0.32.0 (already locked) | ASGI server | Already a declared dependency `[VERIFIED: backend/pyproject.toml:9 — "uvicorn[standard]>=0.32.0"]`. No change needed |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `curl` | 8.21.0 | Readiness polling in `start_mac.sh` | Present on macOS and every mainstream Linux; also on Windows as `C:\Windows\System32\curl.exe` `[VERIFIED: probed this machine — /c/Windows/System32/curl.exe, curl 8.21.0 (Windows)]` |
| `Invoke-WebRequest` | Windows PowerShell 5.1 | Readiness polling in `start_windows.ps1` | Guaranteed present wherever a `.ps1` can run; use instead of `curl.exe` to avoid depending on a Win10-1803+ floor. **Never write bare `curl` in a `.ps1`** — see Pitfall 6 |
| Python stdlib (`urllib`, `sqlite3`, `subprocess`) | 3.12 | Smoke check script (D-15) | Zero dependencies, identical behavior on both platforms, and it solves the bounded SSE read cleanly |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /uvx /bin/` into `python:3.12-slim-trixie` | `FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim` as the builder | Both are documented uv patterns. The `COPY --from` form keeps the *runtime* base as the plain official Python image, which is one fewer vendor in the final image's provenance. Note `ghcr.io/astral-sh/uv:python3.12-trixie-slim` was **not** found in the GHCR tag list this session — only `python3.12-bookworm-slim`, `debian-slim` and `latest` were confirmed present `[VERIFIED: ghcr.io/v2/astral-sh/uv/tags/list]`. Prefer the `COPY --from` form |
| `uv sync --frozen` | `uv sync --locked` | `--locked` *asserts* the lockfile is up to date and errors if `pyproject.toml` has drifted; `--frozen` uses the lock as source of truth and never checks `[CITED: uv-cli/src/lib.rs via Context7 — "Instead of checking if the lockfile is up-to-date, uses the versions in the lockfile as the source of truth"]`. PROJECT.md and D-03 mandate `--frozen`; honor that, but see Pitfall 8 for the drift it cannot catch |
| Multi-stage with a discarded builder | Single-stage build | The uv docs' multi-stage variant copies only `/app/.venv` forward and uses `--no-editable`. **Do not adopt it here** — D-05 requires the source tree at `/app/backend/`, and dropping the source would also drop `backend/static/`. Keep the source in the final image |
| `node:24-slim` | `node:24-trixie-slim` | `24-slim` is an alias whose Debian base moves over time. Pin `24-trixie-slim` so a base-OS bump is a visible diff, not a silent one |
| A separate SSE-reading tool in the smoke check | Bounded read via Python `urllib` | `curl -N --max-time` returns exit 28 on the timeout it is *supposed* to hit, so bash must special-case a "successful failure". Python reads N lines then closes — no exit-code contortion |

**Installation:**

This phase installs **no new packages**. It adds a `Dockerfile`, a `.dockerignore`, four scripts and one smoke-check script. `backend/pyproject.toml` and `backend/uv.lock` are unchanged — which is exactly what makes D-03's `uv sync --frozen --no-dev` available immediately `[VERIFIED: backend/pyproject.toml read this session; dependency list unchanged from Phase 1]`.

Image pulls required (not package installs):

```bash
docker pull node:24-trixie-slim
docker pull python:3.12-slim-trixie
docker pull ghcr.io/astral-sh/uv:0.12.3
```

## Package Legitimacy Audit

**Not applicable in the registry sense — this phase adds zero npm, PyPI or crates dependencies.** No line of `backend/pyproject.toml` or `backend/uv.lock` changes, and there is no `package.json` yet (that arrives in Phase 4). The `package-legitimacy` gate has no packages to check.

The equivalent supply-chain surface here is **container base images**, audited below:

| Image | Registry | Provenance | Verdict | Disposition |
|-------|----------|-----------|---------|-------------|
| `node:24-trixie-slim` | Docker Hub Official Images (`library/node`) | Maintained by `nodejs/docker-node`, part of the Docker Official Images program | OK | Approved `[VERIFIED: hub.docker.com/v2/repositories/library/node/tags]` |
| `python:3.12-slim-trixie` | Docker Hub Official Images (`library/python`) | Docker Official Images program | OK | Approved `[VERIFIED: hub.docker.com/v2/repositories/library/python/tags]` |
| `ghcr.io/astral-sh/uv:0.12.3` | GHCR, `astral-sh` org | First-party publisher of uv; the install method is the one uv's own docs prescribe | OK | Approved `[VERIFIED: ghcr.io/v2/astral-sh/uv/tags/list returned 1000 tags incl. latest; CITED: uv docs/guides/integration/docker.md]` |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

**Pinning recommendation:** pin all three to an explicit tag (not `latest`). Digest-pinning (`@sha256:…`) is the stronger form and uv's docs show it, but it makes the Phase 7 base-image bump a two-step edit; tag-pinning is the right level for a teaching project and is what the rest of the repo's reproducibility story (`--frozen`, `npm ci`) is calibrated to. `[ASSUMED — a judgement call, not a documented standard]`

## Architecture Patterns

### System Architecture Diagram

```text
  HOST (Windows 11 / macOS)                     │  CONTAINER  (one process, one port)
                                                 │
  ┌──────────────┐                               │
  │ start script │──1. build if missing ────────►│  docker build
  │  (.sh/.ps1)  │      + print image & build ts │      │
  │              │                               │      ▼
  │              │──2. docker run ──────────────►│  ┌────────────────────────────────┐
  │              │      -p 8000:8000             │  │ uvicorn --factory              │
  │              │      -v ./db:/app/db          │  │   app.main:create_app          │
  │              │      --env-file .env          │  │   --host 0.0.0.0 --port 8000   │
  │              │                               │  │   --workers 1   (PID 1)        │
  │              │──3. poll /api/health ─────────┼─►│         │                      │
  │              │      until 200, bounded       │  │         ▼                      │
  │              │                               │  │   create_app()                 │
  │              │──4. print URL (no browser)    │  │    ├─ PriceCache  ◄── simulator│
  └──────────────┘                               │  │    ├─ /api/health              │
                                                 │  │    ├─ /api/stream/prices  (SSE)│
  ┌──────────────┐                               │  │    └─ app.frontend("/")  ◄─ LAST
  │ smoke check  │──/api/health ────────────────►│  │            │                   │
  │ (uv run .py) │──/api/stream/prices (bounded)►│  └────────────┼───────────────────┘
  │              │──/  (static, same port) ─────►│               │
  │              │──restart, re-read cash ──────►│               ▼
  └──────────────┘                               │   /app/backend/static/index.html
                                                 │
  ./db/finally.db ◄══════ bind mount (9p/drvfs) ═╪══► /app/db/finally.db
    + .db-wal, .db-shm                           │        (FINALLY_DB_PATH)
                                                 │
  ─────────────── BUILD TIME (multi-stage) ──────┴──────────────────────────────
  Stage "frontend"  node:24-trixie-slim   ──►  emits static output
        │                                        (Phase 7: npm ci && npm run build)
        └── COPY --from=frontend ──────────────►  Stage "runtime" python:3.12-slim-trixie
  Stage builder     uv sync --frozen --no-dev ─►      /app/backend/.venv
```

Trace the primary use case by following the arrows: the user runs one script (1), which builds if needed, starts the container (2), waits for readiness (3), and prints the URL (4). A browser request for `/` lands on the FastAPI app and falls through both `/api/*` routers to `app.frontend()`; a request for `/api/health` is caught by the first router and never reaches the static handler. The database crosses the container boundary once, at the bind mount.

### Recommended Project Structure

```
finally/
├── Dockerfile               # multi-stage: node:24 -> python:3.12
├── .dockerignore            # NEW - see Pitfall 1; the build context is 298 MB without it
├── scripts/
│   ├── start_mac.sh         # LF (enforced by .gitattributes:10)
│   ├── stop_mac.sh          # LF
│   ├── start_windows.ps1    # CRLF (enforced by .gitattributes:17)
│   ├── stop_windows.ps1     # CRLF
│   └── smoke_check.py       # D-15; PEP 723 header, stdlib only, `uv run`
├── backend/                 # unchanged - image mirrors this at /app/backend/
└── db/                      # unchanged - bind-mount target, never touched by stop
```

`.gitattributes` already carries the rules these files are the first real consumers of: `[VERIFIED: .gitattributes:10-12,17 — "*.sh text eol=lf", "Dockerfile text eol=lf", "*.dockerfile text eol=lf", "*.ps1 text eol=crlf"]`.

### Pattern 1: The image mirrors the repo (D-05), so `WORKDIR` is `/app/backend`

**What:** Copy `backend/` to `/app/backend/` rather than flattening it to `/app`. Set `WORKDIR /app/backend` so `uv sync` finds `pyproject.toml`.

**Why it is load-bearing:** `config.py` walks up three levels from the module file. Verbatim: `[VERIFIED: backend/app/config.py:13 — "PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]"]`. From `/app/backend/app/config.py`, `parents[2]` is `/app`. From a flattened `/app/app/config.py`, it is `/`. The comment on lines 10-12 of that file states the intent explicitly: *"the backend runs from backend/ locally and from /app in the container, and both must find the one .env that sits beside the repo root."*

**Consequence for the venv:** `uv sync` creates `.venv` inside the project directory, so it lands at `/app/backend/.venv`. Put `/app/backend/.venv/bin` on `PATH` rather than invoking `uv run` at runtime — the uv docs' own images do exactly this `[CITED: astral-sh/uv-docker-example multistage.Dockerfile — 'ENV PATH="/app/.venv/bin:$PATH"']`.

**When to use:** always, in this phase. `UV_PROJECT_ENVIRONMENT` could relocate the venv elsewhere `[CITED: uv-static/src/env_vars.rs, added in uv 0.4.4]`, but there is no reason to here and it adds a variable the start scripts would have to know about.

### Pattern 2: Single-origin serving is already solved — do not re-solve it

**What:** DOCK-03's hard part was landed in Phase 1. `create_app()` registers both API routers and *then* the static fallback:

```
app.include_router(create_health_router(cache, source))
app.include_router(create_stream_router(cache))
app.frontend("/", directory=STATIC_DIR, fallback="index.html")
```

`[VERIFIED: backend/app/main.py:52-54 — exact lines quoted above]`

**Why it matters here:** the mount-order hazard PLAN.md §11 calls "the most common way this architecture breaks" is closed in code and covered by `test_api_not_shadowed`. This phase's job is to prove it survives *containerization* — same origin, same port — not to re-implement ordering. `STATIC_DIR` is absolute and package-relative: `[VERIFIED: backend/app/main.py:20 — "STATIC_DIR = Path(__file__).resolve().parent.parent / \"static\""]`, which resolves to `/app/backend/static` under D-05. That is the destination `COPY --from=frontend` must write to.

**Anti-pattern:** adding a second static mount, a reverse proxy, or `--root-path`. All three add an origin.

### Pattern 3: The `--factory` invocation is mandatory, not stylistic

**What:** `backend/app/main.py` defines `create_app()` and **no module-level `app`** `[VERIFIED: backend/app/main.py:23 — "def create_app() -> FastAPI:"; grep for "^app\s*=" in main.py returns nothing]`.

Measured this session:

- `uv run uvicorn app.main:app` → `ERROR:    Error loading ASGI app. Attribute "app" not found in module "app.main".`
- `uv run uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8098` → serves; `GET /api/health` returns `200` with `{"status":"ok","market_source":"simulator","tickers_cached":10,"newest_price_age_seconds":0.162}`

`[VERIFIED: both commands executed this session against the live tree]`

**Why it is worth a pattern entry:** the stale `finally:latest` image on this machine carries `CMD ["uvicorn" "app.main:app" "--host" "0.0.0.0" "--port" "8000"]` `[VERIFIED: docker history finally:latest --no-trunc]`. Somebody has already made this mistake here.

### Pattern 4: Making the single-worker guarantee visible (DOCK-06)

**What:** DOCK-06 requires that "exactly one price universe" be a *guarantee*, not an accident. uvicorn's `run()` signature defaults `workers: int | None = None` `[CITED: kludex/uvicorn main.py run() signature via Context7]`, so omitting the flag already yields one process — but omission is invisible, and an invisible guarantee is what the `[CORR]` on DOCK-06 is reacting to.

**Recommendation — two assertions, neither of which touches `backend/app/`:**

1. **Static (intent):** put `--workers 1` explicitly in the exec-form CMD, then assert it from outside:
   `docker inspect --format '{{json .Config.Cmd}}' <container>` must contain `--workers 1`.
2. **Runtime (fact):** `docker top <container>` lists container processes using the *host's* `ps`, so it needs no `procps` inside the slim image. Assert exactly one process whose command line contains `app.main:create_app`.

`--workers 1` was verified to run and serve correctly (`/api/health` → 200) this session. `[VERIFIED: uv run uvicorn --factory app.main:create_app --port 8097 --workers 1, executed this session]`

**Why the runtime half is needed:** the static half proves the *image* is configured right; only `docker top` proves the *running* container has one app process. A future `--reload` or a supervisor added by a base-image change would break the second assertion and not the first. Note `--reload` and `--workers` are mutually exclusive `[CITED: uvicorn docs/deployment/index.md]`, which is a useful guardrail in itself.

### Pattern 5: Exec-form CMD so `docker stop` is fast and clean

**What:** use the JSON-array (exec) form of `CMD`, never the shell form.

**Why:** the shell form runs the process under `/bin/sh -c`, so the executable is not PID 1 and never receives `SIGTERM` from `docker stop`. Docker's own reference demonstrates the cost: `10.19s` to stop (SIGKILL after the grace period) versus `0.20s` with proper signal delivery `[CITED: moby/buildkit dockerfile reference via Context7 /docker/docs — "your executable will not receive a SIGTERM from docker stop <container>"]`. uvicorn's shutdown is signal-driven — `handle_exit` sets `should_exit`, the main loop observes it per tick and then runs `shutdown()` `[CITED: kludex/uvicorn server.py via Context7]` — which is also what runs the lifespan teardown that calls `source.stop()` `[VERIFIED: backend/app/main.py:45 — "await source.stop()"]`.

**Consequence for D-12:** a `stop` script that appears to hang for ten seconds will read as broken. Exec form is what makes `stop` feel idempotent and instant.

### Pattern 6: One smoke check, two platforms (D-15)

**What:** write `scripts/smoke_check.py` as a stdlib-only script with a PEP 723 inline-metadata header, invoked as `uv run scripts/smoke_check.py`.

**Why this over a `.sh` + `.ps1` pair:** D-15 requires the script be re-runnable by anyone and become Phase 7's foundation. Two scripts means two implementations of the same assertions drifting apart — the same argument D-14 used to reject `docker-compose.yml`. A single Python script also solves the bounded SSE read (read N lines, close) without the `curl --max-time` exit-code contortion, and gives real JSON parsing for the `/api/health` and cash-balance assertions.

**Verified to work standalone:** a script with `# /// script` / `# requires-python = ">=3.12"` / `# dependencies = []` / `# ///` ran via both `uv run s.py` and `uv run --script s.py` from a directory with no `pyproject.toml`, on Python 3.12.13 `[VERIFIED: executed this session in a scratch directory]`.

This also honors the project rule "`uv run` / `uv add` only — never bare `python` or `pip`".

### Anti-Patterns to Avoid

- **Flattening `backend/` to `/app`.** The conventional Docker layout, and forbidden by D-05. It silently repoints `PROJECT_ROOT` at `/`. There is a stale image on this machine that does exactly this.
- **`uvicorn app.main:app`.** There is no module-level `app`. Verified to fail.
- **Shell-form `CMD`.** Breaks SIGTERM delivery, makes `docker stop` take 10s.
- **`RUN mkdir -p /app/db` in the Dockerfile.** Unnecessary — the app already creates the parent: `[VERIFIED: backend/app/db/connection.py:114 — "resolved.parent.mkdir(parents=True, exist_ok=True)"]`. The stale image carries this line; it is dead weight.
- **A `HEALTHCHECK` instruction.** Explicitly rejected by D-13.
- **Adding `docker-compose.yml` to match PLAN.md §4's tree.** Explicitly rejected by D-14.
- **Bare `curl` inside a `.ps1`.** It is an alias for `Invoke-WebRequest` in PowerShell 5.1. See Pitfall 6.
- **`grep`-parsing `docker ps` output.** Use `-q` plus an anchored `--filter`; the emptiness of the output *is* the test.
- **Proposing a named volume, `nobrl`, or moving the repo when discussing WAL.** All three are the standard internet answers to "SQLite is locked in Docker" and **all three are forbidden by PROJECT.md Key Decisions and ROADMAP.md "Out of Roadmap".** They are also unnecessary — see the measurements below.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Waiting for the app to be ready | A fixed `sleep 10` | Bounded poll of `/api/health` (D-13) | `sleep` is simultaneously too slow on a warm start and too fast on a cold one. `/api/health` already reports `newest_price_age_seconds`, so it answers "is the stream alive?" not just "is the port open?" `[VERIFIED: backend/app/api/health.py:33-38 returns exactly `status`, `market_source`, `tickers_cached`, `newest_price_age_seconds`]` |
| Detecting a running container | `docker ps \| grep name` | `docker ps -q --filter "name=^NAME$" --filter status=running` | The `name` filter is a substring/regex match, so an unanchored filter matches `finally-backend-check` too — and that image exists on this machine. Anchoring plus `-q` makes emptiness the test `[CITED: docker/cli container_ls.md via Context7]` |
| Reading an image's build time | Parsing `docker images` columns | `docker image inspect --format '{{.Created}}'` | Returns RFC3339 directly. Verified: `2026-08-04T18:10:58.68533732Z` `[VERIFIED: run against a local image this session]` |
| Listing processes inside a slim container | Installing `procps` into the image | `docker top <container>` | Runs the host's `ps` against the container's PID namespace; no image bloat, and it works on `python:*-slim` which has no `ps` |
| Making the DB directory exist | `RUN mkdir -p /app/db` | Nothing — the app does it | `connection.py:114` already calls `mkdir(parents=True, exist_ok=True)` |
| Creating the FastAPI app instance | Adding `app = create_app()` to `main.py` | `uvicorn --factory app.main:create_app` | CONTEXT.md `<domain>` freezes Phase 1 code. `--factory` exists for exactly this |
| Bounded SSE read from a script | `curl -N --max-time N` with exit-code special cases | Python `urllib` + read N lines + close | `curl` exits 28 on the timeout you intended to hit, so every caller has to whitelist a failure code |
| Enforcing script line endings | A pre-commit hook | `.gitattributes` (already committed) | Rules for `*.sh`, `Dockerfile`, `*.dockerfile` and `*.ps1` are already in place and this phase is their first consumer |

**Key insight:** almost every "problem" in this phase already has an answer sitting in the repo from Phase 1 — the health endpoint, the directory creation, the line-ending rules, the static mount ordering, the `FINALLY_DB_PATH` variable. The failure mode for this phase is not under-engineering; it is re-solving solved problems in the Dockerfile and thereby creating a second source of truth.

## Runtime State Inventory

> Included because this phase must reckon with pre-existing Docker daemon state on the developer's machine, which no grep of the repository would reveal.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `db/finally.db` — tracked, WAL, seeded fresh: `cash_balance = 10000.0`, 10 watchlist rows, 1 portfolio snapshot, 6 tables `[VERIFIED: read via sqlite3 this session]` | None — this is the baseline the persistence assertion reads. **`stop` must never touch it (D-12).** |
| Live service config | **Stale Docker image `finally:latest`, created `2026-08-04T18:10:58Z`.** Built with the flattened layout (`WORKDIR /app`, `COPY backend/ ./`), `CMD ["uvicorn" "app.main:app" ...]` (cannot boot), `ENV FINALLY_DB_PATH=/app/db/finally.db`, `RUN mkdir -p /app/db` `[VERIFIED: docker image inspect + docker history finally:latest]` | **Plan must handle this.** Either choose an image name that does not collide, or make D-10's build-timestamp print the gate that catches it. Do not rely on "build if missing" alone |
| Live service config | No containers named `finally` currently exist `[VERIFIED: docker ps -a --filter name=finally returned empty]` | None |
| OS-registered state | Port 8000 is free `[VERIFIED: netstat showed 0 listeners on :8000]` | None now — but the start script must still detect a conflict (Claude's Discretion) |
| Secrets/env vars | `.env` exists at repo root, gitignored; `.env.example` documents `OPENROUTER_API_KEY`, `MASSIVE_API_KEY`, `LLM_MOCK`, `FINALLY_DB_PATH` and states *"In the container the Dockerfile sets this to /app/db/finally.db"* `[VERIFIED: git show HEAD:.env.example]` | `FINALLY_DB_PATH` is set by the **Dockerfile `ENV`**, not by `.env`. `.env` must be `.dockerignore`d (D-07) |
| Build artifacts | `backend/.venv` = **257 MB** of the 298 MB repo; `test/node_modules` = 22 MB; `.git` = 6.7 MB. **No `.dockerignore` exists** `[VERIFIED: du -sh this session; ls .dockerignore → No such file]` | `.dockerignore` is a prerequisite task, not a nicety — see Pitfall 1 |
| Build artifacts | Local image cache already holds `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` (note: **3.13**, not 3.12) `[VERIFIED: docker images]` | Irrelevant to correctness, but explains why a `python3.12-*` uv tag may not be locally cached |

## Common Pitfalls

### Pitfall 1: The build context is 298 MB and 86% of it is the host virtualenv

**What goes wrong:** every `docker build` uploads the whole context to the daemon. Without `.dockerignore`, that is 298 MB — `backend/.venv` alone is 257 MB. Worse, if `backend/.venv` is copied into the image it will *shadow* the container's own venv at `/app/backend/.venv`, installing Windows-built wheels into a Linux container.

**Why it happens:** `.dockerignore` does not exist yet `[VERIFIED: ls .dockerignore → No such file or directory]`, and `COPY backend/ /app/backend/` copies everything.

**How to avoid:** create `.dockerignore` **first**. uv's docs call this out specifically: *"it is recommended to add the .venv directory to a .dockerignore file to prevent local environment artifacts from being included in the image. The project virtual environment should be created from scratch within the container to ensure compatibility with the image's platform"* `[CITED: uv docs/guides/integration/docker.md via Context7]`.

Minimum exclusions, with sizes measured this session: `**/.venv` (257 MB), `test/` (22 MB), `.git/` (6.7 MB), `.planning/` (1.1 MB), `**/node_modules`, `**/__pycache__`, `**/.pytest_cache`, `**/.ruff_cache`, `**/.uv-cache`, `db/`, `.env`, `planning/`.

**Must NOT be excluded:** `backend/pyproject.toml`, `backend/uv.lock`, `backend/README.md` (referenced by `[VERIFIED: backend/pyproject.toml:5 — 'readme = "README.md"']`, so the project build needs it), and `backend/static/index.html`.

**Warning signs:** build step "transferring context" reporting hundreds of MB; a container that starts but imports fail with wheel/platform errors.

### Pitfall 2: A stale image named `finally:latest` defeats "build if missing"

**What goes wrong:** D-10 builds only when the image is missing. On this machine an image called `finally:latest` already exists from 2026-08-04 with the wrong layout and an un-bootable CMD. `start` would find it, skip the build, and run a container that dies on startup with `Error loading ASGI app`.

**Why it happens:** image names are a flat global namespace on the daemon, shared with every other project on the machine. `finally` is a common word.

**How to avoid:** this is exactly what D-10's "print which image it is using and when that image was built" mitigates — print the tag *and* the `docker image inspect --format '{{.Created}}'` timestamp before starting, so a 2026-08-04 timestamp under a 2026-08-10 phase is immediately visible. Consider also a more specific tag (e.g. `finally-app:latest`) so the collision cannot happen at all.

**Warning signs:** container exits immediately; `docker logs` shows `ERROR:    Error loading ASGI app.`; the printed build timestamp predates your last edit.

### Pitfall 3: `--env-file` and `load_dotenv` are two mechanisms, and only one runs

**What goes wrong:** an agent "helpfully" bind-mounts `.env` into the container as well as passing `--env-file`, or bakes `.env` into the image via `COPY`.

**Why it happens:** `config.py` calls `load_dotenv(PROJECT_ROOT / ".env")` at import `[VERIFIED: backend/app/config.py:15 — "load_dotenv(PROJECT_ROOT / \".env\")"]`, which looks like it needs a file.

**How to avoid:** D-07 is explicit — `--env-file` is the only mechanism. Under D-05, `load_dotenv` looks at `/app/.env`, finds nothing and no-ops, because Docker already injected the variables into the process environment. `python-dotenv` does not override already-set environment variables by default, so even if a file *were* present the `--env-file` values would win. Put `.env` in `.dockerignore` so it can never be baked in.

**Warning signs:** `.env` appearing in `docker history` or in the image filesystem; secrets leaking into an image layer.

### Pitfall 4: WAL over the bind mount — what a real failure would look like

**What goes wrong (in theory):** SQLite states plainly: *"All processes using a database must be on the same host computer; WAL does not work over a network filesystem"* and *"the use of shared memory means that all readers must exist on the same machine"* `[CITED: sqlite.org/wal.html]`. A Docker Desktop bind mount of a Windows host path presents as `9p`/`drvfs`, which is the shape that clause warns about.

**What actually happens here (measured):** it works. Three probes were run this session against a OneDrive-synced Windows directory bind-mounted into a `python:3.12-slim-trixie` container on Docker 29.6.1 / WSL2 kernel `6.18.33.2-microsoft-standard-WSL2`:

| Probe | Result |
|-------|--------|
| `PRAGMA journal_mode=WAL` return value | `wal` |
| Sidecars created | `probe.db`, `probe.db-shm`, `probe.db-wal` |
| 6 threads × 40 `BEGIN IMMEDIATE` increments | expected 240, **final 240**, 0 errors, 1.18s |
| Host-native Windows writer **racing** a container writer, 150 each | expected 300, **final 300**, 0 errors, `PRAGMA integrity_check` → `ok` |
| Mount as seen inside container | `C:\ on /probe type 9p (rw,...,aname=drvfs;path=C:\;uid=0;gid=0;metadata;...)`, `/probe` mode `0777` |

`[VERIFIED: all four rows executed this session in a throwaway directory outside the repo; directory deleted afterward, git status confirmed unchanged]`

**The diagnostic that must be in the stress test:** `PRAGMA journal_mode=WAL` **returns the resulting mode**, and *"if the journal mode could not be changed, the original journal mode is returned"* `[CITED: sqlite.org/pragma.html#pragma_journal_mode]`. Phase 1's `connection.py` executes the pragma but never reads the result: `[VERIFIED: backend/app/db/connection.py:62 — 'conn.execute("PRAGMA journal_mode=WAL")']`. A silent downgrade to `delete` mode is therefore invisible to the application today. **D-16's stress test should assert `PRAGMA journal_mode` reads back `wal` from inside the running container**, before it asserts anything about contention. That single assertion is the difference between "WAL is on" and "we asked for WAL".

**Failure signatures to distinguish, if it ever does fire:**

| Signature | Layer | Meaning |
|-----------|-------|---------|
| `PRAGMA journal_mode` reads back `delete` | mount | The filesystem refused WAL; shared memory unavailable. Infrastructure fact |
| `disk I/O error` / `SQLITE_IOERR_SHM*` | mount | `-shm` mmap failed. Infrastructure fact |
| `unable to open database file` | mount/permissions | Directory not writable, or `FINALLY_DB_PATH` points somewhere the mount does not reach |
| `database is locked` **with** `journal_mode = wal` | application | Lock contention that outlived `busy_timeout=5000` `[VERIFIED: backend/app/db/connection.py:31 — "BUSY_TIMEOUT_MS = 5000"]`. Not a mount problem |

**Forbidden responses, restated:** relocating the repo out of OneDrive, changing the `db/` bind-mount source (including to a named volume), and untracking `db/finally.db` are all prohibited by PROJECT.md Key Decisions and ROADMAP.md "Out of Roadmap". Generic web advice recommends all three; ignore it. `PRAGMA locking_mode=EXCLUSIVE` before first access is the documented escape hatch that avoids shared memory entirely `[CITED: sqlite.org/wal.html]`, but it is a Phase 1 code change and is **not needed** given the measurements above — record it only as a contingency.

### Pitfall 5: D-06's stated rationale does not match what this machine does

**What goes wrong:** nothing functionally — but the threat register would record a justification that the evidence contradicts, and a later reader would act on it.

**The evidence:** D-06 says *"on Windows Docker Desktop that mount is presented through drvfs with host-controlled ownership, and a non-root uid commonly cannot create files there."* Measured here, drvfs presents `/probe` as `uid=0 gid=0` mode **`0777`**, and a container running `--user 1000:1000` opened the database, set WAL, created a table and inserted a row successfully `[VERIFIED: docker run --user 1000:1000 probe, output "NONROOT WRITE: OK"]`.

**How to handle it — the decision stands, the rationale needs strengthening.** D-06 is locked and the planner must not re-open it. But the register entry should rest on the reason that *is* true: `scripts/start_mac.sh` exists, and on macOS and Linux bind mounts the host's real uid/gid **do** apply, so a hardcoded non-root container uid would hit a genuine permission failure on those platforms. Root is the choice that keeps one Dockerfile working across all three. Flagging this now prevents Phase 7 from "correcting" D-06 on the basis of a Windows-only test that passes.

### Pitfall 6: In Windows PowerShell 5.1, `curl` is not curl

**What goes wrong:** `curl http://localhost:8000/api/health` inside `start_windows.ps1` invokes `Invoke-WebRequest`, not `curl.exe`. Flags like `-f`, `-s`, `-o`, `--max-time` are then parsed as PowerShell parameters and the command fails in a confusing way.

**Why it happens:** `curl` is a built-in alias in Windows PowerShell 5.1. The alias was removed in PowerShell 7+, so the same script behaves differently depending on which host runs it.

**Measured on this machine** `[VERIFIED: probed this session]`:

| Check | Result |
|-------|--------|
| `$PSVersionTable.PSVersion` | `5.1.26100.8875` |
| `pwsh` on PATH | **absent** |
| `(Get-Command curl).CommandType` | `Alias` |
| `Invoke-WebRequest` has `-SkipHttpErrorCheck` | `False` |
| `C:\Windows\System32\curl.exe` | present, curl 8.21.0 |

**How to avoid:** target Windows PowerShell 5.1 as the floor. Use `Invoke-WebRequest -UseBasicParsing -TimeoutSec 2` wrapped in `try/catch` — in 5.1 a non-2xx response throws a terminating `System.Net.WebException`, and `-SkipHttpErrorCheck` (the clean PowerShell 7 answer) is unavailable. `-UseBasicParsing` also avoids 5.1's Internet-Explorer-engine dependency. If you prefer byte-identical behavior with the bash script, call `curl.exe` **with the `.exe` suffix** — but note that adds a Windows 10 1803+ floor.

Also avoid, as 5.1 lacks them: the ternary `? :`, null-coalescing `??`, and `ForEach-Object -Parallel`.

**Warning signs:** a `.ps1` readiness gate that never succeeds, or that reports a parameter-binding error mentioning `Invoke-WebRequest`.

### Pitfall 7: PowerShell does not stop on a failed native command

**What goes wrong:** `docker run …` fails, PowerShell continues to the next line, and the script prints `http://localhost:8000` for a container that does not exist.

**Why it happens:** `$ErrorActionPreference = "Stop"` governs *cmdlet* errors, not native executables. A failing `docker.exe` sets `$LASTEXITCODE` and nothing else. `docker` also writes normal progress to stderr, which under some settings PowerShell surfaces as errors.

**How to avoid:** check `$LASTEXITCODE` explicitly after every `docker` call and `exit` on non-zero. Keep the bash side symmetric — but note `set -euo pipefail` is *not* symmetric with PowerShell's behavior, so the two scripts need the same explicit checks in the same places if they are to stay behaviorally identical (a D-09/D-12 requirement).

**Warning signs:** `stop` reporting success when the container is still running; `start` printing the URL before readiness.

### Pitfall 8: `--frozen` cannot catch a stale lockfile

**What goes wrong:** someone edits `backend/pyproject.toml`, forgets `uv lock`, and the image builds green while silently missing the new dependency.

**Why it happens:** `--frozen` uses the lockfile as source of truth and performs no comparison. uv's implementation is explicit: the frozen branch reads the existing lockfile, validates only that workspace members are present, and returns it unchanged — *"No comparison is made between pyproject.toml requirements and lockfile contents — the stale lockfile is returned as-is"* `[CITED: uv/src/commands/project/lock.rs via Context7]`. `--locked` is the flag that errors on drift, and the two conflict `[CITED: uv-cli/src/lib.rs — conflicts_with_all]`.

**How to avoid:** D-03 and PROJECT.md both mandate `--frozen`; do not substitute `--locked`. Instead make the drift visible outside the build — the backend suite already runs `uv sync --frozen` as its regression gate from Phase 1 (SETUP-06 / success criterion 4). Record the tradeoff so Phase 7 does not rediscover it.

### Pitfall 9: Forgetting the second `uv sync` leaves the project uninstalled

**What goes wrong:** the cache-friendly pattern is `uv sync --frozen --no-install-project` (deps only) → `COPY` source → `uv sync --frozen` (installs the project). Skip the second sync and the `app` package is never installed; the app then only imports because the CWD happens to contain `app/`.

**Why it happens:** the first sync looks complete. The stale image on this machine does exactly this — `RUN uv sync --frozen --no-dev --no-install-project` followed by `COPY backend/ ./` and no second sync `[VERIFIED: docker history finally:latest]`.

**How to avoid:** always run the second `uv sync --frozen --no-dev` after copying the source. `backend/pyproject.toml` declares `[VERIFIED: backend/pyproject.toml:31-32 — "[tool.hatch.build.targets.wheel]" / "packages = [\"app\"]"]`, so the project is a real installable package and should be installed as one.

### Pitfall 10: Git Bash rewrites container-side absolute paths

**What goes wrong:** running a `docker run -v …:/app/db` command from Git Bash on Windows, MSYS rewrites `/app/db` into a Windows path. Encountered live this session: `python: can't open file '//C:/Program Files/Git/probe/probe.py'` `[VERIFIED: reproduced this session; fixed with MSYS_NO_PATHCONV=1]`.

**Why it matters here:** `start_mac.sh` is for macOS/Linux, but a Windows developer will absolutely try running it in Git Bash, and the failure is baffling.

**How to avoid:** it is not the `.sh` script's job to defend against this (no defensive programming). But the smoke check being a Python script rather than bash sidesteps it entirely for the one thing that has to work on both platforms — another argument for Pattern 6. If a bash-side workaround is ever needed, `MSYS_NO_PATHCONV=1` is the documented switch.

## Code Examples

### Dockerfile skeleton (D-01, D-03, D-05, D-06)

```dockerfile
# syntax=docker/dockerfile:1

# --- Stage 1: frontend ---
# Phase 2: passes the committed placeholder through as build output.
# Phase 7 replaces the body of this stage with `npm ci && npm run build`;
# the stage name and the COPY --from below do not change.
FROM node:24-trixie-slim AS frontend
WORKDIR /build
COPY backend/static/ ./src/
RUN mkdir -p /build/out && cp -r /build/src/. /build/out/

# --- Stage 2: runtime ---
FROM python:3.12-slim-trixie
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/backend/.venv/bin:$PATH" \
    FINALLY_DB_PATH=/app/db/finally.db

# D-05: the image mirrors the repo, so config.py's parents[2] lands on /app.
WORKDIR /app/backend

# Dependency layer: only the lockfile inputs, so source edits do not bust it.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=backend/uv.lock,target=uv.lock \
    --mount=type=bind,source=backend/pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

COPY backend/ /app/backend/
COPY --from=frontend /build/out/ /app/backend/static/

# Second sync installs the project itself. Omitting it is Pitfall 9.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8000

# Exec form: uvicorn becomes PID 1 and receives SIGTERM from `docker stop`.
# --factory is mandatory: main.py exposes create_app(), not a module-level app.
# --workers 1 is explicit so DOCK-06's guarantee is inspectable, not implied.
CMD ["uvicorn", "--factory", "app.main:create_app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

Sources for each construct: `COPY --from` and exec-form signal semantics `[CITED: moby/buildkit dockerfile reference via Context7 /docker/docs]`; the uv env vars, cache mount and two-step sync `[CITED: uv docs/guides/integration/docker.md and astral-sh/uv-docker-example/multistage.Dockerfile via Context7]`; `--factory` `[CITED: kludex/uvicorn docs/index.md]` and verified against this repo this session.

> Note the `RUN mkdir -p /build/out && cp -r …` line is the least-contrived expression of D-01 the research surfaced: it makes the Node stage produce a real filesystem artifact at a stable path that `COPY --from` consumes. Phase 7 replaces those two lines with `COPY frontend/ .` + `RUN npm ci && npm run build` and points the copy at `/build/out` — the Next.js `output: 'export'` directory. The stage name, the output path and the destination all survive. `[ASSUMED — the exact shape is a design choice; the constraint it satisfies is D-01, verified from CONTEXT.md]`

### Idempotent container detection (D-09, D-12)

```bash
# bash - anchored filter, -q, emptiness is the test. No grep parsing.
NAME=finally
running=$(docker ps     -q --filter "name=^${NAME}$" --filter status=running)
exited=$( docker ps -a  -q --filter "name=^${NAME}$" --filter status=exited)

if [ -n "$running" ]; then
  echo "Container ${NAME} is already running."
  echo "http://localhost:8000"
  exit 0
fi
[ -n "$exited" ] && docker rm "${NAME}" >/dev/null
```

```powershell
# PowerShell 5.1 - same logic, explicit $LASTEXITCODE checks (Pitfall 7).
$Name = 'finally'
$running = docker ps    -q --filter "name=^$Name$" --filter status=running
if ($LASTEXITCODE -ne 0) { Write-Error 'docker is not available'; exit 1 }
if ($running) {
    Write-Host "Container $Name is already running."
    Write-Host 'http://localhost:8000'
    exit 0
}
```

`[CITED: docker/cli container_ls.md via Context7 — name is a substring/regex filter; status takes running|exited]`

### Image identity and staleness print (D-10)

```bash
IMAGE=finally:latest
if [ -z "$(docker images -q "$IMAGE")" ] || [ "$BUILD" = "1" ]; then
  docker build -t "$IMAGE" .
fi
built=$(docker image inspect "$IMAGE" --format '{{.Created}}')
echo "Image:      ${IMAGE}"
echo "Built:      ${built}"
```

Verified output format: `2026-08-04T18:10:58.68533732Z` `[VERIFIED: docker image inspect run against a local image this session]`. This is the print that would have caught the stale image documented in Runtime State Inventory.

### Readiness gate (D-13)

```bash
# bash - bounded poll, clear failure message.
deadline=$(( $(date +%s) + 60 ))
until [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/health)" = "200" ]; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "Timed out after 60s waiting for http://localhost:8000/api/health"
    echo "Container logs:"; docker logs --tail 40 finally
    exit 1
  fi
  sleep 1
done
```

```powershell
# PowerShell 5.1 - Invoke-WebRequest throws on non-2xx here, so try/catch is
# the control flow. -SkipHttpErrorCheck does not exist in 5.1.
$deadline = (Get-Date).AddSeconds(60)
while ($true) {
    try {
        $r = Invoke-WebRequest -Uri 'http://localhost:8000/api/health' `
                               -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { break }
    } catch { }
    if ((Get-Date) -ge $deadline) {
        Write-Host 'Timed out after 60s waiting for http://localhost:8000/api/health'
        docker logs --tail 40 finally
        exit 1
    }
    Start-Sleep -Seconds 1
}
```

`[VERIFIED: PowerShell 5.1.26100.8875 is the only host installed; -SkipHttpErrorCheck absent from Invoke-WebRequest parameters — both probed this session]`

### Smoke check shape (D-15)

```python
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Prove the container serves API and static from one origin and survives a restart."""
```

Run as `uv run scripts/smoke_check.py`. Verified that a PEP 723 header with `dependencies = []` runs standalone via `uv run <file>` from a directory containing no `pyproject.toml`, on Python 3.12.13 `[VERIFIED: executed this session]`.

Bounded SSE read, stdlib only — this is the piece that is awkward in both shells:

```python
import urllib.request
req = urllib.request.Request("http://localhost:8000/api/stream/prices")
with urllib.request.urlopen(req, timeout=10) as resp:
    assert resp.headers.get("content-type", "").startswith("text/event-stream")
    lines = []
    for _ in range(40):                    # bounded: never blocks forever
        line = resp.readline()
        if not line:
            break
        lines.append(line)
        if any(l.startswith(b"data: ") for l in lines):
            break
    assert any(l.startswith(b"data: ") for l in lines), "no SSE data frame received"
```

Persistence assertion (success criterion 2) reads the seeded value directly:

```python
# baseline verified this session: cash_balance = 10000.0, 10 watchlist rows,
# 1 portfolio snapshot, journal_mode = wal
```

`[VERIFIED: db/finally.db read via sqlite3 this session — users_profile row {'id': 'default', 'cash_balance': 10000.0, 'created_at': '2026-08-06T18:04:55.054196+00:00'}, watchlist count 10, snapshots 1, journal_mode wal]`

### WAL stress test inside the container (D-16)

```python
# Assert the mode FIRST. PRAGMA journal_mode=WAL returns the RESULTING mode and
# returns the ORIGINAL mode if the change failed - a silent downgrade is
# otherwise invisible, because connection.py never reads this value.
mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
assert mode == "wal", f"WAL refused over the bind mount; mode is {mode!r}"
# Then drive concurrent BEGIN IMMEDIATE writers and assert the FINAL VALUE
# equals the committed write count - the Phase 1 lost-update standard, not
# merely "no exception raised".
```

Measured reference numbers from this session's probe, for the planner to calibrate the test against: 6 writers × 40 increments → 240/240, 0 errors, 1.18s; host-vs-container race 150+150 → 300/300, `integrity_check` = `ok`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pip install -r requirements.txt` in the image | `uv sync --frozen --no-dev` from a committed `uv.lock` | uv project workflow, 2024→ | Reproducible; already the project's mandate |
| Install uv with `pip install uv` or a curl script | `COPY --from=ghcr.io/astral-sh/uv:<ver> /uv /uvx /bin/` | uv's documented Docker guide | No network install step, version pinned by tag `[CITED: uv docs/guides/integration/docker.md]` |
| `uvicorn main:app` | `uvicorn --factory module:factory` where the app is built by a factory | uvicorn has had `--factory` for years; relevant because Phase 1 chose a factory | Mandatory here — verified the non-factory form errors |
| Node 22 (PLAN.md §11 text and PROJECT.md "Active" list) | Node 24 LTS "Krypton" | Node 24 entered Active LTS Oct 2025 | DOCK-01's `[CORR: Node 24]` already captures this. **PLAN.md §11 and PROJECT.md still say "Node 22" — REQUIREMENTS.md's `[CORR]` supersedes them** `[VERIFIED: nodejs.org/dist/index.json — v24.19.0 lts=Krypton]` |
| `python:3.12-slim-bookworm` | `python:3.12-slim-trixie` | Debian 13 "trixie" became the default base | `3.12-slim` now resolves to trixie; pin explicitly `[VERIFIED: hub.docker.com library/python tags, 3.12-slim and 3.12-slim-trixie both refreshed 2026-08-07]` |

**Deprecated/outdated:**

- **PLAN.md §11 "Stage 1: Node 22 slim"** — superseded by DOCK-01 `[CORR: Node 24]`.
- **PLAN.md §4's `docker-compose.yml` entry** — rejected outright by D-14.
- **PLAN.md §4's claim that `db/finally.db` is gitignored** — factually wrong; the file is tracked. PROJECT.md and CONTEXT.md both flag this.
- **`.planning/codebase/*.md` (dated 2026-08-04)** — predates Phase 1 and states that no FastAPI app, no `app/db/` and no `.env.example` exist. All three now do; this research scouted the live tree instead.
- **`01-SECURITY.md` "Carried Forward" row naming Phase 7 as owner of the `/docs` decision** — superseded by D-08, which resolves it here.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Tag-pinning base images (rather than digest-pinning) is the right level for this project | Package Legitimacy Audit | Low. A base-image rebuild could change bytes under a stable tag. Phase 7 could tighten to digests if reproducibility becomes a stated requirement |
| A2 | The `mkdir /build/out && cp -r` shape is the least-contrived expression of D-01's "real stage" requirement | Code Examples | Low. Any shape that produces a real artifact at a stable path satisfies D-01; this one keeps Phase 7's diff to two lines. The planner may choose differently |
| A3 | `.venv`, `test/`, `.git`, `.planning`, `planning/`, `db/`, `.env` is the right `.dockerignore` scope | Pitfall 1 | Low-medium. Over-excluding `backend/README.md` or `backend/uv.lock` would break the build loudly at build time, not silently at runtime |
| A4 | A 60-second readiness timeout is appropriate | Code Examples | Low. The measured cold start on this machine reached `/api/health` 200 within ~12s locally; a cold container will be slower. Tune during execution |
| A5 | `finally:latest` on this machine is a leftover from earlier exploratory work, not something the user depends on | Runtime State Inventory | Low. Its CMD cannot boot against the current `main.py`, so nothing can be depending on it working. Worth one line of confirmation with the user before overwriting the tag |
| A6 | The measured WAL behavior generalizes to the user's `db/` directory specifically | Pitfall 4 | Low. The probe used a OneDrive-synced Windows path on the same drive and the same Docker/WSL2 stack; `db/` differs only in path. D-16's in-place stress test is what closes the remaining gap, which is why it should still be written |

## Open Questions (RESOLVED)

All three questions were decided during planning. Each is recorded with its decision and the plan that made it, so nothing here reads as still-open to a later phase.

1. **Should the image be named something other than `finally`?**
   - What we know: `finally:latest` already exists on this machine with an incompatible layout, and `finally-backend-check:latest` also exists. Image names are a flat global namespace.
   - What's unclear: whether the user has any attachment to the `finally` tag, and whether D-10's staleness print is considered sufficient mitigation on its own.
   - Recommendation: use a more specific tag (e.g. `finally-app:latest`) **and** keep D-10's print. The print is required by D-10 regardless; the rename removes the collision entirely at zero cost. Confirm with the user during planning.
   - **DECIDED — `finally-app:latest`, with D-10's print kept.** Recorded as planner decision 1 in `02-01-PLAN.md` `<planner_decisions>`, and used consistently as the image tag and container name across `02-01`, `02-02`, `02-03` and `02-04`. The pre-existing `finally:latest` is left untouched, and `02-01` Task 1 asserts it still exists after the build.

2. **Does the WAL stress test (D-16) run against `db/finally.db` or a scratch database?**
   - What we know: `db/finally.db` is tracked in git, so writing to it produces a binary diff — PROJECT.md flags this as an accepted but real annoyance. The bind mount is `db/ → /app/db`, so a scratch file inside `db/` shares the mount and filesystem exactly.
   - What's unclear: whether a scratch file inside `db/` would be caught by `.gitignore` (only `db/*.db-wal` and `db/*.db-shm` are ignored `[VERIFIED: .gitignore:213-214]`, so `db/stress.db` would show up as untracked).
   - Recommendation: stress a scratch database at `/app/db/wal_stress.db` — same mount, same filesystem, no diff to the tracked file — and add `db/wal_stress.db*` to `.gitignore` as part of the plan. This is an ignore-rule addition, not an untracking of `finally.db`, so it does not touch the prohibition.
   - **DECIDED — scratch database at `/app/db/wal_stress.db`, with `db/wal_stress.db*` added to `.gitignore`.** Recorded in `02-03-PLAN.md` Task 1, whose acceptance criteria assert `git check-ignore db/wal_stress.db` succeeds while `git check-ignore db/finally.db` fails and `db/finally.db` stays tracked.

3. **Does the smoke check start the container itself, or assume it is running?**
   - What we know: D-15 says the script "starts the container … then restarts the container". That implies it drives the lifecycle.
   - What's unclear: whether it should shell out to the platform start script (inheriting D-13's readiness gate, as D-13 intends) or call `docker` directly (portable, but duplicates the gate).
   - Recommendation: shell out to the platform-appropriate start/stop script, selected by `sys.platform`. That is what makes D-13's "the smoke check … inherits it instead of re-implementing a wait" literally true.
   - **DECIDED — shell out to the platform script, selected on `sys.platform`.** Recorded in `02-04-PLAN.md` Task 1 as `start_container()` / `stop_container()`, and pinned by that plan's `key_links` entry (`pattern: sys.platform`) and by the acceptance criterion requiring at least one `sys.platform` occurrence.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Engine / Desktop | DOCK-01, 03, 04, 05, 06, 07 | ✓ | 29.6.1, WSL2 kernel 6.18.33.2-microsoft-standard-WSL2, overlayfs | — |
| `uv` | D-03 build, smoke-check runner | ✓ | 0.11.30 (host); 0.12.3 recommended in-image | — |
| Node.js (host) | Not required this phase — the Node stage runs in the image | ✓ | v26.4.0 host / **image pins 24** | — |
| npm (host) | Phase 7 only | ✓ | 11.17.0 | — |
| `curl` (Git Bash) | `start_mac.sh` readiness gate | ✓ | 8.21.0 (mingw) | — |
| `curl.exe` (Windows) | Optional parity path for `.ps1` | ✓ | 8.21.0, `C:\Windows\System32\curl.exe` | `Invoke-WebRequest` |
| Windows PowerShell | `start_windows.ps1`, `stop_windows.ps1` | ✓ | **5.1.26100.8875** | — |
| PowerShell 7 (`pwsh`) | — | ✗ | — | **Target 5.1. No `-SkipHttpErrorCheck`, no ternary, no `??`** |
| Python (host) | `uv run` selects 3.12 for the script | ✓ | 3.14.6 system; uv provides 3.12.13 | — |
| Port 8000 | DOCK-03 | ✓ free | — | Script must detect and report a conflict |
| `node:24-trixie-slim` | DOCK-01 | ✓ published | 24.19.0 | — |
| `python:3.12-slim-trixie` | DOCK-01 | ✓ pulled this session | 3.12 | — |
| `ghcr.io/astral-sh/uv:0.12.3` | D-03 | ✓ published | 0.12.3 | Alt: `FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim` (confirmed to exist) |

**Missing dependencies with no fallback:** none.

**Missing dependencies with fallback:**
- **PowerShell 7 is absent.** Fallback: write both `.ps1` scripts against Windows PowerShell 5.1 semantics. This is a constraint on the plan, not a blocker.

**Not verified as present:** the tag `ghcr.io/astral-sh/uv:python3.12-trixie-slim` (used in uv's own example Dockerfile) was **not** in the GHCR tag list this session. Prefer the `COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /uvx /bin/` form, whose base tag `0.12.3` corresponds to the confirmed-current uv release.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3+ with pytest-asyncio (`asyncio_mode = "auto"`) `[VERIFIED: backend/pyproject.toml:20-22, 39]` |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]`, `testpaths = ["tests"]` `[VERIFIED: backend/pyproject.toml:34-40]` |
| Quick run command | `cd backend && uv run --extra dev pytest -q` |
| Full suite command | `cd backend && uv run --extra dev pytest -v` |
| Phase-2 harness | `uv run scripts/smoke_check.py` — **outside pytest by design (D-15)** |

**Load-bearing constraint from D-15:** the container assertions must **not** enter the pytest suite. D-15 states that folding them in "would put a Docker daemon dependency inside a suite that currently runs in seconds without one." The Validation Architecture for this phase therefore has two tiers: the unchanged pytest suite (regression guard, no Docker) and the new smoke script (phase proof, requires Docker).

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DOCK-01 | Multi-stage build completes; both stages present | build | `docker build -t finally-app .` (exit 0) | ❌ Wave 0 (`Dockerfile`) |
| DOCK-01 | Node stage output actually reaches the image | smoke | assert `GET /` returns the placeholder markup (contains `FinAlly`) | ❌ Wave 0 (`scripts/smoke_check.py`) |
| DOCK-03 | API and static served from one origin, one port | smoke | assert `GET :8000/api/health` → 200 `application/json` **and** `GET :8000/` → 200 `text/html`, same host:port | ❌ Wave 0 |
| DOCK-03 | Static mount does not shadow `/api/*` | smoke | assert `GET /api/health` body parses as JSON with key `status` (not HTML) | ❌ Wave 0 |
| DOCK-03 | SSE streams through the container | smoke | bounded read of `/api/stream/prices`; assert `content-type: text/event-stream` and ≥1 `data: ` frame | ❌ Wave 0 |
| DOCK-04 | DB survives a restart | smoke | read `cash_balance` → restart container → re-read; assert equal (baseline `10000.0`) | ❌ Wave 0 |
| DOCK-04 | The bind mount is the file being written | smoke | assert host `db/finally.db` mtime advances after a container write | ❌ Wave 0 |
| DOCK-04 | WAL actually engaged over the mount (D-16) | stress | in-container: assert `PRAGMA journal_mode=WAL` returns `wal`, then N-way `BEGIN IMMEDIATE` contention; assert final value == committed count | ❌ Wave 0 (`scripts/` stress task) |
| DOCK-05 | `start` twice is safe | smoke | run start, run start again; assert exit 0 both times and one container exists | ❌ Wave 0 |
| DOCK-05 | `stop` twice is safe | smoke | run stop, run stop again; assert exit 0 both times | ❌ Wave 0 |
| DOCK-05 | `stop` never touches `db/` | smoke | hash `db/finally.db` before and after `stop`; assert unchanged | ❌ Wave 0 |
| DOCK-06 | Exactly one uvicorn worker (static) | smoke | `docker inspect --format '{{json .Config.Cmd}}'` contains `--workers 1` | ❌ Wave 0 |
| DOCK-06 | Exactly one app process (runtime) | smoke | `docker top <name>`; assert exactly 1 line matching `app.main:create_app` | ❌ Wave 0 |
| DOCK-07 | `.env` reaches the container | smoke | set `LLM_MOCK=true` in `.env`, restart, assert the container's env carries it (`docker exec … printenv LLM_MOCK`) | ❌ Wave 0 |
| DOCK-07 | `.env` is NOT baked into the image | build | assert `.env` absent from the image filesystem (`docker run --rm --entrypoint sh <img> -c 'test ! -f /app/.env'`) | ❌ Wave 0 |
| (regression) | Phase 1 suite still green | unit | `cd backend && uv run --extra dev pytest -q` | ✅ exists (`backend/tests/`, 22 test modules) |

### Sampling Rate

- **Per task commit:** `cd backend && uv run --extra dev pytest -q` (no Docker; must stay fast and green — this phase changes no `backend/app/` code, so any failure here is a regression from something the phase should not have touched)
- **Per wave merge:** `docker build` + `uv run scripts/smoke_check.py`
- **Phase gate:** full `pytest -v` green, `ruff check app/ tests/` clean, and `smoke_check.py` green, before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `.dockerignore` — **prerequisite for every build task** (298 MB context today); blocks DOCK-01
- [ ] `Dockerfile` — covers DOCK-01, DOCK-03, DOCK-06, DOCK-07
- [ ] `scripts/smoke_check.py` — covers DOCK-01, DOCK-03, DOCK-04, DOCK-05, DOCK-06, DOCK-07
- [ ] `scripts/start_mac.sh`, `scripts/stop_mac.sh` — covers DOCK-05 (LF)
- [ ] `scripts/start_windows.ps1`, `scripts/stop_windows.ps1` — covers DOCK-05 (CRLF, PS 5.1 semantics)
- [ ] WAL-over-bind-mount stress task — covers DOCK-04 / D-16
- [ ] `.gitignore` addition for the stress scratch DB (see Open Question 2)
- [ ] Framework install: **none needed** — pytest is already configured and the smoke check runs on stdlib via `uv run`

## Security Domain

### Applicable ASVS Categories

ASVS L1, `security_block_on: high` `[VERIFIED: .planning/config.json — "security_asvs_level": 1, "security_block_on": "high"]`.

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth by design — single local operator, documented in PROJECT.md |
| V3 Session Management | no | No sessions |
| V4 Access Control | no | No users, no roles |
| V5 Input Validation | no (this phase) | This phase adds no request-handling code; ticker/quantity validation is Phase 3 |
| V6 Cryptography | no | No secrets are generated, stored or transmitted by this phase |
| V7 Error Handling & Logging | yes (light) | Scripts must not echo `.env` contents or API keys on failure paths |
| V10 Malicious Code | yes | Base-image provenance — three official/first-party images, tag-pinned (see Package Legitimacy Audit) |
| V12 File & Resource | yes | Bind mount is the only host filesystem the container touches; scope it to `db/` alone |
| V14 Configuration | yes | `--env-file` as the sole config channel (D-07); `.env` in `.dockerignore`; `/docs` deliberately enabled (D-08) |

### Known Threat Patterns for a localhost single-container FastAPI + bind-mounted SQLite

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secrets baked into an image layer via `COPY .env` | Information Disclosure | `.env` in `.dockerignore`; `--env-file` only (D-07). Assert absence in the image as a build check (see Validation Architecture) |
| Container runs as root with a host bind mount | Elevation of Privilege | **Accepted (D-06).** Localhost, single operator, no untrusted input. Note the register rationale correction in Pitfall 5 — the true reason is cross-platform bind-mount ownership on macOS/Linux, not Windows drvfs |
| Full API schema exposed at `/docs`, `/redoc`, `/openapi.json` | Information Disclosure | **Accepted (D-08).** Supersedes `01-SECURITY.md` R-05 / T-1-18, whose "owner phase: Phase 7" row is now closed. No secrets in the schema; localhost only |
| Port published to all interfaces | Information Disclosure | `-p 8000:8000` binds `0.0.0.0` by default. Consider `-p 127.0.0.1:8000:8000` to keep the terminal off the LAN. **New consideration for this phase — not covered by any Phase 1 threat** |
| Base image supply chain | Tampering | Tag-pinned official / first-party images; see Package Legitimacy Audit |
| Bind mount scoped wider than needed | Tampering | Mount only `./db:/app/db`. Never mount the repo root — that would put `.env`, `.git` and source inside the container |
| Unbounded concurrent SSE connections | Denial of Service | **Already accepted** as T-1-08 / R-01 in `01-SECURITY.md`; unchanged by containerization |
| Stale image silently served | Tampering (integrity of what runs) | D-10's image-name + build-timestamp print. Live instance found on this machine — see Runtime State Inventory |

**Threat register guidance for the planner:** carry D-06 forward as an explicit `accept` with the corrected rationale from Pitfall 5, carry D-08 forward as an explicit `accept` that closes R-05, and add the two threats this phase newly introduces — secrets-in-image-layer (mitigate via `.dockerignore` + build assertion) and port-binding scope (decide `0.0.0.0` vs `127.0.0.1`). Phase 1's threat IDs used the `T-1-NN` form and `01-SECURITY.md` warns that `T-1-05` was double-assigned; use a `T-2-NN` series here and do not reuse Phase 1 IDs.

## Project Constraints (from CLAUDE.md)

Extracted from `./CLAUDE.md`, `./.claude/CLAUDE.md` and the user's global instructions. The planner must verify each plan complies.

| Directive | Applies to this phase as |
|-----------|--------------------------|
| **No emojis** in code, print statements, logging or docstrings | Every line of shell and PowerShell output the start/stop/smoke scripts produce |
| **No defensive programming**; exception managers only when needed | No speculative `try/except` around docker calls. The PowerShell `try/catch` in the readiness gate is *required* control flow (5.1 throws on non-2xx), not defensiveness |
| **Short modules and functions**, name things clearly | `smoke_check.py` should be a sequence of small named assertions, not one long main |
| **`uv run` / `uv add` only** — never bare `python` or `pip` | The smoke check is invoked as `uv run scripts/smoke_check.py`. Inside the image the venv is on `PATH`, which is the equivalent |
| **Use latest library APIs** | Node 24 LTS, python:3.12-slim-trixie, uv 0.12.3, `uvicorn --factory` |
| **Docstrings over inline comments** | The Dockerfile is the exception — its comments carry the "why" for D-05, `--factory` and exec form, because a Dockerfile has no docstrings |
| **Work incrementally, validate each increment** | `.dockerignore` → Dockerfile builds → container runs → scripts → smoke check → WAL stress. Each is independently verifiable |
| **Identify root cause before fixing; prove with evidence** | Directly binding on D-16: if `database is locked` appears, read `PRAGMA journal_mode` first to separate mount-layer from application-layer |
| **Mount order**: `StaticFiles` after every `/api/*` router | Already satisfied in `main.py:52-54`. This phase must not disturb it, and the smoke check asserts it over HTTP |
| **Reproducibility**: build from lockfiles | `uv sync --frozen --no-dev` (D-03). `npm ci` is Phase 7 |
| **One container, one port, one origin; no orchestration** | Reinforces D-14's rejection of `docker-compose.yml` |
| **Use Context7 for library/CLI docs** | Followed — uv, uvicorn and Docker docs were fetched via Context7 this session |

## Sources

### Primary (HIGH confidence)

- **Live repository, read this session** — `backend/app/config.py`, `backend/app/main.py`, `backend/app/api/health.py`, `backend/app/db/connection.py`, `backend/pyproject.toml`, `backend/static/index.html`, `.gitattributes`, `.gitignore`, `git show HEAD:.env.example`, `db/finally.db`
- **Empirical measurement, this session** — WAL/`-shm`/`-wal` behavior, 6-way and host-vs-container contention, drvfs mount options and permissions, non-root write; `uvicorn app.main:app` failure and `--factory` success; `--workers 1`; PEP 723 `uv run`; PowerShell 5.1 capabilities; `docker image inspect` timestamp format; build-context sizing; stale `finally:latest` inspection
- **sqlite.org/wal.html** — WAL shared-memory and network-filesystem constraints; `locking_mode=EXCLUSIVE` escape hatch
- **sqlite.org/pragma.html#pragma_journal_mode** — the pragma returns the resulting mode, and the original mode on failure
- **Docker Hub registry API** (`library/node`, `library/python`), **PyPI** (`uv`), **nodejs.org/dist/index.json**, **ghcr.io tag list** (`astral-sh/uv`) — version and tag verification

### Secondary (MEDIUM confidence)

- **Context7 `/astral-sh/uv`** — `--frozen` vs `--locked` semantics from `uv-cli/src/lib.rs` and `commands/project/lock.rs`; `UV_PROJECT_ENVIRONMENT`; `docs/guides/integration/docker.md`
- **Context7 `/astral-sh/uv-docker-example`** — `multistage.Dockerfile`, `UV_COMPILE_BYTECODE` / `UV_LINK_MODE`, venv-on-PATH
- **Context7 `/kludex/uvicorn`** — CLI settings, `--factory`, `--workers`, `run()` defaults, `server.py` signal handling
- **Context7 `/docker/docs`** — multi-stage `COPY --from`, exec-vs-shell form and the 10.19s vs 0.20s stop measurement
- **Context7 `/docker/cli`** — `container_ls` filters, `InspectResponse.State`, `--format` fields

### Tertiary (LOW confidence)

- WebSearch on SQLite-in-Docker locking (docker/for-win#11, Docker forums, TriliumNext#3987) — **used only to characterize failure signatures**. Its recommended remedies (named volumes, `nobrl`, relocating the workspace) are all forbidden by PROJECT.md and are explicitly rejected in this document. Superseded on every factual point by the direct measurement above
- WebSearch on Node LTS status — returned a stale claim that Node 22 is Active LTS and Node 24 is not. **Contradicted and corrected** by `nodejs.org/dist/index.json` and the `lts-krypton` Docker tag aliases
- WebSearch on PowerShell `-SkipHttpErrorCheck` — the PowerShell-7-only claim was confirmed directly against the 5.1 host on this machine

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — every image tag and version confirmed against its registry API this session; no package installs to get wrong
- Architecture: **HIGH** — D-05's `parents[2]`, the `--factory` requirement and the router-then-static ordering were each read from the source file and, where executable, run
- Pitfalls: **HIGH** — eight of the ten were reproduced or measured directly on this machine, including the two that would have cost the most (the stale image and the PowerShell `curl` alias)
- WAL over the bind mount: **HIGH** — measured three ways, including the hardest case (host process racing container process). D-16's flagged risk did not materialize on this machine
- Validation architecture: **MEDIUM** — the assertion set is derived from the six requirements and D-15's wording; the exact smoke-script decomposition is the planner's call
- Security domain: **MEDIUM** — ASVS L1 mapping is judgement over a well-understood localhost threat model; the two new threats are clearly identified

**Research date:** 2026-08-10
**Valid until:** 2026-09-09 (30 days — Docker, uv and the base images are stable; re-verify base-image tags if the phase slips past that)
