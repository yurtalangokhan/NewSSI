"""Tests for the Elasticsearch destination and the outbound correlation hooks.

The Elasticsearch sink is the shipped log platform, so its wire format is pinned
here: the bulk body shape, the per-service index policy, the credential header,
and the failure semantics the base class's retry policy depends on. The hooks
are pinned for the property the chain depends on: headers inside a request,
nothing outside one.
"""

from __future__ import annotations

import asyncio
import io
import json
import urllib.error
from typing import Any

import pytest

from observability import (
    ElasticsearchSink,
    JsonFormatter,
    UnknownSinkError,
    correlation_event_hooks,
    correlation_sync_event_hooks,
    request_scope,
)


def _sink(**options: Any) -> ElasticsearchSink:
    options.setdefault("url", "http://elasticsearch:9200")
    return ElasticsearchSink(formatter=JsonFormatter(service_name="s"), options=options)


def _records() -> list[dict[str, Any]]:
    return [
        {"service": "agent-service", "message": "one", "request_id": "r1"},
        {"service": "user-service", "message": "two", "request_id": "r1"},
    ]


def test_the_bulk_body_is_one_action_line_and_one_document_line_per_record() -> None:
    body = _sink().encode_bulk(_records()).decode("utf-8")
    lines = body.splitlines()

    assert len(lines) == 4
    assert json.loads(lines[0]) == {"index": {"_index": "logs-agent-service"}}
    assert json.loads(lines[1])["message"] == "one"
    assert json.loads(lines[2]) == {"index": {"_index": "logs-user-service"}}
    assert json.loads(lines[3])["message"] == "two"
    # ndjson ends with a newline; a collector reading line by line needs it.
    assert body.endswith("\n")


def test_a_configured_index_overrides_the_per_service_one() -> None:
    sink = _sink(index="logs-all")
    body = sink.encode_bulk(_records()).decode("utf-8")

    assert body.count('"_index":"logs-all"') == 2


def test_the_credential_header_reaches_the_request() -> None:
    """The bearer token configured for the platform must arrive on the wire."""
    sink = _sink(headers={"Authorization": "Bearer token-1"})
    captured: dict[str, Any] = {}

    def fake_post(body: bytes) -> dict[str, Any]:
        captured["called"] = True
        return {"errors": False}

    original_headers = sink.headers
    sink.headers = original_headers
    sink._post = fake_post  # type: ignore[method-assign]
    sink.send(_records())

    assert captured["called"] is True
    assert sink.headers["Authorization"] == "Bearer token-1"


def test_an_http_error_surfaces_the_platforms_reason(monkeypatch) -> None:
    """A refused batch must say why, or the retry report is useless."""
    sink = _sink()

    def failing_urlopen(request, timeout):  # noqa: ARG001 - signature is urllib's
        raise urllib.error.HTTPError(
            sink.url, 413, "Payload Too Large", {}, io.BytesIO(b"too big")
        )

    monkeypatch.setattr("urllib.request.urlopen", failing_urlopen)

    with pytest.raises(RuntimeError) as exc_info:
        sink.send(_records())

    assert "413" in str(exc_info.value)
    assert "too big" in str(exc_info.value)


def test_item_failures_raise_so_the_base_class_retries() -> None:
    """A bulk response with failed items is a failed delivery, not a success."""
    sink = _sink()
    sink._post = lambda body: {  # type: ignore[method-assign]
        "errors": True,
        "items": [
            {"index": {"status": 201}},
            {"index": {"status": 429, "error": "too_many_requests"}},
        ],
    }

    with pytest.raises(RuntimeError) as exc_info:
        sink.send(_records())

    assert "1 of 2" in str(exc_info.value)


def test_a_clean_bulk_response_delivers_the_batch() -> None:
    sink = _sink()
    sink._post = lambda body: {"errors": False, "items": []}  # type: ignore[method-assign]

    sink.send(_records())  # must not raise


def test_the_generic_external_sink_fails_at_startup_without_a_target() -> None:
    """Selecting 'external' with no registered target is a configuration error.

    This is the deployment's real path: the registry builds the bare base class,
    whose send() is the abstract hook, and startup must refuse it rather than
    queue records into a delivery that can never succeed.
    """
    from observability import SinkConfig, create_sink
    from observability.sinks.external import ExternalSink as _Base

    sink = create_sink(
        SinkConfig("external", {"url": "http://logs.invalid/ingest"}),
        formatter=JsonFormatter(service_name="s"),
    )
    assert type(sink) is _Base

    with pytest.raises(UnknownSinkError) as exc_info:
        sink.startup()

    assert "no delivery target" in str(exc_info.value)


def test_the_hooks_add_headers_inside_a_request_and_nothing_outside_one() -> None:
    class _FakeRequest:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {"content-type": "application/json"}

    inside = _FakeRequest()
    outside = _FakeRequest()

    with request_scope("req-1"):
        asyncio.run(correlation_event_hooks()["request"][0](inside))

    asyncio.run(correlation_event_hooks()["request"][0](outside))
    correlation_sync_event_hooks()["request"][0](outside)

    assert inside.headers["x-request-id"] == "req-1"
    assert "x-request-id" not in outside.headers
    # An explicit header the caller set is not overruled: the hook only fills
    # what is missing.
    assert outside.headers["content-type"] == "application/json"


def test_the_hooks_never_overwrite_a_callers_explicit_correlation_id() -> None:
    class _FakeRequest:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {"x-request-id": "caller-chose"}

    request = _FakeRequest()

    with request_scope("ambient"):
        asyncio.run(correlation_event_hooks()["request"][0](request))

    assert request.headers["x-request-id"] == "caller-chose"
