"""Checkpoint state access adapter.

Provides typed wrappers around LangGraph's aget_state, aupdate_state, and
aget_state_history so that ComposedAgent does not import LangGraph types
directly. This keeps the runtime layer framework-agnostic.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.pregel import Pregel

logger = logging.getLogger(__name__)


class CheckpointAdapter:
    """Wraps a compiled LangGraph runtime for typed state operations.

    This adapter keeps checkpoint and state operations isolated from
    the ComposedAgent's main execution path, making them independently
    testable.
    """

    def __init__(self, graph: CompiledStateGraph | Pregel | None = None) -> None:
        self._graph: CompiledStateGraph | Pregel | None = graph

    def attach_graph(self, graph: CompiledStateGraph | Pregel) -> None:
        """Attach the compiled graph after load."""
        if self._graph is not None:
            raise RuntimeError("Graph already attached to CheckpointAdapter.")
        self._graph = graph

    @property
    def _g(self) -> CompiledStateGraph | Pregel:
        if self._graph is None:
            raise RuntimeError(
                "CheckpointAdapter has no graph attached. Call attach_graph() after load()."
            )
        return self._graph

    async def aget_state(self, config: RunnableConfig | None = None, **kwargs: Any) -> Any:
        """Delegate aget_state to the underlying compiled graph."""
        return await self._g.aget_state(config=config, **kwargs)

    async def aupdate_state(
        self, config: RunnableConfig, values: dict[str, Any], **kwargs: Any
    ) -> Any:
        """Delegate aupdate_state to the underlying compiled graph.

        Used by AgentHelpers._handle_input to replace an edited message's
        content in place on a forked checkpoint before regenerating a
        response — without this, every agent subclass would raise
        AttributeError when a user edits a message sent to a custom agent.
        """
        return await self._g.aupdate_state(config, values, **kwargs)

    async def aget_state_history(self, config: RunnableConfig | None = None, **kwargs: Any):
        """Delegate aget_state_history to the underlying compiled graph.

        Used by CheckpointBranchService.find_fork_point to locate where a
        retry should fork its checkpoint from — without this, every agent
        subclass would silently fall back to appending the retry to the
        thread's tip instead of forking.
        """
        async for snapshot in self._g.aget_state_history(config=config, **kwargs):
            yield snapshot
