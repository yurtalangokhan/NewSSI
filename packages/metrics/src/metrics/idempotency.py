"""Prometheus collectors for idempotency decisions.

One counter with an ``outcome`` label answers every decision question in a
single PromQL expression; ten separate counters could not be compared to each
other. Cardinality is bounded: ``service`` is the configured service name,
``route`` is the registered route template (never the resolved path), and
``outcome`` is the closed :class:`~idempotency.models.IdempotencyOutcome` enum.

The lock-wait histogram exists because contention is the one behaviour whose
failure is invisible without a timing series: duplicate suppression working
correctly looks identical to a request that never arrived.

This module must not import ``idempotency``. The recorder receives decisions
through a structural protocol, so the dependency direction stays
``service -> idempotency`` and ``service -> metrics`` with no package cycle.
"""

from typing import Protocol, runtime_checkable

from prometheus_client import Counter, Histogram

from .registry import REGISTRY

_WAIT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)

IDEMPOTENCY_DECISIONS_TOTAL = Counter(
    "idempotency_decisions_total",
    "Idempotency middleware decisions, by closed outcome enum.",
    ("service", "route", "outcome"),
    registry=REGISTRY,
)

IDEMPOTENCY_LOCK_WAIT_SECONDS = Histogram(
    "idempotency_lock_wait_seconds",
    "Time a concurrent duplicate spent waiting on the idempotency lock.",
    ("service", "route"),
    registry=REGISTRY,
    buckets=_WAIT_BUCKETS,
)


@runtime_checkable
class IdempotencyDecisionLike(Protocol):
    """The part of an idempotency decision the recorder needs.

    Structural on purpose: ``metrics`` must not import ``idempotency``, so the
    contract is the attribute shape, not the class.
    """

    outcome: str
    route_template: str | None
    wait_ms: float | None


def install_idempotency_recorder(service_name: str):
    """Return a decision recorder bound to ``service_name``.

    The returned callable matches the ``decision_recorder`` hook on
    ``IdempotencyConfig``. It never raises: a broken recorder must not turn a
    completed request into a 500, and the middleware already guards its side,
    but a defensive swallow here keeps the collector usable standalone.
    """

    def record(decision: IdempotencyDecisionLike) -> None:
        try:
            route = decision.route_template or "<default>"
            IDEMPOTENCY_DECISIONS_TOTAL.labels(
                service=service_name,
                route=route,
                outcome=decision.outcome,
            ).inc()
            if decision.wait_ms is not None:
                IDEMPOTENCY_LOCK_WAIT_SECONDS.labels(
                    service=service_name,
                    route=route,
                ).observe(decision.wait_ms / 1000.0)
        except Exception:  # noqa: BLE001 - metrics must never break a request
            pass

    return record


__all__ = [
    "IDEMPOTENCY_DECISIONS_TOTAL",
    "IDEMPOTENCY_LOCK_WAIT_SECONDS",
    "IdempotencyDecisionLike",
    "install_idempotency_recorder",
]
