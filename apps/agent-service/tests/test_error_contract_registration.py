from error_contract import ApplicationError
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError

from app import app


def test_agent_service_registers_standard_error_handlers():
    assert ApplicationError in app.exception_handlers
    assert HTTPException in app.exception_handlers
    assert RequestValidationError in app.exception_handlers
    assert Exception in app.exception_handlers
