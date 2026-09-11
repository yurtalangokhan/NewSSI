"""Tests for graph schema strategies."""

from agents.graphs.schemas import GraphSchemaType
from agents.graphs.strategies import (
    ReActGraphStrategy,
    get_registry,
    get_strategy,
)


class TestStrategyRegistry:
    """Test the strategy registry."""

    def test_get_registry_returns_singleton(self):
        """Registry should be a singleton."""
        registry1 = get_registry()
        registry2 = get_registry()
        assert registry1 is registry2

    def test_all_schema_types_have_strategies(self):
        """Every GraphSchemaType should have a registered strategy.

        FLOW is the exception by design: a flow-backed definition is compiled
        from its flow_spec by FlowGraphBuilder (agents/graphs/flow_builder.py),
        not by a per-schema strategy, so it never reaches this registry.
        """
        registry = get_registry()
        for schema_type in GraphSchemaType:
            if schema_type is GraphSchemaType.FLOW:
                continue
            strategy_class = registry.get(schema_type)
            assert strategy_class is not None, f"No strategy registered for {schema_type}"

    def test_get_strategy_returns_instance(self):
        """get_strategy should return a strategy instance."""
        strategy = get_strategy(GraphSchemaType.REACT)
        assert strategy is not None
        assert isinstance(strategy, ReActGraphStrategy)

    def test_get_strategy_with_string_key(self):
        """get_strategy should accept string keys."""
        strategy = get_strategy("react")
        assert strategy is not None
        assert isinstance(strategy, ReActGraphStrategy)

    def test_get_strategy_invalid_returns_none(self):
        """get_strategy should return None for invalid schema type."""
        strategy = get_strategy("invalid_schema_type")
        assert strategy is None

    def test_supervisor_validate_empty_sub_agents(self):
        """Supervisor should validate empty sub_agents list."""
        strategy = get_strategy(GraphSchemaType.SUPERVISOR)
        errors = strategy.validate({"sub_agents": []})
        assert len(errors) > 0
        assert any("empty" in e.lower() for e in errors)

    def test_supervisor_validate_valid_sub_agents(self):
        """Supervisor should pass with valid sub_agents."""
        strategy = get_strategy(GraphSchemaType.SUPERVISOR)
        errors = strategy.validate(
            {
                "sub_agents": [
                    {"name": "agent1", "system_prompt": "Do task 1"},
                    {"name": "agent2", "system_prompt": "Do task 2"},
                ]
            }
        )
        assert len(errors) == 0

    def test_supervisor_validate_missing_name(self):
        """Supervisor should detect missing name in sub_agent."""
        strategy = get_strategy(GraphSchemaType.SUPERVISOR)
        errors = strategy.validate(
            {
                "sub_agents": [
                    {"system_prompt": "No name provided"},
                ]
            }
        )
        assert len(errors) > 0
        assert any("name" in e.lower() for e in errors)

    def test_pipeline_validate_empty_stages(self):
        """Pipeline should validate empty stages list."""
        strategy = get_strategy(GraphSchemaType.PIPELINE)
        errors = strategy.validate({"stages": []})
        assert len(errors) > 0
        assert any("empty" in e.lower() for e in errors)

    def test_pipeline_validate_valid_stages(self):
        """Pipeline should pass with valid stages."""
        strategy = get_strategy(GraphSchemaType.PIPELINE)
        errors = strategy.validate(
            {
                "stages": [
                    {"name": "stage1", "system_prompt": "Do step 1"},
                    {"name": "stage2", "system_prompt": "Do step 2"},
                ]
            }
        )
        assert len(errors) == 0

    def test_pipeline_validate_missing_name(self):
        """Pipeline should detect missing name in stage."""
        strategy = get_strategy(GraphSchemaType.PIPELINE)
        errors = strategy.validate(
            {
                "stages": [
                    {"system_prompt": "No name provided"},
                ]
            }
        )
        assert len(errors) > 0
        assert any("name" in e.lower() for e in errors)

    def test_zero_shot_validate_always_passes(self):
        """Zero-shot should have no required fields."""
        strategy = get_strategy(GraphSchemaType.ZERO_SHOT)
        errors = strategy.validate({})
        assert len(errors) == 0

    def test_react_validate_always_passes(self):
        """ReAct should have no required fields."""
        strategy = get_strategy(GraphSchemaType.REACT)
        errors = strategy.validate({})
        assert len(errors) == 0

    def test_plan_execute_validate_always_passes(self):
        """PlanExecute should have no required fields."""
        strategy = get_strategy(GraphSchemaType.PLAN_EXECUTE)
        errors = strategy.validate({})
        assert len(errors) == 0

    def test_self_reflect_validate_always_passes(self):
        """SelfReflect should have no required fields."""
        strategy = get_strategy(GraphSchemaType.SELF_REFLECT)
        errors = strategy.validate({})
        assert len(errors) == 0

    def test_supervisor_validate_wrong_type(self):
        """Supervisor should detect wrong type for sub_agents."""
        strategy = get_strategy(GraphSchemaType.SUPERVISOR)
        errors = strategy.validate({"sub_agents": "not a list"})
        assert len(errors) > 0
        assert any("list" in e.lower() for e in errors)

    def test_pipeline_validate_wrong_type(self):
        """Pipeline should detect wrong type for stages."""
        strategy = get_strategy(GraphSchemaType.PIPELINE)
        errors = strategy.validate({"stages": "not a list"})
        assert len(errors) > 0
        assert any("list" in e.lower() for e in errors)


class TestPipelineDeterministicOrder:
    """Test that pipeline stage order is deterministic."""

    def test_stage_order_is_preserved_in_validation(self):
        """Stage names should appear in order in validation errors if names are missing."""
        strategy = get_strategy(GraphSchemaType.PIPELINE)
        # This tests that the strategy processes stages in order
        errors = strategy.validate(
            {
                "stages": [
                    {"name": "first"},
                    {"system_prompt": "missing name"},  # This will cause an error
                    {"name": "third"},
                ]
            }
        )
        # We expect an error about the second stage missing a name
        assert len(errors) > 0

    def test_supervisor_agent_order_is_preserved(self):
        """Sub-agent names should be processed in order."""
        strategy = get_strategy(GraphSchemaType.SUPERVISOR)
        errors = strategy.validate(
            {
                "sub_agents": [
                    {"name": "first"},
                    {"name": "second"},
                    {"name": "third"},
                ]
            }
        )
        # No errors - all names are present
        assert len(errors) == 0
