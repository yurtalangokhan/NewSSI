"""API routes - FastAPI route modules."""

from api.routes.AgentsRoute import router as agents_router
from api.routes.AssistantsRoute import router as assistants_router
from api.routes.ThreadsRoute import router as threads_router
from api.routes.AuthRoute import router as auth_router
from api.routes.ScheduleRoute import router as schedule_router
from api.routes.IngestRoute import router as ingest_router
from api.routes.ProxyRoute import router as proxy_router
from api.routes.RunRoute import router as run_router
from api.routes.DatasourcesRoute import router as datasources_router
from api.routes.AssistantSchemasRoute import router as assistant_schemas_router

__all__ = [
    "agents_router",
    "assistants_router",
    "threads_router",
    "auth_router",
    "schedule_router",
    "ingest_router",
    "proxy_router",
    "run_router",
    "datasources_router",
    "assistant_schemas_router",
]
