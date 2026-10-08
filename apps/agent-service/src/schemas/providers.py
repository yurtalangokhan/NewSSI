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


class ProviderResponse(BaseModel):
    id: str | int | None = None
    name: str
    provider_type: str
    base_url: str | None = None
    api_base: str | None = None
    default_model: str | None = None
    is_active: bool = True
    config: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class AvailableModelResponse(BaseModel):
    id: str = Field(description="Model identifier.")
    name: str = Field(description="Model display name.")
    provider_name: str | None = None
    provider_type: str | None = None
    is_default: bool = False

    model_config = {"extra": "allow"}


class WellKnownProviderResponse(BaseModel):
    name: str
    provider_type: str
    description: str | None = None
    default_base_url: str | None = None

    model_config = {"extra": "allow"}


class TestConnectionResponse(BaseModel):
    success: bool = True
    message: str | None = None
    models: list[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class UserProviderResponse(BaseModel):
    id: str | int | None = None
    name: str
    provider_type: str
    provider_kind: str | None = "api_key"
    is_active: bool = True
    api_base: str | None = None
    api_version: str | None = None
    default_model: str | None = None
    user_config: dict[str, Any] = Field(default_factory=dict)
    custom_config: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class AllProvidersResponse(BaseModel):
    builtin: list[ProviderResponse] = Field(default_factory=list)
    url_providers: list[ProviderResponse] = Field(default_factory=list)
    user_providers: list[UserProviderResponse] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class ProviderModelResponse(BaseModel):
    name: str = Field(description="Model name or identifier.")
    display_name: str | None = None
    max_input_tokens: int | None = None
    supports_image_input: bool = False
    supports_reasoning: bool = False
    supports_tools: bool = False
    supports_embedding: bool = False
    supports_code: bool = False
    supports_audio: bool = False
    is_remote: bool = False
    is_visible: bool = True
    size: int | None = None

    model_config = {"extra": "allow"}
