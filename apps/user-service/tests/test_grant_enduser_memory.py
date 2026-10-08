"""Personal memory CRUD belongs to the end-user self-service bundle."""

from unittest.mock import AsyncMock

import pytest


def _client():
    role = {
        "id": "self-id",
        "name": "account-self-service",
        "clientRole": True,
        "attributes": {
            "agentic.permissions": ["settings:read"],
            "agentic.builtin": ["true"],
        },
    }
    writes = []

    async def request(method, path, **kwargs):
        if method == "GET" and path == "/roles/enduser":
            return {"id": "end-id", "name": "enduser", "clientRole": False}
        if method == "GET" and path == "/roles-by-id/end-id/composites":
            return [{"id": "self-id", "name": "account-self-service"}]
        if method == "GET" and path == "/clients":
            return [{"id": "user-id", "clientId": "user-service-client"}]
        if method == "GET" and path == "/clients/user-id/roles/account-self-service":
            return role
        if method == "GET" and path == "/clients/user-id/authz/resource-server/resource":
            return [{
                "name": "memory",
                "type": "agentic:feature",
                "scopes": [{"name": action} for action in ("create", "delete", "read", "update")],
            }]
        if method == "PUT" and path == "/roles-by-id/self-id":
            writes.append(kwargs["json"])
            role.update(kwargs["json"])
            return None
        raise AssertionError(f"Unexpected request: {method} {path}")

    client = AsyncMock()
    client.request.side_effect = request
    return client, role, writes


@pytest.mark.asyncio
async def test_dry_run_and_apply_are_idempotent_and_keep_rag_scopes_separate():
    from scripts.grant_enduser_memory import grant_enduser_memory

    client, role, writes = _client()
    expected = ["memory:create", "memory:delete", "memory:read", "memory:update"]
    assert await grant_enduser_memory(
        client, apply=False, service_client_name="user-service-client"
    ) == expected
    assert writes == []

    assert await grant_enduser_memory(
        client, apply=True, service_client_name="user-service-client"
    ) == expected
    assert await grant_enduser_memory(
        client, apply=True, service_client_name="user-service-client"
    ) == []
    assert len(writes) == 1
    assert set(role["attributes"]["agentic.permissions"]) == set(expected) | {"settings:read"}
    assert role["attributes"]["agentic.builtin"] == ["true"]
    assert "memory:search" not in role["attributes"]["agentic.permissions"]
    assert "memory:write" not in role["attributes"]["agentic.permissions"]


@pytest.mark.asyncio
async def test_refuses_to_edit_a_bundle_not_inherited_by_enduser():
    from scripts.grant_enduser_memory import grant_enduser_memory

    client, _, writes = _client()
    original = client.request.side_effect

    async def request(method, path, **kwargs):
        if path == "/roles-by-id/end-id/composites":
            return []
        return await original(method, path, **kwargs)

    client.request.side_effect = request
    with pytest.raises(ValueError, match="does not inherit"):
        await grant_enduser_memory(
            client, apply=True, service_client_name="user-service-client"
        )
    assert writes == []
