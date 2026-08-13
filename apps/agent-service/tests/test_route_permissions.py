from fastapi.routing import APIRoute

from api.routes import DatasourcesRoute, MailConfigsRoute, ProviderRoute, ProxyRoute, UserRoute


def _route(path: str, method: str, routes: list) -> APIRoute:
    return next(
        route
        for route in routes
        if isinstance(route, APIRoute)
        and route.path == path
        and method in route.methods
    )


def _dependency_names(route: APIRoute) -> list[str]:
    return [
        getattr(dependency.call, "__name__", "")
        for dependency in route.dependant.dependencies
    ]


def test_mail_config_routes_require_permissions() -> None:
    expected = {
        ("/api/mail-configs", "GET"): "mail_config:read",
        ("/api/mail-configs", "POST"): "mail_config:create",
        ("/api/mail-configs/{config_id}", "GET"): "mail_config:read",
        ("/api/mail-configs/{config_id}", "PATCH"): "mail_config:update",
        ("/api/mail-configs/{config_id}", "DELETE"): "mail_config:delete",
        ("/api/mail-configs/{config_id}/test", "POST"): "mail_config:test",
        ("/api/mail-configs/{config_id}/send", "POST"): "mail_config:send",
    }

    for (path, method), permission in expected.items():
        route = _route(path, method, MailConfigsRoute.router.routes)
        assert "_check_permission" in _dependency_names(route), permission


def test_proxy_routes_require_permissions() -> None:
    expected = {
        ("/api/proxy/mcp/tools", "GET"): "mcp_tool:read",
        ("/api/proxy/mcp/tools-builtin", "GET"): "mcp_tool:read",
        ("/api/proxy/mcp/execute", "POST"): "tool:execute",
        ("/api/proxy/ollama/models", "GET"): "provider:read",
        ("/api/proxy/rag/collections", "GET"): "collection:list",
    }

    for (path, method), permission in expected.items():
        route = _route(path, method, ProxyRoute.router.routes)
        assert "_check_permission" in _dependency_names(route), permission


def test_llm_provider_routes_require_provider_permissions() -> None:
    expected = {
        ("/api/admin/providers", "GET"): "provider:read",
        ("/api/admin/providers/available-models", "GET"): "provider:read",
    }

    for (path, method), permission in expected.items():
        route = _route(path, method, ProviderRoute.router.routes)
        assert "_check_permission" in _dependency_names(route), permission


def test_legacy_llm_routes_require_provider_permissions() -> None:
    expected = {
        ("/api/admin/llm/built-in/options", "GET"): "provider:read",
        ("/api/admin/llm/ollama/available-models", "GET"): "provider:read",
    }

    for (path, method), permission in expected.items():
        route = _route(path, method, UserRoute.router.routes)
        assert "_check_permission" in _dependency_names(route), permission


def test_datasource_read_and_discovery_routes_require_permissions() -> None:
    expected = {
        ("/datasources/connectors", "GET"): "datasource:read",
        ("/datasources/connectors/{connector_name}/spec", "GET"): "datasource:read",
        ("/datasources/connectors/{connector_name}/validate", "POST"): "datasource:create",
        ("/datasources/connectors/{connector_name}/streams", "POST"): "datasource:create",
        ("/datasources", "GET"): "datasource:read",
        ("/datasources/{id}/details", "GET"): "datasource:read",
        ("/datasources/{id}/status", "GET"): "datasource:read",
        ("/datasources/{id}/sync-history", "GET"): "datasource:read",
    }

    for (path, method), permission in expected.items():
        route = _route(path, method, DatasourcesRoute.router.routes)
        assert "_check_permission" in _dependency_names(route), permission
