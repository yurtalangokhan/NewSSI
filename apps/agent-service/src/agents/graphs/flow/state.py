"""FlowState, ResolvedResources, and state management for flow graphs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from core.exceptions import NotAResourceNodeError
from core.observability.logger import get_logger
from schemas.flows import ComponentKind, ComponentTemplate, FlowNode
from service.flow_model.registry import ComponentRegistry

logger = get_logger(__name__)

_MODEL_RESOURCE_TYPES = frozenset({"LLMModel", "OllamaModel"})
_TOOL_RESOURCE_TYPES = frozenset(
    {
        "CalculatorTools",
        "CodeTools",
        "CommandTools",
        # DockerTools and ServiceTools were removed from tools-service
        # (spec TS-4): both shelled out with shell=True to run arbitrary
        # docker/systemctl commands. A flow referencing either now gets a
        # normal "resource not found" error instead of a resource type
        # that validates but can never actually run.
        "FileTools",
        "GitTools",
        "JavaTools",
        "JsonTools",
        "PdfTools",
        "TextTools",
        "TimeTools",
        "UtilityTools",
        "WebTools",
        "MailTools",
        "ExternalMCPServer",
    }
)


def _merge_scratch(current: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge scratch updates. Same key: last write wins — deliberate,
    since a node re-run (e.g. inside a Loop) should overwrite its own prior
    output, not accumulate it."""
    return {**current, **update}


def _merge_arrivals(current: list[tuple[str, Any]], update: list[tuple[str, Any]] | None) -> list[tuple[str, Any]]:
    """Append arrivals, except that ``None`` clears the channel.

    ``arrivals`` is checkpointed, so a plain accumulating reducer would carry
    a thread's turn-one arrivals into turn two and a "first" Merge would keep
    answering with the earlier turn's branch forever. A write cannot express
    "empty" against an accumulator, so ``None`` is the reset signal — the same
    role ChatInput's zeroed counters play for While / If-Else / foreach.
    """
    if update is None:
        return []
    return [*current, *update]


class FlowState(TypedDict):
    """Shared state every compiled flow uses.

    ``messages`` reuses LangGraph's own accumulation reducer — no custom
    message-merging logic. ``scratch`` carries node-to-node non-message data
    (e.g. a TextInput's configured value, a PromptTemplate's rendered text).
    ``arrivals`` records ``(merge_id, message)`` pairs in super-step order so
    a first/last Merge can tell which branch reached it first — the flat
    ``messages`` list cannot answer that.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    scratch: Annotated[dict[str, Any], _merge_scratch]
    arrivals: Annotated[list[tuple[str, Any]], _merge_arrivals]


def is_tool_mode(node: FlowNode, template: ComponentTemplate) -> bool:
    """Whether this node is configured as an agent tool rather than a step.

    The capability is declared by the template (``tool_mode_field``); a value
    on a component that never declared it is ignored, not honoured.
    """
    field = template.tool_mode_field
    return bool(field) and bool(node.values.get(field, False))


def partition_nodes(nodes: list[FlowNode], registry: ComponentRegistry) -> tuple[list[FlowNode], list[FlowNode]]:
    """Split nodes into (resources, executions), preserving original order.

    Resources are build-time injected into whichever execution node they
    feed; only executions become StateGraph nodes. See design spec 4.3.

    Raises UnknownComponentError for a node type the registry doesn't know —
    by this point (post-validation) that is a programming error, not a
    user-facing validation result.
    """
    resources: list[FlowNode] = []
    executions: list[FlowNode] = []
    for node in nodes:
        if node.type in ("note", "noteNode"):
            continue
        template = registry.get(node.type)  # raises UnknownComponentError
        # A tool-mode node is a resource for this run: the agent calls it, the
        # flow does not run it. That is a per-node mode, so `kind` alone is
        # not enough to decide.
        if template.kind is ComponentKind.RESOURCE or is_tool_mode(node, template):
            resources.append(node)
        else:
            executions.append(node)
    return resources, executions


@dataclass(frozen=True)
class ResolvedResources:
    """What execution nodes consume, keyed by the resource node's own id."""

    models: dict[str, BaseChatModel] = field(default_factory=dict)
    tool_names: dict[str, list[str]] = field(default_factory=dict)
    mail_config_ids: dict[str, str] = field(default_factory=dict)
    datasource_ids: dict[str, str] = field(default_factory=dict)


def _resolve_model(node: FlowNode) -> BaseChatModel:
    """Resolve a Model resource to a real BaseChatModel."""
    from config_manager import env

    from infrastructure.llm import get_model

    model_name = node.values.get("model") or env.DEFAULT_MODEL
    return get_model(model_name)


def resolve_resources(resource_nodes: list[FlowNode], tool_mode_ids: set[str] | None = None) -> ResolvedResources:
    """Resolve every resource node to the object its consumers actually need.

    Raises NotAResourceNodeError for an execution-kind node — partition_nodes
    should already have kept those out; reaching this is a contract violation
    upstream, not a recoverable condition.

    ``tool_mode_ids`` names the nodes that are resources only because they are
    in tool mode. They are execution components by kind, so they have nothing
    to resolve here — ``make_component_tool`` builds their tool instead.
    """
    skip = tool_mode_ids or set()
    models: dict[str, BaseChatModel] = {}
    tool_names: dict[str, list[str]] = {}
    mail_config_ids: dict[str, str] = {}
    datasource_ids: dict[str, str] = {}
    for node in resource_nodes:
        if node.id in skip:
            continue
        if node.type in _MODEL_RESOURCE_TYPES:
            models[node.id] = _resolve_model(node)
        elif node.type in _TOOL_RESOURCE_TYPES:
            tools = node.values.get("tools") or []
            if isinstance(tools, list):
                tool_names[node.id] = [str(t) for t in tools]
            elif isinstance(tools, str):
                tool_names[node.id] = [tools]
            else:
                tool_names[node.id] = []
        elif node.type == "MailConfig":
            mail_config_ids[node.id] = str(node.values.get("config_id") or "")
        elif node.type == "ConnectorDatasource":
            datasource_ids[node.id] = str(node.values.get("datasource_id") or "")
        elif node.type in {"LongTermMemory", "ThreadCheckpointer"}:
            pass
        else:
            raise NotAResourceNodeError(node.id, node.type)
    return ResolvedResources(
        models=models,
        tool_names=tool_names,
        mail_config_ids=mail_config_ids,
        datasource_ids=datasource_ids,
    )


def _select_model(resources: ResolvedResources, model_node_id: str | None) -> BaseChatModel | None:
    """Pick the model for one agent node.

    An explicit `model_node_id` (the resource actually wired to this node via
    a Model-typed edge — Task 10 supplies it) always wins. Without one, a
    single-model flow falls back to its only resource; with zero or multiple
    unresolved candidates there is no safe guess, so this returns None and
    GraphBuilder falls back to env.DEFAULT_MODEL, matching a classic
    agent with no LLM override.
    """
    if model_node_id is not None:
        return resources.models.get(model_node_id)
    if len(resources.models) == 1:
        return next(iter(resources.models.values()))
    return None
