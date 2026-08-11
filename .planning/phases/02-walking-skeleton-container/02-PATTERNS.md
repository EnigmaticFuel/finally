# Phase 2: Walking-Skeleton Container - Pattern Map

**Mapped:** 2026-08-10
**Files analyzed:** 8 new/modified
**Analogs found:** 3 / 8 (in-repo analogs); 5 have no in-repo analog by construction

## Scope note: this is an infrastructure phase

There is **no `Dockerfile`, no `.dockerignore`, no `.sh` and no `.ps1` file anywhere in this
repository** `[VERIFIED: git ls-files scripts -> empty; scripts/ is an empty directory; ls .dockerignore -> absent]`.
Five of the eight files in this phase therefore have **no code analog**, and inventing one would
be worse than saying so. For those files this document supplies the *conventions and repo facts
they must honor* instead — the `.gitattributes` line-ending rules they are the first consumers of,
the exact `config.py` path walk the image layout must keep true, and the `main.py` mount ordering
the smoke check asserts over HTTP.

Two files do have strong in-repo analogs and they are the ones that matter most:
`scripts/smoke_check.py` (analogs: `backend/market_data_demo.py` and `backend/tests/test_main.py`)
and the WAL stress logic (analog: `backend/tests/db/test_concurrency.py`).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `.dockerignore` | config | build-context filter | `.gitignore` (comment-block style only) | style-only |
| `Dockerfile` | config | build/transform | **none in repo.** Load-bearing constraints from `backend/app/config.py`, `backend/app/main.py`, `backend/pyproject.toml` | no analog |
| `scripts/start_mac.sh` | script (host) | process lifecycle + request-response poll | **none in repo** (first `.sh`) | no analog |
| `scripts/stop_mac.sh` | script (host) | process lifecycle | **none in repo** | no analog |
| `scripts/start_windows.ps1` | script (host) | process lifecycle + request-response poll | **none in repo** (first `.ps1`); must mirror `start_mac.sh` line for line | no analog |
| `scripts/stop_windows.ps1` | script (host) | process lifecycle | **none in repo**; mirrors `stop_mac.sh` | no analog |
| `scripts/smoke_check.py` | test harness (standalone script) | request-response + streaming + file I/O | `backend/market_data_demo.py` (standalone `uv run` script) + `backend/tests/test_main.py` (assertion set) | exact (two-part) |
| WAL stress logic (inside `scripts/smoke_check.py` or a sibling) | test harness | concurrent write / batch | `backend/tests/db/test_concurrency.py` | exact |
| `.gitignore` (append) | config | — | `.gitignore:210-215` SQLite WAL sidecar block | exact |

---

## Pattern Assignments

### `scripts/smoke_check.py` (test harness, request-response + streaming)

**Analog A: `backend/market_data_demo.py`** — the repo's only standalone `uv run` script.
Copy its module-docstring-with-run-command shape, its `from __future__` line, its
`SCREAMING_SNAKE_CASE` module constants, its small named functions with full type hints, and its
`if __name__ == "__main__":` tail.

Header pattern (`backend/market_data_demo.py:1-13`):

```python
"""FinAlly Market Data Simulator Demo.

Run with:  uv run market_data_demo.py

Displays a live-updating terminal dashboard of simulated stock prices
using the GBM simulator and Rich library.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
```

For the smoke check, this becomes a PEP 723 header *above* the docstring (RESEARCH.md line 600-606),
then the same `from __future__ import annotations` first-import rule.

Constants pattern (`backend/market_data_demo.py:27-32`):

```python
# Ordered ticker list matching the default watchlist
TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]

DURATION = 60  # seconds
```

Small typed function pattern (`backend/market_data_demo.py:47-51`) — this is the granularity the
"short functions / a sequence of small named assertions" rule means:

```python
def format_price(price: float) -> str:
    """Format a price with comma separator."""
    if price >= 1000:
        return f"{price:,.2f}"
    return f"{price:.2f}"
```

Entrypoint pattern (`backend/market_data_demo.py:260-261`):

```python
if __name__ == "__main__":
    asyncio.run(run())
```

The smoke check is synchronous stdlib, so this is `main()` rather than `asyncio.run(run())`.

**Analog B: `backend/tests/test_main.py`** — the assertion set the smoke check re-runs over HTTP
against the container. **Do not invent new assertions where these already exist**; port them.

Health assertion (`backend/tests/test_main.py:22, 64-66`):

```python
HEALTH_KEYS = {"status", "market_source", "tickers_cached", "newest_price_age_seconds"}
...
health = httpx.get(f"{live_app}/api/health", timeout=10)
assert health.status_code == 200
assert set(health.json()) == HEALTH_KEYS
```

Bounded SSE read + same-origin static assertion (`backend/tests/test_main.py:68-82`) — the exact
three-part shape DOCK-03 needs, already written once:

```python
frames: list[str] = []
with httpx.stream("GET", f"{live_app}/api/stream/prices", timeout=10) as response:
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    for line in response.iter_lines():
        if line.strip():
            frames.append(line)
        if len(frames) >= 2:
            break
assert frames[0] == "retry: 1000"
assert any(frame.startswith("data: ") for frame in frames)

index = httpx.get(f"{live_app}/", timeout=10)
assert index.status_code == 200
assert index.headers["content-type"].startswith("text/html")
```

Note `frames[0] == "retry: 1000"` — a contract the container must also honor. The smoke check is
stdlib-only (`urllib`, not `httpx`), so translate the mechanics but keep the assertions identical.

Mount-order (API-not-shadowed) assertion (`backend/tests/test_main.py:124-146`) — including the
non-obvious Accept-gating behavior, which a smoke check written from scratch would get wrong:

```python
explicit_json = httpx.get(
    f"{live_app}/api/nope", headers={"Accept": "application/json"}, timeout=10
)
assert explicit_json.status_code == 404
assert explicit_json.headers["content-type"].startswith("application/json")

# Correct behavior, not a defect: the fallback is Accept-gated, and fetch()
# sends */*, so the frontend's own calls always land in the JSON rows above.
browser_navigation = httpx.get(
    f"{live_app}/api/nope", headers={"Accept": "text/html"}, timeout=10
)
assert browser_navigation.status_code == 200
```

Bounded-wait-for-readiness pattern (`backend/tests/test_main.py:21, 50-53`) — the deadline loop the
start scripts' readiness gate mirrors:

```python
STARTUP_TIMEOUT = 15.0
...
deadline = time.monotonic() + STARTUP_TIMEOUT
while not server.started:
    if time.monotonic() > deadline:
        raise RuntimeError("uvicorn did not start within %.0fs" % STARTUP_TIMEOUT)
    time.sleep(0.05)
```

---

### WAL stress logic (test harness, concurrent write) — D-16

**Analog:** `backend/tests/db/test_concurrency.py` — an exact-role match. Copy three things.

**1. The load-bearing-assertion doctrine** (`backend/tests/db/test_concurrency.py:1-12`). This
docstring is the standard D-16 must be held to; quote its last paragraph into the new test:

```python
"""Concurrent writes against one file database: no lock errors, no lost updates.

...Every database here is a real file under tmp_path. An in-memory database
cannot exercise WAL, busy_timeout or genuine lock contention...

The load-bearing assertion is not "no errors". A design that silently loses
updates raises nothing; what catches it is the final stored value equalling the
starting value plus the increment times the committed write count.
"""
```

**2. Tunables as module constants** (`test_concurrency.py:26-31`):

```python
WRITER_THREADS = 6
WRITES_PER_THREAD = 20
READER_THREADS = 3
READS_PER_THREAD = 20
INCREMENT = 1.0
HOLD_SECONDS = 0.3
```

**3. The writer/`_run`/final-value structure** (`test_concurrency.py:44-49, 60-90`):

```python
def _run(targets: list[threading.Thread]) -> None:
    """Start every thread and wait for all of them."""
    for thread in targets:
        thread.start()
    for thread in targets:
        thread.join()
...
def writer() -> None:
    for _ in range(WRITES_PER_THREAD):
        try:
            with connect(db_file) as conn:
                with writing(conn):
                    balance = get_profile(conn)["cash_balance"]
                    update_cash_balance(conn, balance + INCREMENT)
            commits.append(1)
        except BaseException as exc:
            errors.append(exc)
...
assert errors == []
assert len(commits) == WRITER_THREADS * WRITES_PER_THREAD
with connect(db_file) as conn:
    final = get_profile(conn)["cash_balance"]
assert final == STARTING_CASH + INCREMENT * len(commits)
```

**What the Phase 2 version adds that the analog lacks:** the journal-mode read-back. Phase 1's
`connect()` executes the pragma and discards the result (`backend/app/db/connection.py:62`), so a
silent downgrade is invisible. Assert it **first**, per RESEARCH.md line 640-648:

```python
mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
assert mode == "wal", f"WAL refused over the bind mount; mode is {mode!r}"
```

**What it must not copy:** this runs *inside the container against `/app/db/`*, not against
`tmp_path`, and against a scratch database (`/app/db/wal_stress.db`) — never `finally.db`.

---

### `Dockerfile` (config, build) — no in-repo analog

There is no Dockerfile in this repo. The stale `finally:latest` image on the daemon is an
**anti-analog**: it uses the flattened layout and `CMD ["uvicorn","app.main:app",...]`, which
cannot boot. Do not read patterns off it.

The three repo facts the Dockerfile must be written against, quoted exactly:

**Fact 1 — the `parents[2]` walk (D-05).** `backend/app/config.py:10-22`:

```python
# Walked up from this module rather than taken from the process CWD: the
# backend runs from backend/ locally and from /app in the container, and both
# must find the one .env that sits beside the repo root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")

_DB_PATH_ENV = os.environ.get("FINALLY_DB_PATH", "").strip()

# The repo-root db/, deliberately not backend/db/. That is the directory the
# Docker bind mount targets, and it is the tracked one; deriving the path
# relative to the package instead lands somewhere the mount never reaches.
DB_PATH: Path = Path(_DB_PATH_ENV) if _DB_PATH_ENV else PROJECT_ROOT / "db" / "finally.db"
```

Consequence: source lands at `/app/backend/`, `WORKDIR /app/backend`, `ENV FINALLY_DB_PATH=/app/db/finally.db`.

**Fact 2 — the factory and the static destination.** `backend/app/main.py:16-20` and `:47-55`:

```python
# Absolute, because app.frontend() resolves `directory` against the process
# CWD and its check_dir="auto" raises at app-creation time. A relative path
# therefore breaks the whole suite at collection depending on where the
# process was launched from, not just the one test that fetches the page.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
...
    app = FastAPI(title="FinAlly", lifespan=lifespan)
    ...
    app.include_router(create_health_router(cache, source))
    app.include_router(create_stream_router(cache))
    app.frontend("/", directory=STATIC_DIR, fallback="index.html")
    return app
```

`create_app()` is a factory with **no module-level `app`** (`main.py:23 — def create_app() -> FastAPI:`),
so `--factory` is mandatory. `STATIC_DIR` resolves to `/app/backend/static` under D-05 — that is
the `COPY --from=frontend` destination. Router-then-`frontend()` ordering is already correct in
code; the Dockerfile must not disturb it and the smoke check asserts it over HTTP.

**Fact 3 — no `RUN mkdir /app/db`.** The app already creates it. `backend/app/db/connection.py:106-115`:

```python
    resolved = Path(path).resolve()
    if resolved in _initialized:
        return

    with _init_lock:
        if resolved in _initialized:
            return

        resolved.parent.mkdir(parents=True, exist_ok=True)
        with connect(resolved) as conn:
```

**Fact 4 — the install inputs.** `backend/pyproject.toml:5, 6, 31-32`:

```toml
readme = "README.md"
requires-python = ">=3.12"
...
[tool.hatch.build.targets.wheel]
packages = ["app"]
```

`readme = "README.md"` means `backend/README.md` must **not** be `.dockerignore`d, and
`packages = ["app"]` means the project is genuinely installable, so the second
`uv sync --frozen --no-dev` after `COPY` is required (Pitfall 9).

**Comment convention for the Dockerfile specifically:** a Dockerfile has no docstrings, so the
"why" moves into `#` comments — the one place in this repo where inline comments carry weight.
Model them on the tone of the `config.py` and `connection.py` comments quoted above: state the
alternative that was rejected and why it breaks. One comment for D-05, one for `--factory`, one
for exec form.

---

### `scripts/start_mac.sh`, `scripts/stop_mac.sh` (host script) — no in-repo analog

First `.sh` files in the repo. No shell conventions exist to copy; the constraints are:

- **Line endings are already legislated.** `.gitattributes:7-12`:

```gitattributes
# Checked out with LF on every platform. A .sh or a Dockerfile checked out with
# CRLF fails on macOS and Linux with a bad interpreter error on the shebang
# line, which is the specific failure this rule exists to prevent.
*.sh text eol=lf
Dockerfile text eol=lf
*.dockerfile text eol=lf
```

  These files make the Phase 1 SETUP-03 `git ls-files --eol` check meaningful for the first time.
- **No emojis in any echoed string.** Applies to every `echo` line.
- **No defensive programming**: no speculative guards around `docker` calls. Explicit exit-code
  checks that the script's contract requires (D-09/D-12 idempotency) are contract, not defense.
- Structural templates for the anchored `docker ps -q --filter` detection, the image/build-time
  print, and the readiness poll are in RESEARCH.md lines 518-575 — those are the source, not
  anything in this repo.

### `scripts/start_windows.ps1`, `scripts/stop_windows.ps1` (host script) — no in-repo analog

First `.ps1` files. `.gitattributes:14-17`:

```gitattributes
# Checked out with CRLF, for the Windows PowerShell and batch entry points.
*.ps1 text eol=crlf
*.bat text eol=crlf
*.cmd text eol=crlf
```

Behavioral contract: **line-for-line mirror of the `.sh` pair** (D-09/D-12 require identical
behavior), targeting Windows PowerShell 5.1 — `Invoke-WebRequest -UseBasicParsing -TimeoutSec 2`
in `try/catch` (never bare `curl`), explicit `$LASTEXITCODE` checks after every `docker` call,
no ternary, no `??`. See RESEARCH.md Pitfalls 6 and 7.

### `.dockerignore` (config) — style analog only

The only in-repo analog is `.gitignore`'s commented-section style. `.gitignore:210-215`:

```gitignore
# SQLite WAL sidecars
#   PRAGMA journal_mode=WAL writes these beside the database. They are
#   per-run state, and OneDrive syncing them independently of the database
#   is a corruption vector. db/finally.db itself stays tracked.
db/*.db-wal
db/*.db-shm
```

Copy the header-comment-explaining-why form for each `.dockerignore` group, especially
`**/.venv` (257 MB, and it would shadow the container venv) and `.env` (must never reach a layer).

### `.gitignore` (append) — exact analog

Append the stress-database rule in exactly the block form shown above, directly below the existing
WAL sidecar block, with a comment stating that this is an ignore-rule *addition* and not an
untracking of `db/finally.db`:

```gitignore
db/wal_stress.db*
```

---

## Shared Patterns

### Python module preamble
**Source:** every module in `backend/app/` and `backend/market_data_demo.py`
**Apply to:** `scripts/smoke_check.py` and any sibling Python file

```python
"""One-line summary, then the why."""

from __future__ import annotations
```

`from __future__ import annotations` is the first import in every Python module in this repo
(`config.py:3`, `main.py:3`, `health.py:3`, `connection.py:14`, `market_data_demo.py:9`,
`tests/test_main.py:3`). Full type hints on every signature including private helpers
(`_free_port() -> int`, `_run(targets: list[threading.Thread]) -> None`). ruff:
`line-length = 100`, `target-version = "py312"`, `select = ["E","F","I","N","W"]`
(`backend/pyproject.toml:42-48`).

### Docstrings carry the why; comments are rare and specific
**Source:** `backend/app/db/connection.py:42-59`, `backend/app/main.py:16-19`
**Apply to:** `scripts/smoke_check.py`, the WAL stress logic

The house style is a docstring that names the rejected alternative and the failure it causes:

```python
    """Open a connection with WAL and a busy timeout, and close it on exit.

    isolation_level=None is mandatory, not stylistic. The stdlib default of ''
    is legacy implicit-transaction mode, in which an explicit BEGIN IMMEDIATE
    raises "cannot start a transaction within a transaction" once any statement
    has already opened one - and trivial single-statement tests still pass, so
    the defect hides.
    """
```

Note also: **plain ASCII hyphens, not em dashes, and no emojis** in docstrings and comments.

### Health-endpoint contract (the one both the start scripts and the smoke check consume)
**Source:** `backend/app/api/health.py:32-38`
**Apply to:** readiness gate in all four scripts; smoke check assertions

```python
        newest = price_cache.newest_timestamp()
        return {
            "status": "ok",
            "market_source": source.source_name,
            "tickers_cached": len(price_cache),
            "newest_price_age_seconds": None if newest is None else round(time.time() - newest, 3),
        }
```

Four keys, no more. `newest_price_age_seconds` is `None` until the first price arrives — a
readiness gate that requires it to be a number will hang on a cold start; gate on
`status_code == 200` and read the age only as reported detail.

### Named-constant tunables instead of magic numbers
**Source:** `backend/tests/test_main.py:21` (`STARTUP_TIMEOUT = 15.0`),
`backend/tests/db/test_concurrency.py:26-31`, `backend/app/db/connection.py:31` (`BUSY_TIMEOUT_MS = 5000`)
**Apply to:** the readiness timeout, the SSE line bound, and every WAL stress dimension.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `Dockerfile` | config | build | No Dockerfile in the repo. The stale `finally:latest` image is an anti-analog (flattened layout, non-bootable CMD). Use RESEARCH.md's skeleton (lines 466-512) plus the four repo facts quoted above |
| `.dockerignore` | config | build-context filter | None; `.gitignore` supplies comment style only. Scope from RESEARCH.md Pitfall 1 |
| `scripts/start_mac.sh` | script | lifecycle | First `.sh` in the repo |
| `scripts/stop_mac.sh` | script | lifecycle | First `.sh` in the repo |
| `scripts/start_windows.ps1` | script | lifecycle | First `.ps1` in the repo; PowerShell 5.1 floor |
| `scripts/stop_windows.ps1` | script | lifecycle | First `.ps1` in the repo |

For all six, RESEARCH.md's Code Examples section is the pattern source and it is explicitly
version-verified; the planner should cite it by line range rather than paraphrasing.

## Metadata

**Analog search scope:** repo root, `backend/app/`, `backend/app/api/`, `backend/app/db/`,
`backend/tests/`, `backend/market_data_demo.py`, `scripts/`, `backend/static/`, `.gitattributes`,
`.gitignore`, `backend/pyproject.toml` — all read live this session, not from `.planning/codebase/*.md`
(which is dated 2026-08-04 and stale).
**Files scanned:** 12 read in full; `git ls-files` used to confirm `scripts/` is empty and
`backend/static/index.html` is the only tracked static file.
**Pattern extraction date:** 2026-08-10
