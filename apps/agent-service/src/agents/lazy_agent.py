"""Agent types with async initialization and dynamic graph creation."""

import logging
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

from memory.long_term import (
    build_event_emitters,
    build_memory_context,
    extract_and_save_memories,
    recall_memories,
    tag_response_with_ltm_recall,
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

    def _get_langgraph_store(self):
        """Get the global LangGraph store for long-term memory."""
        try:
            from service.LangGraphStoreService import get_langgraph_store

            return get_langgraph_store()
        except Exception as exc:
            logger.warning("[LazyAgent] Could not resolve LangGraph store: %s", exc)
            return None

    @staticmethod
    def _build_memory_recall_event(memories: dict[str, Any]) -> dict[str, Any] | None:
        """Build a custom stream event payload for recalled memories."""
        facts = memories.get("user_facts", [])
        if not facts:
            return None
        return {
            "type": "long_term_memory_recall",
            "fact_count": len(facts),
            "memories": facts,
        }

    @staticmethod
    def _mark_input_with_ltm_recalled(input: Any, recalled_count: int) -> Any:
        """Attach recalled-memory count to the latest user message for refresh reconstruction."""
        if recalled_count <= 0:
            return input
        if not isinstance(input, dict) or "messages" not in input:
            return input

        messages = list(input.get("messages") or [])
        for idx in range(len(messages) - 1, -1, -1):
            msg = messages[idx]

            if isinstance(msg, dict):
                msg_type = msg.get("type", "")
                if msg_type not in ("human", "user"):
                    continue
                extra = msg.get("additional_kwargs", {}) or {}
                extra["_ltm_recalled"] = recalled_count
                msg["additional_kwargs"] = extra
                messages[idx] = msg
                return {**input, "messages": messages}

            msg_type = getattr(msg, "type", None)
            if msg_type not in ("human", "user"):
                continue
            extra = getattr(msg, "additional_kwargs", {}) or {}
            extra["_ltm_recalled"] = recalled_count
            setattr(msg, "additional_kwargs", extra)
            messages[idx] = msg
            return {**input, "messages": messages}

        return input

    @staticmethod
    def _tag_output_with_recalled_memories(output: Any, memories: dict[str, Any]) -> Any:
        """Tag response messages so chat history can replay memory recall after refresh."""
        if not memories.get("user_facts"):
            return output

        if isinstance(output, dict) and output.get("messages"):
            tag_response_with_ltm_recall(output["messages"][-1], memories)
            return output

        # 2-tuples: (stream_mode, payload); 3-tuples with subgraphs=True: (path, stream_mode, payload).
        if isinstance(output, tuple) and len(output) in (2, 3):
            stream_mode, payload = output[-2], output[-1]
            if stream_mode == "updates" and isinstance(payload, dict):
                for updates in payload.values():
                    if isinstance(updates, dict) and updates.get("messages"):
                        tag_response_with_ltm_recall(updates["messages"][-1], memories)
            elif stream_mode == "values" and isinstance(payload, dict) and payload.get("messages"):
                tag_response_with_ltm_recall(payload["messages"][-1], memories)

        return output

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

        on_recall, _ = build_event_emitters(configurable)
        memories = await recall_memories(store, user_id, on_recall=on_recall)
        recalled_count = len(memories.get("user_facts", []))
        input = self._mark_input_with_ltm_recalled(input, recalled_count)
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
        on_save=None,
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
            extract_mem = configurable.get("extract_memory", True)
            await extract_and_save_memories(
                store,
                user_id,
                all_messages,
                model,
                memories,
                on_save=on_save,
                extract_memory=extract_mem,
            )
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
        configurable = (config or {}).get("configurable", {})
        _, on_save = build_event_emitters(configurable)
        await self._save_memory_from_output(
            result, original_messages, memories, user_id, config, on_save=on_save
        )

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
            configurable = (config or {}).get("configurable", {})
            _, on_save = build_event_emitters(configurable)
            await self._save_memory_from_output(
                collected_output,
                original_messages,
                memories,
                user_id,
                config,
                on_save=on_save,
            )

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
        async for event in self._graph.astream_events(
            input, config=config, version=version, **kwargs
        ):
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
                    from core import settings
                    from core.llm import get_model_from_config

                    model = get_model_from_config(configurable, settings.DEFAULT_MODEL)
                    extract_mem = configurable.get("extract_memory", True)
                    _, on_save = build_event_emitters(configurable)
                    all_messages = list(original_messages) + response_messages
                    await extract_and_save_memories(
                        store,
                        user_id,
                        all_messages,
                        model,
                        memories,
                        on_save=on_save,
                        extract_memory=extract_mem,
                    )
            except Exception as e:
                logger.warning(f"[LazyAgent] Memory save after stream_events failed: {e}")
