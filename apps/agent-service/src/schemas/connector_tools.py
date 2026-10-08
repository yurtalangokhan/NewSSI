"""Public connector references; credentials are never part of agent payloads."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ConnectorOperation = Literal["list_resources", "read"]


class ConnectorBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datasource_id: str
    operations: list[ConnectorOperation] = Field(min_length=1, max_length=2)

    @field_validator("datasource_id")
    @classmethod
    def valid_datasource_id(cls, value: str) -> str:
        return str(UUID(value))

    @field_validator("operations")
    @classmethod
    def unique_operations(cls, value: list[ConnectorOperation]) -> list[ConnectorOperation]:
        return list(dict.fromkeys(value))


class ConnectorResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona_id: int = Field(ge=2)
    datasource_id: UUID
    operation: ConnectorOperation


class ConnectorOptionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str
    connector_type: str = ""
    operations: list[str] = Field(default_factory=list)
    unavailable_reason: str | None = None


class ConnectorResolveResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
