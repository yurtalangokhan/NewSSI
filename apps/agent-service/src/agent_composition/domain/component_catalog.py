from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ComponentKind(str, Enum):
    BRAIN = "brain"
    PERCEPTRON = "perceptron"
    GRAPH_STRATEGY = "graph_strategy"
    RUNTIME_POLICY = "runtime_policy"
    TOOL = "tool"


@dataclass(frozen=True)
class ComponentDescriptor:
    key: str
    kind: ComponentKind
    description: str
    required_settings: tuple[str, ...] = ()
    settings_schema: Mapping[str, str] | None = None
    required_nested: bool = False
    incompatible_with: tuple[str, ...] = ()
    available: bool = True
    implemented: bool = True
    capabilities: tuple[str, ...] = ()

    def api_metadata(self) -> dict[str, Any]:
        """Public catalog entry. Hides unimplemented choices from API consumers."""
        return {
            "key": self.key,
            "kind": self.kind.value,
            "description": self.description,
            "required_settings": list(self.required_settings),
            "settings_schema": dict(self.settings_schema or {}),
            "required_nested": self.required_nested,
            "incompatible_with": list(self.incompatible_with),
            "available": self.available,
            "capabilities": list(self.capabilities),
        }


def _brain(key: str, description: str, **kw: Any) -> ComponentDescriptor:
    return ComponentDescriptor(key=key, kind=ComponentKind.BRAIN, description=description, **kw)


def _perceptron(key: str, description: str, **kw: Any) -> ComponentDescriptor:
    return ComponentDescriptor(
        key=key, kind=ComponentKind.PERCEPTRON, description=description, **kw
    )


def _strategy(key: str, description: str, **kw: Any) -> ComponentDescriptor:
    return ComponentDescriptor(
        key=key, kind=ComponentKind.GRAPH_STRATEGY, description=description, **kw
    )


def _policy(key: str, description: str, **kw: Any) -> ComponentDescriptor:
    return ComponentDescriptor(
        key=key, kind=ComponentKind.RUNTIME_POLICY, description=description, **kw
    )


COMPONENT_CATALOG: dict[str, ComponentDescriptor] = {
    # Brains
    "standard_model": _brain(
        "standard_model",
        "Single-model reasoning brain.",
        settings_schema={"temperature": "number", "max_tokens": "integer"},
    ),
    "guard": _brain(
        "guard",
        "Legacy guard value mapped to standard_model plus an enabled safety policy.",
        incompatible_with=("multi_model",),
        available=False,
        implemented=False,
    ),
    "multi_model": _brain(
        "multi_model",
        "Multi-model routing brain; unavailable until routing is implemented.",
        available=False,
        implemented=False,
    ),
    # Perceptrons
    "long_term_memory": _perceptron("long_term_memory", "Recall from persisted long-term memory."),
    "current_chat_document": _perceptron(
        "current_chat_document",
        "Enrich from current chat documents.",
        incompatible_with=("project_context",),
    ),
    "project_context": _perceptron("project_context", "Enrich from project or persona context."),
    "input_normalization": _perceptron("input_normalization", "Normalize and validate input."),
    # Graph strategies
    "zero_shot": _strategy("zero_shot", "Direct single-step reasoning."),
    "react": _strategy("react", "Reason-and-act loop."),
    "supervisor": _strategy(
        "supervisor", "Model-directed supervisor delegation.", required_nested=True
    ),
    "pipeline": _strategy(
        "pipeline", "Deterministic ordered pipeline stages.", required_nested=True
    ),
    "plan_and_execute": _strategy("plan_and_execute", "Plan then execute strategy."),
    "self_reflect": _strategy("self_reflect", "Self-reflection strategy."),
    # The flow canvas is a graph strategy like any other from the catalog's
    # point of view: the agent editor lists it, and a flow-backed definition
    # carries its own flow_spec instead of nested definitions.
    "flow": _strategy("flow", "Visual flow canvas compiled into a LangGraph graph."),
    # Runtime policies
    "memory_persistence": _policy(
        "memory_persistence", "Post-run memory extraction and persistence."
    ),
    "safety": _policy("safety", "Pre/post run safety moderation."),
    "retry": _policy("retry", "Retry, timeout, and retry telemetry."),
    "checkpoint": _policy("checkpoint", "Checkpoint state read, update, history, persistence."),
    "telemetry": _policy("telemetry", "Structured events and telemetry."),
}


def get_component(key: str) -> ComponentDescriptor | None:
    return COMPONENT_CATALOG.get(key)


def list_available(kind: ComponentKind | None = None) -> list[dict[str, Any]]:
    """Return API-safe metadata. Unimplemented choices are excluded."""
    entries = [
        descriptor
        for descriptor in COMPONENT_CATALOG.values()
        if descriptor.available and (kind is None or descriptor.kind == kind)
    ]
    return [descriptor.api_metadata() for descriptor in entries]
