from error_contract import ApplicationError
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError

from langconnect.server import APP


def test_rag_service_registers_standard_error_handlers():
    assert ApplicationError in APP.exception_handlers
    assert HTTPException in APP.exception_handlers
    assert RequestValidationError in APP.exception_handlers
    assert Exception in APP.exception_handlers
