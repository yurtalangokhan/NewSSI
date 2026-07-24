"""Controller for built-in Ollama management."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from controller.base import BaseController
from domain.ollama.service import OllamaService


class OllamaController(BaseController):
    def __init__(self, service: OllamaService) -> None:
        self._service = service

    async def get_status(self) -> dict[str, Any]:
        return await self._service.get_status()

    async def list_models(self) -> list[dict[str, Any]]:
        return await self._service.list_models()

    async def delete_model(self, model_name: str) -> dict[str, bool]:
        try:
            return await self._service.delete_model(model_name)
        except ValueError as exc:
            self._raise_not_found(str(exc))

    async def stream_pull(self, model_name: str) -> AsyncIterator[str]:
        return self._service.stream_pull(model_name)
