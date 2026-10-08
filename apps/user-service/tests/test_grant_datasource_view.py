"""A guarded, repeatable grant for the Existing Connectors admin page."""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_dry_run_preserves_role_and_reports_missing_grant():
    from scripts.grant_datasource_view import ensure_datasource_view

    role = {
        "id": "knowledge-id",
        "name": "knowledge-manager",
        "attributes": {
            "agentic.permissions": ["datasource:read", "embedding:view"],
            "agentic.builtin": ["true"],
        },
    }

    async def request(method, path, **kwargs):
        if path == "/clients":
            return [{"id": "rag-id", "clientId": "rag-service-client"}]
        if path == "/clients/rag-id/roles/knowledge-manager":
            return role
        raise AssertionError(f"Unexpected request: {method} {path}")

    client = AsyncMock()
    client.request.side_effect = request
    assert await ensure_datasource_view(
        client, apply=False, service_client_name="rag-service-client"
    ) is True
    assert role["attributes"]["agentic.permissions"] == [
        "datasource:read", "embedding:view",
    ]
    assert all(call.args[0] == "GET" for call in client.request.call_args_list)


@pytest.mark.asyncio
async def test_apply_preserves_other_attributes_and_is_idempotent():
    from scripts.grant_datasource_view import ensure_datasource_view

    role = {
        "id": "knowledge-id",
        "name": "knowledge-manager",
        "description": "Knowledge management",
        "attributes": {
            "agentic.permissions": ["datasource:read", "embedding:view"],
            "agentic.builtin": ["true"],
        },
    }
    writes = []

    async def request(method, path, **kwargs):
        if method == "GET" and path == "/clients":
            return [{"id": "rag-id", "clientId": "rag-service-client"}]
        if method == "GET" and path == "/clients/rag-id/roles/knowledge-manager":
            return role
        if method == "PUT" and path == "/roles-by-id/knowledge-id":
            writes.append(kwargs["json"])
            role.update(kwargs["json"])
            return None
        raise AssertionError(f"Unexpected request: {method} {path}")

    client = AsyncMock()
    client.request.side_effect = request
    assert await ensure_datasource_view(
        client, apply=True, service_client_name="rag-service-client"
    ) is True
    assert await ensure_datasource_view(
        client, apply=True, service_client_name="rag-service-client"
    ) is False
    assert len(writes) == 1
    assert set(role["attributes"]["agentic.permissions"]) == {
        "datasource:read", "datasource:view", "embedding:view",
    }
    assert role["attributes"]["agentic.builtin"] == ["true"]


@pytest.mark.asyncio
async def test_refuses_role_without_datasource_read():
    from scripts.grant_datasource_view import ensure_datasource_view

    client = AsyncMock()
    client.request.side_effect = [
        [{"id": "rag-id", "clientId": "rag-service-client"}],
        {"id": "knowledge-id", "name": "knowledge-manager", "attributes": {}},
    ]
    with pytest.raises(ValueError, match="datasource:read"):
        await ensure_datasource_view(
            client, apply=True, service_client_name="rag-service-client"
        )
    assert all(call.args[0] == "GET" for call in client.request.call_args_list)
