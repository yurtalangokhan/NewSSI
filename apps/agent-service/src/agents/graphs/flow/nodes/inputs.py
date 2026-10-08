"""Flow input node factories (chat input, text input, prompt template)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from agents.graphs.flow.nodes.routing import (
    _condrouter_counter_key,
    _foreach_agg_key,
    _foreach_idx_key,
    _foreach_items_key,
    _loop_counter_key,
)
from agents.graphs.flow.state import FlowState
from core.exceptions import FlowBuildError
from core.observability.logger import get_logger
from schemas.flows import FlowNode
from service.flow_model.safe_format import UnsafeTemplateError, safe_format

logger = get_logger(__name__)


def _make_chat_input_node(
    while_ids: Sequence[str],
    condrouter_ids: Sequence[str],
    foreach_ids: Sequence[str] = (),
) -> Any:
    """ChatInput resets every per-turn iteration state, making each bound per
    *turn*.

    ``scratch`` is checkpointed, so without this a thread's second turn would
    start at the previous turn's count (While / If-Else) or think a Loop is
    mid-iteration, and the loop would misbehave. The ordered ``arrivals``
    channel is checkpointed too and is cleared here for the same reason: a
    "first" Merge must name this turn's earliest branch, not turn one's.

    ChatInput is the right place for it: it declares no input handle, so no
    edge can route back into it, and ``START -> ChatInput`` therefore runs
    exactly once per turn — before any router reads its state. An interrupt
    resume deliberately does *not* re-run it, because the same turn must keep
    counting.
    """
    reset: dict[str, Any] = {}
    for i in while_ids:
        reset[_loop_counter_key(i)] = 0
    for i in condrouter_ids:
        reset[_condrouter_counter_key(i)] = 0
    for i in foreach_ids:
        reset[_foreach_items_key(i)] = None
        reset[_foreach_idx_key(i)] = 0
        reset[_foreach_agg_key(i)] = []

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        return {"scratch": dict(reset), "arrivals": None}

    return _run


def _make_text_input_node(node: FlowNode) -> Any:
    """Langflow's Text Input emits a ``Message``. It also keeps its
    ``scratch[node.id]`` slot so a downstream Prompt Template can still read it
    as ``{node-id}``; the message is what lets it feed an agent or Chat Output.
    """
    text = node.values.get("text", "")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        return {"scratch": {node.id: text}, "messages": [HumanMessage(content=str(text))]}

    return _run


def _make_prompt_template_node(node: FlowNode) -> Any:
    """Substitutes `{node_id}` / `{variable}` placeholders from `scratch`.

    Placeholders are the *source node id* of an incoming edge, or a Set
    Variable name (Phase 0). Like Langflow's Prompt Template this emits the
    rendered text as a ``Message`` so it can feed an agent or Chat Output;
    it also keeps writing ``scratch[node.id]`` so a chained Prompt Template
    can still interpolate ``{node-id}``.
    """
    template = node.values.get("template", "")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        try:
            rendered = safe_format(template, state.get("scratch", {}))
        except KeyError as exc:
            raise KeyError(
                f"PromptTemplate '{node.id}' references {exc}, which is not "
                "present in scratch — check the incoming edge is wired"
            ) from exc
        except UnsafeTemplateError as exc:
            # Flow validation (validator.py) rejects a template shaped like
            # this before it can be saved; this only fires for a flow saved
            # before that check existed, or edited to bypass validation.
            raise FlowBuildError(f"PromptTemplate '{node.id}' has an unsafe template: {exc}") from exc
        return {
            "scratch": {node.id: rendered},
            "messages": [HumanMessage(content=rendered)],
        }

    return _run
