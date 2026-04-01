"""API routes - FastAPI route modules."""

from api.routes.agents import router as agents_router
from api.routes.assistants import router as assistants_router
from api.routes.threads import router as threads_router

__all__ = [
    "agents_router",
    "assistants_router",
    "threads_router",
]
