"""Agent types with async initialization and dynamic graph creation."""

import logging
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

from memory.long_term import (
    build_memory_context,
    extract_and_save_memories,
    recall_memories,
)

logger = logging.getLogger(__name__)


class LazyLoadingAgent(ABC):
    """Base class for agents that require async loading."""

    def __init__(self) -> None:
        """Initialize the agent."""
        self._loaded = False
        self._graph: CompiledStateGraph | Pregel | None = None

    @abstractmethod
    async def load(self) -> None:
        """
        Perform async loading for this agent.

        This method is called during service startup and should handle:
        - Setting up external connections (MCP clients, databases, etc.)
        - Loading tools or resources
        - Any other async setup required
        - Creating the agent's graph
        """
        raise NotImplementedError  # pragma: no cover
    
    async def ensure_loaded(self) -> None:
        """Ensure the agent is loaded."""
        if not self._loaded:
            await self.load()

    def get_graph(self) -> CompiledStateGraph | Pregel:
        """
        Get the agent's graph.

        Returns the graph instance that was created during load().

        Returns:
            The agent's graph (CompiledStateGraph or Pregel)
        """
        if not self._loaded:
            raise RuntimeError("Agent not loaded. Call load() first.")
        if self._graph is None:
            raise RuntimeError("Agent graph not created during load().")
        return self._graph

    async def aget_state(self, config=None, **kwargs):
        """Delegate aget_state to the underlying compiled graph."""
        await self.ensure_loaded()
        return await self._graph.aget_state(config=config, **kwargs)

    def _get_langgraph_store(self):
        """Get the global LangGraph store for long-term memory."""
        try:
            from service.langgraph_store import get_langgraph_store
            return get_langgraph_store()
        except Exception:
            return None

    async def _inject_memory_into_input(
        self,
        input: Any,
        config: RunnableConfig | None = None,
    ) -> tuple[Any, dict, str | None]:
        """
        If long_term_memory is enabled, recall memories and prepend context
        to the first message in the input.

        Returns (modified_input, memories_dict, user_id).
        """
        configurable = (config or {}).get("configurable", {})
        long_term_memory = configurable.get("long_term_memory", False)
        user_id = configurable.get("user_id")
        store = self._get_langgraph_store()
        memories: dict = {}

        if not long_term_memory or not store or not user_id:
            return input, memories, user_id

        memories = await recall_memories(store, user_id)
        memory_context = build_memory_context(memories)

        if memory_context and isinstance(input, dict) and "messages" in input:
            # Prepend a system message with memory context
            input = {
                **input,
                "messages": [SystemMessage(content=memory_context)] + list(input["messages"]),
            }

        return input, memories, user_id

    async def _save_memory_from_output(
        self,
        output: Any,
        original_messages: list,
        memories: dict,
        user_id: str | None,
        config: RunnableConfig | None = None,
    ) -> None:
        """
        If long_term_memory is enabled, extract and save new facts from the output.
        """
        configurable = (config or {}).get("configurable", {})
        long_term_memory = configurable.get("long_term_memory", False)
        store = self._get_langgraph_store()

        if not long_term_memory or not store or not user_id:
            return

        try:
            from core import settings
            from core.llm import get_model_from_config

            model = get_model_from_config(configurable, settings.DEFAULT_MODEL)

            # Get the response messages from output
            output_messages = []
            if isinstance(output, dict) and "messages" in output:
                output_messages = output["messages"]
            
            all_messages = list(original_messages) + list(output_messages)
            await extract_and_save_memories(store, user_id, all_messages, model, memories)
        except Exception as e:
            logger.warning(f"[LazyAgent] Memory save failed: {e}")

    async def ainvoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any
    ) -> Any:
        """
        Default async invoke - proxies to the graph with long-term memory support.
        Subclasses can override for dynamic configuration.
        """
        await self.ensure_loaded()

        # Save original messages for memory extraction
        original_messages = []
        if isinstance(input, dict) and "messages" in input:
            original_messages = list(input["messages"])

        # Inject memory context
        input, memories, user_id = await self._inject_memory_into_input(input, config)

        result = await self._graph.ainvoke(input, config=config, **kwargs)

        # Save memories from output
        await self._save_memory_from_output(result, original_messages, memories, user_id, config)

        return result
    
    async def astream(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any
    ):
        """
        Default async stream - proxies to the graph with long-term memory support.
        Subclasses can override for dynamic configuration.
        """
        await self.ensure_loaded()

        # Save original messages for memory extraction
        original_messages = []
        if isinstance(input, dict) and "messages" in input:
            original_messages = list(input["messages"])

        # Inject memory context
        input, memories, user_id = await self._inject_memory_into_input(input, config)

        collected_output = None
        async for chunk in self._graph.astream(input, config=config, **kwargs):
            collected_output = chunk
            yield chunk

        # Save memories from the last chunk
        if collected_output is not None:
            await self._save_memory_from_output(
                collected_output, original_messages, memories, user_id, config
            )
    
    async def astream_events(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        version: str = "v2",
        **kwargs: Any
    ):
        """
        Default async stream events - proxies to the graph with long-term memory support.
        Subclasses can override for dynamic configuration.
        """
        await self.ensure_loaded()

        # Save original messages for memory extraction
        original_messages = []
        if isinstance(input, dict) and "messages" in input:
            original_messages = list(input["messages"])

        # Inject memory context
        input, memories, user_id = await self._inject_memory_into_input(input, config)

        async for event in self._graph.astream_events(input, config=config, version=version, **kwargs):
            yield event

        # Save memories after streaming completes
        # For astream_events we don't have easy access to the final output,
        # so we save based on the original messages + any context
        configurable = (config or {}).get("configurable", {})
        if configurable.get("long_term_memory", False) and user_id:
            try:
                store = self._get_langgraph_store()
                if store:
                    from core import settings
                    from core.llm import get_model_from_config

                    model = get_model_from_config(configurable, settings.DEFAULT_MODEL)
                    await extract_and_save_memories(
                        store, user_id, original_messages, model, memories
                    )
            except Exception as e:
                logger.warning(f"[LazyAgent] Memory save after stream_events failed: {e}")
