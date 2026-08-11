#!/usr/bin/env bash
#
# Start the FinAlly container on macOS or Linux.
#
# Builds finally-app:latest when it is missing or when --build is passed, prints
# the image tag and the timestamp that image was built, runs one container, waits
# for GET /api/health to return 200, then prints the URL.
#
# Running this twice is safe. A second run reports that the container is already
# running and exits 0 without stopping, restarting or recreating anything, so the
# SSE stream and every ticker's session open price survive.
#
# The image tag and build timestamp are printed on every run, not only after a
# build. Build-if-missing has one real failure mode - edit backend code, forget
# --build, wonder why nothing changed - and a visible build timestamp is the
# whole mitigation for it.
#
# Usage: scripts/start_mac.sh [--build]

set -euo pipefail

IMAGE=finally-app:latest
CONTAINER=finally-app
URL=http://localhost:8000
READY_TIMEOUT_SECONDS=60

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

BUILD=0
if [ "${1:-}" = "--build" ]; then
  BUILD=1
fi

# Anchored filter plus -q: the emptiness of the output is the test. `docker ps`
# is never piped through grep, because the name filter is a substring match and
# an unanchored one would also match a container called finally-app-check.
running=$(docker ps -q --filter "name=^${CONTAINER}$" --filter status=running)
if [ -n "$running" ]; then
  echo "Container ${CONTAINER} is already running."
  echo "${URL}"
  exit 0
fi

present=$(docker ps -a -q --filter "name=^${CONTAINER}$")
if [ -n "$present" ]; then
  docker rm "${CONTAINER}" >/dev/null
fi

if [ -z "$(docker images -q "${IMAGE}")" ] || [ "$BUILD" = "1" ]; then
  docker build -t "${IMAGE}" "${REPO_ROOT}"
fi

echo "Image:      ${IMAGE}"
echo "Built:      $(docker image inspect "${IMAGE}" --format '{{.Created}}')"

if ! docker run -d \
  --name "${CONTAINER}" \
  -p 127.0.0.1:8000:8000 \
  -v "${REPO_ROOT}/db:/app/db" \
  --env-file "${REPO_ROOT}/.env" \
  "${IMAGE}" >/dev/null; then
  echo "Failed to start ${CONTAINER}. If port 8000 is already in use, run scripts/stop_mac.sh and try again."
  exit 1
fi

# Gate on the status code alone. newest_price_age_seconds is null until the
# first price arrives, so a gate that waited for it would hang on a cold start.
deadline=$(( $(date +%s) + READY_TIMEOUT_SECONDS ))
until [ "$(curl -s -o /dev/null -w '%{http_code}' "${URL}/api/health")" = "200" ]; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "Timed out after ${READY_TIMEOUT_SECONDS}s waiting for ${URL}/api/health"
    docker logs --tail 40 "${CONTAINER}"
    exit 1
  fi
  sleep 1
done

echo "${URL}"
