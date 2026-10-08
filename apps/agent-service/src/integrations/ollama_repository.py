"""HTTP adapter for the built-in Ollama service.

Every call goes through the shared pooled client, so a chat turn that touches
Ollama several times (version, tags, show, pull) reuses one connection instead
of dialling a new one per call. The streaming pull deliberately does **not**
close the client: it is process-wide, and closing it would break every other
in-flight Ollama request.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from config_manager import env
from error_contract import DependencyResponseError, raise_for_httpx_response

from core.http import outbound


class OllamaRepository:
    """Wraps the Ollama HTTP API used by the built-in provider."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or env.OLLAMA_BASE_URL).rstrip("/")

    async def get_version(self) -> str:
        response = await outbound.request(outbound.OLLAMA, "GET", f"{self.base_url}/api/version", timeout=5.0)
        raise_for_httpx_response(response)
        try:
            data = response.json()
        except ValueError as error:
            raise DependencyResponseError() from error
        if not isinstance(data, dict):
            raise DependencyResponseError()
        return str(data.get("version") or "")

    async def list_models(self) -> list[dict[str, Any]]:
        response = await outbound.request(outbound.OLLAMA, "GET", f"{self.base_url}/api/tags", timeout=5.0)
        raise_for_httpx_response(response)
        try:
            data = response.json()
        except ValueError as error:
            raise DependencyResponseError() from error
        if not isinstance(data, dict):
            raise DependencyResponseError()
        models = data.get("models")
        return models if isinstance(models, list) else []

    async def show_model(self, model_name: str) -> dict[str, Any]:
        response = await outbound.request(
            outbound.OLLAMA,
            "POST",
            f"{self.base_url}/api/show",
            timeout=5.0,
            json={"name": model_name},
        )
        raise_for_httpx_response(response)
        try:
            data = response.json()
        except ValueError as error:
            raise DependencyResponseError() from error
        return data if isinstance(data, dict) else {}

    async def delete_model(self, model_name: str) -> bool:
        response = await outbound.request(
            outbound.OLLAMA,
            "DELETE",
            f"{self.base_url}/api/delete",
            timeout=20.0,
            json={"name": model_name},
        )
        if response.status_code == 404:
            return False
        raise_for_httpx_response(response)
        return True

    async def stream_pull(self, model_name: str) -> AsyncIterator[str]:
        # No read timeout: a pull can run for minutes and the SSE-style progress
        # lines are the only sign of life. The client itself stays open.
        client = outbound.get_client(outbound.OLLAMA)
        async with client.stream(
            "POST",
            f"{self.base_url}/api/pull",
            json={"name": model_name, "stream": True},
            timeout=None,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    yield line
