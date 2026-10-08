from error_contract.agent import (
    AgentClientError,
    AgentPermissionError,
    InvalidQuestions,
    InvalidQuestionsError,
    MCPAuthError,
)
from error_contract.domain import (
    CompositionValidationError,
    DNSResolutionError,
    DuplicateComponentError,
    FlowNotPublishedError,
    FlowValidationError,
    MissingMigrationError,
    SSRFBlockedException,
    SSRFException,
)


def test_agent_error_constructors_preserve_public_fields_and_messages() -> None:
    permission = AgentPermissionError("update", "agent-1")
    assert permission.action == "update"
    assert permission.agent_id == "agent-1"
    assert str(permission) == "Permission denied: update on agent 'agent-1'"

    assert isinstance(InvalidQuestions("bad questions"), Exception)
    assert isinstance(AgentClientError("client failed"), Exception)
    assert isinstance(MCPAuthError("oauth failed"), Exception)


def test_legacy_agent_error_names_are_exact_compatibility_aliases() -> None:
    assert InvalidQuestions is InvalidQuestionsError


def test_flow_error_constructors_preserve_fields_and_messages() -> None:
    duplicate = DuplicateComponentError("llm")
    assert duplicate.component_type == "llm"
    assert str(duplicate) == "Component type 'llm' is already registered"

    issues = [object()]
    validation = FlowValidationError(issues)
    assert validation.issues is issues
    assert str(validation) == "Flow failed validation with 1 error(s)"

    unpublished = FlowNotPublishedError(42)
    assert unpublished.persona_id == 42

    migration = MissingMigrationError("tool", 2)
    assert migration.component_type == "tool"
    assert migration.from_version == 2


def test_special_base_class_relationships_are_preserved() -> None:
    assert isinstance(CompositionValidationError("invalid"), ValueError)
    assert isinstance(SSRFBlockedException("blocked"), SSRFException)
    assert isinstance(DNSResolutionError("dns"), SSRFException)
