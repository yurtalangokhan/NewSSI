from typing import Any

from pydantic import BaseModel, Field

from schemas.llm import ModelName


class AgentInfo(BaseModel):
    """Info about an available agent."""

    key: str = Field(description="Agent key.", examples=["research-assistant"])
    description: str = Field(
        description="Description of the agent.",
        examples=["A research assistant for generating research papers."],
    )


class ServiceMetadata(BaseModel):
    """Metadata about the service including available agents and models."""

    agents: list[AgentInfo] = Field(description="List of available agents.")
    models: list[ModelName] = Field(description="List of available LLMs.")
    default_agent: str = Field(
        description="Default agent used when none is specified.",
        examples=["research-assistant"],
    )
    default_model: str | None = Field(
        default=None,
        description="Default model used when none is specified.",
    )


class AgentCatalogItemResponse(BaseModel):
    id: str | int = Field(description="Agent or persona ID.")
    name: str = Field(description="Agent display name.")
    description: str | None = None
    icon_name: str | None = None
    uploaded_image_id: str | None = None
    display_priority: int | None = None
    featured: bool = False
    is_public: bool = True
    capabilities: dict[str, Any] = Field(default_factory=dict)
    availability: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class AgentCompositionCatalogResponse(BaseModel):
    components: list[dict[str, Any]] = Field(default_factory=list)
    kinds: list[str] = Field(default_factory=list)


class AgentDetailResponse(BaseModel):
    id: str | int = Field(description="Agent identifier.")
    name: str = Field(description="Agent name.")
    description: str | None = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    availability: dict[str, Any] | None = None

    model_config = {"extra": "allow"}
