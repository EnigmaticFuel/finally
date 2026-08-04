#!/usr/bin/env bash
#
# Start FinAlly (macOS / Linux).
#
#   ./scripts/start_mac.sh              start, building the image if it is absent
#   ./scripts/start_mac.sh --build      force a rebuild first
#   ./scripts/start_mac.sh --no-browser do not open a browser
#
# Idempotent: any existing FinAlly container is replaced. The database lives in
# the bind-mounted db/ directory on the host, so nothing here loses data.

set -euo pipefail

IMAGE="finally"
CONTAINER="finally"
PORT="8000"
URL="http://localhost:${PORT}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FORCE_BUILD=false
OPEN_BROWSER=true
for arg in "$@"; do
  case "$arg" in
    --build) FORCE_BUILD=true ;;
    --no-browser) OPEN_BROWSER=false ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop and try again." >&2
  exit 1
fi

# A fresh clone has no .env; create one so there is no manual first step.
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add your API keys there if you have them."
fi

mkdir -p db

if [ "$FORCE_BUILD" = true ] || [ -z "$(docker images -q "$IMAGE" 2>/dev/null)" ]; then
  echo "Building image ${IMAGE}..."
  docker build -t "$IMAGE" .
fi

if [ -n "$(docker ps -aq -f "name=^${CONTAINER}$")" ]; then
  echo "Removing existing container ${CONTAINER}..."
  docker rm -f "$CONTAINER" >/dev/null
fi

echo "Starting ${CONTAINER}..."
docker run -d \
  --name "$CONTAINER" \
  -p "${PORT}:8000" \
  --env-file .env \
  -v "$ROOT/db:/app/db" \
  "$IMAGE" >/dev/null

printf "Waiting for the app"
for _ in $(seq 1 60); do
  if curl -fsS "${URL}/api/health" >/dev/null 2>&1; then
    echo
    echo "FinAlly is running at ${URL}"
    echo "Database: ${ROOT}/db/finally.db"
    echo "Stop it with ./scripts/stop_mac.sh"
    if [ "$OPEN_BROWSER" = true ] && command -v open >/dev/null 2>&1; then
      open "$URL"
    fi
    exit 0
  fi
  printf "."
  sleep 1
done

echo
echo "The app did not become healthy within 60 seconds. Recent logs:" >&2
docker logs --tail 40 "$CONTAINER" >&2
exit 1
