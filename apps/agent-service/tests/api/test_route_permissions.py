from inspect import getclosurevars

from fastapi import Request, Response
from fastapi.routing import APIRoute
import pytest

from api.routes import (
    datasources_route,
    ingest_route,
    mail_configs_route,
    provider_route,
    proxy_route,
    user_route,
)
from schemas.datasources import DataSourceUpdateInput
from service.datasources import datasource_application_service


def _route(path: str, method: str, routes: list) -> APIRoute:
    return next(
        route
        for route in routes
        if isinstance(route, APIRoute) and route.path == path and method in route.methods
    )


def _dependency_names(route: APIRoute) -> list[str]:
    return [getattr(dependency.call, "__name__", "") for dependency in route.dependant.dependencies]


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
        route = _route(path, method, mail_configs_route.router.routes)
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
        route = _route(path, method, proxy_route.router.routes)
        assert "_check_permission" in _dependency_names(route), permission


def test_llm_provider_routes_require_provider_permissions() -> None:
    expected = {
        ("/api/admin/providers", "GET"): "provider:read",
        ("/api/admin/providers/available-models", "GET"): "provider:read",
    }

    for (path, method), permission in expected.items():
        route = _route(path, method, provider_route.router.routes)
        checks = [
            dependency.call
            for dependency in route.dependant.dependencies
            if getattr(dependency.call, "__name__", "") == "_check_permission"
        ]
        assert len(checks) == 1
        assert getclosurevars(checks[0]).nonlocals["permission"] == permission


def test_legacy_llm_routes_require_provider_permissions() -> None:
    expected = {
        ("/api/admin/llm/built-in/options", "GET"): "provider:read",
        ("/api/admin/llm/ollama/available-models", "GET"): "provider:read",
    }

    for (path, method), permission in expected.items():
        route = _route(path, method, user_route.router.routes)
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
        route = _route(path, method, datasources_route.router.routes)
        assert "_check_permission" in _dependency_names(route), permission


def _required_permissions(route: APIRoute) -> list[str]:
    """The permission each ``require_permission(...)`` dependency of ``route`` was built with."""
    return [
        cell.cell_contents
        for dependency in route.dependant.dependencies
        if getattr(dependency.call, "__name__", "") == "_check_permission"
        for cell in dependency.call.__closure__ or ()
        if isinstance(cell.cell_contents, str)
    ]


def test_source_preview_requires_the_permission_that_editing_the_connection_takes() -> None:
    # It opens a connection with the datasource's stored credentials.
    route = _route("/source-preview", "POST", ingest_route.router.routes)
    assert _required_permissions(route) == ["datasource:update"]


def _transport() -> tuple[Request, Response]:
    """The request/response pair a route needs; only read when an error is rendered."""
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}), Response()


@pytest.mark.asyncio
async def test_details_carry_connection_settings_only_for_callers_who_may_edit(monkeypatch) -> None:
    asked: list[str] = []
    seen: list[bool] = []

    class _Service:
        async def get_datasource_details(self, id, *, page, page_size, include_config, **_):  # noqa: A002
            seen.append(include_config)
            return {
                "id": id,
                "name": "Sales",
                "connector_type": "postgres",
                "connector_display_name": "PostgreSQL",
                "config": {"host": "db"} if include_config else {},
            }

    def grant(*granted: str):
        async def has_permission(user, permission):
            asked.append(permission)
            return permission in granted

        monkeypatch.setattr(datasources_route, "has_permission", has_permission)

    monkeypatch.setattr(datasource_application_service, "_get_service", lambda: _Service())

    grant("datasource:read")
    reader = await datasources_route.get_datasource_details(*_transport(), user=object(), id="ds-1")
    grant("datasource:read", "datasource:update")
    editor = await datasources_route.get_datasource_details(*_transport(), user=object(), id="ds-1")

    assert asked.count("datasource:update") == 2
    assert seen == [False, True]
    assert reader.data.config == {} and editor.data.config == {"host": "db"}


@pytest.mark.asyncio
async def test_the_reason_of_a_failed_sync_goes_only_to_callers_who_may_run_syncs(monkeypatch) -> None:
    seen: dict[str, list[bool]] = {}
    details = {
        "id": "ds-1",
        "name": "Sales",
        "connector_type": "postgres",
        "connector_display_name": "PostgreSQL",
        "config": {},
    }

    class _Service:
        async def get_datasource_details(self, id, *, include_error_detail, **_):  # noqa: A002
            seen.setdefault("details", []).append(include_error_detail)
            return details

        async def update_datasource(self, id, *, include_error_detail, **_):  # noqa: A002
            seen.setdefault("update", []).append(include_error_detail)
            return details

        async def get_sync_status(self, id, *, include_error_detail):  # noqa: A002
            seen.setdefault("status", []).append(include_error_detail)
            return {"id": id}

        async def get_sync_history(self, id, *, limit, include_error_detail):  # noqa: A002
            seen.setdefault("history", []).append(include_error_detail)
            return []

    monkeypatch.setattr(datasource_application_service, "_get_service", lambda: _Service())
    monkeypatch.setattr(datasources_route, "_owner_id", lambda user: "owner-1")

    for granted in ({"datasource:read"}, {"datasource:read", "datasource:sync"}):

        async def has_permission(user, permission, granted=granted):
            return permission in granted

        monkeypatch.setattr(datasources_route, "has_permission", has_permission)
        await datasources_route.get_datasource_details(*_transport(), user=object(), id="ds-1")
        await datasources_route.update_datasource(
            *_transport(), id="ds-1", input=DataSourceUpdateInput(name="Sales"), user=object()
        )
        await datasources_route.get_sync_status(*_transport(), id="ds-1", user=object())
        await datasources_route.get_sync_history(*_transport(), user=object(), id="ds-1", limit=20)

    assert seen == {route: [False, True] for route in ("details", "update", "status", "history")}
