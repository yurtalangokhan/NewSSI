"""Typed memory write payloads; services validate business requirements."""

from pydantic import BaseModel


class MemoryWriteRequest(BaseModel):
    content: str = ""


class MemoryFactsRequest(BaseModel):
    contents: list[str] = []
    source: str = "auto_extracted"
    language: str | None = None
