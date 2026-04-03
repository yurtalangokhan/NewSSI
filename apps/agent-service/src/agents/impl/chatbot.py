"""
Chatbot Agent - Using Brain/Perceptron architecture.

This agent demonstrates the Brain + Perceptron pattern:
- Brain: LLM for reasoning/generating responses
- Perceptron: Memory for context management
"""

import asyncio
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.store.base import BaseStore

from agents.base.agent import BaseAgent
from agents.base.brain import LLMBrain
from agents.base.perceptron import MemoryPerceptron

logger = logging.getLogger(__name__)


class ChatbotAgent(BaseAgent):
    """
    Chatbot agent using Brain/Perceptron architecture.

    Components:
    - Brain: LLMBrain (uses configured LLM)
    - Perceptron: MemoryPerceptron (handles long-term memory)
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self._brain: LLMBrain | None = None
        self._perceptron: MemoryPerceptron | None = None
        self._graph: Any = None
        self._loaded = False

    @property
    def name(self) -> str:
        return "chatbot"

    @property
    def agent_type(self) -> str:
        return "basic"

    @property
    def description(self) -> str:
        return "A simple chatbot with memory support"

    async def load(self) -> None:
        """Initialize brain, perceptron and graph."""
        if self._loaded:
            return

        # Initialize brain
        model_name = self.get_config("model", "gpt-4o-mini")
        self._brain = LLMBrain(
            config={
                "model": model_name,
                "temperature": self.get_config("temperature", 0.7),
            },
            system_prompt=self.get_config("system_prompt", "You are a helpful assistant."),
        )
        await self._brain.load()

        # Initialize perceptron (memory)
        self._perceptron = MemoryPerceptron(
            config={"long_term_memory": self.get_config("long_term_memory", False)}
        )
        await self._perceptron.load()

        # Build LangGraph workflow
        self._graph = self._build_graph()
        self._loaded = True
        logger.info("ChatbotAgent loaded")

    def _build_graph(self) -> Any:
        """Build the LangGraph workflow."""

        async def call_model(
            state: MessagesState, config: RunnableConfig, *, store: BaseStore
        ) -> MessagesState:
            """Process messages through brain and perceptron."""
            messages = state["messages"]
            configurable = config.get("configurable", {})

            # Perceptron: process memory context
            perception = await self._perceptron.perceive(
                {"messages": messages}, {"user_id": configurable.get("user_id")}
            )

            # Inject memory context into messages
            if perception.memory_context.get("memories"):
                memory_context = perception.memory_context["memories"]
                if memory_context:
                    from memory.long_term import build_memory_context

                    ctx = build_memory_context(memory_context)
                    if ctx:
                        messages = [SystemMessage(content=ctx)] + list(messages)

            # Brain: invoke LLM
            reasoning_result = await self._brain.think({"messages": messages})

            return {"messages": reasoning_result.messages}

        workflow = StateGraph(MessagesState)
        workflow.add_node("model", call_model)
        workflow.set_entry_point("model")
        workflow.add_edge("model", END)

        return workflow.compile()

    async def invoke(
        self, input: Any, config: RunnableConfig | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """Synchronous invoke."""
        await self.load()

        # Ensure messages format
        if isinstance(input, str):
            input = {"messages": [HumanMessage(content=input)]}

        result = await self._graph.ainvoke(input, config=config, **kwargs)
        return result

    async def stream(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any):
        """Streaming invoke."""
        await self.load()

        if isinstance(input, str):
            input = {"messages": [HumanMessage(content=input)]}

        async for chunk in self._graph.astream(input, config=config, **kwargs):
            yield chunk

    async def astream_events(
        self, input: Any, config: RunnableConfig | None = None, version: str = "v2", **kwargs: Any
    ):
        """Stream events."""
        await self.load()

        if isinstance(input, str):
            input = {"messages": [HumanMessage(content=input)]}

        async for event in self._graph.astream_events(
            input, config=config, version=version, **kwargs
        ):
            yield event

    def get_graph(self) -> Any:
        """Get the LangGraph graph."""
        if not self._loaded:
            asyncio.run(self.load())
        return self._graph


# Singleton instance for backward compatibility
_chatbot_instance: ChatbotAgent | None = None


def get_chatbot_agent(config: dict[str, Any] | None = None) -> ChatbotAgent:
    """Get or create chatbot agent instance."""
    global _chatbot_instance
    if _chatbot_instance is None:
        _chatbot_instance = ChatbotAgent(config)
    return _chatbot_instance


# Legacy export - create instance but don't load yet
# Loading happens on first get_graph() call
def _create_chatbot():
    """Factory function for backward compatibility."""
    return get_chatbot_agent()


# At module level, just provide the factory - don't evaluate
# This allows lazy loading which is required for the service
chatbot = _create_chatbot()
