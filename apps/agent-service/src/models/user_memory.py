from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class MemoryCreate(BaseModel):
    content: str


class MemoryUpdate(BaseModel):
    content: str


class MemoryRead(BaseModel):
    id: UUID
    content: str
    source: Literal["manual", "auto_extracted", "imported"]
    time_created: datetime
    time_updated: datetime


class MemoryListResponse(BaseModel):
    items: list[MemoryRead]
    total: int


class DeleteAllResponse(BaseModel):
    deleted: int
