#!/usr/bin/env bash
#
# Stop FinAlly (macOS / Linux).
#
# Stops and removes the container. It never touches db/, so the portfolio,
# watchlist and chat history survive. Delete db/finally.db yourself to reset.
#
# Idempotent: doing nothing is a success when nothing is running.

set -euo pipefail

CONTAINER="finally"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running, so neither is FinAlly."
  exit 0
fi

if [ -z "$(docker ps -aq -f "name=^${CONTAINER}$")" ]; then
  echo "FinAlly is not running."
  exit 0
fi

docker rm -f "$CONTAINER" >/dev/null
echo "Stopped and removed ${CONTAINER}. The database in db/ is untouched."
