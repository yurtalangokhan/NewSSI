from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SubAgentRequest(BaseModel):
    name: str
    system_prompt: str = "You are a helpful agent."
    mcp_tools: list[str] = Field(default_factory=list)
    model: str | None = None


class StageRequest(BaseModel):
    name: str
    system_prompt: str = "Process this input."
    mcp_tools: list[str] = Field(default_factory=list)
    model: str | None = None


class CreateAgentDefinitionRequest(BaseModel):
    name: str
    graph_schema: str = "zero_shot"
    brain_type: str = "llm"
    memory_type: str = "none"
    system_prompt: str | None = None
    model: str | None = None
    mcp_tools: list[str] = Field(default_factory=list)
    mcp_tool_configs: dict[str, Any] = Field(default_factory=dict)
    rag_config: dict[str, list[str]] = Field(default_factory=dict)
    sub_agents: list[SubAgentRequest] = Field(default_factory=list)
    sub_agent_ids: list[UUID] = Field(default_factory=list)  # NEW: References to existing agents
    supervisor_prompt: str | None = None
    stages: list[StageRequest] = Field(default_factory=list)
    pipeline_prompt: str | None = None
    reflection_prompt: str | None = None
    max_iterations: int = 3
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class UpdateAgentDefinitionRequest(BaseModel):
    graph_schema: str | None = None
    brain_type: str | None = None
    memory_type: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    mcp_tools: list[str] | None = None
    mcp_tool_configs: dict[str, Any] | None = None
    rag_config: dict[str, list[str]] | None = None
    sub_agents: list[dict[str, Any]] | None = None
    sub_agent_ids: list[UUID] | None = None  # NEW: References to existing agents
    supervisor_prompt: str | None = None
    stages: list[dict[str, Any]] | None = None
    pipeline_prompt: str | None = None
    reflection_prompt: str | None = None
    max_iterations: int | None = None
    description: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None


class GraphSchemaItemResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class ComponentTypeItemResponse(BaseModel):
    id: str
    name: str
    description: str | None = None

    model_config = {"extra": "allow"}


class AgentDefinitionResponse(BaseModel):
    id: UUID | str
    name: str
    graph_schema: str = "zero_shot"
    brain_type: str = "llm"
    memory_type: str = "none"
    system_prompt: str | None = None
    model: str | None = None
    mcp_tools: list[str] = Field(default_factory=list)
    mcp_tool_configs: dict[str, Any] = Field(default_factory=dict)
    rag_config: dict[str, Any] = Field(default_factory=dict)
    sub_agents: list[Any] = Field(default_factory=list)
    sub_agent_ids: list[Any] = Field(default_factory=list)
    stages: list[Any] = Field(default_factory=list)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"extra": "allow"}


class CompositionValidationResponse(BaseModel):
    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class CompositionInfoResponse(BaseModel):
    definition_id: UUID | str
    name: str | None = None
    graph_schema: str | None = None
    is_composite: bool = False
    sub_agents: list[Any] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class AvailableForCompositionItemResponse(BaseModel):
    id: str | UUID
    name: str
    graph_schema: str = "zero_shot"
    status: str = "active"
    depth: int = 0
    preview: str = ""

    model_config = {"extra": "allow"}


class FlowValidationIssue(BaseModel):
    code: str | None = None
    message: str | None = None
    node_id: str | None = None
    edge_id: str | None = None

    model_config = {"extra": "allow"}


class FlowValidationResponse(BaseModel):
    valid: bool = True
    errors: list[FlowValidationIssue | dict[str, Any]] = Field(default_factory=list)
    warnings: list[FlowValidationIssue | dict[str, Any]] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class FlowExpansionResponse(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"extra": "allow"}
