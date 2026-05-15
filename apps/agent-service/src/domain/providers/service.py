"""Business logic for provider management."""
from __future__ import annotations

from typing import Any

from core.logger import get_logger
from domain.providers.repository import ProviderRepository

logger = get_logger(__name__)

def _known_model(
    name: str,
    *,
    display_name: str | None = None,
    supports_image_input: bool = False,
    supports_reasoning: bool = False,
    max_input_tokens: int | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "display_name": display_name or name,
        "is_visible": True,
        "max_input_tokens": max_input_tokens,
        "supports_image_input": supports_image_input,
        "supports_reasoning": supports_reasoning,
    }


KNOWN_MODELS_BY_PROVIDER: dict[str, list[dict[str, Any]]] = {
    "openai": [
        _known_model("gpt-5", supports_reasoning=True, max_input_tokens=200000),
        _known_model("gpt-5-mini", supports_reasoning=True, max_input_tokens=200000),
        _known_model("gpt-4.1", supports_image_input=True, max_input_tokens=128000),
        _known_model("gpt-4o", supports_image_input=True, max_input_tokens=128000),
    ],
    "anthropic": [
        _known_model("claude-opus-4-1", supports_image_input=True, supports_reasoning=True, max_input_tokens=200000),
        _known_model("claude-sonnet-4", supports_image_input=True, supports_reasoning=True, max_input_tokens=200000),
        _known_model("claude-3-7-sonnet-latest", supports_image_input=True, max_input_tokens=200000),
    ],
    "google_genai": [
        _known_model("gemini-2.5-pro", supports_image_input=True, supports_reasoning=True, max_input_tokens=1000000),
        _known_model("gemini-2.5-flash", supports_image_input=True, max_input_tokens=1000000),
        _known_model("gemini-2.0-flash", supports_image_input=True, max_input_tokens=1000000),
    ],
    "google_vertexai": [
        _known_model("gemini-2.5-pro", supports_image_input=True, supports_reasoning=True, max_input_tokens=1000000),
        _known_model("gemini-2.5-flash", supports_image_input=True, max_input_tokens=1000000),
    ],
    "azure_openai": [
        _known_model("gpt-5", supports_reasoning=True, max_input_tokens=200000),
        _known_model("gpt-4.1", supports_image_input=True, max_input_tokens=128000),
        _known_model("gpt-4o", supports_image_input=True, max_input_tokens=128000),
    ],
    "aws_bedrock": [
        _known_model("anthropic.claude-3-7-sonnet-20250219-v1:0", supports_image_input=True, max_input_tokens=200000),
        _known_model("anthropic.claude-3-5-sonnet-20241022-v2:0", supports_image_input=True, max_input_tokens=200000),
        _known_model("amazon.nova-pro-v1:0", supports_image_input=True, max_input_tokens=300000),
    ],
    "groq": [
        _known_model("llama-3.3-70b-versatile", max_input_tokens=131072),
        _known_model("llama-3.1-8b-instant", max_input_tokens=131072),
        _known_model("mixtral-8x7b-32768", max_input_tokens=32768),
    ],
    "mistral": [
        _known_model("mistral-large-latest", supports_reasoning=True, max_input_tokens=128000),
        _known_model("mistral-medium-latest", max_input_tokens=128000),
        _known_model("ministral-8b-latest", max_input_tokens=128000),
    ],
    "cohere": [
        _known_model("command-a-03-2025", max_input_tokens=128000),
        _known_model("command-r-plus", max_input_tokens=128000),
        _known_model("command-r", max_input_tokens=128000),
    ],
    "deepseek": [
        _known_model("deepseek-chat", max_input_tokens=128000),
        _known_model("deepseek-reasoner", supports_reasoning=True, max_input_tokens=128000),
    ],
    "xai": [
        _known_model("grok-3-beta", supports_reasoning=True, max_input_tokens=131072),
        _known_model("grok-2-vision", supports_image_input=True, max_input_tokens=32768),
    ],
    "perplexity": [
        _known_model("sonar-pro", supports_reasoning=True, max_input_tokens=127000),
        _known_model("sonar", max_input_tokens=127000),
    ],
    "together": [
        _known_model("meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", max_input_tokens=131072),
        _known_model("Qwen/Qwen2.5-72B-Instruct-Turbo", max_input_tokens=32768),
    ],
    "fireworks": [
        _known_model("accounts/fireworks/models/llama-v3p1-70b-instruct", max_input_tokens=131072),
        _known_model("accounts/fireworks/models/mixtral-8x22b-instruct", max_input_tokens=65536),
    ],
    "cerebras": [
        _known_model("llama-3.3-70b", max_input_tokens=131072),
        _known_model("llama-3.1-8b", max_input_tokens=131072),
    ],
    "huggingface": [
        _known_model("meta-llama/Llama-3.1-70B-Instruct", max_input_tokens=131072),
        _known_model("Qwen/Qwen2.5-72B-Instruct", max_input_tokens=32768),
    ],
    "nvidia": [
        _known_model("meta/llama-3.1-70b-instruct", max_input_tokens=131072),
        _known_model("google/gemma-2-9b-it", max_input_tokens=8192),
    ],
    "ibm_watsonx": [
        _known_model("ibm/granite-3-8b-instruct", max_input_tokens=32768),
        _known_model("meta-llama/llama-3-1-70b-instruct", max_input_tokens=131072),
    ],
    "sambanova": [
        _known_model("Meta-Llama-3.1-405B-Instruct", max_input_tokens=131072),
        _known_model("Meta-Llama-3.1-70B-Instruct", max_input_tokens=131072),
    ],
    "openrouter": [
        _known_model("openai/gpt-5", supports_reasoning=True, max_input_tokens=200000),
        _known_model("anthropic/claude-sonnet-4", supports_image_input=True, supports_reasoning=True, max_input_tokens=200000),
        _known_model("google/gemini-2.5-pro", supports_image_input=True, supports_reasoning=True, max_input_tokens=1000000),
    ],
}


def _well_known_api_key(
    name: str,
    provider_type: str,
    *,
    icon: str,
    default_model: str | None = None,
    default_model_display: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "provider_type": provider_type,
        "category": "api_key",
        "icon": icon,
        "known_models": KNOWN_MODELS_BY_PROVIDER.get(provider_type, []),
        "recommended_default_model": (
            {"name": default_model, "display_name": default_model_display or default_model}
            if default_model
            else None
        ),
    }


WELL_KNOWN_PROVIDERS: list[dict[str, Any]] = [
    # URL-based
    {"name": "Ollama", "provider_type": "ollama", "category": "url_based", "icon": "ollama"},
    {"name": "vLLM", "provider_type": "vllm", "category": "url_based", "icon": "cpu"},
    {"name": "OpenAI-Compatible", "provider_type": "openai_compatible", "category": "url_based", "icon": "openai"},
    {"name": "LiteLLM Proxy", "provider_type": "litellm", "category": "url_based", "icon": "cpu"},
    # API-key-based
    _well_known_api_key("OpenAI", "openai", icon="openai", default_model="gpt-5"),
    _well_known_api_key("Anthropic", "anthropic", icon="anthropic", default_model="claude-sonnet-4"),
    _well_known_api_key("Google Gemini", "google_genai", icon="google", default_model="gemini-2.5-pro"),
    _well_known_api_key("Google Vertex AI", "google_vertexai", icon="google", default_model="gemini-2.5-pro"),
    _well_known_api_key("Azure OpenAI", "azure_openai", icon="azure", default_model="gpt-5"),
    _well_known_api_key("Azure AI", "azure_ai", icon="azure"),
    _well_known_api_key("AWS Bedrock", "aws_bedrock", icon="amazon", default_model="anthropic.claude-3-7-sonnet-20250219-v1:0", default_model_display="Anthropic Claude 3.7 Sonnet"),
    _well_known_api_key("Groq", "groq", icon="cpu", default_model="llama-3.3-70b-versatile", default_model_display="Llama 3.3 70B Versatile"),
    _well_known_api_key("MistralAI", "mistral", icon="mistral", default_model="mistral-large-latest"),
    _well_known_api_key("Cohere", "cohere", icon="cpu", default_model="command-a-03-2025"),
    _well_known_api_key("DeepSeek", "deepseek", icon="deepseek", default_model="deepseek-chat"),
    _well_known_api_key("xAI (Grok)", "xai", icon="cpu", default_model="grok-3-beta"),
    _well_known_api_key("Perplexity", "perplexity", icon="cpu", default_model="sonar-pro"),
    _well_known_api_key("Together AI", "together", icon="cpu", default_model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", default_model_display="Llama 3.1 70B Turbo"),
    _well_known_api_key("Fireworks AI", "fireworks", icon="cpu", default_model="accounts/fireworks/models/llama-v3p1-70b-instruct", default_model_display="Llama v3.1 70B"),
    _well_known_api_key("Cerebras", "cerebras", icon="cpu", default_model="llama-3.3-70b"),
    _well_known_api_key("HuggingFace", "huggingface", icon="cpu", default_model="meta-llama/Llama-3.1-70B-Instruct", default_model_display="Llama 3.1 70B Instruct"),
    _well_known_api_key("NVIDIA AI", "nvidia", icon="cpu", default_model="meta/llama-3.1-70b-instruct", default_model_display="Llama 3.1 70B Instruct"),
    _well_known_api_key("IBM WatsonX", "ibm_watsonx", icon="cpu", default_model="ibm/granite-3-8b-instruct", default_model_display="granite-3-8b-instruct"),
    _well_known_api_key("SambaNova", "sambanova", icon="cpu", default_model="Meta-Llama-3.1-405B-Instruct", default_model_display="Llama 3.1 405B Instruct"),
    _well_known_api_key("OpenRouter", "openrouter", icon="openrouter", default_model="openai/gpt-5", default_model_display="OpenAI GPT-5"),
]

_WELL_KNOWN_BY_TYPE: dict[str, dict[str, Any]] = {p["provider_type"]: p for p in WELL_KNOWN_PROVIDERS}


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

    async def get_available_models_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """Return all user-visible providers flattened for model selection UIs."""
        all_providers = await self.list_all(user_id)
        results: list[dict[str, Any]] = []

        # URL providers (builtin + DB URL providers) persist synced model metadata
        # in provider.config.model_configurations.
        for provider in [
            *all_providers.get("builtin", []),
            *all_providers.get("url_providers", []),
        ]:
            config = provider.get("config") or {}
            model_configurations = config.get("model_configurations") or []
            if not isinstance(model_configurations, list):
                model_configurations = []

            # Existing providers may not have synced model_configurations yet.
            # In that case, discover models live from the provider endpoint.
            if not model_configurations:
                api_key = await self._get_provider_api_key(provider, user_id)
                live_models = await self._fetch_models_by_type(
                    provider.get("provider_type", ""),
                    provider.get("base_url"),
                    api_key=api_key,
                )
                model_configurations = [
                    {
                        "name": m.get("name"),
                        "display_name": m.get("name"),
                        "is_visible": True,
                        "max_input_tokens": m.get("max_input_tokens"),
                        "supports_image_input": m.get("supports_image_input", False),
                        "supports_reasoning": m.get("supports_reasoning", False),
                    }
                    for m in live_models
                    if m.get("name")
                ]

            # Keep an explicit default model selectable even if discovery fails.
            default_model = (provider.get("user_config") or {}).get("default_model")
            if default_model and not any(m.get("name") == default_model for m in model_configurations):
                model_configurations.append(_known_model(default_model))

            results.append(
                {
                    "id": provider.get("id"),
                    "name": provider.get("name") or provider.get("provider_type"),
                    "provider": provider.get("provider_type"),
                    "provider_display_name": provider.get("name") or provider.get("provider_type"),
                    "model_configurations": model_configurations,
                }
            )

        # API-key providers use the well-known provider catalog as the source of
        # truth (enterprise-safe, deterministic model options).
        for provider in all_providers.get("user_providers", []):
            default_model = (provider.get("user_config") or {}).get("default_model")
            provider_type = provider.get("provider_type")
            known = _WELL_KNOWN_BY_TYPE.get(provider_type, {})
            model_configurations = [
                dict(model) for model in known.get("known_models", [])
            ]

            # Keep user default model selectable even if it is custom and not in catalog.
            if default_model and not any(m.get("name") == default_model for m in model_configurations):
                model_configurations.append(_known_model(default_model))

            provider_display_name = known.get("name") or provider.get("name") or provider_type

            results.append(
                {
                    "id": provider.get("id"),
                    "name": provider.get("name") or provider_display_name,
                    "provider": provider_type,
                    "provider_display_name": provider_display_name,
                    "model_configurations": model_configurations,
                }
            )

        return results

    async def create_url_provider(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self._check_builtin_collision(data)
        created = await self._repo.create_url_provider(user_id, data)
        # Best-effort: auto-sync model capabilities from the provider
        try:
            created = await self.sync_models_for_provider(created["id"], user_id)
        except Exception as exc:
            logger.warning("Auto-sync models failed for new provider %s: %s", created.get("id"), exc)
        return created

    async def update_url_provider(self, provider_id: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        result = await self._repo.update_url_provider(provider_id, user_id, data)
        if result is None:
            raise ValueError("Provider not found or cannot be updated")
        return result

    async def delete_url_provider(self, provider_id: str, user_id: str) -> bool:
        return await self._repo.delete_url_provider(provider_id, user_id)

    async def create_user_provider(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return await self._repo.create_user_provider(user_id, data)

    async def update_user_provider(self, provider_id: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        result = await self._repo.update_user_provider(provider_id, user_id, data)
        if result is None:
            raise ValueError("Provider not found or cannot be updated")
        return result

    async def delete_user_provider(self, provider_id: str, user_id: str) -> bool:
        return await self._repo.delete_user_provider(provider_id, user_id)

    async def reorder_providers(self, user_id: str, ordered_config_ids: list[str]) -> bool:
        return await self._repo.reorder_providers(user_id, ordered_config_ids)

    async def update_provider_default_model(
        self, config_id: str, user_id: str, model: str | None
    ) -> bool:
        return await self._repo.update_provider_default_model(config_id, user_id, model)

    async def get_models_for_provider(self, provider_id: str, user_id: str) -> list[dict[str, Any]]:
        """Fetch available models for either DB-stored or built-in URL-based providers."""
        import uuid

        provider: dict[str, Any] | None = None
        api_key: str | None = None

        # DB providers use UUID ids. Built-ins use provider_type ids like "ollama".
        try:
            uuid.UUID(provider_id)
            provider = await self._repo.get_url_provider(provider_id, user_id)
            if provider:
                api_key = await self._repo.get_decrypted_api_key(provider_id, user_id)
        except ValueError:
            provider = self._resolve_builtin_provider(provider_id)

        if not provider:
            return []

        return await self._fetch_models_by_type(
            provider.get("provider_type", ""),
            provider.get("base_url"),
            api_key=api_key,
        )

    async def get_vllm_models(self, provider_id: str, user_id: str) -> list[dict[str, Any]]:
        provider = await self._repo.get_url_provider(provider_id, user_id)
        if not provider:
            return []
        return await self._fetch_vllm_models(provider["base_url"])

    @staticmethod
    def _resolve_builtin_provider(provider_type: str) -> dict[str, Any] | None:
        from core.providers.registry import provider_registry

        provider_registry.initialize()
        provider = provider_registry.get_provider(provider_type)
        if provider is None:
            return None

        return {
            "provider_type": provider_type,
            "base_url": getattr(provider, "base_url", None),
        }

    async def _fetch_models_by_type(
        self,
        provider_type: str,
        base_url: str | None,
        *,
        api_key: str | None = None,
    ) -> list[dict[str, Any]]:
        if not base_url:
            return []

        if provider_type == "ollama":
            return await self._fetch_ollama_models(base_url)
        if provider_type in ("vllm", "openai_compatible", "litellm"):
            return await self._fetch_vllm_models(base_url, api_key=api_key)
        return []

    async def test_connection(
        self,
        provider_type: str,
        base_url: str | None,
        api_key: str | None,
        provider_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Test connectivity to a provider. Returns {success, latency_ms, error}."""
        import time

        # If provider_id is supplied, resolve persisted config and key.
        if provider_id and user_id:
            resolved_provider = await self._repo.get_url_provider(provider_id, user_id)
            if resolved_provider:
                provider_type = resolved_provider.get("provider_type") or provider_type
                base_url = resolved_provider.get("base_url") or base_url
                if not api_key:
                    api_key = await self._repo.get_decrypted_api_key(provider_id, user_id)

        start = time.monotonic()

        try:
            if provider_type == "ollama":
                result = await self._test_ollama(base_url or "http://localhost:11434")
            elif provider_type in ("vllm", "openai_compatible", "litellm"):
                result = await self._test_openai_compatible(base_url or "", api_key)
            elif provider_type == "openai":
                result = await self._test_openai_api(api_key or "")
            elif provider_type == "anthropic":
                result = await self._test_anthropic(api_key or "")
            elif provider_type in ("google_genai", "google_vertexai"):
                result = await self._test_google_genai(api_key or "")
            else:
                result = await self._test_generic_openai_api(provider_type, api_key or "", base_url)

            latency_ms = round((time.monotonic() - start) * 1000)
            return {"success": result["success"], "latency_ms": latency_ms, "error": result.get("error")}
        except Exception as exc:
            latency_ms = round((time.monotonic() - start) * 1000)
            error_msg = str(exc) or type(exc).__name__
            return {"success": False, "latency_ms": latency_ms, "error": error_msg}

    @staticmethod
    def _extract_origin(url: str) -> str:
        """Return only scheme://host:port, stripping any path/query/fragment."""
        from urllib.parse import urlparse
        parsed = urlparse(url.rstrip("/"))
        if parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return url.rstrip("/")

    @staticmethod
    async def _test_ollama(base_url: str) -> dict[str, Any]:
        import httpx
        from urllib.parse import urlparse
        parsed = urlparse(base_url.rstrip("/"))
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else base_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(f"{origin}/api/tags")
                if resp.is_success:
                    models = resp.json().get("models", [])
                    return {"success": True, "model_count": len(models)}
                return {"success": False, "error": f"HTTP {resp.status_code}"}
        except httpx.ConnectError:
            return {"success": False, "error": f"Cannot connect to {origin}"}
        except httpx.TimeoutException:
            return {"success": False, "error": f"Connection timed out ({origin})"}

    @staticmethod
    async def _test_openai_compatible(base_url: str, api_key: str | None) -> dict[str, Any]:
        import httpx
        from urllib.parse import urlparse
        parsed = urlparse(base_url.rstrip("/"))
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(f"{origin}/v1/models", headers=headers)
                if resp.is_success:
                    return {"success": True}
                return {"success": False, "error": f"HTTP {resp.status_code}"}
        except httpx.ConnectError:
            return {"success": False, "error": f"Cannot connect to {origin}"}
        except httpx.TimeoutException:
            return {"success": False, "error": f"Connection timed out ({origin})"}

    @staticmethod
    async def _test_openai_api(api_key: str) -> dict[str, Any]:
        import httpx
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.is_success:
                return {"success": True}
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}

    @staticmethod
    async def _test_anthropic(api_key: str) -> dict[str, Any]:
        import httpx
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            )
            if resp.is_success:
                return {"success": True}
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}

    @staticmethod
    async def _test_google_genai(api_key: str) -> dict[str, Any]:
        import httpx
        if not api_key:
            return {"success": False, "error": "API key is required"}
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key},
            )
            if resp.is_success:
                return {"success": True}
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}

    @staticmethod
    async def _test_generic_openai_api(provider_type: str, api_key: str, base_url: str | None) -> dict[str, Any]:
        """Fallback: try /v1/models with the api_key as Bearer token."""
        default_base_urls = {
            "openrouter": "https://openrouter.ai/api",
            "deepseek": "https://api.deepseek.com",
            "groq": "https://api.groq.com/openai",
            "xai": "https://api.x.ai",
            "perplexity": "https://api.perplexity.ai",
            "together": "https://api.together.xyz",
            "fireworks": "https://api.fireworks.ai/inference",
            "cerebras": "https://api.cerebras.ai",
            "huggingface": "https://router.huggingface.co",
            "nvidia": "https://integrate.api.nvidia.com",
            "sambanova": "https://api.sambanova.ai",
        }
        resolved_base_url = (base_url or default_base_urls.get(provider_type) or "").rstrip("/")
        if not resolved_base_url:
            return {"success": False, "error": f"No base_url configured for {provider_type}"}
        import httpx
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{resolved_base_url}/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.is_success:
                return {"success": True}
            return {"success": False, "error": f"HTTP {resp.status_code}"}

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

    async def sync_models_for_provider(self, provider_id: str, user_id: str) -> dict[str, Any]:
        """Fetch models from provider, infer capabilities, and persist to config."""
        provider = await self._repo.get_url_provider(provider_id, user_id)
        if not provider:
            raise ValueError("Provider not found")

        ptype = provider["provider_type"]
        base_url = provider["base_url"]
        api_key = await self._repo.get_decrypted_api_key(provider_id, user_id)

        if ptype == "ollama":
            models = await self._fetch_ollama_models(base_url)
        elif ptype in ("vllm", "openai_compatible", "litellm"):
            models = await self._fetch_vllm_models(base_url, api_key=api_key)
        else:
            models = []

        model_configurations = [
            {
                "name": m["name"],
                "is_visible": True,
                "max_input_tokens": m.get("max_input_tokens"),
                "supports_image_input": m.get("supports_image_input", False),
                "supports_reasoning": m.get("supports_reasoning", False),
            }
            for m in models
        ]

        config = dict(provider.get("config") or {})
        config["model_configurations"] = model_configurations

        updated = await self._repo.update_url_provider(
            provider_id, user_id, {**provider, "config": config}
        )
        return updated or provider

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _get_provider_api_key(self, provider: dict[str, Any], user_id: str) -> str | None:
        """Resolve decrypted API key for persisted URL providers."""
        provider_id = provider.get("id")
        if not provider_id or provider.get("is_builtin"):
            return None

        try:
            return await self._repo.get_decrypted_api_key(str(provider_id), user_id)
        except ValueError:
            # Built-in provider ids are not UUIDs.
            return None

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

    # ── Model fetching ───────────────────────────────────────────────────────

    @staticmethod
    def _infer_vllm_reasoning_support(model_payload: dict[str, Any]) -> bool:
        """Infer reasoning support from model metadata without model-name hardcoding."""

        def _contains_reasoning_hint(value: Any) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                return lowered in {"reasoning", "thinking", "reasoner", "cot", "chain_of_thought"}
            if isinstance(value, list):
                return any(_contains_reasoning_hint(item) for item in value)
            if isinstance(value, dict):
                for key, inner in value.items():
                    key_l = str(key).lower()
                    if any(token in key_l for token in ("reason", "think", "cot")):
                        if _contains_reasoning_hint(inner):
                            return True
                    if _contains_reasoning_hint(inner):
                        return True
            return False

        # Common places in OpenAI-compatible / vLLM responses.
        candidates = [
            model_payload.get("capabilities"),
            model_payload.get("supported_capabilities"),
            model_payload.get("supported_features"),
            model_payload.get("metadata"),
            model_payload.get("extra"),
        ]
        if any(_contains_reasoning_hint(candidate) for candidate in candidates):
            return True

        # Fallback: scan full payload for explicit reasoning/thinking markers.
        return _contains_reasoning_hint(model_payload)

    @staticmethod
    def _infer_vllm_image_support(model_payload: dict[str, Any]) -> bool:
        """Infer multimodal/image support from model metadata."""
        for key in ("modalities", "input_modalities", "output_modalities", "capabilities"):
            value = model_payload.get(key)
            if isinstance(value, list):
                lowered = {str(v).lower() for v in value}
                if "image" in lowered or "vision" in lowered or "multimodal" in lowered:
                    return True
            if isinstance(value, dict):
                for k, v in value.items():
                    if str(k).lower() in {"image", "vision", "multimodal"} and bool(v):
                        return True
        return False

    @staticmethod
    async def _fetch_ollama_models(base_url: str) -> list[dict[str, Any]]:
        """Fetch models from Ollama using /api/show capabilities (Ollama >= 0.5.0)."""
        import asyncio
        import httpx

        origin = ProviderService._extract_origin(base_url)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                tags_resp = await client.get(f"{origin}/api/tags")
                if not tags_resp.is_success:
                    return []
                raw_models = tags_resp.json().get("models", [])

                async def _show(model_name: str) -> dict[str, Any]:
                    try:
                        r = await client.post(
                            f"{origin}/api/show",
                            json={"name": model_name},
                            timeout=4.0,
                        )
                        if not r.is_success:
                            return {}
                        data = r.json()

                        # ── Context length ────────────────────────────────
                        ctx_len: int | None = None
                        for key, val in (data.get("model_info") or {}).items():
                            if key.endswith(".context_length") and isinstance(val, int) and val > 0:
                                ctx_len = val
                                break
                        if ctx_len is None and isinstance(data.get("context_length"), int):
                            ctx_len = data["context_length"]

                        # ── Capabilities (Ollama >= 0.5.0) ───────────────
                        # Possible values: "completion", "vision", "thinking", "tools",
                        #                  "embedding", "insert"
                        caps_list: list[str] = data.get("capabilities") or []
                        return {
                            "ctx_len": ctx_len,
                            "supports_image_input": "vision" in caps_list,
                            "supports_reasoning": "thinking" in caps_list,
                        }
                    except Exception:
                        return {}

                show_results = await asyncio.gather(*(_show(m["name"]) for m in raw_models))

                return [
                    {
                        "name": m["name"],
                        "provider_type": "ollama",
                        "size": m.get("size"),
                        "max_input_tokens": show.get("ctx_len"),
                        "supports_image_input": show.get("supports_image_input", False),
                        "supports_reasoning": show.get("supports_reasoning", False),
                    }
                    for m, show in zip(raw_models, show_results)
                ]
        except Exception as e:
            logger.warning("Failed to fetch Ollama models from %s: %s", origin, e)
            return []

    @staticmethod
    async def _fetch_vllm_models(base_url: str, *, api_key: str | None = None) -> list[dict[str, Any]]:
        """Fetch models from a vLLM / OpenAI-compatible endpoint."""
        import httpx

        origin = ProviderService._extract_origin(base_url)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{origin}/v1/models", headers=headers)
                if not resp.is_success:
                    return []
                return [
                    {
                        "name": m.get("id", ""),
                        "provider_type": "vllm",
                        "max_input_tokens": m.get("max_model_len") or m.get("context_length") or m.get("max_input_tokens"),
                        "supports_image_input": ProviderService._infer_vllm_image_support(m),
                        "supports_reasoning": ProviderService._infer_vllm_reasoning_support(m),
                    }
                    for m in resp.json().get("data", [])
                ]
        except Exception as e:
            logger.warning("Failed to fetch vLLM models from %s: %s", origin, e)
            return []
