"""Protocol models shared by sources, destinations and the sync runner.

Definition, spec, catalog, record, state, connection and job: the vocabulary a
host service builds its connector catalog, sync jobs and schedules from.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Catalog / definition
# ---------------------------------------------------------------------------


class ConnectorKind(enum.StrEnum):
    SOURCE = "source"
    DESTINATION = "destination"


class ConnectorCategory(enum.StrEnum):
    """Coarse grouping used by catalog UIs to section the connector list."""

    DATABASE = "database"
    WAREHOUSE = "warehouse"
    FILE = "file"
    STORAGE = "storage"
    API = "api"
    SAAS = "saas"
    KNOWLEDGE_BASE = "knowledge_base"
    TICKETING = "ticketing"
    MESSAGING = "messaging"
    SALES = "sales"
    CODE_REPOSITORY = "code_repository"
    SEARCH_ENGINE = "search_engine"
    STREAMING = "streaming"
    VECTOR_STORE = "vector_store"
    TESTING = "testing"
    OTHER = "other"


class SyncMode(enum.StrEnum):
    """How a stream is read from the source."""

    FULL_REFRESH = "full_refresh"
    INCREMENTAL = "incremental"


class DestinationSyncMode(enum.StrEnum):
    """How records are written into the destination."""

    OVERWRITE = "overwrite"
    APPEND = "append"


class ConnectorDefinition(BaseModel):
    """Static, config-independent description of a connector.

    This is what a catalog UI lists. Visibility (``is_available``) is *not*
    stored on the class; it is computed by the registry's visibility policy at
    request time.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Unique machine name, e.g. 'postgres'.")
    display_name: str
    kind: ConnectorKind
    category: ConnectorCategory | None = None
    documentation_url: str | None = None
    icon_url: str | None = Field(
        default=None,
        description="External icon URL, if any. Services may instead expose the bundled SVG.",
    )
    icon: str | None = Field(
        default=None,
        description="Bundled SVG resource: 'file.svg' (looked up in connector.icons) or "
        "'my_pkg.assets:file.svg' for third-party packages.",
    )
    tags: frozenset[str] = Field(default_factory=frozenset)
    version: str = "0.1.0"


class ConnectorInfo(ConnectorDefinition):
    """Definition enriched with the visibility decision for the caller."""

    is_available: bool = True
    unavailable_reason: str | None = None
    has_icon: bool = False


class ConnectorSpec(BaseModel):
    """JSON Schema describing the configuration a connector accepts."""

    name: str
    display_name: str
    kind: ConnectorKind
    connection_specification: dict[str, Any]
    documentation_url: str | None = None
    category: ConnectorCategory | None = None
    icon_svg: str | None = Field(
        default=None, description="Inline SVG markup for the connector, when bundled."
    )
    supported_sync_modes: list[SyncMode] = Field(default_factory=list)
    supported_destination_sync_modes: list[DestinationSyncMode] = Field(default_factory=list)


class CheckResult(BaseModel):
    ok: bool
    message: str | None = None


class Stream(BaseModel):
    """A logical table / collection / endpoint exposed by a source.

    ``json_schema`` is best effort. Databases report their columns; most API
    sources do not declare one, and an empty ``properties`` map means exactly
    that, not "no fields". Records are never validated against it.
    """

    name: str
    json_schema: dict[str, Any] = Field(default_factory=dict)
    supported_sync_modes: list[SyncMode] = Field(default_factory=lambda: [SyncMode.FULL_REFRESH])
    source_defined_cursor: bool = False
    default_cursor_field: list[str] = Field(default_factory=list)
    source_defined_primary_key: list[list[str]] = Field(default_factory=list)
    namespace: str | None = None


class Catalog(BaseModel):
    streams: list[Stream] = Field(default_factory=list)

    def get(self, name: str) -> Stream | None:
        return next((s for s in self.streams if s.name == name), None)

    def names(self) -> list[str]:
        return [s.name for s in self.streams]


class ConfiguredStream(BaseModel):
    """A stream chosen for a sync, with the modes to use."""

    stream: Stream
    sync_mode: SyncMode = SyncMode.FULL_REFRESH
    destination_sync_mode: DestinationSyncMode = DestinationSyncMode.OVERWRITE
    cursor_field: list[str] = Field(default_factory=list)
    primary_key: list[list[str]] = Field(default_factory=list)


class ConfiguredCatalog(BaseModel):
    streams: list[ConfiguredStream] = Field(default_factory=list)

    @classmethod
    def from_catalog(
        cls,
        catalog: Catalog,
        *,
        sync_mode: SyncMode = SyncMode.FULL_REFRESH,
        destination_sync_mode: DestinationSyncMode = DestinationSyncMode.OVERWRITE,
        only: list[str] | None = None,
    ) -> ConfiguredCatalog:
        """Select every (or ``only`` the named) stream with a uniform mode."""
        chosen = [s for s in catalog.streams if only is None or s.name in only]
        return cls(
            streams=[
                ConfiguredStream(
                    stream=s,
                    sync_mode=sync_mode
                    if sync_mode in s.supported_sync_modes
                    else SyncMode.FULL_REFRESH,
                    destination_sync_mode=destination_sync_mode,
                    cursor_field=s.default_cursor_field,
                    primary_key=s.source_defined_primary_key,
                )
                for s in chosen
            ]
        )

    def names(self) -> list[str]:
        return [s.stream.name for s in self.streams]


# ---------------------------------------------------------------------------
# Data flow
# ---------------------------------------------------------------------------


class Record(BaseModel):
    """One row emitted by a source."""

    stream: str
    data: dict[str, Any]
    emitted_at: datetime = Field(default_factory=utcnow)
    namespace: str | None = None


class State(BaseModel):
    """Per-stream checkpoint. ``data`` is opaque to the framework."""

    stream: str
    data: dict[str, Any] = Field(default_factory=dict)


class SyncState(BaseModel):
    """All stream checkpoints of a connection."""

    streams: dict[str, dict[str, Any]] = Field(default_factory=dict)

    def get(self, stream: str) -> dict[str, Any]:
        return self.streams.get(stream, {})

    def update(self, state: State) -> None:
        self.streams[state.stream] = dict(state.data)


class Batch(BaseModel):
    """What a destination receives per flush."""

    stream: str
    records: list[Record]
    batch_index: int
    is_last: bool = False
    """Set on the closing batch of a stream. Only a destination that declares
    ``needs_final_batch`` is guaranteed to receive one (possibly empty)."""
    connection_id: str | None = None
    source_name: str | None = None
    job_id: str | None = None
    """The sync run this batch belongs to; ``(job_id, stream, batch_index)`` identifies
    a batch across retries."""

    @property
    def size(self) -> int:
        return len(self.records)


class WriteResult(BaseModel):
    records_written: int = 0
    extra: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Connections / jobs / schedule
# ---------------------------------------------------------------------------


class Schedule(BaseModel):
    """When a connection syncs on its own: a cron expression *or* a fixed interval.

    * ``cron_expression`` - five-field crontab syntax evaluated in ``timezone``
      (needs the ``scheduler`` extra).
    * ``interval_seconds`` - "every N seconds"; the next run is counted from the
      previous scheduled time, so runs do not drift with job duration.
    """

    cron_expression: str | None = None
    interval_seconds: int | None = Field(default=None, ge=1)
    timezone: str = "UTC"
    enabled: bool = True
    run_on_create: bool = Field(
        default=False, description="Run once right away instead of waiting for the first slot."
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> Schedule:
        if bool(self.cron_expression) == bool(self.interval_seconds):
            raise ValueError("set exactly one of cron_expression or interval_seconds")
        return self

    @classmethod
    def cron(cls, expression: str, timezone: str = "UTC", **kw: Any) -> Schedule:
        return cls(cron_expression=expression, timezone=timezone, **kw)

    @classmethod
    def every(
        cls, *, seconds: int = 0, minutes: int = 0, hours: int = 0, days: int = 0, **kw: Any
    ) -> Schedule:
        total = seconds + minutes * 60 + hours * 3600 + days * 86400
        return cls(interval_seconds=total, **kw)

    def fingerprint(self) -> str:
        """Changes whenever the timing definition changes (used to reset ``next_run_at``)."""
        return f"{self.cron_expression}|{self.interval_seconds}|{self.timezone}|{self.enabled}"


class ScheduleEntry(BaseModel):
    """Durable scheduling state of one connection. Survives restarts."""

    connection_id: str
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_job_id: str | None = None
    enabled: bool = True
    fingerprint: str = ""
    updated_at: datetime = Field(default_factory=utcnow)


class Connection(BaseModel):
    """Binds a configured source to a configured destination."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    source_name: str
    source_config: dict[str, Any]
    destination_name: str
    destination_config: dict[str, Any]
    catalog: ConfiguredCatalog
    schedule: Schedule | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class JobStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobTrigger(enum.StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    RESUME = "resume"
    """Started automatically because a previous job was interrupted by a shutdown."""


class StreamStats(BaseModel):
    records_read: int = 0
    records_written: int = 0
    batches: int = 0


class Job(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    connection_id: str
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stats: dict[str, StreamStats] = Field(default_factory=dict)
    error: str | None = None
    trigger: JobTrigger = JobTrigger.MANUAL
    worker_id: str | None = Field(default=None, description="Process that owns the job.")
    heartbeat_at: datetime | None = Field(
        default=None, description="Last sign of life; stale heartbeats mark dead jobs."
    )

    @property
    def is_terminal(self) -> bool:
        return self.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}

    @property
    def records_read(self) -> int:
        return sum(s.records_read for s in self.stats.values())

    @property
    def records_written(self) -> int:
        return sum(s.records_written for s in self.stats.values())
