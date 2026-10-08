"""When a request carries no x-request-id/x-correlation-id, the service must
still produce a traceable id rather than leaving request_id null: it is
generated server-side, echoed in the error body, and set as a response
header so it can be correlated with logs even when the caller sent nothing.
"""

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route

from error_contract import ErrorContractMiddleware, NotFoundError, register_error_handlers


def test_request_id_is_generated_when_missing():
    app = FastAPI()
    register_error_handlers(app, service_name="test-service")

    @app.get("/missing")
    async def missing():
        raise NotFoundError()

    response = TestClient(app).get("/missing")

    body_id = response.json()["error"]["request_id"]
    assert body_id is not None
    uuid.UUID(body_id)  # does not raise
    assert response.headers["x-request-id"] == body_id


def test_request_id_from_header_is_preserved_and_echoed_as_response_header():
    app = FastAPI()
    register_error_handlers(app, service_name="test-service")

    @app.get("/missing")
    async def missing():
        raise NotFoundError()

    response = TestClient(app).get("/missing", headers={"X-Request-ID": "req_abc"})

    assert response.json()["error"]["request_id"] == "req_abc"
    assert response.headers["x-request-id"] == "req_abc"


def test_starlette_middleware_generates_request_id_when_missing():
    async def boom(_request):
        raise RuntimeError("boom")

    app = Starlette(routes=[Route("/boom", boom)])
    app.add_middleware(ErrorContractMiddleware, service_name="test-starlette")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")

    body_id = response.json()["error"]["request_id"]
    assert body_id is not None
    uuid.UUID(body_id)  # does not raise
    assert response.headers["x-request-id"] == body_id
