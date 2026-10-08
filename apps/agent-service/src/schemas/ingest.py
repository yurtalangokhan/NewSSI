from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SourcePreviewRequest(BaseModel):
    datasource_id: str
    stream: str | None = None
    limit: int = 20


class SourceStreamInfo(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    name: str
    key_properties: list[Any] = Field(default_factory=list)
    field_count: int | None = None
    stream_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")


class SourcePreviewResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    datasource_id: str
    source_name: str = ""
    connector_type: str = "unknown"
    streams: list[SourceStreamInfo] = Field(default_factory=list)
    note: str = ""
