"""Business logic for provider management."""
from __future__ import annotations

from typing import Any

from core.logger import get_logger
from domain.providers.repository import ProviderRepository

logger = get_logger(__name__)

WELL_KNOWN_PROVIDERS: list[dict[str, str]] = [
    # URL-based
    {"name": "Ollama", "provider_type": "ollama", "category": "url_based", "icon": "ollama"},
    {"name": "vLLM", "provider_type": "vllm", "category": "url_based", "icon": "cpu"},
    {"name": "OpenAI-Compatible", "provider_type": "openai_compatible", "category": "url_based", "icon": "openai"},
    {"name": "LiteLLM Proxy", "provider_type": "litellm", "category": "url_based", "icon": "cpu"},
    # API-key-based
    {"name": "OpenAI", "provider_type": "openai", "category": "api_key", "icon": "openai"},
    {"name": "Anthropic", "provider_type": "anthropic", "category": "api_key", "icon": "anthropic"},
    {"name": "Google Gemini", "provider_type": "google_genai", "category": "api_key", "icon": "google"},
    {"name": "Google Vertex AI", "provider_type": "google_vertexai", "category": "api_key", "icon": "google"},
    {"name": "Azure OpenAI", "provider_type": "azure_openai", "category": "api_key", "icon": "azure"},
    {"name": "Azure AI", "provider_type": "azure_ai", "category": "api_key", "icon": "azure"},
    {"name": "AWS Bedrock", "provider_type": "aws_bedrock", "category": "api_key", "icon": "amazon"},
    {"name": "Groq", "provider_type": "groq", "category": "api_key", "icon": "cpu"},
    {"name": "MistralAI", "provider_type": "mistral", "category": "api_key", "icon": "mistral"},
    {"name": "Cohere", "provider_type": "cohere", "category": "api_key", "icon": "cpu"},
    {"name": "DeepSeek", "provider_type": "deepseek", "category": "api_key", "icon": "deepseek"},
    {"name": "xAI (Grok)", "provider_type": "xai", "category": "api_key", "icon": "cpu"},
    {"name": "Perplexity", "provider_type": "perplexity", "category": "api_key", "icon": "cpu"},
    {"name": "Together AI", "provider_type": "together", "category": "api_key", "icon": "cpu"},
    {"name": "Fireworks AI", "provider_type": "fireworks", "category": "api_key", "icon": "cpu"},
    {"name": "Cerebras", "provider_type": "cerebras", "category": "api_key", "icon": "cpu"},
    {"name": "HuggingFace", "provider_type": "huggingface", "category": "api_key", "icon": "cpu"},
    {"name": "NVIDIA AI", "provider_type": "nvidia", "category": "api_key", "icon": "cpu"},
    {"name": "IBM WatsonX", "provider_type": "ibm_watsonx", "category": "api_key", "icon": "cpu"},
    {"name": "SambaNova", "provider_type": "sambanova", "category": "api_key", "icon": "cpu"},
    {"name": "OpenRouter", "provider_type": "openrouter", "category": "api_key", "icon": "openrouter"},
]

_WELL_KNOWN_BY_TYPE: dict[str, dict[str, str]] = {p["provider_type"]: p for p in WELL_KNOWN_PROVIDERS}


class ProviderService:
    def __init__(self, repo: ProviderRepository) -> None:
        self._repo = repo

    async def list_all(self, user_id: str) -> dict[str, Any]:
        """Return builtin providers (from env) + DB-stored providers."""
        from core.providers.registry import provider_registry
        provider_registry.initialize()

        builtin = []
        for name, prov in provider_registry.get_all_providers().items():
            builtin.append({
                "id": name,
                "name": prov.display_name,
                "provider_type": name,
                "base_url": getattr(prov, "base_url", None),
                "is_active": True,
                "is_builtin": True,
                "has_api_key": False,
                "config": {},
            })

        url_providers = await self._repo.list_url_providers(user_id)
        user_providers = await self._repo.list_user_providers(user_id)

        return {
            "builtin": builtin,
            "url_providers": url_providers,
            "user_providers": user_providers,
        }

    async def create_url_provider(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self._check_builtin_collision(data)
        return await self._repo.create_url_provider(user_id, data)

    async def update_url_provider(self, provider_id: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        result = await self._repo.update_url_provider(provider_id, user_id, data)
        if result is None:
            raise ValueError("Provider not found or cannot be updated")
        return result

    async def delete_url_provider(self, provider_id: str, user_id: str) -> bool:
        return await self._repo.delete_url_provider(provider_id, user_id)

    async def create_user_provider(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return await self._repo.create_user_provider(user_id, data)

    async def delete_user_provider(self, provider_id: str, user_id: str) -> bool:
        return await self._repo.delete_user_provider(provider_id, user_id)

    async def get_models_for_provider(self, provider_id: str, user_id: str) -> list[dict[str, Any]]:
        """Fetch available models for a DB-stored URL-based provider."""
        provider = await self._repo.get_url_provider(provider_id, user_id)
        if not provider:
            return []

        ptype = provider["provider_type"]
        base_url = provider["base_url"]

        if ptype == "ollama":
            return await self._fetch_ollama_models(base_url)
        if ptype in ("vllm", "openai_compatible"):
            return await self._fetch_vllm_models(base_url)
        return []

    async def get_vllm_models(self, provider_id: str, user_id: str) -> list[dict[str, Any]]:
        provider = await self._repo.get_url_provider(provider_id, user_id)
        if not provider:
            return []
        return await self._fetch_vllm_models(provider["base_url"])

    async def stream_ollama_pull(self, model_name: str, provider_id: str, user_id: str):
        """Stream Ollama model pull progress as SSE."""
        import httpx

        if provider_id == "builtin":
            from core.env import env
            base_url = env.OLLAMA_BASE_URL or "http://localhost:11434"
        else:
            provider = await self._repo.get_url_provider(provider_id, user_id)
            base_url = provider["base_url"] if provider else "http://localhost:11434"

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{base_url}/api/pull",
                json={"name": model_name, "stream": True},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        yield f"data: {line}\n\n"
        yield 'data: {"status":"done"}\n\n'

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _check_builtin_collision(self, data: dict[str, Any]) -> None:
        from core.env import env
        ptype = data.get("provider_type")
        base_url = data.get("base_url", "").rstrip("/")
        ollama_url = (env.OLLAMA_BASE_URL or "http://localhost:11434").rstrip("/")
        vllm_url = (env.get("VLLM_BASE_URL") or "").rstrip("/")

        if ptype == "ollama" and base_url == ollama_url:
            raise ValueError("This URL is already used by the built-in Ollama provider.")
        if ptype == "vllm" and vllm_url and base_url == vllm_url:
            raise ValueError("This URL is already used by the built-in vLLM provider.")

    @staticmethod
    async def _fetch_ollama_models(base_url: str) -> list[dict[str, Any]]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{base_url}/api/tags")
                if not resp.is_success:
                    return []
                return [
                    {"name": m["name"], "provider_type": "ollama"}
                    for m in resp.json().get("models", [])
                ]
        except Exception as e:
            logger.warning("Failed to fetch Ollama models from %s: %s", base_url, e)
            return []

    @staticmethod
    async def _fetch_vllm_models(base_url: str) -> list[dict[str, Any]]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{base_url}/v1/models")
                if not resp.is_success:
                    return []
                return [
                    {"name": m["id"], "provider_type": "vllm"}
                    for m in resp.json().get("data", [])
                ]
        except Exception as e:
            logger.warning("Failed to fetch vLLM models from %s: %s", base_url, e)
            return []
