"""Public connector references; credentials are never part of agent payloads."""

from typing import Literal
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
