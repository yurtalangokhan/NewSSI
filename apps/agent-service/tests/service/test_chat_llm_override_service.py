"""Spec: turning a provider/model pair into a live client is one reusable step.

Chat sending and auto-naming both need it; the "clear the override rather than
fall back" rule stays with ``apply_provider_llm_override``.
"""

from unittest.mock import AsyncMock, patch

import pytest

import service.chat.chat_llm_override_service as svc


def _provider(**over) -> dict:
    return {"id": "provider-1", "is_builtin": False, "base_url": None, "provider_type": "google_genai", **over}


class _Repo:
    async def get_decrypted_api_key(self, provider_id, user_id):
        return "secret-key"


@pytest.fixture
def _registry():
    with (
        patch.object(svc, "provider_repository", return_value=_Repo()),
        patch.object(svc, "_resolve_model_supports_reasoning", new=AsyncMock(return_value=None)),
        patch("infrastructure.llm.llm_factory.get_llm_for_provider", new=AsyncMock(return_value="LIVE")) as factory,
    ):
        yield factory


@pytest.mark.asyncio
async def test_resolve_provider_llm_builds_the_client_with_the_users_key(_registry) -> None:
    with patch.object(svc, "_resolve_provider_for_user", new=AsyncMock(return_value=_provider())):
        llm = await svc.resolve_provider_llm(
            model_name="gemini-3.8-flash", provider_id="provider-1", provider_type="google_genai", user_id="user-1"
        )

    assert llm == "LIVE"
    args, kwargs = _registry.call_args
    assert args == ("gemini-3.8-flash", "google_genai")
    assert kwargs["api_key"] == "secret-key"


@pytest.mark.asyncio
async def test_resolve_provider_llm_returns_none_when_the_provider_is_not_visible(_registry) -> None:
    with patch.object(svc, "_resolve_provider_for_user", new=AsyncMock(return_value=None)):
        llm = await svc.resolve_provider_llm(
            model_name="m", provider_id="provider-9", provider_type="google_genai", user_id="user-1"
        )

    assert llm is None
    _registry.assert_not_called()


@pytest.mark.asyncio
async def test_apply_override_still_strips_the_model_when_the_provider_is_not_visible(_registry) -> None:
    override = {"model": "gemini-3.8-flash", "provider_id": "provider-9", "provider_type": "google_genai"}
    with patch.object(svc, "_resolve_provider_for_user", new=AsyncMock(return_value=None)):
        result = await svc.apply_provider_llm_override(override, "user-1")

    assert result == {}


@pytest.mark.asyncio
async def test_apply_override_attaches_the_live_client(_registry) -> None:
    override = {"model": "gemini-3.8-flash", "provider_id": "provider-1", "provider_type": "google_genai"}
    with patch.object(svc, "_resolve_provider_for_user", new=AsyncMock(return_value=_provider())):
        result = await svc.apply_provider_llm_override(override, "user-1")

    assert result["llm_instance"] == "LIVE"
    assert result["model"] == "gemini-3.8-flash"
