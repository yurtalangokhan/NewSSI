"""Memory policy for post-run extraction and persistence.

The MemoryPolicy wraps the existing memory/long_term.py hooks as a
RuntimePolicy-compliant component so it can be composed with other
policies inside ComposedAgent without inheriting from LazyLoadingAgent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableConfig

from core.observability.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class MemoryPolicyConfig:
    """Configuration for the memory policy."""

    enabled: bool = False
    extract_memory: bool = True
    # Model settings can be overridden at runtime via config.
    model_key: str | None = None


class MemoryPolicy:
    """Post-run memory extraction and persistence policy.

    This policy wraps the existing long_term memory hooks:
    - extract_and_save_memories: extracts new facts from the conversation
      and persists them to the LangGraph store.
    - build_event_emitters: builds on-save event emitters for streaming.

    This policy only handles post-run extraction and persistence. Pre-run
    recall is not part of it, and no component performs it today: the
    Perceptron port that was meant to is gone, having never been implemented.
    """

    key: str = "memory"

    def __init__(self, config: MemoryPolicyConfig | None = None) -> None:
        self._config = config or MemoryPolicyConfig()

    @property
    def is_enabled(self) -> bool:
        return self._config.enabled

    def _get_langgraph_store(self):
        """Resolve the process-wide LangGraph store, shared with the agent runtimes."""
        from memory.recall import resolve_langgraph_store

        return resolve_langgraph_store()

    def _resolve_model(self, configurable: dict[str, Any], default_model_key: str) -> BaseChatModel | None:
        """Resolve the chat model from config or default."""
        try:
            from infrastructure.llm.llm import get_model_from_config

            model_key = self._config.model_key or configurable.get("model") or default_model_key
            return get_model_from_config(configurable, model_key)
        except Exception as exc:
            logger.warning("[MemoryPolicy] Could not resolve model: %s", exc)
            return None

    async def after_run(
        self,
        output: Any,
        original_messages: list[Any],
        memories: dict[str, Any],
        user_id: str | None,
        config: RunnableConfig | None = None,
    ) -> None:
        """Extract and save memories from the agent output.

        This is the post-run memory hook equivalent to
        LazyLoadingAgent._save_memory_from_output.
        """
        if not self._config.enabled or not user_id:
            return

        configurable = (config or {}).get("configurable") or {}
        store = self._get_langgraph_store()
        if not store:
            return

        try:
            from memory.long_term import extract_memories_for_turn

            model = self._resolve_model(configurable, "default")
            if model is None:
                return

            # Get the response messages from output
            output_messages = []
            if isinstance(output, dict) and "messages" in output:
                output_messages = output["messages"]

            all_messages = list(original_messages) + list(output_messages)
            # This policy's own default (self._config.extract_memory) only
            # applies when configurable doesn't say otherwise.
            configurable = {
                **configurable,
                "extract_memory": configurable.get("extract_memory", self._config.extract_memory),
            }
            await extract_memories_for_turn(user_id, configurable, all_messages, model, memories)
        except Exception as e:
            logger.warning("[MemoryPolicy] Memory save failed: %s", e)

    async def close(self) -> None:
        """Memory policy has no persistent resources to close."""
