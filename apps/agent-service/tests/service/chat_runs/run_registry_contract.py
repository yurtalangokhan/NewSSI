import asyncio

import pytest

from service.chat_runs.domain import ChatRun, ChatRunSpec, RunStatus


def make_run(run_id: str, thread_id: str = "t1", *, instance_id: str = "i1", **spec) -> ChatRun:
    return ChatRun.start(
        run_id=run_id,
        spec=ChatRunSpec(thread_id=thread_id, owner_user_id=spec.pop("owner", "u1"), **spec),
        instance_id=instance_id,
        now=100.0,
    )


class RunRegistryContract:
    LEASE = 5.0
    SHORT_LEASE = 0.05

    @pytest.fixture
    def registry(self):  # pragma: no cover - overridden
        raise NotImplementedError

    async def test_first_acquire_wins_and_records_the_run(self, registry):
        run = make_run("r1", input_preview="şğü öç", client_request_id="k1")
        result = await registry.try_acquire(run, lease_ttl_seconds=self.LEASE)
        assert result.acquired and result.reclaimed_run_id is None
        assert await registry.get("r1") == run
        assert (await registry.get_active_for_thread("t1")).run_id == "r1"
        assert await registry.running_run_ids() == ["r1"]

    async def test_second_acquire_on_a_live_thread_is_rejected_with_the_holder(self, registry):
        await registry.try_acquire(make_run("r1"), lease_ttl_seconds=self.LEASE)
        result = await registry.try_acquire(make_run("r2"), lease_ttl_seconds=self.LEASE)
        assert not result.acquired and result.holder_run_id == "r1"
        assert await registry.get("r2") is None

    async def test_concurrent_acquires_admit_exactly_one(self, registry):
        runs = [make_run(f"r{i}") for i in range(8)]
        results = await asyncio.gather(
            *(registry.try_acquire(r, lease_ttl_seconds=self.LEASE) for r in runs)
        )
        assert sum(r.acquired for r in results) == 1

    async def test_different_threads_do_not_contend(self, registry):
        a = await registry.try_acquire(make_run("r1", "t1"), lease_ttl_seconds=self.LEASE)
        b = await registry.try_acquire(make_run("r2", "t2"), lease_ttl_seconds=self.LEASE)
        assert a.acquired and b.acquired

    async def test_acquire_reclaims_a_lock_whose_lease_expired(self, registry):
        await registry.try_acquire(make_run("r1"), lease_ttl_seconds=self.SHORT_LEASE)
        await asyncio.sleep(self.SHORT_LEASE * 3)
        result = await registry.try_acquire(make_run("r2"), lease_ttl_seconds=self.LEASE)
        assert result.acquired and result.reclaimed_run_id == "r1"
        assert (await registry.get_active_for_thread("t1")).run_id == "r2"

    async def test_active_lookup_ignores_leaseless_and_terminal_runs(self, registry):
        await registry.try_acquire(make_run("r1"), lease_ttl_seconds=self.SHORT_LEASE)
        await asyncio.sleep(self.SHORT_LEASE * 3)
        assert await registry.get_active_for_thread("t1") is None
        await registry.try_acquire(make_run("r2", "t2"), lease_ttl_seconds=self.LEASE)
        await registry.mark_terminal(
            "r2", RunStatus.COMPLETED, error_code=None, finished_at=101.0
        )
        assert await registry.get_active_for_thread("t2") is None

    async def test_batch_active_lookup_matches_the_per_thread_lookup(self, registry):
        await registry.try_acquire(make_run("r1", "t1"), lease_ttl_seconds=self.LEASE)
        await registry.try_acquire(make_run("r2", "t2"), lease_ttl_seconds=self.SHORT_LEASE)
        await registry.try_acquire(make_run("r3", "t3"), lease_ttl_seconds=self.LEASE)
        await registry.mark_terminal(
            "r3", RunStatus.COMPLETED, error_code=None, finished_at=101.0
        )
        # r2's lease expires: only a live lease keeps a thread "active".
        await asyncio.sleep(self.SHORT_LEASE * 3)

        # Duplicates and unknown threads are tolerated.
        active = await registry.active_runs_for_threads(["t1", "t2", "t3", "t4", "t1"])

        assert set(active) == {"t1"}
        assert active["t1"].run_id == "r1"

    async def test_batch_active_lookup_on_an_empty_batch_is_empty(self, registry):
        assert await registry.active_runs_for_threads([]) == {}

    async def test_renew_lease_only_by_the_owner_instance(self, registry):
        await registry.try_acquire(make_run("r1"), lease_ttl_seconds=self.LEASE)
        assert not await registry.renew_lease("r1", "other", lease_ttl_seconds=self.LEASE)
        assert await registry.renew_lease("r1", "i1", lease_ttl_seconds=self.LEASE)

    async def test_renew_fails_once_the_lease_expired(self, registry):
        await registry.try_acquire(make_run("r1"), lease_ttl_seconds=self.SHORT_LEASE)
        await asyncio.sleep(self.SHORT_LEASE * 3)
        assert not await registry.renew_lease("r1", "i1", lease_ttl_seconds=self.LEASE)
        assert not await registry.has_live_lease("r1")

    async def test_mark_terminal_is_first_wins(self, registry):
        await registry.try_acquire(make_run("r1"), lease_ttl_seconds=self.LEASE)
        first = await registry.mark_terminal(
            "r1", RunStatus.CANCELLED, error_code=None, finished_at=101.0
        )
        second = await registry.mark_terminal(
            "r1", RunStatus.COMPLETED, error_code=None, finished_at=102.0
        )
        stored = await registry.get("r1")
        assert (first, second) == (True, False)
        assert (stored.status, stored.finished_at) == (RunStatus.CANCELLED, 101.0)
        assert await registry.running_run_ids() == []

    async def test_mark_terminal_of_unknown_run_is_false(self, registry):
        assert not await registry.mark_terminal(
            "nope", RunStatus.FAILED, error_code="x", finished_at=1.0
        )

    async def test_release_keeps_a_lock_now_held_by_another_run(self, registry):
        old = make_run("r1")
        await registry.try_acquire(old, lease_ttl_seconds=self.SHORT_LEASE)
        await asyncio.sleep(self.SHORT_LEASE * 3)
        await registry.try_acquire(make_run("r2"), lease_ttl_seconds=self.LEASE)
        await registry.release(old)
        assert (await registry.get_active_for_thread("t1")).run_id == "r2"

    async def test_release_frees_the_thread(self, registry):
        run = make_run("r1")
        await registry.try_acquire(run, lease_ttl_seconds=self.LEASE)
        await registry.release(run)
        assert await registry.get_active_for_thread("t1") is None
        assert not await registry.has_live_lease("r1")

    async def test_cancel_request_is_visible_to_any_reader(self, registry):
        assert not await registry.is_cancel_requested("r1")
        await registry.request_cancel("r1", ttl_seconds=600)
        assert await registry.is_cancel_requested("r1")

    async def test_a_request_cancel_is_scoped_to_its_thread_and_request(self, registry):
        # Marks a Stop that arrived before the send it targets was registered.
        await registry.request_cancel_for_request("t1", "k1", ttl_seconds=60)
        assert await registry.is_request_cancelled("t1", "k1")
        assert not await registry.is_request_cancelled("t1", "k2")
        assert not await registry.is_request_cancelled("t2", "k1")
