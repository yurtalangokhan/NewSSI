"""Redis run registry: thread lock + lease + run hash + cancel flag, via Lua for atomicity.

Scripts compose the holder's lease key at runtime, so this targets single-node or
Sentinel Redis (see design non-goals).
"""

from __future__ import annotations

from collections.abc import Collection

from redis.asyncio import Redis

from infrastructure.runtime.chat_runs.keys import (
    RUN_PREFIX,
    RUNNING_SET_KEY,
    cancel_key,
    lease_key,
    request_cancel_key,
    run_key,
    thread_lock_key,
)
from service.chat_runs.domain import ChatRun, RunStatus
from service.chat_runs.ports import AcquireResult

_ACQUIRE = """
local current = redis.call('GET', KEYS[1])
if current and redis.call('EXISTS', ARGV[4] .. current .. ':lease') == 1 then
  return {0, current}
end
redis.call('SET', KEYS[1], ARGV[1])
redis.call('SET', KEYS[2], ARGV[2], 'PX', ARGV[3])
-- Pairwise HSET instead of unpack(): portable across Redis (Lua 5.1) and lupa (5.4).
for i = 6, #ARGV, 2 do redis.call('HSET', KEYS[3], ARGV[i], ARGV[i + 1]) end
-- The run hash never exists without a TTL: a start or finalization that fails
-- half-way cannot leak it (or the input preview it holds).
if tonumber(ARGV[5]) > 0 then redis.call('PEXPIRE', KEYS[3], ARGV[5]) end
redis.call('SADD', KEYS[4], ARGV[1])
return {1, current or ''}
"""

_RENEW = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
"""

_MARK_TERMINAL = """
if redis.call('HGET', KEYS[1], 'status') ~= 'running' then return 0 end
redis.call('HSET', KEYS[1], 'status', ARGV[1], 'error_code', ARGV[2], 'finished_at', ARGV[3])
redis.call('SREM', KEYS[2], ARGV[4])
return 1
"""

_RELEASE_RUN_LEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then redis.call('DEL', KEYS[1]) end
redis.call('DEL', KEYS[2])
return 1
"""


def _ms(seconds: float) -> int:
    return max(1, int(seconds * 1000))


def _to_hash(run: ChatRun) -> dict[str, str]:
    return {
        "run_id": run.run_id,
        "thread_id": run.thread_id,
        "owner_user_id": run.owner_user_id,
        "status": run.status.value,
        "started_at": repr(run.started_at),
        "finished_at": "" if run.finished_at is None else repr(run.finished_at),
        "instance_id": run.instance_id,
        "input_preview": run.input_preview,
        "client_request_id": run.client_request_id or "",
        "error_code": run.error_code or "",
    }


def _from_hash(data: dict[str, str]) -> ChatRun | None:
    if not data:
        return None
    return ChatRun(
        run_id=data["run_id"],
        thread_id=data["thread_id"],
        owner_user_id=data["owner_user_id"],
        status=RunStatus(data["status"]),
        started_at=float(data["started_at"]),
        instance_id=data["instance_id"],
        input_preview=data.get("input_preview", ""),
        client_request_id=data.get("client_request_id") or None,
        finished_at=float(data["finished_at"]) if data.get("finished_at") else None,
        error_code=data.get("error_code") or None,
    )


class RedisRunRegistry:
    def __init__(self, client: Redis) -> None:
        self._client = client
        self._acquire = client.register_script(_ACQUIRE)
        self._renew = client.register_script(_RENEW)
        self._mark_terminal = client.register_script(_MARK_TERMINAL)
        self._release = client.register_script(_RELEASE_RUN_LEASE)

    async def try_acquire(
        self, run: ChatRun, *, lease_ttl_seconds: float, run_ttl_seconds: float | None = None
    ) -> AcquireResult:
        fields = [item for pair in _to_hash(run).items() for item in pair]
        acquired, current = await self._acquire(
            keys=[
                thread_lock_key(run.thread_id),
                lease_key(run.run_id),
                run_key(run.run_id),
                RUNNING_SET_KEY,
            ],
            args=[
                run.run_id,
                run.instance_id,
                _ms(lease_ttl_seconds),
                RUN_PREFIX,
                _ms(run_ttl_seconds) if run_ttl_seconds else 0,
                *fields,
            ],
        )
        if int(acquired) == 1:
            return AcquireResult(True, reclaimed_run_id=current or None)
        return AcquireResult(False, holder_run_id=current)

    async def get(self, run_id: str) -> ChatRun | None:
        return _from_hash(await self._client.hgetall(run_key(run_id)))

    async def get_active_for_thread(self, thread_id: str) -> ChatRun | None:
        run_id = await self._client.get(thread_lock_key(thread_id))
        if not run_id:
            return None
        run = await self.get(run_id)
        if run is None or run.status.is_terminal or not await self.has_live_lease(run_id):
            return None
        return run

    async def active_runs_for_threads(self, thread_ids: Collection[str]) -> dict[str, ChatRun]:
        # Two pipelines, not two calls per row: listing a page of chats is one
        # of the busiest reads in the app, so the batch stays O(1) round trips.
        unique_threads = list(dict.fromkeys(thread_ids))
        if not unique_threads:
            return {}

        async with self._client.pipeline(transaction=False) as locks:
            for thread_id in unique_threads:
                locks.get(thread_lock_key(thread_id))
            locked_run_ids = await locks.execute()

        run_ids = [run_id for run_id in locked_run_ids if run_id]
        if not run_ids:
            return {}

        async with self._client.pipeline(transaction=False) as hashes:
            for run_id in run_ids:
                hashes.hgetall(run_key(run_id))
                hashes.exists(lease_key(run_id))
            results = await hashes.execute()

        active: dict[str, ChatRun] = {}
        for index, _run_id in enumerate(run_ids):
            data = results[index * 2]
            lease_is_live = results[index * 2 + 1]
            run = _from_hash(data) if data else None
            if run is None or run.status.is_terminal or not lease_is_live:
                continue
            active[run.thread_id] = run
        return active

    async def renew_lease(self, run_id: str, instance_id: str, *, lease_ttl_seconds: float) -> bool:
        result = await self._renew(keys=[lease_key(run_id)], args=[instance_id, _ms(lease_ttl_seconds)])
        return int(result) == 1

    async def has_live_lease(self, run_id: str) -> bool:
        return bool(await self._client.exists(lease_key(run_id)))

    async def mark_terminal(
        self, run_id: str, status: RunStatus, *, error_code: str | None, finished_at: float
    ) -> bool:
        result = await self._mark_terminal(
            keys=[run_key(run_id), RUNNING_SET_KEY],
            args=[status.value, error_code or "", repr(finished_at), run_id],
        )
        return int(result) == 1

    async def release(self, run: ChatRun) -> None:
        await self._release(keys=[thread_lock_key(run.thread_id), lease_key(run.run_id)], args=[run.run_id])

    async def request_cancel(self, run_id: str, *, ttl_seconds: int) -> None:
        await self._client.set(cancel_key(run_id), "1", ex=int(ttl_seconds))

    async def is_cancel_requested(self, run_id: str) -> bool:
        return bool(await self._client.exists(cancel_key(run_id)))

    async def request_cancel_for_request(self, thread_id: str, client_request_id: str, *, ttl_seconds: int) -> None:
        await self._client.set(request_cancel_key(thread_id, client_request_id), "1", ex=int(ttl_seconds))

    async def is_request_cancelled(self, thread_id: str, client_request_id: str) -> bool:
        return bool(await self._client.exists(request_cancel_key(thread_id, client_request_id)))

    async def running_run_ids(self) -> list[str]:
        return sorted(await self._client.smembers(RUNNING_SET_KEY))

    async def expire(self, run_id: str, ttl_seconds: int) -> None:
        await self._client.expire(run_key(run_id), int(ttl_seconds))
