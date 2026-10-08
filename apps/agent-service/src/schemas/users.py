from typing import Any

from pydantic import BaseModel, Field


class RenameProjectPayload(BaseModel):
    name: str


class UpsertProjectInstructionsPayload(BaseModel):
    instructions: str


class MoveChatSessionPayload(BaseModel):
    chat_session_id: str


class FileStatusesPayload(BaseModel):
    file_ids: list[str]


class UserProjectResponse(BaseModel):
    id: int = Field(description="Project ID.")
    name: str = Field(description="Project name.")
    user_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    description: str | None = None

    model_config = {"extra": "allow"}


class UserProjectDetailResponse(BaseModel):
    project: UserProjectResponse
    files: list[dict[str, Any]] = Field(default_factory=list)
    persona_id_to_featured: dict[str, bool] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class ProjectInstructionsResponse(BaseModel):
    instructions: str = Field(default="", description="Project system instructions.")


class ProjectTokenCountResponse(BaseModel):
    token_count: int = Field(default=0, description="Estimated total token count.")


class ProjectFileItemResponse(BaseModel):
    id: str | int = Field(description="File record identifier.")
    name: str = Field(description="Filename.")
    file_id: str | None = None
    user_id: str | None = None
    project_id: int | None = None
    status: str | None = "COMPLETED"
    created_at: str | None = None

    model_config = {"extra": "allow"}


class UserProjectFileUploadResponse(BaseModel):
    user_files: list[ProjectFileItemResponse] = Field(default_factory=list)
    rejected_files: list[dict[str, Any]] = Field(default_factory=list)


class FileStatusesResponse(BaseModel):
    statuses: dict[str, Any] = Field(default_factory=dict, description="File statuses map.")

    model_config = {"extra": "allow"}


class RecentFileResponse(BaseModel):
    id: str | int = Field(description="File record identifier.")
    name: str = Field(description="Filename.")
    created_at: str | None = None
    file_type: str | None = None

    model_config = {"extra": "allow"}


class ProviderConfigItem(BaseModel):
    id: int | str | None = None
    name: str
    provider: str | None = None
    provider_display_name: str | None = None
    model_configurations: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class ProviderConfigResponse(BaseModel):
    providers: list[ProviderConfigItem] = Field(default_factory=list)
    selected_provider: str | None = None
    default_text: str | None = None
    default_vision: str | None = None

    model_config = {"extra": "allow"}


class BuiltinLlmOptionResponse(BaseModel):
    name: str
    is_visible: bool = True
    max_input_tokens: int | None = None
    supports_image_input: bool = False
    supports_reasoning: bool = False
    provider: str | None = None

    model_config = {"extra": "allow"}


class DefaultAssistantResponse(BaseModel):
    id: int | str | None = None
    name: str | None = None

    model_config = {"extra": "allow"}


class AdminProviderItem(BaseModel):
    name: str
    provider_type: str | None = None
    display_name: str | None = None
    is_active: bool = True
    has_api_key: bool = False

    model_config = {"extra": "allow"}


class AdminLlmProviderResponse(BaseModel):
    providers: list[AdminProviderItem] = Field(default_factory=list)
    selected_provider: str | None = None
    default_model: str | None = None

    model_config = {"extra": "allow"}


class OllamaModelSummaryResponse(BaseModel):
    name: str
    display_name: str | None = None

    model_config = {"extra": "allow"}


class PersonaProvidersResponse(BaseModel):
    providers: list[dict[str, Any]] = Field(default_factory=list)
    selected_provider: str | None = None
    default_model: str | None = None

    model_config = {"extra": "allow"}
