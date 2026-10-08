from typing import Any

from pydantic import BaseModel, Field


class ConnectorInfoResponse(BaseModel):
    name: str
    display_name: str
    category: str | None = None


class ConnectorSpecResponse(BaseModel):
    name: str
    display_name: str
    connection_specification: dict[str, Any]
    documentation_url: str | None = None
    supported_sync_modes: list[str] = Field(default_factory=list)


class StreamInfo(BaseModel):
    name: str


class ConnectorInfo(BaseModel):
    name: str
    display_name: str
    category: str | None = None
    icon_url: str | None = None
    documentation_url: str | None = None
    is_available: bool = True


class ConnectorSpec(BaseModel):
    name: str
    display_name: str
    connection_specification: dict[str, Any]
    documentation_url: str | None = None
    supported_sync_modes: list[str] = Field(default_factory=list)
