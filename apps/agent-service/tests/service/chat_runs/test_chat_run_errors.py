import pytest
from error_contract import ApplicationError

from service.chat_runs.domain import (
    ChatRunError,
    ChatRunUnavailableError,
    RunAlreadyActiveError,
    RunNotFoundError,
    SupervisorShuttingDownError,
)


def test_already_active_is_a_409_that_names_the_holder():
    error = RunAlreadyActiveError("run-1")
    assert isinstance(error, ApplicationError) and isinstance(error, ChatRunError)
    assert error.status_code == 409
    assert error.code == "chat_run.active"
    assert error.message_key == "chat.run_already_active"
    assert error.details == {"run_id": "run-1"}
    assert error.run_id == "run-1"


@pytest.mark.parametrize("error_type", [ChatRunUnavailableError, SupervisorShuttingDownError])
def test_unavailable_is_a_503(error_type):
    error = error_type("redis down")
    assert isinstance(error, ApplicationError)
    assert error.status_code == 503
    assert error.code == "chat_run.unavailable"
    assert error.message_key == "chat.run_unavailable"


def test_not_found_is_a_404_that_does_not_leak_the_owner():
    error = RunNotFoundError("run-2")
    assert error.status_code == 404
    assert error.code == "chat_run.not_found"
    assert error.details == {}
    assert error.run_id == "run-2"
