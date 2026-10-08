"""Process-wide connector runtime: catalog registry, sync runner and scheduler.

Datasource syncs run inside agent-service through ``packages/connector-py``.
This module wires the package to the service:

* the **registry** lists the built-in connectors, filtered by configuration;
* the **runner** moves records from a source to the rag-service destination,
  a bounded number of syncs at a time, persisting jobs and checkpoints;
* the **scheduler** starts due syncs from ``sync_schedules`` and resumes the
  ones a restart interrupted.

Obtain it with :func:`get_connector_runtime`; the application lifespan starts
and stops it.
"""

from __future__ import annotations

import asyncio
from typing import Any

from config_manager import env
from connector import (
    BaseSource,
    CallableVisibilitySource,
    Connection,
    ConnectorError,
    ConnectorRegistry,
    Job,
    JobStatus,
    JobTrigger,
    LayeredVisibilityPolicy,
    RegistryConnectorFactory,
    RetryPolicy,
    RuntimeOverrides,
    StaticVisibilitySource,
    SyncAlreadyRunningError,
    SyncOptions,
    SyncRunner,
    SyncScheduler,
    VisibilityRules,
)

from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import datasource_connection_repository
from service.ingest.connector_stores import (
    ConfigExists,
    ConfigReader,
    DatasourceConnectionStore,
    SyncJobStore,
    SyncScheduleStore,
    SyncStateStore,
    read_stored_config,
    stored_config_exists,
)
from service.ingest.ingestion_service import (
    trigger_graph_rag_rebuild,
    update_sync_progress,
    update_sync_status,
)
from service.ingest.rag_destination import RagDatasourceDestination

logger = get_logger(__name__)

HEARTBEAT_SECONDS = 30.0
#: A job silent for three heartbeats belongs to a process that is gone.
STALE_AFTER_SECONDS = 90.0
#: Retries of a failed batch (same idempotency key). The package default gives up
#: in ~3 s; a rag-service restart takes ~10 s and its circuit breaker then stays open
#: for 30 s, so the waits here add up to over a minute: 5 s, 10 s, 20 s, 40 s.
BATCH_RETRY = RetryPolicy(attempts=5, base_delay_seconds=5.0, max_delay_seconds=60.0)

#: Connectors that read the filesystem of the process running them. Inside
#: agent-service that is the service's own container, so they stay hidden unless
#: an operator names them in ``CONNECTORS_ENABLED``.
LOCAL_FILESYSTEM_CONNECTORS = ("jsonl_file", "file_upload", "file_server")

CONFIG_MISSING_MESSAGE = "the stored connector configuration is missing; save the datasource configuration again"


def _names(csv: str | None) -> list[str]:
    return [name.strip() for name in (csv or "").split(",") if name.strip()]


def _configured_rules() -> VisibilityRules:
    return VisibilityRules(
        enabled=_names(env.CONNECTORS_ENABLED),
        disabled=_names(env.CONNECTORS_DISABLED),
    )


def build_registry() -> ConnectorRegistry:
    """The connector catalog of this service.

    Visibility is decided in order by runtime overrides, deployment
    configuration (``CONNECTORS_ENABLED`` / ``CONNECTORS_DISABLED``), and the
    service defaults below; it is evaluated on every lookup, so a changed
    environment needs no new registry.
    """
    overrides = RuntimeOverrides()
    policy = LayeredVisibilityPolicy(
        sources=[
            overrides,
            CallableVisibilitySource(_configured_rules, name="configuration"),
            StaticVisibilitySource(
                {"disabled": list(LOCAL_FILESYSTEM_CONNECTORS), "tags": {"disabled": ["testing"]}},
                name="service defaults",
            ),
        ]
    )
    registry = ConnectorRegistry(policy=policy)  # finds the overrides layer in the policy
    registry.load_entry_points()
    registry.register(RagDatasourceDestination, replace=True)
    return registry


class ConnectorConfigMissingError(ConnectorError):
    """The configuration a datasource's connection points to is not in user-service."""

    def __init__(self) -> None:
        super().__init__(CONFIG_MISSING_MESSAGE)


class DatasourceConnectorFactory(RegistryConnectorFactory):
    """Builds a sync's connectors, fetching the source configuration only then.

    A connection carries a pointer to its configuration, not the configuration.
    The secrets leave user-service when a job actually starts running, and stay
    out of every scheduler tick and status lookup.
    """

    def __init__(
        self,
        registry: ConnectorRegistry,
        read_config: ConfigReader = read_stored_config,
        config_exists: ConfigExists = stored_config_exists,
    ) -> None:
        super().__init__(registry)
        self._read_config = read_config
        self._config_exists = config_exists

    async def stored_config(self, connection: Connection) -> dict[str, Any] | None:
        """The decrypted configuration of ``connection``, or ``None`` when it is gone."""
        meta = connection.metadata
        return await self._read_config(meta["owner_user_id"], meta["config_id"])

    async def config_exists(self, connection: Connection) -> bool:
        """Is the configuration of ``connection`` still stored? Reads no credentials."""
        meta = connection.metadata
        return await self._config_exists(meta["owner_user_id"], meta["config_id"])

    async def source(self, connection: Connection) -> BaseSource[Any]:
        config = await self.stored_config(connection)
        if config is None:
            raise ConnectorConfigMissingError
        return self.registry.get_source(connection.source_name).from_config(config)


class SyncProgressReporter:
    """Mirrors job status into the collection metadata the datasource UI polls.

    Registered as the runner's status hook: called when a job is created, when
    it starts running and when it ends, not once per batch. The runner logs and
    swallows a failure in here, so bookkeeping cannot fail a sync.

    The graph build that may follow a successful sync is started here but
    followed in a task of its own: the hook runs while the job still holds its
    sync slot, and polling rag-service for up to ten minutes there kept every
    other datasource waiting. :meth:`close` stops following the builds still
    in flight (rag-service goes on with them).
    """

    def __init__(self) -> None:
        self.graph_builds: set[asyncio.Task[None]] = set()

    async def __call__(self, job: Job) -> None:
        datasource_id = job.connection_id
        if job.status is JobStatus.PENDING:
            # Only a job that exists says so: a trigger that was refused, by hand or
            # by the scheduler, leaves the progress of the running sync alone.
            await update_sync_progress(datasource_id, "starting", 0)
        elif job.status is JobStatus.RUNNING:
            await update_sync_progress(datasource_id, "syncing", 10)
        elif job.status is JobStatus.SUCCEEDED:
            await update_sync_status(datasource_id, "completed", None)
            connection = await datasource_connection_repository().get(datasource_id)
            if connection and connection.get("update_graph_rag"):
                self._follow_graph_build(datasource_id, job.id)
        elif job.status is JobStatus.FAILED:
            await update_sync_status(datasource_id, "error", job.error or "Sync failed")
        elif job.status is JobStatus.CANCELLED:
            await update_sync_status(datasource_id, "error", "Sync cancelled")

    def _follow_graph_build(self, datasource_id: str, job_id: str) -> None:
        task = asyncio.create_task(
            trigger_graph_rag_rebuild(datasource_id, run_id=job_id), name=f"graph-build-{datasource_id}"
        )
        self.graph_builds.add(task)
        task.add_done_callback(self._graph_build_done)

    def _graph_build_done(self, task: asyncio.Task[None]) -> None:
        self.graph_builds.discard(task)
        if not task.cancelled() and task.exception() is not None:
            # ``trigger_graph_rag_rebuild`` reports its own failures on the datasource;
            # this is what escaped it, and nobody else awaits the task.
            logger.error("following a graph build failed", exc_info=task.exception())

    async def close(self) -> None:
        """Stop following the graph builds in flight; rag-service goes on with them."""
        pending = [task for task in self.graph_builds if not task.done()]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        self.graph_builds.clear()


class ConnectorRuntime:
    """Registry + runner + scheduler, sharing one set of stores."""

    def __init__(
        self,
        *,
        registry: ConnectorRegistry | None = None,
        read_config: ConfigReader = read_stored_config,
        config_exists: ConfigExists = stored_config_exists,
        connections: Any = None,
        jobs: Any = None,
        state: Any = None,
        schedules: Any = None,
    ) -> None:
        self.registry = registry or build_registry()
        self.factory = DatasourceConnectorFactory(self.registry, read_config, config_exists)
        self.connections = connections or DatasourceConnectionStore()
        self.jobs = jobs or SyncJobStore()
        self.reporter = SyncProgressReporter()
        self.runner = SyncRunner(
            self.factory,
            state_store=state or SyncStateStore(),
            job_store=self.jobs,
            options=SyncOptions(
                batch_size=env.CONNECTOR_SYNC_BATCH_SIZE,
                retry=BATCH_RETRY,
                timeout_seconds=env.CONNECTOR_SYNC_TIMEOUT_SECONDS,
                max_concurrent_jobs=env.CONNECTOR_MAX_CONCURRENT_SYNCS,
                status_hook=self.reporter,
                heartbeat_interval_seconds=HEARTBEAT_SECONDS,
                stale_after_seconds=STALE_AFTER_SECONDS,
            ),
        )
        # Several replicas share the tables: a job counts as dead only once its
        # heartbeat is older than the runner's threshold.
        self.scheduler = SyncScheduler(
            self.runner,
            self.connections,
            schedules or SyncScheduleStore(),
            poll_interval_seconds=env.CONNECTOR_SCHEDULER_POLL_SECONDS,
            replicated=True,
        )

    # ---- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        """Reconcile schedules, resume interrupted syncs, start polling."""
        resumed = await self.scheduler.start()
        logger.info(
            "Connector runtime started (%d connectors, %d interrupted sync(s) resumed)",
            len(self.registry),
            len(resumed),
        )

    async def stop(self) -> None:
        """Stop polling and leave running syncs resumable for the next start."""
        await self.scheduler.stop()
        interrupted = await self.runner.shutdown()
        await self.reporter.close()
        logger.info("Connector runtime stopped (%d sync(s) left to resume)", interrupted)

    # ---- syncs -----------------------------------------------------------

    async def start_sync(
        self,
        datasource_id: str,
        *,
        trigger: JobTrigger = JobTrigger.MANUAL,
        full_refresh: bool = False,
    ) -> Job | None:
        """Start a background sync. ``None`` when the datasource is already syncing.

        Raises ``LookupError`` when the datasource has no connector connection,
        and ``ConnectorConfigMissingError`` when its stored configuration is gone
        (checked here so the caller hears about it instead of a job failing later).
        """
        connection = await self.connections.get(datasource_id)
        if connection is None:
            raise LookupError(f"datasource {datasource_id} has no connector connection")
        # A trigger that starts nothing costs nothing: no credentials leave
        # user-service for it, and the status of the sync that runs stays as it is
        # (the datasource is marked "starting" by the job that gets created).
        if await self.runner.has_active_job(datasource_id):
            return None
        # Existence only: the configuration itself is read once, by the job when it runs.
        if not await self.factory.config_exists(connection):
            raise ConnectorConfigMissingError
        try:
            return await self.runner.start(connection, full_refresh=full_refresh, trigger=trigger)
        except SyncAlreadyRunningError:
            return None  # another trigger won in the meantime

    async def reset_checkpoints(self, datasource_id: str) -> None:
        """Forget the saved incremental checkpoints of a datasource.

        The next sync reads every stream from the start, as ``full_refresh``
        does. A connection's id is its datasource id.
        """
        await self.runner.state_store.reset(datasource_id)

    async def queue_position(self, datasource_id: str) -> int | None:
        """0-based position among the syncs waiting for a free slot, or ``None``."""
        waiting = [job.connection_id for job in await self.jobs.list_active() if job.status is JobStatus.PENDING]
        return waiting.index(datasource_id) if datasource_id in waiting else None

    async def is_active(self, datasource_id: str) -> bool:
        """Is a sync of this datasource running right now (not merely waiting)?"""
        return any(job.status is JobStatus.RUNNING for job in await self.jobs.list_active(datasource_id))

    async def latest_job(self, datasource_id: str) -> Job | None:
        jobs = await self.jobs.list(datasource_id, limit=1)
        return jobs[0] if jobs else None


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_INSTANCE: ConnectorRuntime | None = None


def get_connector_runtime() -> ConnectorRuntime:
    """Return the global ConnectorRuntime (creates lazily)."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ConnectorRuntime()
    return _INSTANCE
