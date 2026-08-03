from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from controller.persona_controller import PersonaController


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
