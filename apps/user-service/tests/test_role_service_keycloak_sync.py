from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.service.role_service import (
    ALL_COARSE_ROLE_NAMES,
    COARSE_SERVICE_ROLES,
    CompositeRoleService,
    _coarse_roles_for_db_role,
)


def test_coarse_service_roles_has_all_known_services():
    assert "user-service" in COARSE_SERVICE_ROLES
    assert "agent-service" in COARSE_SERVICE_ROLES
    assert "rag-service" in COARSE_SERVICE_ROLES
    assert "tools-service" in COARSE_SERVICE_ROLES


def test_coarse_service_roles_has_realm_roles():
    for svc in COARSE_SERVICE_ROLES:
        assert "system-admin" in COARSE_SERVICE_ROLES[svc]
        assert "enterprise-admin" in COARSE_SERVICE_ROLES[svc]
        assert "enduser" in COARSE_SERVICE_ROLES[svc]


def test_system_admin_has_admin_level_roles():
    mapping = _coarse_roles_for_db_role("system-admin")
    assert "user-admin" in mapping["user-service"]
    assert "agent-admin" in mapping["agent-service"]
    assert "rag-admin" in mapping["rag-service"]
    assert "tool-admin" in mapping["tools-service"]


def test_enterprise_admin_has_manager_level_roles():
    mapping = _coarse_roles_for_db_role("enterprise-admin")
    assert "user-manager" in mapping["user-service"]
    assert "agent-manager" in mapping["agent-service"]
    assert "rag-manager" in mapping["rag-service"]
    assert "tool-user" in mapping["tools-service"]


def test_enduser_has_enduser_level_roles():
    mapping = _coarse_roles_for_db_role("enduser")
    assert "enduser" in mapping["user-service"]
    assert "agent-enduser" in mapping["agent-service"]
    assert "rag-enduser" in mapping["rag-service"]
    assert "tool-user" in mapping["tools-service"]


def test_unknown_role_gets_enduser_fallback():
    mapping = _coarse_roles_for_db_role("nonexistent-role")
    assert mapping == _coarse_roles_for_db_role("enduser")


def test_all_coarse_role_names_contains_all():
    assert "user-admin" in ALL_COARSE_ROLE_NAMES
    assert "user-manager" in ALL_COARSE_ROLE_NAMES
    assert "agent-admin" in ALL_COARSE_ROLE_NAMES
    assert "agent-manager" in ALL_COARSE_ROLE_NAMES
    assert "agent-enduser" in ALL_COARSE_ROLE_NAMES
    assert "rag-admin" in ALL_COARSE_ROLE_NAMES
    assert "rag-manager" in ALL_COARSE_ROLE_NAMES
    assert "rag-enduser" in ALL_COARSE_ROLE_NAMES
    assert "tool-admin" in ALL_COARSE_ROLE_NAMES
    assert "tool-user" in ALL_COARSE_ROLE_NAMES
    assert "enduser" in ALL_COARSE_ROLE_NAMES


async def test_build_coarse_composite_children_produces_correct_format():
    role_service = CompositeRoleService()

    child_roles = await role_service._build_coarse_composite_children("enduser")

    for child in child_roles:
        assert "name" in child
        assert child["clientRole"] is True
        assert "clientId" in child
        assert child["clientId"] in COARSE_SERVICE_ROLES


async def test_build_coarse_composite_children_contains_tool_user():
    role_service = CompositeRoleService()
    child_roles = await role_service._build_coarse_composite_children("enduser")
    names = [r["name"] for r in child_roles]
    assert "tool-user" in names
    assert "agent-enduser" in names
    assert "rag-enduser" in names


@pytest.mark.asyncio
async def test_set_role_permissions_invalidates_sessions_for_assigned_users():
    role_service = CompositeRoleService()
    role = SimpleNamespace(
        name="analyst",
        description="Analyst",
        permissions=["document:read"],
        role_ids=[],
        is_builtin=False,
        is_admin=False,
    )
    role_service.permission_repo = SimpleNamespace(
        get_all=AsyncMock(return_value=[SimpleNamespace(name="document:read")])
    )
    role_service.role_repo = SimpleNamespace(update=AsyncMock(return_value=role))
    role_service.keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        logout_user_sessions=AsyncMock(return_value=True),
    )
    role_service._sync_role_to_keycloak = AsyncMock()
    role_service._users_with_role = AsyncMock(
        return_value=[SimpleNamespace(email="analyst@example.com", keycloak_id="kc-analyst")]
    )

    result = await role_service.set_role_permissions("analyst", ["document:read"])

    assert result["permissions"] == ["document:read"]
    role_service.keycloak.logout_user_sessions.assert_awaited_once_with("kc-analyst")


@pytest.mark.asyncio
async def test_delete_role_rejects_assigned_roles():
    role_service = CompositeRoleService()
    role_service.role_repo = SimpleNamespace(
        get_by_name=AsyncMock(return_value=SimpleNamespace(name="analyst", is_builtin=False))
    )
    role_service._users_with_role = AsyncMock(
        return_value=[SimpleNamespace(email="analyst@example.com")]
    )

    with pytest.raises(ValueError, match="users are assigned"):
        await role_service.delete_role("analyst")
