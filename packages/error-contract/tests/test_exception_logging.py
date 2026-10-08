"""Spec TS-13: both error handlers must log a traceback (logger.exception,
not logger.error), and the Starlette middleware must not attempt a second
ASGI send() once a response has already started -- that masks the real
exception behind an ASGI protocol violation instead of surfacing it."""

import asyncio
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route

from error_contract import ErrorContractMiddleware, register_error_handlers


def test_fastapi_handler_logs_a_traceback(caplog):
    app = FastAPI()
    register_error_handlers(app, service_name="test-service")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        TestClient(app, raise_server_exceptions=False).get("/boom")

    records = [r for r in caplog.records if "Unhandled test-service request failed" in r.message]
    assert records, "expected the unhandled-error log record"
    assert records[0].exc_info is not None


def test_starlette_middleware_logs_a_traceback(caplog):
    async def boom(_request):
        raise RuntimeError("boom")

    app = Starlette(routes=[Route("/boom", boom)])
    app.add_middleware(ErrorContractMiddleware, service_name="test-starlette")

    with caplog.at_level(logging.ERROR):
        TestClient(app, raise_server_exceptions=False).get("/boom")

    records = [r for r in caplog.records if "Unhandled test-starlette request failed" in r.message]
    assert records, "expected the unhandled-error log record"
    assert records[0].exc_info is not None


async def _started_then_boom(scope, receive, send):
    """A raw ASGI app that starts a response, then raises -- simulating a
    handler that fails after the status line is already on the wire."""
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
    )
    await send({"type": "http.response.body", "body": b"partial", "more_body": True})
    raise RuntimeError("boom after response started")


def test_middleware_does_not_double_send_after_response_started():
    """Once http.response.start is already on the wire, the middleware
    must not send a second one -- that hides the real exception behind an
    ASGI protocol violation instead of letting it surface. It should
    re-raise instead."""
    middleware = ErrorContractMiddleware(_started_then_boom, service_name="test-starlette")

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "GET", "path": "/boom", "headers": [], "query_string": b""}

    async def run():
        await middleware(scope, receive, send)

    with pytest.raises(RuntimeError, match="boom after response started"):
        asyncio.run(run())

    start_messages = [m for m in sent if m["type"] == "http.response.start"]
    assert len(start_messages) == 1
