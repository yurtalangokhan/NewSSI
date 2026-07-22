from typing import Any

from pydantic import BaseModel


class ConnectorInfoResponse(BaseModel):
    name: str
    display_name: str
    source_definition_id: str
    category: str | None = None


class ConnectorSpecResponse(BaseModel):
    name: str
    display_name: str
    source_definition_id: str
    connection_specification: dict[str, Any]
    documentation_url: str | None = None


class StreamInfo(BaseModel):
    name: str


class ConnectorInfo(BaseModel):
    name: str
    display_name: str
    source_definition_id: str
    category: str | None = None
    icon_url: str | None = None
    documentation_url: str | None = None
    is_available: bool = True


class ConnectorSpec(BaseModel):
    name: str
    source_definition_id: str
    connection_specification: dict[str, Any]
    documentation_url: str | None = None
