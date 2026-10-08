from error_contract import ApplicationError, DependencyUnavailableError
from error_contract.identity import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    InternalServerError,
    NotFoundError,
    UnauthorizedError,
    UserServiceError,
)
from error_contract.lifecycle import DependencyStartupError


def test_identity_errors_are_shared_aliases_with_stable_catch_semantics():
    assert UserServiceError is ApplicationError
    assert issubclass(NotFoundError, UserServiceError)
    assert issubclass(BadRequestError, UserServiceError)
    assert issubclass(UnauthorizedError, UserServiceError)
    assert issubclass(ForbiddenError, UserServiceError)
    assert issubclass(ConflictError, UserServiceError)
    assert issubclass(InternalServerError, UserServiceError)


def test_dependency_startup_error_keeps_safe_operator_context():
    error = DependencyStartupError(
        dependency="postgres",
        operation_name="connect",
        remediation="Check that the dependency is reachable.",
    )

    assert isinstance(error, DependencyUnavailableError)
    assert isinstance(error, RuntimeError)
    assert str(error) == (
        "postgres is unavailable during startup connect. Check that the dependency is reachable."
    )
    assert error.dependency == "postgres"
    assert error.operation_name == "connect"
    assert error.remediation == "Check that the dependency is reachable."


def test_open_circuit_is_a_localized_dependency_error():
    from error_contract.localization import render_error_message
    from error_contract.resilience import CircuitBreakerOpenError

    error = CircuitBreakerOpenError("private dependency", 12.5)
    assert isinstance(error, DependencyUnavailableError)
    assert error.status_code == 503
    assert error.name == "private dependency"
    assert error.reset_in_seconds == 12.5
    assert "private dependency" not in render_error_message(error, "tr")
