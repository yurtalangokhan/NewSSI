import pytest

from domain.providers.service import (
    KNOWN_MODELS_BY_PROVIDER,
    WELL_KNOWN_PROVIDERS,
    ProviderService,
)


class _RepoThatFails:
    async def list_url_providers(self, user_id: str):
        raise RuntimeError("url provider query failed")

    async def list_user_providers(self, user_id: str):
        raise RuntimeError("api-key provider query failed")


class _ProviderServiceWithBrokenProvider(ProviderService):
    async def list_all(self, user_id: str):
        return {
            "builtin": [],
            "url_providers": [
                {
                    "id": "provider-1",
                    "name": "Broken Provider",
                    "provider_type": "openai_compatible",
                    "base_url": "http://example.invalid",
                    "config": "not-a-dict",
                    "user_config": {"default_model": "fallback-model"},
                }
            ],
            "user_providers": [],
        }

    async def _get_provider_api_key(self, provider: dict, user_id: str):
        raise RuntimeError("api key cannot be decrypted")


@pytest.mark.asyncio
async def test_list_all_degrades_when_repository_queries_fail():
    service = ProviderService(_RepoThatFails())

    providers = await service.list_all("user-1")

    assert providers["url_providers"] == []
    assert providers["user_providers"] == []
    assert isinstance(providers["builtin"], list)


@pytest.mark.asyncio
async def test_available_models_keeps_default_model_when_provider_metadata_is_invalid():
    service = _ProviderServiceWithBrokenProvider(_RepoThatFails())

    providers = await service.get_available_models_for_user("user-1")

    assert providers == [
        {
            "id": "provider-1",
            "name": "Broken Provider",
            "provider": "openai_compatible",
            "provider_display_name": "Broken Provider",
            "model_configurations": [
                {
                    "name": "fallback-model",
                    "display_name": "fallback-model",
                    "is_visible": True,
                    "max_input_tokens": None,
                    "supports_image_input": False,
                    "supports_reasoning": False,
                    "is_remote": False,
                }
            ],
        }
    ]


class _ProviderServiceWithApiKeyProvider(ProviderService):
    async def list_all(self, user_id: str):
        return {
            "builtin": [],
            "url_providers": [],
            "user_providers": [
                {
                    "id": "provider-1",
                    "name": "OpenAI",
                    "provider_type": "openai",
                    "config": {},
                    "user_config": {"default_model": "gpt-live"},
                }
            ],
        }

    async def _get_provider_api_key(self, provider: dict, user_id: str):
        return "test-key"

    @staticmethod
    async def _fetch_api_key_provider_models(**kwargs):
        return [
            {
                "name": "gpt-live",
                "display_name": "GPT Live",
                "max_input_tokens": 128000,
                "supports_image_input": True,
                "supports_reasoning": True,
                "is_remote": True,
            }
        ]


@pytest.mark.asyncio
async def test_available_models_prefers_live_api_key_provider_models():
    service = _ProviderServiceWithApiKeyProvider(_RepoThatFails())

    providers = await service.get_available_models_for_user("user-1")

    assert providers[0]["model_configurations"] == [
        {
            "name": "gpt-live",
            "display_name": "GPT Live",
            "is_visible": True,
            "max_input_tokens": 128000,
            "supports_image_input": True,
            "supports_reasoning": True,
            "is_remote": True,
        }
    ]


def test_no_provider_hardcodes_a_model_catalog():
    """Every provider's models come from live discovery, not a stale in-code
    list — ids get renamed/retired on each vendor's own schedule."""
    assert KNOWN_MODELS_BY_PROVIDER == {}


def test_no_well_known_api_key_provider_hardcodes_a_default_model():
    api_key_providers = [p for p in WELL_KNOWN_PROVIDERS if p.get("category") == "api_key"]
    assert api_key_providers
    for provider in api_key_providers:
        assert provider.get("recommended_default_model") is None, provider["provider_type"]
        assert provider.get("known_models") == [], provider["provider_type"]


@pytest.mark.parametrize(
    "model_name, selectable",
    [
        ("gemini-3.6-flash", True),
        ("gemini-3.1-pro-preview", True),
        ("gemini-2.5-flash", True),
        ("gemini-flash-latest", False),
        ("gemini-pro-latest", False),
        ("gemini-flash-lite-latest", False),
    ],
)
def test_unversioned_latest_gemini_aliases_are_not_selectable(model_name, selectable):
    """`*-latest` aliases break multi-turn tool use (langchain-google-genai only
    recognises literal `gemini-3` names for the thought_signature round-trip), so
    discovery must not surface them."""
    from domain.providers.service import _is_selectable_gemini_model

    assert _is_selectable_gemini_model(model_name) is selectable


@pytest.mark.parametrize(
    "provider_type",
    ["mistral", "cohere", "groq", "deepseek", "openrouter", "together"],
)
def test_generic_connection_test_resolves_a_base_url_for_known_providers(provider_type):
    """`_test_generic_openai_api` used to keep its own partial base-URL map, so
    Mistral/Cohere fell through to 'No base_url configured'. It now shares
    `_default_api_base_for_provider`."""
    assert ProviderService._default_api_base_for_provider(provider_type)
