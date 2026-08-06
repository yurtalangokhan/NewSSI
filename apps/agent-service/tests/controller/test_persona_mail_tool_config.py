from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from controller.persona_controller import PersonaController


@pytest.mark.asyncio
async def test_create_persona_normalizes_mcp_tools_before_persisting():
    controller = PersonaController()
    controller._validate_mcp_tool_configs = AsyncMock(return_value={})
    controller._upsert_dynamic_definition = AsyncMock()
    controller._serialize_custom_persona = AsyncMock(return_value={"id": 1})
    payload = {
        "name": "Research agent",
        "description": "Searches internal sources",
        "mcp_tools": ["web_search"],
    }

    with patch(
        "controller.persona_controller.PersonaDB.create",
        new=AsyncMock(return_value={"id": 1}),
    ) as create_persona:
        await controller.create_persona(payload, user_id="user-1")

    controller._validate_mcp_tool_configs.assert_awaited_once_with(
        user_id="user-1",
        mcp_tools=["web_search"],
        mcp_tool_configs={},
    )
    assert create_persona.await_args.kwargs["mcp_tools"] == ["web_search"]
    assert create_persona.await_args.kwargs["mcp_tool_configs"] == {}


@pytest.mark.asyncio
async def test_validate_mail_tool_requires_config_when_send_email_selected():
    controller = PersonaController()
    controller._mail_config_service = SimpleNamespace(get_config=AsyncMock())

    with pytest.raises(ValueError, match="send_email requires a mail config"):
        await controller._validate_mcp_tool_configs(
            user_id="user-1",
            mcp_tools=["send_email"],
            mcp_tool_configs={},
        )


@pytest.mark.asyncio
async def test_validate_mail_tool_removes_stale_config_when_tool_is_disabled():
    controller = PersonaController()
    controller._mail_config_service = SimpleNamespace(get_config=AsyncMock())

    result = await controller._validate_mcp_tool_configs(
        user_id="user-1",
        mcp_tools=["web_search"],
        mcp_tool_configs={"send_email": {"mail_config_id": "config-1"}},
    )

    assert result == {}
    controller._mail_config_service.get_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_mail_tool_accepts_active_owned_config():
    controller = PersonaController()
    controller._mail_config_service = SimpleNamespace(
        get_config=AsyncMock(return_value={"id": "config-1", "is_active": True})
    )

    result = await controller._validate_mcp_tool_configs(
        user_id="user-1",
        mcp_tools=["send_email"],
        mcp_tool_configs={"send_email": {"mail_config_id": "config-1"}},
    )

    assert result == {"send_email": {"mail_config_id": "config-1"}}
    controller._mail_config_service.get_config.assert_awaited_once_with("user-1", "config-1")
