"""Pydantic models for proxy endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProxyToolItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ProxyToolsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    tools: list[ProxyToolItem] = Field(default_factory=list)
    error: str | None = None


class ProxyOllamaModelsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    models: list[str] = Field(default_factory=list)
    default: str | None = None
    error: str | None = None


class ProxyRagCollectionsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    collections: list[Any] = Field(default_factory=list)
    error: str | None = None


class ProxyExecuteToolResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    result: Any = None
    error: str | None = None
