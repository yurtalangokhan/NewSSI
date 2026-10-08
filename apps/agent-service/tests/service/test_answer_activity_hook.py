"""A completed answer advances the thread's message activity for the unread dot."""

from datetime import UTC, datetime

import pytest

from service.chat.answer_activity_hook import AnswerActivityHook
from service.chat_runs.domain import ChatRun, ChatRunSpec, RunStatus


def _run(status: RunStatus) -> ChatRun:
    run = ChatRun.start(
        run_id="r1",
        spec=ChatRunSpec(thread_id="t1", owner_user_id="u1"),
        instance_id="i1",
        now=1.0,
    )
    if status is RunStatus.RUNNING:
        return run
    return run.finish(status, error_code=None, now=2.0)


class _ThreadService:
    def __init__(self) -> None:
        self.marked: list[str] = []
        self.marked_at: list[datetime | None] = []
        self.raise_on_mark = False

    async def mark_answer_activity(self, thread_id: str, *, at: datetime | None = None):
        if self.raise_on_mark:
            raise RuntimeError("thread store unavailable")
        self.marked.append(thread_id)
        self.marked_at.append(at)
        return {"thread_id": thread_id}


@pytest.mark.asyncio
async def test_completed_run_marks_answer_activity():
    service = _ThreadService()
    hook = AnswerActivityHook(lambda: service)

    await hook.on_run_completed(_run(RunStatus.COMPLETED))

    assert service.marked == ["t1"]


@pytest.mark.asyncio
async def test_a_run_without_an_answer_is_not_recorded():
    service = _ThreadService()
    hook = AnswerActivityHook(lambda: service)

    await hook.on_run_completed(_run(RunStatus.CANCELLED))
    await hook.on_run_completed(_run(RunStatus.INTERRUPTED))

    assert service.marked == []


@pytest.mark.asyncio
async def test_a_storage_failure_never_escapes_the_hook():
    service = _ThreadService()
    service.raise_on_mark = True
    hook = AnswerActivityHook(lambda: service)

    # A failed bookkeeping write must not fail the run's completion.
    await hook.on_run_completed(_run(RunStatus.COMPLETED))


@pytest.mark.asyncio
async def test_the_answer_is_stamped_with_the_moment_the_run_finished():
    # The client can only learn the answer is done after the run is marked
    # finished, so stamping that instant (not "now") keeps a later /seen newer
    # than the answer whatever order the hook and the request land in.
    service = _ThreadService()
    hook = AnswerActivityHook(lambda: service)

    await hook.on_run_completed(_run(RunStatus.COMPLETED))

    assert service.marked_at == [datetime.fromtimestamp(2.0, UTC)]
