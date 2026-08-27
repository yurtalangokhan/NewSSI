from __future__ import annotations

import pytest

import agent_composition
from agent_composition import (
    AgentDefinition,
    BrainConfig,
    ComponentKind,
    GraphSchemaConfig,
    PerceptronConfig,
    ValidateAgentDefinition,
)
from agent_composition.domain.component_catalog import get_component, list_available
from agent_composition.domain.errors import (
    IncompatibleComponentError,
    MissingRequiredNestedError,
    MissingRequiredSettingError,
    NestedCycleError,
    SecretInConfigError,
    UnavailableComponentError,
    UnknownComponentKeyError,
)


def _valid_definition() -> AgentDefinition:
    return AgentDefinition(
        identity="def-1",
        brain=BrainConfig(key="standard_model"),
        perceptrons=(PerceptronConfig(key="long_term_memory"),),
        graph=GraphSchemaConfig(key="zero_shot"),
    )


def test_catalog_excludes_unavailable_multi_model() -> None:
    brains = {entry["key"] for entry in list_available(ComponentKind.BRAIN)}
    assert "standard_model" in brains
    assert "guard" not in brains
    assert "multi_model" not in brains
    descriptor = get_component("multi_model")
    assert descriptor is not None
    assert descriptor.available is False
    assert descriptor.implemented is False
    guard = get_component("guard")
    assert guard is not None
    assert guard.available is False
    assert guard.implemented is False


def test_domain_ports_include_runtime_policy_and_definition_repository() -> None:
    assert hasattr(agent_composition, "RuntimePolicy")
    assert hasattr(agent_composition, "AgentDefinitionRepository")


def test_catalog_exposes_typed_configuration_metadata() -> None:
    descriptor = get_component("standard_model")
    assert descriptor is not None
    assert descriptor.api_metadata()["settings_schema"]["temperature"] == "number"


def test_validator_reports_invalid_typed_configuration_value() -> None:
    definition = AgentDefinition(
        identity="def-typed",
        brain=BrainConfig(key="standard_model", settings={"temperature": "hot"}),
    )
    issues = ValidateAgentDefinition().validate(definition)
    assert any(issue.code == MissingRequiredSettingError.code for issue in issues)


def test_unknown_key_is_none() -> None:
    assert get_component("does_not_exist") is None


def test_valid_definition_has_no_issues() -> None:
    issues = ValidateAgentDefinition().validate(_valid_definition())
    assert issues == ()


def test_unknown_brain_key_reports_issue() -> None:
    definition = AgentDefinition(
        identity="def-1",
        brain=BrainConfig(key="ghost_brain"),
        perceptrons=(PerceptronConfig(key="long_term_memory"),),
        graph=GraphSchemaConfig(key="zero_shot"),
    )
    issues = ValidateAgentDefinition().validate(definition)
    assert any(issue.code == UnknownComponentKeyError.code for issue in issues)


def test_unavailable_key_reports_issue() -> None:
    definition = AgentDefinition(identity="def-x", brain=BrainConfig(key="multi_model"))
    issues = ValidateAgentDefinition().validate(definition)
    assert any(issue.code == UnavailableComponentError.code for issue in issues)


def test_public_validator_reports_incompatible_component_combination() -> None:
    definition = AgentDefinition(
        identity="def-incompatible",
        brain=BrainConfig(key="standard_model"),
        perceptrons=(
            PerceptronConfig(key="current_chat_document"),
            PerceptronConfig(key="project_context"),
        ),
    )
    issues = ValidateAgentDefinition().validate(definition)
    assert any(issue.code == IncompatibleComponentError.code for issue in issues)


def test_pipeline_requires_nested_definitions() -> None:
    definition = AgentDefinition(identity="def-p", graph=GraphSchemaConfig(key="pipeline"))
    issues = ValidateAgentDefinition().validate(definition)
    assert any(issue.code == MissingRequiredNestedError.code for issue in issues)


def test_nested_cycle_detected() -> None:
    child_loop = AgentDefinition(identity="cycle-a", nested=(AgentDefinition(identity="cycle-a"),))
    issues = ValidateAgentDefinition().validate(child_loop)
    assert any(issue.code == NestedCycleError.code for issue in issues)


def test_max_depth_exceeded() -> None:
    nested: AgentDefinition = AgentDefinition(identity="leaf")
    for depth in range(7):
        nested = AgentDefinition(identity=f"d{depth}", nested=(nested,))
    issues = ValidateAgentDefinition().validate(nested)
    assert any(issue.code == "max_depth_exceeded" for issue in issues)


def test_secret_in_brain_settings_detected() -> None:
    definition = AgentDefinition(
        identity="def-s",
        brain=BrainConfig(key="standard_model", settings={"api_key": "hidden"}),
    )
    issues = ValidateAgentDefinition().validate(definition)
    assert any(issue.code == SecretInConfigError.code for issue in issues)


def test_validate_or_raise_raises_for_unknown_key() -> None:
    definition = AgentDefinition(identity="def-r", brain=BrainConfig(key="ghost_brain"))
    with pytest.raises(UnknownComponentKeyError):
        ValidateAgentDefinition().validate_or_raise(definition)
