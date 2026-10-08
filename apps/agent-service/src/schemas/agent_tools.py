"""Pydantic models for agent-tool bindings."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentToolResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | int | None = None
    agent_id: int | None = None
    tool_id: str | None = None
    name: str | None = None
    description: str | None = None
    provider_id: str | int | None = None
    is_active: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    order_index: int = 0
    binding_id: str | int | None = None


class AgentToolsPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    tool_ids: list[str] = Field(default_factory=list)
