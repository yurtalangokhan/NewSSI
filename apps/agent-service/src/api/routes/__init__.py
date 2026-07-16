"""API routes - FastAPI route modules."""

from api.routes.AgentDefinitionsRoute import router as agent_definitions_router
from api.routes.AgentGroupsRoute import router as agent_groups_router
from api.routes.AgentsRoute import router as agents_router
from api.routes.AgentToolsRoute import router as agent_tools_router
from api.routes.AssistantSchemasRoute import router as assistant_schemas_router
from api.routes.AssistantsRoute import router as assistants_router
from api.routes.AuthRoute import router as auth_router
from api.routes.ChatRoute import router as chat_router
from api.routes.DatasourcesRoute import router as datasources_router
from api.routes.FileRoute import router as file_router
from api.routes.IngestRoute import router as ingest_router
from api.routes.MCPProvidersRoute import router as mcp_providers_router
from api.routes.MCPToolsRoute import router as mcp_tools_router
from api.routes.PersonaRoute import router as persona_router
from api.routes.ProviderRoute import router as provider_router
from api.routes.ProxyRoute import router as proxy_router
from api.routes.RunRoute import router as run_router
from api.routes.ScheduleRoute import router as schedule_router
from api.routes.ThreadsRoute import router as threads_router
from api.routes.UserRoute import router as user_router
from api.routes.WebSearchRoute import router as web_search_router

__all__ = [
    "agents_router",
    "assistants_router",
    "threads_router",
    "auth_router",
    "chat_router",
    "persona_router",
    "user_router",
    "schedule_router",
    "ingest_router",
    "proxy_router",
    "run_router",
    "datasources_router",
    "assistant_schemas_router",
    "file_router",
    "agent_definitions_router",
    "agent_groups_router",
    "agent_tools_router",
    "mcp_providers_router",
    "mcp_tools_router",
    "web_search_router",
    "provider_router",
]
