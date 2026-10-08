"""Every provider endpoint accepts the same two id forms.

Before this, ``GET /admin/mcp/server/{id}`` read the segment as a blake2b digest
of the provider UUID while ``PATCH`` and ``DELETE`` on the same path read it as
the ``int_id`` column — so the id a client received from a read could not be used
to write. A UUID was rejected outright with 422.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import api.routes.mcp_server_admin_route as admin_route
from api.dependencies import require_user
from app import app
from service.auth.auth_service import AuthenticatedUser
from tests.api.idempotency_client import IdempotentTestClient

PROVIDER = {"id": "0b5f1c2e-1111-2222-3333-444455556666", "int_id": 4242, "name": "GitHub"}
INT_ID = str(PROVIDER["int_id"])
UUID = PROVIDER["id"]


@pytest.fixture(autouse=True)
def _allow_overridden_user_permissions(monkeypatch):
    """Grant the overridden test identity every permission explicitly.

    ``require_permission`` resolves fine-grained permissions through
    user-service. The hardcoded ``dev-user`` grant this file used to ride on is
    gone now that Gateway owns authentication, so without this the write
    endpoints call a user-service that is not running and fail closed with 403.
    """
    from tests.gateway_auth import allow_all_permissions

    allow_all_permissions(monkeypatch)


def _fake_dev_user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id="dev-user", email="admin@acme.io")


@pytest.fixture
def provider_svc(monkeypatch):
    svc = AsyncMock()

    async def resolve(server_id: str):
        if server_id == INT_ID or server_id == UUID:
            return PROVIDER
        return None

    svc.resolve_provider = AsyncMock(side_effect=resolve)
    svc.to_mcp_server_dto = AsyncMock(return_value={"id": PROVIDER["int_id"]})
    svc.update_provider = AsyncMock(return_value=PROVIDER)
    svc.delete_provider = AsyncMock(return_value=True)
    monkeypatch.setattr(admin_route, "_provider_service", lambda: svc)
    return svc


@pytest.fixture
def tool_svc(monkeypatch):
    svc = AsyncMock()
    svc.delete_tools_by_provider = AsyncMock(return_value=None)
    monkeypatch.setattr(admin_route, "_tool_service", lambda: svc)
    return svc


@pytest.fixture
def client():
    app.dependency_overrides[require_user] = _fake_dev_user
    try:
        yield IdempotentTestClient(app)
    finally:
        app.dependency_overrides.pop(require_user, None)


@pytest.mark.parametrize("server_id", [INT_ID, UUID])
def test_delete_accepts_both_id_forms(client, provider_svc, tool_svc, server_id) -> None:
    response = client.delete(f"/api/v1/admin/mcp/server/{server_id}")

    assert response.status_code == 200, response.text
    provider_svc.delete_provider.assert_awaited_with(PROVIDER["id"])


@pytest.mark.parametrize("server_id", [INT_ID, UUID])
def test_patch_accepts_both_id_forms(client, provider_svc, server_id) -> None:
    response = client.patch(f"/api/v1/admin/mcp/server/{server_id}", json={"name": "renamed"})

    assert response.status_code == 200, response.text
    provider_svc.update_provider.assert_awaited_with(PROVIDER["id"], name="renamed")


def test_an_unknown_id_is_a_404_not_a_422(client, provider_svc) -> None:
    """A UUID-shaped id used to fail path validation before it reached a lookup."""
    response = client.delete("/api/v1/admin/mcp/server/11111111-dead-beef-0000-000000000000")

    assert response.status_code == 404, response.text


def test_the_path_parameter_is_documented_as_a_string() -> None:
    spec = app.openapi()
    parameters = spec["paths"]["/api/v1/admin/mcp/server/{server_id}"]["delete"]["parameters"]
    server_id = next(p for p in parameters if p["name"] == "server_id")

    assert server_id["schema"]["type"] == "string"


def test_the_read_endpoint_returns_the_id_you_can_write_with(monkeypatch) -> None:
    """A read must hand back an id the write endpoints accept.

    ``GET /admin/mcp/server/{id}`` published ``numeric_id_for(uuid)`` — a blake2b
    digest — while every other provider endpoint speaks ``int_id``. A client that
    read a server therefore could not update or delete it with the id it got.
    """
    import api.routes.admin_mcp_route as admin_mcp

    dto = admin_mcp._to_mcp_server({**PROVIDER, "config": {}}, tool_count=0)

    assert dto["id"] == PROVIDER["int_id"]
    assert dto["provider_id"] == PROVIDER["id"]
