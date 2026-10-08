from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from error_contract import AgentNotFoundError, DependencyResponseError, DependencyUnavailableError

from core.exceptions import NotFoundError
from service.auth.auth_service import AuthenticatedUser
from service.auth.permission_service import PermissionService
from service.personas.persona_service import PersonaService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (httpx.HTTPError("offline"), DependencyUnavailableError),
        (ValueError("invalid JSON"), DependencyResponseError),
    ],
)
async def test_permission_failure_propagates(monkeypatch, error, expected):
    service = PermissionService()
    monkeypatch.setattr(
        "service.auth.permission_service.outbound.request", AsyncMock(side_effect=error)
    )
    with pytest.raises(expected):
        await service.check_agent_access("subject", 42)


@pytest.mark.asyncio
async def test_private_organization_grant_and_local_owner_are_visible(monkeypatch):
    persona_service = PersonaService()
    user = AuthenticatedUser(
        email="", user_id="subject", claims={"user_service_user": {"id": "local"}}
    )
    grants = AsyncMock(return_value=["42"])
    monkeypatch.setattr(
        "service.auth.permission_service.get_permission_service",
        lambda: SimpleNamespace(get_user_accessible_agents=grants),
    )
    restricted, accessible = await persona_service._load_agent_group_visibility(user)
    assert persona_service._can_access_persona(
        {"id": 42, "is_public": False}, user, restricted, accessible, False
    )
    assert persona_service._can_access_persona(
        {"id": 43, "user_id": "local", "is_public": False}, user, restricted, accessible, False
    )
    assert not persona_service._can_access_persona(
        {"id": 44, "is_public": False}, user, restricted, accessible, False
    )
    grants.assert_awaited_once_with("local", required_permission="execute")


@pytest.mark.asyncio
@pytest.mark.parametrize("persona_id", [42, "42"])
async def test_chat_denies_private_agent_before_execution(monkeypatch, persona_id):
    persona_service = PersonaService()
    monkeypatch.setattr(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
        AsyncMock(return_value={"id": 42, "is_public": False}),
    )
    persona_service._load_agent_group_visibility = AsyncMock(return_value=(set(), set()))
    persona_service._can_manage_all_personas = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError) as exc:
        await persona_service.authorize_chat_persona(
            persona_id, AuthenticatedUser(email="", user_id="subject")
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_chat_definition_uuid_uses_linked_persona_permission(monkeypatch):
    persona_service = PersonaService()
    monkeypatch.setattr(
        "infrastructure.db.repositories.agent_definition_repo.AgentDefinitionRepository.get_by_id",
        AsyncMock(return_value=SimpleNamespace(persona_id=42, is_active=True)),
    )
    monkeypatch.setattr(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
        AsyncMock(return_value={"id": 42, "is_public": False}),
    )
    persona_service._load_agent_group_visibility = AsyncMock(return_value=(set(), {42}))
    persona_service._can_manage_all_personas = AsyncMock(return_value=False)
    result = await persona_service.authorize_chat_persona(
        "7ebc3179-88d5-401b-942a-2a0145862caa", AuthenticatedUser(email="", user_id="subject")
    )
    assert result == 42


@pytest.mark.asyncio
async def test_persona_update_permission_does_not_bypass_private_grants(monkeypatch):
    monkeypatch.setattr(
        "integrations.user_service_client.get_user_permissions",
        AsyncMock(return_value={"permissions": ["persona:update"], "is_admin": False}),
    )
    assert not await PersonaService()._can_manage_all_personas(
        AuthenticatedUser(email="", user_id="subject")
    )


@pytest.mark.asyncio
async def test_admin_permission_failure_does_not_hide_public_or_owned_agents(monkeypatch):
    monkeypatch.setattr(
        "integrations.user_service_client.get_user_permissions", AsyncMock(side_effect=ValueError())
    )
    assert not await PersonaService()._can_manage_all_personas(
        AuthenticatedUser(email="", user_id="subject")
    )


@pytest.mark.asyncio
async def test_chat_route_denies_before_provider_or_thread_effects(monkeypatch):
    from api.routes import chat_route

    user = AuthenticatedUser(email="", user_id="subject")
    monkeypatch.setattr(
        chat_route,
        "get_auth_service",
        lambda: SimpleNamespace(
            resolve_user_identity=AsyncMock(return_value={"known_user_ids": ["subject"]})
        ),
    )
    monkeypatch.setattr(chat_route, "extract_auth_token_from_request", lambda _: None)
    monkeypatch.setattr(chat_route, "resolve_effective_chat_user_id", lambda *_: "subject")
    monkeypatch.setattr(chat_route, "get_user_service", lambda: None)
    monkeypatch.setattr(
        chat_route,
        "resolve_chat_identity",
        AsyncMock(return_value=SimpleNamespace(known_user_ids={"subject"}, project_user_id=None)),
    )
    provider = AsyncMock()
    prepare = AsyncMock()
    monkeypatch.setattr(chat_route, "apply_provider_llm_override", provider)
    monkeypatch.setattr(chat_route, "prepare_chat_thread", prepare)
    persona_service = PersonaService()
    persona_service._load_agent_group_visibility = AsyncMock(return_value=(set(), set()))
    persona_service._can_manage_all_personas = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "service.personas.persona_service.get_persona_service", lambda: persona_service
    )
    monkeypatch.setattr(
        "service.auth.permission_service.get_permission_service",
        lambda: SimpleNamespace(
            get_user_accessible_agents=AsyncMock(return_value=[])
        ),
    )
    monkeypatch.setattr(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
        AsyncMock(return_value={"id": 42, "is_public": False}),
    )
    with pytest.raises(NotFoundError) as exc:
        await chat_route.send_chat_message(
            SimpleNamespace(json=AsyncMock(return_value={"message": "Hello", "persona_id": 42})),
            user,
        )
    assert exc.value.status_code == 404
    provider.assert_not_awaited()
    prepare.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("access", ["grant", "owner", "denied"])
async def test_catalog_detail_and_chat_share_resource_visibility(monkeypatch, access):
    persona_service = PersonaService()
    user = AuthenticatedUser(email="", user_id="subject")
    granted = access != "denied"
    persona = {"id": 42, "name": "Private", "is_public": False}
    if access == "owner":
        persona["user_id"] = "local-owner"
        monkeypatch.setattr(
            "integrations.user_service_client.get_user_by_keycloak_id",
            AsyncMock(return_value={"id": "local-owner"}),
        )
    monkeypatch.setattr(
        "service.auth.permission_service.get_permission_service",
        lambda: SimpleNamespace(
            get_user_accessible_agents=AsyncMock(return_value=["42"] if access == "grant" else [])
        ),
    )
    monkeypatch.setattr(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
        AsyncMock(return_value=persona),
    )
    monkeypatch.setattr(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.list_all",
        AsyncMock(return_value=[persona]),
    )
    monkeypatch.setattr(
        "infrastructure.db.repositories.agent_definition_repo.AgentDefinitionRepository.list_all",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "infrastructure.db.repositories.flow_version_repo.FlowVersionRepository.get_summaries",
        AsyncMock(return_value={}),
    )
    persona_service._can_manage_all_personas = AsyncMock(return_value=False)
    persona_service._get_available_model_names = AsyncMock(return_value=set())
    persona_service._get_mcp_tool_metadata = AsyncMock(return_value={})
    persona_service._load_owner_emails = AsyncMock(return_value={})
    persona_service._serialize_builtin_persona_summary = AsyncMock(return_value={"id": 0})
    persona_service._serialize_custom_persona_summary = AsyncMock(return_value=persona)
    persona_service._serialize_custom_persona = AsyncMock(return_value=persona)
    catalog = await persona_service.get_agent_catalog(user)
    assert (42 in [item["id"] for item in catalog]) is granted
    if granted:
        assert (await persona_service.get_agent_detail("42", user))["id"] == 42
        assert await persona_service.authorize_chat_persona(42, user) == 42
    else:
        with pytest.raises(AgentNotFoundError):
            await persona_service.get_agent_detail("42", user)
        with pytest.raises(NotFoundError):
            await persona_service.authorize_chat_persona(42, user)


@pytest.fixture(autouse=True)
def isolated_identity_and_permissions(monkeypatch):
    monkeypatch.setattr(
        "integrations.user_service_client.get_user_by_keycloak_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        "integrations.user_service_client.get_user_permissions",
        AsyncMock(return_value={"permissions": ["persona:update"], "is_admin": False}),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["invoke", "stream"])
async def test_generic_agent_execution_denies_private_uuid(monkeypatch, endpoint):
    from fastapi import Request, Response

    from api.routes import agents_route
    from schemas.chat import StreamInput, UserInput
    from service.orchestration import agent_interaction_service

    persona_service = PersonaService()
    persona_service._load_agent_group_visibility = AsyncMock(return_value=(set(), set()))
    persona_service._can_manage_all_personas = AsyncMock(return_value=False)
    monkeypatch.setattr(agents_route, "get_persona_service", lambda: persona_service)
    monkeypatch.setattr(agent_interaction_service, "get_persona_service", lambda: persona_service)
    monkeypatch.setattr(
        "infrastructure.db.repositories.agent_definition_repo.AgentDefinitionRepository.get_by_id",
        AsyncMock(return_value=SimpleNamespace(persona_id=42, is_active=True)),
    )
    monkeypatch.setattr(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
        AsyncMock(return_value={"id": 42, "is_public": False}),
    )
    service = SimpleNamespace(
        get_graph_and_config=AsyncMock(side_effect=AssertionError("executed"))
    )
    monkeypatch.setattr(agent_interaction_service.AssistantAgentService, "get_instance", lambda: service)
    generator = AsyncMock(side_effect=AssertionError("streamed"))
    monkeypatch.setattr(agents_route, "message_generator", generator)
    agent_id = "7ebc3179-88d5-401b-942a-2a0145862caa"
    user = AuthenticatedUser(email="", user_id="subject")

    if endpoint == "stream":
        with pytest.raises(NotFoundError) as exc:
            await agents_route.stream(user, StreamInput(message="Hi"), agent_id)
        assert exc.value.status_code == 404
    else:
        response = Response()
        result = await agents_route.invoke(
            Request({"type": "http", "headers": [], "query_string": b""}),
            response,
            user,
            UserInput(message="Hi"),
            agent_id,
        )
        assert response.status_code == 404
        assert result.statusCode == 404
        assert result.data is None
    service.get_graph_and_config.assert_not_awaited()
    generator.assert_not_called()


@pytest.mark.asyncio
async def test_raw_subject_owner_is_resolved_for_detail_and_chat(monkeypatch):
    persona_service = PersonaService()
    user = AuthenticatedUser(email="", user_id="subject", claims={"sub": "subject"})
    lookup = AsyncMock(return_value={"id": "local-owner"})
    monkeypatch.setattr("integrations.user_service_client.get_user_by_keycloak_id", lookup)
    persona = {"id": 42, "user_id": "local-owner", "is_public": False}
    monkeypatch.setattr(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
        AsyncMock(return_value=persona),
    )
    grants = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "service.auth.permission_service.get_permission_service",
        lambda: SimpleNamespace(get_user_accessible_agents=grants),
    )
    persona_service._can_manage_all_personas = AsyncMock(return_value=False)
    persona_service._serialize_custom_persona = AsyncMock(return_value=persona)
    assert (await persona_service.get_agent_detail("42", user))["id"] == 42
    assert await persona_service.authorize_chat_persona(42, user) == 42
    assert user.claims == {"sub": "subject"}
    lookup.assert_awaited()
    grants.assert_awaited_with("local-owner", required_permission="execute")


@pytest.mark.asyncio
async def test_inactive_uuid_cannot_execute_even_public_persona(monkeypatch):
    persona_service = PersonaService()
    monkeypatch.setattr(
        "infrastructure.db.repositories.agent_definition_repo.AgentDefinitionRepository.get_by_id",
        AsyncMock(return_value=SimpleNamespace(persona_id=42, is_active=False)),
    )
    monkeypatch.setattr(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
        AsyncMock(return_value={"id": 42, "is_public": True}),
    )
    persona_service._load_agent_group_visibility = AsyncMock(return_value=(set(), set()))
    persona_service._can_manage_all_personas = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError) as exc:
        await persona_service.authorize_chat_persona(
            "7ebc3179-88d5-401b-942a-2a0145862caa", AuthenticatedUser(email="", user_id="subject")
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_authoritative_enterprise_admin_retains_global_access(monkeypatch):
    monkeypatch.setattr(
        "integrations.user_service_client.get_user_permissions",
        AsyncMock(return_value={"permissions": ["persona:update"], "is_admin": True}),
    )
    monkeypatch.setattr(
        "integrations.authorization_client.get_authorization_client",
        lambda: SimpleNamespace(has_permission=AsyncMock(return_value=False)),
    )
    assert await PersonaService()._can_manage_all_personas(
        AuthenticatedUser(email="", user_id="subject")
    )
