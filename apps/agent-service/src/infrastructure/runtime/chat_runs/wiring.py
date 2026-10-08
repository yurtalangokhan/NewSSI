"""Composition root for chat runs: Redis adapters -> services -> process-wide provider."""

from __future__ import annotations

from dataclasses import dataclass
import os
import socket
import uuid

from redis.asyncio import BlockingConnectionPool, Redis

from infrastructure.runtime.chat_runs.prometheus_metrics import PrometheusChatRunMetrics
from infrastructure.runtime.chat_runs.redis_event_log import RedisRunEventLog
from infrastructure.runtime.chat_runs.redis_naming_lock import RedisNamingLock
from infrastructure.runtime.chat_runs.redis_run_registry import RedisRunRegistry
from service.chat.answer_activity_hook import AnswerActivityHook
from service.chat.chat_title_service import get_chat_title_service
from service.chat.session_naming_service import SessionNamingService, configure_naming_lock
from service.chat.session_title_hook import SessionTitleHook
from service.chat_runs.provider import configure_chat_runs, reset_chat_runs
from service.chat_runs.reader import RunEventReader
from service.chat_runs.reaper import OrphanRunReaper
from service.chat_runs.service import ChatRunService
from service.chat_runs.settings import ChatRunSettings
from service.chat_runs.supervisor import ChatRunSupervisor
from service.runtime.active_runs_service import bind_run_cancel_event, cancel_all_for_thread
from service.threads import get_thread_access_service

# Chat runs never use the shared (idempotency) pool: redis-py fails at once
# when a pool is exhausted, so a burst of viewers there would fail token
# writes, lease renewals and every idempotent POST alike. Writers (tokens,
# leases, reaper) and readers (SSE viewers) get separate pools that *wait* for
# a free connection instead of raising. A writer must not wait long (its lease
# is ticking); a viewer can, e.g. while hundreds of tabs replay at once after a
# deploy.
WRITER_POOL_SIZE = 50
READER_POOL_SIZE = 100
WRITER_POOL_WAIT_SECONDS = 2.0
READER_POOL_WAIT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class ChatRunRuntime:
    service: ChatRunService
    supervisor: ChatRunSupervisor
    reaper: OrphanRunReaper
    writer_client: Redis
    reader_client: Redis
    event_logs: tuple[RedisRunEventLog, ...]


def _dedicated_client(base: Redis, max_connections: int, wait_seconds: float) -> Redis:
    """A client with its own waiting pool, connected like ``base``."""
    pool = base.connection_pool
    return Redis.from_pool(
        BlockingConnectionPool(
            connection_class=pool.connection_class,
            max_connections=max_connections,
            timeout=wait_seconds,
            **pool.connection_kwargs,
        )
    )


def new_instance_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def start_chat_runs(
    client: Redis,
    *,
    settings: ChatRunSettings,
    instance_id: str,
    writer_pool_size: int = WRITER_POOL_SIZE,
    reader_pool_size: int = READER_POOL_SIZE,
) -> ChatRunRuntime:
    writer_client = _dedicated_client(client, writer_pool_size, WRITER_POOL_WAIT_SECONDS)
    reader_client = _dedicated_client(client, reader_pool_size, READER_POOL_WAIT_SECONDS)
    registry = RedisRunRegistry(writer_client)
    event_log = RedisRunEventLog(writer_client, max_events=settings.max_events)
    reader_log = RedisRunEventLog(reader_client, max_events=settings.max_events)
    naming_lock = RedisNamingLock(writer_client)
    configure_naming_lock(naming_lock)
    metrics = PrometheusChatRunMetrics()
    title_hook = SessionTitleHook(
        lambda: SessionNamingService(
            thread_service=get_thread_access_service(),
            title_service=get_chat_title_service(),
            lock=naming_lock,
        )
    )
    supervisor = ChatRunSupervisor(
        registry=registry,
        event_log=event_log,
        settings=settings,
        instance_id=instance_id,
        hooks=[title_hook, AnswerActivityHook()],
        local_cancel=cancel_all_for_thread,
        bind_cancel_event=bind_run_cancel_event,
        metrics=metrics,
    )
    reader = RunEventReader(
        registry=RedisRunRegistry(reader_client),
        event_log=reader_log,
        settings=settings,
        metrics=metrics,
    )
    reaper = OrphanRunReaper(registry=registry, event_log=event_log, settings=settings, metrics=metrics)
    service = ChatRunService(supervisor=supervisor, reader=reader, registry=registry)
    configure_chat_runs(service)
    reaper.start()
    return ChatRunRuntime(
        service=service,
        supervisor=supervisor,
        reaper=reaper,
        writer_client=writer_client,
        reader_client=reader_client,
        event_logs=(event_log, reader_log),
    )


async def stop_chat_runs(runtime: ChatRunRuntime) -> None:
    # Runs still need Redis to write their terminal frames: stop them before the pool closes.
    await runtime.supervisor.shutdown()
    await runtime.reaper.stop()
    reset_chat_runs()
    configure_naming_lock(None)
    for log in runtime.event_logs:
        await log.aclose()
    await runtime.reader_client.aclose()
    await runtime.writer_client.aclose()
