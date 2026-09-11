"""Explicit lifecycle ownership for agent runtime resources.

ComposedAgent.load() acquires resources in dependency order.
ComposedAgent.close() releases them in reverse order.
Both operations are idempotent — calling load() twice or close() twice
has no additional effect beyond the first call.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.pregel import Pregel

logger = get_logger(__name__)


class AgentLifecycle(ABC):
    """Abstract lifecycle contract for agent runtime resources."""

    @abstractmethod
    async def load(self) -> None:
        """Acquire all runtime resources in dependency order.

        Subclasses should override this to perform async graph compilation,
        tool gateway loading, model initialization, or store acquisition.
        """
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    async def close(self) -> None:
        """Release all runtime resources in reverse dependency order.

        Subclasses should override this to close model clients, tool gateways,
        MCP transports, and graph resources.
        """
        raise NotImplementedError  # pragma: no cover

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Return True if load() has completed successfully."""
        raise NotImplementedError  # pragma: no cover


class IdempotentLifecycle(AgentLifecycle):
    """Wraps a lifecycle with idempotent load/close semantics.

    A lock prevents concurrent load() from racing. The first caller
    performs the actual load; concurrent callers await the same operation.
    """

    def __init__(self) -> None:
        self._loaded = False
        self._loading: asyncio.Lock | None = None
        self._closing: asyncio.Lock | None = None

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def _ensure_locks(self) -> None:
        if self._loading is None:
            self._loading = asyncio.Lock()
        if self._closing is None:
            self._closing = asyncio.Lock()

    async def ensure_loaded(self) -> None:
        """Ensure the wrapped agent is loaded, waiting if load is in progress."""
        if self._loaded:
            return
        await self._ensure_locks()
        async with self._loading:
            # Double-check after acquiring the lock
            if self._loaded:
                return
            await self.load()

    async def load(self) -> None:
        """Override in subclass to perform actual resource acquisition."""
        raise NotImplementedError  # pragma: no cover

    async def close(self) -> None:
        """Override in subclass to perform actual resource release."""
        raise NotImplementedError  # pragma: no cover

    async def close_idempotent(self) -> None:
        """Idempotent close — safe to call multiple times."""
        await self._ensure_locks()
        if not self._loaded:
            return
        async with self._closing:
            if not self._loaded:
                return  # Already closed by another caller
            await self.close()
            self._loaded = False


class GraphResource:
    """Wraps the compiled LangGraph runtime handle with lifecycle awareness."""

    def __init__(self) -> None:
        self._graph: CompiledStateGraph | Pregel | None = None

    def assign_graph(self, graph: CompiledStateGraph | Pregel) -> None:
        """Assign the compiled graph after successful load."""
        if self._graph is not None:
            raise RuntimeError("Graph already assigned.")
        self._graph = graph

    @property
    def graph(self) -> CompiledStateGraph | Pregel:
        """Return the compiled graph.

        Raises:
            RuntimeError: if the graph has not been loaded.
        """
        if self._graph is None:
            raise RuntimeError("Graph not loaded.")
        return self._graph

    @property
    def is_ready(self) -> bool:
        return self._graph is not None
