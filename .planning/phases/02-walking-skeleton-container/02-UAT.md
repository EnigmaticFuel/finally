---
status: partial
phase: 02-walking-skeleton-container
source: [02-VERIFICATION.md]
started: 2026-08-11T17:20:00Z
updated: 2026-08-11T17:55:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Native POSIX run of the `.sh` pair (A-05)
expected: On a macOS or Linux host with Docker, from a clean state run `bash scripts/start_mac.sh`, then `docker inspect finally-app --format '{{(index .Mounts 0).Source}}'`, open the printed URL, then run `bash scripts/stop_mac.sh` twice. Exit 0 throughout; mount Source is the repo's own `db/`; the page renders; the second stop reports nothing to stop. The uid/gid behaviour D-06's root-user rationale turns on is POSIX-specific, so Windows cannot stand in for it.
result: blocked
blocked_by: other
reason: "No native macOS or Linux host available. This machine is Windows 11 and Docker Desktop's WSL integration is disabled for the installed Ubuntu distro. The .sh bind-mount branch remains unexecuted on any host; assumption A-05 stands until a POSIX operator runs it."

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
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 1

## Gaps
