from typing import Any

from idempotency import (
    IdempotencyConfig,
    IdempotencyMode,
    IdempotencyPolicy,
    IdempotencyPolicyConfig,
)

from core.api_versioning import API_PREFIX
from core.idempotency_principal import extract_principal_from_jwt


def build_idempotency_config(settings: Any) -> IdempotencyConfig:
    return IdempotencyConfig(
        redis_host=settings.REDIS_HOST,
        redis_port=settings.REDIS_PORT,
        redis_db=settings.REDIS_DB,
        redis_password=settings.REDIS_PASSWORD,
        idempotency_ttl=settings.IDEMPOTENCY_TTL,
        idempotency_enabled=settings.IDEMPOTENCY_ENABLED,
        service_name="agent-service",
        enforce_required_keys=getattr(settings, "IDEMPOTENCY_ENFORCE_REQUIRED_KEYS", False),
        lock_ttl=getattr(settings, "IDEMPOTENCY_LOCK_TTL", 10),
        wait_timeout=getattr(settings, "IDEMPOTENCY_WAIT_TIMEOUT", 10.0),
        principal_extractor=extract_principal_from_jwt,
        policy=build_idempotency_policy(),
    )


def build_idempotency_exclude_paths(api_prefix: str = API_PREFIX) -> set[str]:
    return {
        f"{api_prefix}/health",
        f"{api_prefix}/health/ready",
        "/internal/connector-tools/resolve",
        f"{api_prefix}/internal/connector-tools/resolve",
    }


def build_idempotency_policy(api_prefix: str = API_PREFIX) -> IdempotencyPolicyConfig:
    # High-risk operations that start jobs, stream responses, send email,
    # upload files, call external services, sync data, execute tools, or
    # delete broad/destructive resources.
    domain_required = {
        "POST": [
            # Chat - high-risk state changes
            "/agents/feedback",
            "/chat/send-chat-message",
            "/chat/messages",
            "/chat/delete-all-chat-sessions",
            "/chat/delete-chat-session/{chat_session_id}",
            "/chat/stop-chat-session/{chat_session_id}",
            "/chat/set-message-as-latest",
            "/chat/create-chat-message-feedback",
            "/chat/remove-chat-message-feedback",
            # Threads
            "/threads/{thread_id}/runs/stream",
            # Agents - streaming and invocation
            "/agents/invoke",
            "/agents/{agent_id}/invoke",
            "/agents/stream",
            "/agents/{agent_id}/stream",
            # MCP and proxy
            "/proxy/mcp/execute",
            # Data sources and ingestion
            "/datasources/{id}/sync",
            "/ingest/batch",
            # Project file operations
            "/user/projects/file/upload",
            "/user/projects/{project_id}/files/{file_id}",
            "/user/projects/{project_id}/instructions",
            "/user/projects/{project_id}/move_chat_session",
            "/user/projects/remove_chat_session",
            # Mail
            "/mail-configs/{config_id}/test",
            "/mail-configs/{config_id}/send",
            "/mail-configs/user-credentials/test",
            # Admin provider operations
            "/admin/providers/{provider_id}/sync-models",
            "/admin/ollama/pull",
            "/admin/web-search/content-providers/crawl",
            "/admin/web-search/content-providers/reset-default",
            "/admin/web-search/content-providers/{provider_id}/activate",
            "/admin/web-search/content-providers/{provider_id}/deactivate",
            "/admin/persona/upload-image",
            # Thread runs
            "/threads/{thread_id}/runs/{run_id}/cancel",
            # MCP providers and tools
            "/mcp-providers/{provider_id}/sync",
            "/mcp-tools/sync",
            "/mcp-tools/provider/{provider_id}/sync",
            # Datasource connectors
            "/datasources/connectors/{connector_name}/validate",
            "/datasources/connectors/{connector_name}/streams",
            # Flow playground — every run executes the flow for real
            "/agent-definitions/flow/playground/runs/stream",
            "/agent-definitions/{definition_id}/flow/playground/runs/stream",
            # External MCP servers — tool execution and the OAuth handshake
            "/admin/mcp/server/{int_id}/tools/{tool_name}/execute",
            "/admin/mcp/oauth/connect",
            "/mcp/oauth/callback",
        ],
        "PUT": [
            "/chat/set-message-as-latest",
        ],
        "DELETE": [
            "/admin/ollama/models/{model_name:path}",
            "/chat/delete-all-chat-sessions",
            "/chat/remove-chat-message-feedback",
            "/user/projects/{project_id}",
            "/user/projects/{project_id}/files/{file_id}",
            "/user/projects/file/{file_id}",
            "/mcp-tools/{tool_id}",
        ],
    }
    # Deterministic creates and updates that can be safely replayed.
    required_replay = {
        "POST": [
            # Chat sessions
            "/chat/create-chat-session",
            "/chat/sessions",
            # Threads
            "/threads",
            "/threads/{thread_id}/history",
            # Assistants
            "/assistants",
            "/assistants/search",
            # Persona
            "/persona",
            # Agent definitions
            "/agent-definitions",
            "/agent-definitions/validate-composition",
            "/agent-definitions/available-for-composition",
            # Agent groups
            "/agent-groups",
            # Data sources
            "/datasources",
            # MCP providers
            "/mcp-providers",
            "/admin/mcp/server",
            "/admin/mcp/servers/create",
            # Provider admin (uses /api/admin prefix)
            "/admin/providers",
            "/admin/providers/test-connection",
            "/admin/user-providers",
            # Projects
            "/user/projects/create",
            "/user/projects",
            # Providers
            "/providers",
            "/providers/test-connection",
            "/user-providers",
            # Schedules
            "/datasources/{datasource_id}/schedule",
            # Ingest
            "/ingest/source-preview",
            # LLM test
            "/admin/llm/test/default",
            "/admin/llm/test",
            # Assistant operations
            "/assistants/{assistant_id}",
            # Agent tools
            "/assistants/{agent_id}/tools",
            "/assistants/{agent_id}/tools/{tool_id}",
            # Mail configuration
            "/mail-configs",
            # LLM configuration
            "/admin/llm/default",
            "/admin/llm/provider",
            # Flow versions — publish/rollback append a version row
            "/agent-definitions/{definition_id}/flow/publish",
            "/agent-definitions/{definition_id}/flow/rollback",
            "/agent-definitions/{definition_id}/expand",
            # External MCP server registration
            "/admin/mcp/server",
            "/admin/mcp/servers/create",
        ],
        "PUT": [
            "/agent-definitions/{definition_id}/sub-agents",
            "/agent-definitions/{definition_id}",
            "/assistants/{assistant_id}",
            "/chat/rename-chat-session",
            "/datasources/{id}",
            "/datasources/{datasource_id}/schedule",
            "/admin/providers/{provider_id}",
            "/admin/providers/order",
            "/admin/user-providers/{provider_id}",
            "/admin/llm/provider",
            "/assistants/{agent_id}/tools/reorder",
            "/mail-configs/user-credentials",
        ],
        "PATCH": [
            "/assistants/{assistant_id}",
            "/persona/{persona_id}",
            "/agent-definitions/{definition_id}/sub-agents",
            "/agent-definitions/{definition_id}",
            "/agent-groups/{group_id}",
            "/threads/{thread_id}",
            "/mail-configs/{config_id}",
        ],
        "DELETE": [
            "/assistants/{assistant_id}",
            "/agent-definitions/{definition_id}",
            "/agent-groups/{group_id}",
            "/persona/{persona_id}",
            "/datasources/{id}",
            "/mcp-providers/{provider_id}",
            "/user-providers/{provider_id}",
            "/admin/providers/{provider_id}",
            "/admin/user-providers/{provider_id}",
            "/datasources/{datasource_id}/schedule",
            "/threads/{thread_id}",
            "/chat/sessions/{chat_session_id}",
            "/chat/delete-chat-session/{chat_session_id}",
            "/mail-configs/{config_id}",
            "/mail-configs/user-credentials",
            "/assistants/{agent_id}/tools/{tool_id}",
            "/admin/mcp/server/{server_id}",
        ],
    }
    # Read-like POST endpoints where a missing key is acceptable.
    optional_replay = {
        "POST": [
            "/agents/history",
            "/threads/search",
            "/user/projects/file/statuses",
            "/admin/web-search/content-providers/test",
            # Pure validation: reads a spec, writes nothing
            "/agent-definitions/validate-flow",
        ],
        "PATCH": [
            "/chat/rename-chat-session",
            "/admin/mcp/server/{int_id}",
            "/admin/mcp/server/{server_id}",
            "/admin/mcp/server/{int_id}/status",
            "/admin/mcp/server/{server_id}/status",
            "/admin/tool/status",
            "/providers/{provider_id}/default-model",
            "/datasources/{id}",
            "/user/projects/{project_id}",
            "/mcp-providers/{provider_id}",
            "/admin/providers/{config_id}/default-model",
            "/admin/mcp/server/{server_id}",
            "/admin/mcp/server/{server_id}/status",
            "/admin/tool/status",
        ],
        "PUT": [
            "/agent-definitions/{definition_id}/flow/draft",
            "/chat/update-chat-session-model",
            "/chat/update-chat-session-temperature",
            "/providers/{provider_id}",
            "/user-providers/{provider_id}",
            "/admin/llm/default",
        ],
        "DELETE": [
            "/providers/{provider_id}",
            "/datasources/{id}/schedule",
            "/agent-definitions/{definition_id}/flow/draft",
            "/admin/mcp/server/{int_id}",
            "/admin/mcp/server/{server_id}",
        ],
    }

    return IdempotencyPolicyConfig(
        default_mode=IdempotencyMode.OPTIONAL_REPLAY,
        route_policies=[
            *build_route_policies(
                api_prefix,
                domain_required,
                IdempotencyMode.DOMAIN_REQUIRED,
            ),
            *build_route_policies(api_prefix, required_replay, IdempotencyMode.REQUIRED_REPLAY),
            *build_route_policies(api_prefix, optional_replay, IdempotencyMode.OPTIONAL_REPLAY),
        ],
    )


def build_route_policies(
    api_prefix: str,
    routes_by_method: dict[str, list[str]],
    mode: IdempotencyMode,
) -> list[IdempotencyPolicy]:
    return [
        IdempotencyPolicy(
            method=method,
            path=f"{api_prefix}{path}",
            mode=mode,
            # domain_required always enforces a key; other modes fall back to
            # the global enforce_required_keys flag (None).
            enforce_missing_key=(True if mode == IdempotencyMode.DOMAIN_REQUIRED else None),
        )
        for method, paths in routes_by_method.items()
        for path in paths
    ]
