---
status: complete
phase: 02-walking-skeleton-container
source: [02-VERIFICATION.md]
started: 2026-08-11T17:20:00Z
updated: 2026-08-12T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Native POSIX run of the `.sh` pair (A-05)
expected: On a macOS or Linux host with Docker, from a clean state run `bash scripts/start_mac.sh`, then `docker inspect finally-app --format '{{(index .Mounts 0).Source}}'`, open the printed URL, then run `bash scripts/stop_mac.sh` twice. Exit 0 throughout; mount Source is the repo's own `db/`; the page renders; the second stop reports nothing to stop. The uid/gid behaviour D-06's root-user rationale turns on is POSIX-specific, so Windows cannot stand in for it.
result: pass
reason: "Executed 2026-08-12 on Ubuntu WSL2 (kernel 6.18.33.2-microsoft-standard-WSL2, ext4 root) after the operator enabled Docker Desktop's WSL integration for the distro. Run from a fresh `git clone` at ~/finally on ext4 - deliberately NOT /mnt/c, whose drvfs fakes ownership and would not exercise the uid/gid semantics this test exists for. Scripts arrived from the clone at mode 100755 with LF endings and `bash -n` clean. `bash scripts/start_mac.sh` exited 0, printing image, build timestamp and URL; `docker inspect finally-app --format '{{(index .Mounts 0).Source}}'` returned /home/ehasin/finally/db, the clone's own db/. /api/health returned 200 with market_source=simulator and tickers_cached=10, / returned 200, and /api/stream/prices emitted `retry: 1000` plus one all-ticker event carrying open_price and change_from_open_percent. Operator confirmed the D-11 placeholder page renders in a browser. `bash scripts/stop_mac.sh` exited 0 reporting 'Stopped and removed container finally-app.', and a second run exited 0 reporting 'No container named finally-app exists. Nothing to stop.' - idempotence proven. D-06's root-user rationale verified directly: the container runs uid=0(root) while db/finally.db is uid/gid 1000, and a root-written scratch WAL database appeared on the ext4 host side as uid/gid 0 alongside it. Two distinct owners in one directory is unfakeable by drvfs, confirming genuine POSIX ownership passthrough, and `pragma journal_mode=wal` negotiated successfully over the bind mount. Scratch files and the clone (which held a copy of .env) were removed afterwards. Caveat recorded: start_mac.sh reused the pre-existing finally-app:latest image built on Windows 2026-08-11, since it builds only when the image is missing or --build is passed, so the Dockerfile build itself has not been exercised on Linux - the run path has."

### 2. One command reaches a working terminal (coverage D5 / D6)
expected: Run `scripts/start_windows.ps1` from a clean state and judge the output as a first-time operator would. Three lines naming the image and its build time, then `http://localhost:8000`; no browser opens automatically; the page actually renders in a browser you open yourself.
result: pass

### 3. Is the image-staleness print legible? (T-2-05)
expected: Build the image, edit a file under `backend/app/`, run start again WITHOUT `--build`, then revert the edit. The printed build timestamp makes the staleness obvious at a glance. A print that is technically present but visually buried has failed.
result: pass

### 4. `.env` changes do not reach a running container (backstop truth)
expected: With the container running, change a value in the root `.env`, then run `docker exec finally-app printenv <KEY>`. The container still reports the OLD value, because `docker run --env-file` snapshots the environment at creation time and a config change requires stop + start.
result: pass

## Summary

total: 4
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
