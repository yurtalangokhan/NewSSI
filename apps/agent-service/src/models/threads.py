from typing import Any

from pydantic import BaseModel


class ThreadSearchRequest(BaseModel):
    limit: int = 100
    offset: int = 0
    metadata: dict | None = None


class ThreadCreateRequest(BaseModel):
    thread_id: str | None = None
    metadata: dict | None = None


class ThreadUpdateRequest(BaseModel):
    metadata: dict | None = None


class ThreadState(BaseModel):
    values: dict[str, Any]
    next: list[str]
    checkpoint: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    created_at: str | None = None
    parent_config: dict[str, Any] | None = None
    parent_checkpoint: dict[str, Any] | None = None


class ThreadHistoryRequest(BaseModel):
    limit: int = 10
    before: str | None = None
    metadata: dict | None = None
    checkpoint: dict | None = None
