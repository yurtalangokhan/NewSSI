from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from .definitions import GraphBuildRequest, GraphSchemaConfig
from .errors import ValidationIssue


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in value)
    return value


@dataclass(frozen=True)
class BrainRequest:
    messages: list[dict[str, Any]]
    settings: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "settings", _freeze_value(self.settings))


@dataclass(frozen=True)
class BrainResponse:
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))


@dataclass(frozen=True)
class PerceptionRequest:
    inputs: dict[str, Any]
    settings: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "settings", _freeze_value(self.settings))


@dataclass(frozen=True)
class PerceptionResult:
    context: dict[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))


@dataclass(frozen=True)
class ToolDescriptor:
    key: str
    description: str
    required_trusted_bindings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrustedToolContext:
    """Request-scoped platform values never placed in model-visible arguments.

    Only opaque references and identity values are carried here. Never decrypted
    credentials, raw attachment bytes, access tokens, or the internal service token.
    """

    user_id: str | None = None
    tenant_id: str | None = None
    binding_references: Mapping[str, str] = field(default_factory=dict)
    attachment_handles: tuple[str, ...] = ()
    project_id: str | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "binding_references", _freeze_value(self.binding_references))


@dataclass(frozen=True)
class ToolInvocation:
    model_arguments: Mapping[str, Any]
    trusted_context: TrustedToolContext | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_arguments", _freeze_value(self.model_arguments))


@dataclass(frozen=True)
class ToolResult:
    output: Any
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "output", _freeze_value(self.output))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))


@dataclass(frozen=True)
class AgentRunRequest:
    inputs: dict[str, Any]
    settings: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "settings", _freeze_value(self.settings))


@dataclass(frozen=True)
class AgentRunResult:
    output: Any
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))


@dataclass(frozen=True)
class AgentChunk:
    delta: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))


@dataclass(frozen=True)
class AgentEvent:
    name: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze_value(self.payload))


@dataclass(frozen=True)
class AgentState:
    values: dict[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))


@dataclass(frozen=True)
class StateRequest:
    thread_id: str


@dataclass(frozen=True)
class StateUpdateRequest:
    thread_id: str
    values: dict[str, Any]


@dataclass(frozen=True)
class RuntimePolicyRequest:
    agent: Any
    inputs: Mapping[str, Any] = field(default_factory=dict)
    state: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", _freeze_value(self.inputs))
        object.__setattr__(self, "state", _freeze_value(self.state))


@dataclass(frozen=True)
class RuntimePolicyDecision:
    continue_run: bool
    reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))


@dataclass(frozen=True)
class RuntimePolicyResult:
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))


@runtime_checkable
class Brain(Protocol):
    async def load(self) -> None: ...

    async def generate(self, request: BrainRequest) -> BrainResponse: ...

    async def close(self) -> None: ...


@runtime_checkable
class Perceptron(Protocol):
    async def load(self) -> None: ...

    async def perceive(self, request: PerceptionRequest) -> PerceptionResult: ...

    async def close(self) -> None: ...


@runtime_checkable
class ToolBinding(Protocol):
    descriptor: ToolDescriptor

    async def invoke(self, invocation: ToolInvocation) -> ToolResult: ...


@runtime_checkable
class ToolGateway(Protocol):
    async def load(self) -> None: ...

    async def describe(self) -> tuple[ToolDescriptor, ...]: ...

    async def resolve(self, keys: tuple[str, ...]) -> tuple[ToolBinding, ...]: ...

    async def close(self) -> None: ...


@runtime_checkable
class ExecutableAgent(Protocol):
    async def ainvoke(self, request: AgentRunRequest) -> AgentRunResult: ...

    async def astream(self, request: AgentRunRequest) -> AsyncIterator[AgentChunk]: ...

    async def astream_events(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]: ...

    async def aget_state(self, request: StateRequest) -> AgentState: ...

    async def aupdate_state(self, request: StateUpdateRequest) -> AgentState: ...

    async def aget_state_history(self, request: StateRequest) -> AsyncIterator[AgentState]: ...

    async def close(self) -> None: ...


@runtime_checkable
class GraphSchemaStrategy(Protocol):
    key: str

    def validate(self, config: GraphSchemaConfig) -> tuple[ValidationIssue, ...]: ...

    async def build(self, request: GraphBuildRequest) -> ExecutableAgent: ...


@runtime_checkable
class RuntimePolicy(Protocol):
    key: str

    async def before_run(self, request: RuntimePolicyRequest) -> RuntimePolicyDecision: ...

    async def after_run(
        self, request: RuntimePolicyRequest, result: AgentRunResult
    ) -> RuntimePolicyResult: ...

    async def close(self) -> None: ...


@runtime_checkable
class AgentDefinitionRepository(Protocol):
    async def get(self, identity: str) -> Any | None: ...

    async def save(self, definition: Any) -> Any: ...
