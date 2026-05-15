"""Pydantic DTOs for the user_memory domain."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class MemoryUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class MemoryRead(BaseModel):
    id: UUID
    content: str
    source: Literal["manual", "auto_extracted", "imported"]
    time_created: datetime
    time_updated: datetime

    model_config = {"from_attributes": True}


class MemoryListResponse(BaseModel):
    items: list[MemoryRead]
    total: int


class DeleteAllResponse(BaseModel):
    deleted: int
