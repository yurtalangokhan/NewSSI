from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BrainConfig:
    key: str
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PerceptronConfig:
    key: str
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolSelection:
    keys: tuple[str, ...] = ()
    bindings: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphSchemaConfig:
    key: str
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphBuildRequest:
    brain: BrainConfig
    perceptrons: tuple[PerceptronConfig, ...] = ()
    tools: ToolSelection = field(default_factory=ToolSelection)
    graph: GraphSchemaConfig | None = None
    nested: tuple[AgentDefinition, ...] = ()


@dataclass(frozen=True)
class RuntimePolicyConfig:
    memory: dict[str, Any] = field(default_factory=dict)
    safety: dict[str, Any] = field(default_factory=dict)
    retry: dict[str, Any] = field(default_factory=dict)
    limits: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentDefinition:
    identity: str
    name: str = ""
    description: str = ""
    version: str = "1"
    tags: tuple[str, ...] = ()
    brain: BrainConfig | None = None
    perceptrons: tuple[PerceptronConfig, ...] = ()
    tools: ToolSelection = field(default_factory=ToolSelection)
    graph: GraphSchemaConfig | None = None
    runtime_policy: RuntimePolicyConfig = field(default_factory=RuntimePolicyConfig)
    nested: tuple[AgentDefinition, ...] = ()
