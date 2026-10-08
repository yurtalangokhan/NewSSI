from typing import Any

from pydantic import BaseModel, Field


class AssistantSearchRequest(BaseModel):
    limit: int = 100
    offset: int = 0
    metadata: dict | None = None
    graph_id: str | None = None


class AssistantCreateRequest(BaseModel):
    graph_id: str
    name: str | None = None
    config: dict | None = None
    metadata: dict | None = None


class AssistantUpdateRequest(BaseModel):
    name: str | None = None
    config: dict | None = None
    metadata: dict | None = None


class AssistantResponse(BaseModel):
    assistant_id: str = Field(description="Assistant identifier.")
    graph_id: str = Field(description="Graph topology identifier.")
    name: str = Field(description="Assistant name.")
    config: dict[str, Any] = Field(default_factory=dict, description="Configuration parameters.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata dictionary.")
    created_at: str | None = None
    updated_at: str | None = None
    version: int = 1

    model_config = {"extra": "allow"}


class AssistantDeleteResponse(BaseModel):
    status: str = "ok"
    assistant_id: str
    detail: str | None = None


class AssistantSchemaResponse(BaseModel):
    graph_id: str | None = None
    config_schema: dict[str, Any] | None = None
    context_schema: dict[str, Any] | None = None
    state_schema: dict[str, Any] | None = None

    model_config = {"extra": "allow"}
