"""connector-py: a generic, pluggable source → destination connector framework.

Quick start::

    from connector import ConnectorRegistry, RuntimeOverrides, SyncRunner
    from connector import Connection, ConfiguredCatalog
    from connector.sources.jsonl_file import JsonlFileSource
    from connector.destinations.http_batch import HttpBatchDestination

    registry = ConnectorRegistry(overrides=RuntimeOverrides())
    registry.register(JsonlFileSource)
    registry.register(HttpBatchDestination)

    src = JsonlFileSource.from_config({"directory": "./data"})
    catalog = ConfiguredCatalog.from_catalog(await src.discover())
    conn = Connection(
        name="demo", source_name="jsonl_file", source_config={"directory": "./data"},
        destination_name="http_batch",
        destination_config={"base_url": "http://ingest.internal:8080",
                            "batch_path": "/ingest/batch", "datasource_id": "abc"},
        catalog=catalog,
    )
    job = await SyncRunner(registry).run(conn)
"""

from .base import (
    BaseConnector,
    BaseDestination,
    BaseSource,
    EmptyConfig,
    secret_field,
    sensitive_mapping_field,
)
from .errors import (
    CheckFailedError,
    ConfigValidationError,
    ConnectorDisabledError,
    ConnectorError,
    ConnectorNotFoundError,
    DestinationWriteError,
    DuplicateConnectorError,
    JobNotFoundError,
    JobTakenOverError,
    MissingExtraError,
    SourceError,
    StreamNotFoundError,
    SyncAlreadyRunningError,
    SyncError,
)
from .factory import ConnectorFactory, RegistryConnectorFactory
from .models import (
    Batch,
    Catalog,
    CheckResult,
    ConfiguredCatalog,
    ConfiguredStream,
    Connection,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorInfo,
    ConnectorKind,
    ConnectorSpec,
    DestinationSyncMode,
    Job,
    JobStatus,
    JobTrigger,
    Record,
    Schedule,
    ScheduleEntry,
    State,
    Stream,
    StreamStats,
    SyncMode,
    SyncState,
    WriteResult,
)
from .redaction import redact_secrets
from .registry import ConnectorRegistry, default_registry
from .scheduler import SyncScheduler, next_run_at
from .stores import (
    ConnectionReader,
    ConnectionStore,
    ExclusiveJobStore,
    InMemoryConnectionStore,
    InMemoryJobStore,
    InMemoryScheduleStore,
    InMemoryStateStore,
    JobStore,
    ScheduleStore,
    StateStore,
)
from .sync import RetryPolicy, SyncOptions, SyncRunner
from .visibility import (
    AllowAllPolicy,
    CallableVisibilitySource,
    EnvVisibilitySource,
    FileVisibilitySource,
    LayeredVisibilityPolicy,
    RuntimeOverrides,
    StaticVisibilitySource,
    Verdict,
    VisibilityPolicy,
    VisibilityRules,
    VisibilitySource,
    default_policy,
)

__all__ = [
    # base
    "BaseConnector",
    "BaseSource",
    "BaseDestination",
    "EmptyConfig",
    "secret_field",
    "sensitive_mapping_field",
    "redact_secrets",
    # errors
    "ConnectorError",
    "ConnectorNotFoundError",
    "ConnectorDisabledError",
    "ConfigValidationError",
    "CheckFailedError",
    "StreamNotFoundError",
    "DestinationWriteError",
    "SyncError",
    "SyncAlreadyRunningError",
    "JobNotFoundError",
    "JobTakenOverError",
    "SourceError",
    "MissingExtraError",
    "DuplicateConnectorError",
    # factory
    "ConnectorFactory",
    "RegistryConnectorFactory",
    # models
    "ConnectorKind",
    "ConnectorCategory",
    "ConnectorDefinition",
    "ConnectorInfo",
    "ConnectorSpec",
    "CheckResult",
    "SyncMode",
    "DestinationSyncMode",
    "Stream",
    "Catalog",
    "ConfiguredStream",
    "ConfiguredCatalog",
    "Record",
    "State",
    "SyncState",
    "Batch",
    "WriteResult",
    "Schedule",
    "Connection",
    "Job",
    "JobStatus",
    "JobTrigger",
    "ScheduleEntry",
    "StreamStats",
    # registry
    "ConnectorRegistry",
    "default_registry",
    # visibility
    "VisibilityPolicy",
    "VisibilitySource",
    "VisibilityRules",
    "Verdict",
    "LayeredVisibilityPolicy",
    "AllowAllPolicy",
    "StaticVisibilitySource",
    "EnvVisibilitySource",
    "FileVisibilitySource",
    "CallableVisibilitySource",
    "RuntimeOverrides",
    "default_policy",
    # stores
    "StateStore",
    "JobStore",
    "ExclusiveJobStore",
    "ConnectionReader",
    "ConnectionStore",
    "InMemoryStateStore",
    "InMemoryJobStore",
    "InMemoryConnectionStore",
    "InMemoryScheduleStore",
    "ScheduleStore",
    # sync / schedule
    "SyncRunner",
    "SyncOptions",
    "RetryPolicy",
    "SyncScheduler",
    "next_run_at",
]
