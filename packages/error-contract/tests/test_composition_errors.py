from error_contract import ApplicationError
from error_contract.composition import (
    CompositionError,
    ForbiddenTrustedFieldError,
    ToolInvocationError,
)


def test_composition_error_preserves_legacy_contract() -> None:
    error = ToolInvocationError("Tool failed", {"tool": "search"})

    assert isinstance(error, ApplicationError)
    assert isinstance(error, CompositionError)
    assert str(error) == "Tool failed"
    assert error.message == "Tool failed"
    assert error.details == {"tool": "search"}
    assert error.code == "tool_invocation_error"
    assert error.status_code == 503
    assert error.message_key == "errors.dependency.unavailable"


def test_forbidden_trusted_field_accepts_keyword_details() -> None:
    error = ForbiddenTrustedFieldError(
        "Trusted field is forbidden",
        details={"key": "user_id"},
    )

    assert error.code == "forbidden_trusted_field"
    assert error.status_code == 400
    assert error.details == {"key": "user_id"}
