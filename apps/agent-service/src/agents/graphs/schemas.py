"""Graph schema definitions and registry."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class GraphSchemaType(str, Enum):
    """Available graph schema types."""

    ZERO_SHOT = "zero_shot"
    REACT = "react"
    SUPERVISOR = "supervisor"
    PIPELINE = "pipeline"
    PLAN_EXECUTE = "plan_execute"
    SELF_REFLECT = "self_reflect"


@dataclass
class SubAgentConfig:
    """Configuration for a sub-agent in supervisor/pipeline."""

    name: str
    system_prompt: str
    mcp_tools: list[str] = field(default_factory=list)
    model: str | None = None


@dataclass
class GraphSchema:
    """
    Graph schema definition.

    Defines how an agent's execution graph is built.
    """

    schema_type: GraphSchemaType
    description: str
    config_schema: dict[str, Any] = field(default_factory=dict)
    required_fields: list[str] = field(default_factory=list)
    supports_memory: bool = True
    supports_tools: bool = False
    supports_rag: bool = False
    supports_sub_agents: bool = False
    builder_factory: Callable | None = None
    default_system_prompt: str = "You are a helpful AI assistant."
    is_multi_step: bool = False


class ZeroShotSchema(GraphSchema):
    """Zero-shot chat - simple model call with system prompt."""

    def __init__(self):
        super().__init__(
            schema_type=GraphSchemaType.ZERO_SHOT,
            description="Simple conversational agent - direct LLM call with system prompt",
            config_schema={
                "system_prompt": {"type": "string", "default": "You are a helpful AI assistant."},
                "model": {"type": "string", "default": None},
            },
            required_fields=["system_prompt"],
            supports_memory=True,
            supports_tools=False,
            supports_sub_agents=False,
            default_system_prompt="You are a helpful AI assistant.",
            is_multi_step=False,
        )


class ReActSchema(GraphSchema):
    """ReAct - tool-using agent with reasoning."""

    def __init__(self):
        super().__init__(
            schema_type=GraphSchemaType.REACT,
            description="ReAct agent with tools - can use MCP tools to complete tasks",
            config_schema={
                "system_prompt": {
                    "type": "string",
                    "default": "You are a helpful AI assistant with tools.",
                },
                "model": {"type": "string", "default": None},
                "mcp_tools": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            required_fields=["system_prompt"],
            supports_memory=True,
            supports_tools=True,
            supports_rag=True,
            supports_sub_agents=False,
            default_system_prompt="You are a helpful AI assistant with tools. Use your tools to complete tasks.",
            is_multi_step=False,
        )


class SupervisorSchema(GraphSchema):
    """Supervisor - multi-agent coordination with delegation."""

    def __init__(self):
        super().__init__(
            schema_type=GraphSchemaType.SUPERVISOR,
            description="Supervisor agent - coordinates multiple sub-agents in parallel",
            config_schema={
                "supervisor_prompt": {"type": "string", "default": "You are a team supervisor."},
                "model": {"type": "string", "default": None},
                "sub_agents": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "system_prompt": {"type": "string"},
                            "mcp_tools": {"type": "array", "items": {"type": "string"}},
                            "model": {"type": "string"},
                        },
                    },
                    "default": [],
                },
            },
            required_fields=["supervisor_prompt", "sub_agents"],
            supports_memory=False,
            supports_tools=False,
            supports_sub_agents=True,
            default_system_prompt="You are a team supervisor managing multiple specialized agents.",
            is_multi_step=True,
        )


class PipelineSchema(GraphSchema):
    """Pipeline - sequential stage execution."""

    def __init__(self):
        super().__init__(
            schema_type=GraphSchemaType.PIPELINE,
            description="Pipeline agent - executes stages sequentially, each output feeds next",
            config_schema={
                "model": {"type": "string", "default": None},
                "stages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "system_prompt": {"type": "string"},
                            "mcp_tools": {"type": "array", "items": {"type": "string"}},
                            "model": {"type": "string"},
                        },
                    },
                    "default": [],
                },
                "pipeline_prompt": {
                    "type": "string",
                    "default": "Process input through all stages.",
                },
            },
            required_fields=["stages"],
            supports_memory=False,
            supports_tools=True,
            supports_rag=True,
            supports_sub_agents=True,
            default_system_prompt="Process input through the pipeline stages sequentially.",
            is_multi_step=True,
        )


class PlanExecuteSchema(GraphSchema):
    """Plan & Execute - plan first, then execute."""

    def __init__(self):
        super().__init__(
            schema_type=GraphSchemaType.PLAN_EXECUTE,
            description="Plan & Execute - creates a plan, then executes it step by step",
            config_schema={
                "system_prompt": {"type": "string", "default": "You are a planning assistant."},
                "model": {"type": "string", "default": None},
                "mcp_tools": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            required_fields=["system_prompt"],
            supports_memory=True,
            supports_tools=True,
            supports_rag=True,
            supports_sub_agents=False,
            default_system_prompt="First plan your approach, then execute it step by step.",
            is_multi_step=True,
        )


class SelfReflectSchema(GraphSchema):
    """Self-Reflect - agent with self-correction."""

    def __init__(self):
        super().__init__(
            schema_type=GraphSchemaType.SELF_REFLECT,
            description="Self-Reflect - generates output, reflects, and revises if needed",
            config_schema={
                "system_prompt": {"type": "string", "default": "You are a helpful assistant."},
                "reflection_prompt": {
                    "type": "string",
                    "default": "Review this response and suggest improvements.",
                },
                "model": {"type": "string", "default": None},
                "max_iterations": {"type": "integer", "default": 3},
            },
            required_fields=["system_prompt"],
            supports_memory=True,
            supports_tools=False,
            supports_sub_agents=False,
            default_system_prompt="Generate a response, then reflect and improve if needed.",
            is_multi_step=True,
        )


_schema_registry: dict[GraphSchemaType, GraphSchema] = {}


def _init_schemas() -> None:
    """Initialize schema registry."""
    global _schema_registry

    schemas = [
        ZeroShotSchema(),
        ReActSchema(),
        SupervisorSchema(),
        PipelineSchema(),
        PlanExecuteSchema(),
        SelfReflectSchema(),
    ]

    for schema in schemas:
        _schema_registry[schema.schema_type] = schema
        logger.debug("Registered graph schema: %s", schema.schema_type)


def get_all_schemas() -> list[GraphSchema]:
    """Get all registered schemas."""
    return list(_schema_registry.values())


def get_schema(schema_type: GraphSchemaType | str) -> GraphSchema | None:
    """Get schema by type."""
    if isinstance(schema_type, str):
        try:
            schema_type = GraphSchemaType(schema_type)
        except ValueError:
            return None
    return _schema_registry.get(schema_type)


def is_multi_step_schema(schema_type: str | GraphSchemaType) -> bool:
    """Return True if the schema produces a multi-node graph (supervisor/pipeline/self_reflect)."""
    schema = get_schema(schema_type)
    return schema.is_multi_step if schema else False


def register_schema(schema: GraphSchema) -> None:
    """Register a custom schema."""
    _schema_registry[schema.schema_type] = schema
    logger.info("Registered custom graph schema: %s", schema.schema_type)


_init_schemas()
