from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.service.role_service import (
    CompositeRoleService,
)


async def test_build_coarse_composite_children_produces_correct_format(monkeypatch):
    import src.service.role_service as role_service_module

    role_service = CompositeRoleService()
    role_service.role_repo = SimpleNamespace(
        get_by_name=AsyncMock(
            return_value=SimpleNamespace(name="member", role_ids=["account-self-service"])
        )
    )
    coarse_service = SimpleNamespace(
        repo=SimpleNamespace(
            get_by_names=AsyncMock(
                return_value=[
                    SimpleNamespace(name="account-self-service", service_client="user-service")
                ]
            )
        )
    )
    monkeypatch.setattr(role_service_module, "get_role_service", lambda: coarse_service)

    child_roles = await role_service._build_coarse_composite_children("member")

    for child in child_roles:
        assert "name" in child
        assert child["clientRole"] is True
        assert "clientId" in child


async def test_build_coarse_composite_children_contains_tool_user(monkeypatch):
    import src.service.role_service as role_service_module

    role_service = CompositeRoleService()
    role_service.role_repo = SimpleNamespace(
        get_by_name=AsyncMock(
            return_value=SimpleNamespace(
                name="member",
                role_ids=["tooling-user", "agent-workspace-user", "knowledge-search-user"],
            )
        )
    )
    coarse_service = SimpleNamespace(
        repo=SimpleNamespace(
            get_by_names=AsyncMock(
                return_value=[
                    SimpleNamespace(name="tooling-user", service_client="tools-service"),
                    SimpleNamespace(name="agent-workspace-user", service_client="agent-service"),
                    SimpleNamespace(name="knowledge-search-user", service_client="rag-service"),
                ]
            )
        )
    )
    monkeypatch.setattr(role_service_module, "get_role_service", lambda: coarse_service)

    child_roles = await role_service._build_coarse_composite_children("member")
    names = [r["name"] for r in child_roles]
    assert "tooling-user" in names
    assert "agent-workspace-user" in names
    assert "knowledge-search-user" in names


async def test_build_coarse_composite_children_has_no_role_name_fallback():
    role_service = CompositeRoleService()
    role_service.role_repo = SimpleNamespace(
        get_by_name=AsyncMock(return_value=SimpleNamespace(name="legacy-admin", role_ids=[]))
    )

    assert await role_service._build_coarse_composite_children("legacy-admin") == []


async def test_build_coarse_composite_children_uses_db_service_client(monkeypatch):
    import src.service.role_service as role_service_module

    role_service = CompositeRoleService()
    role_service.role_repo = SimpleNamespace(
        get_by_name=AsyncMock(
            return_value=SimpleNamespace(name="analyst", role_ids=["custom-tool-bundle"])
        )
    )
    coarse_service = SimpleNamespace(
        repo=SimpleNamespace(
            get_by_names=AsyncMock(
                return_value=[
                    SimpleNamespace(name="custom-tool-bundle", service_client="tools-service")
                ]
            )
        )
    )
    monkeypatch.setattr(role_service_module, "get_role_service", lambda: coarse_service)

    child_roles = await role_service._build_coarse_composite_children("analyst")

    assert child_roles == [
        {
            "name": "custom-tool-bundle",
            "clientRole": True,
            "clientId": "tools-service",
        }
    ]


async def test_cleanup_permission_roles_preserves_db_feature_bundles(monkeypatch):
    import src.service.role_service as role_service_module

    role_service = CompositeRoleService()
    role_service.keycloak = SimpleNamespace(
        get_client_roles=AsyncMock(
            return_value=[
                {"name": "custom-tool-bundle"},
                {"name": "permission-level-role"},
            ]
        ),
        delete_client_role=AsyncMock(),
    )
    coarse_service = SimpleNamespace(
        repo=SimpleNamespace(
            get_all=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        name="custom-tool-bundle",
                        service_client="tools-service",
                    )
                ]
            )
        )
    )
    monkeypatch.setattr(role_service_module, "get_role_service", lambda: coarse_service)

    cleaned = await role_service._cleanup_permission_roles("tools-service")

    assert cleaned == 1
    role_service.keycloak.delete_client_role.assert_awaited_once_with(
        "permission-level-role",
        client_id="tools-service",
    )


@pytest.mark.asyncio
async def test_sync_to_keycloak_invalidates_user_sessions(monkeypatch):
    import src.repository as repository_module

    role_service = CompositeRoleService()
    role_service.role_repo = SimpleNamespace(
        get_all=AsyncMock(
            return_value=[
                SimpleNamespace(
                    name="enduser",
                    description="End user",
                    role_ids=["account-self-service"],
                )
            ]
        ),
        get_by_name=AsyncMock(
            return_value=SimpleNamespace(
                name="enduser",
                role_ids=["account-self-service"],
            )
        ),
    )
    role_service.keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        ensure_client=AsyncMock(return_value=False),
        get_client_roles=AsyncMock(return_value=[]),
        get_client_role=AsyncMock(return_value={"name": "account-self-service"}),
        create_client_role=AsyncMock(return_value=True),
        get_realm_role=AsyncMock(return_value={"id": "realm-role-id", "name": "enduser"}),
        create_realm_role=AsyncMock(return_value=True),
        get_realm_role_composites=AsyncMock(return_value=[]),
        set_realm_role_composites=AsyncMock(return_value=True),
        remove_permissions_protocol_mappers=AsyncMock(return_value={}),
        set_realm_role=AsyncMock(return_value=True),
        logout_user_sessions=AsyncMock(return_value=True),
    )
    coarse_service = SimpleNamespace(
        list_service_clients=AsyncMock(return_value=["user-service"]),
        repo=SimpleNamespace(
            get_all=AsyncMock(return_value=[]),
            get_by_names=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        name="account-self-service",
                        service_client="user-service",
                    )
                ]
            ),
        )
    )
    monkeypatch.setattr("src.service.role_service.get_role_service", lambda: coarse_service)

    class FakeUserRepository:
        async def get_all(self):
            return [SimpleNamespace(email="user@example.com", keycloak_id="kc-user", role="enduser")]

    monkeypatch.setattr(repository_module, "UserRepository", FakeUserRepository)

    result = await role_service.sync_to_keycloak()

    assert result["user_sessions_invalidated"] == 1
    role_service.keycloak.logout_user_sessions.assert_awaited_once_with("kc-user")


async def test_build_coarse_composite_children_falls_back_when_role_ids_are_legacy_names():
    role_service = CompositeRoleService()
    role_service.role_repo = SimpleNamespace(
        get_by_name=AsyncMock(
            return_value=SimpleNamespace(
                role_ids=[
                    "account-self-service",
                    "agent-workspace-user",
                    "knowledge-search-user",
                    "tooling-user",
                ]
            )
        )
    )

    child_roles = await role_service._build_coarse_composite_children("enduser")

    assert [r["name"] for r in child_roles] == [
        "enduser",
        "agent-enduser",
        "rag-enduser",
        "tool-user",
    ]


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
