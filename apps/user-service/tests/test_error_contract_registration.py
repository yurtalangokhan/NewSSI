from error_contract import ApplicationError
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError

from src.main import create_app


def test_user_service_registers_standard_error_handlers():
    app = create_app()

    assert ApplicationError in app.exception_handlers
    assert HTTPException in app.exception_handlers
    assert RequestValidationError in app.exception_handlers
    assert Exception in app.exception_handlers
