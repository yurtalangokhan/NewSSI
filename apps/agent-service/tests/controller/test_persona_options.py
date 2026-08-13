"""Tests for lightweight persona assignment options."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from controller.persona_controller import PersonaController


@pytest.mark.asyncio
async def test_get_persona_options_skips_full_persona_serialization(monkeypatch) -> None:
    """Assignment options return visible identifiers without availability work."""
    controller = PersonaController()
    user = SimpleNamespace(user_id="user-1", roles=[])
    custom_personas = [
        {"id": 12, "name": "Visible", "description": "Assignable", "is_public": True},
        {"id": 13, "name": "Hidden", "description": "Restricted", "is_public": False},
    ]
    monkeypatch.setattr(
        "controller.persona_controller.PersonaDB.list_all",
        AsyncMock(return_value=custom_personas),
    )
    controller._load_agent_group_visibility = AsyncMock(return_value=({13}, set()))
    controller._serialize_custom_persona = AsyncMock(
        side_effect=AssertionError("full serialization must not run")
    )

    result = await controller.get_persona_options(user)  # type: ignore[arg-type]

    assert [(item["id"], item["name"]) for item in result] == [
        (0, "Chatbot"),
        (1, "Configurable MCP Agent"),
        (12, "Visible"),
    ]
    assert result[2]["description"] == "Assignable"
