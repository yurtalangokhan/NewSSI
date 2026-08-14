import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.service.permission_resolver_service import PermissionResolverService


@pytest.mark.asyncio
async def test_resolver_unions_permissions_across_multiple_user_roles(monkeypatch):
    import src.service.permission_resolver_service as resolver_module

    user_id = uuid.uuid4()
    resolver = PermissionResolverService(cache_ttl_seconds=0)
    resolver.user_role_repo = SimpleNamespace(
        list_user_roles=AsyncMock(
            return_value=[
                {"name": "auditor", "is_primary": True},
                {"name": "operator", "is_primary": False},
            ]
        )
    )
    resolver.user_repo = SimpleNamespace(get_by_id=AsyncMock())
    resolver.role_repo = SimpleNamespace(
        get_by_names=AsyncMock(
            return_value=[
                SimpleNamespace(name="auditor", permissions=["user:list"], role_ids=[]),
                SimpleNamespace(
                    name="operator",
                    permissions=["project:read"],
                    role_ids=["agent-workspace-user"],
                ),
            ]
        )
    )
    coarse_service = SimpleNamespace(
        get_aggregated_permissions=AsyncMock(return_value=["agent:read", "thread:read"])
    )
    monkeypatch.setattr(resolver_module, "get_role_service", lambda: coarse_service)

    permissions = await resolver.resolve_effective_permissions(user_id)

    assert permissions == ["agent:read", "project:read", "thread:read", "user:list"]
    resolver.role_repo.get_by_names.assert_awaited_once_with(["auditor", "operator"])
    coarse_service.get_aggregated_permissions.assert_awaited_once_with(["agent-workspace-user"])


@pytest.mark.asyncio
async def test_resolver_falls_back_to_users_role_until_user_roles_are_backfilled():
    user_id = uuid.uuid4()
    resolver = PermissionResolverService(cache_ttl_seconds=0)
    resolver.user_role_repo = SimpleNamespace(list_user_roles=AsyncMock(return_value=[]))
    resolver.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(role="enduser"))
    )
    resolver.role_repo = SimpleNamespace(
        get_by_names=AsyncMock(
            return_value=[
                SimpleNamespace(name="enduser", permissions=["chat:read"], role_ids=[]),
            ]
        )
    )

    permissions = await resolver.resolve_effective_permissions(user_id)

    assert permissions == ["chat:read"]
    resolver.user_repo.get_by_id.assert_awaited_once_with(user_id)


@pytest.mark.asyncio
async def test_resolver_preserves_wildcard_access():
    user_id = uuid.uuid4()
    resolver = PermissionResolverService(cache_ttl_seconds=0)
    resolver.user_role_repo = SimpleNamespace(
        list_user_roles=AsyncMock(return_value=[{"name": "system-admin", "is_primary": True}])
    )
    resolver.user_repo = SimpleNamespace(get_by_id=AsyncMock())
    resolver.role_repo = SimpleNamespace(
        get_by_names=AsyncMock(
            return_value=[
                SimpleNamespace(name="system-admin", permissions=["*"], role_ids=[]),
            ]
        )
    )

    assert await resolver.resolve_effective_permissions(user_id) == ["*"]
