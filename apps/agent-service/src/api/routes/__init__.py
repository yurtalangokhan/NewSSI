"""API routes - FastAPI route modules."""

from api.routes.admin_mcp_route import router as admin_mcp_router
from api.routes.agent_definitions_route import router as agent_definitions_router
from api.routes.agent_tools_route import router as agent_tools_router
from api.routes.agents_route import router as agents_router
from api.routes.assistant_schemas_route import router as assistant_schemas_router
from api.routes.assistants_route import router as assistants_router
from api.routes.authored_documents_route import router as authored_documents_router
from api.routes.chat_route import router as chat_router
from api.routes.connector_tools_route import router as connector_tools_router
from api.routes.datasources_route import router as datasources_router
from api.routes.file_route import router as file_router
from api.routes.flow_components_route import router as flow_components_router
from api.routes.flow_playground_route import router as flow_playground_router
from api.routes.flow_versions_route import router as flow_versions_router
from api.routes.ingest_route import router as ingest_router
from api.routes.mail_configs_route import router as mail_configs_router
from api.routes.mcp_oauth_callback_route import router as mcp_oauth_callback_router
from api.routes.mcp_providers_route import router as mcp_providers_router
from api.routes.mcp_server_admin_route import router as mcp_server_admin_router
from api.routes.mcp_tools_route import router as mcp_tools_router
from api.routes.ollama_route import router as ollama_router
from api.routes.persona_route import router as persona_router
from api.routes.provider_route import router as provider_router
from api.routes.proxy_route import router as proxy_router
from api.routes.run_route import router as run_router
from api.routes.schedule_route import router as schedule_router
from api.routes.threads_route import router as threads_router
from api.routes.user_route import router as user_router
from api.routes.web_search_route import router as web_search_router

__all__ = [
    "admin_mcp_router",
    "agent_definitions_router",
    "agent_tools_router",
    "agents_router",
    "assistant_schemas_router",
    "assistants_router",
    "authored_documents_router",
    "chat_router",
    "connector_tools_router",
    "datasources_router",
    "file_router",
    "flow_components_router",
    "flow_playground_router",
    "flow_versions_router",
    "ingest_router",
    "mail_configs_router",
    "mcp_oauth_callback_router",
    "mcp_providers_router",
    "mcp_server_admin_router",
    "mcp_tools_router",
    "ollama_router",
    "persona_router",
    "provider_router",
    "proxy_router",
    "run_router",
    "schedule_router",
    "threads_router",
    "user_router",
    "web_search_router",
]
