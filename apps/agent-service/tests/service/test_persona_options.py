"""Tests for lightweight persona assignment options."""

from unittest.mock import AsyncMock

import pytest

from service.auth.auth_service import AuthenticatedUser
from service.personas.persona_service import PersonaService


@pytest.mark.asyncio
async def test_get_persona_options_skips_full_persona_serialization(monkeypatch) -> None:
    """Assignment options return visible identifiers without availability work."""
    service = PersonaService()
    monkeypatch.setattr(
        "integrations.user_service_client.get_user_by_keycloak_id", AsyncMock(return_value=None)
    )
    user = AuthenticatedUser(user_id="user-1", email="")
    custom_personas = [
        {"id": 12, "name": "Visible", "description": "Assignable", "is_public": True},
        {"id": 13, "name": "Hidden", "description": "Restricted", "is_public": False},
    ]
    monkeypatch.setattr(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.list_all",
        AsyncMock(return_value=custom_personas),
    )
    service._load_agent_group_visibility = AsyncMock(return_value=({13}, set()))
    service._can_manage_all_personas = AsyncMock(return_value=False)
    service._serialize_custom_persona = AsyncMock(
        side_effect=AssertionError("full serialization must not run")
    )

    result = await service.get_persona_options(user)  # type: ignore[arg-type]

    assert [(item["id"], item["name"]) for item in result] == [
        (0, "Chatbot"),
        (1, "Configurable MCP Agent"),
        (12, "Visible"),
    ]
    assert result[2]["description"] == "Assignable"
