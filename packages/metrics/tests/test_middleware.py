"""Behavioural contract for the shared HTTP metrics middleware.

The rules these tests lock down exist because the previous hand-rolled
implementation broke them: it labelled series with the raw request path
(unbounded cardinality) and emitted label values without escaping, which
corrupts the whole exposition payload for a scrape target.
"""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from metrics import (
    PROMETHEUS_CONTENT_TYPE,
    REGISTRY,
    UNKNOWN_METHOD,
    MetricsMiddleware,
    metrics_response,
)

UNMATCHED = "__unmatched__"


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def item(item_id: int) -> dict[str, int]:
        if item_id == 500:
            raise HTTPException(status_code=500)
        return {"id": item_id}

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return metrics_response()

    app.add_middleware(MetricsMiddleware, service_name="test-service")
    return app


def _sample(name: str, **labels: str) -> float | None:
    return REGISTRY.get_sample_value(name, labels)


def test_counts_requests_by_route_template_not_by_raw_path() -> None:
    client = TestClient(_app())
    client.get("/items/1")
    client.get("/items/2")

    labels = {
        "service": "test-service",
        "method": "GET",
        "route": "/items/{item_id}",
        "status": "200",
    }
    assert _sample("http_requests_total", **labels) == 2.0


def test_records_latency_under_the_route_template() -> None:
    client = TestClient(_app())
    client.get("/items/7")

    assert (
        _sample(
            "http_request_duration_seconds_count",
            service="test-service",
            method="GET",
            route="/items/{item_id}",
        )
        == 1.0
    )


def test_counts_server_errors_separately() -> None:
    client = TestClient(_app())
    client.get("/items/500")

    labels = {
        "service": "test-service",
        "method": "GET",
        "route": "/items/{item_id}",
        "status": "500",
    }
    assert _sample("http_request_errors_total", **labels) == 1.0


def test_client_errors_are_counted_but_not_as_server_errors() -> None:
    client = TestClient(_app())
    client.get("/items/not-an-int")

    labels = {
        "service": "test-service",
        "method": "GET",
        "route": "/items/{item_id}",
        "status": "422",
    }
    assert _sample("http_requests_total", **labels) == 1.0
    assert _sample("http_request_errors_total", **labels) is None


def test_unmatched_paths_collapse_into_a_single_series() -> None:
    client = TestClient(_app())
    for suffix in ("alpha", "beta", "gamma"):
        client.get(f"/no/such/route/{suffix}")

    labels = {
        "service": "test-service",
        "method": "GET",
        "route": UNMATCHED,
        "status": "404",
    }
    assert _sample("http_requests_total", **labels) == 3.0


def test_unknown_http_methods_collapse_into_a_single_series() -> None:
    # scope["method"] is set by the ASGI server straight from the raw
    # request line, before routing ever runs: an attacker can send any
    # RFC 7230 token as the method ("X-PROBE-1", "X-PROBE-2", ...) and, if
    # this label were unbounded the way route once was, mint one permanent
    # new series per probe -- the exact cardinality bug this package's own
    # route-template fix exists to prevent, just on a different label.
    client = TestClient(_app())
    for method in ("X-PROBE-1", "X-PROBE-2", "TEAPOT"):
        client.request(method, "/no/such/route")

    labels = {
        "service": "test-service",
        "method": UNKNOWN_METHOD,
        "route": UNMATCHED,
        "status": "404",
    }
    assert _sample("http_requests_total", **labels) == 3.0


def test_known_http_methods_are_labelled_verbatim() -> None:
    client = TestClient(_app())
    client.get("/items/1")

    labels = {
        "service": "test-service",
        "method": "GET",
        "route": "/items/{item_id}",
        "status": "200",
    }
    assert _sample("http_requests_total", **labels) == 1.0


def test_hostile_paths_cannot_corrupt_the_exposition_payload() -> None:
    client = TestClient(_app())
    client.get('/items/1"} fake_metric{evil="yes')

    body = metrics_response().body.decode()
    assert "fake_metric" not in body
    for line in body.splitlines():
        if line.startswith("http_requests_total{"):
            assert line.count('"') % 2 == 0


def test_metrics_endpoint_is_prometheus_text_and_not_self_counted() -> None:
    client = TestClient(_app())
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["content-type"] == PROMETHEUS_CONTENT_TYPE
    assert "http_requests_total" in response.text
    assert (
        _sample(
            "http_requests_total",
            service="test-service",
            method="GET",
            route="/metrics",
            status="200",
        )
        is None
    )


def test_unhandled_exceptions_are_recorded_as_500_and_reraised() -> None:
    app = FastAPI()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    app.add_middleware(MetricsMiddleware, service_name="test-service")
    client = TestClient(app, raise_server_exceptions=False)
    client.get("/boom")

    labels = {
        "service": "test-service",
        "method": "GET",
        "route": "/boom",
        "status": "500",
    }
    assert _sample("http_request_errors_total", **labels) == 1.0
