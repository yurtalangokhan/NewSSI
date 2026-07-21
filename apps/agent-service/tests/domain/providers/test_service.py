import pytest

from domain.providers.service import ProviderService


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
