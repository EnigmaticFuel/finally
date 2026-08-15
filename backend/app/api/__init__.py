"""HTTP routers for the FinAlly API.

Public API:
    create_health_router - FastAPI router factory for GET /api/health
    create_portfolio_router - FastAPI router factory for the /api/portfolio routes
    create_watchlist_router - FastAPI router factory for the /api/watchlist routes
    register_exception_handlers - Map the service error taxonomy onto status codes
"""

from __future__ import annotations

from .errors import register_exception_handlers
from .health import create_health_router
from .portfolio import create_portfolio_router
from .watchlist import create_watchlist_router

__all__ = [
    "create_health_router",
    "create_portfolio_router",
    "create_watchlist_router",
    "register_exception_handlers",
]
