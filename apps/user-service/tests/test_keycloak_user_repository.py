import uuid
from unittest.mock import AsyncMock

import httpx
from error_contract import DependencyAuthenticationError, DependencyResponseError
import pytest

from src.repository.user_repository import UserRepository


def response(status, payload=None):
    return httpx.Response(status, json=payload, request=httpx.Request("GET", "https://kc/users"))


@pytest.mark.asyncio
async def test_identity_uses_subject_and_upsert_does_not_overwrite_keycloak():
    subject = str(uuid.uuid4())
    kc = AsyncMock()
    kc._keycloak_request.return_value = response(
        200,
        {
            "id": subject,
            "email": "authoritative@example.com",
            "enabled": False,
            "attributes": {"agentic.primary_role": ["enterprise-admin"]},
        },
    )
    repo = UserRepository(keycloak=kc)
    repo._roles = AsyncMock(return_value=["enterprise-admin"])
    repo._group_paths = AsyncMock(return_value=[])
    user = await repo.upsert_by_keycloak_id(subject, email="stale@example.com", is_active=True)
    assert str(user.id) == subject == user.keycloak_id
    assert user.email == "authoritative@example.com"
    assert not user.is_active
    assert all(call.args[0] == "GET" for call in kc._keycloak_request.call_args_list)


@pytest.mark.asyncio
async def test_update_preserves_custom_attributes_and_checks_failure():
    subject = uuid.uuid4()
    kc = AsyncMock()
    kc._keycloak_request.side_effect = [
        response(200, {"id": str(subject), "attributes": {"external": ["keep"]}}),
        response(403, {}),
    ]
    repo = UserRepository(keycloak=kc)
    with pytest.raises(DependencyAuthenticationError):
        await repo.update(subject, team_name="Research")
    payload = kc._keycloak_request.call_args.kwargs["json"]
    assert payload["attributes"]["external"] == ["keep"]
    assert payload["attributes"]["agentic.team_name"] == ["Research"]


@pytest.mark.asyncio
async def test_listing_uses_native_enabled_filter_and_count():
    kc = AsyncMock()
    row = {"id": str(uuid.uuid4()), "email": "active@example.com", "enabled": True}
    kc._keycloak_request.side_effect = [response(200, 1), response(200, [row])]
    repo = UserRepository(keycloak=kc)
    repo._roles = AsyncMock(return_value=[])
    repo._group_paths = AsyncMock(return_value=[])
    users, total, _ = await repo.list_paginated(is_active=True)
    assert total == 1
    assert users[0].email == "active@example.com"
    assert kc._keycloak_request.call_args_list[0].kwargs["params"] == {"enabled": "true"}


@pytest.mark.asyncio
async def test_missing_user_is_not_created_from_token_claims():
    kc = AsyncMock()
    kc._keycloak_request.return_value = response(404, {})
    with pytest.raises(DependencyResponseError):
        await UserRepository(keycloak=kc).upsert_by_keycloak_id(str(uuid.uuid4()), email="x@y.test")


@pytest.mark.asyncio
async def test_user_group_paths_come_from_keycloak_membership():
    subject = str(uuid.uuid4())
    kc = AsyncMock()
    kc._keycloak_request.side_effect = [
        response(200, {"id": subject, "email": "user@example.com"}),
        response(200, [{"id": "group", "path": "/Company/Research"}]),
    ]
    repo = UserRepository(keycloak=kc)
    repo._roles = AsyncMock(return_value=[])
    user = await repo.get_by_id(subject)
    assert user.groups == ["/Company/Research"]


@pytest.mark.parametrize("status, exists", [(200, True), (404, False)])
async def test_identity_existence_reads_only_the_profile(status, exists):
    subject = uuid.uuid4()
    keycloak = AsyncMock()
    keycloak._keycloak_request.return_value = response(status, {"id": str(subject)})
    repo = UserRepository(keycloak)
    repo._roles = AsyncMock()
    repo._group_paths = AsyncMock()

    assert await repo.exists_by_id(subject) is exists
    keycloak._keycloak_request.assert_awaited_once_with("GET", f"/users/{subject}")
    repo._roles.assert_not_awaited()
    repo._group_paths.assert_not_awaited()
