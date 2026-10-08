"""Agent types with async initialization and dynamic graph creation.

``LazyLoadingAgent`` is the base every concrete agent still extends
(DynamicAgent, ConfigurableMCPAgent, FlowAgent, GitHubMCPAgent). It exists
because an agent must be callable exactly like a compiled LangGraph graph:
``ainvoke(input, config)``, ``astream``, ``aget_state`` and friends, which is
what the streaming stack and every flow node expect.

``agent_composition.runtime.ComposedAgent`` is not a drop-in replacement for
it. That class takes domain request objects (``AgentRunRequest``,
``StateRequest``) instead, so swapping one for the other means rewriting every
caller of the runnable-shaped interface, not changing a base class. Until that
is a deliberate piece of work, this class is the runtime, not a shim.

What the two did share — long-term memory recall — now lives once, in
``memory.recall``; both call it.
"""

from abc import ABC, abstractmethod
import asyncio
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

from core.observability.logger import get_logger
from memory.long_term import extract_memories_for_turn
from memory.recall import (
    build_memory_recall_event,
    inject_memory_into_input,
    mark_input_with_ltm_recalled,
    resolve_langgraph_store,
    tag_output_with_recalled_memories,
)

logger = get_logger(__name__)


class LazyLoadingAgent(ABC):
    """Base class for agents that require async loading.

    This class is kept for backward compatibility with existing subclasses.
    New code should use agent_composition.runtime.ComposedAgent.

    The class owns the following split responsibilities (now delegatable):
    - lifecycle: _loaded flag, ensure_loaded(), load()/close() contract
    - checkpoint: aget_state, aupdate_state, aget_state_history delegation
    - memory: _inject_memory_into_input, _save_memory_from_output, event builders
    - execution context: user/tenant identity from RunnableConfig

    Subclasses must:
    - Implement load() to set self._graph
    - Call super().__init__() before using any inherited method
    """

    def __init__(self) -> None:
        """Initialize the agent."""
        self._loaded = False
        self._graph: CompiledStateGraph | Pregel | None = None
        self._load_lock = asyncio.Lock()

    @abstractmethod
    async def load(self) -> None:
        """
        Perform async loading for this agent.

        This method is called during service startup and should handle:
        - Setting up external connections (MCP clients, databases, etc.)
        - Loading tools or resources
        - Any other async setup required
        - Creating the agent's graph and assigning it to self._graph
        """
        raise NotImplementedError  # pragma: no cover

    async def ensure_loaded(self) -> None:
        """Ensure the agent is loaded, exactly once.

        Without the lock, concurrent first requests all saw ``_loaded`` False
        and each ran ``load()`` — duplicating the MCP connections and graph
        compilation the load performs, and racing on the attributes it sets.
        """
        if self._loaded:
            return
        async with self._load_lock:
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

    async def aupdate_state(self, config, values, **kwargs):
        """Delegate aupdate_state to the underlying compiled graph.

        Used by AgentHelpers._handle_input to replace an edited message's
        content in place on a forked checkpoint before regenerating a
        response — without this, every subclass (ConfigurableMCPAgent,
        DynamicAgent, CommandAgent, GitHubMCPAgent, the supervisor agents)
        would raise AttributeError when a user edits a message sent to a
        custom agent.
        """
        await self.ensure_loaded()
        return await self._graph.aupdate_state(config, values, **kwargs)

    async def aget_state_history(self, config=None, **kwargs):
        """Delegate aget_state_history to the underlying compiled graph.

        Used by CheckpointBranchService.find_fork_point to locate where a
        retry should fork its checkpoint from — without this, every
        subclass (ConfigurableMCPAgent, DynamicAgent, CommandAgent,
        GitHubMCPAgent, the supervisor agents) would silently fall back to
        appending the retry to the thread's tip instead of forking.
        """
        await self.ensure_loaded()
        async for snapshot in self._graph.aget_state_history(config=config, **kwargs):
            yield snapshot

    @staticmethod
    def _get_langgraph_store():
        """Get the global LangGraph store for long-term memory."""
        return resolve_langgraph_store()

    @staticmethod
    def _build_memory_recall_event(memories: dict[str, Any]) -> dict[str, Any] | None:
        """Build a custom stream event payload for recalled memories."""
        return build_memory_recall_event(memories)

    @staticmethod
    def _mark_input_with_ltm_recalled(input: Any, recalled_count: int) -> Any:
        """Attach recalled-memory count to the latest user message."""
        return mark_input_with_ltm_recalled(input, recalled_count)

    @staticmethod
    def _tag_output_with_recalled_memories(output: Any, memories: dict[str, Any]) -> Any:
        """Tag response messages so chat history can replay memory recall."""
        return tag_output_with_recalled_memories(output, memories)

    async def _inject_memory_into_input(
        self,
        input: Any,
        config: RunnableConfig | None = None,
    ) -> tuple[Any, dict, str | None]:
        """Recall long-term memories and prepend them to *input*.

        Returns (modified_input, memories_dict, user_id).
        """
        return await inject_memory_into_input(input, config)

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
            from config_manager import env

            from infrastructure.llm.llm import get_model_from_config

            model = get_model_from_config(configurable, env.DEFAULT_MODEL)

            # Get the response messages from output
            output_messages = []
            if isinstance(output, dict) and "messages" in output:
                output_messages = output["messages"]

            all_messages = list(original_messages) + list(output_messages)
            await extract_memories_for_turn(user_id, configurable, all_messages, model, memories)
        except Exception as e:
            logger.warning(f"[LazyAgent] Memory save failed: {e}")

    async def ainvoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:
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
        result = self._tag_output_with_recalled_memories(result, memories)

        # Save memories from output
        await self._save_memory_from_output(result, original_messages, memories, user_id, config)

        return result

    async def astream(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any):
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

        recall_event = self._build_memory_recall_event(memories)
        if recall_event is not None:
            yield ("custom", recall_event)

        collected_output = None
        async for chunk in self._graph.astream(input, config=config, **kwargs):
            chunk = self._tag_output_with_recalled_memories(chunk, memories)
            collected_output = chunk
            yield chunk

        # Save memories from the last chunk
        if collected_output is not None:
            await self._save_memory_from_output(collected_output, original_messages, memories, user_id, config)

    async def astream_events(
        self, input: Any, config: RunnableConfig | None = None, version: str = "v2", **kwargs: Any
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

        # Collect AI response messages from events for higher-quality extraction
        response_messages: list = []
        async for event in self._graph.astream_events(input, config=config, version=version, **kwargs):
            # Capture AI responses from model end events
            if event.get("event") == "on_chat_model_end":
                output = event.get("data", {}).get("output")
                if output is not None and hasattr(output, "content"):
                    response_messages.append(output)
            yield event

        # Save memories after streaming completes using full conversation (input + response)
        configurable = (config or {}).get("configurable", {})
        if configurable.get("long_term_memory", False) and user_id:
            try:
                store = self._get_langgraph_store()
                if store:
                    from config_manager import env

                    from infrastructure.llm.llm import get_model_from_config

                    model = get_model_from_config(configurable, env.DEFAULT_MODEL)
                    all_messages = list(original_messages) + response_messages
                    await extract_memories_for_turn(user_id, configurable, all_messages, model, memories)
            except Exception as e:
                logger.warning(f"[LazyAgent] Memory save after stream_events failed: {e}")
