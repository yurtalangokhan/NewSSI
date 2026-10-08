"""OpenTelemetry: distributed traces and push-based metrics.

The package's other modules own what a service emits on its own: logs in one
schema, Prometheus metrics on a scrape endpoint, correlation ids in every
record. This module owns the third pillar and the push half of the second: spans
that follow a request across services, and metrics delivered to a collector over
OTLP without that collector having to scrape anything.

Everything here is off until it is switched on. With ``enabled=False`` the setup
is a no-op, the middleware creates no spans, and the process pays nothing - which
is what lets the same image run with tracing in one environment and without it
in another. When enabled, the SDK is configured from a :class:`TelemetryConfig`
the service binding builds from its own environment; this module reads no
environment itself.

The trace id a span produces is the same one the log records carry: the
correlation middleware binds it into the log context, so a trace in the tracing
UI and its log lines in Elasticsearch are joined by one value.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: The W3C header a trace context travels in. Kept here because it is what the
#: middleware extracts and what outbound calls inject.
TRACEPARENT_HEADER = "traceparent"


@dataclass(frozen=True)
class TelemetryConfig:
    """Everything a service needs to say about its own telemetry.

    ``enabled`` gates the whole module: with it false, nothing is configured and
    no span or metric is produced. ``endpoint`` is the OTLP endpoint of a
    collector; without one there is nowhere to deliver to, so enabling without an
    endpoint is treated as not enabled rather than as a silent loss of data.
    """

    service_name: str
    enabled: bool = False
    endpoint: str | None = None
    headers: tuple[tuple[str, str], ...] = ()
    sample_ratio: float = 1.0
    metrics_enabled: bool = False
    metrics_interval_ms: int = 60000
    export_timeout_ms: int = 10000

    def __post_init__(self) -> None:
        if not self.service_name:
            raise ValueError("service_name is required: every span and metric carries it")
        if not 0.0 <= self.sample_ratio <= 1.0:
            raise ValueError("sample_ratio must be between 0.0 and 1.0")
        object.__setattr__(self, "headers", tuple(self.headers))

    @property
    def active(self) -> bool:
        """Whether telemetry can actually deliver: enabled and with somewhere to go."""
        return self.enabled and bool(self.endpoint)


_state_lock = threading.Lock()
_config: TelemetryConfig | None = None
_tracer_provider: Any = None
_meter_provider: Any = None


def setup_telemetry(config: TelemetryConfig) -> TelemetryConfig:
    """Install *config* as this process's telemetry configuration.

    Safe to call again: the previous providers are shut down before the new ones
    are installed, so a repeated call cannot leak exporters or double-export.
    """
    global _config, _tracer_provider, _meter_provider

    with _state_lock:
        previous_providers = (_tracer_provider, _meter_provider)
        _config = config
        _tracer_provider = None
        _meter_provider = None

    for provider in previous_providers:
        if provider is not None:
            _shutdown_provider_quietly(provider)

    if not config.active:
        return config

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
    except ImportError:
        # The SDK is an optional dependency: a service that ships without it
        # still runs, it just has no traces or OTLP metrics to offer.
        logger.warning("opentelemetry-sdk is not installed; telemetry stays off")
        return config

    resource = Resource.create(
        {
            "service.name": config.service_name,
            "service.namespace": "agenticai",
        }
    )

    tracer_provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(config.sample_ratio)),
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=config.endpoint,
                headers=dict(config.headers) or None,
                timeout=config.export_timeout_ms / 1000,
            )
        )
    )

    meter_provider = None
    if config.metrics_enabled:
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=(
                PeriodicExportingMetricReader(
                    _otlp_metric_exporter(config),
                    export_interval_millis=config.metrics_interval_ms,
                ),
            ),
        )

    with _state_lock:
        _tracer_provider = tracer_provider
        _meter_provider = meter_provider

    from opentelemetry import metrics as otel_metrics
    from opentelemetry import trace as otel_trace

    try:
        otel_trace.set_tracer_provider(tracer_provider)
    except Exception:  # noqa: BLE001 - the SDK refuses a second global set
        logger.debug("global tracer provider already set; ours is used directly")
    if meter_provider is not None:
        try:
            otel_metrics.set_meter_provider(meter_provider)
        except Exception:  # noqa: BLE001 - same restriction on the meter side
            logger.debug("global meter provider already set; ours is used directly")

    _install_propagator()

    logger.info(
        "OpenTelemetry enabled",
        extra={
            "event": "telemetry.enabled",
            "status": "ok",
            "endpoint": config.endpoint,
            "metrics": config.metrics_enabled,
        },
    )
    return config


def _otlp_metric_exporter(config: TelemetryConfig) -> Any:
    """Build the OTLP metric exporter for the configured protocol."""
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

    return OTLPMetricExporter(
        endpoint=config.endpoint,
        headers=dict(config.headers) or None,
        timeout=config.export_timeout_ms / 1000,
    )


def _install_propagator() -> None:
    """Make W3C TraceContext (+ baggage) the global propagation format.

    Set explicitly rather than trusting the default, because the default is
    exactly this today but is not a contract; the middleware and the outbound
    hooks depend on it.
    """
    from opentelemetry.baggage.propagation import W3CBaggagePropagator
    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.propagators.composite import CompositePropagator
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    set_global_textmap(
        CompositePropagator([TraceContextTextMapPropagator(), W3CBaggagePropagator()])
    )


def shutdown_telemetry() -> None:
    """Flush and shut down the providers, then clear the configuration."""
    global _config, _tracer_provider, _meter_provider
    with _state_lock:
        providers = (_tracer_provider, _meter_provider)
        _config = None
        _tracer_provider = None
        _meter_provider = None
    for provider in providers:
        if provider is not None:
            _shutdown_provider_quietly(provider)


def _shutdown_provider_quietly(provider: Any) -> None:
    """Shut a provider down without letting a flush failure reach the caller."""
    try:
        provider.shutdown()
    except Exception:  # noqa: BLE001 - teardown must not raise
        logger.debug("telemetry provider shutdown failed", exc_info=True)


def is_enabled() -> bool:
    """Whether telemetry is configured and can deliver."""
    return _config is not None and _config.active


def current_config() -> TelemetryConfig | None:
    """Return the active configuration, or ``None`` before setup."""
    return _config


def tracer(name: str = "observability") -> Any:
    """Return a tracer, or a no-op tracer when telemetry is off.

    The tracer comes from this module's own provider rather than the global one:
    the SDK allows the global provider to be set once per process, and a
    reconfiguration must not silently keep exporting through a shut-down one.
    Call sites never branch on whether telemetry is on; a no-op tracer makes span
    code safe to write unconditionally.
    """
    if _tracer_provider is not None:
        return _tracer_provider.get_tracer(name)
    from opentelemetry import trace as otel_trace

    return otel_trace.get_tracer(name)


def meter(name: str = "observability") -> Any:
    """Return a meter, or a no-op meter when telemetry is off."""
    if _meter_provider is not None:
        return _meter_provider.get_meter(name)
    from opentelemetry import metrics as otel_metrics

    return otel_metrics.get_meter(name)


def extract_context(carrier: Any) -> Any:
    """Extract an upstream trace context from *carrier* (e.g. request headers)."""
    from opentelemetry.propagate import extract

    return extract(carrier)


def inject_context(carrier: dict[str, str]) -> dict[str, str]:
    """Inject the current trace context into *carrier* for an outbound call.

    Only fills what is missing: a caller that deliberately set its own
    ``traceparent`` is starting or continuing its own trace, and is not overruled.
    """
    from opentelemetry.propagate import inject

    if "traceparent" in carrier or TRACEPARENT_HEADER in carrier:
        return carrier
    inject(carrier)
    return carrier


def current_trace_id() -> str | None:
    """The current span's trace id as 32 hex characters, or ``None``.

    This is the join key between a trace and its log records: the correlation
    middleware binds it into the log context so every record written inside the
    span carries it.
    """
    from opentelemetry import trace as otel_trace

    span_context = otel_trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return f"{span_context.trace_id:032x}"


def counter(name: str, *, unit: str = "", description: str = "") -> Any:
    """A monotonic counter from the process meter."""
    return meter().create_counter(name, unit=unit or None, description=description or None)


def histogram(name: str, *, unit: str = "", description: str = "") -> Any:
    """A value distribution from the process meter."""
    return meter().create_histogram(name, unit=unit or None, description=description or None)


__all__ = [
    "TRACEPARENT_HEADER",
    "TelemetryConfig",
    "counter",
    "current_config",
    "current_trace_id",
    "extract_context",
    "histogram",
    "inject_context",
    "is_enabled",
    "meter",
    "setup_telemetry",
    "shutdown_telemetry",
    "tracer",
]
