# FinAlly - one image, one port.
#
# Stage 1 builds the Next.js static export. Stage 2 installs the Python
# dependencies and copies that export to backend/app/static, which is the
# directory app/main.py mounts (and mounts only if it exists).

# ---------------------------------------------------------------------------
# Stage 1 - Next.js static export
# ---------------------------------------------------------------------------
FROM node:22-slim AS frontend

WORKDIR /frontend

# Manifests first: a source-only change reuses the installed node_modules layer.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2 - FastAPI serving the API, the SSE stream and the static export
# ---------------------------------------------------------------------------
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    FINALLY_DB_PATH=/app/db/finally.db

WORKDIR /app

# Dependencies before source, for the same layer-caching reason as stage 1.
# --frozen installs exactly what uv.lock pins and never re-resolves.
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./

# main.py resolves its static directory as Path(__file__).parent / "static",
# so the export has to land at /app/app/static and nowhere else.
COPY --from=frontend /frontend/out ./app/static

# Exists so the image also runs without the bind mount; normally /app/db is
# the mounted host directory and the database file lives there.
RUN mkdir -p /app/db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
