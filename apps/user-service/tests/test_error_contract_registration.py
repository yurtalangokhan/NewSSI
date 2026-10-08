from error_contract import ApplicationError
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.main import create_app


def test_user_service_registers_standard_error_handlers():
    app = create_app()

    assert ApplicationError in app.exception_handlers
    assert RequestValidationError in app.exception_handlers
    assert Exception in app.exception_handlers
    # Registered against Starlette's class rather than FastAPI's. FastAPI's
    # HTTPException subclasses it, so this covers both — and, unlike registering
    # the FastAPI class, it also covers the errors the router itself raises.
    assert StarletteHTTPException in app.exception_handlers
    assert issubclass(HTTPException, StarletteHTTPException)


def test_raised_http_exceptions_produce_the_error_envelope():
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise HTTPException(status_code=409, detail="already exists")

    response = TestClient(app).get("/boom")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "request.conflict"


def test_routing_errors_produce_the_error_envelope():
    response = TestClient(create_app()).get("/no-such-route")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "request.not_found"
