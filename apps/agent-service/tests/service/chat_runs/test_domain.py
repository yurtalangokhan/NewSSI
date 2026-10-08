import pytest

from service.chat_runs.domain import (
    INPUT_PREVIEW_MAX_CHARS,
    ChatRun,
    ChatRunSpec,
    InvalidRunTransitionError,
    RunStatus,
)


def _run() -> ChatRun:
    return ChatRun.start(
        run_id="r1",
        spec=ChatRunSpec(thread_id="t1", owner_user_id="u1", input_preview="x" * 5000),
        instance_id="i1",
        now=100.0,
    )


def test_only_running_is_non_terminal():
    assert [s for s in RunStatus if not s.is_terminal] == [RunStatus.RUNNING]


def test_start_bounds_the_input_preview_and_starts_running():
    run = _run()
    assert run.status is RunStatus.RUNNING
    assert len(run.input_preview) == INPUT_PREVIEW_MAX_CHARS
    assert run.client_request_id is None


def test_finish_records_status_error_and_time():
    done = _run().finish(RunStatus.FAILED, error_code="provider_unavailable", now=105.0)
    assert (done.status, done.error_code, done.finished_at) == (
        RunStatus.FAILED,
        "provider_unavailable",
        105.0,
    )


def test_a_terminal_run_cannot_finish_again():
    done = _run().finish(RunStatus.COMPLETED, error_code=None, now=101.0)
    with pytest.raises(InvalidRunTransitionError):
        done.finish(RunStatus.CANCELLED, error_code=None, now=102.0)


def test_finish_rejects_a_non_terminal_target():
    with pytest.raises(InvalidRunTransitionError):
        _run().finish(RunStatus.RUNNING, error_code=None, now=101.0)
