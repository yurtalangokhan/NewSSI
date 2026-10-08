from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from error_contract import BadRequestError
import pytest

from tests.error_support import raises_localized
from service.personas.persona_service import PersonaService


@pytest.mark.asyncio
async def test_create_persona_normalizes_mcp_tools_before_persisting():
    service = PersonaService()
    service._validate_mcp_tool_configs = AsyncMock(return_value={})
    service._upsert_dynamic_definition = AsyncMock()
    service._serialize_custom_persona = AsyncMock(return_value={"id": 1})
    payload = {
        "name": "Research agent",
        "description": "Searches internal sources",
        "mcp_tools": ["web_search"],
    }

    with patch(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.create",
        new=AsyncMock(return_value={"id": 1}),
    ) as create_persona:
        await service.create_persona(payload, user_id="user-1")

    service._validate_mcp_tool_configs.assert_awaited_once_with(
        user_id="user-1",
        mcp_tools=["web_search"],
        mcp_tool_configs={},
    )
    assert create_persona.await_args.kwargs["mcp_tools"] == ["web_search"]
    assert create_persona.await_args.kwargs["mcp_tool_configs"] == {}


@pytest.mark.asyncio
async def test_validate_mail_tool_requires_config_when_send_email_selected():
    service = PersonaService()
    service._mail_config_service = SimpleNamespace(get_config=AsyncMock())

    with raises_localized(BadRequestError, "mail configuration is required"):
        await service._validate_mcp_tool_configs(
            user_id="user-1",
            mcp_tools=["send_email"],
            mcp_tool_configs={},
        )


@pytest.mark.asyncio
async def test_validate_mail_tool_removes_stale_config_when_tool_is_disabled():
    service = PersonaService()
    service._mail_config_service = SimpleNamespace(get_config=AsyncMock())

    result = await service._validate_mcp_tool_configs(
        user_id="user-1",
        mcp_tools=["web_search"],
        mcp_tool_configs={"send_email": {"mail_config_id": "config-1"}},
    )

    assert result == {}
    service._mail_config_service.get_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_mail_tool_accepts_active_owned_config():
    service = PersonaService()
    service._mail_config_service = SimpleNamespace(
        get_config=AsyncMock(return_value={"id": "config-1", "is_active": True})
    )

    result = await service._validate_mcp_tool_configs(
        user_id="user-1",
        mcp_tools=["send_email"],
        mcp_tool_configs={"send_email": {"mail_config_id": "config-1"}},
    )

    assert result == {"send_email": {"mail_config_id": "config-1"}}
    service._mail_config_service.get_config.assert_awaited_once_with("user-1", "config-1")
