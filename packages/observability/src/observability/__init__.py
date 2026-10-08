"""The platform's logging, dependency health, and startup retry mechanisms.

One package owns every log line the services write. A service's
``core/observability`` binding extends it with that service's own names: the
service name, its environment variable names, and its policy. Nothing here reads
environment variables or knows which service calls it.

A service uses logging through three calls:

  - :func:`configure` once at startup, with a :class:`LoggerConfig` its binding
    built from that service's own environment
  - :func:`get_logger` wherever it logs, which is the call most modules make
  - :func:`request_scope` or :func:`set_context_tokens` once per request, so every
    record written while handling it carries the same correlation id without any
    call site passing one

Log records carry one field set (:data:`RECORD_FIELDS`) in every destination and
every service, so a dashboard query or an index mapping works across the
platform. A destination is a :class:`LogSink`; :class:`ExternalSink` is the base
for any log platform reached over the network, so adding one is a
configuration change rather than a change to any service.
"""

from __future__ import annotations

from .config import (
    LogFormat,
    LoggerConfig,
    SinkConfig,
    UnknownSinkError,
    build_logger_config,
    sink_for,
)
from .context import (
    CORRELATION_HEADERS,
    ContextBinding,
    LogContext,
    correlation_id_from_headers,
    current_context,
    new_request_id,
    request_scope,
    reset_context,
    sanitize_correlation_id,
    set_context,
    set_context_tokens,
)
from .formatter import RECORD_FIELDS, BaseFormatter, JsonFormatter, TextFormatter, build_fields
from .health import (
    DependencyPolicy,
    DependencyRegistry,
    DependencyStartupError,
    DependencyStatus,
    readiness_payload,
)
from .manager import (
    active_sinks,
    available_sinks,
    configure,
    configured_level,
    current_config,
    flush,
    get_logger,
    is_configured,
    shutdown,
)
from .middleware import CorrelationMiddleware
from .otel import (
    TRACEPARENT_HEADER,
    TelemetryConfig,
    counter,
    current_trace_id,
    extract_context,
    histogram,
    inject_context,
    meter,
    setup_telemetry,
    shutdown_telemetry,
    tracer,
)
from .otel import (
    is_enabled as telemetry_enabled,
)
from .outbound import (
    correlation_event_hooks,
    correlation_sync_event_hooks,
    outbound_headers,
)
from .retry import RetryPolicy, retry_async, retry_sync
from .sanitize import (
    SENSITIVE_KEY_PARTS,
    dependency_error_fields,
    is_sensitive_key,
    mask_fields,
    sanitize_exception,
    sanitize_text,
)
from .sinks import LogSink, create_sink, register_sink
from .sinks.elasticsearch import ElasticsearchSink
from .sinks.external import ExternalSink

__all__ = [
    "CORRELATION_HEADERS",
    "ContextBinding",
    "CorrelationMiddleware",
    "correlation_event_hooks",
    "correlation_sync_event_hooks",
    "counter",
    "current_trace_id",
    "extract_context",
    "histogram",
    "inject_context",
    "meter",
    "DependencyPolicy",
    "DependencyRegistry",
    "BaseFormatter",
    "DependencyStartupError",
    "DependencyStatus",
    "ElasticsearchSink",
    "ExternalSink",
    "JsonFormatter",
    "LogContext",
    "LogFormat",
    "LogSink",
    "LoggerConfig",
    "RECORD_FIELDS",
    "RetryPolicy",
    "SENSITIVE_KEY_PARTS",
    "SinkConfig",
    "TRACEPARENT_HEADER",
    "TelemetryConfig",
    "TextFormatter",
    "UnknownSinkError",
    "active_sinks",
    "available_sinks",
    "build_logger_config",
    "build_fields",
    "configure",
    "configured_level",
    "correlation_id_from_headers",
    "create_sink",
    "current_config",
    "current_context",
    "dependency_error_fields",
    "flush",
    "get_logger",
    "is_configured",
    "is_sensitive_key",
    "mask_fields",
    "new_request_id",
    "outbound_headers",
    "readiness_payload",
    "register_sink",
    "request_scope",
    "setup_telemetry",
    "shutdown_telemetry",
    "telemetry_enabled",
    "tracer",
    "reset_context",
    "retry_async",
    "retry_sync",
    "sanitize_correlation_id",
    "sanitize_exception",
    "sanitize_text",
    "set_context",
    "set_context_tokens",
    "sink_for",
    "shutdown",
]
