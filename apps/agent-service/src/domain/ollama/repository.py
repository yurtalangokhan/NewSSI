"""HTTP adapter for the built-in Ollama service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.env import env
from core.settings import settings


class OllamaRepository:
    """Wraps the Ollama HTTP API used by the built-in provider."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or env.OLLAMA_BASE_URL or settings.OLLAMA_BASE_URL).rstrip("/")

    async def get_version(self) -> str:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self.base_url}/api/version")
            response.raise_for_status()
            data = response.json()
            return str(data.get("version") or "")

    async def list_models(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            models = data.get("models")
            return models if isinstance(models, list) else []

    async def show_model(self, model_name: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{self.base_url}/api/show",
                json={"name": model_name},
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}

    async def delete_model(self, model_name: str) -> bool:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.request(
                "DELETE",
                f"{self.base_url}/api/delete",
                json={"name": model_name},
            )
            if response.status_code == 404:
                return False
            response.raise_for_status()
            return True

    async def stream_pull(self, model_name: str) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/pull",
                json={"name": model_name, "stream": True},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        yield line
