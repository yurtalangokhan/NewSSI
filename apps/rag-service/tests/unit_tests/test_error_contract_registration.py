from error_contract import ApplicationError
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.server import APP


def test_rag_service_registers_standard_error_handlers():
    assert ApplicationError in APP.exception_handlers
    assert RequestValidationError in APP.exception_handlers
    assert Exception in APP.exception_handlers
    # Registered against Starlette's class rather than FastAPI's. FastAPI's
    # HTTPException subclasses it, so this covers both — and, unlike registering
    # the FastAPI class, it also covers the errors the router itself raises.
    assert StarletteHTTPException in APP.exception_handlers
    assert issubclass(HTTPException, StarletteHTTPException)


def test_routing_errors_produce_the_error_envelope():
    response = TestClient(APP).get("/no-such-route")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "request.not_found"
