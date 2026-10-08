"""Prometheus collectors for chat runs, on the service-wide registry served at /metrics.

Labels are bounded: ``status`` is a RunStatus and ``reason`` a platform end
reason or ``agent_error`` (see ``bounded_reason``).
"""

from __future__ import annotations

from metrics import REGISTRY
from prometheus_client import Counter, Gauge, Histogram

from service.chat_runs.domain import RunStatus

CHAT_RUNS_ACTIVE = Gauge(
    "chat_runs_active",
    "Chat runs this process is executing.",
    registry=REGISTRY,
)
CHAT_RUN_EVENT_STREAMS_OPEN = Gauge(
    "chat_run_event_streams_open",
    "Open chat-run SSE subscriptions; each holds a Redis connection while it waits.",
    registry=REGISTRY,
)
CHAT_RUNS_FINISHED_TOTAL = Counter(
    "chat_runs_finished_total",
    "Chat runs this process recorded as finished, by status and end reason.",
    ("status", "reason"),
    registry=REGISTRY,
)
# A lag near CHAT_RUN_LEASE_TTL_SECONDS means other instances are about to
# reap every run on this one.
CHAT_RUN_HEARTBEAT_LAG_SECONDS = Histogram(
    "chat_run_heartbeat_lag_seconds",
    "How late chat-run lease heartbeats woke up (event-loop stall time).",
    registry=REGISTRY,
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)


class PrometheusChatRunMetrics:
    def run_started(self) -> None:
        CHAT_RUNS_ACTIVE.inc()

    def run_ended(self) -> None:
        CHAT_RUNS_ACTIVE.dec()

    def run_finished(self, status: RunStatus, reason: str) -> None:
        CHAT_RUNS_FINISHED_TOTAL.labels(status=status.value, reason=reason).inc()

    def heartbeat_lag(self, seconds: float) -> None:
        CHAT_RUN_HEARTBEAT_LAG_SECONDS.observe(seconds)

    def stream_opened(self) -> None:
        CHAT_RUN_EVENT_STREAMS_OPEN.inc()

    def stream_closed(self) -> None:
        CHAT_RUN_EVENT_STREAMS_OPEN.dec()
