"""Persistence abstractions used by the sync runner and scheduler.

Only protocols plus in-memory implementations live here; services provide
database-backed implementations (e.g. SQLAlchemy) by satisfying the same
protocols, keeping the framework free of storage dependencies (DIP).

Each protocol lists what the framework itself calls, nothing more. A host's
store may offer further operations (job history, deleting a connection); those
are between the host and its store.
"""

from __future__ import annotations

import asyncio
import builtins
from datetime import datetime
from typing import Protocol, runtime_checkable

from .errors import JobTakenOverError
from .models import Connection, Job, ScheduleEntry, SyncState


@runtime_checkable
class StateStore(Protocol):
    """Stores incremental checkpoints per connection."""

    async def load(self, connection_id: str) -> SyncState: ...

    async def save(self, connection_id: str, state: SyncState) -> None: ...

    async def reset(self, connection_id: str) -> None:
        """Forget the checkpoints of a connection: its next run reads from the start."""
        ...


@runtime_checkable
class JobStore(Protocol):
    async def create(self, job: Job) -> Job: ...

    async def update(self, job: Job) -> Job:
        """Overwrite the stored job. Raises :class:`JobTakenOverError` instead of
        making a job that is stored as terminal live again (a worker that was
        declared dead must not resurrect its job)."""
        ...

    async def get(self, job_id: str) -> Job | None: ...

    async def list_active(self, connection_id: str | None = None) -> list[Job]:
        """Jobs that are not in a terminal state (pending or running)."""
        ...


@runtime_checkable
class ExclusiveJobStore(JobStore, Protocol):
    """A job store that can guarantee one live job per connection.

    Without it the runner checks and then creates, which two replicas can do at
    the same moment. A store that implements this closes the gap.
    """

    async def create_exclusive(self, job: Job) -> Job | None:
        """Create ``job`` unless its connection has another non-terminal job.

        One atomic step. Returns ``None`` when such a job exists.
        """
        ...


@runtime_checkable
class ConnectionReader(Protocol):
    """What the scheduler needs to know about connections."""

    async def get(self, connection_id: str) -> Connection | None: ...

    async def list(self) -> builtins.list[Connection]: ...


@runtime_checkable
class ConnectionStore(ConnectionReader, Protocol):
    """Full connection persistence, for hosts that keep connections in a store of this shape."""

    async def create(self, connection: Connection) -> Connection: ...

    async def update(self, connection: Connection) -> Connection: ...

    async def delete(self, connection_id: str) -> None: ...


@runtime_checkable
class ScheduleStore(Protocol):
    """Durable ``next_run_at`` bookkeeping. ``claim`` makes scheduling safe with several
    replicas: only the process whose compare-and-set succeeds starts the run."""

    async def get(self, connection_id: str) -> ScheduleEntry | None: ...

    async def upsert(self, entry: ScheduleEntry) -> ScheduleEntry: ...

    async def delete(self, connection_id: str) -> None: ...

    async def list(self) -> builtins.list[ScheduleEntry]: ...

    async def list_due(self, now: datetime, limit: int = 100) -> builtins.list[ScheduleEntry]: ...

    async def claim(
        self, connection_id: str, expected_next_run_at: datetime | None, new_next_run_at: datetime
    ) -> bool:
        """Atomically move ``next_run_at`` from ``expected`` to ``new``. False if it moved."""
        ...


class InMemoryStateStore:
    def __init__(self) -> None:
        self._states: dict[str, SyncState] = {}
        self._lock = asyncio.Lock()

    async def load(self, connection_id: str) -> SyncState:
        async with self._lock:
            found = self._states.get(connection_id)
            return found.model_copy(deep=True) if found else SyncState()

    async def save(self, connection_id: str, state: SyncState) -> None:
        async with self._lock:
            self._states[connection_id] = state.model_copy(deep=True)

    async def reset(self, connection_id: str) -> None:
        async with self._lock:
            self._states.pop(connection_id, None)


class InMemoryJobStore:
    """Jobs of this process. Finished jobs are kept newest-first up to
    ``max_finished_jobs``; live jobs are never dropped."""

    def __init__(self, max_finished_jobs: int = 1000) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self._max_finished = max(int(max_finished_jobs), 0)
        self._finished = 0

    async def create(self, job: Job) -> Job:
        async with self._lock:
            self._put(job)
            return job

    async def create_exclusive(self, job: Job) -> Job | None:
        async with self._lock:
            if any(
                not other.is_terminal and other.connection_id == job.connection_id
                for other in self._jobs.values()
            ):
                return None
            self._put(job)
            return job

    async def update(self, job: Job) -> Job:
        async with self._lock:
            stored = self._jobs.get(job.id)
            if stored is not None and stored.is_terminal and not job.is_terminal:
                # Ended by another worker (a stale-job takeover): it stays ended.
                raise JobTakenOverError(job.id)
            self._put(job)
            return job

    def _put(self, job: Job) -> None:
        before = self._jobs.get(job.id)
        self._jobs[job.id] = job.model_copy(deep=True)
        if job.is_terminal and (before is None or not before.is_terminal):
            self._finished += 1
            self._evict()

    def _evict(self) -> None:
        """Drop the oldest finished jobs over the cap (insertion order = creation order)."""
        if self._finished <= self._max_finished:
            return
        for job_id in [i for i, j in self._jobs.items() if j.is_terminal]:
            if self._finished <= self._max_finished:
                return
            del self._jobs[job_id]
            self._finished -= 1

    async def get(self, job_id: str) -> Job | None:
        async with self._lock:
            found = self._jobs.get(job_id)
            return found.model_copy(deep=True) if found else None

    async def list_active(self, connection_id: str | None = None) -> list[Job]:
        async with self._lock:
            return [
                j.model_copy(deep=True)
                for j in self._jobs.values()
                if not j.is_terminal and (connection_id is None or j.connection_id == connection_id)
            ]

    async def list(self, connection_id: str | None = None, limit: int = 50) -> builtins.list[Job]:
        """Job history, newest first."""
        async with self._lock:
            jobs = [
                j.model_copy(deep=True)
                for j in self._jobs.values()
                if connection_id is None or j.connection_id == connection_id
            ]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]


class InMemoryConnectionStore:
    def __init__(self) -> None:
        self._items: dict[str, Connection] = {}
        self._lock = asyncio.Lock()

    async def create(self, connection: Connection) -> Connection:
        async with self._lock:
            self._items[connection.id] = connection.model_copy(deep=True)
            return connection

    async def update(self, connection: Connection) -> Connection:
        async with self._lock:
            self._items[connection.id] = connection.model_copy(deep=True)
            return connection

    async def get(self, connection_id: str) -> Connection | None:
        async with self._lock:
            found = self._items.get(connection_id)
            return found.model_copy(deep=True) if found else None

    async def delete(self, connection_id: str) -> None:
        async with self._lock:
            self._items.pop(connection_id, None)

    async def list(self) -> builtins.list[Connection]:
        async with self._lock:
            return [c.model_copy(deep=True) for c in self._items.values()]


class InMemoryScheduleStore:
    def __init__(self) -> None:
        self._items: dict[str, ScheduleEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, connection_id: str) -> ScheduleEntry | None:
        async with self._lock:
            found = self._items.get(connection_id)
            return found.model_copy(deep=True) if found else None

    async def upsert(self, entry: ScheduleEntry) -> ScheduleEntry:
        async with self._lock:
            self._items[entry.connection_id] = entry.model_copy(deep=True)
            return entry

    async def delete(self, connection_id: str) -> None:
        async with self._lock:
            self._items.pop(connection_id, None)

    async def list(self) -> builtins.list[ScheduleEntry]:
        async with self._lock:
            return [e.model_copy(deep=True) for e in self._items.values()]

    async def list_due(self, now: datetime, limit: int = 100) -> builtins.list[ScheduleEntry]:
        async with self._lock:
            due = [
                e.model_copy(deep=True)
                for e in self._items.values()
                if e.enabled and e.next_run_at is not None and e.next_run_at <= now
            ]
        due.sort(key=lambda e: e.next_run_at or now)
        return due[:limit]

    async def claim(
        self, connection_id: str, expected_next_run_at: datetime | None, new_next_run_at: datetime
    ) -> bool:
        async with self._lock:
            entry = self._items.get(connection_id)
            if entry is None or entry.next_run_at != expected_next_run_at:
                return False
            entry.next_run_at = new_next_run_at
            return True
