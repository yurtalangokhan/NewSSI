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

        # DB providers use UUID ids. Built-ins use provider_type ids like "ollama".
        try:
            uuid.UUID(provider_id)
            provider = await self._repo.get_url_provider(provider_id, user_id)
        except ValueError:
            provider = self._resolve_builtin_provider(provider_id)

        if not provider:
            return []

        return await self._fetch_models_by_type(
            provider.get("provider_type", ""),
            provider.get("base_url"),
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

    async def _fetch_models_by_type(self, provider_type: str, base_url: str | None) -> list[dict[str, Any]]:
        if not base_url:
            return []

        if provider_type == "ollama":
            return await self._fetch_ollama_models(base_url)
        if provider_type in ("vllm", "openai_compatible", "litellm"):
            return await self._fetch_vllm_models(base_url)
        return []

    async def test_connection(self, provider_type: str, base_url: str | None, api_key: str | None) -> dict[str, Any]:
        """Test connectivity to a provider. Returns {success, latency_ms, error}."""
        import time
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

        if ptype == "ollama":
            models = await self._fetch_ollama_models(base_url)
        elif ptype in ("vllm", "openai_compatible", "litellm"):
            models = await self._fetch_vllm_models(base_url)
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
    async def _fetch_vllm_models(base_url: str) -> list[dict[str, Any]]:
        """Fetch models from a vLLM / OpenAI-compatible endpoint."""
        import httpx

        origin = ProviderService._extract_origin(base_url)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{origin}/v1/models")
                if not resp.is_success:
                    return []
                return [
                    {
                        "name": m.get("id", ""),
                        "provider_type": "vllm",
                        "max_input_tokens": m.get("max_model_len"),
                        "supports_image_input": False,
                        "supports_reasoning": False,
                    }
                    for m in resp.json().get("data", [])
                ]
        except Exception as e:
            logger.warning("Failed to fetch vLLM models from %s: %s", origin, e)
            return []
