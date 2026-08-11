# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""The one command that proves the walking skeleton, against a real container.

Run with:  uv run scripts/smoke_check.py [--build]

Every ROADMAP Phase 2 success criterion has at least one named check here, so
"the walking skeleton works" is a claim anyone can re-check rather than a claim
that was true once on one machine.

The container is driven through the platform's own start and stop scripts
rather than through docker run. Those scripts already refuse to return until
GET /api/health has answered 200, so this script inherits that readiness gate
instead of writing a third one, and a regression in either script fails the
smoke check rather than hiding behind a duplicated timer.

The assertion set is ported from backend/tests/test_main.py rather than
re-derived, because that suite already pins the non-obvious case: an unknown
/api/ path returns 200 for a text/html client. That is the SPA fallback being
Accept-gated and it is correct - a check written from scratch would report it
as a bug.

Stdlib only, for two reasons. The script lives outside the backend uv project
so it cannot reach the backend's dev dependencies, and urllib reads N lines
from the SSE stream and closes, which sidesteps curl -N --max-time exiting 28
on precisely the timeout it was told to hit.

These assertions deliberately do not live in backend/tests/. Folding them in
would put a Docker daemon dependency inside a suite that runs in seconds
without one, and every future phase would pay that on every test run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
STATIC_INDEX = REPO_ROOT / "backend" / "static" / "index.html"
DB_FILE = REPO_ROOT / "db" / "finally.db"
ENV_FILE = REPO_ROOT / ".env"

IMAGE = "finally-app:latest"
CONTAINER = "finally-app"
# Anchored, so the filter cannot also match a container called finally-app-check.
NAME_FILTER = "name=^finally-app$"
APP_FACTORY = "app.main:create_app"

# The container publishes on IPv4 loopback only, and localhost resolves to ::1
# first on a dual-stack host - measured at 2231ms against 145ms. Poll the
# address that exists; the user is still told http://localhost:8000.
BASE_URL = "http://127.0.0.1:8000"
STREAM_PATH = "/api/stream/prices"
HTTP_TIMEOUT_SECONDS = 10
SSE_TIMEOUT_SECONDS = 20
# A hard bound rather than an unbounded loop: the stream never ends on its own,
# so a reader without a ceiling hangs the whole smoke check.
SSE_MAX_LINES = 40

HEALTH_KEYS = {"status", "market_source", "tickers_cached", "newest_price_age_seconds"}

PROFILE_QUERY = "select created_at, cash_balance from users_profile where id = 'default'"
WATCHLIST_QUERY = "select count(*) from watchlist"

# Executed by `docker exec ... python -c`, so the container reads its own
# database through its own app.config.DB_PATH rather than a path this script
# guessed at.
CONTAINER_READ_SOURCE = "\n".join(
    [
        "import sqlite3",
        "from app.config import DB_PATH",
        "connection = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)",
        f'row = connection.execute("{PROFILE_QUERY}").fetchone()',
        f'count = connection.execute("{WATCHLIST_QUERY}").fetchone()[0]',
        "print(row[0])",
        "print(row[1])",
        "print(count)",
    ]
)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command and capture both streams as text."""
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _docker(*args: str) -> str:
    """Run one docker command and return its stdout, raising on a non-zero exit."""
    result = _run(["docker", *args])
    if result.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} exited {result.returncode}: {result.stderr}")
    return result.stdout.strip()


def _platform_command(bash_script: str, powershell_script: str) -> list[str]:
    """Select the platform's own lifecycle script and build its invocation."""
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-File", str(SCRIPTS_DIR / powershell_script)]
    return ["bash", str(SCRIPTS_DIR / bash_script)]


def _container_ids(all_states: bool = True) -> list[str]:
    """Ids of containers named exactly finally-app, running or in any state."""
    args = ["ps", "-a", "-q", "--filter", NAME_FILTER]
    if not all_states:
        args = ["ps", "-q", "--filter", NAME_FILTER, "--filter", "status=running"]
    return _docker(*args).split()


def _get(path: str, accept: str | None = None) -> tuple[int, str, bytes]:
    """Fetch one URL and return its status, content type and body.

    HTTPError is caught because a 404 is an expected outcome here rather than a
    failure: urllib raises on every non-2xx, so the mount-order check could not
    observe the status it exists to assert without this.
    """
    request = urllib.request.Request(BASE_URL + path)
    if accept is not None:
        request.add_header("Accept", accept)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return response.status, response.headers.get("content-type", ""), response.read()
    except urllib.error.HTTPError as error:
        with error:
            return error.status, error.headers.get("content-type", ""), error.read()


def _read_env_keys() -> dict[str, str]:
    """Parse the root .env into key and value pairs, skipping comments and blanks.

    Values are returned so the comparison can happen in memory. Nothing that
    touches them prints them on any path, including the failure path: a
    verification script that echoes a credential into a terminal or a CI log
    has leaked it, and a mismatch is diagnosable from the key name alone.
    """
    pairs: dict[str, str] = {}
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        pairs[key.strip()] = value.strip()
    return pairs


def start_container(build: bool = False) -> None:
    """Start the container through the platform's own start script.

    Its stdout is printed rather than swallowed because it names the image tag
    and the timestamp that image was built. That is what stops a green run from
    certifying a stale build.
    """
    command = _platform_command("start_mac.sh", "start_windows.ps1")
    if build:
        command.append("--build")
    result = _run(command)
    for line in result.stdout.splitlines():
        print(f"  start: {line}")
    if result.returncode != 0:
        raise RuntimeError(f"start script exited {result.returncode}: {result.stderr.strip()}")


def stop_container() -> None:
    """Stop and remove the container through the platform's own stop script."""
    command = _platform_command("stop_mac.sh", "stop_windows.ps1")
    result = _run(command)
    for line in result.stdout.splitlines():
        print(f"  stop: {line}")
    if result.returncode != 0:
        raise RuntimeError(f"stop script exited {result.returncode}: {result.stderr.strip()}")


def check_health() -> None:
    """GET /api/health answers JSON with exactly the four documented keys.

    newest_price_age_seconds is deliberately not asserted to be a number: it is
    null until the first price arrives, so a check that required one would fail
    on a cold container that is behaving correctly.
    """
    status, content_type, body = _get("/api/health")
    if status != 200:
        raise RuntimeError(f"expected 200, got {status}")
    if not content_type.startswith("application/json"):
        raise RuntimeError(f"expected application/json, got {content_type!r}")
    keys = set(json.loads(body))
    if keys != HEALTH_KEYS:
        raise RuntimeError(f"expected keys {sorted(HEALTH_KEYS)}, got {sorted(keys)}")


def check_static_page() -> None:
    """GET / serves the committed placeholder page byte for byte.

    The equality is D-02's contract made checkable - the container and a local
    uvicorn serve the same page because both resolve to the same committed
    file - and it simultaneously proves the Node stage's output reached the
    image through COPY --from=frontend.
    """
    status, content_type, body = _get("/")
    if status != 200:
        raise RuntimeError(f"expected 200, got {status}")
    if not content_type.startswith("text/html"):
        raise RuntimeError(f"expected text/html, got {content_type!r}")
    expected = STATIC_INDEX.read_bytes()
    if body != expected:
        raise RuntimeError(f"expected {len(expected)} bytes of {STATIC_INDEX.name}, got {len(body)}")


def check_api_not_shadowed() -> None:
    """An unknown /api/ path stays JSON for JSON clients, whatever is mounted at /.

    This is the highest-risk property in the architecture: a static mount
    registered before the routers would shadow every /api/ route and 404 the
    whole API while the page still looked fine.

    The text/html row returning 200 is correct behaviour and not a defect. The
    SPA fallback is Accept-gated, fetch() sends */*, so the frontend's own calls
    always land in the JSON rows above, and a browser navigating to an unknown
    path correctly gets the app shell. Do not "fix" it.
    """
    for accept in ("application/json", "*/*"):
        status, content_type, _ = _get("/api/nope", accept)
        if status != 404:
            raise RuntimeError(f"Accept {accept}: expected 404, got {status}")
        if not content_type.startswith("application/json"):
            raise RuntimeError(f"Accept {accept}: expected application/json, got {content_type!r}")

    status, content_type, _ = _get("/api/nope", "text/html")
    if status != 200:
        raise RuntimeError(f"Accept text/html: expected 200 from the SPA fallback, got {status}")
    if not content_type.startswith("text/html"):
        raise RuntimeError(f"Accept text/html: expected text/html, got {content_type!r}")


def check_sse_stream() -> None:
    """GET /api/stream/prices opens with retry: 1000 and delivers a data frame."""
    request = urllib.request.Request(BASE_URL + STREAM_PATH)
    frames: list[str] = []
    with urllib.request.urlopen(request, timeout=SSE_TIMEOUT_SECONDS) as response:
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("text/event-stream"):
            raise RuntimeError(f"expected text/event-stream, got {content_type!r}")
        for _ in range(SSE_MAX_LINES):
            line = response.readline().decode("utf-8").strip()
            if line:
                frames.append(line)
            if len(frames) >= 2:
                break

    if not frames:
        raise RuntimeError(f"expected frames within {SSE_MAX_LINES} lines, got none")
    if frames[0] != "retry: 1000":
        raise RuntimeError(f"expected first frame 'retry: 1000', got {frames[0]!r}")
    if not any(frame.startswith("data: ") for frame in frames):
        raise RuntimeError(f"expected a 'data: ' frame, got {len(frames)} frames without one")


def check_single_worker() -> None:
    """One uvicorn worker, asserted from the image's intent and the running fact.

    Both halves are needed. The Config.Cmd half proves what the image asks for;
    only the docker top half would catch a supervisor or a reload watcher
    introduced by a future base-image change.
    """
    command = json.loads(_docker("inspect", CONTAINER, "--format", "{{json .Config.Cmd}}"))
    if "--workers" not in command:
        raise RuntimeError(f"expected --workers in Config.Cmd, got {command}")
    worker_count = command[command.index("--workers") + 1]
    if worker_count != "1":
        raise RuntimeError(f"expected --workers 1, got --workers {worker_count}")

    lines = [line for line in _docker("top", CONTAINER).splitlines() if APP_FACTORY in line]
    if len(lines) != 1:
        raise RuntimeError(f"expected 1 process matching {APP_FACTORY}, got {len(lines)}")


def check_env_delivered() -> None:
    """Every root .env key reaches the container, and no .env reached a layer.

    Values are compared here and never printed, on the failure path as much as
    the happy one.
    """
    for key, host_value in _read_env_keys().items():
        result = _run(["docker", "exec", CONTAINER, "printenv", key])
        if result.returncode != 0:
            raise RuntimeError(f"{key} is absent from the container environment")
        if result.stdout.strip() != host_value:
            raise RuntimeError(f"{key} differs between the host .env and the container")

    baked = _run(["docker", "run", "--rm", "--entrypoint", "sh", IMAGE, "-c", "test ! -f /app/.env"])
    if baked.returncode != 0:
        raise RuntimeError("expected no /app/.env in the image, found one")


CHECK_ORDER = (
    check_health,
    check_static_page,
    check_api_not_shadowed,
    check_sse_stream,
    check_single_worker,
    check_env_delivered,
)


def main() -> int:
    """Run every check in a fixed order and print one summary line.

    The broad except is the report: a run that aborted on the first failure
    would name one problem and hide the rest, and the point of a smoke check is
    to say how much of the skeleton is standing.
    """
    parser = argparse.ArgumentParser(description="Prove the walking skeleton against a container.")
    parser.add_argument("--build", action="store_true", help="rebuild the image before starting")
    args = parser.parse_args()

    start_container(args.build)

    passed = 0
    failed = 0
    for check in CHECK_ORDER:
        try:
            check()
        except Exception as error:
            failed += 1
            print(f"FAIL {check.__name__}: {error}")
        else:
            passed += 1
            print(f"PASS {check.__name__}")

    stop_container()
    print(f"{len(CHECK_ORDER)} checks, {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
