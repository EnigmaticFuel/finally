#!/usr/bin/env bash
#
# Stop the FinAlly container on macOS or Linux.
#
# Stops and removes the container, and does nothing else. It never deletes,
# moves, truncates or writes to the bind-mounted database directory - a stop
# that reset the user's portfolio is the failure this script exists to make
# impossible, so no path under that directory appears anywhere below.
#
# Running this twice is safe. A second run reports that there is nothing to stop
# and exits 0, which is what keeps stop-then-start a safe pattern.
#
# Usage: scripts/stop_mac.sh

set -euo pipefail

CONTAINER=finally-app

present=$(docker ps -a -q --filter "name=^${CONTAINER}$")
if [ -z "$present" ]; then
  echo "No container named ${CONTAINER} exists. Nothing to stop."
  exit 0
fi

docker stop "${CONTAINER}" >/dev/null
docker rm "${CONTAINER}" >/dev/null
echo "Stopped and removed container ${CONTAINER}."
