"""Graph schema strategy registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agents.graphs.schemas import GraphSchemaType
from core.logger import get_logger

if TYPE_CHECKING:
    from agents.graphs.strategies.base import GraphSchemaStrategy

logger = get_logger(__name__)


class GraphSchemaStrategyRegistry:
    """
    Registry for graph schema strategies.

    Adding a new graph schema only requires registering a new strategy,
    not modifying a central builder.
    """

    def __init__(self) -> None:
        self._strategies: dict[GraphSchemaType, type[GraphSchemaStrategy]] = {}

    def register(self, strategy_class: type[GraphSchemaStrategy]) -> None:
        """
        Register a strategy class.

        Args:
            strategy_class: A GraphSchemaStrategy subclass
        """
        from agents.graphs.strategies.base import GraphSchemaStrategy

        if not issubclass(strategy_class, GraphSchemaStrategy):
            raise TypeError(f"{strategy_class.__name__} must be a GraphSchemaStrategy subclass")

        # Get schema_type from the class (subclasses must define it)
        schema_type = getattr(strategy_class, "schema_type", None)
        if schema_type is None:
            raise TypeError(f"{strategy_class.__name__} must define schema_type attribute")

        self._strategies[schema_type] = strategy_class
        logger.debug(
            "Registered strategy %s for schema type %s",
            strategy_class.__name__,
            schema_type,
        )

    def get(self, schema_type: GraphSchemaType | str) -> type[GraphSchemaStrategy] | None:
        """
        Get the strategy class for a schema type.

        Args:
            schema_type: The graph schema type

        Returns:
            The strategy class, or None if not registered
        """
        if isinstance(schema_type, str):
            try:
                schema_type = GraphSchemaType(schema_type)
            except ValueError:
                return None
        return self._strategies.get(schema_type)

    def create(
        self,
        schema_type: GraphSchemaType | str,
        **kwargs: Any,
    ) -> GraphSchemaStrategy | None:
        """
        Create a strategy instance for the given schema type.

        Args:
            schema_type: The graph schema type
            **kwargs: Arguments to pass to the strategy constructor

        Returns:
            A strategy instance, or None if not registered
        """
        strategy_class = self.get(schema_type)
        if strategy_class is None:
            return None
        return strategy_class(**kwargs)

    def supported_types(self) -> list[GraphSchemaType]:
        """Return list of all registered schema types."""
        return list(self._strategies.keys())


# Global registry instance
_registry: GraphSchemaStrategyRegistry | None = None


def get_registry() -> GraphSchemaStrategyRegistry:
    """Get the global strategy registry, initializing if needed."""
    global _registry
    if _registry is None:
        _registry = GraphSchemaStrategyRegistry()
        _register_default_strategies()
    return _registry


def _register_default_strategies() -> None:
    """Register the default built-in strategies."""
    from agents.graphs.strategies.pipeline import PipelineGraphStrategy
    from agents.graphs.strategies.plan_execute import PlanExecuteGraphStrategy
    from agents.graphs.strategies.react import ReActGraphStrategy
    from agents.graphs.strategies.self_reflect import SelfReflectGraphStrategy
    from agents.graphs.strategies.supervisor import SupervisorGraphStrategy
    from agents.graphs.strategies.zero_shot import ZeroShotGraphStrategy

    registry = _registry
    if registry is None:
        return

    registry.register(ZeroShotGraphStrategy)
    registry.register(ReActGraphStrategy)
    registry.register(SupervisorGraphStrategy)
    registry.register(PipelineGraphStrategy)
    registry.register(PlanExecuteGraphStrategy)
    registry.register(SelfReflectGraphStrategy)


def get_strategy(
    schema_type: GraphSchemaType | str,
    **kwargs: Any,
) -> GraphSchemaStrategy | None:
    """
    Get a strategy instance for the given schema type.

    Args:
        schema_type: The graph schema type
        **kwargs: Arguments to pass to the strategy constructor

    Returns:
        A strategy instance, or None if not registered
    """
    return get_registry().create(schema_type, **kwargs)
