"""Agent Factory - Creates agents from configuration."""

from typing import Any

from core.logger import get_logger

logger = get_logger(__name__)


class AgentFactory:
    """
    Factory for creating agents from configuration.

    Uses registry class reference system to instantiate agents
    defined in JSON/YAML config files.
    """

    _instance: "AgentFactory | None" = None
    _registered_configs: dict[str, dict[str, Any]] = {}

    def __init__(self):
        if AgentFactory._instance is not None:
            raise RuntimeError("Use get_instance() to get singleton")

    @classmethod
    def get_instance(cls) -> "AgentFactory":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._load_configs()
        return cls._instance

    def _load_configs(self) -> None:
        """Load agent configs from config files."""
        try:
            from agents.configs.loader import load_agent_configs

            configs = load_agent_configs()
            for config in configs:
                name = config.get("name")
                if name:
                    self._registered_configs[name] = config
                    logger.info("Loaded config for agent: %s", name)

            logger.info("Loaded %d agent configs", len(self._registered_configs))
        except Exception as e:
            logger.warning("Could not load agent configs: %s", e)

    def get_registered_configs(self) -> dict[str, dict[str, Any]]:
        """Get all registered configs."""
        return self._registered_configs.copy()

    def get_config(self, name: str) -> dict[str, Any] | None:
        """Get a specific config by name."""
        return self._registered_configs.get(name)

    def create_from_config(self, config: dict[str, Any]) -> Any:
        """
        Create an agent instance from a config dict.

        Args:
            config: Agent configuration dictionary

        Returns:
            Agent instance
        """
        agent_class_path = config.get("class")
        if not agent_class_path:
            logger.warning("Config missing 'class' field, using default chatbot")
            from agents.impl.chatbot import ChatbotAgent

            return ChatbotAgent(config=config.get("defaults", {}))

        try:
            agent_class = self._load_class(agent_class_path)
            defaults = config.get("defaults", {})
            return agent_class(config=defaults)
        except Exception as e:
            logger.error("Failed to create agent from config %s: %s", config.get("name"), e)
            from agents.impl.chatbot import ChatbotAgent

            return ChatbotAgent()

    def _load_class(self, class_path: str) -> type:
        """
        Load a class from a dotted string path.

        Args:
            class_path: Dotted path like 'agents.impl.chatbot.ChatbotAgent'

        Returns:
            The loaded class
        """
        parts = class_path.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid class path: {class_path}")

        module_path, class_name = parts

        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    def create_agent(self, name: str, config: dict[str, Any] | None = None) -> Any:
        """
        Create an agent by name.

        Args:
            name: Agent name (must be registered in configs)
            config: Optional runtime configuration

        Returns:
            Agent instance
        """
        agent_config = self._registered_configs.get(name)
        if not agent_config:
            raise KeyError(f"Agent '{name}' not found in registry")

        agent = self.create_from_config(agent_config)

        if config:
            agent.update_config(config)

        return agent

    def list_registered_agents(self) -> list[str]:
        """List all registered agent names."""
        return list(self._registered_configs.keys())

    def register_config(self, config: dict[str, Any]) -> None:
        """
        Register a new agent config at runtime.

        Args:
            config: Agent configuration dictionary
        """
        name = config.get("name")
        if name:
            self._registered_configs[name] = config
            logger.info("Registered config for agent: %s", name)


# Singleton instance accessor
agent_factory = AgentFactory.get_instance()
