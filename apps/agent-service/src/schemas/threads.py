from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from schemas.base import BaseSchemaModel


@dataclass
class ThreadRunStreamRequest:
    """Request body for the SDK-compatible ``POST /threads/{id}/runs/stream``.

    Deliberately not ``models.chat.StreamInput``: this mirrors the
    ``@langchain/langgraph-sdk`` run payload (``assistant_id``/``input``/
    ``model``/``stream_tokens``), not the chat endpoint's message shape. It stays
    a stdlib dataclass so FastAPI validates it exactly as it did when the class
    lived inside the route module.
    """

    assistant_id: str | None = None
    input: dict | None = None
    model: str | None = None
    stream_tokens: bool = True
    user_id: str | None = None


class ThreadSearchRequest(BaseModel):
    limit: int = 100
    offset: int = 0
    metadata: dict | None = None


class ThreadCreateRequest(BaseModel):
    thread_id: str | None = None
    metadata: dict | None = None


class ThreadUpdateRequest(BaseModel):
    metadata: dict | None = None


class ThreadResponse(BaseModel):
    thread_id: str = Field(description="Unique thread identifier.")
    created_at: str | None = Field(default=None, description="ISO timestamp of creation.")
    updated_at: str | None = Field(default=None, description="ISO timestamp of last update.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Thread metadata dictionary.")
    values: dict[str, Any] | None = Field(default=None, description="Sanitized checkpoint values if populated.")


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


class Thread(BaseSchemaModel):
    """Schema model representing a persistent conversation thread."""

    thread_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = "idle"
    project_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    last_message_at: str | None = None
    last_accessed_at: str | None = None
    run_kind: str = "production"
    values: dict[str, Any] | None = None


# Backward compatibility alias
ThreadEntity = Thread
