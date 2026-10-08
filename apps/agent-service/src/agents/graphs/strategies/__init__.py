"""Graph schema strategies package."""

from agents.graphs.strategies.base import GraphSchemaStrategy
from agents.graphs.strategies.pipeline import PipelineGraphStrategy
from agents.graphs.strategies.plan_execute import PlanExecuteGraphStrategy
from agents.graphs.strategies.react import ReActGraphStrategy
from agents.graphs.strategies.registry import (
    GraphSchemaStrategyRegistry,
    get_registry,
    get_strategy,
)
from agents.graphs.strategies.self_reflect import SelfReflectGraphStrategy
from agents.graphs.strategies.supervisor import SupervisorGraphStrategy
from agents.graphs.strategies.zero_shot import ZeroShotGraphStrategy

__all__ = [
    "GraphSchemaStrategy",
    "GraphSchemaStrategyRegistry",
    "PipelineGraphStrategy",
    "PlanExecuteGraphStrategy",
    "ReActGraphStrategy",
    "SelfReflectGraphStrategy",
    "SupervisorGraphStrategy",
    "ZeroShotGraphStrategy",
    "get_registry",
    "get_strategy",
]


def _register_built_in_strategies() -> None:
    """Populate the registry once, from the one place that already imports every strategy.

    Registration lives here rather than in ``registry`` so the registry stays
    free of concrete strategies; importing any module in this package runs this
    first, so the registry is never observed empty.
    """
    registry = get_registry()
    if registry.supported_types():
        return
    for strategy in (
        ZeroShotGraphStrategy,
        ReActGraphStrategy,
        SupervisorGraphStrategy,
        PipelineGraphStrategy,
        PlanExecuteGraphStrategy,
        SelfReflectGraphStrategy,
    ):
        registry.register(strategy)


_register_built_in_strategies()
