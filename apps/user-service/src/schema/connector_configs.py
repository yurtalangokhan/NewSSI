from typing import Any

from pydantic import BaseModel, Field, model_validator


class ConnectorConfigCreate(BaseModel):
    connector_name: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    config: dict[str, Any]


class ConnectorConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    config: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _something_to_update(self) -> "ConnectorConfigUpdate":
        if self.name is None and self.config is None:
            raise ValueError("provide name or config")
        return self


class ConnectorConfigMeta(BaseModel):
    id: str
    user_id: str
    connector_name: str
    name: str
    created_at: str | None = None
    updated_at: str | None = None


class ConnectorConfigDetail(ConnectorConfigMeta):
    config: dict[str, Any]


__all__ = [
    "ConnectorConfigCreate",
    "ConnectorConfigDetail",
    "ConnectorConfigMeta",
    "ConnectorConfigUpdate",
]
