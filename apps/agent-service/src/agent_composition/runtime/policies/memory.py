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

from core.logger import get_logger

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

    Memory recall (pre-run enrichment) is handled by a Perceptron, not
    this policy. This policy only handles post-run extraction and persistence.
    """

    key: str = "memory"

    def __init__(self, config: MemoryPolicyConfig | None = None) -> None:
        self._config = config or MemoryPolicyConfig()

    @property
    def is_enabled(self) -> bool:
        return self._config.enabled

    def _get_langgraph_store(self):
        """Get the global LangGraph store for long-term memory.

        This is the same lookup used by LazyLoadingAgent._get_langgraph_store.
        """
        try:
            from service.LangGraphStoreService import get_langgraph_store

            return get_langgraph_store()
        except Exception as exc:
            logger.warning("[MemoryPolicy] Could not resolve LangGraph store: %s", exc)
            return None

    def _resolve_model(
        self, configurable: dict[str, Any], default_model_key: str
    ) -> BaseChatModel | None:
        """Resolve the chat model from config or default."""
        try:
            from core.llm import get_model_from_config

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
            from memory.long_term import build_event_emitters, extract_and_save_memories

            model = self._resolve_model(configurable, "default")
            if model is None:
                return

            # Get the response messages from output
            output_messages = []
            if isinstance(output, dict) and "messages" in output:
                output_messages = output["messages"]

            all_messages = list(original_messages) + list(output_messages)
            extract_mem = configurable.get("extract_memory", self._config.extract_memory)
            _, on_save = build_event_emitters(configurable)
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
            logger.warning("[MemoryPolicy] Memory save failed: %s", e)

    async def close(self) -> None:
        """Memory policy has no persistent resources to close."""
        pass
