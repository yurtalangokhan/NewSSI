"""Brain - LLM/reasoning component for agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage


@dataclass
class ReasoningResult:
    """Result from brain reasoning."""

    messages: list[BaseMessage]
    reasoning: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class Brain(ABC):
    """
    Brain - LLM/reasoning component.

    Brains are responsible for:
    - Selecting and invoking the LLM
    - Processing and understanding input
    - Generating output based on context
    - Chain-of-thought reasoning (optional)

    Brains can be combined with different Perceptrons to create
    different agent behaviors.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the brain.

        Args:
            config: Brain configuration (model, temperature, etc.)
        """
        self._config = config or {}
        self._model: BaseChatModel | None = None

    @property
    @abstractmethod
    def brain_type(self) -> str:
        """Type of brain: llm, reasoning, guard, multi_model."""
        pass

    @abstractmethod
    async def load(self) -> None:
        """
        Load/initialize the brain.

        Should set up the LLM connection and any required resources.
        """
        pass

    @abstractmethod
    async def think(
        self,
        input: Any,
        context: dict[str, Any] | None = None,
    ) -> ReasoningResult:
        """
        Process input through the LLM and generate output.

        Args:
            input: Input to process (can be messages, state dict, etc.)
            context: Additional context (tools results, memory, etc.)

        Returns:
            ReasoningResult with generated messages and metadata
        """
        pass

    @abstractmethod
    def get_llm(self) -> BaseChatModel:
        """
        Get the underlying LLM instance.

        Returns:
            BaseChatModel instance
        """
        pass

    def select_model(self, task: str | None = None) -> BaseChatModel:
        """
        Select appropriate model based on task.

        Args:
            task: Optional task identifier

        Returns:
            Selected BaseChatModel instance
        """
        return self.get_llm()

    def update_config(self, config: dict[str, Any]) -> None:
        """Update brain configuration."""
        self._config.update(config)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self._config.get(key, default)


class LLMBrain(Brain):
    """Standard LLM-based brain with message processing."""

    def __init__(
        self,
        model: BaseChatModel | None = None,
        system_prompt: str | None = None,
        config: dict[str, Any] | None = None,
    ):
        super().__init__(config)
        self._model = model
        self._system_prompt = system_prompt

    @property
    def brain_type(self) -> str:
        return "llm"

    async def load(self) -> None:
        """Load the LLM."""
        if self._model is None:
            from core import settings
            from core.llm import get_model_from_config

            self._model = get_model_from_config(self._config, settings.DEFAULT_MODEL)

    async def think(
        self,
        input: Any,
        context: dict[str, Any] | None = None,
    ) -> ReasoningResult:
        """Process input through LLM."""
        await self.load()

        # Convert input to messages
        messages = self._prepare_messages(input)

        # Add system prompt if present
        if self._system_prompt:
            from langchain_core.messages import SystemMessage

            messages = [SystemMessage(content=self._system_prompt)] + messages

        # Add context messages if provided
        if context and context.get("messages"):
            messages = list(context["messages"]) + messages

        # Invoke LLM
        response = await self._model.ainvoke(messages)

        return ReasoningResult(messages=[response], metadata={"model": self._model.model_name})

    def get_llm(self) -> BaseChatModel:
        """Get the LLM instance."""
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() first.")
        return self._model

    def _prepare_messages(self, input: Any) -> list[BaseMessage]:
        """Convert input to message list."""
        if isinstance(input, list):
            return input
        if isinstance(input, dict) and "messages" in input:
            return list(input["messages"])
        if isinstance(input, str):
            from langchain_core.messages import HumanMessage

            return [HumanMessage(content=input)]
        return []


class GuardBrain(Brain):
    """
    Safety-enforcing brain with content filtering.

    Wraps another brain and adds safety checks on input/output.
    """

    def __init__(
        self,
        wrapped_brain: Brain | None = None,
        config: dict[str, Any] | None = None,
    ):
        super().__init__(config)
        self._wrapped = wrapped_brain
        self._guard: Any = None

    @property
    def brain_type(self) -> str:
        return "guard"

    async def load(self) -> None:
        """Load the guard and wrapped brain."""
        if self._wrapped:
            await self._wrapped.load()

        # Load llama guard if available
        try:
            from agents.llama_guard import LlamaGuard

            self._guard = LlamaGuard()
        except ImportError:
            pass

    async def think(
        self,
        input: Any,
        context: dict[str, Any] | None = None,
    ) -> ReasoningResult:
        """Process with safety checks."""
        # Check input safety
        if self._guard:
            input_safe = self._guard.check_input(input)
            if not input_safe:
                from langchain_core.messages import AIMessage

                return ReasoningResult(
                    messages=[AIMessage(content="Input blocked by safety filter.")],
                    metadata={"blocked": "input"},
                )

        # Process through wrapped brain
        if self._wrapped:
            result = await self._wrapped.think(input, context)
        else:
            result = ReasoningResult(messages=[])

        # Check output safety
        if self._guard and result.messages:
            output_safe, _ = self._guard.check_output(result.messages[-1])
            if not output_safe:
                from langchain_core.messages import AIMessage

                return ReasoningResult(
                    messages=[AIMessage(content="Output blocked by safety filter.")],
                    metadata={"blocked": "output"},
                )

        return result

    def get_llm(self) -> BaseChatModel:
        """Get wrapped brain's LLM."""
        if self._wrapped:
            return self._wrapped.get_llm()
        raise RuntimeError("No wrapped brain")
