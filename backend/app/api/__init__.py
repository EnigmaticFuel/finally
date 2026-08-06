"""HTTP routers for the FinAlly API.

Public API:
    create_health_router - FastAPI router factory for GET /api/health
"""

from .health import create_health_router

__all__ = [
    "create_health_router",
]
