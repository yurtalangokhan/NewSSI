"""Agent registry - Dynamic agent registration and discovery."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentRegistration:
    """Registration info for an agent."""

    name: str
    agent_class: type
    agent_type: str
    description: str
    config_schema: dict[str, Any] = field(default_factory=dict)
    default_config: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    factory: Callable | None = None


class AgentRegistry:
    """
    Central registry for agent definitions.

    Supports:
    - Decorator-based registration
    - Dynamic agent discovery
    - Config-based agent creation
    - Backward compatibility with existing agents
    """

    _registry: dict[str, AgentRegistration] = {}
    _initialized: bool = False

    @classmethod
    def register(
        cls,
        name: str,
        agent_class: type,
        agent_type: str,
        description: str = "",
        config_schema: dict[str, Any] | None = None,
        default_config: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        factory: Callable | None = None,
    ) -> None:
        """
        Register an agent.

        Args:
            name: Unique agent identifier
            agent_class: Agent class (not instance)
            agent_type: Type of agent (basic, manager, etc.)
            description: Human-readable description
            config_schema: JSON schema for config validation
            default_config: Default configuration values
            tags: Optional tags for categorization
            factory: Optional factory function to create instances
        """
        if name in cls._registry:
            # Allow re-registration for overrides
            pass

        cls._registry[name] = AgentRegistration(
            name=name,
            agent_class=agent_class,
            agent_type=agent_type,
            description=description,
            config_schema=config_schema or {},
            default_config=default_config or {},
            tags=tags or [],
            factory=factory,
        )

    @classmethod
    def get(cls, name: str) -> AgentRegistration | None:
        """Get agent registration by name."""
        return cls._registry.get(name)

    @classmethod
    def get_agent_class(cls, name: str) -> type | None:
        """Get agent class by name."""
        reg = cls._registry.get(name)
        return reg.agent_class if reg else None

    @classmethod
    def list_agents(cls, agent_type: str | None = None) -> list[str]:
        """
        List registered agent names.

        Args:
            agent_type: Optional filter by type

        Returns:
            List of agent names
        """
        if agent_type:
            return [name for name, reg in cls._registry.items() if reg.agent_type == agent_type]
        return list(cls._registry.keys())

    @classmethod
    def create_instance(
        cls,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> Any:
        """
        Create an agent instance from registration.

        Args:
            name: Agent name
            config: Optional configuration

        Returns:
            Agent instance
        """
        reg = cls._registry.get(name)
        if not reg:
            raise KeyError(f"Agent '{name}' not found in registry")

        if reg.factory:
            return reg.factory(config or {})

        # Create instance with config
        agent_class = reg.agent_class
        merged_config = {**reg.default_config, **(config or {})}
        return agent_class(config=merged_config)

    @classmethod
    def get_info(cls, name: str) -> dict[str, Any] | None:
        """Get agent info for API/metadata."""
        reg = cls._registry.get(name)
        if not reg:
            return None

        return {
            "name": reg.name,
            "type": reg.agent_type,
            "description": reg.description,
            "config_schema": reg.config_schema,
            "default_config": reg.default_config,
            "tags": reg.tags,
        }

    @classmethod
    def all_info(cls) -> list[dict[str, Any]]:
        """Get info for all registered agents."""
        return [
            {
                "name": reg.name,
                "type": reg.agent_type,
                "description": reg.description,
                "tags": reg.tags,
            }
            for reg in cls._registry.values()
        ]

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations (mainly for testing)."""
        cls._registry.clear()
        cls._initialized = False

    @classmethod
    def initialize_defaults(cls) -> None:
        """Initialize default agents from config files."""
        if cls._initialized:
            return

        # Load from config files
        from agents.configs.loader import load_agent_configs

        configs = load_agent_configs()

        for config in configs:
            name = config.get("name")
            if name and name not in cls._registry:
                # Will be loaded via factory when needed
                cls._initialized = True


def agent(
    name: str,
    agent_type: str = "basic",
    description: str = "",
    config_schema: dict[str, Any] | None = None,
    default_config: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> Callable[[type], type]:
    """
    Decorator to register an agent class.

    Usage:
        @agent(
            name="chatbot",
            agent_type="basic",
            description="Simple chatbot agent",
            tags=["production"]
        )
        class ChatbotAgent(BaseAgent):
            ...

    Args:
        name: Unique agent identifier
        agent_type: Type of agent (basic, manager, etc.)
        description: Human-readable description
        config_schema: JSON schema for configuration
        default_config: Default configuration values
        tags: Optional tags

    Returns:
        Decorator function
    """

    def decorator(cls: type) -> type:
        AgentRegistry.register(
            name=name,
            agent_class=cls,
            agent_type=agent_type,
            description=description,
            config_schema=config_schema,
            default_config=default_config,
            tags=tags,
        )
        return cls

    return decorator


def agent_factory(
    name: str,
    agent_type: str = "basic",
    description: str = "",
    config_schema: dict[str, Any] | None = None,
    default_config: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> Callable[[Callable], Callable]:
    """
    Decorator for factory-based agent registration.

    Use when agent creation requires custom logic.

    Usage:
        @agent_factory(name="custom", description="Custom agent")
        def create_custom_agent(config):
            return CustomAgent(**config)
    """

    def decorator(factory: Callable) -> Callable:
        AgentRegistry.register(
            name=name,
            agent_class=factory,  # Store factory as class
            agent_type=agent_type,
            description=description,
            config_schema=config_schema,
            default_config=default_config,
            tags=tags,
            factory=factory,
        )
        return factory

    return decorator
