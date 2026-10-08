from copy import deepcopy

from error_contract import DependencyUnavailableError, ForbiddenError, NotFoundError
import pytest

from service.chat.chat_management_service import ChatManagementService


class _Threads:
    def __init__(self, owner: str) -> None:
        self.thread = {"thread_id": "t1", "metadata": {"user_id": owner}}

    async def get_thread(self, thread_id):
        return deepcopy(self.thread) if thread_id == "t1" else None

    async def update_thread(self, *args, **kwargs):
        return None


class _ChatRuns:
    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self.request_ids: list[str | None] = []

    async def cancel_active(self, thread_id, *, client_request_id=None):
        self.cancelled.append(thread_id)
        self.request_ids.append(client_request_id)
        return True


@pytest.mark.asyncio
async def test_a_non_owner_cannot_stop_someone_elses_run():
    runs = _ChatRuns()
    service = ChatManagementService(thread_service=_Threads("owner"), user_id="intruder", chat_runs=runs)
    with pytest.raises(ForbiddenError):
        await service.stop_chat_session("t1")
    assert runs.cancelled == []


@pytest.mark.asyncio
async def test_the_owner_stops_the_run_across_instances():
    runs = _ChatRuns()
    service = ChatManagementService(thread_service=_Threads("owner"), user_id="owner", chat_runs=runs)
    assert (await service.stop_chat_session("t1"))["success"] is True
    assert runs.cancelled == ["t1"]


@pytest.mark.asyncio
async def test_stopping_an_unknown_session_reports_not_found():
    runs = _ChatRuns()
    service = ChatManagementService(thread_service=_Threads("owner"), user_id="owner", chat_runs=runs)
    with pytest.raises(NotFoundError):
        await service.stop_chat_session("missing")
    assert runs.cancelled == []


@pytest.mark.asyncio
async def test_the_supervisor_records_the_stop_before_the_generator_is_told_to_break():
    # If the cooperative flag fired first, the generator could finish before
    # the supervisor knew about the Stop and the run would end `completed`.
    from service.runtime.active_runs_service import register_run, unregister_run

    flag = register_run("t1", "legacy-run")

    class _OrderedRuns(_ChatRuns):
        async def cancel_active(self, thread_id, *, client_request_id=None):
            assert not flag.is_set()
            return await super().cancel_active(thread_id, client_request_id=client_request_id)

    runs = _OrderedRuns()
    service = ChatManagementService(thread_service=_Threads("owner"), user_id="owner", chat_runs=runs)
    try:
        assert (await service.stop_chat_session("t1"))["success"] is True
        assert runs.cancelled == ["t1"]
        assert flag.is_set()
    finally:
        unregister_run("t1", "legacy-run")


@pytest.mark.asyncio
async def test_a_registry_failure_still_stops_a_local_run():
    from service.runtime.active_runs_service import register_run, unregister_run

    flag = register_run("t1", "legacy-run")

    class _BrokenRuns(_ChatRuns):
        async def cancel_active(self, thread_id, *, client_request_id=None):
            raise ConnectionError("redis down")

    service = ChatManagementService(thread_service=_Threads("owner"), user_id="owner", chat_runs=_BrokenRuns())
    try:
        with pytest.raises(DependencyUnavailableError):
            await service.stop_chat_session("t1")
        assert flag.is_set()
    finally:
        unregister_run("t1", "legacy-run")


@pytest.mark.asyncio
async def test_the_stop_carries_the_send_it_targets():
    runs = _ChatRuns()
    service = ChatManagementService(thread_service=_Threads("owner"), user_id="owner", chat_runs=runs)
    assert (await service.stop_chat_session("t1", client_request_id="k1"))["success"] is True
    assert runs.request_ids == ["k1"]
