import uuid
import pytest
from unittest.mock import AsyncMock
from types import SimpleNamespace
from src.service.user_service import UserService

@pytest.mark.asyncio
async def test_get_current_user_includes_pinned_assistants_in_preferences():
    user_id = uuid.uuid4()
    mock_user = SimpleNamespace(
        id=user_id,
        email="test@example.com",
        first_name="Ali",
        last_name="Pekisik",
        role="user",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        invited=False,
        password_configured=True,
        team_name=None,
        keycloak_id=None,
        username="ali",
        created_at=None,
        updated_at=None,
    )
    mock_settings = SimpleNamespace(
        pinned_assistants=[1, 2, 5],
        default_model="gpt-4o",
        default_provider_id=None,
        auto_scroll=True,
        shortcut_enabled=True,
        theme_preference="dark",
        chat_background=None,
        default_app_mode="AUTO",
        work_role="engineer",
        memories=[],
        use_memories=False,
        enable_memory_tool=False,
        user_preferences="",
        long_term_memory_enabled=False,
        extract_memory=False,
    )


    service = UserService()
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=mock_user),
    )
    service.settings_repo = SimpleNamespace(
        ensure_defaults=AsyncMock(return_value=mock_settings),
    )
    service.keycloak = SimpleNamespace(is_enabled=lambda: False)

    result = await service.get_current_user(str(user_id))

    assert "preferences" in result
    assert result["preferences"]["pinned_assistants"] == [1, 2, 5]
