"""Centralized API route registration for agent-service.

Consolidates all modular sub-routers and registers them with the canonical
versioned API prefix (/api/v1).
"""

from __future__ import annotations

from collections import Counter

from fastapi import FastAPI
from fastapi.routing import APIRoute

from api.routes import (
    admin_mcp_router,
    agent_definitions_router,
    agent_tools_router,
    agents_router,
    assistant_schemas_router,
    assistants_router,
    authored_documents_router,
    chat_router,
    connector_tools_router,
    datasources_router,
    file_router,
    flow_components_router,
    flow_playground_router,
    flow_versions_router,
    ingest_router,
    mail_configs_router,
    mcp_oauth_callback_router,
    mcp_providers_router,
    mcp_server_admin_router,
    mcp_tools_router,
    ollama_router,
    persona_router,
    provider_router,
    proxy_router,
    run_router,
    schedule_router,
    threads_router,
    user_router,
    web_search_router,
)
from core.http.api_versioning import API_PREFIX

#: Specification of all API routers: (router, optional_resource_prefix)
ROUTERS = (
    (agents_router, ""),
    (agent_definitions_router, ""),
    (assistants_router, ""),
    (authored_documents_router, ""),
    (threads_router, ""),
    (chat_router, ""),
    (persona_router, ""),
    (user_router, ""),
    (schedule_router, ""),
    (ingest_router, "/ingest"),
    (proxy_router, ""),
    (run_router, ""),
    (connector_tools_router, ""),
    (datasources_router, ""),
    (assistant_schemas_router, ""),
    (file_router, ""),
    (flow_components_router, ""),
    (flow_versions_router, ""),
    (flow_playground_router, ""),
    (web_search_router, ""),
    (provider_router, ""),
    (ollama_router, ""),
    (mail_configs_router, ""),
    (mcp_providers_router, ""),
    (mcp_server_admin_router, ""),
    (mcp_oauth_callback_router, ""),
    (mcp_tools_router, ""),
    (agent_tools_router, ""),
    (admin_mcp_router, ""),
)


def register_api_routes(app: FastAPI) -> None:
    """Registers all versioned API routes onto the FastAPI application."""
    for router, resource_prefix in ROUTERS:
        original_paths = [route.path if hasattr(route, "path") else None for route in router.routes]
        for route in router.routes:
            if hasattr(route, "path") and route.path.startswith("/api/"):
                route.path = route.path[4:]
        prefix = f"{API_PREFIX}{resource_prefix}"
        app.include_router(router, prefix=prefix)
        for route, orig_path in zip(router.routes, original_paths, strict=False):
            if orig_path is not None and hasattr(route, "path"):
                route.path = orig_path

    # Disambiguate colliding route operation IDs across routers for OpenAPI schema
    counts = Counter(route.name for route in app.routes if isinstance(route, APIRoute) and route.include_in_schema)
    colliding = {name for name, count in counts.items() if count > 1}
    for route in app.routes:
        if isinstance(route, APIRoute) and route.name in colliding:
            tag = str(route.tags[0]) if route.tags else "default"
            clean_tag = tag.replace("-", "_").replace(" ", "_")
            route.unique_id = f"{clean_tag}_{route.name}"
