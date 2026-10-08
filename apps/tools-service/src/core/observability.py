"""Service binding for the shared observability core.

The mechanism lives in the ``observability`` package; this module owns the
tools-service names: the service name stamped on every record, the mapping from this
service's environment onto one logging configuration, its own noisy-logger
policy, the per-process dependency registry, and the readiness payload built from
it.
"""

from __future__ import annotations

from config_manager import env
from observability import (
    DependencyPolicy,
    DependencyRegistry,
    DependencyStartupError,
    DependencyStatus,
    LoggerConfig,
    RetryPolicy,
    TelemetryConfig,
    build_logger_config,
    configure,
    dependency_error_fields,
    get_logger,
    retry_async,
    retry_sync,
    sanitize_exception,
    setup_telemetry,
)
from observability.health import readiness_payload as package_readiness_payload

__all__ = [
    "DependencyPolicy",
    "DependencyRegistry",
    "DependencyStartupError",
    "DependencyStatus",
    "LoggerConfig",
    "RetryPolicy",
    "configure_logging",
    "configure_telemetry",
    "dependency_error_fields",
    "dependency_registry",
    "get_logger",
    "logger_config",
    "readiness_payload",
    "retry_async",
    "retry_sync",
    "sanitize_exception",
    "telemetry_config",
]

SERVICE_NAME = "tools-service"

# httpx/httpcore narrate every outbound request at INFO while the access log
# belongs to the gateway, so the client libraries are pinned to WARNING.
_NOISY_DEPENDENCY_LOGGERS = ("httpx", "httpcore")

dependency_registry = DependencyRegistry()


def logger_config(
    *,
    service_name: str = SERVICE_NAME,
    log_level: str | None = None,
    log_format: str | None = None,
) -> LoggerConfig:
    """Return this service's logging configuration.

    The arguments exist so a test or an embedding process can point the service
    somewhere else without changing the environment; everything else comes from
    this service's own environment names.
    """
    return build_logger_config(
        service_name,
        level=log_level or env.LOG_LEVEL,
        format=log_format or env.LOG_FORMAT,
        output=env.LOG_OUTPUT,
        file_path=env.LOG_FILE_PATH,
        max_bytes=env.LOG_MAX_SIZE,
        backup_count=env.LOG_BACKUP_COUNT,
        include_source=env.LOG_INCLUDE_SOURCE,
        quiet_loggers=_NOISY_DEPENDENCY_LOGGERS + tuple(env.LOG_QUIET_LOGGERS),
        syslog_address=env.LOG_SYSLOG_ADDRESS,
        syslog_facility=env.LOG_SYSLOG_FACILITY,
        external_url=env.LOG_EXTERNAL_URL,
        external_bearer_token=env.LOG_EXTERNAL_BEARER_TOKEN,
        external_batch_size=env.LOG_EXTERNAL_BATCH_SIZE,
        external_flush_interval=env.LOG_EXTERNAL_FLUSH_INTERVAL,
        external_max_queue=env.LOG_EXTERNAL_MAX_QUEUE,
        external_max_retries=env.LOG_EXTERNAL_MAX_RETRIES,
        external_retry_backoff=env.LOG_EXTERNAL_RETRY_BACKOFF,
        external_shutdown_timeout=env.LOG_EXTERNAL_SHUTDOWN_TIMEOUT,
    )


def configure_logging(
    *,
    service_name: str = SERVICE_NAME,
    log_level: str | None = None,
    log_format: str | None = None,
) -> None:
    """Configure this service's logging from its environment."""
    configure(logger_config(service_name=service_name, log_level=log_level, log_format=log_format))


def telemetry_config() -> TelemetryConfig:
    """Return this service's telemetry configuration from its environment.

    Off until switched on: with ``OTEL_ENABLED=false`` (the default) the setup is
    a no-op and the process produces no spans or OTLP metrics.
    """
    return TelemetryConfig(
        service_name=SERVICE_NAME,
        enabled=env.OTEL_ENABLED,
        endpoint=env.OTEL_EXPORTER_OTLP_ENDPOINT,
        headers=tuple(env.OTEL_EXPORTER_OTLP_HEADERS),
        sample_ratio=env.OTEL_TRACES_SAMPLE_RATIO,
        metrics_enabled=env.OTEL_METRICS_ENABLED,
        metrics_interval_ms=env.OTEL_METRICS_EXPORT_INTERVAL,
    )


def configure_telemetry() -> TelemetryConfig:
    """Configure this service's traces and OTLP metrics from its environment."""
    return setup_telemetry(telemetry_config())


def readiness_payload(*, service_name: str) -> dict[str, object]:
    """Build the readiness response payload from this service's registry."""
    return package_readiness_payload(dependency_registry, service_name=service_name)
