"""Process-wide Prometheus collectors for inbound HTTP traffic.

Every platform service exposes the same three series so that one dashboard and
one alert rule set work across the fleet. Label sets are deliberately small and
bounded: ``route`` carries the *route template* (``/items/{item_id}``), never the
resolved path, so a service handling millions of distinct ids still produces a
single time series per endpoint.
"""

from prometheus_client import CollectorRegistry, Counter, Histogram

REGISTRY = CollectorRegistry(auto_describe=True)

_LABELS = ("service", "method", "route")

# Latency buckets span the range a synchronous API call is expected to live in
# (5ms) up to the point where a request is effectively a timeout (30s).
_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests handled, by route template and status code.",
    (*_LABELS, "status"),
    registry=REGISTRY,
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds, by route template.",
    _LABELS,
    registry=REGISTRY,
    buckets=_DURATION_BUCKETS,
)

HTTP_REQUEST_ERRORS_TOTAL = Counter(
    "http_request_errors_total",
    "HTTP requests that ended in a 5xx response or an unhandled exception.",
    (*_LABELS, "status"),
    registry=REGISTRY,
)

__all__ = [
    "HTTP_REQUESTS_TOTAL",
    "HTTP_REQUEST_DURATION_SECONDS",
    "HTTP_REQUEST_ERRORS_TOTAL",
    "REGISTRY",
]
