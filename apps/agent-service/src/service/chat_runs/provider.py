"""Process-wide ChatRunService handle, configured by the app lifespan."""

from __future__ import annotations

from service.chat_runs.domain import ChatRunUnavailableError
from service.chat_runs.service import ChatRunService

_service: ChatRunService | None = None


def configure_chat_runs(service: ChatRunService) -> None:
    global _service
    _service = service


def reset_chat_runs() -> None:
    global _service
    _service = None


def get_chat_run_service() -> ChatRunService:
    if _service is None:
        raise ChatRunUnavailableError("chat runs are not initialised")
    return _service
