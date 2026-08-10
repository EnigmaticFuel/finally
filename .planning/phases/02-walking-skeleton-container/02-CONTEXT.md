# Phase 2: Walking-Skeleton Container - Context

**Gathered:** 2026-08-10
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase wraps the Phase 1 spine in a single Docker image and gives the user one command to run it.

**In scope:** a multi-stage `Dockerfile` (Node 24 frontend stage, Python 3.12 backend stage), the `db/` bind mount that makes SQLite survive restarts, `scripts/start_mac.sh`, `scripts/stop_mac.sh`, `scripts/start_windows.ps1`, `scripts/stop_windows.ps1`, a single-uvicorn-worker run command, `.env` delivery into the container, a committed smoke check that proves the four success criteria, and a deliberate stress of WAL over the bind mount.

**Out of scope:** any real frontend (the Node stage builds a placeholder — Phase 4 creates the Next.js project, Phase 7 makes the stage build it), `npm ci` (DOCK-02's Node half, Phase 7), portfolio/watchlist/chat routers (Phase 3, Phase 6), the Playwright E2E suite (Phase 7), cloud deployment (out of scope for the milestone).

**Frozen:** `backend/app/market/` is untouched. Phase 1's `create_app()`, `config.py`, `db/` layer and `backend/static/index.html` are consumed as they stand — no decision here edits Phase 1 code.

</domain>

<decisions>
## Implementation Decisions

### Build stages

- **D-01:** The Node 24 stage is real, not a formality. It takes the committed `backend/static/index.html` as its input and emits it as build output; the Python stage pulls that output in with `COPY --from`. Nothing meaningful is compiled, but the stage boundary and the cross-stage copy — the exact seam Phase 7 replaces with `npm ci && npm run build` — are exercised now. A no-op stage would satisfy DOCK-01's wording while leaving Phase 7 to meet the seam for the first time, which is the risk this phase exists to retire.

- **D-02:** One page, one source of truth. The container and a local `uvicorn` serve byte-identical content because both resolve to the same committed placeholder. No synthesized container-only page and no build-time stamp — Phase 7 changes only the producer of the static output, never its destination or its content contract.

- **D-03:** The Python stage installs with `uv sync --frozen --no-dev` from the start. `backend/uv.lock` already exists and is committed, so a looser install would be extra work that proves less, and it would mean the image is built one way in Phase 2 and another in Phase 7. **DOCK-02 therefore narrows in Phase 7 to its `npm ci` half** — the only half that genuinely cannot exist yet, because there is no `package.json`. Planner should note this as a scope reduction for Phase 7, not a scope addition here.

- **D-04:** `backend/static/` stays tracked with the placeholder as its only committed content. The Next.js export exists solely inside the Docker build and is written into the image at `COPY --from` time — it never lands in the host working tree. Nothing to gitignore, nothing to clobber, and a local `uvicorn` always serves the placeholder until Phase 4 replaces it deliberately. — **Reversibility:** costly — Phase 4's frontend dev loop and Phase 7's build stage are both written against this contract, and switching to a host-side export later means adding ignore rules and reasoning about a stale export shadowing the tracked file.

### Image layout

- **D-05:** The image mirrors the repository: backend code lands at `/app/backend/`, so `config.py`'s `PROJECT_ROOT = Path(__file__).resolve().parents[2]` resolves to `/app` exactly as it resolves to the repo root locally. Flattening `backend/` to `/app` — the conventional Docker layout — would make `parents[2]` resolve to `/`, so `load_dotenv` would look for `/.env` and silently find nothing. That currently happens to be harmless because `--env-file` populates the environment before Python starts, but it is harmless by accident, and any later code assuming `PROJECT_ROOT` is the repo root would be right on the host and wrong in the container. The bind mount stays at `/app/db` and `FINALLY_DB_PATH` stays `/app/db/finally.db`, exactly as D-26 documented in `.env.example`. — **Reversibility:** costly — the Dockerfile `COPY` paths, `WORKDIR`, the uvicorn invocation and every path in the start scripts encode this layout.

- **D-06:** The container runs as **root**, and this is a deliberate recorded choice rather than an unexamined default. DOCK-04 turns on writing `finally.db` and its `-wal`/`-shm` sidecars into a bind-mounted host directory; on Windows Docker Desktop that mount is presented through drvfs with host-controlled ownership, and a non-root uid commonly cannot create files there. Hardening the user would risk failing DOCK-04 on the exact platform this project is developed on. The justification is the same one `01-SECURITY.md` already applied to accept T-1-07, T-1-08 and T-1-10: a localhost single-operator app with no auth and no untrusted input. **The planner must carry this into the Phase 2 threat register as an explicit accept with this rationale, not leave it unmentioned.**

- **D-07:** `--env-file .env` on the `docker run` line is the only configuration mechanism, exactly as PLAN.md section 11 shows. No second bind mount for `.env` — one job, one mechanism, and the real secrets file stays out of the container filesystem. Note the consequence, which is now correct rather than accidental: inside the container `load_dotenv` looks at `/app/.env`, finds nothing, and no-ops, because Docker has already injected the variables.

- **D-08:** **R-05 / T-1-18 is resolved: `/docs`, `/redoc` and `/openapi.json` stay enabled**, in the image and locally. No secrets appear in the schema, the app is a localhost single-operator terminal with no auth, and for a capstone teaching project the interactive docs are a feature — a student can open `/docs` and exercise every endpoint by hand. This requires no code change to `main.py` and closes an item `01-SECURITY.md` carried forward. `01-SECURITY.md` lists the owner phase as Phase 7; that is superseded — the decision is made here and Phase 7 inherits it rather than re-opening it.

### Start and stop scripts

- **D-09:** `start` is idempotent in the strict sense: if a container is already running it reports that, prints `http://localhost:8000`, and exits 0. It does not stop and recreate — an accidental second invocation must not drop the SSE stream or reset every ticker's session open price. This is the reading of success criterion 3 that matches "same command, same end state".

- **D-10:** The image is built when it is missing, or when `--build` is passed — PLAN.md section 11's stated behavior. The known failure mode is real (edit backend code, forget `--build`, wonder why nothing changed), so **the script must print which image it is using and when that image was built**, making staleness visible rather than silent. Always-rebuilding was rejected: it slows the first-run experience, which is the thing a student actually judges.

- **D-11:** The start script prints the URL and does not open a browser. Predictable, identical over SSH and in CI, and it never steals focus or spawns a tab on the no-op second run. No `--open` flag — the script pair already carries `--build`.

- **D-12:** `stop` stops and removes the container, reports "nothing to stop" and exits 0 when none is running, and **never touches `db/`**. Exiting non-zero on an already-stopped container would break the safe `stop` -then- `start` pattern and reads as unsafe against success criterion 3. The `db/` prohibition is what success criterion 2 and DOCK-04 turn on.

- **D-13:** The start script owns the readiness gate: it polls `/api/health` until 200 with a bounded timeout and a clear failure message, and only then prints the URL. Putting the gate in the script means the smoke check, a human, and Phase 7's Playwright `globalSetup` all inherit it instead of each re-implementing a wait. `/api/health` already reports `tickers_cached` and `newest_price_age_seconds`, so it answers "is the stream alive?" in the same request. A Docker `HEALTHCHECK` instruction was rejected — it adds a polling process inside the container and the scripts would still need an HTTP check to prove same-origin serving.

- **D-14:** **No `docker-compose.yml`.** The start scripts already wrap the single `docker run`, so a compose file would be a second expression of the same port, mount and env-file configuration — two sources of truth that drift. This is a deliberate deviation from PLAN.md section 4, which lists the file in its directory tree as an "optional convenience wrapper"; PROJECT.md's constraints ("one container, one command, no orchestration") win. Recorded so the next agent does not re-add it or re-ask.

### Proving the phase

- **D-15:** Verification is a committed smoke script plus human UAT, not manual UAT alone and not pytest. The script starts the container, asserts `/api/health` and `/api/stream/prices` respond, asserts the static page and the API serve from the same origin and port, then restarts the container and re-reads the cash balance to prove persistence. It is re-runnable by anyone and becomes the foundation Phase 7's E2E suite layers on rather than duplicates. Folding these checks into the backend pytest suite was rejected: it would put a Docker daemon dependency inside a suite that currently runs in seconds without one.

- **D-16:** WAL over the bind mount is **stressed deliberately in this phase**, not left to surface later. Phase 1's concurrency test passed against a host-filesystem database; the bind mount is the untested variable, and the roadmap flags it as unconfirmed on this machine. Driving concurrent writes against the containerized, bind-mounted database here means a `database is locked` failure is diagnosed as an infrastructure fact, rather than discovered under Phase 3's trade logic where it would look like a trade bug. If it fires, PROJECT.md and the roadmap both apply: **diagnose it in place — no plan may propose relocating the repo out of OneDrive, changing the `db/` bind-mount source, or untracking `db/finally.db`.**

### Claude's Discretion

The user took the recommended option on every question, so no area was explicitly delegated. Left to the planner and executor: the uvicorn invocation's exact form and how DOCK-06's single-worker guarantee is made visible; `.dockerignore` scope (`db/`, `.venv`, `node_modules`, `.planning`, `.git`); image and container naming; how a port-8000 conflict is detected and reported; base-image variant and pinning strategy for both stages; layer ordering for cache efficiency; and the precise assertions the smoke script makes beyond those named in D-15.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product specification (authoritative for behavior and shapes)
- `planning/PLAN.md` §11 — Dockerfile stages, the bind-mount form of `docker run`, start/stop script responsibilities, and the static mount-order hazard
- `planning/PLAN.md` §5 — environment variables and the single-`.env`-at-the-root rule
- `planning/PLAN.md` §4 — directory structure; note D-14 deliberately departs from its `docker-compose.yml` entry, and note that its claim that `db/finally.db` is gitignored is factually wrong
- `planning/PLAN.md` §13 — build order; this phase is the user-approved early execution of step 7

### Phase scope and constraints
- `.planning/ROADMAP.md` — Phase 2 goal, the four success criteria, the "Why here and not at the end" note, and the "Watch for" note on WAL over the Windows bind mount
- `.planning/REQUIREMENTS.md` — DOCK-01, DOCK-03, DOCK-04, DOCK-05, DOCK-06, DOCK-07, including the `[CORR: Node 24]` correction on DOCK-01 and the `[CORR]` on DOCK-06. DOCK-02 belongs to Phase 7 and D-03 narrows it there
- `.planning/PROJECT.md` — Key Decisions table. The OneDrive location, the `db/` bind mount and the tracked `db/finally.db` are accepted risks, not tasks

### Phase 1 contracts this phase builds on
- `.planning/phases/01-foundation-spine/01-CONTEXT.md` — D-11 (committed `backend/static/index.html`), D-12 and D-26 (`FINALLY_DB_PATH`, its local default and the Docker value), D-03/D-04 (WAL and `busy_timeout=5000`, and why the short timeout is diagnostic)
- `.planning/phases/01-foundation-spine/01-SECURITY.md` — R-05 / T-1-18, resolved here by D-08; the accept rationale for T-1-07, T-1-08 and T-1-10 that D-06 reuses
- `backend/app/config.py` — the `parents[2]` walk that D-05 exists to keep honest, and the four configuration constants
- `backend/app/main.py` — `create_app()`, `STATIC_DIR`, and the `app.frontend()` call registered after both routers

### Code style
- `.planning/codebase/CONVENTIONS.md` — style rules this phase must match
- `.gitattributes` — `.sh` and `Dockerfile` pinned to LF, `.ps1` to CRLF. The scripts this phase creates are the first real consumers of those rules

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`GET /api/health`** (`backend/app/api/health.py`) — already returns `status`, `market_source`, `tickers_cached` and `newest_price_age_seconds`. D-13's readiness gate and D-15's smoke check both consume it; neither needs a new endpoint.
- **`backend/static/index.html`** — committed in Phase 1 specifically so the static path is real from day one. D-01 and D-02 make it the Node stage's payload.
- **`FINALLY_DB_PATH`** — the env var D-12/D-26 introduced for exactly this phase. The Docker value `/app/db/finally.db` is already documented in `.env.example`.
- **`backend/uv.lock`** — committed and current, which is what makes D-03's `uv sync --frozen --no-dev` available immediately.

### Established Patterns

- No emojis anywhere, including shell and PowerShell output
- Docstrings and comments carry the "why"; inline comments are rare
- Short modules and functions; no defensive branches for conditions that cannot occur
- `uv run` / `uv add` only — never bare `python` or `pip`

### Integration Points

- **`create_app()`** is consumed unchanged. The container's uvicorn invocation targets it; nothing in this phase edits `main.py`.
- **The bind mount** connects host `db/` to `/app/db`, and `FINALLY_DB_PATH` is what points the app at it. Both halves must agree or DOCK-04 fails silently by writing to a container-local path.
- **`.gitattributes`** already pins line endings for `.sh`, `Dockerfile` and `.ps1`. Phase 1's SETUP-03 verification was rewritten to `git check-attr` precisely because these files did not exist yet — this phase creates the files those rules were written for, so the original `git ls-files --eol` check becomes meaningful again.

### Stale map warning

`.planning/codebase/STACK.md` and the other `.planning/codebase/*.md` maps are dated 2026-08-04, **before Phase 1**. They state that no FastAPI app, no `app/db/`, and no `.env.example` exist. All three now do. Scout the live tree rather than trusting those maps.

</code_context>

<specifics>
## Specific Ideas

- **The `/docs` decision is closed, not deferred.** `01-SECURITY.md` lists Phase 7 as the owner of R-05. D-08 supersedes that. Phase 7 should inherit the decision, not re-open it.
- **DOCK-02 shrinks rather than moves.** D-03 lands the `uv sync --frozen --no-dev` half now, so Phase 7 owns only `npm ci`. The planner should say so explicitly in the Phase 2 summary so Phase 7 does not re-plan work already done.
- **The "print which image and when it was built" requirement in D-10 is load-bearing**, not cosmetic. It is the entire mitigation for the build-if-missing policy's one real failure mode.
- **`stop` never touching `db/` is a prohibition, not a preference.** Success criterion 2 and DOCK-04 both depend on it.
- If WAL over the bind mount fails (D-16), the response is diagnosis and documentation. Relocating the repo, changing the mount source, or untracking `db/finally.db` are all forbidden by PROJECT.md's Key Decisions.

</specifics>

<deferred>
## Deferred Ideas

- **`npm ci` and the real Next.js build stage** — Phase 7 (DOCK-02, remaining half). D-01 builds the seam it will slot into.
- **Playwright E2E against the container** — Phase 7 (TEST-04..15). D-15's smoke script is the foundation, deliberately not a replacement.
- **A Docker `HEALTHCHECK` instruction** — considered and rejected for this phase (D-13). Could be revisited in Phase 7 when the container becomes production-shaped, but it would not remove the need for an HTTP same-origin check.
- **Non-root container user** — rejected here on DOCK-04 grounds (D-06). If the project ever leaves localhost, this is the first thing to revisit.
- **`docker-compose.yml`** — rejected outright (D-14), not deferred. Recorded so it is not silently re-added to match PLAN.md section 4's tree.

</deferred>

---

*Phase: 2-Walking-Skeleton Container*
*Context gathered: 2026-08-10*
