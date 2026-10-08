"""Shared response shaping helpers for tool modules.

Tool modules (e.g. ``mail_tools``) expose module-level functions that are not
methods on a ``BaseToolCategory`` subclass, yet still need the same
MCP-visible JSON contract. This module re-exports the canonical helpers from
:mod:`core.base` so every tool category shapes responses identically.
"""

from subprocess import TimeoutExpired

from error_contract import (
    ApplicationError,
    InternalServerError,
    OperationExecutionError,
    OperationTimeoutError,
    ValidationFailedError,
    from_httpx_error,
    render_error_message,
)
import httpx

from ..core.base import BaseToolCategory
from ..core.observability import get_logger

logger = get_logger(__name__)

success_response = BaseToolCategory.success_response
error_response = BaseToolCategory.error_response


def tool_error_message(error: Exception) -> str:
    """Translate expected tool failures without exposing driver or filesystem text."""
    if isinstance(error, ApplicationError):
        public = error
    elif isinstance(error, httpx.HTTPError):
        public = from_httpx_error(error)
    elif isinstance(error, (TimeoutError, TimeoutExpired)):
        public = OperationTimeoutError()
    elif isinstance(error, (ValueError, UnicodeError, ArithmeticError, SyntaxError)):
        public = ValidationFailedError()
    elif isinstance(error, OSError):
        public = OperationExecutionError()
    else:
        logger.error("Unexpected tool failure", exc_info=(type(error), error, error.__traceback__))
        public = InternalServerError()
    return render_error_message(public)
