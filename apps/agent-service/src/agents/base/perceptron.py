"""Perceptron - Tools/Memory component for agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool


@dataclass
class PerceptionResult:
    """Result from perceptron processing."""

    tools_results: dict[str, Any] = field(default_factory=dict)
    memory_context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class Perceptron(ABC):
    """
    Perceptron - Tools/Memory component.

    Perceptrons are responsible for:
    - Loading and managing tools
    - Executing tool calls
    - Managing short-term and long-term memory
    - Processing external data (RAG, vector stores)

    Perceptrons can be composed to create complex agent behaviors.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the perceptron.

        Args:
            config: Perceptron configuration (tools, memory settings, etc.)
        """
        self._config = config or {}
        self._tools: dict[str, BaseTool] = {}

    @property
    @abstractmethod
    def perceptron_type(self) -> str:
        """Type of perceptron: tool, mcp, memory, vector, composite."""
        pass

    @abstractmethod
    async def load(self) -> None:
        """
        Load/initialize the perceptron.

        Should load tools, connect to memory stores, etc.
        """
        pass

    @abstractmethod
    async def perceive(
        self,
        input: Any,
        context: dict[str, Any] | None = None,
    ) -> PerceptionResult:
        """
        Process input through perceptron's capabilities.

        Args:
            input: Input to process
            context: Execution context

        Returns:
            PerceptionResult with tool results, memory context, metadata
        """
        pass

    def get_tools(self) -> list[BaseTool]:
        """
        Get list of available tools.

        Returns:
            List of BaseTool instances
        """
        return list(self._tools.values())

    def get_tool(self, name: str) -> BaseTool | None:
        """Get a specific tool by name."""
        return self._tools.get(name)

    def add_tool(self, tool: BaseTool) -> None:
        """Add a tool to the perceptron."""
        self._tools[tool.name] = tool

    def remove_tool(self, name: str) -> None:
        """Remove a tool from the perceptron."""
        self._tools.pop(name, None)

    def update_config(self, config: dict[str, Any]) -> None:
        """Update perceptron configuration."""
        self._config.update(config)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self._config.get(key, default)


class ToolPerceptron(Perceptron):
    """Basic perceptron with tool execution capabilities."""

    def __init__(self, tools: list[BaseTool] | None = None, config: dict[str, Any] | None = None):
        super().__init__(config)
        if tools:
            self._tools = {t.name: t for t in tools}

    @property
    def perceptron_type(self) -> str:
        return "tool"

    async def load(self) -> None:
        """Load tools - already initialized in __init__."""
        pass

    async def perceive(
        self,
        input: Any,
        context: dict[str, Any] | None = None,
    ) -> PerceptionResult:
        """Process input - return available tools info."""
        return PerceptionResult(metadata={"available_tools": list(self._tools.keys())})


class MemoryPerceptron(Perceptron):
    """Perceptron with memory management capabilities."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self._short_term: list = []
        self._long_term_store: Any = None

    @property
    def perceptron_type(self) -> str:
        return "memory"

    async def load(self) -> None:
        """Load memory store."""
        # Initialize long-term memory if configured
        if self.get_config("long_term_memory", False):
            try:
                from service.langgraph_store import get_langgraph_store

                self._long_term_store = get_langgraph_store()
            except Exception:
                pass

    async def perceive(
        self,
        input: Any,
        context: dict[str, Any] | None = None,
    ) -> PerceptionResult:
        """Process input with memory context."""
        # Add to short-term memory
        if isinstance(input, dict) and "messages" in input:
            for msg in input["messages"]:
                self._short_term.append(msg)

        # Get long-term memory if available
        memory_context = {}
        if self._long_term_store and context and context.get("user_id"):
            try:
                from memory.long_term import build_event_emitters, recall_memories

                on_recall, _ = build_event_emitters(context)
                memories = await recall_memories(self._long_term_store, context["user_id"], on_recall=on_recall)
                memory_context = {"memories": memories}
            except Exception:
                pass

        return PerceptionResult(
            memory_context=memory_context, metadata={"short_term_size": len(self._short_term)}
        )

    def add_to_memory(self, item: Any) -> None:
        """Add item to short-term memory."""
        self._short_term.append(item)

    def clear_short_term(self) -> None:
        """Clear short-term memory."""
        self._short_term.clear()

    def get_recent(self, count: int = 10) -> list:
        """Get recent memory items."""
        return self._short_term[-count:]


class VectorPerceptron(Perceptron):
    """Perceptron with vector store / RAG capabilities."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self._vector_store: Any = None
        self._embeddings: Any = None

    @property
    def perceptron_type(self) -> str:
        return "vector"

    async def load(self) -> None:
        """Load vector store."""
        # Load from config
        collection_name = self.get_config("collection_name")
        if collection_name:
            try:
                from agents.tools import load_vector_store

                self._vector_store = load_vector_store(collection_name)
            except Exception:
                pass

    async def perceive(
        self,
        input: Any,
        context: dict[str, Any] | None = None,
    ) -> PerceptionResult:
        """Process input with vector search if needed."""
        return PerceptionResult(metadata={})

    async def search(
        self,
        query: str,
        k: int = 4,
    ) -> list[Any]:
        """Search vector store."""
        if not self._vector_store:
            return []

        try:
            return await self._vector_store.asimilarity_search(query, k=k)
        except Exception:
            return []

    async def add_documents(self, documents: list[Any]) -> None:
        """Add documents to vector store."""
        if self._vector_store:
            await self._vector_store.aadd_documents(documents)
