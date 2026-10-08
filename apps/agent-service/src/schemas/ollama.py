"""Pydantic response models for Ollama management."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OllamaStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    base_url: str
    online: bool
    version: str | None = None
    model_count: int = 0
    error: str | None = None


class OllamaModelDetailResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    display_name: str | None = None
    size: int | None = None
    max_input_tokens: int | None = None
    supports_image_input: bool = False
    supports_reasoning: bool = False
    supports_tools: bool = False
    supports_embedding: bool = False
    supports_code: bool = False
    supports_audio: bool = False
    is_remote: bool = False
