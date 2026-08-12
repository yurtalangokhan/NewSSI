"""Business logic for managing the built-in Ollama service."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Protocol

from core.logger import get_logger

logger = get_logger(__name__)


class OllamaRepositoryProtocol(Protocol):
    base_url: str

    async def get_version(self) -> str: ...

    async def list_models(self) -> list[dict[str, Any]]: ...

    async def show_model(self, model_name: str) -> dict[str, Any]: ...

    async def delete_model(self, model_name: str) -> bool: ...


class OllamaPullRepositoryProtocol(OllamaRepositoryProtocol, Protocol):
    def stream_pull(self, model_name: str) -> AsyncIterator[str]: ...


class OllamaService:
    def __init__(self, repository: OllamaRepositoryProtocol) -> None:
        self._repository = repository

    async def get_status(self) -> dict[str, Any]:
        try:
            version, models = await asyncio.gather(
                self._repository.get_version(),
                self._repository.list_models(),
            )
            return {
                "base_url": self._repository.base_url,
                "online": True,
                "version": version or None,
                "model_count": len(models),
                "error": None,
            }
        except Exception as exc:
            logger.warning("Built-in Ollama status check failed: %s", exc)
            return {
                "base_url": self._repository.base_url,
                "online": False,
                "version": None,
                "model_count": 0,
                "error": str(exc) or type(exc).__name__,
            }

    async def list_models(self) -> list[dict[str, Any]]:
        raw_models = await self._repository.list_models()

        async def _show(raw_model: dict[str, Any]) -> dict[str, Any]:
            name = raw_model.get("name")
            if not isinstance(name, str) or not name:
                return {}
            try:
                return await self._repository.show_model(name)
            except Exception as exc:
                logger.warning("Failed to inspect Ollama model %s: %s", name, exc)
                return {}

        show_payloads = await asyncio.gather(*(_show(model) for model in raw_models))

        models: list[dict[str, Any]] = []
        for raw_model, show_payload in zip(raw_models, show_payloads):
            name = raw_model.get("name")
            if not isinstance(name, str) or not name:
                continue

            capabilities = show_payload.get("capabilities")
            capability_set = set(capabilities if isinstance(capabilities, list) else [])
            models.append(
                {
                    "name": name,
                    "display_name": name,
                    "size": raw_model.get("size"),
                    "max_input_tokens": self._extract_context_length(raw_model, show_payload),
                    "supports_image_input": "vision" in capability_set,
                    "supports_reasoning": "thinking" in capability_set,
                    "is_remote": bool(raw_model.get("remote_model")),
                }
            )
        return models

    async def delete_model(self, model_name: str) -> dict[str, bool]:
        deleted = await self._repository.delete_model(model_name)
        if not deleted:
            raise ValueError("Model not found")
        return {"success": True}

    async def stream_pull(self, model_name: str) -> AsyncIterator[str]:
        stream_pull = getattr(self._repository, "stream_pull", None)
        if stream_pull is None:
            raise RuntimeError("Ollama repository does not support model pulls")

        async for line in stream_pull(model_name):
            yield f"data: {line}\n\n"
        yield 'data: {"status":"done"}\n\n'

    @staticmethod
    def _extract_context_length(
        raw_model: dict[str, Any], show_payload: dict[str, Any]
    ) -> int | None:
        model_info = show_payload.get("model_info")
        if isinstance(model_info, dict):
            for key, value in model_info.items():
                if key.endswith(".context_length") and isinstance(value, int) and value > 0:
                    return value

        context_length = show_payload.get("context_length")
        if isinstance(context_length, int) and context_length > 0:
            return context_length

        details = raw_model.get("details")
        if isinstance(details, dict):
            details_context_length = details.get("context_length")
            if isinstance(details_context_length, int) and details_context_length > 0:
                return details_context_length

        return None
