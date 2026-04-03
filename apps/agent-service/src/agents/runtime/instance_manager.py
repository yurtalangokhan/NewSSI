"""Runtime agent instance manager.

Manages agent lifecycle - creation, loading, and caching.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentInstanceManager:
    """
    Singleton manager for agent instances.

    Provides:
    - Agent creation from configs
    - Instance caching
    - Lazy loading coordination
    """

    _instance: "AgentInstanceManager | None" = None
    _instances: dict[str, Any] = {}
    _initialized: bool = False

    def __new__(cls) -> "AgentInstanceManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not self._initialized:
            self._instances = {}
            self._initialized = True

    def get_instance(self, name: str) -> Any:
        """Get a cached agent instance."""
        return self._instances.get(name)

    def set_instance(self, name: str, instance: Any) -> None:
        """Cache an agent instance."""
        self._instances[name] = instance
        logger.debug(f"Cached agent instance: {name}")

    def remove_instance(self, name: str) -> bool:
        """Remove an agent instance from cache."""
        if name in self._instances:
            del self._instances[name]
            return True
        return False

    def clear_all(self) -> None:
        """Clear all cached instances."""
        self._instances.clear()
        logger.info("Cleared all agent instances")

    def list_instances(self) -> list[str]:
        """List cached instance names."""
        return list(self._instances.keys())

    def is_cached(self, name: str) -> bool:
        """Check if an agent is cached."""
        return name in self._instances


# Singleton accessor
_agent_manager: AgentInstanceManager | None = None


def get_agent_manager() -> AgentInstanceManager:
    """Get the singleton agent instance manager."""
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentInstanceManager()
    return _agent_manager


def create_agent_from_config(config: dict[str, Any]) -> Any:
    """
    Create an agent from configuration dictionary.

    Args:
        config: Agent configuration with 'name', 'type', 'class', etc.

    Returns:
        Agent instance
    """
    from agents.managers import get_supervisor, get_pipeline

    agent_type = config.get("type", "manager")
    name = config.get("name", "unnamed")

    if agent_type == "manager":
        if "pipeline" in name.lower():
            return get_pipeline(config)
        else:
            return get_supervisor(config)

    # Default fallback
    from agents.chatbot import chatbot

    return chatbot


__all__ = [
    "AgentInstanceManager",
    "get_agent_manager",
    "create_agent_from_config",
]
