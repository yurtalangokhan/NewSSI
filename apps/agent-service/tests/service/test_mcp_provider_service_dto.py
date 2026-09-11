"""Unit tests for MCPProviderService MCPServer DTO + status helpers (plan task 5)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def _service():
    from service.MCPProviderService import MCPProviderService

    return MCPProviderService(repo=AsyncMock())


@pytest.mark.asyncio
async def test_dto_maps_int_id_to_id_and_status():
    svc = _service()
    row = {
        "id": "uuid-1",
        "int_id": 1000,
        "name": "GH",
        "description": "d",
        "url": "https://x/mcp",
        "transport": "streamable_http",
        "auth_type": "OAUTH",
        "auth_performer": "PER_USER",
        "server_status": "CONNECTED",
        "auth_template": None,
        "owner_email": "admin@acme.io",
        "time_updated": "2026-08-28T00:00:00+00:00",
    }
    with (
        patch.object(svc, "_tool_count", AsyncMock(return_value=4)),
        patch("service.MCPProviderService.MCPCredentialService") as cs,
    ):
        cs.get_instance.return_value.has_valid_auth = AsyncMock(return_value=True)
        dto = await svc.to_mcp_server_dto(row, user_id="u1")

    assert dto["id"] == 1000
    assert dto["server_url"] == "https://x/mcp"
    assert dto["status"] == "CONNECTED"
    assert dto["owner"] == "admin@acme.io"
    assert dto["tool_count"] == 4
    assert dto["is_authenticated"] is True
    assert dto["auth_type"] == "OAUTH"


@pytest.mark.asyncio
async def test_dto_none_auth_is_always_authenticated():
    svc = _service()
    row = {
        "id": "u",
        "int_id": 1001,
        "name": "n",
        "description": "",
        "url": "https://x/mcp",
        "transport": "streamable_http",
        "auth_type": "NONE",
        "auth_performer": None,
        "server_status": "CREATED",
        "auth_template": None,
        "owner_email": None,
        "time_updated": None,
    }
    with patch.object(svc, "_tool_count", AsyncMock(return_value=0)):
        dto = await svc.to_mcp_server_dto(row, user_id="u1")

    assert dto["is_authenticated"] is True
    assert dto["owner"] == "system"


@pytest.mark.asyncio
async def test_dto_includes_masked_credentials_when_requested():
    svc = _service()
    row = {
        "id": "u",
        "int_id": 1002,
        "name": "n",
        "description": "",
        "url": "https://x/mcp",
        "transport": "streamable_http",
        "auth_type": "API_TOKEN",
        "auth_performer": "ADMIN",
        "auth_template": None,
        "owner_email": None,
        "time_updated": None,
    }
    with (
        patch.object(svc, "_tool_count", AsyncMock(return_value=0)),
        patch("service.MCPProviderService.MCPCredentialService") as cs,
    ):
        inst = cs.get_instance.return_value
        inst.has_valid_auth = AsyncMock(return_value=True)
        inst.get_credentials = AsyncMock(return_value={"api_key": "supersecret"})
        inst.masked_credentials = lambda c: {"api_key": "****cret"}
        dto = await svc.to_mcp_server_dto(row, user_id="u1", include_credentials=True)

    assert dto["admin_credentials"] == {"api_key": "****cret"}


def test_builtin_server_dto_has_id_1():
    from service.MCPProviderService import MCPProviderService

    dto = MCPProviderService.builtin_server_dto()
    assert dto["id"] == 1
    assert dto["name"] == "Built-in Tools"
    assert dto["status"] == "CONNECTED"
    assert dto["is_authenticated"] is True


@pytest.mark.asyncio
async def test_set_status_and_get_by_int_id_delegate_to_repo():
    svc = _service()
    svc._repo.set_status = AsyncMock(return_value=True)
    svc._repo.get_by_int_id = AsyncMock(return_value={"id": "u", "int_id": 1000})

    assert await svc.set_status("u", "CONNECTED") is True
    assert (await svc.get_by_int_id(1000))["int_id"] == 1000
    svc._repo.set_status.assert_awaited_with("u", "CONNECTED")
