from typing import Any

from pydantic import BaseModel, Field


class UrlProviderPayload(BaseModel):
    name: str
    provider_type: str
    base_url: str
    api_key: str | None = None
    clear_api_key: bool = False
    default_model: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class UserProviderPayload(BaseModel):
    name: str
    provider_type: str
    api_key: str
    api_base: str | None = None
    api_version: str | None = None
    default_model: str | None = None
    custom_config: dict[str, Any] = Field(default_factory=dict)


class UserProviderUpdatePayload(BaseModel):
    name: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    api_version: str | None = None
    default_model: str | None = None


class ReorderPayload(BaseModel):
    ordered_config_ids: list[str]


class DefaultModelPayload(BaseModel):
    model: str | None = None


class OllamaPullPayload(BaseModel):
    model: str
    provider_id: str = "builtin"


class TestConnectionPayload(BaseModel):
    provider_type: str
    base_url: str | None = None
    api_key: str | None = None
    provider_id: str | None = None
