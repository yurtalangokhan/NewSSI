"""Regression tests for the observability wiring of the idempotency middleware.

Two contracts live here:

- Ordering: ``MetricsMiddleware`` must be registered last, so it is outermost
  and observes the responses the idempotency middleware short-circuits. When
  metrics sat inside it, a store outage's 503 never reached the counter and
  the outage was invisible in dashboards.
- Wiring: the idempotency config must carry a decision recorder bound to this
  service, so decisions land in ``idempotency_decisions_total``.
"""

import redis.exceptions
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import app
from core.http.api_versioning import API_PREFIX
from core.http.idempotency import build_idempotency_config
from idempotency import AsyncRedisPool, IdempotencyMiddleware
from metrics import REGISTRY, MetricsMiddleware


def _is_idempotency(cls: type) -> bool:
    """The service installs its response-envelope subclass of the shared middleware."""
    return issubclass(cls, IdempotencyMiddleware)


def _middleware_classes() -> list[type]:
    # Starlette's add_middleware prepends, so index 0 is the outermost
    # middleware and the list runs inward.
    return [middleware.cls for middleware in app.user_middleware]


def test_metrics_middleware_is_registered_last_and_outermost() -> None:
    classes = _middleware_classes()

    assert classes[0] is MetricsMiddleware, (
        "MetricsMiddleware must be registered last so it wraps every other "
        f"middleware; got order {classes}"
    )
    assert classes.index(MetricsMiddleware) < next(i for i, c in enumerate(classes) if _is_idempotency(c)), (
        "metrics must sit outside idempotency, or the 503 an unavailable store "
        "produces is never counted"
    )


def test_idempotency_config_carries_a_decision_recorder() -> None:
    from metrics import install_idempotency_recorder

    config = build_idempotency_config(
        SimpleNamespace(
            REDIS_HOST="localhost",
            REDIS_PORT=6379,
            REDIS_DB=0,
            REDIS_PASSWORD="",
            IDEMPOTENCY_TTL=86400,
            IDEMPOTENCY_ENABLED=True,
            IDEMPOTENCY_LOCK_TTL=10.0,
            IDEMPOTENCY_WAIT_TIMEOUT=10.0,
        )
    )

    assert config.decision_recorder is not None
    assert config.service_name == "agent-service"


def test_store_unavailable_503_is_counted_by_http_metrics() -> None:
    """The G2 regression: a 503 the idempotency middleware produces must show
    up in http_requests_total. This fails while metrics sits inside the
    idempotency middleware, because the short-circuited response never
    reaches the counter."""

    def _count_503() -> float:
        # collect() reports the counter family without the _total suffix
        # ("http_requests"); the samples inside still carry it.
        total = 0.0
        for metric in REGISTRY.collect():
            if metric.name != "http_requests":
                continue
            for sample in metric.samples:
                if sample.name == "http_requests_total" and sample.labels.get("status") == "503":
                    total += sample.value
        return total

    before = _count_503()

    async def fail(config):
        raise redis.exceptions.RedisError("down")

    with _patch_connect(fail):
        response = TestClient(app).post(
            f"{API_PREFIX}/chat/sessions",
            json={"title": "t"},
            headers={"Idempotency-Key": "observability-regression"},
        )

    assert response.status_code == 503
    assert _count_503() > before, "the 503 must be counted by http_requests_total"


def _patch_connect(fail):
    return patch.object(AsyncRedisPool, "connect", fail)
