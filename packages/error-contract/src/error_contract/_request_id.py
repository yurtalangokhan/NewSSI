"""Shared request-id resolution for the FastAPI handlers and the Starlette
middleware: prefer the caller's own correlation header, and generate one when
absent rather than leaving request_id null and untraceable.
"""

import uuid
from typing import Protocol


class _HeaderCarrier(Protocol):
    def get(self, key: str) -> str | None: ...


def resolve_request_id(headers: _HeaderCarrier) -> str:
    return headers.get("x-request-id") or headers.get("x-correlation-id") or str(uuid.uuid4())
