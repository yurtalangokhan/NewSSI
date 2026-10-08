from unittest.mock import AsyncMock, patch

import pytest

from schemas.personas import PersonaUpsertRequest
from service.personas.persona_service import PersonaService

BINDINGS = [
    {"datasource_id": "e22ef0bf-3c16-4591-a254-7c48cb16fc55", "operations": ["read"]},
    {"datasource_id": "e22ef0bf-3c16-4591-a254-7c48cb16fc56", "operations": ["list_resources"]},
]


def test_request_keeps_multiple_connector_bindings_and_tools():
    request = PersonaUpsertRequest(
        name="Analyst",
        description="",
        base_agent="configurable-mcp-agent",
        mcp_tools=["calculator"],
        connector_bindings=BINDINGS,
    )
    assert request.model_dump()["connector_bindings"] == BINDINGS
    assert request.mcp_tools == ["calculator"]


@pytest.mark.asyncio
async def test_create_persists_validated_bindings_without_replacing_tools():
    service = PersonaService()
    service._validate_connector_bindings = AsyncMock(return_value=BINDINGS)
    service._upsert_dynamic_definition = AsyncMock()
    service._serialize_custom_persona = AsyncMock(return_value={"id": 5})
    payload = {
        "name": "Analyst",
        "description": "",
        "base_agent": "configurable-mcp-agent",
        "mcp_tools": ["calculator"],
        "connector_bindings": BINDINGS,
    }
    with patch(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.create",
        new=AsyncMock(return_value={"id": 5}),
    ) as create:
        await service.create_persona(payload, user_id="user-1")
    assert create.await_args.kwargs["connector_bindings"] == BINDINGS
    assert create.await_args.kwargs["mcp_tools"] == ["calculator"]
    service._validate_connector_bindings.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_can_clear_bindings_without_replacing_tools():
    service = PersonaService()
    service._validate_connector_bindings = AsyncMock(return_value=[])
    service._upsert_dynamic_definition = AsyncMock()
    service._serialize_custom_persona = AsyncMock(return_value={"id": 5})
    with (
        patch(
            "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
            new=AsyncMock(
                return_value={"id": 5, "user_id": "user-1", "connector_bindings": BINDINGS}
            ),
        ),
        patch(
            "infrastructure.db.repositories.persona_repo.PersonaRepository.update",
            new=AsyncMock(return_value={"id": 5}),
        ) as update,
    ):
        await service.update_persona(
            5,
            {
                "name": "Analyst",
                "description": "",
                "base_agent": "configurable-mcp-agent",
                "mcp_tools": ["calculator"],
                "connector_bindings": [],
            },
            user_id="user-1",
        )
    assert update.await_args.kwargs["connector_bindings"] == []
    assert update.await_args.kwargs["mcp_tools"] == ["calculator"]


@pytest.mark.asyncio
async def test_legacy_update_omitting_connectors_preserves_saved_assignments():
    service = PersonaService()
    service._validate_connector_bindings = AsyncMock(return_value=BINDINGS)
    service._upsert_dynamic_definition = AsyncMock()
    service._serialize_custom_persona = AsyncMock(return_value={"id": 5})
    with (
        patch(
            "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
            new=AsyncMock(
                return_value={
                    "id": 5,
                    "user_id": "user-1",
                    "connector_bindings": BINDINGS,
                    "base_agent": "configurable-mcp-agent",
                }
            ),
        ),
        patch(
            "infrastructure.db.repositories.persona_repo.PersonaRepository.update",
            new=AsyncMock(return_value={"id": 5}),
        ) as update,
    ):
        await service.update_persona(
            5,
            {
                "name": "Renamed",
                "description": "",
                "base_agent": "configurable-mcp-agent",
            },
            user_id="user-1",
        )
    assert service._validate_connector_bindings.await_args.args[0]["connector_bindings"] == BINDINGS
    assert update.await_args.kwargs["connector_bindings"] == BINDINGS
