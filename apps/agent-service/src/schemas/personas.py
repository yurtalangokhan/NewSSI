from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from schemas.base import BaseDomainEntity, BaseSchemaModel
from schemas.connector_tools import ConnectorBinding


class PersonaUpsertRequest(BaseModel):
    name: str
    description: str
    system_prompt: str = ""
    task_prompt: str = ""
    datetime_aware: bool = True
    document_set_ids: list = Field(default_factory=list)
    is_public: bool = True
    llm_model_provider_override: str | None = None
    llm_model_version_override: str | None = None
    starter_messages: list | None = None
    users: list = Field(default_factory=list)
    groups: list = Field(default_factory=list)
    tool_ids: list = Field(default_factory=list)
    remove_image: bool = False
    uploaded_image_id: str | None = None
    icon_name: str | None = None
    search_start_date: str | None = None
    featured: bool = False
    display_priority: int | None = None
    label_ids: list = Field(default_factory=list)
    user_file_ids: list = Field(default_factory=list)
    replace_base_system_prompt: bool = False
    hierarchy_node_ids: list = Field(default_factory=list)
    document_ids: list = Field(default_factory=list)
    base_agent: str | None = None
    graph_schema: str = "zero_shot"
    brain_type: str = "llm"
    memory_type: str = "none"
    sub_agent_ids: list[str] = Field(default_factory=list)
    sub_agents: list[dict] = Field(default_factory=list)
    supervisor_prompt: str | None = None
    stages: list[dict] = Field(default_factory=list)
    pipeline_prompt: str | None = None
    reflection_prompt: str | None = None
    max_iterations: int = 3
    mcp_tools: list[str] = Field(default_factory=list)
    mcp_tool_configs: dict = Field(default_factory=dict)
    connector_bindings: list[ConnectorBinding] = Field(default_factory=list, max_length=32)
    rag_config: dict | None = None
    long_term_memory: bool = False


class PersonaOwnerResponse(BaseModel):
    id: str | None = None
    email: str | None = None


class PersonaCapabilitiesResponse(BaseModel):
    has_actions: bool = False
    has_conversation_starters: bool = False
    has_retrieval: bool = False
    has_web_search: bool = False
    has_scoped_knowledge: bool = False
    long_term_memory: bool = False


class PersonaAvailabilityResponse(BaseModel):
    available: bool = True
    reasons: list[str] = Field(default_factory=list)
    missing_models: list[str] = Field(default_factory=list)
    missing_tools: list[str] = Field(default_factory=list)
    memory_available: bool = True
    rag_available: bool = True


class PersonaResponse(BaseDomainEntity):
    id: int
    external_id: str | None = None
    name: str
    description: str | None = None
    uploaded_image_id: str | None = None
    icon_name: str | None = None
    is_public: bool = True
    is_visible: bool = True
    display_priority: int | None = None
    featured: bool = False
    builtin_persona: bool = False
    is_dynamic: bool = False
    labels: list[dict[str, Any]] = Field(default_factory=list)
    owner: PersonaOwnerResponse | dict[str, Any] | None = None
    base_agent: str | None = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    starter_messages: list[Any] | None = None
    document_sets: list[Any] = Field(default_factory=list)
    hierarchy_node_count: int = 0
    attached_document_count: int = 0
    knowledge_sources: list[Any] = Field(default_factory=list)
    llm_model_version_override: str | None = None
    llm_model_provider_override: str | None = None
    mcp_tools: list[str] = Field(default_factory=list)
    rag_config: dict[str, Any] | None = None
    connector_bindings: list[Any] = Field(default_factory=list)
    action_count: int = 0
    memory_type: str | None = None
    long_term_memory: bool = False
    capabilities: PersonaCapabilitiesResponse | dict[str, Any] = Field(default_factory=dict)
    graph_schema: str | None = None
    agent_definition_id: str | None = None
    availability: PersonaAvailabilityResponse | dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow", populate_by_name=True, from_attributes=True)


class PersonaOptionResponse(BaseDomainEntity):
    id: int
    name: str
    description: str | None = None
    icon_name: str | None = None
    uploaded_image_id: str | None = None
    display_priority: int | None = None

    model_config = ConfigDict(extra="allow", populate_by_name=True, from_attributes=True)


class PersonaLabelResponse(BaseDomainEntity):
    id: int
    name: str

    model_config = ConfigDict(extra="allow", populate_by_name=True, from_attributes=True)


class PersonaImageUploadResponse(BaseDomainEntity):
    uploaded_image_id: str = Field(description="Unique uploaded image identifier.")
    file_id: str | None = None
    url: str | None = None


class Persona(BaseSchemaModel):
    """Schema model representing an AI persona / assistant profile."""

    id: int | str
    name: str
    description: str | None = None
    system_prompt: str | None = None
    task_prompt: str | None = None
    datetime_aware: bool = True
    is_public: bool = False
    llm_model_provider_override: str | None = None
    llm_model_version_override: str | None = None
    starter_messages: list[Any] | None = None
    labels: list[str] = Field(default_factory=list)
    user_id: str | None = None
    is_builtin: bool = False
    builtin_key: str | None = None
    uploaded_image_id: str | None = None
    icon_name: str | None = None
    base_agent: str | None = None
    mcp_tools: list[Any] = Field(default_factory=list)
    mcp_tool_configs: dict[str, Any] = Field(default_factory=dict)
    connector_bindings: list[Any] = Field(default_factory=list)
    rag_config: dict[str, Any] | None = None
    long_term_memory: bool = False
    time_created: str | None = None
    time_updated: str | None = None


# Backward compatibility alias
PersonaEntity = Persona
