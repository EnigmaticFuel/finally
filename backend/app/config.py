"""Configuration constants, loaded from the project-root .env at import."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

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

OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "").strip()
MASSIVE_API_KEY: str = os.environ.get("MASSIVE_API_KEY", "").strip()
LLM_MOCK: bool = os.environ.get("LLM_MOCK", "").strip().lower() == "true"
