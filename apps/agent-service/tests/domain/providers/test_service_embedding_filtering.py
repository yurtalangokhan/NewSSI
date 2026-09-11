from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.providers.vllm import VLLMProvider
from domain.flows.resolvers import ResolverContext, _resolve_llm_models
from domain.providers.service import ProviderService


class _MockRepo:
    async def list_url_providers(self, user_id: str):
        return [
            {
                "id": "url-prov-1",
                "name": "Ollama Local",
                "provider_type": "ollama",
                "base_url": "http://localhost:11434",
                "config": {
                    "model_configurations": [
                        {
                            "name": "llama3.2:latest",
                            "is_visible": True,
                            "supports_embedding": False,
                        },
                        {
                            "name": "nomic-embed-text:latest",
                            "is_visible": True,
                            "supports_embedding": True,
                        },
                    ]
                },
                "user_config": {},
            },
            {
                "id": "url-prov-vllm",
                "name": "vLLM Local",
                "provider_type": "vllm",
                "base_url": "http://localhost:8000",
                "config": {
                    "model_configurations": [
                        {
                            "name": "meta-llama/Llama-3.1-8B-Instruct",
                            "is_visible": True,
                            "supports_embedding": False,
                        },
                        {
                            "name": "BAAI/bge-large-en-v1.5",
                            "is_visible": True,
                            "supports_embedding": True,
                        },
                    ]
                },
                "user_config": {},
            },
            {
                "id": "url-prov-lmstudio",
                "name": "LM Studio Local",
                "provider_type": "openai_compatible",
                "base_url": "http://localhost:1234",
                "config": {
                    "model_configurations": [
                        {
                            "name": "qwen2.5-7b-instruct",
                            "is_visible": True,
                            "supports_embedding": False,
                        },
                        {
                            "name": "text-embedding-nomic-embed-text-v1.5",
                            "is_visible": True,
                            "supports_embedding": True,
                        },
                    ]
                },
                "user_config": {},
            },
        ]

    async def list_user_providers(self, user_id: str):
        return [
            {
                "id": "user-prov-1",
                "name": "OpenAI",
                "provider_type": "openai",
                "config": {},
                "user_config": {},
            }
        ]


class _MockProviderService(ProviderService):
    async def _get_provider_api_key(self, provider: dict, user_id: str):
        return "fake-key"

    @staticmethod
    async def _fetch_api_key_provider_models(**kwargs):
        return [
            {
                "name": "gpt-4o",
                "display_name": "GPT-4o",
                "supports_embedding": False,
            },
            {
                "name": "text-embedding-3-small",
                "display_name": "Text Embedding 3 Small",
                "supports_embedding": True,
            },
        ]


@pytest.mark.asyncio
async def test_get_available_models_filters_out_embedding_models():
    service = _MockProviderService(_MockRepo())
    results = await service.get_available_models_for_user("user-1")

    # url-prov-1 (Ollama)
    ollama_prov = next(p for p in results if p["id"] == "url-prov-1")
    ollama_model_names = [m["name"] for m in ollama_prov["model_configurations"]]
    assert "llama3.2:latest" in ollama_model_names
    assert "nomic-embed-text:latest" not in ollama_model_names

    # url-prov-vllm (vLLM)
    vllm_prov = next(p for p in results if p["id"] == "url-prov-vllm")
    vllm_model_names = [m["name"] for m in vllm_prov["model_configurations"]]
    assert "meta-llama/Llama-3.1-8B-Instruct" in vllm_model_names
    assert "BAAI/bge-large-en-v1.5" not in vllm_model_names

    # url-prov-lmstudio (OpenAI Compatible)
    lmstudio_prov = next(p for p in results if p["id"] == "url-prov-lmstudio")
    lmstudio_model_names = [m["name"] for m in lmstudio_prov["model_configurations"]]
    assert "qwen2.5-7b-instruct" in lmstudio_model_names
    assert "text-embedding-nomic-embed-text-v1.5" not in lmstudio_model_names

    # user-prov-1 (OpenAI API key)
    openai_prov = next(p for p in results if p["id"] == "user-prov-1")
    openai_model_names = [m["name"] for m in openai_prov["model_configurations"]]
    assert "gpt-4o" in openai_model_names
    assert "text-embedding-3-small" not in openai_model_names


@pytest.mark.asyncio
async def test_resolve_llm_models_filters_out_embedding_models():
    service = _MockProviderService(_MockRepo())
    items = await _resolve_llm_models(ResolverContext(user_id="user-1"), service=service)
    values = [item.value for item in items]

    assert "llama3.2:latest" in values
    assert "meta-llama/Llama-3.1-8B-Instruct" in values
    assert "qwen2.5-7b-instruct" in values
    assert "gpt-4o" in values

    assert "nomic-embed-text:latest" not in values
    assert "BAAI/bge-large-en-v1.5" not in values
    assert "text-embedding-nomic-embed-text-v1.5" not in values
    assert "text-embedding-3-small" not in values


@pytest.mark.asyncio
async def test_vllm_provider_detects_supports_embedding_flag():
    provider = VLLMProvider()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {
                "id": "meta-llama/Llama-3.1-8B-Instruct",
                "max_model_len": 8192,
                "supports_embedding": False,
            },
            {"id": "BAAI/bge-large-en-v1.5", "max_model_len": 512, "supports_embedding": True},
        ]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_resp

    with patch("core.env.env.get", return_value="http://localhost:8000"):
        with patch("httpx.AsyncClient", return_value=mock_client):
            models = await provider.get_available_models()
            assert len(models) == 2
            llm_model = next(m for m in models if m.name == "meta-llama/Llama-3.1-8B-Instruct")
            embed_model = next(m for m in models if m.name == "BAAI/bge-large-en-v1.5")
            assert llm_model.supports_embedding is False
            assert embed_model.supports_embedding is True
