# syntax=docker/dockerfile:1

# --- Stage 1: frontend ---
# Phase 2 has no Next.js project yet, so this stage passes the committed
# placeholder through as build output. It is a real stage rather than a
# formality because Phase 7 replaces only the two lines below with
# `COPY frontend/ .` and `RUN npm ci && npm run build`; the stage name, the
# output path /build/out and the COPY --from in stage 2 all survive unchanged.
FROM node:24-trixie-slim AS frontend
WORKDIR /build
COPY backend/static/ ./src/
RUN mkdir -p /build/out && cp -r /build/src/. /build/out/

# --- Stage 2: runtime ---
FROM python:3.12-slim-trixie

# uv's own documented install-into-image method. Copying the binary from the
# published image avoids a network install step during the build.
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/backend/.venv/bin:$PATH" \
    FINALLY_DB_PATH=/app/db/finally.db

# The image mirrors the repository. Flattening backend/ onto /app is the
# conventional Docker layout and it silently repoints config.py's
# PROJECT_ROOT = parents[2] from /app to /, so load_dotenv would look for
# /.env. That is harmless today only because --env-file populates the
# environment before Python starts, and it would be wrong for any later code
# that assumes PROJECT_ROOT is the repo root.
WORKDIR /app/backend

# Dependency-only layer, so editing backend source does not reinstall the world.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=backend/uv.lock,target=uv.lock \
    --mount=type=bind,source=backend/pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

COPY backend/ /app/backend/
COPY --from=frontend /build/out/ /app/backend/static/

# The second sync installs the project itself. pyproject.toml declares
# packages = ["app"], so app is a real installable package; without this it is
# importable only by accident of the working directory.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8000

# --factory: main.py exposes create_app() and no module-level app, so the
#   conventional `app.main:app` target errors at load.
# Exec form: uvicorn stays PID 1 and receives SIGTERM from `docker stop`. Under
#   the shell form it never does, turning a 0.2s shutdown into a 10s SIGKILL
#   and skipping the lifespan teardown that stops the market data source.
# --workers 1: redundant to uvicorn's default, and that is the point. One
#   worker means one PriceCache, and the guarantee has to be readable from
#   `docker inspect` rather than inferred from an omitted flag.
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
